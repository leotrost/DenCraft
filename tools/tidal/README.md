# TIDAL curator

A small CLI (`tools/tidal/tidal`) over the unofficial [`tidalapi`](https://github.com/tamland/python-tidal)
library so Claude Code can build and maintain playlists in your TIDAL account.
The matching skill is `.claude/skills/tidal-curate` — ask Claude something like
*"make me a TIDAL playlist for a rainy Sunday morning"* or run `/tidal-curate`.

## One-time setup

1. **Log in** (on your own computer is easiest; needs Python 3.9+):
   ```sh
   tools/tidal/tidal login          # open the printed link, approve the device
   tools/tidal/tidal whoami         # sanity check
   ```
   This stores tokens in `~/.config/tidal-curator/session.json` (mode 600).

2. **For Claude Code on the web**, the container is fresh each session, so give it the
   session via an env var:
   ```sh
   tools/tidal/tidal export-session   # prints one JSON line
   ```
   In the cloud environment's settings, add an environment variable
   `TIDAL_SESSION` with that JSON as its value. Treat it like a password — it
   grants write access to your TIDAL library. The refresh token keeps it working;
   re-run these steps if TIDAL ever revokes it.

3. **Network access**: allow `api.tidal.com`, `auth.tidal.com`, and `listen.tidal.com`
   in the environment's network settings (PyPI access is also needed to install `tidalapi`).

## Commands

| command | what it does |
|---|---|
| `whoami` | logged-in user |
| `search "<q>" [--type track\|artist\|album\|playlist]` | catalog search |
| `resolve "Artist - Title" ...` (or lines on stdin) | best-match track IDs |
| `favorites [--type tracks\|artists\|albums]` | your favorites |
| `playlists` / `tracks <playlist_id>` | your playlists / their tracks |
| `artist-top <id>`, `similar <id>`, `radio <track_id>` | discovery |
| `create "<name>" [--description] [--tracks ids...]` | new playlist (tagged `[curated by Claude]`) |
| `add` / `remove <playlist_id> <track_ids...>`, `clear`, `edit` | modify your playlists |

All output is JSON on stdout.
