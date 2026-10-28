"""PersonalWindow: the Personal Hub workspace.

Nine pages (Overview, Weekly Plan, Notes, Tasks, Review, Calendar, Boards, Files, Sites)
sit in a QStackedWidget behind a navigation rail. The rail lives in a
QSplitter so it can be dragged wider/narrower AND collapsed with one click on
the divider (the same feel as the browser sidebar divider).

The Review page is a browsable flashcard deck (SM-2 scheduling); the Sites
page can show user-added sites only, or also the bundled project apps
(``Include bundled sites`` toggle, persisted in prefs).
"""
import copy
import hashlib
import math
import os
import random
import re
import time

from PyQt5.QtCore import (
    QDate,
    QEvent,
    QFileSystemWatcher,
    QPointF,
    QRect,
    QSize,
    QStringListModel,
    Qt,
    QTimer,
    QUrl,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PyQt5.QtWebEngineWidgets import (
    QWebEnginePage as _PersonalWebEnginePage,
)
from PyQt5.QtWebEngineWidgets import (
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineView,
)
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCalendarWidget,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QScrollArea,
    QFileDialog,
    QFrame,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from litebrowser.browser.browser_page import (
    BrowserPage,
    build_text_highlight_js,
    ensure_chrome_compat_script,
    ensure_text_highlight_script,
)
from litebrowser.qt import QtCore, QtGui, QtWidgets

QGridLayout = QtWidgets.QGridLayout

from litebrowser.core import app_paths, app_version, prefs
from litebrowser.services import (
    focus_service,
    life_service,
    link_service,
    personal_plan,
    personal_service,
    study_flow,
    study_session,
    tab_sets,
)
from litebrowser.ui import components, theme, win_titlebar
from litebrowser.ui.dialogs.common import (
    ghost_button,
    icon_button,
    more_menu,
    primary_button,
)
from litebrowser.ui.focus_heatmap import FocusHeatmap
from litebrowser.ui.board_canvas import BoardView, InkStrokeItem

MAX_NOTE_WATCH_DIRS = 64
NEURAL_GRAPH_MAX_NOTES = 48


class _MinuteTimeSpin(QSpinBox):
    """Keep the plan's integer minutes API, present a familiar 24-hour time."""
    def textFromValue(self, value):
        return f"{value // 60:02d}:{value % 60:02d}"

    def valueFromText(self, text):
        try:
            hour, minute = [int(part) for part in text.split(":")]
            return hour * 60 + minute
        except ValueError:
            return self.value()

    def validate(self, text, pos):
        state = QtGui.QValidator.State.Intermediate
        if re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", text):
            state = QtGui.QValidator.State.Acceptable
        elif len(text) > 5 or re.search(r"[^0-9:]", text):
            state = QtGui.QValidator.State.Invalid
        return state, text, pos


def _is_dark_palette(p: dict) -> bool:
    """Heuristic: MAIN_BG brightness decides whether canvas art should go dark."""
    try:
        value = str(p.get("MAIN_BG", "#000000")).lstrip("#")
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
        return (r * 299 + g * 587 + b * 114) / 1000 < 150
    except (TypeError, ValueError):
        return False


class NeuralGraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setMaximumHeight(180)
        self._tick = 0.0
        self._nodes: list[dict] = []
        self._edges: list[tuple[int, int]] = []
        self._total_note_count = 0
        self._subtitle = "No notes yet"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._visible = False
        self._cached_pixmap = None
        self._dirty = True

    def set_animation_running(self, run: bool):
        if run:
            if not self._timer.isActive():
                self._timer.start(50)
        else:
            self._timer.stop()
        self._visible = run

    def set_notes(self, notes: list, *, total_note_count: int | None = None):
        raw = notes or []
        self._total_note_count = int(total_note_count) if total_note_count is not None else len(raw)
        self._nodes = []
        title_index = {}
        for note in raw:
            nid = str(note.get("id") or "")
            title = (note.get("title") or "").strip()
            title_index[title.lower()] = len(self._nodes)
            # Deterministic layout: builtin hash() is salted per process, which
            # reshuffled the graph on every launch (v6.4 bug).
            digest = hashlib.md5(nid.encode("utf-8") or b"mei").hexdigest()
            h = int(digest[:8], 16)
            h2 = int(digest[8:16], 16)
            self._nodes.append(
                {
                    "phase": (h % 628) / 100.0,
                    "speed": 0.012 + (h % 17) / 500.0,
                    "layer": ((h >> 8) % 200) / 100.0 - 1.0,
                    "orbit": 0.25 + ((h >> 16) % 75) / 100.0,
                    "title": title[:28],
                    "hue": (h2 % 40) - 20,
                }
            )
        # Real edges from [[wiki-links]]: a link between two known notes draws
        # as a highlighted connection (v6.6 turns the decorative graph into an
        # actual note map).
        self._edges = []
        for note in raw:
            src = title_index.get((note.get("title") or "").strip().lower())
            if src is None:
                continue
            for match in WIKILINK_RE.finditer(note.get("content") or ""):
                dst = title_index.get(match.group(1).strip().lower())
                if dst is not None and dst != src:
                    edge = (min(src, dst), max(src, dst))
                    if edge not in self._edges:
                        self._edges.append(edge)
        if self._total_note_count == 0:
            self._subtitle = "No notes yet"
        elif self._edges:
            self._subtitle = f"{self._total_note_count} notes · {len(self._edges)} links"
        else:
            self._subtitle = f"{self._total_note_count} notes · type [[ to link"
        if not self._nodes:
            for _idx in range(10):
                self._nodes.append(
                    {
                        "phase": random.uniform(0.0, math.pi * 2.0),
                        "speed": random.uniform(0.012, 0.03),
                        "layer": random.uniform(-0.8, 0.8),
                        "orbit": random.uniform(0.35, 0.9),
                        "title": "",
                        "hue": 0,
                    }
                )
            self._subtitle = "Add notes to populate this graph"
        self._dirty = True
        self.update()

    def _advance(self):
        self._tick += 1.0
        self._dirty = True
        self.update()

    def paintEvent(self, event):
        if not self._visible:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Follow the active theme instead of hardcoded cream colors that glared
        # in every dark theme (v6.4 bug).
        p = theme.palette()
        dark = _is_dark_palette(p)
        painter.fillRect(self.rect(), QColor(p["MAIN_BG_ALT"]) if dark else QColor(p["CARD_BG"]))

        w = max(1, self.width())
        h = max(1, self.height())
        cx = w * 0.5
        cy = h * 0.52
        points = []
        for index, node in enumerate(self._nodes):
            angle = node["phase"] + self._tick * node["speed"]
            depth = math.sin(angle * 0.7 + index * 0.4 + node["layer"]) * 0.5 + 0.5
            radius_x = w * (0.14 + 0.26 * node["orbit"])
            radius_y = h * (0.10 + 0.18 * node["orbit"])
            x = cx + math.cos(angle) * radius_x * (0.65 + depth * 0.6)
            y = cy + math.sin(angle * 1.35) * radius_y + (node["layer"] * 18.0)
            size = 2.5 + depth * 6.5
            points.append((x, y, size, depth, node))

        base_rgb = (140, 170, 210) if dark else (155, 109, 60)
        accent = QColor(p["ACCENT"])
        # Real wiki-link edges first (under the dots): thick accent lines.
        for src, dst in self._edges:
            if src >= len(points) or dst >= len(points):
                continue
            x1, y1, _s1, _d1, _n1 = points[src]
            x2, y2, _s2, _d2, _n2 = points[dst]
            painter.setPen(QPen(accent, 2))
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        # Decorative proximity lines only between unlinked pairs.
        linked = {e for e in self._edges}
        for idx, (x1, y1, _s1, d1, _n1) in enumerate(points):
            limit = min(idx + 4, len(points))
            for jdx in range(idx + 1, limit):
                if (min(idx, jdx), max(idx, jdx)) in linked:
                    continue
                x2, y2, _s2, d2, _n2 = points[jdx]
                alpha = int(30 + 70 * ((d1 + d2) * 0.5))
                painter.setPen(QPen(QColor(*base_rgb, alpha), 1))
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        for x, y, size, depth, node in points:
            dh = int(node.get("hue") or 0)
            glow = QColor(
                max(0, min(255, accent.red() + dh)),
                max(0, min(255, accent.green() + dh // 2)),
                max(0, min(255, accent.blue())),
                int(90 + depth * 120),
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(int(x - size), int(y - size), int(size * 2), int(size * 2))

        painter.setPen(QColor(p["TEXT_MUTED"]))
        painter.drawText(12, 20, "Neural Notes Graph")
        painter.drawText(12, 36, self._subtitle)
        painter.end()


class StickyCardItem(QGraphicsRectItem):
    def __init__(self, node: dict):
        super().__init__(0, 0, 220, 120)
        self.node = node
        self._edges = []
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
        )
        p = theme.palette()
        fill = QColor(node.get("color") or p["CARD_BG"])
        self.setBrush(QBrush(fill))
        self.setPen(QPen(QColor(p["BORDER_SOFT"]), 2))
        self.setPos(float(node.get("x", 40)), float(node.get("y", 40)))
        # Text contrast follows the fill: light cards get ink, dark cards get
        # the theme text color (v6.4 always painted near-black text).
        lum = (fill.red() * 299 + fill.green() * 587 + fill.blue() * 114) / 1000
        text_color = QColor(p["TEXT"]) if lum < 150 else QColor("#1b140f")
        text = QGraphicsTextItem(node.get("title", "Card"), self)
        text.setDefaultTextColor(text_color)
        text.setTextWidth(190)
        text.setPos(14, 12)
        body = node.get("payload", "").strip()
        if body:
            body_item = QGraphicsTextItem(body[:180], self)
            body_item.setDefaultTextColor(text_color)
            body_item.setTextWidth(190)
            body_item.setPos(14, 42)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemPositionHasChanged:
            for edge in self._edges:
                edge.update_path()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    """A dashed connector between two sticky cards that follows them as they move."""

    def __init__(self, edge: dict, from_item: StickyCardItem, to_item: StickyCardItem):
        super().__init__()
        self.edge = dict(edge or {})
        self.from_item = from_item
        self.to_item = to_item
        self.setZValue(-15)  # below cards, above ink strokes
        self.setAcceptedMouseButtons(Qt.NoButton)
        color = self.edge.get("color") or "#a36a3c"
        self.setPen(QPen(QColor(color), 2, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
        from_item._edges.append(self)
        to_item._edges.append(self)
        self.update_path()

    def update_path(self):
        start = self.from_item.mapToScene(self.from_item.rect().center())
        end = self.to_item.mapToScene(self.to_item.rect().center())
        path = QPainterPath(QPointF(start.x(), start.y()))
        path.lineTo(QPointF(end.x(), end.y()))
        self.setPath(path)


class MeiNotesList(QListWidget):
    """Notes list with drag-to-reorder. Records the dragged note ids on the
    owner so the categories panel can move them without decoding Qt's internal
    drag mime format."""

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(self.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(self.SelectionMode.SingleSelection)

    def startDrag(self, supported_actions):
        self._owner._drag_note_ids = [it.data(Qt.UserRole) for it in self.selectedItems()]
        try:
            super().startDrag(supported_actions)
        finally:
            self._owner._drag_note_ids = []

    def dropEvent(self, event):
        super().dropEvent(event)
        # InternalMove just reordered the rows — persist the new arrangement.
        self._owner._persist_note_order()


class CategoryDropList(QListWidget):
    """Drop target listing note categories. Dropping a note onto a category
    moves the note's file into that category folder."""

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setAcceptDrops(True)
        self.setDragDropMode(self.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.MoveAction)

    def dropEvent(self, event):
        target_item = self.itemAt(event.pos())
        category = target_item.data(Qt.UserRole) if target_item else ""
        note_ids = list(getattr(self._owner, "_drag_note_ids", []) or [])
        if category and note_ids:
            self._owner._move_notes_to_category(note_ids, category)
            event.accept()
        else:
            # No category target or no dragged note: ignore instead of
            # accepting a silent no-op (v6.4 swallowed every drop).
            event.ignore()


WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")

# Writing sizes in CSS pixels, matching the textSize rules in the stylesheet so
# the Tools row control actually moves the editor (see _apply_note_font_size).
NOTE_FONT_SIZES = (13, 14, 15, 16, 18, 20)
NOTE_FONT_DEFAULT = 15

# The note id stays on Qt.UserRole (drag-reorder, deep links and the category
# drop target all read it); the rendered row payload travels beside it.
NOTE_ID_ROLE = Qt.UserRole
NOTE_ROW_ROLE = Qt.UserRole + 1
# Reading measure: a comfortable line of prose, in pixels.
NOTE_MEASURE_MAX = 760


def _repolish(widget):
    """Re-apply the stylesheet so a dynamic property takes effect."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def _option_is_selected(option, index) -> bool:
    """Whether the row is selected — read without Qt flag arithmetic.

    The documented ``option.state & QStyle.State_Selected`` test crashed the
    whole process inside the list's paint pass on the Qt/PyQt build this app
    ships with (STATUS_STACK_BUFFER_OVERRUN, no traceback), so the selection is
    asked of the view's own selection model instead. A synthetic option with no
    widget — a test painting a row by hand — simply reports unselected.
    """
    widget = getattr(option, "widget", None)
    if widget is None or index is None:
        return False
    try:
        if not index.isValid():
            return False
        selection = widget.selectionModel()
        return bool(selection.isSelected(index)) if selection is not None else False
    except (AttributeError, TypeError, RuntimeError):
        return False


def _text_width(metrics: QFontMetrics, text: str) -> int:
    """QFontMetrics.width() is gone in Qt6; horizontalAdvance() is Qt5.11+."""
    advance = getattr(metrics, "horizontalAdvance", None)
    if advance is not None:
        return int(advance(text))
    return int(metrics.width(text))


def _friendly_age(epoch: str) -> str:
    """"today" / "3d ago" for a note's mtime — plain language, no invented data."""
    try:
        stamp = int(epoch)
    except (TypeError, ValueError):
        return ""
    if stamp <= 0:
        return ""
    seconds = max(0, int(time.time()) - stamp)
    if seconds < 90:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days}d ago"
    if days < 60:
        return f"{days // 7}w ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def _note_preview(note: dict, limit: int = 160) -> str:
    """The note's own opening lines, minus the heading that repeats the title.

    Built from the stored content only — no guessed titles, no summaries.
    """
    lines = (note.get("content") or "").splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    text = " ".join(line.strip() for line in lines if line.strip())
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _note_word_count(note: dict) -> int:
    return sum(1 for _ in re.finditer(r"\S+", note.get("content") or ""))


def _note_row_payload(note: dict) -> dict:
    """Everything the row delegate paints, derived from the note record."""
    category = (note.get("category") or "General").strip() or "General"
    bits = []
    age = _friendly_age(note.get("updated_at", ""))
    if age:
        bits.append(age)
    words = _note_word_count(note)
    if words:
        bits.append(f"{words} words" if words != 1 else "1 word")
    return {"title": note.get("title") or "(untitled)", "category": category, "meta": "  ·  ".join(bits)}


class NoteRowDelegate(QStyledItemDelegate):
    """A note row: an elided title over a quiet category · age · length line.

    Painted rather than plain-labelled so a long title elides at the column edge
    instead of being clipped mid-word, and so the shelf carries a little
    metadata without turning every row into a box. The theme still paints the
    row itself (hover, selected wash, focus), so this only draws text on top.
    Rows without a payload — the empty-list hint — keep the default painting.
    """

    ROW_HEIGHT = 50
    LINE_GAP = 2

    def sizeHint(self, option, index):
        if index.data(NOTE_ROW_ROLE):
            return QSize(0, self.ROW_HEIGHT)
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        payload = index.data(NOTE_ROW_ROLE)
        if not payload:
            super().paint(painter, option, index)
            return
        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        super().paint(painter, base, index)

        inner = option.rect.adjusted(11, 6, -8, -5)
        if inner.width() < 24 or inner.height() < 18:
            return
        try:
            p = theme.palette()
        except (AttributeError, KeyError, RuntimeError, TypeError):
            # A paint pass must never be the thing that crashes the window.
            return
        title_font = components._font(13, components.WEIGHT_DEMI)
        meta_font = components._font(10, components.WEIGHT_NORMAL)
        title_metrics = QFontMetrics(title_font)
        meta_metrics = QFontMetrics(meta_font)
        block = title_metrics.height() + self.LINE_GAP + meta_metrics.height()
        top = inner.top() + max(0, (inner.height() - block) // 2)

        painter.save()
        painter.setFont(title_font)
        # The wash + left rule come from the theme; the title picks up the accent
        # ink so the open note is unmistakable at a glance.
        painter.setPen(QColor(p["ACCENT_HOVER"] if _option_is_selected(option, index) else p["TEXT"]))
        painter.drawText(
            QRect(inner.left(), top, inner.width(), title_metrics.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            title_metrics.elidedText(str(payload.get("title") or ""), Qt.ElideRight, inner.width()),
        )

        meta_top = top + title_metrics.height() + self.LINE_GAP
        meta_rect = QRect(inner.left(), meta_top, inner.width(), meta_metrics.height())
        painter.setFont(meta_font)
        category = str(payload.get("category") or "")
        if category:
            painter.setPen(QColor(p["CLAY"]))
            chip = meta_metrics.elidedText(category, Qt.ElideRight, max(0, inner.width() - 20))
            painter.drawText(meta_rect, Qt.AlignLeft | Qt.AlignVCenter, chip)
            used = _text_width(meta_metrics, chip) + _text_width(meta_metrics, "  ·  ")
            rest = QRect(
                meta_rect.left() + used,
                meta_rect.top(),
                max(0, meta_rect.width() - used),
                meta_rect.height(),
            )
            if rest.width() > 12:
                painter.setPen(QColor(p["TEXT_MUTED"]))
                painter.drawText(
                    rest,
                    Qt.AlignLeft | Qt.AlignVCenter,
                    meta_metrics.elidedText(str(payload.get("meta") or ""), Qt.ElideRight, rest.width()),
                )
        else:
            painter.setPen(QColor(p["TEXT_MUTED"]))
            painter.drawText(
                meta_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                meta_metrics.elidedText(str(payload.get("meta") or ""), Qt.ElideRight, meta_rect.width()),
            )
        painter.restore()


class WikiLinkHighlighter(QSyntaxHighlighter):
    """Paints [[wiki-links]] in the accent color and underlines them, so the
    Obsidian-style linking is visible while writing. Pure regex over the block
    text; no per-char cost beyond the matched spans."""

    def __init__(self, document, palette_getter):
        super().__init__(document)
        self._palette_getter = palette_getter

    def highlightBlock(self, text):
        pal = self._palette_getter() or {}
        accent = QColor(pal.get("ACCENT", "#A66A2E"))
        fmt = QTextCharFormat()
        fmt.setForeground(accent)
        fmt.setFontUnderline(True)
        for match in WIKILINK_RE.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), fmt)



class PlannerDayList(QListWidget):
    """A read-only day column that supports dragging items to another day."""

    def __init__(self, owner, day_key: str, parent=None):
        super().__init__(parent)
        self._owner = owner
        self.day_key = day_key
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # DragDrop (rather than DragOnly) is required for Qt to deliver drops
        # to another day column; dropEvent performs the persisted reschedule.
        self.setDragDropMode(self.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(self.SelectionMode.SingleSelection)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        item_id = item.data(Qt.UserRole) if item is not None else ""
        if not item_id:
            return
        self._owner._planner_drag_item_id = str(item_id)
        self._owner._planner_drag_source_day = self.day_key
        try:
            super().startDrag(supported_actions)
        finally:
            self._owner._planner_drag_item_id = ""
            self._owner._planner_drag_source_day = ""

    def dragEnterEvent(self, event):
        if getattr(self._owner, "_planner_drag_item_id", ""):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if getattr(self._owner, "_planner_drag_item_id", ""):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        item_id = str(getattr(self._owner, "_planner_drag_item_id", "") or "")
        if not item_id:
            event.ignore()
            return
        if self._owner._planner_drop_item(item_id, self.day_key):
            event.acceptProposedAction()
        else:
            event.ignore()


class _CourseDialog(QDialog):
    """Create/edit form for a planner course (name, code, color, schedule, credits)."""

    def __init__(self, parent=None, course: dict | None = None):
        super().__init__(parent)
        course = course or {}
        self.setWindowTitle(f"Course - {app_version.APP_NAME}")
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.ed_name = QLineEdit(course.get("name", ""))
        self.ed_name.setPlaceholderText("Course name")
        self.ed_code = QLineEdit(course.get("code", ""))
        self.ed_code.setPlaceholderText("e.g. MA101")
        self.ed_schedule = QLineEdit(course.get("schedule", ""))
        self.ed_schedule.setPlaceholderText("e.g. Tue 09:00 · Room B2")
        self.ed_credits = QLineEdit(course.get("credits", ""))
        self.ed_credits.setPlaceholderText("e.g. 3")
        self.ed_color = QLineEdit(course.get("color", "#c39d63"))
        self.btn_color = QPushButton("Pick…")
        self.btn_color.clicked.connect(self._pick_color)
        color_row = QHBoxLayout()
        color_row.addWidget(self.ed_color, 1)
        color_row.addWidget(self.btn_color)
        color_holder = QWidget()
        color_holder.setLayout(color_row)

        for label_text, widget in (
            ("Name", self.ed_name),
            ("Code", self.ed_code),
            ("Schedule", self.ed_schedule),
            ("Credits", self.ed_credits),
            ("Color", color_holder),
        ):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setMinimumWidth(70)
            row.addWidget(label)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_save)
        layout.addLayout(buttons)

    def _pick_color(self):
        chosen = QColorDialog.getColor(
            QColor(self.ed_color.text().strip() or "#c39d63"), self, "Course color"
        )
        if chosen.isValid():
            self.ed_color.setText(chosen.name())

    def values(self) -> dict:
        return {
            "name": self.ed_name.text().strip(),
            "code": self.ed_code.text().strip(),
            "schedule": self.ed_schedule.text().strip(),
            "credits": self.ed_credits.text().strip(),
            "color": self.ed_color.text().strip() or "#c39d63",
        }


class _BlockDialog(QDialog):
    """Edit a planner time block: title, start, duration, optional course."""

    def __init__(self, parent=None, block: dict | None = None, courses: list | None = None):
        super().__init__(parent)
        block = block or {}
        courses = courses or []
        self.setWindowTitle(f"Time block - {app_version.APP_NAME}")
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.ed_title = QLineEdit(block.get("title", ""))
        self.ed_title.setPlaceholderText("Study block title")
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 1439)
        self.spin_start.setValue(int(block.get("start_minutes", 540) or 0))
        self.spin_start.setSuffix(" start min")
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(5, 1440)
        self.spin_duration.setValue(int(block.get("duration_minutes", 50) or 50))
        self.spin_duration.setSuffix(" min")
        self.cmb_course = QComboBox()
        self.cmb_course.addItem("— No course —", "")
        for course in courses:
            self.cmb_course.addItem(course.get("name", ""), course.get("id", ""))
        index = self.cmb_course.findData(block.get("course_id", "") or "")
        self.cmb_course.setCurrentIndex(max(0, index))

        for label_text, widget in (
            ("Title", self.ed_title),
            ("Start", self.spin_start),
            ("Duration", self.spin_duration),
            ("Course", self.cmb_course),
        ):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setMinimumWidth(70)
            row.addWidget(label)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_save)
        layout.addLayout(buttons)

    def values(self) -> dict:
        return {
            "title": self.ed_title.text().strip(),
            "start_minutes": self.spin_start.value(),
            "duration_minutes": self.spin_duration.value(),
            "course_id": self.cmb_course.currentData() or "",
        }


class PersonalWindow(QMainWindow):
    def __init__(self, base_dir: str, app_dir: str = None, embedded: bool = False):
        super().__init__()
        self.base_dir = prefs.ensure_profile_layout(base_dir)
        self.app_dir = app_dir or app_paths.project_root()
        self.embedded = embedded
        self.current_note_id = None
        self.current_note_category = "General"
        self._note_title = ""
        self._note_dirty = False
        self._suppress_note_dirty = False
        self.current_board_id = None
        self._site_preview_on = False
        self._nav_collapsed = False
        self._drag_note_ids = []
        self._current_note_image_path = ""
        self._note_find_matches = []
        self.setWindowTitle(f"Personal Hub - {app_version.APP_NAME}")
        self.setWindowIcon(QIcon(os.path.join(self.app_dir, "icon.png")))
        self.resize(1160, 760)
        self.setMinimumSize(0 if embedded else 900, 0 if embedded else 620)
        if not self.embedded:
            win_titlebar.apply_dark_titlebar(self, enabled=True)

        root = QWidget()
        root.setObjectName("PersonalWorkspace")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav = QWidget()
        nav.setObjectName("LeftRail")
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(8, 10, 8, 10)
        nav_layout.setSpacing(3)
        self.btn_nav_toggle = QPushButton("≪")
        self.btn_nav_toggle.setCheckable(True)
        self.btn_nav_toggle.setToolTip("Collapse / expand the sidebar")
        self.btn_nav_toggle.setObjectName("NavToggle")
        nav_layout.addWidget(self.btn_nav_toggle, 0, Qt.AlignRight)
        # The rail names the room without spending a hero block on it: one
        # serif line, one muted hint, then the shelf of pages.
        self.nav_header = QWidget()
        self.nav_header.setObjectName("RailBrandWrap")
        nav_head_layout = QVBoxLayout(self.nav_header)
        nav_head_layout.setContentsMargins(8, 0, 6, 4)
        nav_head_layout.setSpacing(0)
        nav_title = QLabel("Personal")
        nav_title.setObjectName("RailBrand")
        nav_head_layout.addWidget(nav_title)
        nav_hint = QLabel("Notes, plan, cards, calendar")
        nav_hint.setObjectName("RailProfile")
        nav_hint.setWordWrap(True)
        nav_head_layout.addWidget(nav_hint)
        nav_layout.addWidget(self.nav_header)
        self.nav_buttons = {}
        for key, label, glyph in (
            ("overview", "Overview", "◧"),
            ("notes", "Notes", "✎"),
            ("plan", "Weekly Plan", "▦"),
            ("tasks", "Tasks", "✓"),
            ("review", "Review", "⇄"),
            ("calendar", "Calendar", "◷"),
            ("boards", "Boards", "◌"),
            ("files", "Files", "▤"),
            ("sites", "Sites", "↗"),
        ):
            button = components.nav_button(label, glyph)
            button.clicked.connect(lambda checked, item=key: self._switch_page(item))
            self.nav_buttons[key] = button
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        # Session controls are housekeeping, not destinations: quiet links at
        # the foot of the shelf instead of two filled buttons.
        self.btn_save_set = QPushButton("Save session")
        self.btn_save_set.setObjectName("QuietButton")
        self.btn_save_set.setToolTip("Save the current Personal session state")
        self.btn_set_root = QPushButton("Set root…")
        self.btn_set_root.setObjectName("QuietButton")
        self.btn_set_root.setToolTip("Choose the folder that stores personal data")
        nav_layout.addWidget(self.btn_save_set)
        nav_layout.addWidget(self.btn_set_root)
        # The nav rail lives in a splitter so it is both resizable by dragging
        # the divider and collapsible (click the divider, or the « button).
        # The stack ignores horizontal size hints on purpose: the Boards/Notes
        # pages hint ~1340px wide, which otherwise locks the divider shut (the
        # stack would refuse to shrink and the rail could never widen).
        self.nav_splitter = QSplitter(Qt.Horizontal)
        self.nav_splitter.setChildrenCollapsible(False)
        self.nav_splitter.setHandleWidth(8)
        layout.addWidget(self.nav_splitter)
        self.nav_splitter.addWidget(nav)
        self.btn_nav_toggle.toggled.connect(self._toggle_nav_collapse)

        self.stack = QStackedWidget()
        # Ignore the pages' (large) horizontal minimum hints — the boards/notes
        # pages hint ~1340px, which otherwise locks the divider: the nav could
        # never widen because the stack refused to shrink. Content pages stay
        # fully usable; they scroll/compact like they already do when the
        # window is narrow.
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.nav_splitter.addWidget(self.stack)
        self.nav_splitter.setStretchFactor(0, 0)
        self.nav_splitter.setStretchFactor(1, 1)
        self.nav_splitter.setCollapsible(0, False)
        self.nav_splitter.setCollapsible(1, False)
        self._nav_split_press = None
        _nav_handle = self.nav_splitter.handle(1)
        if _nav_handle is not None:
            _nav_handle.installEventFilter(self)
        self.page_order = {}
        for key, widget in (
            ("overview", self._build_overview_page()),
            ("notes", self._build_notes_page()),
            ("plan", self._build_plan_page()),
            ("tasks", self._build_tasks_page()),
            ("review", self._build_review_page()),
            ("calendar", self._build_calendar_page()),
            ("boards", self._build_boards_page()),
            ("files", self._build_files_page()),
            ("sites", self._build_sites_page()),
        ):
            self.page_order[key] = self.stack.count()
            self.stack.addWidget(widget)

        self.btn_set_root.clicked.connect(self._choose_root)
        self.btn_save_set.clicked.connect(self.save_current_set)
        self.setStyleSheet(theme.main_qss(prefs.resolved_auto_theme(self.base_dir), prefs.get_accent(self.base_dir)))
        self._switch_page("overview")
        self.refresh_all()
        self._apply_compact_layout()
        self._setup_notes_fs_watcher()
        # Every visible string is selectable/copyable: labels highlight with
        # the mouse, buttons get a right-click "Copy text" menu.
        from litebrowser.ui.textselect import enable_text_selection

        enable_text_selection(self)

    def _setup_notes_fs_watcher(self):
        self._notes_fs_watcher = QFileSystemWatcher(self)
        self._notes_fs_watcher.directoryChanged.connect(self._on_notes_directory_changed)
        self._notes_refresh_debounce = QTimer(self)
        self._notes_refresh_debounce.setSingleShot(True)
        self._notes_refresh_debounce.setInterval(300)
        self._notes_refresh_debounce.timeout.connect(self._refresh_notes_from_fs)
        self._notes_watch_hashes = set()
        self._sync_notes_watcher_paths()

    def _get_notes_dirs_checksum(self):
        nd = personal_service.notes_dir(self.base_dir)
        hasher = hashlib.md5()
        if os.path.isdir(nd):
            for root, subdirs, _files in os.walk(nd):
                for d in sorted(subdirs):
                    hasher.update(os.path.join(root, d).encode("utf-8"))
        return hasher.hexdigest()

    def _sync_notes_watcher_paths(self):
        if not hasattr(self, "_notes_fs_watcher"):
            return
        nd = personal_service.notes_dir(self.base_dir)
        current_hash = self._get_notes_dirs_checksum()
        if current_hash in self._notes_watch_hashes:
            return
        for p in list(self._notes_fs_watcher.directories()):
            self._notes_fs_watcher.removePath(p)
        dirs_to_watch = []
        if os.path.isdir(nd):
            dirs_to_watch.append(nd)
            for root, subdirs, _files in os.walk(nd):
                for d in subdirs:
                    dirs_to_watch.append(os.path.join(root, d))
                    if len(dirs_to_watch) >= MAX_NOTE_WATCH_DIRS:
                        break
                if len(dirs_to_watch) >= MAX_NOTE_WATCH_DIRS:
                    break
        if len(dirs_to_watch) > MAX_NOTE_WATCH_DIRS:
            dirs_to_watch = [nd] if os.path.isdir(nd) else []
        for d in dirs_to_watch:
            if os.path.isdir(d):
                self._notes_fs_watcher.addPath(d)
        self._notes_watch_hashes.add(current_hash)
        if len(self._notes_watch_hashes) > 10:
            self._notes_watch_hashes = set(list(self._notes_watch_hashes)[-5:])

    def _on_notes_directory_changed(self, _path: str):
        self._notes_refresh_debounce.start()

    def _refresh_notes_from_fs(self):
        self._sync_notes_watcher_paths()
        if hasattr(self, "notes_list"):
            self._refresh_notes()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(0, self.width())
        bucket = 600 if width < 600 else 820 if width < 820 else 980 if width < 980 else 1220 if width < 1220 else 1 << 30
        if bucket != getattr(self, "_compact_bucket", None):
            self._compact_bucket = bucket
            self._apply_compact_layout()

    def _apply_compact_layout(self):
        width = max(0, self.width())
        if hasattr(self, "_boards_splitter"):
            self._boards_splitter.setSizes([110 if width < 980 else 200, max(240, width - 340)])
        if hasattr(self, "categories_list"):
            self.categories_list.setVisible(width >= 680)
            self._categories_hint.setVisible(width >= 680)
        if hasattr(self, "_notes_splitter"):
            orientation = Qt.Vertical if width < 680 else Qt.Horizontal
            if self._notes_splitter.orientation() != orientation:
                self._notes_splitter.setOrientation(orientation)
                self._notes_splitter.setSizes([100, 400] if width < 680 else [220, 620])
        if hasattr(self, "_editor_layout"):
            self._apply_notes_measure()
        if getattr(self, "_nav_collapsed", False):
            nav = self.findChild(QWidget, "LeftRail")
            if nav:
                nav.setMinimumWidth(56)
                nav.setMaximumWidth(320)
            sw = max(0, width)
            if sw > 0:
                self.nav_splitter.setSizes([56, max(240, sw - 56)])
            for button in getattr(self, "nav_buttons", {}).values():
                button.setVisible(True)
                button.setText(button.property("navGlyph") or "◇")
                button.setToolTip(button.property("navLabel") or "")
                self._set_icon_only(button, True)
                button.setMinimumHeight(34)
                button.setMaximumHeight(40)
            self.btn_save_set.setVisible(False)
            self.btn_set_root.setVisible(False)
            self.nav_header.setVisible(False)
            self.btn_nav_toggle.setVisible(True)
            return
        self.nav_header.setVisible(width >= 820)
        compact = width < 1220
        narrow = width < 980
        tiny = width < 820
        xtiny = width < 600
        # The rail keeps its labels down to the narrowest desktop width: two
        # unlabelled icon columns side by side read as a broken layout, not as
        # a compact one.  Only phone-sized panes fall back to glyphs.
        default_w = 64 if xtiny else 132 if tiny else 138 if narrow else 146 if compact else 162
        nav = self.findChild(QWidget, "LeftRail")
        if nav:
            # Never lock min == max: the divider must stay draggable (dragging
            # is how users resize the bar; a fixed-width lock made it look
            # stuck in earlier builds). Only re-anchor when out of range.
            nav.setMinimumWidth(56)
            nav.setMaximumWidth(320)
            current = nav.width()
            sw = max(0, width)
            nav_bucket = 600 if xtiny else 820 if tiny else 980 if narrow else 1220 if compact else 1 << 30
            changed_bucket = nav_bucket != getattr(self, "_nav_size_bucket", None)
            self._nav_size_bucket = nav_bucket
            if changed_bucket or current < 56 or current > 320:
                if sw > 0:
                    self.nav_splitter.setSizes([default_w, max(300, sw - default_w)])
        self.btn_save_set.setVisible(not tiny)
        self.btn_set_root.setVisible(not tiny)
        if hasattr(self, "nav_buttons"):
            for key, button in self.nav_buttons.items():
                button.setVisible(True)
                labels = {
                    "overview": ("Overview", "◧"),
                    "notes": ("Notes", "✎"),
                    "plan": ("Weekly Plan", "▦"),
                    "tasks": ("Tasks", "✓"),
                    "calendar": ("Calendar", "◷"),
                    "boards": ("Boards", "◌"),
                    "files": ("Files", "▦"),
                    "sites": ("Sites", "↗"),
                    "review": ("Review", "⇄"),
                }
                label, glyph = labels.get(key, (key.title(), "◇"))
                icon_only = xtiny
                button.setText(glyph if icon_only else f"{glyph}  {label}")
                button.setToolTip(label)
                self._set_icon_only(button, icon_only)
                button.setMinimumHeight(34)
                button.setMaximumHeight(40)

    @staticmethod
    def _set_icon_only(button, icon_only: bool):
        """Keep the QSS in step with a glyph-only rail button."""
        if bool(button.property("iconOnly")) == bool(icon_only):
            return
        button.setProperty("iconOnly", bool(icon_only))
        style = button.style()
        if style is not None:
            style.unpolish(button)
            style.polish(button)
        button.update()

    def _toggle_nav_collapse(self, checked: bool):
        self._nav_collapsed = bool(checked)
        self.btn_nav_toggle.setText("≫" if checked else "≪")
        self._apply_compact_layout()
        if not checked:
            # Coming out of the 46px rail: explicitly re-open to a usable
            # width (the expanded branch only re-anchors out-of-range widths,
            # and 46 is exactly the rail minimum so it would stay stuck).
            width = max(0, self.width())
            default_w = 98 if width < 820 else 112 if width < 980 else 126 if width < 1220 else 150
            sw = max(0, width)
            if sw > 0:
                self.nav_splitter.setSizes([default_w, max(300, sw - default_w)])

    def eventFilter(self, obj, ev):
        # Writing column: its width decides the editor's measure, and it is the
        # splitter/layout that actually knows the final size (a window resize
        # reaches _apply_compact_layout before the splitter settles).
        if obj is getattr(self, "_writing_column", None):
            if ev.type() == QEvent.Type.Resize:
                QTimer.singleShot(0, self._apply_notes_measure)
            return super().eventFilter(obj, ev)
        # Divider between the nav rail and the content: drag to resize, bare
        # click (or double-click) to collapse/expand — same feel as the
        # browser sidebar divider.
        handle = self.nav_splitter.handle(1) if hasattr(self, "nav_splitter") else None
        if handle is not None and obj is handle:
            et = ev.type()
            if et == QEvent.Type.MouseButtonPress and ev.button() == Qt.LeftButton:
                self._nav_split_press = (ev.pos(), list(self.nav_splitter.sizes()), False)
            elif et == QEvent.Type.MouseButtonDblClick and ev.button() == Qt.LeftButton:
                self._nav_split_press = (ev.pos(), list(self.nav_splitter.sizes()), True)
            elif et in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
                press = getattr(self, "_nav_split_press", None)
                self._nav_split_press = None
                if press is not None and ev.button() == Qt.LeftButton:
                    press_pos, press_sizes, was_dbl = press
                    moved = (ev.pos() - press_pos).manhattanLength()
                    if moved < 4 and not was_dbl:
                        # Bare click: keep the pre-click widths, then toggle.
                        self.nav_splitter.setSizes(press_sizes)
                        self.btn_nav_toggle.setChecked(not self._nav_collapsed)
            return False
        return super().eventFilter(obj, ev)

    def _switch_page(self, key: str):
        if key not in self.page_order:
            return
        if self.stack.currentIndex() == self.page_order.get("notes") and key != "notes" and not self._flush_note_edits():
            return
        previous = self.stack.currentIndex()
        self.stack.setCurrentIndex(self.page_order[key])
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        # Pause the embedded site preview when leaving the Sites tab so it
        # stops consuming CPU / network in the background; reload the cached
        # URL when returning so the user sees the same site instantly.
        self._update_site_preview_activity(key == "sites")
        # Refresh the review queue when entering the Review page.
        if key == "review" and getattr(self, "lbl_review_stats", None) is not None:
            self._refresh_review()
        # The neural graph repaints at 20 FPS; stop the timer when the Notes
        # page is hidden (v6.4 kept animating behind every other page).
        if hasattr(self, "neural_graph") and hasattr(self, "chk_neural_graph"):
            self.neural_graph.set_animation_running(key == "notes" and self.chk_neural_graph.isChecked())
        if previous != self.stack.currentIndex() and key != "sites":  # #[c] keep WebEngine preview out of QWidget compositing.
            theme.animate_entrance(self.stack.currentWidget())

    def refresh_all(self):
        now = time.time()
        if hasattr(self, "_last_refresh") and (now - self._last_refresh) < 2.0:
            return
        self._last_refresh = now
        self._refresh_overview()
        self._refresh_notes()
        self._refresh_tasks()
        self._refresh_calendar()
        self._refresh_boards()
        self._refresh_files()
        self._refresh_sites()
        if getattr(self, "lbl_review_stats", None) is not None:
            self._refresh_review()
            # Nav badge: due-count on the Review button so the queue is
            # visible without opening the page.
            from litebrowser.services import flashcard_service

            due = flashcard_service.stats(self.base_dir)["due"]
            btn = self.nav_buttons.get("review")
            if btn is not None:
                base_label = "Review"
                btn.setText("⇄" if self._nav_collapsed or self.width() < 820 else f"⇄  Review ({due})" if due else f"⇄  {base_label}")
                btn.setToolTip(f"Review · {due} cards due")

    def _build_overview_page(self):
        import time as _time

        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(22, 18, 22, 18)
        l.setSpacing(16)
        l.addWidget(
            components.masthead(
                _time.strftime("Personal · %A %d %B"),
                "Your day, at a glance",
                "The open loop in one place: what is active, what is coming, and how the week is going.",
            )
        )

        stats_row = QHBoxLayout()
        stat_specs = (
            ("lbl_overview_tasks", "pending tasks"),
            ("lbl_overview_events", "upcoming events"),
            ("lbl_overview_boards", "boards"),
            ("lbl_overview_notes", "notes"),
            ("lbl_overview_focus", "min focus today"),
        )
        tiles = []
        for attr, label in stat_specs:
            tile = components.stat_tile("0", label)
            tiles.append(tile)
            setattr(self, attr, tile._value)
        stats_row.addWidget(components.stat_row(tiles), 1)
        l.addLayout(stats_row)

        # Focus streak heatmap (12 weeks, Duolingo-style) — visible motivation.
        self.focus_heatmap = FocusHeatmap()
        l.addWidget(components.section_header("Focus history", "Minutes poured across the last twelve weeks", kicker="Rhythm"))
        heatmap_card = QFrame()
        heatmap_card.setObjectName("SectionCard")
        heatmap_layout = QVBoxLayout(heatmap_card)
        heatmap_layout.setContentsMargins(14, 12, 14, 12)
        heatmap_layout.addWidget(self.focus_heatmap)
        l.addWidget(heatmap_card)

        body = QHBoxLayout()
        body.setSpacing(24)
        self.overview_focus_list = QListWidget()
        self.overview_focus_list.setObjectName("CafeList")
        self.overview_timeline_list = QListWidget()
        self.overview_timeline_list.setObjectName("CafeList")
        focus_col = QWidget()
        focus_layout = QVBoxLayout(focus_col)
        focus_layout.setContentsMargins(0, 0, 0, 0)
        focus_layout.setSpacing(4)
        focus_layout.addWidget(components.section_header("In hand", "Active tasks", kicker="Focus"))
        focus_layout.addWidget(components.rule())
        focus_layout.addWidget(self.overview_focus_list, 1)
        upcoming_col = QWidget()
        upcoming_layout = QVBoxLayout(upcoming_col)
        upcoming_layout.setContentsMargins(0, 0, 0, 0)
        upcoming_layout.setSpacing(4)
        upcoming_layout.addWidget(components.section_header("Ahead", "Calendar events", kicker="Upcoming"))
        upcoming_layout.addWidget(components.rule())
        upcoming_layout.addWidget(self.overview_timeline_list, 1)
        body.addWidget(focus_col, 1)
        body.addWidget(upcoming_col, 1)
        l.addLayout(body, 1)
        return w

    def _wrap_list_card(self, title_text: str, subtitle: str, list_widget: QListWidget):
        card = QFrame()
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(components.section_header(title_text, subtitle))
        layout.addWidget(list_widget, 1)
        return card

    def _refresh_overview(self):
        snapshot = life_service.get_dashboard_snapshot(self.base_dir)
        self.lbl_overview_tasks.setText(f"{snapshot['tasks_pending']}")
        self.lbl_overview_events.setText(f"{len(snapshot['events_upcoming'])}")
        self.lbl_overview_boards.setText(f"{snapshot['boards_total']}")
        self.lbl_overview_notes.setText(f"{len(personal_service.list_notes(self.base_dir))}")
        minutes = focus_service.today_focus_seconds(self.base_dir) // 60
        self.lbl_overview_focus.setText(f"{minutes}")
        if getattr(self, "focus_heatmap", None) is not None:
            self.focus_heatmap.refresh(self.base_dir)
        self.overview_focus_list.clear()
        for item in [task for task in life_service.load_tasks(self.base_dir) if not task.get("completed")] [:8]:
            self.overview_focus_list.addItem(f"{item.get('title', '')} · {item.get('bucket', '')}")
        if self.overview_focus_list.count() == 0:
            self.overview_focus_list.addItem(components.hint_list_item("No active tasks", "○"))
        self.overview_timeline_list.clear()
        for event in life_service.load_events(self.base_dir)[:8]:
            self.overview_timeline_list.addItem(f"{event.get('title', '')} · {_format_ts(int(event.get('starts_at', 0) or 0))}")
        if self.overview_timeline_list.count() == 0:
            self.overview_timeline_list.addItem(components.hint_list_item("No calendar events yet", "○"))

    def _import_ics(self):
        from litebrowser.services import ics_service

        path, _ = QFileDialog.getOpenFileName(self, "Import ICS calendar", "", "iCalendar (*.ics);;All files (*)")
        if not path:
            return
        try:
            count = ics_service.import_ics_file(self.base_dir, path)
        except Exception as exc:
            QMessageBox.warning(self, "Calendar", f"Import failed: {exc}")
            return
        self._refresh_calendar()
        self._refresh_overview()
        QMessageBox.information(self, "Calendar", f"Imported {count} events from the .ics file.")

    def _export_ics(self):
        from litebrowser.services import ics_service

        default = os.path.join(self.base_dir, "mei-calendar-" + time.strftime("%Y%m%d") + ".ics")
        path, _ = QFileDialog.getSaveFileName(self, "Export calendar", default, "iCalendar (*.ics)")
        if not path:
            return
        try:
            count = ics_service.export_ics_file(self.base_dir, path)
        except Exception as exc:
            QMessageBox.warning(self, "Calendar", f"Export failed: {exc}")
            return
        QMessageBox.information(self, "Calendar", f"Exported {count} events to:\n{path}")

    def _build_notes_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(22, 18, 22, 18)
        l.setSpacing(10)
        l.addWidget(components.page_header("Notes", "A quiet page for reading, writing and linking ideas", kicker="SafeVault"))
        top_row = QHBoxLayout()
        self.ed_note_search = QLineEdit()
        self.ed_note_search.setPlaceholderText("Search notes in SafeVault…")
        self.ed_note_search.setAccessibleName("Search notes")
        self.ed_note_search.setClearButtonEnabled(True)
        # This resets the *list* (category filter and selection), so it sits with
        # the list it resets instead of floating above both columns.
        self.btn_note_back = components.chip("All notes", checkable=False)
        self.btn_note_back.setToolTip("Clear the category filter and show every note")
        self.btn_note_back.setAccessibleName("Show all notes")
        self.cmb_note_category = QComboBox()
        self.cmb_note_category.setEditable(True)
        self.cmb_note_category.setMinimumWidth(130)
        self.cmb_note_font = QComboBox()
        # Pixel sizes, matching how the editor font is applied (see
        # _apply_note_font_size): the old list was point sizes while the control
        # was labelled as a size in the editor's own pixels.
        self.cmb_note_font.addItems([str(size) for size in NOTE_FONT_SIZES])
        self.btn_new_note = primary_button("New note", "Create a note in the category named in the filter")
        self.btn_delete_note = QPushButton("Delete")
        self.btn_save_note = QPushButton("Save")
        self.btn_save_note.setObjectName("NoteSave")
        # Set explicitly so the themed rule is deterministic rather than
        # depending on a property that no one has written yet.
        self.btn_save_note.setProperty("dirty", False)
        self.btn_note_ai = ghost_button("Ask AI", "Ask the assistant about this note")
        self.btn_note_flash = ghost_button(
            "⇄ Make flashcard",
            "Create a flashcard from the selected text (front = selection, back = prompt)",
        )
        self.chk_neural_graph = QCheckBox("Show neural graph")
        self.chk_neural_graph.setChecked(prefs.get_show_neural_notes_graph(self.base_dir))
        self.chk_neural_graph.toggled.connect(self._on_neural_graph_toggled)
        top_row.addWidget(self.ed_note_search, 1)
        top_row.addWidget(self.cmb_note_category)
        self.cmb_note_category.setAccessibleName("Filter notes by category")
        self.cmb_note_category.setMaximumWidth(160)
        self.ed_note_search.setMinimumWidth(0)
        top_row.addWidget(self.btn_new_note)
        l.addLayout(top_row)
        # Save, New note and the note title stay outside this row. Everything
        # occasional (flashcards, AI, delete, text size, the graph) folds into
        # one collapsible Tools row inside the writing column.
        self.lbl_note_save = QLabel("Saved locally")
        self.lbl_note_save.setObjectName("NoteSaveState")
        self.lbl_note_save.setAccessibleName("Note save status")
        self.lbl_note_save.setProperty("state", "saved")
        self.btn_note_tools = components.chip("Tools ▾", checkable=True, checked=False)
        self.btn_note_tools.setToolTip("Flashcards, AI, delete, text size and the neural graph")
        self.btn_note_tools.toggled.connect(self._toggle_note_tools)
        self._note_tools = QWidget()
        tools = QGridLayout(self._note_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(6)
        tools.addWidget(self.btn_note_ai, 0, 0)
        tools.addWidget(self.btn_note_flash, 0, 1)
        tools.addWidget(self.btn_delete_note, 0, 2)
        self.btn_delete_note.setObjectName("DangerButton")
        font_caption = QLabel("Text size")
        font_caption.setObjectName("MutedLabel")
        tools.addWidget(font_caption, 1, 0)
        tools.addWidget(self.cmb_note_font, 1, 1)
        self.cmb_note_font.setAccessibleName("Note text size")
        self.cmb_note_font.setToolTip("Writing size for the note editor")
        self.cmb_note_font.setCurrentText(str(NOTE_FONT_DEFAULT))
        tools.addWidget(self.chk_neural_graph, 1, 2)
        self._note_tools.hide()
        # Transient messages get their own line at the foot of the page, so a
        # move or a wiki-link open never rewrites the note's title (see _flash).
        self.lbl_note_status = QLabel("")
        self.lbl_note_status.setObjectName("NoteStatus")
        self.lbl_note_status.setAccessibleName("Note status message")
        self.lbl_note_status.setWordWrap(True)
        self.lbl_note_status.hide()

        # Find-within-note toolbar. It lives inside the writing column, not
        # above the whole page: two full-width search fields stacked on top of
        # each other made it unclear which one searched what.
        self._find_bar = QWidget()
        self._find_bar.setObjectName("NoteFindBar")
        find_row = QHBoxLayout(self._find_bar)
        find_row.setContentsMargins(0, 0, 0, 0)
        find_row.setSpacing(6)
        self.ed_note_find = QLineEdit()
        self.ed_note_find.setObjectName("NoteFind")
        self.ed_note_find.setPlaceholderText("Find in this note…")
        self.btn_find_prev = QPushButton("‹")
        self.btn_find_prev.setObjectName("FindStep")
        self.btn_find_prev.setToolTip("Previous match")
        self.btn_find_next = QPushButton("›")
        self.btn_find_next.setObjectName("FindStep")
        self.btn_find_next.setToolTip("Next match")
        self.lbl_find_count = QLabel("")
        self.lbl_find_count.setObjectName("MutedLabel")
        find_row.addWidget(self.ed_note_find, 1)
        find_row.addWidget(self.btn_find_prev)
        find_row.addWidget(self.btn_find_next)
        find_row.addWidget(self.lbl_find_count)

        split = QSplitter(Qt.Horizontal)
        left_pane = QWidget()
        left_pane.setObjectName("NoteListPane")
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        # The shelf names itself and says how much of the vault it is showing.
        self._notes_header = components.section_header("Notes", "No notes yet", action=self.btn_note_back)
        self._notes_header_subtitle = getattr(self._notes_header, "_subtitle", None)
        left_layout.addWidget(self._notes_header)
        self.notes_list = MeiNotesList(self)
        self.notes_list.setObjectName("CafeList")
        # A narrow shelf must elide its titles, not slice them mid-word.
        self.notes_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.notes_list.setTextElideMode(Qt.ElideRight)
        self.notes_list.setItemDelegate(NoteRowDelegate(self.notes_list))
        self.notes_list.setUniformItemSizes(True)
        self.notes_list.currentItemChanged.connect(self._load_selected_note)
        left_layout.addWidget(self.notes_list, 1)
        categories_hint = QLabel("Drag a note to a category to move it")
        categories_hint.setObjectName("MutedLabel")
        categories_hint.setWordWrap(True)
        left_layout.addWidget(categories_hint)
        self._categories_hint = categories_hint
        self.categories_list = CategoryDropList(self)
        self.categories_list.setObjectName("CafeList")
        self.categories_list.setMaximumHeight(150)
        left_layout.addWidget(self.categories_list)
        split.addWidget(left_pane)
        editor_wrap = QWidget()
        editor_wrap.setObjectName("NoteWritingColumn")
        self._writing_column = editor_wrap
        editor_wrap.installEventFilter(self)
        editor_layout = QVBoxLayout(editor_wrap)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        # Kept so the writing column's measure can be inset on a wide window.
        self._editor_layout = editor_layout
        self.neural_graph = NeuralGraphWidget()
        editor_layout.addWidget(self.neural_graph)
        # The open note's own header: which note this is, whether it is saved,
        # and the verbs that act on it — Save next to the text it saves.
        self._note_head = QWidget()
        self._note_head.setObjectName("NoteHead")
        head_row = QHBoxLayout(self._note_head)
        head_row.setContentsMargins(2, 0, 0, 0)
        head_row.setSpacing(8)
        self.lbl_note_title = QLabel("No note selected")
        self.lbl_note_title.setObjectName("NoteTitleLabel")
        self.lbl_note_title.setWordWrap(True)
        head_row.addWidget(self.lbl_note_title, 1)
        head_row.addWidget(self.lbl_note_save)
        head_row.addWidget(self.btn_save_note)
        head_row.addWidget(self.btn_note_tools)
        editor_layout.addWidget(self._note_head)
        editor_layout.addWidget(self._note_tools)
        editor_layout.addWidget(self._find_bar)
        self.lbl_note_image = QLabel()
        self.lbl_note_image.setAlignment(Qt.AlignCenter)
        self.lbl_note_image.hide()
        editor_layout.addWidget(self.lbl_note_image)
        self.btn_open_note_image = QPushButton("Open image")
        self.btn_open_note_image.setToolTip("Open the attached image at full size")
        self.btn_open_note_image.hide()
        editor_layout.addWidget(self.btn_open_note_image)
        # Nothing open: say so, and offer the one next step. A live editor with
        # no note behind it looked broken and quietly dropped what was typed.
        self._note_empty = QFrame()
        self._note_empty.setObjectName("EmptyState")
        empty_box = QVBoxLayout(self._note_empty)
        empty_box.setContentsMargins(24, 28, 24, 28)
        empty_box.setSpacing(8)
        empty_box.setAlignment(Qt.AlignCenter)
        empty_glyph = QLabel("✎")
        empty_glyph.setObjectName("EmptyGlyph")
        empty_glyph.setAlignment(Qt.AlignCenter)
        empty_box.addWidget(empty_glyph)
        self._note_empty_title = QLabel("Pick a note to start writing")
        self._note_empty_title.setObjectName("NoteEmptyTitle")
        self._note_empty_title.setAlignment(Qt.AlignCenter)
        self._note_empty_title.setWordWrap(True)
        empty_box.addWidget(self._note_empty_title)
        self._note_empty_hint = QLabel("")
        self._note_empty_hint.setObjectName("NoteEmptyHint")
        self._note_empty_hint.setAlignment(Qt.AlignCenter)
        self._note_empty_hint.setWordWrap(True)
        empty_box.addWidget(self._note_empty_hint)
        empty_actions = QHBoxLayout()
        empty_actions.setSpacing(8)
        empty_actions.addStretch(1)
        self.btn_empty_new = primary_button("New note", "Create a note in the category named in the filter")
        self.btn_empty_new.clicked.connect(self._create_note)
        empty_actions.addWidget(self.btn_empty_new)
        self.btn_empty_search = ghost_button("Search notes…", "Jump to the note search field")
        self.btn_empty_search.clicked.connect(self._focus_note_search)
        empty_actions.addWidget(self.btn_empty_search)
        empty_actions.addStretch(1)
        empty_box.addLayout(empty_actions)
        self._note_empty.hide()
        editor_layout.addWidget(self._note_empty, 1)
        self.note_editor = QPlainTextEdit()
        self.note_editor.setObjectName("NoteEditor")
        self.note_editor.setAccessibleName("Note content")
        self.note_editor.setFont(components._font(NOTE_FONT_DEFAULT, components.WEIGHT_NORMAL))
        self.note_editor.setPlaceholderText("Longform notes, clipped notes, study notes...\n\nTip: type [[ to link another note — Obsidian-style, with autocomplete.")
        editor_layout.addWidget(self.note_editor, 1)
        # Wiki-links: accent-highlight [[targets]] + completion from note titles.
        self._wiki_highlighter = WikiLinkHighlighter(self.note_editor.document(), lambda: theme.palette())
        self._wiki_completer = QCompleter(self)
        try:
            self._wiki_completer.setCaseSensitivity(Qt.CaseInsensitive)
        except AttributeError:
            self._wiki_completer.setCaseSensitivity(Qt.CaseInsensitive if hasattr(Qt, "CaseInsensitive") else False)
        self._wiki_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion if hasattr(QCompleter, "CompletionMode") else QCompleter.PopupCompletion
        )
        self._wiki_completer.activated.connect(self._insert_wiki_link)
        self._wiki_start = -1
        self.lbl_note_stats = QLabel("0 words · 0 characters")
        self.lbl_note_stats.setObjectName("MutedLabel")
        editor_layout.addWidget(self.lbl_note_stats)
        self.lbl_backlinks = QLabel("")
        self.lbl_backlinks.setObjectName("MutedLabel")
        self.lbl_backlinks.setWordWrap(True)
        self.lbl_backlinks.setTextFormat(Qt.RichText)
        self.lbl_backlinks.hide()
        editor_layout.addWidget(self.lbl_backlinks)
        # Entity links: note <-> planner item / card / page, stored once in
        # entity_links.json so both directions always agree.
        self.links_list = QListWidget()
        self.links_list.setObjectName("CafeList")
        self.links_list.setMaximumHeight(84)
        self.links_list.setToolTip("Links between this note and planner items, cards, or pages")
        self.links_list.hide()
        editor_layout.addWidget(self.links_list)
        links_row = QHBoxLayout()
        self.btn_note_link_add = QPushButton("🔗 Link…")
        self.btn_note_link_add.setToolTip("Link this note to a planner item")
        self.btn_note_link_remove = QPushButton("Unlink")
        self.btn_note_link_remove.setToolTip("Remove the selected link")
        links_row.addWidget(self.btn_note_link_add)
        links_row.addWidget(self.btn_note_link_remove)
        links_row.addStretch(1)
        editor_layout.addLayout(links_row)
        # Click a [[wiki-link]] in the editor (Ctrl+click safer than plain):
        self.note_editor.mousePressEvent = self._note_mouse_press  # type: ignore[assignment]
        split.addWidget(editor_wrap)
        self._notes_splitter = split
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([250, 800])
        split.splitterMoved.connect(lambda *_: self._apply_notes_measure())
        l.addWidget(split, 1)
        l.addWidget(self.lbl_note_status)

        self.ed_note_search.textChanged.connect(self._schedule_notes_refresh)
        self.btn_note_back.clicked.connect(self._back_to_all_notes)
        self.btn_open_note_image.clicked.connect(self._open_note_image)
        self.ed_note_find.textChanged.connect(self._find_in_note)
        self.btn_find_prev.clicked.connect(self._find_prev)
        self.btn_find_next.clicked.connect(self._find_next)
        self.cmb_note_category.currentTextChanged.connect(lambda _value: self._refresh_notes())
        self.cmb_note_font.currentTextChanged.connect(self._apply_note_font_size)
        self.btn_new_note.clicked.connect(self._create_note)
        self.btn_delete_note.clicked.connect(self._delete_note)
        self.btn_save_note.clicked.connect(self._save_note)
        self.btn_note_ai.clicked.connect(self._ask_ai_about_note)
        self.btn_note_flash.clicked.connect(self._make_flashcard_from_selection)
        self.btn_note_link_add.clicked.connect(self._add_note_link)
        self.btn_note_link_remove.clicked.connect(self._remove_note_link)
        self.links_list.itemDoubleClicked.connect(self._open_entity_link)
        self.note_editor.textChanged.connect(self._on_note_text_changed)
        self._note_idle_timer = QTimer(self)
        self._note_idle_timer.setSingleShot(True)
        self._note_idle_timer.setInterval(250)
        self._note_idle_timer.timeout.connect(self._on_note_edit_idle)
        self._notes_search_timer = QTimer(self)
        self._notes_search_timer.setSingleShot(True)
        self._notes_search_timer.setInterval(250)
        self._notes_search_timer.timeout.connect(self._refresh_notes)
        if not self.embedded:
            self.btn_note_ai.hide()
        self._apply_neural_graph_visibility()
        # Nothing is open yet on a cold start: the column states that instead of
        # presenting a live editor with no note behind it.
        self._apply_note_font_size()
        self._set_writing_active(False)
        return w

    def _schedule_notes_refresh(self):
        """Debounce list rebuilds so typing in the search box stays smooth."""
        self._notes_search_timer.start()

    def _on_neural_graph_toggled(self, checked: bool):
        prefs.set_show_neural_notes_graph(self.base_dir, checked)
        self._apply_neural_graph_visibility()
        if checked and hasattr(self, "notes_list"):
            all_notes = personal_service.list_notes(self.base_dir, "")
            self.neural_graph.set_notes(all_notes[:NEURAL_GRAPH_MAX_NOTES], total_note_count=len(all_notes))

    def _apply_neural_graph_visibility(self):
        if not hasattr(self, "neural_graph") or not hasattr(self, "chk_neural_graph"):
            return
        on = self.chk_neural_graph.isChecked()
        self.neural_graph.setVisible(on)
        if on:
            self.neural_graph.setMinimumHeight(120)
            self.neural_graph.setMaximumHeight(150)
            self.neural_graph.set_animation_running(True)
        else:
            self.neural_graph.setMinimumHeight(0)
            self.neural_graph.setMaximumHeight(0)
            self.neural_graph.set_animation_running(False)

    def _apply_note_font_size(self):
        """The writing size, applied where Qt actually reads it.

        The editor is styled by the window stylesheet, which re-applies its own
        font at every polish — the old ``setPointSize`` on the widget font was
        therefore a no-op (and mixed point sizes into a combo labelled in
        pixels). The size is a themed stylesheet rule selected by a dynamic
        property; the document font is then synced to the polished widget font
        so layout and cursor agree.
        """
        try:
            size = int(self.cmb_note_font.currentText())
        except (TypeError, ValueError):
            size = NOTE_FONT_DEFAULT
        size = min(max(size, min(NOTE_FONT_SIZES)), max(NOTE_FONT_SIZES))
        self.note_editor.setProperty("textSize", str(size))
        style = self.note_editor.style()
        if style is not None:
            style.unpolish(self.note_editor)
            style.polish(self.note_editor)
        font = QFont(self.note_editor.font())
        if font.pixelSize() > 0:
            document = self.note_editor.document()
            if document is not None:
                document.setDefaultFont(font)
        self.note_editor.update()

    def _toggle_note_tools(self, checked: bool):
        self._note_tools.setVisible(bool(checked))
        self.btn_note_tools.setText("Tools ▴" if checked else "Tools ▾")
        self.btn_note_tools.setToolTip(
            "Hide the note tools" if checked else "Flashcards, AI, delete, text size and the neural graph"
        )

    def _focus_note_search(self):
        self.ed_note_search.setFocus()
        self.ed_note_search.selectAll()

    def _apply_notes_measure(self):
        """Keep prose lines readable on a wide window.

        The writing column is inset until the editor measures about 760px; a
        narrow window and the stacked (vertical) layout keep the full width.
        Only the column's margins change, so both splitter handles stay
        draggable and no widget is reparented.
        """
        layout = getattr(self, "_editor_layout", None)
        split = getattr(self, "_notes_splitter", None)
        if layout is None or split is None:
            return
        inset = 0
        if split.orientation() == Qt.Horizontal:
            column = getattr(self, "_writing_column", None)
            width = column.width() if column is not None else 0
            if width <= 0:
                sizes = split.sizes()
                width = sizes[1] if len(sizes) > 1 else 0
            if width > NOTE_MEASURE_MAX + 120:
                inset = min(170, (width - NOTE_MEASURE_MAX) // 2)
        margins = layout.contentsMargins()
        if margins.left() != inset:
            layout.setContentsMargins(inset, margins.top(), inset, margins.bottom())

    def _set_save_state(self, state: str, text: str = ""):
        """One place for the save line and the Save button's weight.

        ``dirty`` gives Save the accent fill so an unsaved note is visible at a
        glance; ``saved`` leaves it quiet next to a muted line; ``error``
        (a conflict or a failed write) colours the line instead of adding a
        badge for a state that should be rare.
        """
        label = getattr(self, "lbl_note_save", None)
        if label is not None:
            if text:
                label.setText(text)
            if label.property("state") != state:
                label.setProperty("state", state)
                _repolish(label)
        button = getattr(self, "btn_save_note", None)
        if button is not None:
            on = state == "dirty"
            if bool(button.property("dirty")) != on:
                button.setProperty("dirty", on)
                _repolish(button)
            button.setToolTip(
                "Save this note now — it is currently unsaved"
                if on
                else "Write this note to SafeVault (saves happen automatically while you type)"
            )

    def _on_note_text_changed(self):
        self._update_note_stats()
        if self._suppress_note_dirty:
            return
        if not self.current_note_id:
            return
        self._note_dirty = True
        self._set_save_state("dirty", "Unsaved changes…")
        self._note_idle_timer.start()
        self._maybe_wiki_autocomplete()

    def _maybe_wiki_autocomplete(self):
        """When the user just typed '[[', offer note titles as completions."""
        editor = self.note_editor
        pos = editor.textCursor().position()
        text = editor.toPlainText()
        start = text.rfind("[[", 0, pos)
        if start < 0:
            return
        between = text[start + 2:pos]
        if "]]" in between or "\n" in between or len(between) > 80:
            return
        titles = sorted({n["title"] for n in personal_service.list_notes(self.base_dir)})
        model = self._wiki_completer.model()

        if model is None or not isinstance(model, QStringListModel):
            model = QStringListModel(titles, self._wiki_completer)
            self._wiki_completer.setModel(model)
        else:
            model.setStringList(titles)
        self._wiki_start = start
        self._wiki_completer.setCompletionPrefix(between)
        if between and self._wiki_completer.currentRow() < 0:
            return  # no candidates; stay quiet instead of popping an empty box
        rect = editor.cursorRect()
        self._wiki_completer.complete(rect.adjusted(0, 18, 140, 18))

    def _insert_wiki_link(self, choice: str):
        editor = self.note_editor
        pos = editor.textCursor().position()
        start = getattr(self, "_wiki_start", -1)
        if start < 0 or start > pos:
            return
        cursor = editor.textCursor()
        cursor.setPosition(start, QTextCursor.MoveAnchor)
        cursor.setPosition(pos, QTextCursor.KeepAnchor)
        cursor.insertText(f"[[{choice}]]")
        self._wiki_start = -1

    def _on_note_edit_idle(self):
        """Autosave debounced: persist edits 250 ms after typing stops."""
        if not self._note_dirty or not self.current_note_id:
            return
        self._flush_note_edits()
        # Find highlights were computed against the old text; offsets are now
        # stale (v6.4 jumped to wrong spans). Recompute on the edited content.
        self._find_in_note()

    def _update_note_stats(self):
        if not hasattr(self, "lbl_note_stats"):
            return
        text = self.note_editor.toPlainText()
        # Avoid building a full word list on every keystroke for large notes.
        word_count = sum(1 for _ in re.finditer(r"\S+", text))
        self.lbl_note_stats.setText("%d words · %d characters" % (word_count, len(text)))

    def _refresh_notes(self):
        query = self.ed_note_search.text().strip() if hasattr(self, "ed_note_search") else ""
        selected_category = self.cmb_note_category.currentText().strip() if hasattr(self, "cmb_note_category") else ""
        self._refresh_note_categories(keep_value=selected_category)
        # Flush pending edits BEFORE touching the list: list.clear() fires
        # currentItemChanged(None) which used to blank the editor and wipe
        # unsaved edits on every search keystroke (v6.4 data-loss bug).
        self._on_note_edit_idle()
        keep_selection = self.current_note_id
        self._suppress_note_dirty = True
        try:
            self.notes_list.clear()
        finally:
            self._suppress_note_dirty = False
        notes = []
        for note in personal_service.list_notes(self.base_dir, query):
            if selected_category and selected_category.lower() != "all" and note.get("category", "").lower() != selected_category.lower():
                continue
            notes.append(note)
        total_notes = len(personal_service.list_notes(self.base_dir, ""))
        self._update_notes_header(len(notes), total_notes)
        # The empty column's wording follows the vault: "no notes yet" becomes
        # "pick a note" as soon as the first note exists.
        if not self.current_note_id:
            self._set_note_empty(bool(total_notes))
        # Honour the user's drag-and-drop arrangement; unknown ids keep their
        # natural (most-recent-first) order at the end.
        order = prefs.get_note_order(self.base_dir)
        if order:
            rank = {nid: idx for idx, nid in enumerate(order)}
            notes.sort(key=lambda n: rank.get(n["id"], len(order)))
        restored = None
        for note in notes:
            item = QListWidgetItem(note["title"] or "(untitled)")
            item.setData(NOTE_ID_ROLE, note["id"])
            # The delegate paints these two lines; the tooltip carries the full
            # title (long ones elide) and the note's own opening words.
            item.setData(NOTE_ROW_ROLE, _note_row_payload(note))
            item.setToolTip(self._note_row_tooltip(note))
            self.notes_list.addItem(item)
            if keep_selection and note["id"] == keep_selection:
                restored = item
        # Keep the note that was open selected across filter changes; with
        # signals blocked the editor is left untouched (no wipe, no scroll jump).
        if restored is not None:
            self.notes_list.blockSignals(True)
            try:
                self.notes_list.setCurrentItem(restored)
            finally:
                self.notes_list.blockSignals(False)
            self.current_note_id = keep_selection
        if hasattr(self, "neural_graph") and getattr(self, "chk_neural_graph", None) and self.chk_neural_graph.isChecked():
            all_notes = personal_service.list_notes(self.base_dir, "")
            self.neural_graph.set_notes(all_notes[:NEURAL_GRAPH_MAX_NOTES], total_note_count=len(all_notes))
        # Empty state: a muted hint row (disabled, unselectable) instead of a
        # blank list when the search/filter matches nothing.
        if self.notes_list.count() == 0:
            hint = components.hint_list_item("No notes match — try another search, or press New note")
            hint.setFlags(Qt.NoItemFlags)
            self.notes_list.addItem(hint)
        if hasattr(self, "_notes_fs_watcher"):
            now = time.time()
            if not hasattr(self, "_last_watcher_sync") or (now - self._last_watcher_sync) > 5.0:
                self._last_watcher_sync = now
                self._sync_notes_watcher_paths()

    def _update_notes_header(self, shown: int, total: int):
        """Say how much of the vault the shelf is showing."""
        label = getattr(self, "_notes_header_subtitle", None)
        if label is None:
            return
        if total == 0:
            text = "No notes yet"
        elif shown == total:
            text = f"{total} note" if total == 1 else f"{total} notes"
        else:
            text = f"{shown} of {total} notes"
        if label.text() != text:
            label.setText(text)

    def _note_row_tooltip(self, note: dict) -> str:
        payload = _note_row_payload(note)
        head = payload["title"]
        meta = payload["category"] + (f"  ·  {payload['meta']}" if payload["meta"] else "")
        preview = _note_preview(note)
        parts = [head, meta]
        if preview:
            parts.append("")
            parts.append(preview)
        return "\n".join(parts)

    def _refresh_note_categories(self, keep_value: str = ""):
        if not hasattr(self, "cmb_note_category"):
            return
        current = keep_value or self.cmb_note_category.currentText().strip() or "All"
        self.cmb_note_category.blockSignals(True)
        self.cmb_note_category.clear()
        self.cmb_note_category.addItem("All")
        for category in personal_service.list_note_categories(self.base_dir):
            self.cmb_note_category.addItem(category)
        idx = self.cmb_note_category.findText(current)
        if idx >= 0:
            self.cmb_note_category.setCurrentIndex(idx)
        else:
            self.cmb_note_category.setEditText(current)
        self.cmb_note_category.blockSignals(False)
        # Refresh the drag-and-drop category target list.
        if hasattr(self, "categories_list"):
            self.categories_list.blockSignals(True)
            self.categories_list.clear()
            for category in personal_service.list_note_categories(self.base_dir):
                drop_item = QListWidgetItem(category)
                drop_item.setData(Qt.UserRole, category)
                self.categories_list.addItem(drop_item)
            self.categories_list.blockSignals(False)

    def _create_note(self):
        title, ok = QInputDialog.getText(self, "Create note", "Note title:")
        if not ok or not (title or "").strip():
            return
        category = (self.cmb_note_category.currentText().strip() or "General")
        if category.lower() == "all":
            category = "General"
        note = personal_service.create_note(self.base_dir, title.strip(), "# " + title.strip() + "\n\n", category=category)
        # New notes appear at the top of the manual order.
        order = [nid for nid in prefs.get_note_order(self.base_dir) if nid != note["id"]]
        prefs.set_note_order(self.base_dir, [note["id"]] + order)
        self._refresh_notes()
        self.select_note(note["id"])

    def select_note(self, note_id: str):
        if not note_id or not self._flush_note_edits():
            return
        self._switch_page("notes")
        if not any(self.notes_list.item(i).data(Qt.UserRole) == note_id for i in range(self.notes_list.count())):
            # Deep links from Home/Library must work even when a prior filter
            # hid the target. Keep the editor's text safe before clearing it.
            self.ed_note_search.clear()
            self.cmb_note_category.setCurrentIndex(0)
            self._notes_search_timer.stop()
            self._refresh_notes()
        for index in range(self.notes_list.count()):
            item = self.notes_list.item(index)
            if item.data(Qt.UserRole) == note_id:
                if self.notes_list.currentItem() is item:
                    return  # already selected; re-selecting would reset the editor
                self.notes_list.setCurrentItem(item)
                self._switch_page("notes")
                break

    def _load_selected_note(self, current, _previous):
        if self._suppress_note_dirty:
            return
        if not self._flush_note_edits():
            self.notes_list.blockSignals(True)
            self.notes_list.setCurrentItem(_previous)
            self.notes_list.blockSignals(False)
            return
        if not current:
            # Mid-refresh the list clear is spurious: _refresh_notes re-selects
            # the open note afterwards, so keep the editor untouched here.
            if self._suppress_note_dirty:
                return
            self._show_no_note_state()
            return
        note = personal_service.read_note(self.base_dir, current.data(Qt.UserRole))
        if not note:
            return
        self.current_note_id = note["id"]
        self.current_note_category = note.get("category") or "General"
        self._note_title = note["title"]
        self._note_loaded_content = note["content"]
        self._note_dirty = False
        self._set_writing_active(True)
        self._suppress_note_dirty = True
        try:
            prev_content = self.note_editor.toPlainText()
            if note["content"] != prev_content:
                self.note_editor.setPlainText(note["content"])
                self._render_note_attachments(note["content"])
        finally:
            self._suppress_note_dirty = False
        # The category combo is a *filter* only. Do not change it here, or the
        # note's own category would leak into the filter and hide every other note.
        self.lbl_note_title.setText(f"{note['title']}  ·  {self.current_note_category}")
        self._set_save_state("saved", "Saved locally")
        self._refresh_backlinks(note)
        self._find_in_note()

    def _show_no_note_state(self):
        """Nothing is open: an intentional empty column, never a dead editor.

        The editor used to stay live with no note behind it, so anything typed
        there was dropped on the next selection without a word. Disabling the
        writing surface while nothing is open (and explaining it) is the honest
        version of the same screen.
        """
        self.current_note_id = None
        self.current_note_category = "General"
        self._note_title = ""
        self._note_dirty = False
        self.lbl_note_title.setText("No note selected")
        self._suppress_note_dirty = True
        try:
            self.note_editor.setPlainText("")
        finally:
            self._suppress_note_dirty = False
        self._clear_note_attachments()
        self._find_in_note()
        self._set_writing_active(False)

    def _set_writing_active(self, active: bool):
        """Enable the writing surface only while a note is behind it.

        A read-only editor keeps selection, copy and find usable, and stops the
        old failure mode where text typed with nothing open disappeared on the
        next selection without a word. The verbs that need an open note go with
        it, and the column explains the state instead of sitting blank.
        """
        active = bool(active)
        self.note_editor.setReadOnly(not active)
        self.btn_save_note.setEnabled(active)
        self.ed_note_find.setEnabled(active)
        self.btn_find_prev.setEnabled(active)
        self.btn_find_next.setEnabled(active)
        self.lbl_note_save.setVisible(active)
        self.btn_save_note.setVisible(active)
        self.btn_note_tools.setVisible(active)
        if not active:
            self.btn_note_tools.setChecked(False)
            self._note_tools.hide()
            self._set_note_empty()
        self._find_bar.setVisible(active)
        self.note_editor.setVisible(active)
        self._note_empty.setVisible(not active)

    def _set_note_empty(self, has_notes: bool | None = None):
        """Name the empty column honestly: no vault yet, or nothing selected."""
        if not hasattr(self, "_note_empty_title"):
            return
        if has_notes is None:
            try:
                has_notes = bool(personal_service.list_notes(self.base_dir, ""))
            except OSError:
                has_notes = True
        if has_notes:
            self._note_empty_title.setText("Pick a note to start writing")
            self._note_empty_hint.setText(
                "Search or filter on the left. Everything typed here saves to SafeVault automatically, "
                "and [[double brackets]] link one note to another."
            )
            self.btn_empty_search.show()
        else:
            self._note_empty_title.setText("Your vault is empty")
            self._note_empty_hint.setText(
                "Notes stay on this machine as markdown files under SafeVault. "
                "Start with a title — you can organise and link them as the shelf fills up."
            )
            self.btn_empty_search.hide()

    def _refresh_backlinks(self, note):
        """'Linked mentions' — every note whose content references this one."""
        if not hasattr(self, "lbl_backlinks"):
            return
        target = note.get("title", "")
        if not target:
            self.lbl_backlinks.hide()
            return
        needle = f"[[{target}]]"
        links = []
        for other in personal_service.list_notes(self.base_dir):
            if other["id"] == note["id"]:
                continue
            if needle in (other.get("content") or ""):
                links.append(other)
        if links:
            names = ", ".join(other["title"] for other in links[:6])
            more = f" (+{len(links) - 6})" if len(links) > 6 else ""
            self.lbl_backlinks.setText(f"🔗 Linked from: {names}{more}")
            self.lbl_backlinks.setToolTip("\n".join(other["title"] for other in links))
            self.lbl_backlinks.show()
        else:
            self.lbl_backlinks.hide()
        self._refresh_entity_links()

    def _link_title(self, entity_type: str, entity_id: str) -> str:
        """Human title for one side of an entity link."""
        if entity_type == "note":
            for note in personal_service.list_notes(self.base_dir):
                if note.get("id") == entity_id:
                    return note.get("title", "")
        elif entity_type == "planner_item":
            for item in personal_plan.load_plan(self.base_dir)["items"]:
                if item.get("id") == entity_id:
                    return item.get("title", "")
        elif entity_type == "planner_block":
            for block in personal_plan.load_plan(self.base_dir)["time_blocks"]:
                if block.get("id") == entity_id:
                    return block.get("title", "")
        elif entity_type == "flashcard":
            from litebrowser.services import flashcard_service

            for card in flashcard_service.load_cards(self.base_dir):
                if card.get("id") == entity_id:
                    return card.get("front", "")
        return f"{entity_type} · {entity_id[:8]}"

    def _refresh_entity_links(self):
        if not hasattr(self, "links_list"):
            return
        self.links_list.clear()
        if not self.current_note_id:
            self.links_list.hide()
            return
        related = link_service.links_for(self.base_dir, "note", self.current_note_id)
        entries = [(link, link["to_type"], link["to_id"]) for link in related["outgoing"]]
        entries += [(link, link["from_type"], link["from_id"]) for link in related["incoming"]]
        for link, entity_type, entity_id in entries:
            row = QListWidgetItem(f"🔗 {self._link_title(entity_type, entity_id)} · {entity_type}")
            row.setData(
                Qt.UserRole,
                {"link_id": link.get("id", ""), "kind": entity_type, "id": entity_id},
            )
            row.setToolTip("Double-click to open; select and choose Unlink to remove")
            self.links_list.addItem(row)
        self.links_list.setVisible(self.links_list.count() > 0)

    def _add_note_link(self):
        """Link the open note to a planner item (the study side of the graph)."""
        if not self.current_note_id:
            QMessageBox.information(self, "Links", "Open a note first.")
            return
        plan = personal_plan.load_plan(self.base_dir)
        items = plan["items"]
        if not items:
            QMessageBox.information(
                self, "Links", "No planner items yet — add one on the Weekly Plan page."
            )
            return
        course_names = {
            course.get("id", ""): course.get("name", "") for course in plan["courses"]
        }
        labels = []
        for item in items:
            course = course_names.get(item.get("course_id", ""), "")
            labels.append(item.get("title", "") + (f" · {course}" if course else ""))
        choice, ok = QInputDialog.getItem(
            self, "Link note", "Link this note to a planner item", labels, 0, False
        )
        if not ok:
            return
        target = items[labels.index(choice)]
        link_service.add_link(
            self.base_dir, "note", self.current_note_id, "planner_item", target.get("id", "")
        )
        self._refresh_entity_links()

    def _remove_note_link(self):
        row = self.links_list.currentItem() if hasattr(self, "links_list") else None
        data = row.data(Qt.UserRole) if row is not None else {}
        if not data:
            QMessageBox.information(self, "Links", "Select a link to remove.")
            return
        link_service.remove_link(self.base_dir, data.get("link_id", ""))
        self._refresh_entity_links()

    def _open_entity_link(self, row: QListWidgetItem):
        data = row.data(Qt.UserRole) or {}
        kind = data.get("kind", "")
        entity_id = data.get("id", "")
        if kind == "note":
            self.select_note(entity_id)
        elif kind == "planner_item":
            self.open_plan_item(entity_id)
        elif kind == "flashcard":
            self.open_flashcard(entity_id)

    def _note_mouse_press(self, event):
        """Ctrl+click on a [[wiki-link]] opens that note (creates it if missing)."""

        if not (event.modifiers() & Qt.ControlModifier) or event.button() != Qt.LeftButton:
            QPlainTextEdit.mousePressEvent(self.note_editor, event)
            return
        cursor = self.note_editor.cursorForPosition(event.pos())
        pos = cursor.position()
        text = self.note_editor.toPlainText()
        match = None
        for m in WIKILINK_RE.finditer(text):
            if m.start() <= pos <= m.end():
                match = m
                break
        if match is None:
            QPlainTextEdit.mousePressEvent(self.note_editor, event)
            return
        target = match.group(1).strip()
        if not target:
            return
        self._flush_note_edits()
        for note in personal_service.list_notes(self.base_dir):
            if note["title"].lower() == target.lower():
                self.select_note(note["id"])
                self._flash(f"Opened [[{target}]]")
                return
        # Missing link → create a stub note (Obsidian behavior).
        note = personal_service.create_note(self.base_dir, target, f"# {target}\n\n", category=self.current_note_category or "General")
        self._refresh_notes()
        self.select_note(note["id"])
        self._flash(f"Created [[{target}]]")

    def _flush_note_edits(self) -> bool:
        if not getattr(self, "_note_dirty", False) or not self.current_note_id:
            return True
        self._note_idle_timer.stop()
        try:
            saved = personal_service.save_note(self.base_dir, self.current_note_id, self.note_editor.toPlainText(), expected_content=getattr(self, "_note_loaded_content", None))
        except personal_service.NoteConflictError:
            self._flash("Newer version found — your draft is retained. Press Save to keep both.")
            self._set_save_state("error", "Conflict · Save keeps both")
            return False
        except OSError:
            saved = False
        if not saved:
            # Keep both the dirty flag and the text; never navigate away from
            # the only copy of an edit after a failed autosave.
            self._flash("Not saved — check disk access and press Save to retry")
            self._set_save_state("error", "Not saved · retry Save")
            return False
        self._note_dirty = False
        self._note_loaded_content = self.note_editor.toPlainText()
        self._set_save_state("saved", "Saved locally")
        return True

    def _flash(self, message: str):
        """Show a transient status line in the writing column.

        Never the note title: ``_flash`` wrote into ``lbl_note_title`` before,
        so a drag-to-category or a wiki-link open replaced the open note's
        title with a status sentence and the next reader of that label (delete
        prompt, flashcard back, the AI context sent to the shell) treated the
        status text as the note's name.
        """
        label = getattr(self, "lbl_note_status", None)
        if label is None:
            return
        label.setText(message or "")
        # Hidden while empty so the foot of the page costs nothing until a
        # message actually exists.
        label.setVisible(bool(message))
        timer = getattr(self, "_note_status_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(6000)
            timer.timeout.connect(self._clear_note_status)
            self._note_status_timer = timer
        timer.start()

    def _clear_note_status(self):
        label = getattr(self, "lbl_note_status", None)
        if label is not None:
            label.clear()
            label.hide()

    def _back_to_all_notes(self):
        """Return to the full note list: clear any category filter + selection."""
        if not self._flush_note_edits():
            return
        self.cmb_note_category.blockSignals(True)
        self.cmb_note_category.setCurrentIndex(0)  # "All"
        self.cmb_note_category.blockSignals(False)
        self.notes_list.clearSelection()
        self.notes_list.setCurrentItem(None)  # resets the editor via currentItemChanged
        self._refresh_notes()

    def _first_note_image_path(self, content: str) -> str:
        """Find the first image referenced by a note (Attachment: or ![..](..))."""
        candidates: list[str] = []
        for line in (content or "").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("attachment:"):
                candidates.append(stripped.split(":", 1)[1].strip())
            for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", stripped):
                candidates.append(match.group(1).strip())
        vault = prefs.vault_path(self.base_dir)
        image_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
        for raw in candidates:
            raw = (raw or "").strip().strip("\"'<>")
            if not raw:
                continue
            resolved = raw if os.path.isabs(raw) else os.path.join(vault, raw.replace("/", os.sep))
            if os.path.isfile(resolved) and resolved.lower().endswith(image_exts):
                return resolved
        return ""

    def _render_note_attachments(self, content: str):
        self._clear_note_attachments()
        path = self._first_note_image_path(content or "")
        if not path:
            return
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                return
            max_w, max_h = 460, 260
            if pixmap.width() > max_w or pixmap.height() > max_h:
                pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_note_image.setPixmap(pixmap)
            self.lbl_note_image.show()
            self._current_note_image_path = path
            self.btn_open_note_image.show()
        except Exception:
            self._clear_note_attachments()

    def _clear_note_attachments(self):
        self._current_note_image_path = ""
        if hasattr(self, "lbl_note_image"):
            self.lbl_note_image.clear()
            self.lbl_note_image.hide()
        if hasattr(self, "btn_open_note_image"):
            self.btn_open_note_image.hide()

    def _open_note_image(self):
        path = getattr(self, "_current_note_image_path", "")
        if path and os.path.isfile(path):
            try:
                os.startfile(path)
            except Exception:
                QMessageBox.information(self, "Notes", "Cannot open:\n" + str(path))

    def _find_in_note(self):
        """Highlight every match of the find query in the current note."""
        self._note_find_matches = []
        if not hasattr(self, "ed_note_find"):
            return
        query = self.ed_note_find.text().strip()
        selections = []
        if query and self.current_note_id:
            text = self.note_editor.toPlainText()
            lowered = text.lower()
            needle = query.lower()
            doc = self.note_editor.document()
            pos = 0
            while True:
                idx = lowered.find(needle, pos)
                if idx < 0:
                    break
                extra = QTextEdit.ExtraSelection()
                cursor = QTextCursor(doc)
                cursor.setPosition(idx)
                cursor.setPosition(idx + len(query), QTextCursor.KeepAnchor)
                extra.cursor = cursor
                # Theme-aware highlight: v6.4 hard-coded amber/ink colors that
                # vanished on dark themes.
                p = theme.palette()
                extra.format.setBackground(QColor(p["ACCENT"]))
                extra.format.setForeground(QColor(p["MAIN_BG"]))
                selections.append(extra)
                self._note_find_matches.append(idx)
                pos = idx + len(query)
        self.note_editor.setExtraSelections(selections)
        if not hasattr(self, "lbl_find_count"):
            return
        if not query:
            self.lbl_find_count.setText("")
        elif self._note_find_matches:
            self.lbl_find_count.setText(f"{len(self._note_find_matches)} matches")
        else:
            self.lbl_find_count.setText("No matches")

    def _find_note_step(self, direction):
        matches = getattr(self, "_note_find_matches", [])
        if not matches:
            return
        query = self.ed_note_find.text()
        if not query:
            return
        doc = self.note_editor.document()
        current = self.note_editor.textCursor().selectionStart()
        target = -1
        if direction > 0:
            for match in matches:
                if match > current:
                    target = match
                    break
            if target < 0:
                target = matches[0]
        else:
            for match in reversed(matches):
                if match < current:
                    target = match
                    break
            if target < 0:
                target = matches[-1]
        cursor = QTextCursor(doc)
        cursor.setPosition(target)
        cursor.setPosition(target + len(query), QTextCursor.KeepAnchor)
        self.note_editor.setTextCursor(cursor)
        self.note_editor.centerCursor()

    def _find_next(self):
        self._find_note_step(1)

    def _find_prev(self):
        self._find_note_step(-1)

    def _persist_note_order(self):
        order = []
        for index in range(self.notes_list.count()):
            item = self.notes_list.item(index)
            if item is None:
                continue
            note_id = item.data(Qt.UserRole)
            if note_id:
                order.append(str(note_id))
        prefs.set_note_order(self.base_dir, order)

    def _move_notes_to_category(self, note_ids, category):
        # Flush unsaved edits first: moving rewrites the file under a new id,
        # and pending editor text would otherwise be lost (v6.4 bug).
        if not self._flush_note_edits():
            return
        moved = 0
        open_moved = None
        for note_id in note_ids:
            note = personal_service.read_note(self.base_dir, note_id)
            if not note:
                continue
            result = personal_service.update_note(self.base_dir, note_id, note["content"], category=category)
            if result:
                moved += 1
                if note_id == self.current_note_id:
                    open_moved = result
        # update_note relocates the file, which changes the note id; the open
        # note must follow or later saves would fail silently.
        if open_moved is not None:
            self.current_note_id = open_moved["id"]
            self.current_note_category = open_moved.get("category") or category
        self._refresh_notes()
        if self.current_note_id:
            self.select_note(self.current_note_id)
        self._refresh_overview()
        if moved:
            self._flash(f"Moved {moved} note(s) to {category}")
        else:
            self._flash("Could not move the notes")

    def _save_note(self):
        if not self.current_note_id:
            QMessageBox.information(self, "Notes", "Select a note first.")
            return
        # Preserve the note's own category on save; the combo is only a filter.
        category = self.current_note_category or "General"
        try:
            saved = personal_service.save_note(self.base_dir, self.current_note_id, self.note_editor.toPlainText(), expected_content=getattr(self, "_note_loaded_content", None))
            note = personal_service.read_note(self.base_dir, self.current_note_id) if saved else None
        except personal_service.NoteConflictError:
            # Explicit Save offers a non-destructive resolution without a modal.
            existing = personal_service.read_note(self.base_dir, self.current_note_id)
            title = (existing or {}).get("title", "Note") + " (my draft)"
            try:
                note = personal_service.create_note(self.base_dir, title, self.note_editor.toPlainText(), category=category)
            except OSError:
                note = None
        except OSError:
            note = None
        if not note:
            QMessageBox.warning(self, "Notes", "Could not save this note.")
            return
        self.current_note_id = note["id"]
        self.current_note_category = note.get("category") or "General"
        self._note_loaded_content = note["content"]
        self._note_dirty = False
        self._set_writing_active(True)
        self._set_save_state("saved", "Saved locally")
        self._refresh_notes()
        self.select_note(self.current_note_id)
        self._refresh_overview()

    def _ask_ai_about_note(self):
        if not self.current_note_id:
            QMessageBox.information(self, "AI", "Select a note first.")
            return
        shell = self._host_shell()
        if not shell or not hasattr(shell, "ai_page"):
            QMessageBox.information(self, "AI", "Open Personal Hub inside the main shell to use the assistant.")
            return
        title = self._note_title or "Current note"
        body = self.note_editor.toPlainText().strip()
        question = f"Summarize and improve this note: {title}"
        if not shell.switch_workspace("ai"):
            return
        shell.ed_ai_quick.setText(question)
        shell.ai_page.ask_with_context(question, "Current note", f"Title: {title}\n\n{body[:3000]}")

    def _delete_note(self):
        if not self.current_note_id:
            return
        deleted_id = self.current_note_id
        # The note's own title, not the title label: the label carries the
        # category suffix and once held transient status text.
        confirm = QMessageBox.question(
            self,
            "Delete note",
            "Delete this note permanently?\n\n" + (self._note_title or deleted_id),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        personal_service.delete_note(self.base_dir, deleted_id)
        # Cascade: cards generated from this note have no context without it.
        from litebrowser.services import flashcard_service

        removed_cards = flashcard_service.delete_cards_for_note(self.base_dir, deleted_id)
        prefs.set_note_order(self.base_dir, [nid for nid in prefs.get_note_order(self.base_dir) if nid != deleted_id])
        self.current_note_id = None
        self._note_title = ""
        self._note_dirty = False
        self.note_editor.setPlainText("")
        self.lbl_note_title.setText("No note selected")
        self._clear_note_attachments()
        self._find_in_note()
        self._set_writing_active(False)
        self._refresh_notes()
        self._refresh_overview()
        if removed_cards:
            self._flash(f"Note deleted — {removed_cards} linked card(s) removed too")

    def _make_flashcard_from_selection(self):
        """Selection → flashcard: front = the selection, back = a prompt; or
        'question ==== answer' on one line splits into both sides."""
        if not self.current_note_id:
            QMessageBox.information(self, "Flashcards", "Open a note first.")
            return
        cursor = self.note_editor.textCursor()
        selection = cursor.selectedText().strip()
        if not selection:
            QMessageBox.information(self, "Flashcards", "Select the text to turn into a card first.")
            return
        selection = selection.replace("\u2029", "\n")
        if "====" in selection:
            front, _, back = selection.partition("====")
            front, back = front.strip(), back.strip()
        else:
            front = selection[:200]
            back = f"From: {self._note_title}"
        if not front or not back:
            QMessageBox.information(self, "Flashcards", "Selection did not yield both sides of a card.")
            return
        self.make_flashcard_from_note(front, back, self.current_note_id)
        self._switch_page("review")

    def _build_review_page(self):
        """Flashcard review: card flip with Again/Hard/Good/Easy grading."""
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.addWidget(components.page_header("Review", "Spaced repetition — a little every day"), 1)
        self.lbl_review_stats = QLabel("")
        self.lbl_review_stats.setObjectName("MutedLabel")
        header_row.addWidget(self.lbl_review_stats)
        l.addLayout(header_row)

        # Deck toolbar: practice scope (Due vs All cards) on the left; on the
        # right the position counter with prev/next paging plus delete, so a
        # long queue can be browsed in both directions at any time.
        tool_row = QHBoxLayout()
        tool_row.setSpacing(6)
        self.btn_mode_due = QPushButton("Due")
        self.btn_mode_all = QPushButton("All cards")
        for _btn in (self.btn_mode_due, self.btn_mode_all):
            _btn.setObjectName("ChipButton")
            _btn.setCheckable(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.btn_mode_due)
        mode_group.addButton(self.btn_mode_all)
        self.btn_mode_due.setChecked(True)
        tool_row.addWidget(self.btn_mode_due)
        tool_row.addWidget(self.btn_mode_all)
        tool_row.addStretch(1)
        self.lbl_review_counter = QLabel("0 / 0")
        self.lbl_review_counter.setObjectName("MutedLabel")
        self.lbl_review_counter.setToolTip("Position in the current practice deck")
        tool_row.addWidget(self.lbl_review_counter)
        self.btn_review_prev = QPushButton("‹")
        self.btn_review_prev.setObjectName("NavToggle")
        self.btn_review_prev.setToolTip("Previous card (←)")
        self.btn_review_next = QPushButton("›")
        self.btn_review_next.setObjectName("NavToggle")
        self.btn_review_next.setToolTip("Next card (→)")
        self.btn_card_delete = QPushButton("🗑")
        self.btn_card_delete.setObjectName("NavToggle")
        self.btn_card_delete.setToolTip("Delete the current card")
        # Importing a deck from Anki (and exporting this one back) is what the
        # deck does occasionally, not what this page is for, so the two verbs
        # sit in an overflow menu instead of adding two more look-alike buttons.
        self.btn_deck_file = more_menu(
            [
                ("📥  Import an Anki deck (.apkg)…", self._import_deck),
                ("📤  Export as an Anki deck…", self._export_deck),
            ],
            label="⋯",
            tooltip="Import a deck from Anki, or export this one for Anki",
        )
        self.btn_deck_file.setObjectName("QuietButton")
        self.btn_deck_file.setProperty("compactIcon", True)
        self.btn_deck_file.setFixedSize(34, 34)
        tool_row.addWidget(self.btn_review_prev)
        tool_row.addWidget(self.btn_review_next)
        tool_row.addWidget(self.btn_card_delete)
        tool_row.addWidget(self.btn_deck_file)
        l.addLayout(tool_row)

        # Card surface: front/back flip in one themed card.
        self.review_card = QFrame()
        self.review_card.setObjectName("HeroCard")
        card_layout = QVBoxLayout(self.review_card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(10)
        card_layout.addStretch(1)
        self.lbl_card_front = QLabel("")
        self.lbl_card_front.setObjectName("HeroTitle")
        self.lbl_card_front.setWordWrap(True)
        self.lbl_card_front.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.lbl_card_front)
        self.lbl_card_hint = QLabel("Click to reveal")
        self.lbl_card_hint.setObjectName("MutedLabel")
        self.lbl_card_hint.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.lbl_card_hint)
        self.lbl_card_back = QLabel("")
        self.lbl_card_back.setObjectName("HeroSubtitle")
        self.lbl_card_back.setWordWrap(True)
        self.lbl_card_back.setAlignment(Qt.AlignCenter)
        self.lbl_card_back.hide()
        card_layout.addWidget(self.lbl_card_back)
        card_layout.addStretch(1)
        self.review_card.setFocusPolicy(Qt.StrongFocus)
        self.review_card.setAccessibleName("Flashcard — Space to reveal; 1 to 4 to grade")
        self.review_card.setCursor(Qt.PointingHandCursor)
        self.review_card.mousePressEvent = lambda _ev: self._flip_review_card()
        self.review_card.setMinimumHeight(200)

        # The card and the empty state share one surface slot between the
        # header and the grade/add rows.  (Previously the empty state was a
        # separate layout entry BELOW the fixed rows: when the queue drained,
        # hiding the stretch-1 card left the empty panel stranded at the
        # bottom of the page and stretched it into a giant misplaced panel.)
        self.review_surface = QStackedWidget()
        card_slot = QWidget()
        card_slot_layout = QVBoxLayout(card_slot)
        card_slot_layout.setContentsMargins(0, 0, 0, 0)
        card_slot_layout.addWidget(self.review_card)
        self.review_surface_card_index = self.review_surface.addWidget(card_slot)

        empty_slot = QWidget()
        empty_slot_layout = QVBoxLayout(empty_slot)
        empty_slot_layout.setContentsMargins(40, 24, 40, 24)
        empty = components.empty_state("No cards due", "Add a card above, or select text in a note and make one.")
        self.review_empty = empty
        empty_slot_layout.addWidget(empty)
        self.review_surface_empty_index = self.review_surface.addWidget(empty_slot)
        l.addWidget(self.review_surface, 1)

        grades_row = QHBoxLayout()
        grades_row.addStretch(1)
        self.btn_card_again = QPushButton("Again")
        self.btn_card_hard = QPushButton("Hard")
        self.btn_card_good = QPushButton("Good")
        self.btn_card_easy = QPushButton("Easy")
        for b in (self.btn_card_again, self.btn_card_hard, self.btn_card_good, self.btn_card_easy):
            b.setEnabled(False)
            grades_row.addWidget(b)
        l.addLayout(grades_row)

        add_row = QHBoxLayout()
        self.ed_card_front = QLineEdit()
        self.ed_card_front.setPlaceholderText("New card front (question)...")
        self.ed_card_back = QLineEdit()
        self.ed_card_back.setPlaceholderText("Back (answer)...")
        self.btn_card_add = QPushButton("Add card")
        add_row.addWidget(self.ed_card_front, 1)
        add_row.addWidget(self.ed_card_back, 1)
        add_row.addWidget(self.btn_card_add)
        l.addLayout(add_row)

        self._deck: list[dict] = []
        self._deck_pos = 0
        self._deck_mode = "due"
        self.btn_mode_due.clicked.connect(lambda: self._set_review_mode("due"))
        self.btn_mode_all.clicked.connect(lambda: self._set_review_mode("all"))
        self.btn_review_prev.clicked.connect(lambda: self._nav_review(-1))
        self.btn_review_next.clicked.connect(lambda: self._nav_review(1))
        self.btn_card_delete.clicked.connect(self._delete_current_card)
        self.btn_card_again.clicked.connect(lambda: self._grade_review("again"))
        self.btn_card_hard.clicked.connect(lambda: self._grade_review("hard"))
        self.btn_card_good.clicked.connect(lambda: self._grade_review("good"))
        self.btn_card_easy.clicked.connect(lambda: self._grade_review("easy"))
        self.btn_card_add.clicked.connect(self._add_review_card)
        # Keyboard-first review: Space flips, 1-4 grade (Anki muscle memory).
        grade_shortcuts = (
            (Qt.Key_Space, self._flip_review_card),
            (Qt.Key_1, lambda: self._grade_review("again")),
            (Qt.Key_2, lambda: self._grade_review("hard")),
            (Qt.Key_3, lambda: self._grade_review("good")),
            (Qt.Key_4, lambda: self._grade_review("easy")),
            (Qt.Key_Left, lambda: self._nav_review(-1)),
            (Qt.Key_Right, lambda: self._nav_review(1)),
        )
        for key_code, handler in grade_shortcuts:
            shortcut = QShortcut(QKeySequence(int(key_code)), self.review_card)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)
        return w

    def _refresh_review(self):
        """Called when entering Review / after data changes."""
        self._update_review_stats()
        if not getattr(self, "_deck", None):
            # A fresh visit starts from the due queue — even when the last
            # visit ended in an All-cards session that just drained.
            self._deck_mode = "due"
            if hasattr(self, "btn_mode_due"):
                self.btn_mode_due.setChecked(True)
                self.btn_mode_all.setChecked(False)
            self._reload_deck()
        else:
            # An in-progress session survives a page refresh: graded cards
            # have already left the deck, so just re-render the current one.
            self._show_current_card()

    def _set_review_mode(self, mode: str):
        self._deck_mode = mode
        self.btn_mode_due.setChecked(mode == "due")
        self.btn_mode_all.setChecked(mode == "all")
        self._reload_deck()

    def _reload_deck(self):
        from litebrowser.services import flashcard_service

        if getattr(self, "_deck_mode", "due") == "all":
            self._deck = flashcard_service.load_cards(self.base_dir)
        else:
            self._deck = flashcard_service.due_cards(self.base_dir)
        self._deck_pos = 0
        self._show_current_card()

    def _update_review_stats(self):
        from litebrowser.services import flashcard_service

        stats = flashcard_service.stats(self.base_dir)
        self.lbl_review_stats.setText(f"{stats['total']} cards · {stats['due']} due · {stats['matured']} matured")

    def _show_current_card(self):
        deck = getattr(self, "_deck", None)
        if not deck:
            self._show_review_empty()
            return
        pos = min(max(0, getattr(self, "_deck_pos", 0)), len(deck) - 1)
        self._deck_pos = pos
        self.review_surface.setCurrentIndex(self.review_surface_card_index)
        self.review_empty.hide()
        self.review_card.show()
        card = deck[pos]
        self.lbl_card_front.setText(card.get("front", ""))
        self.lbl_card_back.setText(card.get("back", ""))
        self.lbl_card_back.hide()
        self.lbl_card_hint.setText("Click to reveal")
        for b in (self.btn_card_again, self.btn_card_hard, self.btn_card_good, self.btn_card_easy):
            b.setEnabled(False)
        self.lbl_review_counter.setText(f"{pos + 1} / {len(deck)}")
        self.btn_review_prev.setEnabled(pos > 0)
        self.btn_review_next.setEnabled(pos < len(deck) - 1)
        self.btn_card_delete.setEnabled(True)

    def _show_review_empty(self):
        from litebrowser.services import flashcard_service

        self.review_surface.setCurrentIndex(self.review_surface_empty_index)
        self.review_card.hide()
        self.review_empty.show()
        total = flashcard_service.stats(self.base_dir)["total"]
        if total == 0:
            title, hint = "No cards yet", "Add a card below, or select text in a note and choose “Make flashcard”."
        elif getattr(self, "_deck_mode", "due") == "all":
            title, hint = "Deck complete", "Every card practiced — graded cards are scheduled for their next review."
        else:
            title, hint = "All due cards reviewed", "Nothing left due right now — switch to “All cards” to practice the whole deck."
        if getattr(self.review_empty, "_empty_title", None) is not None:
            self.review_empty._empty_title.setText(title)
        if getattr(self.review_empty, "_empty_hint", None) is not None:
            self.review_empty._empty_hint.setText(hint)
        for b in (self.btn_card_again, self.btn_card_hard, self.btn_card_good, self.btn_card_easy):
            b.setEnabled(False)
        self.btn_review_prev.setEnabled(False)
        self.btn_review_next.setEnabled(False)
        self.btn_card_delete.setEnabled(False)
        self.lbl_review_counter.setText("0 / 0")

    def _nav_review(self, delta: int):
        """Move through the deck without grading (peek ahead / go back)."""
        if not getattr(self, "_deck", None):
            return
        pos = self._deck_pos + delta
        if not (0 <= pos < len(self._deck)):
            return
        self._deck_pos = pos
        self._show_current_card()

    def _flip_review_card(self):
        if not getattr(self, "_deck", None):
            return
        if self.lbl_card_back.isHidden():
            self.lbl_card_back.show()
            self.lbl_card_hint.setText("How well did you remember?")
            for b in (self.btn_card_again, self.btn_card_hard, self.btn_card_good, self.btn_card_easy):
                b.setEnabled(True)
        else:
            self.lbl_card_back.hide()
            self.lbl_card_hint.setText("Click to reveal")
            for b in (self.btn_card_again, self.btn_card_hard, self.btn_card_good, self.btn_card_easy):
                b.setEnabled(False)

    def _grade_review(self, grade: str):
        from litebrowser.services import flashcard_service

        deck = getattr(self, "_deck", None)
        if not deck:
            return
        pos = min(max(0, self._deck_pos), len(deck) - 1)
        card = deck[pos]
        flashcard_service.review_card(self.base_dir, card["id"], grade)
        # The graded card leaves this session's deck (a due review drains,
        # All-cards walks the whole library once).  Keeping the index shows
        # the next card; a last-card grade clamps back onto the previous one.
        self._deck = [c for c in deck if c.get("id") != card["id"]]
        self._deck_pos = min(pos, max(0, len(self._deck) - 1))
        self._update_review_stats()
        self._show_current_card()

    def _delete_current_card(self):
        deck = getattr(self, "_deck", None)
        if not deck:
            return
        pos = min(max(0, self._deck_pos), len(deck) - 1)
        card = deck[pos]
        answer = QMessageBox.question(
            self,
            "Delete card",
            f"Delete this card?\n\n{card.get('front', '')}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        from litebrowser.services import flashcard_service

        flashcard_service.delete_card(self.base_dir, card["id"])
        self._deck = [c for c in self._deck if c.get("id") != card["id"]]
        self._deck_pos = min(pos, max(0, len(self._deck) - 1))
        self._update_review_stats()
        self._show_current_card()

    def _add_review_card(self):
        from litebrowser.services import flashcard_service

        front = self.ed_card_front.text().strip()
        back = self.ed_card_back.text().strip()
        if not front or not back:
            QMessageBox.information(self, "Review", "Fill in both sides of the card.")
            return
        flashcard_service.add_card(self.base_dir, front, back)
        self.ed_card_front.clear()
        self.ed_card_back.clear()
        self._reload_deck()

    def _import_deck(self):
        """An .apkg from Anki → cards here, with its interval and ease intact."""
        from litebrowser.services import anki_service

        path, _ = QFileDialog.getOpenFileName(
            self, "Import an Anki deck", "", "Anki deck (*.apkg);;All files (*)"
        )
        if not path:
            return
        try:
            report = anki_service.import_package(self.base_dir, path)
        except Exception as exc:
            QMessageBox.warning(self, "Deck", f"Import failed: {exc}")
            return
        self._reload_deck()
        self._update_review_stats()
        imported = int(report["imported"])
        note = f"Imported {imported} card{'' if imported == 1 else 's'} from “{report['deck']}”."
        if report["duplicates"]:
            note += f"\n{report['duplicates']} were already in the deck."
        if report["skipped"]:
            note += f"\n{report['skipped']} notes had no answer and were skipped."
        if report["media"]:
            note += f"\n{report['media']} media files stayed in Anki — Mei cards are text."
        QMessageBox.information(self, "Deck", note)

    def _export_deck(self):
        """The whole deck as one .apkg Anki can open, scheduling included."""
        from litebrowser.services import anki_service

        default = os.path.join(self.base_dir, "mei-deck-" + time.strftime("%Y%m%d") + ".apkg")
        path, _ = QFileDialog.getSaveFileName(self, "Export the deck", default, "Anki deck (*.apkg)")
        if not path:
            return
        try:
            report = anki_service.export_package(self.base_dir, path)
        except Exception as exc:
            QMessageBox.warning(self, "Deck", f"Export failed: {exc}")
            return
        exported = int(report["cards"])
        QMessageBox.information(
            self,
            "Deck",
            f"Exported {exported} card{'' if exported == 1 else 's'} to:\n{path}\n\nAnki: File → Import.",
        )

    def make_flashcard_from_note(self, front: str, back: str, note_id: str = ""):
        """Entry point for the notes page ('Make flashcard' on selection)."""
        from litebrowser.services import flashcard_service

        card = flashcard_service.add_card(self.base_dir, front, back, source_note_id=note_id)
        if note_id and card:
            # Make the card's source explicit in the link graph too, so the
            # note's Related panel lists it and deleting either side cascades.
            link_service.add_link(self.base_dir, "flashcard", card["id"], "note", note_id)
        self._flash(f"Card added — {stats_text(flashcard_service.stats(self.base_dir))}")

    def _build_plan_page(self):
        """Build the weekly student planner surface on the shared plan schema."""
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(6)
        header = QHBoxLayout()
        header.addWidget(
            components.page_header(
                "Weekly Plan",
                "A paper planner for the week: deadlines, blocks, and the study loop",
                kicker="Planner",
            ),
            1,
        )
        self.btn_plan_prev = QPushButton("‹")
        self.btn_plan_prev.setToolTip("Previous week")
        self.btn_plan_today = QPushButton("Today")
        self.btn_plan_next = QPushButton("›")
        self.lbl_plan_week = QLabel("")
        self.lbl_plan_week.setObjectName("PlanWeek")
        self.btn_plan_settings = QPushButton("⚙ Semester")
        self.btn_plan_settings.setToolTip(
            "Semester name and dates — the planner keeps its term settings in the plan store"
        )
        self.btn_plan_settings.clicked.connect(self._edit_plan_settings)
        header.addWidget(self.btn_plan_settings)
        l.addLayout(header)

        # Week navigation gets its own quiet strip: the header says where you
        # are, this says which week you are looking at.  Keeping them apart is
        # what stops a date field from being clipped by five neighbours.
        week_strip = QFrame()
        week_strip.setObjectName("PlanToolbar")
        week_layout = QHBoxLayout(week_strip)
        week_layout.setContentsMargins(8, 4, 8, 4)
        week_layout.setSpacing(6)
        week_layout.addWidget(self.btn_plan_prev)
        week_layout.addWidget(self.btn_plan_today)
        week_layout.addWidget(self.btn_plan_next)
        week_layout.addWidget(self.lbl_plan_week)
        week_layout.addStretch(1)
        l.addWidget(week_strip)

        form_frame = QFrame()
        form_frame.setObjectName("PlanToolbar")
        form = QHBoxLayout(form_frame)
        form.setContentsMargins(8, 6, 8, 6)
        form.setSpacing(7)
        self.ed_plan_title = QLineEdit()
        self.ed_plan_title.setPlaceholderText("New assignment or task...")
        self.cmb_plan_kind = QComboBox()
        self.cmb_plan_kind.addItems(["task", "assignment", "exam", "project", "study"])
        self.ed_plan_date = QDateEdit(QDate.currentDate())
        self.ed_plan_date.setCalendarPopup(True)
        self.ed_plan_date.setDisplayFormat("yyyy-MM-dd")
        self.ed_plan_date.setToolTip("The day this item appears in the weekly planner")
        self.ed_plan_due = QDateEdit(QDate.currentDate())
        self.ed_plan_due.setCalendarPopup(True)
        self.ed_plan_due.setDisplayFormat("yyyy-MM-dd")
        self.ed_plan_due.setToolTip("The deadline; it follows the planned date until you edit it")
        self._planner_due_follows_schedule = True
        self.ed_plan_date.dateChanged.connect(self._planner_sync_due_date)
        self.ed_plan_due.dateChanged.connect(self._planner_due_date_edited)
        self.cmb_plan_priority = QComboBox()
        self.cmb_plan_priority.addItems(["low", "medium", "high", "urgent"])
        self.cmb_plan_course = QComboBox()
        self.cmb_plan_course.setToolTip("Tag the item with the course it belongs to")
        self.spin_plan_duration = QSpinBox()
        self.spin_plan_duration.setRange(5, 1440)
        self.spin_plan_duration.setValue(personal_plan.DEFAULT_DURATION_MINUTES)
        self.spin_plan_duration.setSuffix(" min")
        # The form row is mostly fields; the two row chores are glyphs now, so
        # the only filled control in it is the one that creates the item.
        self.btn_plan_add = primary_button("Add item")
        self.btn_plan_add.setToolTip("Create the item and show it on its planned day")
        self.btn_plan_delete = icon_button("🗑", "Delete the selected planner item or focus block")
        self.btn_plan_study = ghost_button("▶ Study")
        self.btn_plan_study.setToolTip(
            "Pour a focus session for the selected item or block; the minutes are credited back"
        )
        form.addWidget(self.ed_plan_title, 2)
        self.ed_plan_title.setMinimumWidth(120)
        self.ed_plan_date.setAccessibleName("Planned date")
        # Date fields carry a calendar button; without a floor the form squeezed
        # the year out of "2026-09-30" at 1440px.
        self.ed_plan_date.setMinimumWidth(122)
        form.addWidget(QLabel("On"))
        form.addWidget(self.ed_plan_date)
        self.btn_plan_details = components.chip("Details ▾", checkable=True, checked=False)
        form.addWidget(self.btn_plan_details)
        form.addWidget(self.btn_plan_add)
        form.addWidget(self.btn_plan_study)
        form.addWidget(self.btn_plan_delete)
        l.addWidget(form_frame)
        self._plan_details = QWidget()
        detail_grid = QGridLayout(self._plan_details)
        detail_grid.setContentsMargins(0, 0, 0, 0)
        for index, (label, control) in enumerate((("Type", self.cmb_plan_kind), ("Deadline", self.ed_plan_due), ("Priority", self.cmb_plan_priority), ("Course", self.cmb_plan_course), ("Duration", self.spin_plan_duration))):
            row_index, col = index // 3, (index % 3) * 2
            control.setAccessibleName(label)
            control.setMinimumWidth(0)
            detail_grid.addWidget(QLabel(label), row_index, col)
            detail_grid.addWidget(control, row_index, col + 1)
        self._plan_details.hide()
        self.btn_plan_details.toggled.connect(self._plan_details.setVisible)
        l.addWidget(self._plan_details)
        self.btn_plan_setup = components.chip("Focus blocks & courses ▾", checkable=True, checked=False)
        l.addWidget(self.btn_plan_setup, 0, Qt.AlignLeft)
        self._plan_setup = QWidget()
        setup_layout = QVBoxLayout(self._plan_setup)
        setup_layout.setContentsMargins(0, 0, 0, 0)
        self._plan_setup.hide()
        self.btn_plan_setup.toggled.connect(self._plan_setup.setVisible)
        l.addWidget(self._plan_setup)
        block_form = QGridLayout()
        self.ed_plan_block_title = QLineEdit()
        self.ed_plan_block_title.setPlaceholderText("Study block title...")
        self.spin_plan_block_start = _MinuteTimeSpin()
        self.spin_plan_block_start.setRange(0, 1439)
        self.spin_plan_block_start.setValue(9 * 60)
        self.spin_plan_block_start.setSingleStep(15)
        self.spin_plan_block_start.setAccessibleName("Focus block start time")
        self.spin_plan_block_duration = QSpinBox()
        self.spin_plan_block_duration.setRange(5, 1440)
        self.spin_plan_block_duration.setValue(50)
        self.spin_plan_block_duration.setSuffix(" block min")
        self.cmb_plan_block_course = QComboBox()
        self.cmb_plan_block_course.setToolTip("Optional course for this focus block")
        self.btn_plan_add_block = ghost_button("Add time block")
        self.btn_plan_add_block.setToolTip("Add a focused study block to the selected planned day")
        block_form.addWidget(self.ed_plan_block_title, 0, 0, 1, 5)
        block_form.addWidget(QLabel("Start"), 1, 0)
        block_form.addWidget(self.spin_plan_block_start, 1, 1)
        block_form.addWidget(QLabel("Duration"), 1, 2)
        block_form.addWidget(self.spin_plan_block_duration, 1, 3)
        block_form.addWidget(self.cmb_plan_block_course, 1, 4)
        block_form.addWidget(self.btn_plan_add_block, 0, 5, 2, 1)
        setup_layout.addLayout(block_form)

        courses_card = QFrame()
        courses_card.setObjectName("SectionCard")
        courses_layout = QVBoxLayout(courses_card)
        courses_layout.setContentsMargins(8, 6, 8, 6)
        courses_layout.setSpacing(4)
        courses_header = QHBoxLayout()
        courses_header.addWidget(
            components.section_header("Courses", "Optional subjects for your study plan"), 1
        )
        self.btn_plan_course_add = ghost_button("＋ Course", "Add a course to plan items against")
        self.btn_plan_course_edit = icon_button("✎", "Edit the selected course")
        self.btn_plan_course_delete = icon_button(
            "🗑", "Delete the selected course; its items are kept, just detached"
        )
        courses_header.addWidget(self.btn_plan_course_add)
        courses_header.addWidget(self.btn_plan_course_edit)
        courses_header.addWidget(self.btn_plan_course_delete)
        courses_layout.addLayout(courses_header)
        self.plan_courses_list = QListWidget()
        self.plan_courses_list.setObjectName("CafeList")
        self.plan_courses_list.setMaximumHeight(72)
        self.plan_courses_list.setToolTip("Double-click a course to edit it")
        courses_layout.addWidget(self.plan_courses_list)
        setup_layout.addWidget(courses_card)

        self.lbl_plan_guide = QLabel(
            "Guide: choose a date, add an item, tick it when complete, drag it to reschedule, or select it and delete it."
        )
        self.lbl_plan_guide.setObjectName("MutedLabel")
        self.lbl_plan_guide.setWordWrap(True)
        self.lbl_plan_guide.setText("Tick to complete · drag to reschedule · double-click a focus block to edit")
        l.addWidget(self.lbl_plan_guide)
        self.lbl_plan_study = QLabel("")
        self.lbl_plan_study.setObjectName("MutedLabel")
        self.lbl_plan_study.setWordWrap(True)
        l.addWidget(self.lbl_plan_study)
        self.lbl_plan_summary = QLabel("")
        self.lbl_plan_summary.setObjectName("MutedLabel")
        l.addWidget(self.lbl_plan_summary)
        self.plan_columns_wrap = QWidget()
        columns = QHBoxLayout(self.plan_columns_wrap)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(5)
        self.plan_day_lists = {}
        for offset in range(7):
            card = QFrame()
            card.setObjectName("PlanColumn")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(6)
            day_label = QLabel("")
            day_label.setObjectName("PlanDayHead")
            day_label.setAlignment(Qt.AlignCenter)
            day_list = PlannerDayList(self, "", card)
            day_list.setObjectName("CafeList")
            day_list.itemClicked.connect(self._planner_item_clicked)
            day_list.itemDoubleClicked.connect(self._planner_edit_clicked)
            day_body = QFrame()
            day_body.setObjectName("PlanColumnBody")
            day_body_layout = QVBoxLayout(day_body)
            day_body_layout.setContentsMargins(4, 4, 4, 4)
            day_body_layout.setSpacing(0)
            day_body_layout.addWidget(day_list, 1)
            card_layout.addWidget(day_label)
            card_layout.addWidget(day_body, 1)
            card.setMinimumWidth(128)
            columns.addWidget(card, 1)
            self.plan_day_lists[offset] = (day_label, day_list)
        self.plan_scroll = QScrollArea()
        self.plan_scroll.setWidget(self.plan_columns_wrap)
        self.plan_scroll.setWidgetResizable(True)
        self.plan_scroll.setFrameShape(QFrame.NoFrame)
        self.plan_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        l.addWidget(self.plan_scroll, 1)

        self._planner_week_start = personal_plan.week_key()
        self._planner_drag_item_id = ""
        self._planner_drag_source_day = ""
        self.btn_plan_prev.clicked.connect(lambda: self._shift_planner_week(-7))
        self.btn_plan_today.clicked.connect(self._planner_today)
        self.btn_plan_next.clicked.connect(lambda: self._shift_planner_week(7))
        self.btn_plan_add.clicked.connect(self._planner_add_item)
        self.btn_plan_add_block.clicked.connect(self._planner_add_block)
        self.btn_plan_delete.clicked.connect(self._planner_delete_selected)
        self.btn_plan_study.clicked.connect(self._planner_study_selected)
        self.btn_plan_course_add.clicked.connect(self._planner_add_course)
        self.btn_plan_course_edit.clicked.connect(self._planner_edit_course)
        self.btn_plan_course_delete.clicked.connect(self._planner_delete_course)
        self.plan_courses_list.itemDoubleClicked.connect(lambda _row: self._planner_edit_course())
        self._refresh_plan()
        return w

    def _planner_due_date_edited(self, _date):
        self._planner_due_follows_schedule = False

    def _planner_sync_due_date(self, scheduled_date):
        if not self._planner_due_follows_schedule:
            return
        self.ed_plan_due.blockSignals(True)
        self.ed_plan_due.setDate(scheduled_date)
        self.ed_plan_due.blockSignals(False)

    def _shift_planner_week(self, days: int):
        anchor = QDate.fromString(self._planner_week_start, "yyyy-MM-dd").addDays(days)
        self._planner_week_start = personal_plan.week_key(anchor.toString("yyyy-MM-dd"))
        self._refresh_plan()

    def _planner_today(self):
        self._planner_week_start = personal_plan.week_key()
        self._refresh_plan()

    def _planner_add_item(self):
        title = self.ed_plan_title.text().strip()
        if not title:
            return
        scheduled = self.ed_plan_date.date().toString("yyyy-MM-dd")
        due = self.ed_plan_due.date().toString("yyyy-MM-dd")
        course = self._planner_course_fields(self.cmb_plan_course)
        try:
            personal_plan.create_item(
                self.base_dir,
                title,
                kind=self.cmb_plan_kind.currentText(),
                scheduled_date=scheduled,
                due_date=due,
                priority=self.cmb_plan_priority.currentText(),
                category=course["category"],
                course_id=course["course_id"],
                duration_minutes=self.spin_plan_duration.value(),
            )
        except ValueError:
            return
        self.ed_plan_title.clear()
        self._planner_due_follows_schedule = True
        self._planner_sync_due_date(self.ed_plan_date.date())
        self._refresh_plan()
        self._refresh_overview()

    def _planner_add_block(self):
        title = self.ed_plan_block_title.text().strip()
        if not title:
            return
        course = self._planner_course_fields(self.cmb_plan_block_course)
        try:
            personal_plan.create_time_block(
                self.base_dir,
                title,
                self.ed_plan_date.date().toString("yyyy-MM-dd"),
                self.spin_plan_block_start.value(),
                duration_minutes=self.spin_plan_block_duration.value(),
                course_id=course["course_id"],
                color=course["color"],
            )
        except ValueError:
            return
        self.ed_plan_block_title.clear()
        self._refresh_plan()

    def _planner_drop_item(self, item_id: str, day_key: str) -> bool:
        item = personal_plan.update_item(self.base_dir, item_id, scheduled_date=day_key)
        if item is None:
            return False
        self._refresh_plan()
        self._refresh_overview()
        return True

    def _planner_selected_id(self) -> str:
        for _label, day_list in self.plan_day_lists.values():
            row = day_list.currentItem()
            if row is not None:
                return str(row.data(Qt.UserRole) or "")
        return ""

    def _planner_study_selected(self):
        """Start a study pour from the selected item/block (minutes get credited)."""
        selected_id = self._planner_selected_id()
        if not selected_id:
            QMessageBox.information(self, "Study", "Select a planner item or focus block first.")
            return
        if selected_id.startswith("block:"):
            session = study_session.start_for_block(self.base_dir, selected_id[6:])
        else:
            session = study_session.start_for_item(self.base_dir, selected_id)
        if session is None:
            return
        self._refresh_plan()

    def _planner_delete_selected(self):
        selected_id = self._planner_selected_id()
        if not selected_id:
            return
        if selected_id.startswith("block:"):
            deleted = personal_plan.delete_time_block(self.base_dir, selected_id[6:])
        else:
            deleted = personal_plan.delete_item(self.base_dir, selected_id)
        if deleted:
            self._refresh_plan()
            self._refresh_overview()

    def _planner_edit_clicked(self, row: QListWidgetItem):
        entry_id = str(row.data(Qt.UserRole) or "")
        if entry_id.startswith("block:"):
            self._planner_edit_block(entry_id[6:])

    def _planner_edit_block(self, block_id: str):
        plan = personal_plan.load_plan(self.base_dir)
        block = next((entry for entry in plan["time_blocks"] if entry.get("id") == block_id), None)
        if block is None:
            return
        dialog = _BlockDialog(self, block, plan["courses"])
        if dialog.exec_() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["title"]:
            return
        personal_plan.update_time_block(self.base_dir, block_id, **values)
        self._refresh_plan()

    def _planner_course_fields(self, combo: QComboBox) -> dict:
        """Course picker -> the fields create_item/create_time_block want."""
        course_id = combo.currentData() or ""
        for course in personal_plan.load_plan(self.base_dir)["courses"]:
            if course.get("id") == course_id:
                return {
                    "course_id": course_id,
                    "color": course.get("color") or "#c39d63",
                    "category": course.get("name") or "General",
                }
        return {"course_id": "", "color": "#c39d63", "category": "General"}

    def _refresh_plan_courses(self, courses: list):
        if not hasattr(self, "plan_courses_list"):
            return
        self.plan_courses_list.clear()
        for course in courses:
            label = course.get("name", "")
            if course.get("code"):
                label += f" · {course['code']}"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, course.get("id", ""))
            if course.get("color"):
                row.setForeground(QColor(course["color"]))
            self.plan_courses_list.addItem(row)
        for combo in (self.cmb_plan_course, self.cmb_plan_block_course):
            keep = combo.currentData() or ""
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— No course —", "")
            for course in courses:
                combo.addItem(course.get("name", ""), course.get("id", ""))
            index = combo.findData(keep)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def _selected_course(self):
        row = self.plan_courses_list.currentItem()
        course_id = str(row.data(Qt.UserRole) or "") if row is not None else ""
        if not course_id:
            return None
        return next(
            (
                course
                for course in personal_plan.load_plan(self.base_dir)["courses"]
                if course.get("id") == course_id
            ),
            None,
        )

    def _planner_add_course(self):
        dialog = _CourseDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            return
        personal_plan.create_course(
            self.base_dir,
            values["name"],
            code=values["code"],
            color=values["color"],
            schedule=values["schedule"],
            credits=values["credits"],
        )
        self._refresh_plan()
        self._refresh_overview()

    def _planner_edit_course(self):
        course = self._selected_course()
        if course is None:
            QMessageBox.information(self, "Courses", "Select a course first.")
            return
        dialog = _CourseDialog(self, course)
        if dialog.exec_() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["name"]:
            return
        personal_plan.update_course(self.base_dir, course["id"], **values)
        self._refresh_plan()

    def _planner_delete_course(self):
        course = self._selected_course()
        if course is None:
            QMessageBox.information(self, "Courses", "Select a course first.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete course",
            f"Delete “{course.get('name', '')}”?\n\nIts items and time blocks are kept — they are just detached.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        personal_plan.delete_course(self.base_dir, course["id"])
        self._refresh_plan()
        self._refresh_overview()

    def _planner_item_clicked(self, row: QListWidgetItem):
        item_id = row.data(Qt.UserRole)
        if not item_id or str(item_id).startswith("block:"):
            return
        item = personal_plan.load_plan(self.base_dir)
        current = next((entry for entry in item["items"] if entry.get("id") == item_id), None)
        if current is None:
            return
        if row.checkState() == Qt.Checked:
            personal_plan.complete_item(self.base_dir, item_id, True)
        elif current.get("completed"):
            personal_plan.complete_item(self.base_dir, item_id, False)
        self._refresh_plan()
        self._refresh_overview()

    def _edit_plan_settings(self):
        """Term settings for the planner: name plus the dates the weeks are read against."""
        semester = personal_plan.load_plan(self.base_dir).get("semester") or {}
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Semester settings - {app_version.APP_NAME}")
        if hasattr(self, "_dialog_stylesheet"):
            dialog.setStyleSheet(self._dialog_stylesheet())
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Semester name"))
        ed_name = QLineEdit(semester.get("name", ""))
        ed_name.setPlaceholderText("HK1 2026-2027")
        layout.addWidget(ed_name)
        editors = []
        for label, key in (("Start date", "start_date"), ("End date", "end_date")):
            layout.addWidget(QLabel(label))
            editor = QDateEdit(QDate.currentDate())
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
            parsed = QDate.fromString(semester.get(key, ""), "yyyy-MM-dd")
            if parsed.isValid():
                editor.setDate(parsed)
            layout.addWidget(editor)
            editors.append(editor)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_cancel = QPushButton("Cancel")
        btn_save = QPushButton("Save")
        btn_save.setObjectName("TopAccentButton")
        btn_cancel.clicked.connect(dialog.reject)
        btn_save.clicked.connect(dialog.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_save)
        layout.addLayout(row)
        if dialog.exec_() != QDialog.Accepted:
            return
        name = ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Semester", "Give the semester a name first.")
            return
        personal_plan.update_plan_settings(
            self.base_dir,
            semester={
                "name": name,
                "start_date": editors[0].date().toString("yyyy-MM-dd"),
                "end_date": editors[1].date().toString("yyyy-MM-dd"),
            },
        )
        self._refresh_plan()
        self._flash(f"Semester set — {name}")

    def _refresh_plan(self):
        if not hasattr(self, "plan_day_lists"):
            return
        credited = study_session.credit_pending(self.base_dir)
        week = personal_plan.items_for_week(self.base_dir, self._planner_week_start)
        self._refresh_plan_courses(week["courses"])
        start = QDate.fromString(week["week_start"], "yyyy-MM-dd")
        self.lbl_plan_week.setText(f"{week['week_start']} → {week['week_end']}")
        # The term settings are part of the plan store, so the button that opens
        # them also reports them (with no name set it stays a plain invitation).
        semester_name = (personal_plan.load_plan(self.base_dir).get("semester") or {}).get("name", "")
        self.btn_plan_settings.setText(f"⚙ {semester_name}" if semester_name else "⚙ Semester")
        completed = sum(1 for item in week["items"] if item.get("completed"))
        self.lbl_plan_summary.setText(
            f"{len(week['items'])} planned item(s) · {completed} completed · {len(week['time_blocks'])} focus block(s)"
        )
        for offset, (day_label, day_list) in self.plan_day_lists.items():
            day = start.addDays(offset)
            day_key = day.toString("yyyy-MM-dd")
            day_label.setText(day.toString("ddd") + "\n" + day.toString("dd MMM"))
            day_list.day_key = day_key
            day_list.clear()
        course_names = {course.get("id"): course.get("name") for course in week["courses"]}
        course_colors = {course.get("id"): course.get("color", "") for course in week["courses"]}
        link_counts: dict[str, int] = {}
        for link in link_service.load_links(self.base_dir):
            for entity_type, entity_id in (
                (link["from_type"], link["from_id"]),
                (link["to_type"], link["to_id"]),
            ):
                if entity_type == "planner_item":
                    link_counts[entity_id] = link_counts.get(entity_id, 0) + 1
        for item in week["items"]:
            day_key = item.get("scheduled_date") or item.get("due_date") or ""
            if not (week["week_start"] <= day_key <= week["week_end"]):
                day_key = item.get("due_date") or item.get("scheduled_date") or ""
            offset = start.daysTo(QDate.fromString(day_key, "yyyy-MM-dd"))
            if offset not in self.plan_day_lists:
                continue
            label = f"[{item.get('kind', 'task')}] {item.get('title', '')}"
            if course_names.get(item.get("course_id")):
                label = "● " + label
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, item.get("id", ""))
            row.setFlags(row.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            row.setCheckState(Qt.Checked if item.get("completed") else Qt.Unchecked)
            if course_colors.get(item.get("course_id")):
                row.setForeground(QColor(course_colors[item.get("course_id")]))
            course = course_names.get(item.get("course_id"))
            details = f"{item.get('priority', 'medium')} · {item.get('category', 'General')}"
            if course:
                details += f" · {course}"
            if item.get("due_date"):
                details += f" · due {item['due_date']}"
            if int(item.get("studied_minutes", 0) or 0):
                details += f" · studied {item['studied_minutes']}m"
            if link_counts.get(item.get("id", "")):
                details += f" · 🔗 {link_counts[item['id']]}"
            row.setToolTip(details)
            self.plan_day_lists[offset][1].addItem(row)
        blocks_by_day = {}
        for block in week["time_blocks"]:
            blocks_by_day.setdefault(block.get("date"), []).append(block)
        for day_key, blocks in blocks_by_day.items():
            offset = start.daysTo(QDate.fromString(day_key, "yyyy-MM-dd"))
            if offset not in self.plan_day_lists:
                continue
            day_list = self.plan_day_lists[offset][1]
            for block in blocks:
                row = QListWidgetItem(f"◷ {block.get('title', '')} · {block.get('duration_minutes', 0)}m")
                row.setData(Qt.UserRole, f"block:{block.get('id', '')}")
                row.setFlags(Qt.ItemIsEnabled)
                row.setToolTip("Focus block — double-click to edit")
                if course_colors.get(block.get("course_id")):
                    row.setForeground(QColor(course_colors[block.get("course_id")]))
                day_list.addItem(row)

        active = study_session.active_session(self.base_dir)
        # Only when a pour is live or was just credited does the planner ask the
        # loop what comes next (build_flow reads every store; not a hot-path call).
        hint = ""
        if active["running"] or credited["credited"]:
            action = study_flow.build_flow(self.base_dir).get("next") or {}
            if action and action.get("step") != "study":
                hint = f" · next: {action.get('label', '')}"
        if active["running"]:
            remaining = int(active.get("remaining", 0) or 0)
            clock = f"{remaining // 60}m {remaining % 60:02d}s"
            item = active.get("item") or {}
            target = f" “{item.get('title', '')}”" if item else ""
            self.lbl_plan_study.setText(
                f"▶ Studying{target} — {clock} left · {active['cards_due']} card(s) due{hint}"
            )
        elif credited["credited"]:
            self.lbl_plan_study.setText(
                f"✓ Study credited — {credited['minutes']} min · {credited['cards_due']} card(s) "
                f"due{hint} (open Review with /review)"
            )
        else:
            self.lbl_plan_study.setText("")

    def _build_tasks_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(6)
        l.addWidget(components.page_header("Tasks", "Across personal, work, and study"))
        top_row = QHBoxLayout()
        self.ed_task_title = QLineEdit()
        self.ed_task_title.setPlaceholderText("New task...")
        self.cmb_task_bucket = QComboBox()
        self.cmb_task_bucket.addItems(["personal", "work", "study"])
        # Row verbs on a task are glyphs: they act on the selected line, so
        # three full boxes competed with the field you actually type in.
        self.btn_add_task = primary_button("Add task")
        self.btn_toggle_task = icon_button("✓", "Tick the selected task off (or put it back)")
        self.btn_remove_task = icon_button("🗑", "Delete the selected task")
        top_row.addWidget(self.ed_task_title, 1)
        top_row.addWidget(self.cmb_task_bucket)
        top_row.addWidget(self.btn_add_task)
        top_row.addWidget(self.btn_toggle_task)
        top_row.addWidget(self.btn_remove_task)
        self.ed_task_title.returnPressed.connect(self._add_task)
        l.addLayout(top_row)
        self.tasks_list = QListWidget()
        self.tasks_list.setObjectName("CafeList")
        l.addWidget(self.tasks_list, 1)
        self.btn_add_task.clicked.connect(self._add_task)
        self.btn_toggle_task.clicked.connect(self._toggle_task)
        self.btn_remove_task.clicked.connect(self._remove_task)
        return w

    def _refresh_tasks(self):
        self.tasks_list.clear()
        for item in life_service.load_tasks(self.base_dir):
            prefix = "[x]" if item.get("completed") else "[ ]"
            due = _format_ts(int(item.get("due_at", 0) or 0)) if int(item.get("due_at", 0) or 0) else item.get("bucket", "")
            row = QListWidgetItem(f"{prefix} {item.get('title', '')} · {due}")
            row.setData(Qt.UserRole, item.get("id", ""))
            self.tasks_list.addItem(row)
        if self.tasks_list.count() == 0:
            hint = components.hint_list_item("No tasks yet — type a title above and press Add task", "○")
            hint.setFlags(Qt.NoItemFlags)
            self.tasks_list.addItem(hint)

    def _add_task(self):
        title = self.ed_task_title.text().strip()
        if not title:
            return
        life_service.add_task(self.base_dir, title, bucket=self.cmb_task_bucket.currentText())
        self.ed_task_title.clear()
        self._refresh_tasks()
        self._refresh_overview()

    def _toggle_task(self):
        item = self.tasks_list.currentItem()
        if item and item.data(Qt.UserRole):
            life_service.toggle_task(self.base_dir, item.data(Qt.UserRole))
            self._refresh_tasks()
            self._refresh_overview()

    def _remove_task(self):
        item = self.tasks_list.currentItem()
        if item and item.data(Qt.UserRole):
            life_service.remove_task(self.base_dir, item.data(Qt.UserRole))
            self._refresh_tasks()
            self._refresh_overview()

    def _build_calendar_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(6)
        l.addWidget(components.page_header("Calendar", "Events and your day view"))
        row = QHBoxLayout()
        # Adding is the action; deleting one event is a row chore, and the two
        # .ics verbs are a pair of icon buttons instead of two more full boxes.
        self.btn_add_event = primary_button("Add event")
        self.btn_today = ghost_button("Today", "Jump back to today")
        self.btn_ics_import = ghost_button("Import .ics", "Import events from an .ics file")
        self.btn_ics_export = ghost_button("Export .ics", "Export your calendar as .ics")
        row.addWidget(self.btn_add_event)
        row.addWidget(self.btn_today)
        row.addWidget(self.btn_ics_import)
        row.addWidget(self.btn_ics_export)
        row.addWidget(more_menu((("🗑  Delete the selected event", self._remove_event),), tooltip="Calendar chores"))
        row.addStretch(1)
        l.addLayout(row)
        body = QHBoxLayout()
        body.setSpacing(6)
        left_card = QFrame()
        left_card.setObjectName("SectionCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)
        self.calendar_widget = QCalendarWidget()
        self.calendar_widget.setGridVisible(False)
        self.calendar_widget.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar_widget.setSelectedDate(QDate.currentDate())
        # Native Qt calendar chevrons can retain white icons on light themes.
        # Text-only navigation follows the same foreground/focus tokens as chrome.
        for name, glyph, label in (("qt_calendar_prevmonth", "‹", "Previous month"), ("qt_calendar_nextmonth", "›", "Next month")):
            button = self.calendar_widget.findChild(QtWidgets.QToolButton, name)
            if button is not None:
                button.setIcon(QIcon())
                button.setText(glyph)
                button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.setAccessibleName(label)
                button.setToolTip(label)
                button.setMinimumSize(34, 34)
        left_layout.addWidget(self.calendar_widget)
        self.lbl_calendar_hint = QLabel("")
        self.lbl_calendar_hint.setWordWrap(True)
        self.lbl_calendar_hint.setObjectName("MutedLabel")
        left_layout.addWidget(self.lbl_calendar_hint)
        body.addWidget(left_card, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        self.lbl_calendar_day = QLabel("")
        self.lbl_calendar_day.setFont(components._font(15, components.WEIGHT_BOLD))
        right_col.addWidget(self.lbl_calendar_day)

        self.day_events_list = QListWidget()
        self.day_events_list.setObjectName("CafeList")
        right_col.addWidget(self._wrap_list_card("Events on selected day", "Click a date to see its events", self.day_events_list), 1)

        self.calendar_list = QListWidget()
        self.calendar_list.setObjectName("CafeList")
        right_col.addWidget(self._wrap_list_card("Upcoming", "Across all events", self.calendar_list), 1)
        body.addLayout(right_col, 1)
        l.addLayout(body, 1)
        self.btn_add_event.clicked.connect(self._add_event)
        self.btn_today.clicked.connect(self._jump_calendar_today)
        self.btn_ics_import.clicked.connect(self._import_ics)
        self.btn_ics_export.clicked.connect(self._export_ics)
        self.calendar_widget.selectionChanged.connect(self._refresh_calendar)
        return w

    def _refresh_calendar(self):
        events = life_service.load_events(self.base_dir)
        selected_date = self.calendar_widget.selectedDate() if hasattr(self, "calendar_widget") else QDate.currentDate()
        selected_key = selected_date.toString("yyyy-MM-dd")
        events_by_day = {}
        for item in events:
            ts = int(item.get("starts_at", 0) or 0)
            date_key = time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""
            if not date_key:
                continue
            events_by_day.setdefault(date_key, []).append(item)

        if hasattr(self, "calendar_widget"):
            for date_key in getattr(self, "_calendar_marked_dates", set()):
                year, month, day = [int(part) for part in date_key.split("-")]
                self.calendar_widget.setDateTextFormat(QDate(year, month, day), QTextCharFormat())
            # Theme-aware event marks: v6.4 hard-coded beige/ink on every theme.
            p = theme.palette()
            accent_fmt = QTextCharFormat()
            accent_fmt.setBackground(QColor(p["ACCENT"]))
            accent_fmt.setForeground(QColor(p["TEXT_ON_ACCENT"]))
            accent_fmt.setFontWeight(QFont.DemiBold)
            for date_key in events_by_day:
                year, month, day = [int(part) for part in date_key.split("-")]
                self.calendar_widget.setDateTextFormat(QDate(year, month, day), accent_fmt)
            self._calendar_marked_dates = set(events_by_day.keys())

        day_items = events_by_day.get(selected_key, [])
        self.lbl_calendar_day.setText(selected_date.toString("dddd, MMMM d"))
        if day_items:
            self.lbl_calendar_hint.setText(f"{len(day_items)} event(s) on this day")
        else:
            self.lbl_calendar_hint.setText("No events on this day yet. Use Add event to place one on the selected date.")

        self.day_events_list.clear()
        for item in day_items:
            label = time.strftime("%H:%M", time.localtime(int(item.get("starts_at", 0) or 0)))
            row = QListWidgetItem(f"{label}  {item.get('title', '')}")
            row.setData(Qt.UserRole, item.get("id", ""))
            self.day_events_list.addItem(row)
        if self.day_events_list.count() == 0:
            placeholder = QListWidgetItem("No events scheduled")
            placeholder.setFlags(Qt.NoItemFlags)
            self.day_events_list.addItem(placeholder)
        self.calendar_list.clear()
        for item in [event for event in events if int(event.get("starts_at", 0) or 0) >= int(time.time())][:20]:
            row = QListWidgetItem(f"{item.get('title', '')} · {_format_ts(int(item.get('starts_at', 0) or 0))}")
            row.setData(Qt.UserRole, item.get("id", ""))
            self.calendar_list.addItem(row)
        if not self.calendar_list.count():
            self.calendar_list.addItem(components.hint_list_item("No upcoming events", "○"))

    def _add_event(self):
        title, ok = QInputDialog.getText(self, "Add event", "Event title:")
        if not ok or not (title or "").strip():
            return
        selected_date = self.calendar_widget.selectedDate() if hasattr(self, "calendar_widget") else QDate.currentDate()
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Event date & time - {app_version.APP_NAME}")
        dialog.setStyleSheet(self._dialog_stylesheet())
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Start date and time"))
        start = QtWidgets.QDateTimeEdit(QtCore.QDateTime(selected_date, QtCore.QTime(9, 0)))
        start.setCalendarPopup(True)
        start.setDisplayFormat("ddd, d MMM yyyy · HH:mm")
        start.setAccessibleName("Event start")
        layout.addWidget(start)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QDialog.Accepted:
            return
        starts_at = start.dateTime().toSecsSinceEpoch()
        life_service.add_event(self.base_dir, title.strip(), starts_at)
        self._refresh_calendar()
        self._refresh_overview()

    def _remove_event(self):
        item = self.day_events_list.currentItem() if hasattr(self, "day_events_list") else None
        if not item or not item.data(Qt.UserRole):
            item = self.calendar_list.currentItem()
        if not item or not item.data(Qt.UserRole):
            return
        if QMessageBox.question(self, "Calendar", "Delete this event?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        life_service.remove_event(self.base_dir, item.data(Qt.UserRole))
        self._refresh_calendar()
        self._refresh_overview()

    def _jump_calendar_today(self):
        self.calendar_widget.setSelectedDate(QDate.currentDate())
        self._refresh_calendar()

    def select_event(self, event_id: str):
        for event in life_service.load_events(self.base_dir):
            if event.get("id") != event_id:
                continue
            ts = int(event.get("starts_at", 0) or 0)
            if ts:
                dt = time.localtime(ts)
                self.calendar_widget.setSelectedDate(QDate(dt.tm_year, dt.tm_mon, dt.tm_mday))
            self._refresh_calendar()
            for widget in (self.day_events_list, self.calendar_list):
                for index in range(widget.count()):
                    item = widget.item(index)
                    if item.data(Qt.UserRole) == event_id:
                        widget.setCurrentItem(item)
                        return

    def _build_boards_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(6)
        l.addWidget(components.page_header("Idea Boards", "Sticky cards, pan, and draw"))
        # Eleven equal boxes in one row became: the verb you came for, three
        # mode chips (they are a state, not an action), the pen settings, and a
        # menu holding the round chores (new/delete board, clear ink/links, save).
        row = QHBoxLayout()
        self.btn_add_card = primary_button("Add sticky")
        self.btn_mode_pan = components.chip("Pan")
        self.btn_mode_draw = components.chip("Draw")
        self.btn_mode_link = components.chip("Link")
        self.cmb_board_tool = QComboBox()
        for tool in BoardView.TOOLS:
            self.cmb_board_tool.addItem(tool.capitalize(), tool)
        self.cmb_board_tool.setAccessibleName("Drawing tool")
        self.cmb_board_tool.setToolTip("Pen, pencil, translucent marker, stroke eraser and shapes")
        self.cmb_pen_color = QComboBox()
        for label, color in (("Ink", "#292d32"), ("Espresso", "#6f4e37"), ("Coral", "#c75b52"), ("Honey", "#c89331"), ("Forest", "#42795c"), ("Ocean", "#3e799f"), ("Lilac", "#8462b1"), ("White", "#ffffff")):
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(color))
            self.cmb_pen_color.addItem(QIcon(pixmap), label, color)
        self.cmb_pen_color.setAccessibleName("Pen color preset")
        self.btn_pen_custom = ghost_button("Color…", "Choose any drawing color")
        self.cmb_pen_width = QComboBox()
        for label, value in (("1 px", 1.0), ("3 px", 3.0), ("6 px", 6.0), ("12 px", 12.0), ("24 px", 24.0)):
            self.cmb_pen_width.addItem(label, value)
        self.cmb_pen_width.setCurrentIndex(1)
        self.cmb_pen_width.setAccessibleName("Stroke size")
        self.spin_board_opacity = QSpinBox()
        self.spin_board_opacity.setRange(5, 100)
        self.spin_board_opacity.setValue(100)
        self.spin_board_opacity.setSuffix("%")
        self.spin_board_opacity.setAccessibleName("Ink opacity")
        self.btn_canvas_color = ghost_button("Paper…", "Choose the canvas background color")
        self.btn_board_undo = ghost_button("Undo", "Undo board change (Ctrl+Z on canvas)")
        self.btn_board_redo = ghost_button("Redo", "Redo board change (Ctrl+Shift+Z on canvas)")
        self.board_mode_group = QButtonGroup(self)
        self.board_mode_group.setExclusive(True)
        self.board_mode_group.addButton(self.btn_mode_pan)
        self.board_mode_group.addButton(self.btn_mode_draw)
        self.board_mode_group.addButton(self.btn_mode_link)
        row.addWidget(self.btn_add_card)
        row.addWidget(self.btn_mode_pan)
        row.addWidget(self.btn_mode_draw)
        row.addWidget(self.btn_mode_link)
        row.addWidget(self.btn_board_undo)
        row.addWidget(self.btn_board_redo)
        row.addStretch(1)
        row.addWidget(
            more_menu(
                (
                    ("New board…", self._add_board),
                    ("Delete this board", self._delete_board),
                    (None, None),
                    ("Clear the ink on this board", self._clear_board_ink),
                    ("Clear every link", self._clear_board_links),
                    ("Save board", self._save_current_board_positions),
                    ("Save canvas as a new board…", self._save_board_copy),
                ),
                tooltip="Board chores: create, delete, clear, save",
            )
        )
        l.addLayout(row)
        # A second short tool row keeps creation/navigation distinct from ink.
        tools = QHBoxLayout()
        tools.setSpacing(6)
        for label, control in (("Tool", self.cmb_board_tool), ("Ink", self.cmb_pen_color), ("Size", self.cmb_pen_width), ("Opacity", self.spin_board_opacity)):
            tools.addWidget(QLabel(label))
            tools.addWidget(control)
        tools.addWidget(self.btn_pen_custom)
        tools.addWidget(self.btn_canvas_color)
        tools.addStretch(1)
        self.btn_board_zoom_out = ghost_button("−", "Zoom out")
        self.btn_board_zoom_reset = ghost_button("100%", "Reset canvas zoom")
        self.btn_board_zoom_in = ghost_button("+", "Zoom in")
        self.btn_board_fit = ghost_button("Fit", "Fit the entire canvas")
        toolbar = QWidget()
        toolbar.setLayout(tools)
        self._board_tools_scroll = QScrollArea()
        self._board_tools_scroll.setWidget(toolbar)
        self._board_tools_scroll.setWidgetResizable(True)
        self._board_tools_scroll.setFrameShape(QFrame.NoFrame)
        self._board_tools_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._board_tools_scroll.setFixedHeight(58)
        l.addWidget(self._board_tools_scroll)
        self.lbl_board_hint = QLabel("Select a board, then draw. Ctrl+wheel to zoom · Space or middle-drag to pan.")
        self.lbl_board_hint.setWordWrap(True)
        self.lbl_board_hint.setObjectName("MutedLabel")
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(self.lbl_board_hint, 1)
        for button in (self.btn_board_zoom_out, self.btn_board_zoom_reset, self.btn_board_zoom_in, self.btn_board_fit):
            zoom_row.addWidget(button)
        l.addLayout(zoom_row)

        split = QSplitter(Qt.Horizontal)
        self._boards_splitter = split
        self.boards_list = QListWidget()
        self.boards_list.setObjectName("CafeList")
        self.boards_list.setMinimumWidth(90)
        self.boards_list.setMaximumWidth(240)
        self.boards_list.currentItemChanged.connect(self._load_selected_board)
        split.addWidget(self.boards_list)
        self.board_scene = QGraphicsScene(self)
        self.board_scene.setSceneRect(0, 0, 2200, 1400)
        # Paper is white by default, independent from the application theme.
        self.board_scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        self.board_view = BoardView()
        self.board_view.setScene(self.board_scene)
        self.board_view.set_history_callbacks(self._board_snapshot, self._restore_board_snapshot)
        self.board_view.setEnabled(False)
        self._board_autosave = QTimer(self)
        self._board_autosave.setSingleShot(True)
        self._board_autosave.setInterval(700)
        self._board_autosave.timeout.connect(lambda: self._save_current_board_positions(notify=False))
        self.board_view.stroke_finished.connect(self._board_autosave.start)
        split.addWidget(self.board_view)
        split.setChildrenCollapsible(True)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 860])
        l.addWidget(split, 1)

        self.btn_add_card.clicked.connect(self._add_board_card)
        self.btn_mode_pan.clicked.connect(lambda: self._set_board_mode("pan"))
        self.btn_mode_draw.clicked.connect(lambda: self._set_board_mode("draw"))
        self.btn_mode_link.clicked.connect(lambda: self._set_board_mode("link"))
        self.cmb_pen_color.currentIndexChanged.connect(self._apply_board_pen)
        self.cmb_pen_width.currentIndexChanged.connect(self._apply_board_pen)
        self.spin_board_opacity.valueChanged.connect(self._apply_board_pen)
        self.cmb_board_tool.currentIndexChanged.connect(self._select_board_tool)
        self.btn_pen_custom.clicked.connect(self._choose_pen_color)
        self.btn_canvas_color.clicked.connect(self._choose_canvas_color)
        self.btn_board_undo.clicked.connect(self.board_view.undo)
        self.btn_board_redo.clicked.connect(self.board_view.redo)
        self.btn_board_undo.setEnabled(False)
        self.btn_board_redo.setEnabled(False)
        self.board_view.history_changed.connect(lambda undo, redo: (self.btn_board_undo.setEnabled(undo), self.btn_board_redo.setEnabled(redo)))
        self.btn_board_zoom_out.clicked.connect(lambda: self.board_view.set_zoom(self.board_view.transform().m11() / 1.2))
        self.btn_board_zoom_in.clicked.connect(lambda: self.board_view.set_zoom(self.board_view.transform().m11() * 1.2))
        self.btn_board_zoom_reset.clicked.connect(lambda: self.board_view.set_zoom(1.0))
        self.btn_board_fit.clicked.connect(self.board_view.fit_canvas)
        self.board_view.zoom_changed.connect(lambda value: self.btn_board_zoom_reset.setText(f"{value}%"))
        self.board_view.link_created.connect(self._add_board_edge)
        self.btn_mode_pan.setChecked(True)
        self._apply_board_pen()
        return w

    def _refresh_boards(self):
        current = self.current_board_id
        if current and not self._save_current_board_positions(notify=False):
            return
        boards = life_service.load_boards(self.base_dir)
        self.boards_list.blockSignals(True)
        self.boards_list.clear()
        for board in boards:
            item = QListWidgetItem(board.get("title", "Untitled board"))
            item.setData(Qt.UserRole, board.get("id", ""))
            self.boards_list.addItem(item)
        self.boards_list.blockSignals(False)
        if current and current == getattr(self, "_board_loaded_id", None):
            # Refresh metadata without destroying the live undo stack/canvas.
            self.boards_list.blockSignals(True)
            for index in range(self.boards_list.count()):
                if self.boards_list.item(index).data(Qt.UserRole) == current:
                    self.boards_list.setCurrentRow(index)
                    break
            self.boards_list.blockSignals(False)
        elif current:
            self.open_life_item("board", current)
        elif self.boards_list.count() > 0 and self.boards_list.currentRow() < 0:
            self.boards_list.setCurrentRow(0)
        else:
            self._load_selected_board(None, None)

    def _add_board(self):
        title, ok = QInputDialog.getText(self, "New board", "Board title:")
        if not ok:
            return
        if not self._save_current_board_positions(notify=False):
            return
        board = life_service.add_board(self.base_dir, title.strip() or "Idea board")
        self.board_view.cancel_gesture()
        self.board_view._clear_link_start()
        self.current_board_id = None
        self.board_scene.clear()
        self.board_view.set_background("#ffffff")
        self.board_view.reset_history()
        self.current_board_id = board["id"]
        self._refresh_boards()
        self._refresh_overview()

    def _save_board_copy(self):
        if not self.current_board_id:
            return
        title, ok = QInputDialog.getText(self, "Save board copy", "New board title:", text="Idea board copy")
        if not ok:
            return
        snapshot = self._board_snapshot()
        try:
            board = life_service.add_board(self.base_dir, title.strip() or "Idea board copy")
            board.update(snapshot)
            life_service.update_board(self.base_dir, board)
        except (OSError, ValueError, RuntimeError) as error:
            self.lbl_board_hint.setText(f"Copy not saved — your canvas is retained: {error}")
            return
        self._board_autosave.stop()
        self.current_board_id = board["id"]
        self._board_loaded_id = board["id"]
        self._board_saved_id = board["id"]
        self._board_disk_snapshot = copy.deepcopy(snapshot)
        self._refresh_boards()
        self.lbl_board_hint.setText("Saved as a separate board · the original is unchanged")

    def _delete_board(self):
        if not self.current_board_id:
            return
        confirm = QMessageBox.question(
            self,
            "Delete board",
            "Delete this board with all its cards, strokes and links?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        life_service.remove_board(self.base_dir, self.current_board_id)
        self._board_autosave.stop()
        self.board_view.cancel_gesture()
        self.board_view._clear_link_start()
        self.current_board_id = None
        self._refresh_boards()
        self._refresh_overview()

    def _load_selected_board(self, current, _previous):
        previous_board_id = self.current_board_id
        if previous_board_id and not self._save_current_board_positions(notify=False):
            self.boards_list.blockSignals(True)
            for index in range(self.boards_list.count()):
                if self.boards_list.item(index).data(Qt.UserRole) == previous_board_id:
                    self.boards_list.setCurrentRow(index)
                    break
            self.boards_list.blockSignals(False)
            return
        selected_id = current.data(Qt.UserRole) if current else None
        if selected_id and selected_id == previous_board_id and selected_id == getattr(self, "_board_loaded_id", None):
            return  # Deep links to the open board must not wipe Undo.
        # Cancel any pending autosave: it must not fire against the *new*
        # board after a quick switch (v6.4 saved the wrong board's positions).
        self._board_autosave.stop()
        self.board_view.cancel_gesture()
        self.board_view._clear_link_start()
        self.board_scene.clear()
        self.current_board_id = current.data(Qt.UserRole) if current else None
        self._board_loaded_id = self.current_board_id
        self.board_view.reset_history()
        self.board_view.setEnabled(bool(self.current_board_id))
        self.btn_add_card.setEnabled(bool(self.current_board_id))
        if not self.current_board_id:
            self.lbl_board_hint.setText("Create a board to start sketching ideas, tasks, or study maps.")
            return
        boards = life_service.load_boards(self.base_dir)
        for board in boards:
            if board.get("id") == self.current_board_id:
                self.board_view.set_background(board.get("background", "#ffffff"))
                card_by_id = {}
                for node in board.get("nodes", []):
                    item = StickyCardItem(node)
                    card_by_id[node.get("id")] = item
                    self.board_scene.addItem(item)
                for stroke in board.get("strokes", []):
                    self.board_scene.addItem(InkStrokeItem(stroke))
                for edge in board.get("edges", []):
                    from_item = card_by_id.get(edge.get("from"))
                    to_item = card_by_id.get(edge.get("to"))
                    if from_item and to_item:
                        self.board_scene.addItem(EdgeItem(edge, from_item, to_item))
                self._board_saved_id = self.current_board_id
                self._board_disk_snapshot = {key: copy.deepcopy(board.get(key, "#ffffff" if key == "background" else [])) for key in ("nodes", "strokes", "edges", "background")}
                self.board_view.fit_canvas()
                self.lbl_board_hint.setText(
                    f"{len(board.get('nodes', []))} sticky cards · {len(board.get('edges', []))} links · {len(board.get('strokes', []))} ink strokes"
                )
                break

    def _add_board_card(self):
        if not self.current_board_id:
            QMessageBox.information(self, "Boards", "Create or select a board first.")
            return
        title, ok = QInputDialog.getText(self, "New sticky", "Card title:")
        if not ok:
            return
        before = self._board_snapshot()
        center = self.board_view.mapToScene(self.board_view.viewport().rect().center())
        import uuid
        node = {"id": uuid.uuid4().hex, "title": title or "Card", "kind": "sticky", "payload": "", "x": max(0, min(1980, center.x() - 110)), "y": max(0, min(1280, center.y() - 60)), "color": "#f5e4ad"}
        self.board_scene.addItem(StickyCardItem(node))
        self.board_view.record_change(before)
        self._save_current_board_positions(notify=False)

    def _set_board_mode(self, mode: str):
        self.board_view.set_mode(mode)
        if mode == "draw":
            self.board_view.set_tool(self.cmb_board_tool.currentData())
        self.btn_mode_pan.setChecked(mode == "pan")
        self.btn_mode_draw.setChecked(mode == "draw")
        self.btn_mode_link.setChecked(mode == "link")
        if mode == "draw":
            self.lbl_board_hint.setText("Draw mode is on. Drag on empty canvas to sketch. Sticky cards remain draggable.")
        elif mode == "link":
            self.lbl_board_hint.setText("Link mode: click a sticky card, then another, to draw a connection. Click empty canvas to cancel.")
        elif self.current_board_id:
            self.lbl_board_hint.setText("Pan mode · drag the canvas or cards · Ctrl+wheel to zoom.")
        else:
            self.lbl_board_hint.setText("Create a board to start sketching ideas, tasks, or study maps.")

    def _apply_board_pen(self):
        color = self.cmb_pen_color.currentData() or "#6f4e37"
        width = float(self.cmb_pen_width.currentData() or 3.0)
        self.board_view.set_pen(color, width, self.spin_board_opacity.value() / 100)
        self.btn_pen_custom.setText(f"Color {color.upper()}")
        self.btn_pen_custom.setToolTip(f"Current ink: {color.upper()} · choose a custom color")

    def _select_board_tool(self):
        self._set_board_mode("draw")

    def _choose_pen_color(self):
        color = QColorDialog.getColor(QColor(self.board_view.pen_color), self, "Drawing color")
        if color.isValid():
            idx = self.cmb_pen_color.findData(color.name())
            if idx < 0:
                self.cmb_pen_color.addItem(color.name().upper(), color.name())
                idx = self.cmb_pen_color.count() - 1
            self.cmb_pen_color.setCurrentIndex(idx)
            self._apply_board_pen()

    def _choose_canvas_color(self):
        if not self.current_board_id:
            return
        color = QColorDialog.getColor(QColor(self.board_view.background_color), self, "Canvas / paper color")
        if color.isValid():
            before = self._board_snapshot()
            self.board_view.set_background(color.name())
            self.board_view.record_change(before)

    def _board_snapshot(self):
        nodes, strokes, edges = [], [], []
        for item in reversed(self.board_scene.items()):
            if isinstance(item, StickyCardItem):
                nodes.append(dict(item.node, x=item.pos().x(), y=item.pos().y()))
            elif isinstance(item, InkStrokeItem):
                strokes.append(copy.deepcopy(item.stroke))
            elif isinstance(item, EdgeItem):
                edges.append(dict(item.edge))
        return {"nodes": nodes, "strokes": strokes, "edges": edges, "background": self.board_view.background_color}

    def _restore_board_snapshot(self, snapshot):
        self.board_view.cancel_gesture()
        self.board_view._clear_link_start()
        self.board_scene.clear()
        self.board_view.set_background(snapshot.get("background", "#ffffff"))
        cards = {}
        for node in snapshot["nodes"]:
            card = StickyCardItem(node)
            cards[node["id"]] = card
            self.board_scene.addItem(card)
        for stroke in snapshot["strokes"]:
            self.board_scene.addItem(InkStrokeItem(stroke))
        for edge in snapshot["edges"]:
            if edge.get("from") in cards and edge.get("to") in cards:
                self.board_scene.addItem(EdgeItem(edge, cards[edge["from"]], cards[edge["to"]]))

    def _clear_board_ink(self):
        before = self._board_snapshot()
        removed = False
        for item in list(self.board_scene.items()):
            if isinstance(item, InkStrokeItem):
                self.board_scene.removeItem(item)
                removed = True
        if removed:
            self.board_view.record_change(before)
            self.lbl_board_hint.setText("Ink strokes cleared. Sticky cards are still intact.")
            self._save_current_board_positions(notify=False)

    def _clear_board_links(self):
        before = self._board_snapshot()
        removed = False
        for item in list(self.board_scene.items()):
            if isinstance(item, EdgeItem):
                for card in (item.from_item, item.to_item):
                    if item in card._edges:
                        card._edges.remove(item)
                self.board_scene.removeItem(item)
                removed = True
        if removed:
            self.board_view.record_change(before)
            self.lbl_board_hint.setText("Links cleared. Sticky cards and ink are still intact.")
            self._save_current_board_positions(notify=False)

    def _add_board_edge(self, from_id, to_id):
        if not self.current_board_id or not from_id or not to_id or from_id == to_id:
            return
        card_by_id = {}
        for item in self.board_scene.items():
            if isinstance(item, StickyCardItem):
                card_by_id[item.node.get("id")] = item
        from_item = card_by_id.get(from_id)
        to_item = card_by_id.get(to_id)
        if not from_item or not to_item:
            return
        for item in self.board_scene.items():
            if isinstance(item, EdgeItem):
                pair = {item.edge.get("from"), item.edge.get("to")}
                if pair == {from_id, to_id}:
                    return
        edge = {"id": str(int(time.time() * 1000)), "from": from_id, "to": to_id, "color": "#a36a3c"}
        before = self._board_snapshot()
        self.board_scene.addItem(EdgeItem(edge, from_item, to_item))
        self.board_view.record_change(before)
        self.lbl_board_hint.setText("Linked two cards. Drag either card and the line follows.")
        self._save_current_board_positions(notify=False)

    def _save_current_board_positions(self, notify: bool = True):
        if not self.current_board_id:
            return True
        try:
            board = next((board for board in life_service.load_boards(self.base_dir) if board.get("id") == self.current_board_id), None)
            if board is None:
                raise ValueError("The open board was removed outside this window")
            snapshot = self._board_snapshot()
            disk_snapshot = {key: board.get(key, "#ffffff" if key == "background" else []) for key in snapshot}
            if disk_snapshot == snapshot:
                self._board_saved_id = self.current_board_id
                self._board_disk_snapshot = copy.deepcopy(snapshot)
                return True
            if getattr(self, "_board_saved_id", None) == self.current_board_id and disk_snapshot != self._board_disk_snapshot:
                raise ValueError("Another window changed this board; your local canvas is kept, not overwritten")
            board.update(snapshot)
            if life_service.update_board(self.base_dir, board) is None:
                raise ValueError("The board disappeared while saving")
            self._board_saved_id = self.current_board_id
            self._board_disk_snapshot = copy.deepcopy(snapshot)
            self.lbl_board_hint.setText(f"Saved locally · {len(snapshot['nodes'])} cards · {len(snapshot['strokes'])} strokes · Ctrl+wheel to zoom")
            if notify:
                self._flash("Board saved locally")
            return True
        except (OSError, ValueError, RuntimeError) as error:
            self.lbl_board_hint.setText(f"Board not saved — your canvas is retained. Retry Save: {error}")
            return False

    def _build_files_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(6)
        l.addWidget(components.page_header("Files", "Browse files in your personal root"))
        search_row = QHBoxLayout()
        self.ed_file_search = QLineEdit()
        self.ed_file_search.setPlaceholderText("Search files in personal root...")
        self.btn_file_refresh = QPushButton("Refresh")
        search_row.addWidget(self.ed_file_search, 1)
        search_row.addWidget(self.btn_file_refresh)
        l.addLayout(search_row)
        self.lbl_root = QLabel("")
        self.lbl_root.setObjectName("MutedLabel")
        l.addWidget(self.lbl_root)
        self.files_list = QListWidget()
        self.files_list.setObjectName("CafeList")
        self.files_list.itemDoubleClicked.connect(self._open_file_item)
        l.addWidget(self.files_list, 1)
        self.ed_file_search.textChanged.connect(self._schedule_files_refresh)
        self.btn_file_refresh.clicked.connect(self._refresh_files)
        self._files_search_timer = QTimer(self)
        self._files_search_timer.setSingleShot(True)
        self._files_search_timer.setInterval(250)
        self._files_search_timer.timeout.connect(self._refresh_files)
        return w

    def _schedule_files_refresh(self):
        self._files_search_timer.start()

    def _choose_root(self):
        current = prefs.get_personal_root(self.base_dir) or ""
        chosen = QFileDialog.getExistingDirectory(self, "Choose personal root", current or os.path.expanduser("~"))
        if chosen:
            prefs.set_personal_root(self.base_dir, chosen)
            self._refresh_files()

    def _refresh_files(self):
        query = self.ed_file_search.text().strip() if hasattr(self, "ed_file_search") else ""
        root = prefs.get_personal_root(self.base_dir) or ""
        self.lbl_root.setText("Root: " + (root if root else "(not set)"))
        self.files_list.clear()
        for entry in personal_service.list_root_entries(self.base_dir, query):
            label = ("[DIR] " if entry["kind"] == "dir" else "[FILE] ") + entry["name"]
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry["path"])
            self.files_list.addItem(item)

    def _open_file_item(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path:
            try:
                os.startfile(path)
            except Exception:
                QMessageBox.information(self, "Files", "Cannot open:\n" + str(path))

    def _build_sites_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(12, 10, 12, 12)
        l.setSpacing(6)
        self.sites_header = components.page_header("Sites", "Quick links and site preview")
        l.addWidget(self.sites_header)

        top_bar = QWidget()
        row = QHBoxLayout(top_bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.btn_add_site = QPushButton("Add site")
        self.btn_remove_site = QPushButton("Delete site")
        self.btn_open_site = QPushButton("Open in Browser")
        self.btn_site_ai = QPushButton("Ask AI")
        self.btn_bundled_sites = QPushButton("Include bundled sites")
        self.btn_bundled_sites.setCheckable(True)
        self.btn_bundled_sites.setChecked(prefs.get_show_bundled_sites(self.base_dir))
        self.btn_bundled_sites.setToolTip(
            "Show the bundled project sites (Management Hub, PersonalFrequency, …) alongside your own. "
            "Off = only sites you added yourself."
        )
        self.chk_site_preview = QCheckBox("Live preview")
        self.chk_site_preview.setToolTip("Render the selected site here (off = instant, no background load)")
        self.chk_site_preview.setChecked(False)
        row.addWidget(self.btn_add_site)
        row.addWidget(self.btn_remove_site)
        row.addWidget(self.btn_open_site)
        row.addWidget(self.btn_site_ai)
        row.addStretch(1)
        l.addWidget(top_bar)
        preview_options = QHBoxLayout()
        preview_options.addWidget(self.btn_bundled_sites)
        preview_options.addWidget(self.chk_site_preview)
        preview_options.addStretch(1)
        l.addLayout(preview_options)
        self._sites_top_bar = top_bar

        self.lbl_sites_summary = QLabel("Personal sites stay separate from shared browser bookmarks.")
        self.lbl_sites_summary.setObjectName("MutedLabel")
        l.addWidget(self.lbl_sites_summary)

        split = QSplitter(Qt.Horizontal)
        left_card = QFrame()
        left_card.setObjectName("SectionCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(5)
        left_layout.addWidget(QLabel("Saved personal sites"))
        self.sites_list = QListWidget()
        self.sites_list.setObjectName("CafeList")
        self.sites_list.currentItemChanged.connect(self._preview_site_selection)
        self.sites_list.itemDoubleClicked.connect(self._open_site_item)
        left_layout.addWidget(self.sites_list, 1)
        split.addWidget(left_card)
        self._sites_left_card = left_card

        right_card = QFrame()
        right_card.setObjectName("SectionCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(5)
        title_row = QHBoxLayout()
        self.lbl_site_title = QLabel("Site preview")
        self.lbl_site_title.setObjectName("SectionTitle")
        title_row.addWidget(self.lbl_site_title)
        title_row.addStretch(1)
        self.btn_full_preview = QPushButton("Full preview")
        self.btn_full_preview.setCheckable(True)
        self.btn_full_preview.setToolTip("Expand the preview: hide the toolbars and site list")
        title_row.addWidget(self.btn_full_preview)
        right_layout.addLayout(title_row)
        self.lbl_site_url = QLabel("Select a site to preview it here.")
        self.lbl_site_url.setObjectName("MutedLabel")
        self.lbl_site_url.setWordWrap(True)
        right_layout.addWidget(self.lbl_site_url)
        self.site_preview_stack = QStackedWidget()
        placeholder = QWidget()
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(12, 12, 12, 12)
        placeholder_layout.setSpacing(6)
        self.lbl_site_placeholder_title = QLabel("No site selected")
        self.lbl_site_placeholder_title.setFont(QFont("Georgia", 18, QFont.Bold))
        self.lbl_site_placeholder_detail = QLabel("Choose a saved personal site on the left to preview it, or open it directly in Browser.")
        self.lbl_site_placeholder_detail.setWordWrap(True)
        self.lbl_site_placeholder_detail.setObjectName("MutedLabel")
        placeholder_layout.addStretch(1)
        placeholder_layout.addWidget(self.lbl_site_placeholder_title)
        placeholder_layout.addWidget(self.lbl_site_placeholder_detail)
        placeholder_layout.addStretch(1)
        self.site_preview_stack.addWidget(placeholder)
        # The WebEngine view is built lazily on first use: constructing it at
        # window startup spawned a Chromium renderer even for users who never
        # open the Sites page (v6.4 memory/startup cost).
        self.site_view = None
        self._placeholder_index = self.site_preview_stack.indexOf(placeholder)
        right_layout.addWidget(self.site_preview_stack, 1)
        self._site_loaded_url = ""
        split.addWidget(right_card)
        split.setChildrenCollapsible(True)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 960])
        l.addWidget(split, 1)
        self._sites_splitter = split

        self.btn_add_site.clicked.connect(self._add_site)
        self.btn_remove_site.clicked.connect(self._remove_site)
        self.btn_open_site.clicked.connect(self._open_selected_site_in_browser)
        self.btn_site_ai.clicked.connect(self._ask_ai_about_site)
        self.btn_bundled_sites.toggled.connect(self._on_bundled_sites_toggled)
        self.chk_site_preview.toggled.connect(self._on_site_preview_toggled)
        self.btn_full_preview.toggled.connect(self._on_full_preview_toggled)
        if not self.embedded:
            self.btn_site_ai.hide()
        return w

    def _ensure_site_view(self):
        """Build the WebEngine preview on first use (lazy)."""
        if getattr(self, "site_view", None) is None:
            self.site_view = self._build_site_view()
            self.site_preview_stack.addWidget(self.site_view)
        return self.site_view

    def _bundled_site_urls(self) -> set:
        """URLs the app seeds itself (bundled local + deployed chain)."""
        urls = set()
        for site in app_paths.bundled_sites(self.app_dir) + app_paths.chain_remote_sites(self.app_dir):
            url = (site.get("url") or "").strip()
            if url:
                urls.add(url)
        return urls

    def _refresh_sites(self):
        sites = prefs.get_personal_sites(self.base_dir)
        if not prefs.get_show_bundled_sites(self.base_dir):
            bundled = self._bundled_site_urls()
            sites = [s for s in sites if (s.get("url") or "").strip() not in bundled]
        current_url = ""
        if self.sites_list.currentItem():
            current_url = self.sites_list.currentItem().data(Qt.UserRole) or ""
        self.sites_list.blockSignals(True)
        self.sites_list.clear()
        for site in sites:
            item = QListWidgetItem(site.get("title") or site.get("url") or "")
            item.setData(Qt.UserRole, site.get("url") or "")
            self.sites_list.addItem(item)
        self.sites_list.blockSignals(False)
        self.lbl_sites_summary.setText(f"{len(sites)} personal sites · select one to preview or double-click to open in Browser.")
        if not sites:
            if prefs.get_show_bundled_sites(self.base_dir):
                self._set_site_placeholder("No personal sites yet", "Add a site to keep your private study, work, or life spaces separate from normal browser bookmarks.")
            else:
                self._set_site_placeholder(
                    "No personal sites yet",
                    "No personal sites added yet. Choose Add site, or enable \"Include bundled sites\" to browse the project apps.",
                )
            return
        for index in range(self.sites_list.count()):
            item = self.sites_list.item(index)
            if item.data(Qt.UserRole) == current_url:
                self.sites_list.setCurrentItem(item)
                return
        self.sites_list.setCurrentRow(0)

    def _on_bundled_sites_toggled(self, checked: bool):
        """Persist the bundled-sites choice and re-render the list.

        Bundled entries are project shortcuts the app seeds itself (e.g. the
        linked web apps); the toggle only filters what is *displayed* — the
        entries stay in prefs untouched, so nothing the user added is ever
        removed."""
        prefs.set_show_bundled_sites(self.base_dir, bool(checked))
        self._refresh_sites()

    def _add_site(self):
        url, ok = QInputDialog.getText(self, "Add site", "URL:")
        if not ok or not (url or "").strip():
            return
        normalized_url = QUrl.fromUserInput(url.strip()).toString()
        if not normalized_url:
            QMessageBox.warning(self, "Sites", "The URL is not valid.")
            return
        title, _ = QInputDialog.getText(self, "Add site", "Display title:")
        display_title = (title or "").strip() or (QUrl(normalized_url).host() or normalized_url)
        prefs.add_personal_site(self.base_dir, normalized_url, display_title)
        self._refresh_sites()

    def _remove_site(self):
        item = self.sites_list.currentItem()
        if not item:
            return
        if QMessageBox.question(self, "Personal sites", "Remove this site from your list?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        prefs.remove_personal_site(self.base_dir, item.data(Qt.UserRole) or "")
        self._refresh_sites()

    def _build_site_view(self) -> QWebEngineView:
        """Site preview that piggybacks on the main browser profile when possible.

        Sharing the profile gives us cookies/cache/the Chrome-shape JS shim for
        free, which removes most of the perceived lag from picking a saved site
        like Cuc Quan Ly: pages stay warm in the same renderer, and a re-click
        on the same URL becomes a no-op instead of a fresh disk reload.
        """
        view = QWebEngineView()
        host_profile = self._host_browser_profile()
        if host_profile is not None:
            try:
                ensure_chrome_compat_script(host_profile)
                page = BrowserPage(host_profile, view, base_dir=self.base_dir)
                view.setPage(page)
            except Exception:
                pass
        settings = view.settings()
        try:
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
            settings.setAttribute(QWebEngineSettings.ShowScrollBars, True)
            try:
                settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
            except AttributeError:
                pass
            try:
                settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
            except AttributeError:
                pass
            try:
                settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, True)
            except AttributeError:
                pass
            try:
                settings.setAttribute(QWebEngineSettings.DnsPrefetchEnabled, True)
            except AttributeError:
                pass
        except Exception:
            pass
        # Highlight-text-to-copy on the embedded preview too: install the
        # profile script so every future load in this view gets the helper,
        # then re-run it after each finished load in case this view runs on
        # its own (standalone) profile.
        try:
            page_profile = view.page().profile() if view.page() else None
            if page_profile is not None:
                ensure_text_highlight_script(page_profile, prefs.get_text_highlight_enabled(self.base_dir), self.base_dir)
        except Exception:
            pass
        view.loadFinished.connect(self._on_site_view_loaded)
        view.setZoomFactor(0.95)
        return view

    def _on_site_view_loaded(self, ok: bool):
        """Re-apply the highlight-to-copy helper after each preview load."""
        if not ok:
            return
        try:
            if not prefs.get_text_highlight_enabled(self.base_dir):
                return
            if self.site_view.page() is None:
                return
            self.site_view.page().runJavaScript(build_text_highlight_js(True))
        except Exception:
            pass

    def _host_browser_profile(self):
        """Return the main browser's QWebEngineProfile, or None if running standalone."""
        shell = self._host_shell()
        if shell is None:
            return None
        candidates = (
            getattr(shell, "browser_page", None),
            getattr(shell, "browser_window", None),
            getattr(shell, "main_window", None),
            shell,
        )
        for owner in candidates:
            if owner is None:
                continue
            profile = getattr(owner, "profile", None)
            if isinstance(profile, QWebEngineProfile):
                return profile
        return None

    def _update_site_preview_activity(self, active: bool) -> None:
        """Stop the embedded preview when the Sites page is hidden so it does
        not keep timers/animations/network running in the background."""
        if not hasattr(self, "site_preview_stack"):
            return
        if getattr(self, "site_view", None) is None:
            return  # lazy view not built yet — nothing to pause
        page = self.site_view.page()
        if active:
            if not getattr(self, "_site_preview_on", False):
                return
            cached = self._site_loaded_url or ""
            if cached and self.site_preview_stack.currentWidget() is self.site_view:
                if not (page and page.url().toString() == cached):
                    self.site_view.setUrl(QUrl(cached))
            return
        try:
            if page is not None:
                # "Stop" alone leaves loaded JS timers running in the background
                # (v6.4 claimed the preview "stops consuming CPU" but did not).
                # Navigating to about:blank actually unloads the site.
                page.triggerAction(_PersonalWebEnginePage.Stop)
                page.setUrl(QUrl("about:blank"))
        except Exception:
            pass

    def _preview_site_selection(self, current, _previous):
        if not current:
            self._set_site_placeholder("No site selected", "Choose a saved personal site to preview it here.")
            self._site_loaded_url = ""
            return
        url = (current.data(Qt.UserRole) or "").strip()
        title = current.text().strip() or "Personal site"
        self.lbl_site_title.setText(title)
        self.lbl_site_url.setText(url or "(empty url)")
        if not url:
            self._site_loaded_url = ""
            return
        if not self._site_preview_on:
            # Lazy preview: navigating the list must never spin up a heavy
            # WebEngine renderer (LinkLumina runs WebGL + hundreds of KB of JS).
            # Show a cheap placeholder until the user opts into a live preview.
            self._show_site_placeholder(
                "Preview paused",
                "Tick 'Live preview' to render the site here, or click 'Open in Browser' to open it as a full tab.",
            )
            return
        site_view = self._ensure_site_view()
        self.site_preview_stack.setCurrentWidget(site_view)
        if url == self._site_loaded_url:
            page = site_view.page()
            if page and page.url().toString() == url:
                return
        self._site_loaded_url = url
        site_view.setUrl(QUrl(url))

    def _set_site_placeholder(self, title: str, detail: str):
        self.lbl_site_title.setText("Site preview")
        self.lbl_site_url.setText(detail)
        self.lbl_site_placeholder_title.setText(title)
        self.lbl_site_placeholder_detail.setText(detail)
        self.site_preview_stack.setCurrentIndex(0)

    def _show_site_placeholder(self, title: str, detail: str):
        """Show the lightweight placeholder without overwriting title/URL labels."""
        self.lbl_site_placeholder_title.setText(title)
        self.lbl_site_placeholder_detail.setText(detail)
        self.site_preview_stack.setCurrentIndex(0)

    def _on_site_preview_toggled(self, checked: bool):
        self._site_preview_on = bool(checked)
        if checked:
            item = self.sites_list.currentItem()
            if item is not None:
                self._preview_site_selection(item, None)
        else:
            self._stop_preview()

    def _on_full_preview_toggled(self, checked: bool):
        """Expand the preview to the full Sites area (collapse toolbars + list)."""
        checked = bool(checked)
        for widget in (
            getattr(self, "_sites_top_bar", None),
            self.lbl_sites_summary,
            getattr(self, "sites_header", None),
        ):
            if widget is not None:
                widget.setVisible(not checked)
        if hasattr(self, "_sites_left_card"):
            self._sites_left_card.setVisible(not checked)
        self.btn_full_preview.setText("Exit full" if checked else "Full preview")
        if checked:
            # Full preview implies the user actually wants to see the site.
            if not self.chk_site_preview.isChecked():
                self.chk_site_preview.setChecked(True)
            if hasattr(self, "_sites_splitter"):
                self._sites_splitter.setSizes([0, 1200])
        elif hasattr(self, "_sites_splitter"):
            self._sites_splitter.setSizes([220, 960])

    def _stop_preview(self):
        """Unload the embedded renderer so a heavy local app stops using CPU/GPU."""
        self._site_loaded_url = ""
        try:
            if getattr(self, "site_view", None) is not None:
                page = self.site_view.page()
                if page is not None:
                    page.triggerAction(_PersonalWebEnginePage.Stop)
                    self.site_view.setUrl(QUrl("about:blank"))
        except Exception:
            pass
        self._show_site_placeholder(
            "Preview paused",
            "The embedded preview is unloaded to save resources. Tick 'Live preview' to load it again.",
        )

    def _open_site_item(self, item: QListWidgetItem):
        url = item.data(Qt.UserRole) or ""
        if url:
            self._open_url_in_browser(url)

    def _open_selected_site_in_browser(self):
        item = self.sites_list.currentItem()
        if item:
            self._open_url_in_browser(item.data(Qt.UserRole) or "")

    def _ask_ai_about_site(self):
        item = self.sites_list.currentItem()
        if not item:
            QMessageBox.information(self, "AI", "Select a site first.")
            return
        shell = self._host_shell()
        if not shell or not hasattr(shell, "ai_page"):
            QMessageBox.information(self, "AI", "Open Personal Hub inside the main shell to use the assistant.")
            return
        url = (item.data(Qt.UserRole) or "").strip()
        title = (item.text() or url or "Personal site").strip()
        if not url:
            QMessageBox.information(self, "AI", "This site has no URL to read.")
            return
        question = f"What is this personal site for and how should I use it: {title}"
        self._site_ai_shell = shell
        self._site_ai_question = question
        self._site_ai_meta = (title, url)
        self._site_preview_was_on_before_ai = bool(self._site_preview_on)
        already_loaded = ""
        try:
            already_loaded = self._ensure_site_view().page().url().toString()
        except Exception:
            pass
        if already_loaded == url:
            # Site is already rendered in the preview — read it straight away.
            self._on_site_ai_load_finished(True)
            return
        # Load the site in the embedded preview (even when Live preview is off)
        # and read its real content so the assistant answers from the page,
        # not just from the saved URL.
        self._site_preview_on = True
        site_view = self._ensure_site_view()
        self.site_preview_stack.setCurrentWidget(site_view)
        self._site_loaded_url = url
        try:
            site_view.loadFinished.disconnect(self._on_site_ai_load_finished)
        except Exception:
            pass
        site_view.loadFinished.connect(self._on_site_ai_load_finished)
        site_view.setUrl(QUrl(url))

    def _on_site_ai_load_finished(self, _ok: bool):
        try:
            self._ensure_site_view().loadFinished.disconnect(self._on_site_ai_load_finished)
        except Exception:
            pass
        shell = getattr(self, "_site_ai_shell", None)
        if not shell or not hasattr(shell, "ai_page"):
            return
        title, url = getattr(self, "_site_ai_meta", ("", ""))
        question = getattr(self, "_site_ai_question", "") or f"What is this personal site for and how should I use it: {title}"

        def _grab(page_text):
            body = (page_text or "").strip()
            context = f"Title: {title}\nURL: {url}\n\nSite content:\n{body[:8000]}"
            shell.ed_ai_quick.setText(question)
            shell.ai_page.ask_with_context(question, f"Personal site: {title}", context)
            shell.switch_workspace("ai")
            # If Live preview was off, unload the temporary preview again so a
            # heavy site does not keep running in the background.
            was_on = bool(getattr(self, "_site_preview_was_on_before_ai", True))
            if not was_on:
                self._stop_preview()
            self._site_preview_on = was_on

        try:
            self._ensure_site_view().page().toPlainText(_grab)
        except Exception:
            _grab("")

    def _open_url_in_browser(self, url: str):
        if not url:
            return
        shell = self._host_shell()
        if shell is not None:
            shell.switch_workspace("browser")
            shell.browser_page.url_bar.setText(url)
            shell.browser_page.navigate()
            return
        site_view = self._ensure_site_view()
        self.site_preview_stack.setCurrentWidget(site_view)
        site_view.setUrl(QUrl(url))

    def _host_shell(self):
        current = self.parent()
        while current is not None:
            if hasattr(current, "switch_workspace") and hasattr(current, "browser_page"):
                return current
            current = current.parent()
        win = self.window()
        if hasattr(win, "switch_workspace") and hasattr(win, "browser_page"):
            return win
        return None

    def open_plan_item(self, item_id: str):
        """Open the Weekly Plan on an item's week and highlight its row."""
        plan = personal_plan.load_plan(self.base_dir)
        target = next((item for item in plan["items"] if item.get("id") == item_id), None)
        if target is None:
            return
        anchor = target.get("scheduled_date") or target.get("due_date") or ""
        if anchor:
            self._planner_week_start = personal_plan.week_key(anchor)
        self._switch_page("plan")
        self._refresh_plan()
        for _label, day_list in self.plan_day_lists.values():
            for index in range(day_list.count()):
                row = day_list.item(index)
                if str(row.data(Qt.UserRole) or "") == item_id:
                    day_list.setCurrentItem(row)
                    day_list.scrollToItem(row)
                    return

    def open_plan_block(self, block_id: str):
        """Open the Weekly Plan on a time block's week and highlight it."""
        plan = personal_plan.load_plan(self.base_dir)
        target = next((block for block in plan["time_blocks"] if block.get("id") == block_id), None)
        if target is None:
            return
        anchor = target.get("date") or ""
        if anchor:
            self._planner_week_start = personal_plan.week_key(anchor)
        self._switch_page("plan")
        self._refresh_plan()
        tag = f"block:{block_id}"
        for _label, day_list in self.plan_day_lists.values():
            for index in range(day_list.count()):
                row = day_list.item(index)
                if str(row.data(Qt.UserRole) or "") == tag:
                    day_list.setCurrentItem(row)
                    day_list.scrollToItem(row)
                    return

    def open_plan_course(self, course_id: str):
        """Open the Weekly Plan on a course row (row list ships with the course UI)."""
        self._switch_page("plan")
        course_list = getattr(self, "plan_courses_list", None)
        if course_list is None:
            return
        for index in range(course_list.count()):
            row = course_list.item(index)
            if str(row.data(Qt.UserRole) or "") == course_id:
                course_list.setCurrentItem(row)
                course_list.scrollToItem(row)
                return

    def open_flashcard(self, card_id: str):
        """Open Review focused on one card, switching to the full deck if needed."""
        self._switch_page("review")
        if getattr(self, "_deck_mode", "due") != "all":
            self._set_review_mode("all")
        deck = getattr(self, "_deck", None) or []
        for index, card in enumerate(deck):
            if card.get("id") == card_id:
                self._deck_pos = index
                self._show_current_card()
                return

    def open_life_item(self, kind: str, item_id: str):
        if kind == "task":
            self._switch_page("tasks")
            for index in range(self.tasks_list.count()):
                item = self.tasks_list.item(index)
                if item.data(Qt.UserRole) == item_id:
                    self.tasks_list.setCurrentItem(item)
                    break
            return
        if kind == "event":
            self._switch_page("calendar")
            self.select_event(item_id)
            return
        if kind in ("board", "board-node"):
            self._switch_page("boards")
            target_board_id = item_id
            if kind == "board-node":
                # Resolve the node's parent board; v6.4 used the node id itself
                # and could never match any board.
                target_board_id = self._find_board_for_node(item_id) or self.current_board_id
            if not any(self.boards_list.item(i).data(Qt.UserRole) == target_board_id for i in range(self.boards_list.count())):
                self._refresh_boards()
            for index in range(self.boards_list.count()):
                item = self.boards_list.item(index)
                if item.data(Qt.UserRole) == target_board_id:
                    if self.boards_list.currentItem() is not item:
                        self.boards_list.setCurrentItem(item)
                    else:
                        self._load_selected_board(item, None)  # force scene rebuild
                    return

    def _find_board_for_node(self, node_id: str) -> str:
        for board in life_service.load_boards(self.base_dir):
            for node in board.get("nodes", []) or []:
                if isinstance(node, dict) and node.get("id") == node_id:
                    return board.get("id", "")
        return ""

    def get_current_state(self):
        tabs = []
        for idx, site in enumerate(prefs.get_personal_sites(self.base_dir)):
            url = (site.get("url") or "").strip()
            if url:
                tabs.append({"url": url, "active": idx == 0})
        return tabs

    def _auto_save_set(self):
        tabs = self.get_current_state()
        if tabs:
            tab_sets.add_tab_set(self.base_dir, "personal", time.strftime("Personal auto %Y-%m-%d %H:%M"), tabs)

    def save_current_set(self):
        tabs = self.get_current_state()
        if not tabs:
            QMessageBox.information(self, "Personal", "No personal sites to save yet.")
            return
        default = time.strftime("Personal manual %Y-%m-%d %H:%M")
        name, ok = QInputDialog.getText(self, "Save Personal session", "Session name:", text=default)
        if not ok:
            return
        tab_sets.add_tab_set(self.base_dir, "personal", name or default, tabs)
        QMessageBox.information(self, "Personal", "Current personal session saved.")

    def persist_state(self) -> bool:
        save_errors = []
        try:
            if not self._flush_note_edits():
                save_errors.append("the open note could not be saved")
        except Exception as exc:
            save_errors.append(f"note save failed: {exc}")
        try:
            if not self._save_current_board_positions(notify=False):
                save_errors.append("the open board could not be saved")
        except Exception as exc:
            save_errors.append(f"board save failed: {exc}")
        try:
            self._auto_save_set()
        except Exception:
            pass
        if save_errors:
            QMessageBox.warning(
                self,
                "Personal Hub",
                "Close was canceled to protect your edits:\n- " + "\n- ".join(save_errors),
            )
            return False
        return True

    def shutdown(self):
        for timer in self.findChildren(QTimer):
            timer.stop()

    def closeEvent(self, event):
        if not self.persist_state():
            event.ignore()
            return
        self.shutdown()
        event.accept()


def _format_ts(ts_value: int) -> str:
    """Backward-compatible alias; the canonical helper lives in core.time_utils.

    This used to be a hand-rolled copy without the int()/exception guards the
    shared helper has, so a malformed timestamp raised instead of showing "-".
    """
    from litebrowser.core.time_utils import format_ts

    return format_ts(ts_value)


def stats_text(stats: dict) -> str:
    return f"{stats.get('total', 0)} cards, {stats.get('due', 0)} due"
