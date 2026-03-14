# attic-observatory

Lightweight web UI for inspecting an Attic binary cache.

## Features

- Overview cards for cache, object, NAR, and chunk counts
- Recent uploads table
- Upload activity over time
- Largest objects table
- Object detail page with references and signatures

## Requirements

- Python 3.11+
- Read access to an Attic SQLite database, typically `/var/lib/atticd/server.db`

## Run

```bash
export ATTIC_DB_PATH=/var/lib/atticd/server.db
python3 app.py
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

## Default Ports

- App listen port: `8088`
- Suggested nginx proxy port: `8082`

With the matching NixOS service and nginx config, the UI will be visible at:

```bash
http://attic-cache:8082/
```
