#!/usr/bin/env python3

import html
import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse


DB_PATH = os.environ.get("ATTIC_DB_PATH", "/var/lib/atticd/server.db")
HOST = os.environ.get("ATTIC_OBSERVATORY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ATTIC_OBSERVATORY_PORT", "8088"))


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with connect_db() as conn:
        return list(conn.execute(sql, params))


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with connect_db() as conn:
        return conn.execute(sql, params).fetchone()


def format_int(value) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}"


def format_bytes(value) -> str:
    if value is None:
        return "-"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    if unit == 0:
        return f"{int(size)} {units[unit]}"
    return f"{size:.1f} {units[unit]}"


def page_template(title: str, body: str) -> bytes:
    css = """
    :root {
      color-scheme: light;
      --bg: #f3efe6;
      --panel: #fffdf8;
      --ink: #1e1d19;
      --muted: #6f6a5f;
      --accent: #0b6e4f;
      --accent-2: #d97b29;
      --line: #ddd3bf;
      --danger: #8f1d1d;
      --shadow: 0 10px 30px rgba(37, 27, 7, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iosevka Aile", "IBM Plex Sans", sans-serif;
      background:
        radial-gradient(circle at top right, rgba(217, 123, 41, 0.14), transparent 28%),
        linear-gradient(180deg, #f8f3ea 0%, var(--bg) 100%);
      color: var(--ink);
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .shell {
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px;
    }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 24px;
    }
    .hero h1 {
      margin: 0;
      font-size: 2.2rem;
      line-height: 1;
      letter-spacing: -0.04em;
    }
    .hero p {
      margin: 8px 0 0;
      color: var(--muted);
      max-width: 60ch;
    }
    .badge {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.65);
      border-radius: 999px;
      padding: 10px 14px;
      box-shadow: var(--shadow);
      font-size: 0.95rem;
      color: var(--muted);
    }
    .nav {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }
    .nav a {
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }
    .card, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }
    .card {
      padding: 18px;
    }
    .card .label {
      color: var(--muted);
      font-size: 0.92rem;
      margin-bottom: 6px;
    }
    .card .value {
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: -0.04em;
    }
    .layout {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px;
    }
    .panel {
      padding: 18px;
      overflow: hidden;
    }
    .panel h2 {
      margin: 0 0 14px;
      font-size: 1.1rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.94rem;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-top: 1px solid var(--line);
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 600;
      border-top: 0;
      padding-top: 0;
    }
    code {
      font-family: "Iosevka Term", "IBM Plex Mono", monospace;
      font-size: 0.92em;
      background: #f6f0e2;
      border: 1px solid #eadcbc;
      border-radius: 8px;
      padding: 2px 6px;
      word-break: break-all;
    }
    .mono { font-family: "Iosevka Term", "IBM Plex Mono", monospace; }
    .spark {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(36px, 1fr));
      gap: 8px;
      align-items: end;
      min-height: 180px;
      padding-top: 8px;
    }
    .bar-wrap {
      display: flex;
      flex-direction: column;
      justify-content: end;
      gap: 6px;
      min-height: 100%;
    }
    .bar {
      background: linear-gradient(180deg, var(--accent-2), var(--accent));
      border-radius: 10px 10px 4px 4px;
      min-height: 4px;
    }
    .axis {
      font-size: 0.78rem;
      color: var(--muted);
      writing-mode: vertical-rl;
      transform: rotate(180deg);
      white-space: nowrap;
      height: 80px;
      overflow: hidden;
    }
    .muted { color: var(--muted); }
    .empty {
      padding: 14px;
      border: 1px dashed var(--line);
      border-radius: 12px;
      color: var(--muted);
      background: #fcfaf4;
    }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }
    .kv {
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fcfaf4;
    }
    .kv .k {
      color: var(--muted);
      font-size: 0.82rem;
      margin-bottom: 4px;
    }
    .footer {
      margin-top: 24px;
      color: var(--muted);
      font-size: 0.9rem;
    }
    @media (max-width: 920px) {
      .layout { grid-template-columns: 1fr; }
      .hero { flex-direction: column; align-items: start; }
    }
    """
    markup = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{css}</style>
</head>
<body>
  <div class="shell">
    {body}
  </div>
