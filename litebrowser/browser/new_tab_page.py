from html import escape as _html_escape
from urllib.parse import urlparse

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
        "@ACCENT@": p["ACCENT"],
        "@ACCENT_HOVER@": p["ACCENT_HOVER"],
        "@BORDER_SOFT@": p["BORDER_SOFT"],
        "@ACCENT_SOFT@": p["ACCENT_SOFT"],
        "@GLOW1@": _rgba(p["ACCENT"], 0.16),
        "@GLOW2@": _rgba(p["ACCENT"], 0.20),
        "@WATERMARK@": _rgba(p["ACCENT"], 0.12),
    }


# 5.8 "café bar" speed dial — a shop awning, a hero with rising steam, and
# menu-card shortcuts. Palette-driven so every theme stays in sync with the shell.
_NEW_TAB_CSS = """
* { box-sizing: border-box; }
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
  padding: 14px 30px;
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
  max-width: 1000px;
  margin: 0 auto;
  padding: 46px 30px 44px;
}

/* A single quiet wisp beside the masthead — the only literal nod to warmth,
   and the thing the new-tab steam preference still controls. */
.hero {
  display: flex;
  align-items: flex-start;
  gap: 26px;
  border: none;
  border-bottom: 1px solid @BORDER_SOFT@;
  border-radius: 0;
  padding: 0 0 34px;
  background: transparent;
}
.hero-copy { flex: 1; min-width: 0; }
.hero-mark {
  flex: 0 0 auto;
  padding-top: 6px;
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
  margin: 13px 0 10px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 44px;
  font-weight: 600;
  letter-spacing: -.02em;
  line-height: 1.06;
  color: @TEXT@;
}
.hero p {
  max-width: 580px;
  margin: 0 0 22px;
  color: @TEXT_MUTED@;
  font-size: 14px;
  line-height: 1.6;
}
.search-bar { max-width: 680px; }
form { margin: 0; }
input[type="search"] {
  width: 100%;
  padding: 15px 17px;
  border-radius: 10px;
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

/* Sections are open headings on the paper, divided by hairlines. */
.section {
  margin-top: 30px;
  border: none;
  border-radius: 0;
  padding: 0;
  background: transparent;
}
.section h2 {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 14px;
  color: @TEXT_MUTED@;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .16em;
  text-transform: uppercase;
}
.section h2 .rule { flex: 1; height: 1px; background: @BORDER_SOFT@; }
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}
.tile {
  position: relative;
  display: flex;
  align-items: center;
  gap: 11px;
  text-decoration: none;
  background: @CARD_BG@;
  border: 1px solid @BORDER_SOFT@;
  border-radius: 10px;
  min-height: 68px;
  padding: 12px 13px;
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
.tile-label {
  position: relative;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: @TEXT@;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
}
/* Recent pour list */
.recent-row {
  display: flex;
  align-items: center;
  gap: 10px;
  color: @TEXT_MUTED@;
  text-decoration: none;
  padding: 12px 10px;
  border-radius: 10px;
  border-bottom: 1px solid @BORDER_SOFT@;
  transition: color .12s ease, padding-left .12s ease, background .12s ease;
}
.recent-row::before { content: "◦"; color: @ACCENT_HOVER@; }
.recent-row .recent-url { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-row .recent-host {
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: @ACCENT_HOVER@;
  background: @ACCENT_SOFT@;
  border: 1px solid @INPUT_BORDER@;
  border-radius: 999px;
  padding: 2px 9px;
}
.recent-row:hover { color: @TEXT@; background: @MAIN_BG_ALT@; padding-left: 14px; }
.recent-row:last-child { border-bottom: none; }

.empty { color: @TEXT_MUTED@; font-size: 13px; padding: 8px 4px; }
/* Keyboard users get a visible ring on every interactive row. */
a:focus-visible {
  outline: 2px solid @ACCENT@;
  outline-offset: 2px;
  border-radius: 8px;
}
/* Quiet themed scrollbar for the page itself. */
::-webkit-scrollbar { width: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: @INPUT_BORDER@;
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: content-box;
}
::-webkit-scrollbar-thumb:hover { background: @ACCENT@; background-clip: content-box; }
.hint-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 26px;
}
.hint {
  font-size: 10px;
  letter-spacing: .04em;
  color: @TEXT_MUTED@;
  border: 1px solid @BORDER_SOFT@;
  border-radius: 999px;
  padding: 5px 11px;
  background: @CARD_BG@;
}
.code {
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid @BORDER_SOFT@;
  background: @MAIN_BG_ALT@;
  font-size: 12px;
}
.footer-note {
  margin-top: 34px;
  text-align: left;
  color: @TEXT_MUTED@;
  font-size: 11px;
}

@media (max-width: 680px) {
  h1 { font-size: 33px; }
  .shell { padding: 30px 16px 32px; }
  .awning { padding: 12px 16px; }
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
    recent = [url for _, url in entries[:12] if url.startswith("http")]

    seen = set()
    quick_links = []
    for item in bookmarks[:10]:
        url = _safe_link_url(item.get("url", ""))
        if url and url not in seen:
            seen.add(url)
            quick_links.append((url, item.get("title", "")[:24] or url[:24]))
    # Early-break: v6.5 audited a full O(N) walk of the entire history file
    # even after the 12 slots were filled (history is sorted newest-first).
    if len(quick_links) < 12:
        for _, url in entries:
            if len(quick_links) >= 12:
                break
            url = _safe_link_url(url)
            if url.startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                quick_links.append((url, url.replace("https://", "").replace("http://", "")[:24]))

    tiles_html = ""
    for url, label in quick_links:
        # Per-site glyph: first letter of the host looks like a favicon chip
        # and stops every tile showing the identical teacup emoji.
        try:
            host = urlparse(url).netloc.removeprefix("www.")
        except Exception:
            host = ""
        glyph = escape_html((host[:1] or "•").upper())
        tiles_html += (
            '<a href="%s" class="tile" title="%s"><span class="tile-mark tile-mark-letter">%s</span>'
            '<span class="tile-label">%s</span></a>'
            % (escape_html(url), escape_html(url), glyph, escape_html(label))
        )
    if not tiles_html:
        tiles_html = '<div class="empty">Save bookmarks or visit more pages to build your cafe shelf.</div>'

    recent_rows = ""
    for url in recent:
        try:
            host = urlparse(url).netloc or ""
        except Exception:
            host = ""
        host = host[:26]
        label = url.replace("https://", "").replace("http://", "")[:60]
        recent_rows += (
            '<a href="%s" class="recent-row" title="%s">'
            '<span class="recent-url">%s</span>'
            '<span class="recent-host">%s</span></a>'
            % (escape_html(url), escape_html(url), escape_html(label), escape_html(host or "link"))
        )
    if not recent_rows:
        recent_rows = '<div class="empty">No recent browsing yet.</div>'

    hub_tiles = ""
    for site in app_paths.bundled_sites(app_dir):
        # Use the local copy when shipped; the deployed fallback keeps all six
        # project apps reachable in a lean/package build too.
        tile_url = site.get("url") or site.get("remote")
        if not tile_url:
            continue
        hub_tiles += (
            '<a href="%s" class="tile" title="%s — %s"><span class="tile-mark">%s</span><span class="tile-label">%s</span></a>'
            % (
                escape_html(tile_url),
                escape_html(site["display"]),
                escape_html(site.get("subtitle", "")),
                escape_html(site.get("glyph", "▦")),
                escape_html(site["display"]),
            )
        )
    support_section = ""
    if hub_tiles:
        support_section = """
    <div class="section">
      <h2>Project Hub — Your App Chain <span class="rule"></span></h2>
      <p style="font-size:14px;margin:0 0 14px;">Jump straight into any of the bundled apps (all run locally on your machine). Online versions (if deployed) live in Project Hub.</p>
      <div class="tiles">%s</div>
      <p style="font-size:12px;margin:14px 0 0;">Omnibar: <code class="code">/hub</code> · <code class="code">/cql</code> · <code class="code">/mas</code> · <code class="code">/leaderboard</code> · <code class="code">/linklumina</code> · <code class="code">/bimat</code> · <code class="code">/boitoan</code></p>
    </div>
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
        else ''
    )
    css = _NEW_TAB_CSS
    if reduce_motion:
        css += "\n*,:before,:after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }\n"
    for token, value in _resolve_theme_tokens(mode, accent).items():
        css = css.replace(token, value)

    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="%s">
<title>@BRAND@ Home</title>
<style>%s</style>
</head>
<body>
  <div class="awning"><span class="cup-logo">M</span> @BRAND@ · The Quiet Table</div>
  <div class="shell">
    <div class="hero">
      <div class="hero-copy">
        <div class="eyebrow">%s</div>
        <h1>%s</h1>
        <p>Search the web, reopen your work, or return to what you were reading. Everything stays on this device.</p>
        <form action="%s" method="get" class="search-bar">
          <input type="search" name="%s" placeholder="Search %s or type a URL..." autofocus />
        </form>
      </div>
      %s
    </div>
    %s
    <div class="section">
      <h2>Saved shelf <span class="rule"></span></h2>
      <div class="tiles">%s</div>
    </div>
    <div class="section">
      <h2>Recently opened <span class="rule"></span></h2>
      <div>%s</div>
    </div>
    <div class="hint-row">
      <span class="hint">? Help · F1</span>
      <span class="hint">Ctrl+T new tab</span>
      <span class="hint">Ctrl+K command</span>
      <span class="hint">/agent · /brief · /group-tabs</span>
    </div>
    <div class="footer-note">Local-first. No account required.</div>
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
