from html import escape as _html_escape
from urllib.parse import unquote, urlparse

from litebrowser.core import app_paths, app_version, prefs

_CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "form-action https: http:; "
    "navigate-to http: https: file: about:; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)
_ALLOWED_LINK_SCHEMES = {"http", "https", "file"}

# Search-engine templates live in litebrowser.core.prefs (single source of
# truth shared with the address bar), so the speed-dial form stays in sync.


def escape_html(text):
    return _html_escape(str(text or ""), quote=True)


# Café-themed, time-of-day greetings for the speed-dial hero. Each is a
# (eyebrow, headline) pair so the home page feels alive and on-brand.
# Greetings are plain text and live in core so the data layer (brief_service),
# the new-tab page and the Home hero all read one definition. Re-exported here
# because this module is the historical home of the helper.
from litebrowser.core.greetings import CAFE_GREETINGS as _CAFE_GREETINGS  # noqa: E402,F401
from litebrowser.core.greetings import cafe_greeting  # noqa: E402,F401


def _safe_link_url(url):
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme.lower() not in _ALLOWED_LINK_SCHEMES:
        return ""
    return text


def _rgba(hex_color, alpha):
    """Turn a #rrggbb token into an rgba() string for soft glows/watermarks."""
    try:
        value = hex_color.lstrip("#")
        red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
        return "rgba(%d, %d, %d, %s)" % (red, green, blue, alpha)
    except (TypeError, ValueError):
        return "rgba(160, 140, 110, %s)" % alpha


def _resolve_theme_tokens(mode, accent):
    """Resolve theme + accent into the color tokens used by the speed dial."""
    from litebrowser.core import theme_data
    p = theme_data.palette_tokens(mode or theme_data.DEFAULT_THEME, accent)
    return {
        "@MAIN_BG@": p["MAIN_BG"],
        "@MAIN_BG_ALT@": p["MAIN_BG_ALT"],
        "@CARD_BG@": p["CARD_BG"],
        "@INPUT_BG@": p["INPUT_BG"],
        "@INPUT_BORDER@": p["INPUT_BORDER"],
        "@TEXT@": p["TEXT"],
        "@TEXT_MUTED@": p["TEXT_MUTED"],
        "@TEXT_ON_ACCENT@": p["TEXT_ON_ACCENT"],
        "@ACCENT@": p["ACCENT"],
        "@ACCENT_HOVER@": p["ACCENT_HOVER"],
        "@ACCENT_FILL_HOVER@": p["ACCENT_FILL_HOVER"],
        "@BORDER_SOFT@": p["BORDER_SOFT"],
        "@ACCENT_SOFT@": p["ACCENT_SOFT"],
        "@GLOW1@": _rgba(p["ACCENT"], 0.16),
        "@GLOW2@": _rgba(p["ACCENT"], 0.20),
        "@WATERMARK@": _rgba(p["ACCENT"], 0.12),
    }


def _link_parts(url):
    """Return (host, path) from an already-validated link.

    Only existing URL data is used: there is no attempt to invent titles or
    metadata for history rows that do not store a title.
    """
    parsed = urlparse(str(url or ""))
    host = (parsed.netloc or "").removeprefix("www.")
    path = unquote(parsed.path or "").strip("/")
    return host, path


def _path_label(path):
    if not path:
        return ""
    segment = str(path).rsplit("/", 1)[-1].strip()
    stem, dot, extension = segment.rpartition(".")
    if dot and extension.lower() in {"html", "htm", "php", "asp", "aspx", "jsp"}:
        segment = stem
    return segment.replace("-", " ").replace("_", " ").strip()


def _link_label(url, title=""):
    label = str(title or "").strip()
    if label:
        return label
    host, path = _link_parts(url)
    return _path_label(path) or host or url


def _display_host(url):
    host, _path = _link_parts(url)
    return host or "local file"


