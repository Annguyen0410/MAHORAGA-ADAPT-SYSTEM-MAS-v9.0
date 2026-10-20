"""Shared dialog chrome: the stylesheet hook and one calm button vocabulary.

A dialog used to end in a row of five to seven look-alike push buttons, so the
single action the dialog exists for was impossible to spot. Every dialog now
builds its bottom row through :func:`dialog_footer`: the job's own action on the
right, at most two secondary verbs beside it, and every occasional verb folded
into one "⋯ More" overflow menu. The four roles below map onto object names the
theme paints (``theme.py``, section 6.7), so a dialog can no longer invent its
own button look.
"""

from litebrowser.qt import QtWidgets

# Role -> object name the theme paints. Add a role only together with its QSS.
ROLE_OBJECT_NAMES = {
    "primary": "PrimaryButton",
    "ghost": "GhostButton",
    "quiet": "QuietButton",
    "danger": "DangerButton",
}


def _stylesheet(parent):
    return getattr(parent, "_dialog_stylesheet", lambda: "")()


def role_button(text: str, role: str = "ghost", tooltip: str = "") -> QtWidgets.QPushButton:
    """One button in the shared dialog vocabulary."""
    button = QtWidgets.QPushButton(text)
    button.setObjectName(ROLE_OBJECT_NAMES.get(role, ROLE_OBJECT_NAMES["ghost"]))
    if tooltip:
        button.setToolTip(tooltip)
    button.setAccessibleName(tooltip or text)
    return button


def primary_button(text: str, tooltip: str = "") -> QtWidgets.QPushButton:
    """The one action this dialog exists for (accent-filled, takes Enter)."""
    return role_button(text, "primary", tooltip)


def ghost_button(text: str, tooltip: str = "") -> QtWidgets.QPushButton:
    """A secondary verb that is worth keeping visible."""
    return role_button(text, "ghost", tooltip)


def quiet_button(text: str, tooltip: str = "") -> QtWidgets.QPushButton:
    """Borderless variant: Close, overflow menus, glyph-only controls."""
    return role_button(text, "quiet", tooltip)


def danger_button(text: str, tooltip: str = "") -> QtWidgets.QPushButton:
    """A destructive verb — tinted, never filled, so it cannot be the reflex."""
    return role_button(text, "danger", tooltip)


def icon_button(glyph: str, tooltip: str = "") -> QtWidgets.QPushButton:
    """Square borderless glyph button for actions that belong to a list row.

    Row-level verbs (unsubscribe, remove, refresh) read as part of the list they
    act on instead of adding another look-alike box next to the real actions.
    """
    button = quiet_button(glyph, tooltip)
    button.setProperty("compactIcon", True)
    button.setFixedSize(34, 34)
    return button


def more_menu(
    entries,
    label: str = "⋯  More",
    tooltip: str = "Everything else this dialog can do",
) -> QtWidgets.QPushButton:
    """Fold the occasional verbs into one overflow menu button.

    ``entries`` is a sequence of ``(label, callback)`` pairs; ``(None, None)``
    draws a separator, which is how the destructive verbs stay apart from the
    safe ones.
    """
    button = ghost_button(label, tooltip)
    menu = QtWidgets.QMenu(button)
    menu.setObjectName("DialogOverflowMenu")
    for text, callback in entries:
        if not text:
            menu.addSeparator()
            continue
        action = menu.addAction(text)
        if callback is not None:
            action.triggered.connect(lambda _checked=False, run=callback: run())
    # Keep Qt ownership/modal membership intact. A parentless popup can be
    # blocked by an active modal dialog and does not inherit its stylesheet.
    button._overflow_menu = menu
    button.setMenu(menu)
    menu.aboutToShow.connect(lambda: menu.setStyleSheet(button.window().styleSheet()))
    return button


def menu_action(button: QtWidgets.QPushButton, label: str):
    """The ``QAction`` behind ``label`` in a :func:`more_menu` button, else ``None``.

    Menu verbs carry state too: "Sign out" in a card with no account signed in
    still has to grey out, and this is how the owner of the button reaches it.
    """
    menu = button.menu()
    if menu is None:
        return None
    for action in menu.actions():
        if action.text() == label:
            return action
    return None


def dialog_footer(
    layout,
    *,
    primary: QtWidgets.QPushButton | None = None,
    secondary=(),
    menu=(),
    close=True,
    close_label: str = "Close",
    default: bool = True,
) -> QtWidgets.QHBoxLayout:
    """Build the single bottom row every dialog ends with.

    ``primary``   the action the dialog exists for (right-aligned, accent-filled).
    ``secondary`` widgets worth keeping visible, on the left — rarely more than two.
    ``menu``      ``(label, callback)`` pairs folded into the "⋯ More" menu.
    ``close``     ``True`` for the plain Close button, ``False`` to omit it, a
                  widget to place your own, or a callable to run instead of the
                  dialog's default dismiss.
    ``default``   hand the Enter key to the primary action (turn it off when a
                  text field in the dialog owns Enter — e.g. subscribing to a feed).
    """
    row = QtWidgets.QHBoxLayout()
    row.setSpacing(8)
    for widget in secondary:
        row.addWidget(widget)
    row.addStretch(1)
    if menu:
        row.addWidget(more_menu(menu))
    if primary is not None:
        if default:
            primary.setDefault(True)
        row.addWidget(primary)
    if close:
        if isinstance(close, QtWidgets.QWidget):
            row.addWidget(close)
        else:
            close_button = quiet_button(close_label, "Close this dialog (Esc)")
            if callable(close):
                close_button.clicked.connect(close)
            else:
                host = layout.parentWidget()
                dismiss = getattr(host, "reject", None) if host is not None else None
                close_button.clicked.connect(dismiss or (host.close if host else (lambda: None)))
            row.addWidget(close_button)
    layout.addLayout(row)
    return row
