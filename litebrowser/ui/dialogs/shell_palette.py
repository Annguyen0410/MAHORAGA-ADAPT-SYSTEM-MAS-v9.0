"""Shell command palette: search every app feature *and your own content*.

Typing filters workspaces, Personal sub-pages, the bundled/remote sites and
every slash command by name — ``b`` surfaces Browser, Boards, Bookmarks,
Boards, ... Enter (or a click) executes the highlighted row through the
shell's own dispatch, so password-protected workspaces (AI / Personal)
prompt for the passcode first and then enter automatically.

Since 1.0.0.0 the same box also reaches *what you wrote*: ``content_entries``
adds your notes, cards, planner rows, tasks and saved pages under the feature
rows, because "jump to Notes" was never the hard part — "jump to the note I
half-remember" is. Feature rows and content rows are assembled here so the
palette dialog, the omnibar popup and the tests all read one list.
"""
from litebrowser.services import life_service, personal_service, tab_sets
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QWidget

from litebrowser.core import app_paths, prefs
from litebrowser.core.commands import COMMANDS

_WORKSPACES = (
    ("home", "Home", "🏠"),
    ("browser", "Browser", "🌐"),
    ("history", "History", "🕐"),
    ("ai", "AI Assistant", "✨"),
    ("personal", "Personal Hub", "◧"),
    ("library", "Library", "📚"),
    ("settings", "Settings", "⚙"),
)

_PERSONAL_PAGES = (
    ("overview", "Overview", "◧"),
    ("notes", "Notes", "✎"),
    ("plan", "Weekly Plan", "▦"),
    ("tasks", "Tasks", "✓"),
    ("review", "Review", "⇄"),
    ("calendar", "Calendar", "◷"),
    ("boards", "Boards", "◌"),
    ("files", "Files", "▦"),
    ("sites", "Sites", "↗"),
)


def _build_entries(parent) -> list[dict]:
    """The single feature registry behind the palette AND the omnibar popup.

    Each entry is a dict the shell dispatches on:
      kind      -> workspace | personal_page | site | hub | command
      payload   -> workspace key, page key, site key, or slash command text
      title/…   -> what the user sees and searches
    Because both UIs read from here, the omnibar and the palette can never
    drift out of sync.
    """
    entries: list[dict] = []
    for key, label, glyph in _WORKSPACES:
        entries.append(
            {
                "title": label,
                "category": "Workspace",
                "keywords": label.lower(),
                "glyph": glyph,
                "kind": "workspace",
                "payload": key,
            }
        )
    for key, label, glyph in _PERSONAL_PAGES:
        entries.append(
            {
                "title": "Personal · %s" % label,
                "category": "Personal page",
                "keywords": "personal %s %s" % (label.lower(), key),
                "glyph": glyph,
                "kind": "personal_page",
                "payload": key,
            }
        )
    seen = set()
    for site in app_paths.bundled_sites(getattr(parent, "app_dir", None)) + app_paths.chain_remote_sites(
        getattr(parent, "app_dir", None)
    ):
        key = site.get("key") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "title": site.get("display") or key,
                "category": "Open site",
                "keywords": " ".join(
                    str(part).lower()
                    for part in (site.get("display"), site.get("subtitle"), key)
                    if part
                ),
                "glyph": site.get("glyph", "↗"),
                "kind": "site",
                "payload": key,
            }
        )
    entries.append(
        {
            "title": "Project Hub",
            "category": "Open site",
            "keywords": "project hub chain apps portal",
            "glyph": "☰",
            "kind": "hub",
            "payload": None,
        }
    )
    for command in COMMANDS:
        entries.append(
            {
                "title": command.name,
                "category": command.description,
                "keywords": "%s %s" % (command.name, command.description),
                "glyph": "⚡",
                "kind": "command",
                "payload": command.completion(),
            }
        )
    return entries


#: Glyph + category per content kind returned by ``life_service.search_everything``
#: (plus ``note``, which comes from the note store). Used to paint a content row
#: exactly like a feature row so the popup does not need a second look.
CONTENT_GLYPHS = {
    "note": "✎",
    "task": "✓",
    "event": "◷",
    "board": "◌",
    "board-node": "◌",
    "saved-page": "▦",
    "planner-course": "▦",
    "planner-item": "▦",
    "planner-block": "◷",
    "flashcard": "⇄",
    "research_workspace": "⌘",
}

CONTENT_CATEGORIES = {
    "note": "Your note",
    "task": "Your task",
    "event": "Your calendar",
    "board": "Your board",
    "board-node": "Your board",
    "saved-page": "Saved page",
    "planner-course": "Your course",
    "planner-item": "Your plan",
    "planner-block": "Focus block",
    "flashcard": "Your card",
    "research_workspace": "Research workspace",
}

#: Two characters minimum: one letter matches half the profile, which is noise.
CONTENT_MIN_QUERY = 2


