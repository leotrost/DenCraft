---
name: tidal-curate
description: Curate the user's TIDAL playlists — build a new playlist from a vibe/prompt, refresh an existing one, or prune it. Use when the user asks to make, update, or tune a TIDAL playlist.
---

# Curating TIDAL playlists

All TIDAL access goes through `tools/tidal/tidal <command>` (run from the repo root).
It creates its own venv on first run and prints JSON. `tools/tidal/tidal --help` lists commands.

## Preflight
1. `tools/tidal/tidal whoami`. If it errors with "Not logged in" / "expired", stop and tell the
   user to refresh the `TIDAL_SESSION` env var (see `tools/tidal/README.md`). Never try to
   print or echo token values.
2. If requests to `*.tidal.com` fail with a proxy 403, the environment's network policy needs
   `api.tidal.com`, `auth.tidal.com` and `listen.tidal.com` allowed; tell the user.

## Gather taste signals
- `favorites --type tracks|artists --limit 100` — what the user actually likes.
- `playlists`, then `tracks <id>` on a few — existing taste and what to avoid repeating.
- `similar <artist_id>`, `artist-top <artist_id>`, `radio <track_id>` — expand from seeds.
- `search "<query>"` / `resolve "Artist - Title" ...` — turn your own song ideas into IDs.

## Build
- New: `create "<name>" --description "<one line on the vibe>" --tracks <ids...>`.
  The tool appends `[curated by Claude]` to the description; `playlists` reports those as
  `"managed": true`.
- Existing: `add <playlist_id> <ids...>`, `remove <playlist_id> <ids...>`, `edit`, `clear`.

## Rules
- Only modify playlists with `"managed": true` unless the user names a specific other playlist.
  Never `clear` or bulk-remove on a non-managed playlist without explicit confirmation.
- Aim for ~25–40 tracks unless asked otherwise; avoid more than 2–3 tracks per artist;
  mix familiar favorites with discoveries (roughly 30/70) and skip tracks already in the target.
- Check that `resolve` matches are the right song (artist + title), not a cover or karaoke version.
- Finish by reporting the playlist name, track count, and a short list of highlights.
