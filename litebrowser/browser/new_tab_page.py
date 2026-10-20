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
  background:
    radial-gradient(circle at 6% 0%, @GLOW2@, transparent 26%),
    radial-gradient(circle at 96% 10%, @GLOW1@, transparent 30%),
    radial-gradient(circle at 50% 122%, @GLOW2@, transparent 42%),
    linear-gradient(160deg, @MAIN_BG_ALT@ 0%, @MAIN_BG@ 55%, @MAIN_BG_ALT@ 100%);
  background-attachment: fixed;
}

/* Shop awning */
.awning {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 26px;
  color: @TEXT@;
  background: linear-gradient(90deg, @CARD_BG@, @MAIN_BG_ALT@, @CARD_BG@);
  border-bottom: 1px solid @BORDER_SOFT@;
  letter-spacing: .16em;
  font-weight: 700;
  font-size: 11px;
  text-transform: uppercase;
}
.awning .cup-logo { font-size: 17px; color: @ACCENT_HOVER@; }

.shell {
  max-width: 1020px;
  margin: 0 auto;
  padding: 44px 26px 40px;
}

/* Daily-special board */
.hero {
  position: relative;
  display: flex;
  align-items: center;
  gap: 30px;
  overflow: hidden;
  border: 1px solid @BORDER_SOFT@;
  border-radius: 30px;
  padding: 40px 38px;
  background:
    radial-gradient(circle at 78% 12%, @GLOW1@, transparent 36%),
    linear-gradient(135deg, @CARD_BG@ 0%, @MAIN_BG_ALT@ 100%);
}
.hero-copy { flex: 1; min-width: 0; }
.eyebrow {
  color: @ACCENT_HOVER@;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .2em;
  text-transform: uppercase;
}
h1 {
  margin: 12px 0 10px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 46px;
  font-weight: 700;
  letter-spacing: -.03em;
  line-height: 1.08;
  color: @TEXT@;
}
.hero p {
  max-width: 620px;
  margin: 0 0 20px;
  color: @TEXT_MUTED@;
  font-size: 15px;
  line-height: 1.65;
}
.search-bar { max-width: 720px; }
form { margin: 0; }
input[type="search"] {
  width: 100%;
  padding: 17px 20px;
  border-radius: 16px;
  border: 1px solid @INPUT_BORDER@;
  background: @INPUT_BG@;
  color: @TEXT@;
  font-size: 15px;
  outline: none;
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
input[type="search"]::placeholder { color: @TEXT_MUTED@; }
input[type="search"]:focus {
  border-color: @ACCENT_HOVER@;
  box-shadow: 0 0 0 4px @GLOW1@;
  transform: translateY(-1px);
}

/* Cup + rising steam — drawn in pure CSS so it stays crisp and centered
   (no emoji glyph to clip or offset) */
.cup {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 170px;
  height: 170px;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 34%, @ACCENT_SOFT@, transparent 74%);
  border: 1px solid @INPUT_BORDER@;
}
.cup-art {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.steam {
  position: relative;
  width: 46px;
  height: 58px;
  margin-bottom: -4px;
  pointer-events: none;
}
.steam i {
  position: absolute;
  bottom: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: @ACCENT_HOVER@;
  opacity: 0;
  animation: steam-rise 3.2s ease-out infinite;
}
.steam i:nth-child(1) { left: 5px;  animation-delay: 0s; }
.steam i:nth-child(2) { left: 19px; animation-delay: 1.05s; }
.steam i:nth-child(3) { left: 33px; animation-delay: 2.1s; }
@keyframes steam-rise {
  0%   { transform: translateY(8px) scale(.5); opacity: 0; }
  25%  { opacity: .6; }
  100% { transform: translateY(-50px) scale(1.7); opacity: 0; }
}
.cup-mug {
  position: relative;
  width: 62px;
  height: 46px;
  background: linear-gradient(180deg, @ACCENT_HOVER@, @ACCENT@);
  border-radius: 5px 5px 18px 18px;
  box-shadow: inset 0 -7px 0 rgba(0,0,0,.08);
}
.cup-mug::before {
  content: "";
  position: absolute;
  right: -21px;
  top: 6px;
  width: 20px;
  height: 27px;
  border: 7px solid @ACCENT@;
  border-left: none;
  border-radius: 0 16px 16px 0;
}
.cup-saucer {
  width: 90px;
  height: 10px;
  margin-top: -1px;
  background: linear-gradient(180deg, @ACCENT_HOVER@, @ACCENT@);
  border-radius: 50%;
  opacity: .92;
}

/* Menu cards */
.section {
  margin-top: 24px;
  border: 1px solid @BORDER_SOFT@;
  border-radius: 22px;
  padding: 22px;
  background: linear-gradient(180deg, @CARD_BG@, transparent);
}
.section h2 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 16px;
  color: @TEXT@;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: .04em;
}
.section h2 .rule { flex: 1; height: 1px; background: @BORDER_SOFT@; }
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(128px, 1fr));
  gap: 12px;
}
.tile {
  position: relative;
  /* Column + centred: a grid row is as tall as its tallest tile, and the short
     labels used to sit at the top of that box with dead space underneath. */
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  background: @CARD_BG@;
  border: 1px solid @BORDER_SOFT@;
  border-radius: 16px;
  min-height: 92px;
  padding: 14px 10px;
  text-align: center;
  overflow: hidden;
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
}
.tile::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 0%, @GLOW1@, transparent 70%);
  opacity: 0;
  transition: opacity .15s ease;
}
.tile:hover,
.tile:focus-visible {
  transform: translateY(-4px);
  border-color: @ACCENT_HOVER@;
  box-shadow: 0 10px 24px @WATERMARK@;
  outline: none;
}
.tile:hover::before, .tile:focus-visible::before { opacity: 1; }
.tile:focus-visible { box-shadow: 0 0 0 3px @GLOW2@, 0 10px 24px @WATERMARK@; }
.tile-mark {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  margin: 0 auto 8px;
  border-radius: 50%;
  font-size: 20px;
  color: @ACCENT_HOVER@;
  background: radial-gradient(circle at 50% 32%, @ACCENT_SOFT@, transparent 78%);
  border: 1px solid @INPUT_BORDER@;
  transition: transform .15s ease, border-color .15s ease;
}
.tile-mark-letter {
  font-size: 19px;
  font-weight: 800;
  font-family: Georgia, serif;
  background: @ACCENT_SOFT@;
}
.tile:hover .tile-mark { transform: scale(1.08); border-color: @ACCENT@; }
.tile-label {
  position: relative;
  /* Two lines maximum, balanced across them: "MAS — Mahoraga Adapt System" and
     "MAS — Mahoraga Adapt System" otherwise stretched their whole grid row. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-wrap: balance;
  color: @TEXT@;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  min-height: 2.8em;
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
  margin-top: 30px;
  text-align: center;
  color: @TEXT_MUTED@;
  font-size: 11px;
  letter-spacing: .12em;
  text-transform: uppercase;
}

@media (max-width: 680px) {
  .hero { flex-direction: column; text-align: center; padding: 30px 22px; }
  .cup { width: 122px; height: 122px; }
  .cup-mug { width: 50px; height: 38px; }
  .cup-saucer { width: 74px; height: 8px; }
  .steam { width: 40px; height: 50px; }
  h1 { font-size: 34px; }
  .shell { padding: 28px 14px 32px; }
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
        '<span class="steam"><i></i><i></i><i></i></span>'
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
  <div class="awning"><span class="cup-logo">🍵</span> @BRAND@ · Tea Room Edition</div>
  <div class="shell">
    <div class="hero">
      <div class="cup">
        <div class="cup-art">
          %s
          <div class="cup-mug"></div>
          <div class="cup-saucer"></div>
        </div>
      </div>
      <div class="hero-copy">
        <div class="eyebrow">%s</div>
        <h1>%s</h1>
        <p>Search the web, reopen your work, or jump back into your saved reading from one calm starting point.</p>
        <form action="%s" method="get" class="search-bar">
          <input type="search" name="%s" placeholder="Search %s or type a URL..." autofocus />
        </form>
      </div>
    </div>
    %s
    <div class="section">
      <h2>Quick Shelf <span class="rule"></span></h2>
      <div class="tiles">%s</div>
    </div>
    <div class="section">
      <h2>Recent Pour <span class="rule"></span></h2>
      <div>%s</div>
    </div>
    <div class="hint-row">
      <span class="hint">? Help · F1</span>
      <span class="hint">⌨ Ctrl+T new tab</span>
      <span class="hint">Ctrl+K command</span>
      <span class="hint">/agent · /brief · /group-tabs</span>
    </div>
    <div class="footer-note">✦ @BRAND@ — privacy-first, local-first ✦</div>
  </div>
</body>
</html>""" % (
        escape_html(_CSP),
        css,
        steam_html,
        escape_html(eyebrow),
        escape_html(headline),
        escape_html(form_action),
        escape_html(form_param),
        escape_html(engine_label),
        support_section,
        tiles_html,
        recent_rows,
    )
    # One brand string for the whole app (core/product.py): this page used to
    # hard-code the pre-rename name, so a tab could read a different product than
    # the .exe that opened it.
    return html.replace("@BRAND@", app_version.APP_NAME)