def content_entries(base_dir: str, query: str, limit: int = 8) -> list[dict]:
    """Your own records matching ``query``, shaped exactly like feature entries.

    Reads ``life_service.search_everything`` (tasks, calendar, boards, saved
    pages, courses, plan items, focus blocks, cards) plus the note store, which
    that function deliberately does not touch. Rows carry ``kind: "content"``
    with a payload the shell routes through ``open_library_item``, so a result
    lands where the item actually lives instead of opening a workspace.
    """
    q = (query or "").strip()
    if len(q) < CONTENT_MIN_QUERY or not base_dir:
        return []
    hits = list(life_service.search_everything(base_dir, q))
    try:
        # Notes come from their own store, and are tagged explicitly so the shell
        # routes them to the note editor (a bare row would route nowhere).
        hits.extend(
            {
                "kind": "note",
                "title": note.get("title", ""),
                "id": note.get("id", ""),
                "subtitle": note.get("category", ""),
            }
            for note in personal_service.list_notes(base_dir, q)
        )
    except Exception:  # noqa: BLE001  a broken vault must not break the omnibar
        pass
    research_hits = []
    try:
        needle = q.lower()
        research_hits = [
            {
                "kind": "research_workspace",
                "title": workspace.get("title", ""),
                "id": workspace.get("id", ""),
                "subtitle": f"{len(workspace.get('tabs', []))} saved tabs",
            }
            for workspace in tab_sets.list_tab_sets(base_dir)
            if workspace.get("kind") == "workspace"
            and not workspace.get("auto")
            and needle in str(workspace.get("title", "")).lower()
        ]
    except Exception:  # a broken optional collection store must not break search
        research_hits = []
    entries: list[dict] = []
    for hit in hits[: max(0, limit - min(limit, len(research_hits))) ] + research_hits[:limit]:
        kind = str(hit.get("kind", ""))
        title = str(hit.get("title", "") or "").strip() or "(untitled)"
        subtitle = str(hit.get("subtitle", "") or "").strip()
        entries.append(
            {
                "title": title,
                "category": CONTENT_CATEGORIES.get(kind, "Your content"),
                "keywords": f"{title.lower()} {subtitle.lower()} {kind}",
                "glyph": CONTENT_GLYPHS.get(kind, "•"),
                "kind": "content",
                "payload": {"kind": kind, "id": hit.get("id", ""), "subtitle": subtitle},
            }
        )
    return entries


def _base_dir(parent) -> str:
    return getattr(parent, "profile_dir", None) or getattr(parent, "base_dir", None) or ""


def _entry_haystack(entry: dict) -> str:
    return "%s %s %s" % (
        entry["title"].lower(),
        entry.get("category", "").lower(),
        entry.get("keywords", ""),
    )


def search_entries(feature_entries: list, base_dir: str, query: str) -> list:
    """Feature rows plus your content, ready for one popup.

    Content is appended so a query that names a feature (``review``) still lands
    on the feature first, while a query that names your work lands on your work.
    When content matches, the feature list is trimmed so the content rows cannot
    be pushed past a popup's row budget.
    """
    rows = filter_feature_entries(feature_entries, query)
    content = content_entries(base_dir, query)
    if content:
        return (rows[:24] + content)[:40]
    return rows


def filter_feature_entries(entries: list, q: str) -> list:
    """Feature rows matching ``q`` (case-insensitive substring over title +
    category + keywords). Any single letter must surface something: when a
    one-character query matches nothing, the whole registry is shown so the
    user can browse and keep typing to zoom in."""
    q = (q or "").strip().lower()
    rows = [e for e in entries if q in _entry_haystack(e)]
    if not rows and len(q) <= 1:
        rows = list(entries)
    return rows


def feature_row_widget(entry: dict, base: str) -> QWidget:
    """The glyph + title + category row used by the palette dialog AND the
    omnibar feature popup (kept in one place so both look identical)."""
    from litebrowser.ui import theme

    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(8, 3, 8, 3)
    row_layout.setSpacing(8)
    glyph = QLabel(entry.get("glyph", "◆"))
    glyph.setStyleSheet("font-size:15px;")
    row_layout.addWidget(glyph)
    title = QLabel(entry["title"])
    title.setStyleSheet("font-size:13px; font-weight:600;")
    row_layout.addWidget(title)
    row_layout.addStretch(1)
    category = QLabel(entry.get("category", ""))
    muted = theme.palette_tokens(prefs.resolved_auto_theme(base), prefs.get_accent(base))["TEXT_MUTED"]
    category.setStyleSheet("color:%s; font-size:11px;" % muted)
    row_layout.addWidget(category)
    return row


def add_feature_row(list_widget: QListWidget, entry: dict, base: str) -> QListWidgetItem:
    """Append one feature row to ``list_widget`` and return its item."""
    item = QListWidgetItem()
    row = feature_row_widget(entry, base)
    item.setSizeHint(row.sizeHint())
    list_widget.addItem(item)
    list_widget.setItemWidget(item, row)
    return item


def clear_feature_rows(list_widget: QListWidget) -> None:
    """Remove all rows, disposing their item widgets (safe to call repeatedly)."""
    while list_widget.count():
        item = list_widget.takeItem(0)
        widget = list_widget.itemWidget(item)
        if widget is not None:
            list_widget.removeItemWidget(item)
            widget.deleteLater()
        del item


