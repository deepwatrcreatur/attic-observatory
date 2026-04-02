# attic-observatory

Lightweight web UI for inspecting an Attic binary cache.

## Features

- Overview cards for cache, object, NAR, and chunk counts
- Recent uploads table
- Upload activity over time
- Largest objects table
- Object detail page with references and signatures
- Built-in themes with a query-string theme switcher

## Requirements

- Python 3.11+
- Read access to an Attic SQLite database, typically `/var/lib/atticd/server.db`

## Run

For an ephemeral run from the flake:

```bash
nix run github:deepwatrcreatur/attic-observatory
```

Or from a local checkout:

```bash
nix run .
```

The packaged app still expects the Attic database path via environment variables:

```bash
export ATTIC_DB_PATH=/var/lib/atticd/server.db
export ATTIC_OBSERVATORY_THEME=sugarplum
nix run .
```

Then open `http://127.0.0.1:8088`.

You can override the bind address and port:

```bash
ATTIC_OBSERVATORY_HOST=0.0.0.0 ATTIC_OBSERVATORY_PORT=8088 python3 app.py
```

## Suggested deployment on attic-cache

```bash
ssh attic-cache
cd ~/flakes/attic-observatory
git pull
ATTIC_DB_PATH=/var/lib/atticd/server.db python3 app.py
```

For a persistent deployment, wrap it in a systemd service or reverse proxy it behind nginx.

## Development

Run the built-in unit tests with:

```bash
nix flake check
```

Or enter the dev shell and work directly with Python:

```bash
nix develop
python3 -m unittest -v test_app.py
```

## Default Ports

- App listen port: `8088`
- Suggested nginx proxy port: `8082`
- Default theme: `sugarplum`

With the matching NixOS service and nginx config, the UI will be visible at:

```bash
http://attic-cache:8082/
```

## Themes

Available themes:

- `sugarplum`
- `x-dark`
- `catppuccin-latte`
- `gruvbox-light`
- `nord`
- `solarized-light`

You can switch themes with a query parameter:

```bash
http://attic-cache:8082/?theme=x-dark
```
