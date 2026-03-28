#!/usr/bin/env python3

import html
import json
import os
import re
import sqlite3
import sys
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlparse, urlsplit, urlunsplit


DB_PATH = os.environ.get("ATTIC_DB_PATH", "/var/lib/atticd/server.db")
HOST = os.environ.get("ATTIC_OBSERVATORY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ATTIC_OBSERVATORY_PORT", "8088"))
DB_IMMUTABLE = os.environ.get("ATTIC_DB_IMMUTABLE", "").strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_THEME = os.environ.get("ATTIC_OBSERVATORY_THEME", "x-dark").strip().lower()
STORE_PATH_HASH_RE = re.compile(r"^[0-9a-df-np-sv-z]{32}$")

THEMES = {
    "sugarplum": {
        "name": "Sugarplum",
        "mode": "dark",
        "bg": "#111147",
        "bg_secondary": "#1c1a63",
        "panel": "#1a175f",
        "panel_alt": "#201d6a",
        "ink": "#f9f3f9",
        "muted": "#d0beee",
        "accent": "#53b397",
        "accent_2": "#db7ddd",
        "line": "#5ca8dc",
        "code_bg": "#15124f",
        "code_line": "#7a57b2",
        "shadow": "0 18px 40px rgba(1, 0, 27, 0.42)",
        "gradient_a": "rgba(250, 93, 253, 0.25)",
        "gradient_b": "rgba(83, 179, 151, 0.18)",
        "danger": "#ff7aa2",
    },
    "catppuccin-latte": {
        "name": "Catppuccin Latte",
        "mode": "light",
        "bg": "#eff1f5",
        "bg_secondary": "#e6e9ef",
        "panel": "#ffffff",
        "panel_alt": "#f5f7fb",
        "ink": "#4c4f69",
        "muted": "#7c7f93",
        "accent": "#1e66f5",
        "accent_2": "#ea76cb",
        "line": "#bcc0cc",
        "code_bg": "#eff1f5",
        "code_line": "#ccd0da",
        "shadow": "0 10px 26px rgba(76, 79, 105, 0.10)",
        "gradient_a": "rgba(30, 102, 245, 0.12)",
        "gradient_b": "rgba(234, 118, 203, 0.10)",
        "danger": "#d20f39",
    },
    "gruvbox-light": {
        "name": "Gruvbox Light",
        "mode": "light",
        "bg": "#fbf1c7",
        "bg_secondary": "#f2e5bc",
        "panel": "#fff8d8",
        "panel_alt": "#f8edc9",
        "ink": "#3c3836",
        "muted": "#7c6f64",
        "accent": "#98971a",
        "accent_2": "#d79921",
        "line": "#d5c4a1",
        "code_bg": "#f2e5bc",
        "code_line": "#d5c4a1",
        "shadow": "0 10px 26px rgba(60, 56, 54, 0.10)",
        "gradient_a": "rgba(152, 151, 26, 0.12)",
        "gradient_b": "rgba(215, 153, 33, 0.10)",
        "danger": "#cc241d",
    },
    "nord": {
        "name": "Nord",
        "mode": "dark",
        "bg": "#2e3440",
        "bg_secondary": "#3b4252",
        "panel": "#3b4252",
        "panel_alt": "#434c5e",
        "ink": "#eceff4",
        "muted": "#d8dee9",
        "accent": "#88c0d0",
        "accent_2": "#b48ead",
        "line": "#4c566a",
        "code_bg": "#2b303b",
        "code_line": "#4c566a",
        "shadow": "0 18px 40px rgba(15, 17, 21, 0.28)",
        "gradient_a": "rgba(136, 192, 208, 0.16)",
        "gradient_b": "rgba(180, 142, 173, 0.14)",
        "danger": "#bf616a",
    },
    "x-dark": {
        "name": "X Dark",
        "mode": "dark",
        "bg": "#000000",
        "bg_secondary": "#0f0f10",
        "panel": "#16181c",
        "panel_alt": "#111317",
        "ink": "#e7e9ea",
        "muted": "#71767b",
        "accent": "#1d9bf0",
        "accent_2": "#8b98a5",
        "line": "#2f3336",
        "code_bg": "#0f1114",
        "code_line": "#2f3336",
        "shadow": "0 18px 40px rgba(0, 0, 0, 0.45)",
        "gradient_a": "rgba(29, 155, 240, 0.10)",
        "gradient_b": "rgba(139, 152, 165, 0.08)",
        "danger": "#f4212e",
    },
    "solarized-light": {
        "name": "Solarized Light",
        "mode": "light",
        "bg": "#fdf6e3",
        "bg_secondary": "#eee8d5",
        "panel": "#fffdf4",
        "panel_alt": "#f7f0de",
        "ink": "#073642",
        "muted": "#657b83",
        "accent": "#2aa198",
        "accent_2": "#b58900",
        "line": "#93a1a1",
        "code_bg": "#eee8d5",
        "code_line": "#93a1a1",
        "shadow": "0 10px 26px rgba(7, 54, 66, 0.10)",
        "gradient_a": "rgba(42, 161, 152, 0.14)",
        "gradient_b": "rgba(181, 137, 0, 0.10)",
        "danger": "#dc322f",
    },
}

