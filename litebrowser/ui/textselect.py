"""Make every visible string in the app selectable and copyable.

Two complementary behaviours:

* QLabel (and subclasses): text becomes selectable with the mouse and the
  keyboard (Ctrl+A / Ctrl+C) so users can highlight and copy any label —
  titles, subtitles, stats, tooltips-on-screen, etc.
* QPushButton / QToolButton / QCheckBox: Qt cannot select text inside a
  button, so a right-click context menu with "Copy text" fills that gap.

Call :func:`enable_text_selection` once per top-level window after its UI
is fully constructed.
"""
from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
)

__all__ = ["enable_text_selection"]


class _ButtonCopyFilter(QObject):
    """Right-click a button → "Copy <text>" menu (text inside Qt buttons
    cannot be mouse-selected, this is the closest Qt-native equivalent)."""

    _shared = None

    def __init__(self):
        super().__init__()

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.ContextMenu:
            text = ""
            if isinstance(obj, QPushButton) or isinstance(obj, QToolButton) or isinstance(obj, QCheckBox):
                text = obj.text()
            text = (text or "").strip()
            if text:
                snippet = text if len(text) <= 40 else text[:37] + "..."
                menu = QMenu(obj)
                action = menu.addAction("Copy text: \"%s\"" % snippet)
                action.triggered.connect(lambda _=False, t=text: QApplication.clipboard().setText(t))
                menu.exec_(ev.globalPos())
                ev.accept()
                return True
        return False


def _button_copy_filter() -> _ButtonCopyFilter:
    if _ButtonCopyFilter._shared is None:
        _ButtonCopyFilter._shared = _ButtonCopyFilter()
    return _ButtonCopyFilter._shared


def enable_text_selection(window) -> None:
    """Walk ``window`` once; labels become selectable, buttons copyable.

    Idempotent for the button filters (a shared event filter instance is
    installed per widget, Qt ignores duplicate installs). Safe to call on
    freshly constructed windows; QSS styling is not affected.
    """
    if window is None:
        return
    for label in window.findChildren(QLabel):
        if label.property("decorative"):
            continue
        flags = label.textInteractionFlags()
        label.setTextInteractionFlags(flags | Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    for button in window.findChildren((QPushButton, QToolButton, QCheckBox)):
        button.installEventFilter(_button_copy_filter())