</body>
</html>
"""
    return markup.encode("utf-8")


def render_nav() -> str:
    return """
    <div class="nav">
      <a href="/">Overview</a>
      <a href="/uploads">Recent Uploads</a>
      <a href="/largest">Largest Objects</a>
    </div>
    """


def parse_json_array(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else [str(parsed)]
    except json.JSONDecodeError:
        return [value]


def render_overview() -> bytes:
    stats = query_one(
        """
        select
          (select count(*) from cache where deleted_at is null) as caches,
          (select count(*) from object) as objects,
          (select count(*) from nar) as nars,
          (select count(*) from chunk) as chunks,
          (select coalesce(sum(nar_size), 0) from nar) as total_nar_bytes,
          (select coalesce(sum(chunk_size), 0) from chunk) as total_chunk_bytes
        """
    )
    cache = query_one("select * from cache where deleted_at is null order by id asc limit 1")
    recent = query_all(
        """
        select
          object.store_path_hash,
          object.store_path,
          object.created_at,
          object.created_by,
          nar.nar_size,
          nar.num_chunks
        from object
        join nar on nar.id = object.nar_id
        order by object.created_at desc
        limit 12
        """
    )
    activity = query_all(
        """
        select
          substr(object.created_at, 1, 13) || ':00' as hour_bucket,
          count(*) as uploads,
          coalesce(sum(nar.nar_size), 0) as nar_bytes
        from object
        join nar on nar.id = object.nar_id
        where object.created_at >= datetime('now', '-24 hours')
        group by hour_bucket
        order by hour_bucket asc
        """
    )
    largest = query_all(
        """
        select object.store_path_hash, object.store_path, object.created_at, nar.nar_size
        from object
        join nar on nar.id = object.nar_id
        order by nar.nar_size desc
        limit 8
        """
    )
    max_uploads = max((row["uploads"] for row in activity), default=1)
    bars = "".join(
        f"""
        <div class="bar-wrap" title="{html.escape(row['hour_bucket'])}: {row['uploads']} uploads, {format_bytes(row['nar_bytes'])}">
          <div class="bar" style="height:{max(8, int((row['uploads'] / max_uploads) * 140))}px"></div>
          <div class="axis">{html.escape(row['hour_bucket'][11:16])}</div>
        </div>
        """
        for row in activity
    ) or '<div class="empty">No uploads in the last 24 hours.</div>'
    recent_rows = "".join(
        f"""
        <tr>
          <td><a class="mono" href="/object/{quote(row['store_path_hash'])}">{html.escape(row['store_path_hash'])}</a></td>
          <td>{html.escape(row['store_path'].split('/')[-1])}</td>
          <td>{format_bytes(row['nar_size'])}</td>
          <td>{html.escape(row['created_at'])}</td>
          <td>{html.escape(row['created_by'] or '-')}</td>
        </tr>
        """
        for row in recent
    )
    largest_rows = "".join(
        f"""
        <tr>
          <td><a href="/object/{quote(row['store_path_hash'])}" class="mono">{html.escape(row['store_path_hash'])}</a></td>
          <td>{html.escape(row['store_path'].split('/')[-1])}</td>
          <td>{format_bytes(row['nar_size'])}</td>
          <td>{html.escape(row['created_at'])}</td>
        </tr>
        """
        for row in largest
    )
    cache_name = cache["name"] if cache else "unknown"
    cache_key = cache["keypair"].split(":")[0] if cache and cache["keypair"] else "-"
    body = f"""
    <div class="hero">
      <div>
        <h1>attic-observatory</h1>
        <p>Operational view into Attic uploads, object growth, and cache contents.</p>
      </div>
      <div class="badge">DB: <code>{html.escape(DB_PATH)}</code></div>
    </div>
    {render_nav()}
    <div class="cards">
      <div class="card"><div class="label">Cache</div><div class="value">{html.escape(cache_name)}</div></div>
      <div class="card"><div class="label">Objects</div><div class="value">{format_int(stats['objects'])}</div></div>
      <div class="card"><div class="label">NARs</div><div class="value">{format_int(stats['nars'])}</div></div>
      <div class="card"><div class="label">Chunks</div><div class="value">{format_int(stats['chunks'])}</div></div>
      <div class="card"><div class="label">Logical Size</div><div class="value">{format_bytes(stats['total_nar_bytes'])}</div></div>
      <div class="card"><div class="label">Stored Chunks</div><div class="value">{format_bytes(stats['total_chunk_bytes'])}</div></div>
    </div>
    <div class="layout">
      <div class="panel">
        <h2>Recent Uploads</h2>
        <table>
          <thead>
            <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Created</th><th>Created By</th></tr>
          </thead>
          <tbody>{recent_rows}</tbody>
        </table>
      </div>
      <div class="panel">
        <h2>24h Upload Activity</h2>
        <div class="muted">Grouped by hour. Hover bars for counts and bytes.</div>
        <div class="spark">{bars}</div>
      </div>
    </div>
    <div class="layout" style="margin-top:16px;">
      <div class="panel">
        <h2>Largest Objects</h2>
        <table>
          <thead>
            <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Created</th></tr>
          </thead>
          <tbody>{largest_rows}</tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Cache Settings</h2>
        <div class="detail-grid">
          <div class="kv"><div class="k">Public Key Prefix</div><div class="mono">{html.escape(cache_key)}</div></div>
          <div class="kv"><div class="k">Priority</div><div>{format_int(cache['priority'] if cache else None)}</div></div>
          <div class="kv"><div class="k">Store Directory</div><div><code>{html.escape(cache['store_dir'] if cache else '-')}</code></div></div>
          <div class="kv"><div class="k">Upstream Keys</div><div>{html.escape(", ".join(parse_json_array(cache['upstream_cache_key_names'] if cache else None)) or "-")}</div></div>
          <div class="kv"><div class="k">Created At</div><div>{html.escape(cache['created_at'] if cache else '-')}</div></div>
          <div class="kv"><div class="k">Retention Period</div><div>{format_int(cache['retention_period'] if cache else None)}</div></div>
        </div>
      </div>
    </div>
    <div class="footer">Source schema: <code>cache</code>, <code>object</code>, <code>nar</code>, <code>chunk</code>, <code>chunkref</code>.</div>
    """
    return page_template("attic-observatory", body)


def render_uploads(query: dict[str, list[str]]) -> bytes:
    limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
    rows = query_all(
        """
        select
          object.store_path_hash,
          object.store_path,
          object."references" as "references",
          object.system,
          object.deriver,
          object.sigs,
          object.created_at,
          object.created_by,
          nar.nar_size,
          nar.num_chunks,
          nar.compression
        from object
        join nar on nar.id = object.nar_id
        order by object.created_at desc
        limit ?
        """,
        (limit,),
    )
    body_rows = "".join(
        f"""
        <tr>
          <td><a class="mono" href="/object/{quote(row['store_path_hash'])}">{html.escape(row['store_path_hash'])}</a></td>
          <td>{html.escape(row['store_path'])}</td>
          <td>{format_bytes(row['nar_size'])}</td>
          <td>{format_int(row['num_chunks'])}</td>
          <td>{html.escape(row['compression'])}</td>
          <td>{html.escape(row['created_at'])}</td>
          <td>{html.escape(row['created_by'] or '-')}</td>
        </tr>
        """
        for row in rows
    )
    body = f"""
    <div class="hero">
      <div>
        <h1>Recent Uploads</h1>
        <p>Newest objects accepted by the cache.</p>
      </div>
      <div class="badge">Showing {format_int(limit)} rows</div>
    </div>
    {render_nav()}
    <div class="panel">
      <table>
        <thead>
          <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Chunks</th><th>Compression</th><th>Created</th><th>Created By</th></tr>
        </thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>
    """
    return page_template("Recent Uploads", body)


def render_largest() -> bytes:
    rows = query_all(
        """
        select
          object.store_path_hash,
          object.store_path,
          object.created_at,
          nar.nar_size,
          nar.num_chunks,
          object.created_by
        from object
        join nar on nar.id = object.nar_id
        order by nar.nar_size desc
        limit 100
        """
    )
    body_rows = "".join(
        f"""
        <tr>
          <td><a class="mono" href="/object/{quote(row['store_path_hash'])}">{html.escape(row['store_path_hash'])}</a></td>
          <td>{html.escape(row['store_path'])}</td>
          <td>{format_bytes(row['nar_size'])}</td>
          <td>{format_int(row['num_chunks'])}</td>
          <td>{html.escape(row['created_at'])}</td>
          <td>{html.escape(row['created_by'] or '-')}</td>
        </tr>
        """
        for row in rows
    )
    body = f"""
    <div class="hero">
      <div>
        <h1>Largest Objects</h1>
        <p>Top 100 store paths by NAR size.</p>
      </div>
    </div>
    {render_nav()}
    <div class="panel">
      <table>
        <thead>
          <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Chunks</th><th>Created</th><th>Created By</th></tr>
        </thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>
    """
    return page_template("Largest Objects", body)


def render_object_detail(store_hash: str) -> bytes:
    row = query_one(
        """
        select
          object.*,
          nar.nar_hash,
          nar.nar_size,
          nar.compression,
          nar.num_chunks,
          nar.state as nar_state,
          nar.completeness_hint
        from object
        join nar on nar.id = object.nar_id
        where object.store_path_hash = ?
        """,
        (store_hash,),
    )
    if row is None:
        return page_template(
            "Object Not Found",
            f"""
            <div class="hero"><div><h1>Object Not Found</h1><p>No object matched <code>{html.escape(store_hash)}</code>.</p></div></div>
            {render_nav()}
            """,
        )
    refs = parse_json_array(row["references"])
    sigs = parse_json_array(row["sigs"])
    chunks = query_all(
        """
        select chunkref.seq, chunk.chunk_hash, chunk.chunk_size, chunk.created_at, chunk.remote_file_id
        from chunkref
        left join chunk on chunk.id = chunkref.chunk_id
        where chunkref.nar_id = ?
        order by chunkref.seq asc
        limit 50
        """,
        (row["nar_id"],),
    )
    ref_list = "".join(f"<li><code>{html.escape(ref)}</code></li>" for ref in refs) or "<li class='muted'>None</li>"
    sig_list = "".join(f"<li><code>{html.escape(sig)}</code></li>" for sig in sigs) or "<li class='muted'>None</li>"
    chunk_rows = "".join(
        f"""
        <tr>
          <td>{format_int(chunk['seq'])}</td>
          <td><code>{html.escape((chunk['chunk_hash'] or '-'))}</code></td>
          <td>{format_bytes(chunk['chunk_size'])}</td>
          <td>{html.escape(chunk['created_at'] or '-')}</td>
          <td><code>{html.escape(chunk['remote_file_id'] or '-')}</code></td>
        </tr>
        """
        for chunk in chunks
    )
    body = f"""
    <div class="hero">
      <div>
        <h1>Object Detail</h1>
        <p class="mono">{html.escape(row['store_path'])}</p>
      </div>
      <div class="badge"><a href="/uploads">Back to uploads</a></div>
    </div>
    {render_nav()}
    <div class="panel">
      <div class="detail-grid">
        <div class="kv"><div class="k">Store Path Hash</div><div><code>{html.escape(row['store_path_hash'])}</code></div></div>
        <div class="kv"><div class="k">Created At</div><div>{html.escape(row['created_at'])}</div></div>
        <div class="kv"><div class="k">Created By</div><div>{html.escape(row['created_by'] or '-')}</div></div>
        <div class="kv"><div class="k">System</div><div>{html.escape(row['system'] or '-')}</div></div>
        <div class="kv"><div class="k">Deriver</div><div><code>{html.escape(row['deriver'] or '-')}</code></div></div>
        <div class="kv"><div class="k">NAR Size</div><div>{format_bytes(row['nar_size'])}</div></div>
        <div class="kv"><div class="k">Compression</div><div>{html.escape(row['compression'])}</div></div>
        <div class="kv"><div class="k">NAR Chunks</div><div>{format_int(row['num_chunks'])}</div></div>
        <div class="kv"><div class="k">NAR State</div><div>{html.escape(row['nar_state'])}</div></div>
        <div class="kv"><div class="k">NAR Hash</div><div><code>{html.escape(row['nar_hash'])}</code></div></div>
      </div>
    </div>
    <div class="layout" style="margin-top:16px;">
      <div class="panel">
        <h2>References</h2>
        <ul>{ref_list}</ul>
      </div>
      <div class="panel">
        <h2>Signatures</h2>
        <ul>{sig_list}</ul>
      </div>
    </div>
    <div class="panel" style="margin-top:16px;">
      <h2>Chunk Map</h2>
      <table>
        <thead>
          <tr><th>Seq</th><th>Chunk Hash</th><th>Chunk Size</th><th>Chunk Created</th><th>Remote File</th></tr>
        </thead>
        <tbody>{chunk_rows}</tbody>
      </table>
    </div>
    """
    return page_template(f"Object {store_hash}", body)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        try:
            if route == "/":
                self.respond(200, render_overview())
            elif route == "/uploads":
                self.respond(200, render_uploads(query))
            elif route == "/largest":
                self.respond(200, render_largest())
            elif route.startswith("/object/"):
                self.respond(200, render_object_detail(route.split("/", 2)[2]))
            else:
                self.respond(404, page_template("Not Found", f"<div class='hero'><div><h1>Not Found</h1><p>{html.escape(route)}</p></div></div>{render_nav()}"))
        except sqlite3.Error as exc:
            self.respond(500, page_template("Database Error", f"<div class='hero'><div><h1>Database Error</h1><p><code>{html.escape(str(exc))}</code></p></div></div>"))

    def respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"attic-observatory listening on http://{HOST}:{PORT} using {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