# The speed dial is a small editorial desk: a hero and search, then a main
# column for Project Hub and the saved shelf, with recent pages in the margin.
# The grid changes shape at 1080/900/760/600px instead of stretching every tile.
_NEW_TAB_CSS = """
* { box-sizing: border-box; }
html { background: @MAIN_BG@; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: "Segoe UI", "Segoe UI Symbol", sans-serif;
  color: @TEXT@;
  background: @MAIN_BG@;
}

/* The house line: a paper header rule, not a shop awning. */
.awning {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 14px clamp(20px, 4vw, 42px);
  color: @TEXT_MUTED@;
  background: @CARD_BG@;
  border-bottom: 1px solid @BORDER_SOFT@;
  letter-spacing: .14em;
  font-weight: 700;
  font-size: 10px;
  text-transform: uppercase;
}
.awning .cup-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px solid @INPUT_BORDER@;
  border-radius: 4px;
  color: @TEXT@;
  font-family: Georgia, serif;
  font-size: 13px;
  letter-spacing: 0;
  text-transform: none;
}

.shell {
  width: min(1280px, calc(100% - 48px));
  margin: 0 auto;
  padding: 36px 0 44px;
}

.hero {
  display: flex;
  align-items: flex-start;
  gap: 28px;
  border-bottom: 1px solid @BORDER_SOFT@;
  padding: 0 0 30px;
}
.hero-copy { flex: 1; min-width: 0; max-width: 800px; }
.hero-mark {
  flex: 0 0 auto;
  padding-top: 8px;
  opacity: .55;
}
.steam {
  position: relative;
  display: block;
  width: 18px;
  height: 26px;
  pointer-events: none;
}
.steam i {
  position: absolute;
  bottom: 0;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: @ACCENT@;
  opacity: 0;
  animation: steam-rise 3.2s ease-out infinite;
}
.steam i:nth-child(1) { left: 0;   animation-delay: 0s; }
.steam i:nth-child(2) { left: 6px; animation-delay: 1.05s; }
.steam i:nth-child(3) { left: 12px; animation-delay: 2.1s; }
@keyframes steam-rise {
  0%   { transform: translateY(6px) scale(.6); opacity: 0; }
  25%  { opacity: .8; }
  100% { transform: translateY(-20px) scale(1.1); opacity: 0; }
}
.eyebrow {
  color: @ACCENT_HOVER@;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .18em;
  text-transform: uppercase;
}
h1 {
  margin: 12px 0 10px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(34px, 4.2vw, 52px);
  font-weight: 600;
  letter-spacing: -.02em;
  line-height: 1.05;
  color: @TEXT@;
}
.hero p {
  max-width: 650px;
  margin: 0 0 20px;
  color: @TEXT_MUTED@;
  font-size: 14px;
  line-height: 1.6;
}
.search-form { max-width: 760px; width: 100%; }
form { margin: 0; }
.search-row { display: flex; align-items: stretch; gap: 8px; }
input[type="search"] {
  min-width: 0;
  width: 100%;
  padding: 14px 16px;
  border-radius: 9px;
  border: 1px solid @INPUT_BORDER@;
  background: @INPUT_BG@;
  color: @TEXT@;
  font-size: 14px;
  outline: none;
  transition: border-color .15s ease, box-shadow .15s ease;
}
input[type="search"]::placeholder { color: @TEXT_MUTED@; }
input[type="search"]:focus {
  border-color: @ACCENT@;
  box-shadow: 0 0 0 3px @GLOW1@;
}
.search-go {
  flex: 0 0 auto;
  min-width: 92px;
  padding: 0 18px;
  border: 1px solid @ACCENT@;
  border-radius: 9px;
  background: @ACCENT@;
  color: @TEXT_ON_ACCENT@;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease;
}
.search-go:hover { background: @ACCENT_FILL_HOVER@; border-color: @ACCENT_FILL_HOVER@; }
.search-go:focus-visible { outline: 2px solid @ACCENT@; outline-offset: 3px; }

.desk {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, .8fr);
  gap: clamp(24px, 4vw, 44px);
  align-items: start;
}
.desk-main, .desk-side { min-width: 0; }
.desk-side {
  border-left: 1px solid @BORDER_SOFT@;
  padding-left: 28px;
}

/* Sections are open headings on the paper, divided by hairlines. */
.section { margin-top: 28px; }
.desk-main > .section:first-child, .desk-side > .section:first-child { margin-top: 0; }
.section h2 {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 12px;
  color: @TEXT_MUTED@;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .16em;
  text-transform: uppercase;
}
.section h2 .rule { flex: 1; height: 1px; background: @BORDER_SOFT@; }
.section-note {
  max-width: 680px;
  margin: 0 0 14px;
  color: @TEXT_MUTED@;
  font-size: 12px;
  line-height: 1.55;
}
.tiles { display: grid; gap: 10px; }
.hub-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.shelf-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.tile {
  position: relative;
  display: flex;
  align-items: center;
  gap: 11px;
  text-decoration: none;
  background: @CARD_BG@;
  border: 1px solid @BORDER_SOFT@;
  border-radius: 10px;
  min-height: 76px;
  padding: 11px 12px;
  text-align: left;
  overflow: hidden;
  transition: border-color .15s ease, background .15s ease;
}
.tile:hover,
.tile:focus-visible {
  border-color: @ACCENT@;
  background: @ACCENT_SOFT@;
  outline: none;
}
.tile:focus-visible { box-shadow: 0 0 0 2px @ACCENT@; }
.tile-mark {
  position: relative;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  font-size: 15px;
  color: @TEXT@;
  background: @MAIN_BG_ALT@;
  border: 1px solid @BORDER_SOFT@;
}
.tile-mark-letter {
  font-size: 13px;
  font-weight: 700;
  font-family: Georgia, serif;
}
.tile:hover .tile-mark { border-color: @ACCENT@; }
.tile-copy {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.tile-kicker {
  overflow: hidden;
  color: @TEXT_MUTED@;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .08em;
  line-height: 1.2;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}
.tile-label {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: @TEXT@;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
}
.tile-sub {
  overflow: hidden;
  color: @TEXT_MUTED@;
  font-size: 10px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Recent browsing: a compact margin list, not another card wall. */
.recent-list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid @BORDER_SOFT@;
}
.recent-row {
  display: flex;
  align-items: center;
  gap: 10px;
  color: @TEXT;
  text-decoration: none;
  padding: 11px 0;
  border-bottom: 1px solid @BORDER_SOFT@;
  transition: color .12s ease, padding-left .12s ease, background .12s ease;
}
.recent-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.recent-title {
  overflow: hidden;
  color: @TEXT@;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-sub {
  overflow: hidden;
  color: @TEXT_MUTED@;
  font-size: 10px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-host {
  flex: 0 0 auto;
  max-width: 120px;
  overflow: hidden;
  color: @ACCENT_HOVER@;
  background: @ACCENT_SOFT@;
  border: 1px solid @INPUT_BORDER@;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .04em;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}
.recent-row:hover {
  color: @ACCENT_HOVER@;
  background: @MAIN_BG_ALT@;
  padding-left: 6px;
  padding-right: 6px;
}
.recent-row:last-child { border-bottom: none; }

.empty {
  grid-column: 1 / -1;
  color: @TEXT_MUTED@;
  font-size: 12px;
  line-height: 1.55;
  padding: 8px 2px;
}
.command-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 13px;
  color: @TEXT_MUTED@;
  font-size: 10px;
}
.command-label {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.code {
  padding: 2px 7px;
  border-radius: 6px;
  border: 1px solid @BORDER_SOFT@;
  background: @MAIN_BG_ALT@;
  color: @TEXT_MUTED@;
  font-size: 10px;
}
.hint-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 24px;
}
.hint {
  font-size: 10px;
  letter-spacing: .02em;
  color: @TEXT_MUTED@;
  border: 1px solid @BORDER_SOFT@;
  border-radius: 999px;
  padding: 5px 10px;
  background: @CARD_BG@;
}
.footer-note {
  margin-top: 20px;
  color: @TEXT_MUTED@;
  font-size: 10px;
  line-height: 1.5;
}
a:focus-visible {
  outline: 2px solid @ACCENT@;
  outline-offset: 2px;
  border-radius: 8px;
}
::-webkit-scrollbar { width: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: @INPUT_BORDER@;
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: content-box;
}
::-webkit-scrollbar-thumb:hover { background: @ACCENT@; background-clip: content-box; }

@media (max-width: 1080px) {
  .shell { width: min(calc(100% - 40px), 1040px); }
  .desk { gap: 26px; }
  .desk-side { padding-left: 24px; }
}
@media (max-width: 900px) {
  .shell { width: min(calc(100% - 40px), 820px); }
  .desk { grid-template-columns: 1fr; gap: 0; }
  .desk-side { border-left: none; padding-left: 0; }
  .desk-side > .section:first-child { margin-top: 28px; }
}
@media (max-width: 760px) {
  .hub-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .shell { width: calc(100% - 32px); padding: 24px 0 32px; }
  .awning { padding: 12px 16px; }
  .hero { gap: 14px; padding-bottom: 24px; }
  .hero-mark { display: none; }
  h1 { font-size: 34px; }
  .hero p { font-size: 13px; }
  .search-row { flex-direction: column; }
  .search-go { min-height: 40px; }
  .hub-grid, .shelf-grid { grid-template-columns: 1fr; }
  .tile { min-height: 64px; }
  .recent-host { display: none; }
}
"""