if DEFAULT_THEME not in THEMES:
    warnings.warn(f"Unknown theme '{DEFAULT_THEME}', falling back to 'x-dark'", stacklevel=1)


def get_theme(theme_name: str | None) -> tuple[str, dict]:
    key = (theme_name or DEFAULT_THEME or "x-dark").strip().lower()
    if key not in THEMES:
        key = "x-dark"
    return key, THEMES[key]


def with_theme(path: str, theme_key: str) -> str:
    split = urlsplit(path)
    safe_path = "/" + split.path.lstrip("/")
    query = [(key, value) for key, value in parse_qsl(split.query, keep_blank_values=True) if key != "theme"]
    query.append(("theme", theme_key))
    return urlunsplit(("", "", safe_path, urlencode(query), split.fragment))


def connect_db() -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode=ro"
    if DB_IMMUTABLE:
        uri += "&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
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


def page_template(title: str, body: str, theme_key: str) -> bytes:
    _, theme = get_theme(theme_key)
    css = """
    :root {{
      color-scheme: {mode};
      --bg: {bg};
      --bg-secondary: {bg_secondary};
      --panel: {panel};
      --panel-alt: {panel_alt};
      --ink: {ink};
      --muted: {muted};
      --accent: {accent};
      --accent-2: {accent_2};
      --line: {line};
      --danger: {danger};
      --code-bg: {code_bg};
      --code-line: {code_line};
      --shadow: {shadow};
      --gradient-a: {gradient_a};
      --gradient-b: {gradient_b};
      --panel-glow: color-mix(in srgb, var(--accent) 12%, transparent);
      --accent-soft: color-mix(in srgb, var(--accent) 16%, var(--panel));
      --accent-strong: color-mix(in srgb, var(--accent) 72%, white 8%);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iosevka Aile", "IBM Plex Sans", sans-serif;
      background:
        linear-gradient(color-mix(in srgb, var(--bg) 90%, transparent), color-mix(in srgb, var(--bg-secondary) 94%, transparent)),
        radial-gradient(circle at top right, var(--gradient-a), transparent 24%),
        radial-gradient(circle at bottom left, var(--gradient-b), transparent 28%),
        repeating-linear-gradient(0deg, transparent, transparent 71px, color-mix(in srgb, var(--line) 35%, transparent) 71px, color-mix(in srgb, var(--line) 35%, transparent) 72px),
        repeating-linear-gradient(90deg, transparent, transparent 71px, color-mix(in srgb, var(--line) 35%, transparent) 71px, color-mix(in srgb, var(--line) 35%, transparent) 72px),
        linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg) 100%);
      color: var(--ink);
      min-height: 100vh;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 28px 24px 40px;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: stretch;
      margin-bottom: 24px;
    }}
    .hero-main, .hero-aside {{
      background: color-mix(in srgb, var(--panel) 88%, transparent);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}
    .hero-main {{
      flex: 1 1 auto;
      padding: 26px;
      min-width: 0;
    }}
    .hero-aside {{
      flex: 0 0 320px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 14px;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      color: var(--accent-strong);
      font-size: 0.82rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(2.2rem, 5vw, 3.4rem);
      line-height: 0.96;
      letter-spacing: -0.04em;
    }}
    .hero p {{
      margin: 12px 0 0;
      color: var(--muted);
      max-width: 64ch;
      font-size: 1rem;
      line-height: 1.55;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel-alt) 88%, transparent);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 0.92rem;
      color: var(--muted);
    }}
    .hero-stats {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .hero-stat {{
      background: var(--panel-alt);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
    }}
    .hero-stat .label {{
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 6px;
    }}
    .hero-stat .value {{
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      word-break: break-word;
    }}
    .nav-grid {{
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }}
    .nav-panel {{
      padding: 20px;
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .nav-kicker {{
      margin: 0 0 8px;
      font-size: 0.78rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent-strong);
    }}
    .nav-panel h2 {{
      margin: 0 0 8px;
      font-size: 1.12rem;
    }}
    .nav-note {{
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 0.95rem;
      max-width: 48ch;
      line-height: 1.5;
    }}
    .nav {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .nav a {{
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel-alt) 86%, transparent);
      transition: transform 120ms ease, border-color 120ms ease, background 120ms ease, box-shadow 120ms ease;
    }}
    .nav a:hover {{
      text-decoration: none;
      transform: translateY(-1px);
      border-color: var(--accent);
      box-shadow: 0 10px 22px var(--panel-glow);
    }}
    .nav a.is-active {{
      background: var(--accent-soft);
      border-color: var(--accent);
      color: var(--ink);
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .card, .panel {{
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .card {{
      padding: 18px 18px 20px;
      position: relative;
      overflow: hidden;
    }}
    .card::before {{
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 4px;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      opacity: 0.92;
    }}
    .card .label {{
      color: var(--muted);
      font-size: 0.8rem;
      margin-bottom: 10px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }}
    .card .value {{
      font-size: clamp(1.5rem, 3vw, 2.2rem);
      font-weight: 700;
      letter-spacing: -0.04em;
      line-height: 1.05;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px;
    }}
    .panel {{
      padding: 20px;
      overflow: hidden;
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: end;
      margin-bottom: 14px;
    }}
    .panel-header h2 {{
      margin: 0;
      font-size: 1.14rem;
    }}
    .panel-note {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.45;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 0 -2px;
      padding-bottom: 2px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.94rem;
    }}
    th, td {{
      text-align: left;
      padding: 12px 10px;
      border-top: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      border-top: 0;
      padding-top: 0;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.74rem;
    }}
    tbody tr:hover {{
      background: color-mix(in srgb, var(--panel-alt) 82%, transparent);
    }}
    code {{
      font-family: "Iosevka Term", "IBM Plex Mono", monospace;
      font-size: 0.92em;
      background: var(--code-bg);
      border: 1px solid var(--code-line);
      border-radius: 8px;
      padding: 2px 6px;
      word-break: break-all;
    }}
    .mono {{ font-family: "Iosevka Term", "IBM Plex Mono", monospace; }}
    .spark {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(28px, 1fr));
      gap: 8px;
      align-items: end;
      min-height: 180px;
      padding: 16px 0 4px;
    }}
    .bar-wrap {{
      display: flex;
      flex-direction: column;
      justify-content: end;
      gap: 6px;
      min-height: 100%;
    }}
    .bar {{
      background: linear-gradient(180deg, var(--accent-2), var(--accent));
      border-radius: 10px 10px 4px 4px;
      min-height: 4px;
      box-shadow: 0 10px 20px color-mix(in srgb, var(--accent) 18%, transparent);
    }}
    .axis {{
      font-size: 0.78rem;
      color: var(--muted);
      writing-mode: vertical-rl;
      transform: rotate(180deg);
      white-space: nowrap;
      height: 80px;
      overflow: hidden;
    }}
    .muted {{ color: var(--muted); }}
    .empty {{
      padding: 14px;
      border: 1px dashed var(--line);
      border-radius: 12px;
      color: var(--muted);
      background: var(--panel-alt);
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .kv {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--panel-alt);
    }}
    .kv .k {{
      color: var(--muted);
      font-size: 0.78rem;
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.09em;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    li + li {{
      margin-top: 8px;
    }}
    .footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .split-layout {{
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px;
      margin-top: 16px;
    }}
    .object-path {{
      margin-top: 12px;
      font-size: 0.96rem;
      line-height: 1.5;
    }}
    @media (max-width: 920px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .split-layout {{ grid-template-columns: 1fr; }}
      .nav-grid {{ grid-template-columns: 1fr; }}
      .hero {{ flex-direction: column; }}
      .hero-aside {{ flex-basis: auto; }}
      .shell {{ padding-inline: 16px; }}
      .panel-header {{ flex-direction: column; align-items: start; }}
    }}
    @media (max-width: 640px) {{
      .hero-main, .hero-aside, .nav-panel, .card, .panel {{ border-radius: 18px; }}
      .hero-main {{ padding: 20px; }}
      .hero-aside, .panel, .nav-panel, .card {{ padding: 16px; }}
      .hero-stats {{ grid-template-columns: 1fr; }}
      th, td {{ padding-inline: 8px; }}
    }}
    """.format(**theme)
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


