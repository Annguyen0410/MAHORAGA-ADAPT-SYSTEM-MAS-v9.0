"""Export center: bundle SafeVault notes for sharing or backup.

Two free formats from one dialog:
- Markdown bundle (zip): notes/ tree with categories as folders + an index.md
- Static HTML mini-site: index + one page per note, styled with the active
  theme palette; works offline, opens in any browser.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import time
import zipfile
from contextlib import contextmanager
from urllib.parse import quote, unquote, urlsplit

from litebrowser.core import prefs, storage_utils
from litebrowser.services import personal_service


def _safe_name(title: str) -> str:
    raw = re.sub(r'[\\/:*?"<>|]', "-", (title or "").strip())[:60]
    raw = raw.strip(" .")
    if raw.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raw = "_" + raw
    return raw or "note"


@contextmanager
def _atomic_zip(out_path):
    parent = os.path.dirname(os.path.abspath(out_path))
    fd, temporary = storage_utils.tempfile_mkstemp_same_dir(parent, os.path.basename(out_path))
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            yield archive
        with open(temporary, "r+b") as handle:
            os.fsync(handle.fileno())
        storage_utils._atomic_replace(temporary, out_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _note_digest(note):
    return hashlib.sha256(str(note.get("id", "")).encode("utf-8")).hexdigest()[:16]


def _render_html_page(title: str, content: str, theme_tokens: dict) -> str:
    """Minimal markdown-ish → HTML (headings, bold, lists, wiki-link hints,
    code, paragraphs). Enough for notes; never claims to be full CommonMark."""
    p = theme_tokens

    def inline(text: str) -> str:
        text = html.escape(text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
        text = re.sub(r"\[\[([^\]]+)\]\]", r'<span class="wl">\1</span>', text)
        def link(match):
            label, escaped_url = match.groups()
            url = html.unescape(escaped_url).strip()
            try:
                parsed = urlsplit(url)
            except ValueError:
                return label
            safe = parsed.scheme.lower() in ("http", "https", "mailto") or (
                not parsed.scheme and not parsed.netloc and url[:1] not in ("/", chr(92))
                and ".." not in re.split(r"[\\/]", unquote(url))
            )
            if not safe or any(ord(char) < 32 for char in url):
                return label
            return f'<a href="{html.escape(url, quote=True)}" rel="noopener noreferrer">{label}</a>'
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
        return text

    body_lines = []
    in_list = False
    in_code = False
    code_buf = []
    for line in content.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                body_lines.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
                code_buf = []
            in_code = not in_code
            continue
        if in_code:
            code_buf.append(line)
            continue
        if re.match(r"^\s*[-*] ", line):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append("<li>" + inline(re.sub(r"^\s*[-*] ", "", line)) + "</li>")
            continue
        if in_list:
            body_lines.append("</ul>")
            in_list = False
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            body_lines.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            continue
        if line.strip() == "---":
            body_lines.append("<hr>")
            continue
        if line.strip():
            body_lines.append(f"<p>{inline(line)}</p>")
    if in_list:
        body_lines.append("</ul>")
    if in_code and code_buf:
        body_lines.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>
body {{ background:{p['MAIN_BG']}; color:{p['TEXT']}; font-family:'Segoe UI',sans-serif;
       max-width:820px; margin:0 auto; padding:34px 22px; line-height:1.65; }}
h1,h2,h3 {{ color:{p['ACCENT_HOVER']}; font-family:Georgia,serif; }}
a {{ color:{p['ACCENT']}; }}
.wl {{ color:{p['ACCENT_HOVER']}; border-bottom:1px dotted {p['ACCENT']}; }}
pre {{ background:{p['MAIN_BG_ALT']}; padding:12px; border-radius:8px; overflow:auto; }}
code {{ background:{p['MAIN_BG_ALT']}; padding:1px 5px; border-radius:4px; }}
hr {{ border:none; border-top:1px solid {p['BORDER_SOFT']}; margin:18px 0; }}
footer {{ color:{p['TEXT_MUTED']}; font-size:12px; margin-top:34px; }}
</style></head><body>
{chr(10).join(body_lines)}
<footer>Exported from Mei · {html.escape(time.strftime('%Y-%m-%d %H:%M'))}</footer>
</body></html>"""


def export_notes_html(base_dir: str, out_path: str) -> int:
    """Static mini-site: index.html + note pages under notes/. Returns count."""
    # Exported HTML should look like the app in its *current* mode, not like the
    # stored preference (auto day/night would otherwise export day pages at night).
    mode = prefs.resolved_auto_theme(base_dir)
    from litebrowser.core import theme_data

    tokens = theme_data._palette(mode, prefs.get_accent(base_dir))
    notes = personal_service.list_notes(base_dir)
    if not notes:
        return 0
    # Write only current notes directly into a new archive; no stale site tree.
    pages = []
    with _atomic_zip(out_path) as archive:
        for note in notes:
            slug = _safe_name(note["title"]) + "-" + _note_digest(note) + ".html"
            relative = "notes/" + slug
            archive.writestr(relative, _render_html_page(note["title"], note["content"], tokens))
            pages.append((note["title"], note.get("category", "General"), relative))
        # Build the index with escaped HTML labels rather than interpreting
        # user-controlled titles as Markdown syntax.
        index = _render_html_page("Mei Notes", f"# Mei Notes\n\n{len(pages)} notes\n\n## All notes", tokens)
        listing = "<ul>" + "".join(
            f'<li><a href="{quote(relative, safe="/")}">{html.escape(title)}</a> · {html.escape(category)}</li>'
            for title, category, relative in pages
        ) + "</ul>"
        archive.writestr("index.html", index.replace("<footer>", listing + "<footer>", 1))
    return len(pages)


def export_notes_md_zip(base_dir: str, out_path: str) -> int:
    """Markdown bundle preserving categories as folders."""
    notes = personal_service.list_notes(base_dir)
    used = set()
    with _atomic_zip(out_path) as zf:
        index = ["# Mei notes index", ""]
        for note in notes:
            rel = os.path.join(_safe_name(note.get("category", "General")), _safe_name(note["title"]) + ".md")
            rel = rel.replace("\\", "/")
            if rel.casefold() in used:
                rel = rel[:-3] + "-" + _note_digest(note) + ".md"
            used.add(rel.casefold())
            zf.writestr(rel, note["content"])
            index.append(f"- [{note['title']}]({rel}) · {note.get('category', 'General')}")
        zf.writestr("index.md", "\n".join(index) + "\n")
    return len(notes)