def build_new_tab_html(base_dir, app_dir=None, search_engine="Google", mode=None, accent=None):
    # Default to the theme the shell is showing (not the bare default theme): a
    # caller that omits the mode used to get a bright speed dial inside a dark
    # window, which is the exact "page ignores my theme" report this fixes.
    if mode is None:
        mode = prefs.resolved_auto_theme(base_dir)
    if accent is None:
        accent = prefs.get_accent(base_dir)
    bookmarks = prefs.load_bookmarks(base_dir)
    entries = prefs.load_history_entries(base_dir)
    entries.sort(key=lambda item: -item[0])
    recent = [
        safe_url
        for _ts, url in entries[:12]
        if (safe_url := _safe_link_url(url)).startswith(("http://", "https://"))
    ]

    seen = set()
    quick_links = []
    for item in bookmarks[:10]:
        url = _safe_link_url(item.get("url", ""))
        if url and url not in seen:
            seen.add(url)
            quick_links.append(
                {
                    "url": url,
                    "label": _link_label(url, item.get("title", "")),
                    "host": _display_host(url),
                }
            )
    # Early-break: v6.5 audited a full O(N) walk of the entire history file
    # even after the 12 slots were filled (history is sorted newest-first).
    if len(quick_links) < 12:
        for _ts, raw_url in entries:
            if len(quick_links) >= 12:
                break
            url = _safe_link_url(raw_url)
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            quick_links.append(
                {
                    "url": url,
                    "label": _link_label(url),
                    "host": _display_host(url),
                }
            )

    tiles_html = ""
    for link in quick_links:
        url = link["url"]
        label = link["label"]
        host = link["host"]
        glyph = escape_html((host[:1] or "•").upper())
        kicker = (
            '<span class="tile-kicker">%s</span>' % escape_html(host)
            if host and host.casefold() != label.casefold()
            else ""
        )
        tiles_html += (
            '<a href="%s" class="tile shelf-tile" title="%s">'
            '<span class="tile-mark tile-mark-letter">%s</span>'
            '<span class="tile-copy">%s<span class="tile-label">%s</span></span>'
            "</a>"
            % (
                escape_html(url),
                escape_html(url),
                glyph,
                kicker,
                escape_html(label),
            )
        )
    if not tiles_html:
        tiles_html = (
            '<div class="empty">Save a bookmark or visit a page to build your shelf. '
            "Bookmarks and recent pages stay on this device.</div>"
        )

    recent_rows = ""
    for url in recent:
        host, path = _link_parts(url)
        title = _path_label(path) or host or "Home"
        sub = host + (("/" + path) if path else "")
        recent_rows += (
            '<a href="%s" class="recent-row" title="%s">'
            '<span class="recent-copy"><span class="recent-title">%s</span>'
            '<span class="recent-sub">%s</span></span>'
            '<span class="recent-host">%s</span></a>'
            % (
                escape_html(url),
                escape_html(url),
                escape_html(title),
                escape_html(sub or url),
                escape_html(host or "link"),
            )
        )
    if not recent_rows:
        recent_rows = '<div class="empty">No recent browsing yet. Pages you open will appear here.</div>'

    hub_tiles = ""
    for site in app_paths.bundled_sites(app_dir):
        # Use the local copy when shipped; the deployed fallback keeps all six
        # project apps reachable in a lean/package build too.
        tile_url = site.get("url") or site.get("remote")
        if not tile_url:
            continue
        hub_tiles += (
            '<a href="%s" class="tile hub-tile" title="%s — %s">'
            '<span class="tile-mark">%s</span>'
            '<span class="tile-copy"><span class="tile-label">%s</span>'
            '<span class="tile-sub">%s</span></span></a>'
            % (
                escape_html(tile_url),
                escape_html(site["display"]),
                escape_html(site.get("subtitle", "")),
                escape_html(site.get("glyph", "▦")),
                escape_html(site["display"]),
                escape_html(site.get("subtitle", "")),
            )
        )
    support_section = ""
    if hub_tiles:
        support_section = """
    <section class="section hub-section">
      <h2>Project Hub — Your App Chain <span class="rule"></span></h2>
      <p class="section-note">Jump straight into any of the bundled apps. They run locally; online versions, when deployed, live in Project Hub.</p>
      <div class="tiles hub-grid">%s</div>
      <div class="command-strip">
        <span class="command-label">Omnibar</span>
        <code class="code">/hub</code><code class="code">/cql</code><code class="code">/mas</code>
        <code class="code">/leaderboard</code><code class="code">/linklumina</code>
        <code class="code">/bimat</code><code class="code">/boitoan</code>
      </div>
    </section>
    """ % hub_tiles

    engine_label = search_engine or prefs.DEFAULT_SEARCH_ENGINE
    engine_search_template = prefs.search_engine_search_template(engine_label)  # e.g. https://www.google.com/search?q={q}
    form_action = engine_search_template.split("?", 1)[0]
    form_param = engine_search_template.split("?", 1)[1].split("=", 1)[0] if "?" in engine_search_template else "q"

    eyebrow, headline = cafe_greeting()
    if not prefs.get_new_tab_greeting(base_dir):
        eyebrow, headline = "Mei", "Your calm starting point."
    reduce_motion = prefs.reduced_motion_enabled(base_dir)
    steam_html = (
        '<div class="hero-mark"><span class="steam"><i></i><i></i><i></i></span></div>'
        if prefs.get_new_tab_steam(base_dir) and not reduce_motion
        else ""
    )
    css = _NEW_TAB_CSS
    if reduce_motion:
        css += "\n*,:before,:after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }\n"
    for token, value in _resolve_theme_tokens(mode, accent).items():
        css = css.replace(token, value)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="%s">