def build_current_path(route: str, query: dict[str, list[str]]) -> str:
    filtered_query = [(key, value) for key, values in query.items() if key != "theme" for value in values]
    if not filtered_query:
        return route
    return f"{route}?{urlencode(filtered_query)}"


def render_nav(theme_key: str, current_path: str) -> str:
    current_route = urlsplit(current_path).path or "/"
    links = [
        ("Overview", "/"),
        ("Recent Uploads", "/uploads"),
        ("Largest Objects", "/largest"),
    ]
    nav_links = "".join(
        f'<a class="{"is-active" if current_route == path else ""}" href="{html.escape(with_theme(path, theme_key))}">{html.escape(label)}</a>'
        for label, path in links
    )
    theme_links = "".join(
        f'<a class="{"is-active" if key == theme_key else ""}" href="{html.escape(with_theme(current_path, key))}">{html.escape(data["name"])}</a>'
        for key, data in sorted(THEMES.items(), key=lambda item: item[1]["name"])
    )
    return f"""
    <div class="nav-grid">
      <section class="nav-panel">
        <p class="nav-kicker">Shortcuts</p>
        <h2>Browse the main views</h2>
        <p class="nav-note">Jump between the cache overview, the newest uploads, and the heaviest stored paths.</p>
        <div class="nav">
          {nav_links}
        </div>
      </section>
      <section class="nav-panel">
        <p class="nav-kicker">Themes</p>
        <h2>Change the dashboard palette</h2>
        <p class="nav-note">Switch color themes without losing your current page or filters. The active choice stays embedded in each link.</p>
        <div class="nav">
          {theme_links}
        </div>
      </section>
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


def extract_store_path_hash(store_path: str | None) -> str | None:
    if not store_path:
        return None
    prefix = "/nix/store/"
    if not store_path.startswith(prefix):
        return None
    tail = store_path[len(prefix) :]
    store_hash, separator, _name = tail.partition("-")
    if not separator or not store_hash or not STORE_PATH_HASH_RE.fullmatch(store_hash):
        return None
    return store_hash


def render_reference_item(reference: str, theme_key: str) -> str:
    store_hash = extract_store_path_hash(reference)
    if store_hash is None:
        return f"<li><code>{html.escape(reference)}</code></li>"
    href = html.escape(with_theme("/object/" + quote(store_hash), theme_key))
    return f'<li><a href="{href}"><code>{html.escape(reference)}</code></a></li>'


def render_overview(theme_key: str, current_path: str) -> bytes:
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
          <td><a class="mono" href="{html.escape(with_theme('/object/' + quote(row['store_path_hash']), theme_key))}">{html.escape(row['store_path_hash'])}</a></td>
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
          <td><a href="{html.escape(with_theme('/object/' + quote(row['store_path_hash']), theme_key))}" class="mono">{html.escape(row['store_path_hash'])}</a></td>
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
      <div class="hero-main">
        <div class="eyebrow">Attic Cache Dashboard</div>
        <h1>attic-observatory</h1>
        <p>Operational view into Attic uploads, object growth, and cache contents.</p>
        <div class="hero-meta">
          <div class="badge">Cache: <strong>{html.escape(cache_name)}</strong></div>
          <div class="badge">DB: <code>{html.escape(DB_PATH)}</code></div>
        </div>
      </div>
      <aside class="hero-aside">
        <div>
          <div class="eyebrow">Snapshot</div>
          <div class="hero-stats">
            <div class="hero-stat"><div class="label">Public Key</div><div class="value mono">{html.escape(cache_key)}</div></div>
            <div class="hero-stat"><div class="label">Retention</div><div class="value">{format_int(cache['retention_period'] if cache else None)}</div></div>
            <div class="hero-stat"><div class="label">Logical Size</div><div class="value">{format_bytes(stats['total_nar_bytes'])}</div></div>
            <div class="hero-stat"><div class="label">Chunk Storage</div><div class="value">{format_bytes(stats['total_chunk_bytes'])}</div></div>
          </div>
        </div>
      </aside>
    </div>
    {render_nav(theme_key, current_path)}
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
        <div class="panel-header">
          <div>
            <h2>Recent Uploads</h2>
            <div class="panel-note">Newest store paths accepted by the cache, trimmed to their package names for fast scanning.</div>
          </div>
        </div>
        <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Created</th><th>Created By</th></tr>
          </thead>
          <tbody>{recent_rows}</tbody>
        </table>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>24h Upload Activity</h2>
            <div class="panel-note">Grouped by hour. Hover bars for upload counts and transferred NAR bytes.</div>
          </div>
        </div>
        <div class="spark">{bars}</div>
      </div>
    </div>
    <div class="split-layout">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>Largest Objects</h2>
            <div class="panel-note">Biggest stored paths by NAR size, useful for identifying the heaviest cache growth drivers.</div>
          </div>
        </div>
        <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Created</th></tr>
          </thead>
          <tbody>{largest_rows}</tbody>
        </table>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>Cache Settings</h2>
            <div class="panel-note">High-signal cache configuration surfaced directly from the Attic database.</div>
          </div>
        </div>
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
    return page_template("attic-observatory", body, theme_key)


def render_uploads(query: dict[str, list[str]], theme_key: str, current_path: str) -> bytes:
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
          <td><a class="mono" href="{html.escape(with_theme('/object/' + quote(row['store_path_hash']), theme_key))}">{html.escape(row['store_path_hash'])}</a></td>
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
      <div class="hero-main">
        <div class="eyebrow">Attic Queue</div>
        <h1>Recent Uploads</h1>
        <p>Newest objects accepted by the cache.</p>
        <div class="hero-meta">
          <div class="badge">Live ordering: newest first</div>
          <div class="badge">Theme: {html.escape(THEMES[theme_key]["name"])}</div>
        </div>
      </div>
      <aside class="hero-aside">
        <div class="eyebrow">Window</div>
        <div class="hero-stats">
          <div class="hero-stat"><div class="label">Rows</div><div class="value">{format_int(limit)}</div></div>
          <div class="hero-stat"><div class="label">Route</div><div class="value mono">/uploads</div></div>
        </div>
      </aside>
    </div>
    {render_nav(theme_key, current_path)}
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Upload Stream</h2>
          <div class="panel-note">Package path, compression, chunk count, and publisher identity in one responsive table.</div>
        </div>
      </div>
      <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Chunks</th><th>Compression</th><th>Created</th><th>Created By</th></tr>
        </thead>
        <tbody>{body_rows}</tbody>
      </table>
      </div>
    </div>
    """
    return page_template("Recent Uploads", body, theme_key)


