#!/usr/bin/env python3
"""Small TIDAL CLI for letting Claude Code curate playlists.

Every command prints JSON to stdout so it is easy for an agent to read.

Credentials (first match wins):
  1. TIDAL_SESSION env var  - JSON produced by `export-session`
  2. session file           - $TIDAL_SESSION_FILE or ~/.config/tidal-curator/session.json

Run `login` once (device-code flow: open the printed link, approve), then
`export-session` to get the value to store as TIDAL_SESSION in a cloud env.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import tidalapi

SESSION_FILE = Path(
    os.environ.get(
        "TIDAL_SESSION_FILE",
        Path.home() / ".config" / "tidal-curator" / "session.json",
    )
)
# Tag added to descriptions of playlists this tool creates, so Claude can
# tell its own playlists apart from the user's hand-made ones.
MANAGED_TAG = "[curated by Claude]"


def out(obj):
    json.dump(obj, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def die(msg, code=1):
    out({"error": msg})
    sys.exit(code)


# --- serialization -----------------------------------------------------------

def track_dict(t):
    return {
        "id": t.id,
        "name": t.name,
        "artists": [a.name for a in (t.artists or [])],
        "album": t.album.name if t.album else None,
        "duration_s": t.duration,
        "popularity": getattr(t, "popularity", None),
        "explicit": getattr(t, "explicit", None),
    }


def artist_dict(a):
    return {"id": a.id, "name": a.name}


def album_dict(a):
    return {
        "id": a.id,
        "name": a.name,
        "artist": a.artist.name if a.artist else None,
        "year": a.year,
    }


def playlist_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "num_tracks": p.num_tracks,
        "managed": bool(p.description and MANAGED_TAG in p.description),
        "editable": isinstance(p, tidalapi.UserPlaylist),
    }


# --- session handling --------------------------------------------------------

def session_to_dict(s):
    return {
        "token_type": s.token_type,
        "access_token": s.access_token,
        "refresh_token": s.refresh_token,
    }


def save_session(s):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(session_to_dict(s)))
    SESSION_FILE.chmod(0o600)


def load_creds():
    raw = os.environ.get("TIDAL_SESSION")
    if raw:
        return json.loads(raw)
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return None


def get_session():
    creds = load_creds()
    if not creds:
        die("Not logged in. Run `login` (or set TIDAL_SESSION).", 2)
    s = tidalapi.Session()
    ok = False
    try:
        ok = s.load_oauth_session(
            creds.get("token_type", "Bearer"),
            creds["access_token"],
            creds.get("refresh_token"),
        )
    except Exception:
        ok = False
    if not ok and creds.get("refresh_token"):
        # Access token is stale: refresh explicitly and retry.
        if s.token_refresh(creds["refresh_token"]):
            ok = s.load_oauth_session(s.token_type, s.access_token, s.refresh_token)
    if not ok:
        die("TIDAL session invalid or expired. Run `login` again.", 2)
    if not os.environ.get("TIDAL_SESSION"):
        save_session(s)  # persist refreshed tokens locally
    return s


def user_playlist(s, playlist_id):
    p = s.playlist(playlist_id)
    if not isinstance(p, tidalapi.UserPlaylist):
        die(f"Playlist {playlist_id} is not owned by you and can't be edited.")
    return p


# --- commands ----------------------------------------------------------------

def cmd_login(args):
    s = tidalapi.Session()
    login, future = s.login_oauth()
    link = login.verification_uri_complete
    if not link.startswith("http"):
        link = "https://" + link
    print(f"Open this link and approve access: {link}", file=sys.stderr)
    print(f"(code {login.user_code}, expires in {int(login.expires_in)}s)", file=sys.stderr)
    future.result()
    if not s.check_login():
        die("Login failed.")
    save_session(s)
    out({"ok": True, "user_id": s.user.id, "session_file": str(SESSION_FILE)})


def cmd_export_session(args):
    s = get_session()
    # Printed raw so it can be pasted straight into an env var.
    print(json.dumps(session_to_dict(s)))


def cmd_whoami(args):
    s = get_session()
    u = s.user
    out({"id": u.id, "username": getattr(u, "username", None), "country": s.country_code})


SEARCH_MODELS = {
    "track": (tidalapi.Track, "tracks", track_dict),
    "artist": (tidalapi.Artist, "artists", artist_dict),
    "album": (tidalapi.Album, "albums", album_dict),
    "playlist": (tidalapi.Playlist, "playlists", playlist_dict),
}


def cmd_search(args):
    s = get_session()
    model, key, fn = SEARCH_MODELS[args.type]
    res = s.search(args.query, models=[model], limit=args.limit)
    out([fn(x) for x in res.get(key, [])])


def cmd_resolve(args):
    """Map free-text 'Artist - Title' lines to TIDAL track IDs (best match)."""
    s = get_session()
    lines = args.songs or [l for l in sys.stdin.read().splitlines()]
    results = []
    for line in (l.strip() for l in lines):
        if not line:
            continue
        hits = s.search(line.replace(" - ", " "), models=[tidalapi.Track], limit=5).get("tracks", [])
        results.append({
            "query": line,
            "match": track_dict(hits[0]) if hits else None,
            "alternatives": [track_dict(h) for h in hits[1:3]],
        })
    out(results)


def cmd_favorites(args):
    s = get_session()
    fav = s.user.favorites
    if args.type == "tracks":
        out([track_dict(t) for t in fav.tracks(limit=args.limit)])
    elif args.type == "artists":
        out([artist_dict(a) for a in fav.artists(limit=args.limit)])
    else:
        out([album_dict(a) for a in fav.albums(limit=args.limit)])


def cmd_playlists(args):
    s = get_session()
    out([playlist_dict(p) for p in s.user.playlists()])


def cmd_tracks(args):
    s = get_session()
    p = s.playlist(args.playlist_id)
    tracks = []
    while len(tracks) < args.limit:  # TIDAL pages at 100 items
        page = p.tracks(limit=min(100, args.limit - len(tracks)), offset=len(tracks))
        tracks += page
        if not page:
            break
    out({"playlist": playlist_dict(p), "tracks": [track_dict(t) for t in tracks]})


def cmd_artist_top(args):
    s = get_session()
    out([track_dict(t) for t in s.artist(args.artist_id).get_top_tracks(limit=args.limit)])


def cmd_similar(args):
    s = get_session()
    out([artist_dict(a) for a in s.artist(args.artist_id).get_similar()])


def cmd_radio(args):
    s = get_session()
    out([track_dict(t) for t in s.track(args.track_id).get_track_radio(limit=args.limit)])


def cmd_create(args):
    s = get_session()
    desc = f"{args.description} {MANAGED_TAG}".strip()
    p = s.user.create_playlist(args.name, desc)
    added = p.add([str(t) for t in args.tracks]) if args.tracks else []
    out({"playlist": playlist_dict(s.playlist(p.id)), "added": len(added)})


def cmd_add(args):
    s = get_session()
    p = user_playlist(s, args.playlist_id)
    added = p.add([str(t) for t in args.tracks], allow_duplicates=args.allow_duplicates)
    out({"added": len(added), "playlist": playlist_dict(s.playlist(p.id))})


def cmd_remove(args):
    s = get_session()
    p = user_playlist(s, args.playlist_id)
    ok = p.delete_by_id([str(t) for t in args.tracks])
    out({"ok": ok, "playlist": playlist_dict(s.playlist(p.id))})


def cmd_clear(args):
    s = get_session()
    p = user_playlist(s, args.playlist_id)
    out({"ok": p.clear()})


def cmd_edit(args):
    s = get_session()
    p = user_playlist(s, args.playlist_id)
    desc = args.description
    if desc is not None and MANAGED_TAG in (p.description or "") and MANAGED_TAG not in desc:
        desc = f"{desc} {MANAGED_TAG}".strip()
    out({"ok": p.edit(title=args.name, description=desc)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help):
        p = sub.add_parser(name, help=help)
        p.set_defaults(fn=fn)
        return p

    add("login", cmd_login, "device-code login; saves session file")
    add("export-session", cmd_export_session, "print session JSON for the TIDAL_SESSION env var")
    add("whoami", cmd_whoami, "show logged-in user")

    p = add("search", cmd_search, "search the catalog")
    p.add_argument("query")
    p.add_argument("--type", choices=SEARCH_MODELS, default="track")
    p.add_argument("--limit", type=int, default=10)

    p = add("resolve", cmd_resolve, "map 'Artist - Title' strings (args or stdin lines) to track IDs")
    p.add_argument("songs", nargs="*")

    p = add("favorites", cmd_favorites, "list favorited tracks/artists/albums")
    p.add_argument("--type", choices=["tracks", "artists", "albums"], default="tracks")
    p.add_argument("--limit", type=int, default=50)

    add("playlists", cmd_playlists, "list your playlists")

    p = add("tracks", cmd_tracks, "list tracks in a playlist")
    p.add_argument("playlist_id")
    p.add_argument("--limit", type=int, default=500)

    p = add("artist-top", cmd_artist_top, "an artist's top tracks")
    p.add_argument("artist_id")
    p.add_argument("--limit", type=int, default=10)

    p = add("similar", cmd_similar, "artists similar to an artist")
    p.add_argument("artist_id")

    p = add("radio", cmd_radio, "track radio (tracks similar to a track)")
    p.add_argument("track_id")
    p.add_argument("--limit", type=int, default=25)

    p = add("create", cmd_create, "create a playlist, optionally with tracks")
    p.add_argument("name")
    p.add_argument("--description", default="")
    p.add_argument("--tracks", nargs="*", default=[])

    p = add("add", cmd_add, "add track IDs to a playlist")
    p.add_argument("playlist_id")
    p.add_argument("tracks", nargs="+")
    p.add_argument("--allow-duplicates", action="store_true")

    p = add("remove", cmd_remove, "remove track IDs from a playlist")
    p.add_argument("playlist_id")
    p.add_argument("tracks", nargs="+")

    p = add("clear", cmd_clear, "remove all tracks from a playlist")
    p.add_argument("playlist_id")

    p = add("edit", cmd_edit, "rename / re-describe a playlist")
    p.add_argument("playlist_id")
    p.add_argument("--name")
    p.add_argument("--description")

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