<title>@BRAND@ Home</title>
<style>%s</style>
</head>
<body>
  <div class="awning"><span class="cup-logo">M</span> @BRAND@ · The Quiet Table</div>
  <div class="shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="eyebrow">%s</div>
        <h1>%s</h1>
        <p>Search the web, reopen your work, or return to what you were reading. Everything stays on this device.</p>
        <form action="%s" method="get" class="search-form" role="search">
          <div class="search-row">
            <input type="search" name="%s" id="mei-search" placeholder="Search %s or enter a URL..." aria-label="Search the web or enter a URL" autofocus />
            <button type="submit" class="search-go">Search</button>
          </div>
        </form>
      </div>
      %s
    </header>
    <div class="desk">
      <main class="desk-main">
        %s
        <section class="section shelf-section">
          <h2>Saved shelf <span class="rule"></span></h2>
          <p class="section-note">Bookmarks first, then the pages you return to most recently.</p>
          <div class="tiles shelf-grid">%s</div>
        </section>
      </main>
      <aside class="desk-side">
        <section class="section recent-section">
          <h2>Recently opened <span class="rule"></span></h2>
          <div class="recent-list">%s</div>
        </section>
        <div class="hint-row">
          <span class="hint">? Help · F1</span>
          <span class="hint">Ctrl+T new tab</span>
          <span class="hint">Ctrl+K command</span>
          <span class="hint">/agent · /brief · /group-tabs</span>
        </div>
        <div class="footer-note">Local-first. No account required.</div>
      </aside>
    </div>
  </div>
</body>
</html>""" % (
        escape_html(_CSP),
        css,
        escape_html(eyebrow),
        escape_html(headline),
        escape_html(form_action),
        escape_html(form_param),
        escape_html(engine_label),
        steam_html,
        support_section,
        tiles_html,
        recent_rows,
    )
    # One brand string for the whole app (core/product.py): this page used to
    # hard-code the pre-rename name, so a tab could read a different product than
    # the .exe that opened it.
    return html.replace("@BRAND@", app_version.APP_NAME)