def render_largest(theme_key: str, current_path: str) -> bytes:
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
          <td><a class="mono" href="{html.escape(with_theme('/object/' + quote(row['store_path_hash']), theme_key))}">{html.escape(row['store_path_hash'])}</a></td>
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
      <div class="hero-main">
        <div class="eyebrow">Capacity View</div>
        <h1>Largest Objects</h1>
        <p>Top 100 store paths by NAR size.</p>
        <div class="hero-meta">
          <div class="badge">Ranking: descending size</div>
          <div class="badge">Theme: {html.escape(THEMES[theme_key]["name"])}</div>
        </div>
      </div>
      <aside class="hero-aside">
        <div class="eyebrow">Window</div>
        <div class="hero-stats">
          <div class="hero-stat"><div class="label">Rows</div><div class="value">100</div></div>
          <div class="hero-stat"><div class="label">Route</div><div class="value mono">/largest</div></div>
        </div>
      </aside>
    </div>
    {render_nav(theme_key, current_path)}
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Largest Store Paths</h2>
          <div class="panel-note">Use this view to spot oversized outputs and expensive artifacts occupying cache space.</div>
        </div>
      </div>
      <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Hash</th><th>Store Path</th><th>Size</th><th>Chunks</th><th>Created</th><th>Created By</th></tr>
        </thead>
        <tbody>{body_rows}</tbody>
      </table>
      </div>
    </div>
    """
    return page_template("Largest Objects", body, theme_key)


def render_object_detail(store_hash: str, theme_key: str, current_path: str) -> bytes:
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
      {render_nav(theme_key, current_path)}
            """,
            theme_key,
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
    ref_list = "".join(render_reference_item(ref, theme_key) for ref in refs) or "<li class='muted'>None</li>"
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
      <div class="hero-main">
        <div class="eyebrow">Object Explorer</div>
        <h1>Object Detail</h1>
        <p class="object-path mono">{html.escape(row['store_path'])}</p>
      </div>
      <aside class="hero-aside">
        <div class="eyebrow">Navigation</div>
        <div class="hero-meta">
          <div class="badge"><a href="{html.escape(with_theme('/uploads', theme_key))}">Back to uploads</a></div>
          <div class="badge"><a href="{html.escape(with_theme('/largest', theme_key))}">Largest objects</a></div>
        </div>
      </aside>
    </div>
    {render_nav(theme_key, current_path)}
    <div class="panel">
      <div class="panel-header">
        <div>
          <h2>Object Metadata</h2>
          <div class="panel-note">Key identity and storage fields for the selected object and its backing NAR.</div>
        </div>
      </div>
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
    <div class="split-layout">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>References</h2>
            <div class="panel-note">Direct store-path references extracted from the object metadata. Internal references link back into the explorer.</div>
          </div>
        </div>
        <ul>{ref_list}</ul>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div>
            <h2>Signatures</h2>
            <div class="panel-note">Recorded signatures attached to this object.</div>
          </div>
        </div>
        <ul>{sig_list}</ul>
      </div>
    </div>
    <div class="panel" style="margin-top:16px;">
      <div class="panel-header">
        <div>
          <h2>Chunk Map</h2>
          <div class="panel-note">The first 50 chunk references for this NAR, including remote file ids where available.</div>
        </div>
      </div>
      <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Seq</th><th>Chunk Hash</th><th>Chunk Size</th><th>Chunk Created</th><th>Remote File</th></tr>
        </thead>
        <tbody>{chunk_rows}</tbody>
      </table>
      </div>
    </div>
    """
    return page_template(f"Object {store_hash}", body, theme_key)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        current_path = build_current_path(route, query)
        theme_key, _theme = get_theme(query.get("theme", [None])[0])
        try:
            if route == "/":
                self.respond(200, render_overview(theme_key, current_path))
            elif route == "/uploads":
                self.respond(200, render_uploads(query, theme_key, current_path))
            elif route == "/largest":
                self.respond(200, render_largest(theme_key, current_path))
            elif route.startswith("/object/"):
                self.respond(200, render_object_detail(route.split("/", 2)[2], theme_key, current_path))
            else:
                self.respond(404, page_template("Not Found", f"<div class='hero'><div><h1>Not Found</h1><p>{html.escape(route)}</p></div></div>{render_nav(theme_key, current_path)}", theme_key))
        except sqlite3.Error as exc:
            self.respond(500, page_template("Database Error", f"<div class='hero'><div><h1>Database Error</h1><p><code>{html.escape(str(exc))}</code></p></div></div>{render_nav(theme_key, current_path)}", theme_key))

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
