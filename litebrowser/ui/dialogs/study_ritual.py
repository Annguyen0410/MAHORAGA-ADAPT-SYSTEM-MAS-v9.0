"""The study-session dialog: pick a cup, see the pace, name what you will finish.

One question, one action. The menu is the timer — choosing "Milk coffee" chooses
45 minutes — and the line about what you will finish rides into the session
label, so the journal explains itself a week later. Everything it does lives in
:mod:`litebrowser.services.study_ritual`; this file is only the door.
"""
from __future__ import annotations

from litebrowser.qt import QtWidgets
from litebrowser.services import study_ritual
from litebrowser.ui.dialogs.common import _stylesheet, dialog_footer, primary_button


def _desk_hint(desk: dict | None) -> str:
    """The desk's next step, offered as the default thing to finish."""
    desk = desk if isinstance(desk, dict) else {}
    for block in desk.get("blocks", []):
        if block.get("key") != "next":
            continue
        flow = block.get("flow") or {}
        return str(flow.get("label") or "").strip()
    return ""


def show_study_ritual(shell, desk: dict | None = None) -> dict | None:
    """Open the ritual dialog; returns the started session (None when cancelled)."""
    base_dir = getattr(shell, "profile_dir", "") or ""
    dlg = QtWidgets.QDialog(shell)
    dlg.setWindowTitle("Study session")
    dlg.resize(520, 320)
    dlg.setStyleSheet(_stylesheet(shell))
    layout = QtWidgets.QVBoxLayout(dlg)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Sit down properly ☕")
    title.setObjectName("HeroTitle")
    layout.addWidget(title)
    intro = QtWidgets.QLabel(
        "Every cup is a pace: pick one and the timer is set for you. What you write "
        "below lands in the session label, so the weekly review remembers what it was for."
    )
    intro.setObjectName("MutedLabel")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    combo = QtWidgets.QComboBox()
    for pour, line, minutes in study_ritual.POURS:
        combo.addItem(f"{line}  ·  {minutes} min", pour)
    saved = study_ritual.last_pour(base_dir)
    combo.setCurrentIndex(max(0, combo.findData(saved)))
    layout.addWidget(combo)

    minutes_row = QtWidgets.QHBoxLayout()
    minutes_row.setSpacing(8)
    minutes_row.addWidget(QtWidgets.QLabel("Minutes:"))
    spin = QtWidgets.QSpinBox()
    spin.setRange(5, 180)
    spin.setSingleStep(5)
    spin.setValue(study_ritual.pour_minutes(saved))
    minutes_row.addWidget(spin)
    minutes_row.addStretch(1)
    layout.addLayout(minutes_row)

    note = QtWidgets.QLineEdit()
    note.setPlaceholderText("What will you finish? (optional)")
    note.setText(_desk_hint(desk))
    layout.addWidget(note)

    hint = QtWidgets.QLabel("")
    hint.setObjectName("MutedLabel")
    hint.setWordWrap(True)
    layout.addWidget(hint)

    def _sync_hint():
        """Choosing a cup sets the pace: the spin box follows the menu."""
        pour = combo.currentData() or saved
        minutes = study_ritual.pour_minutes(pour)
        spin.setValue(minutes)
        hint.setText(f"This cup is a {minutes}-minute sitting. The timer runs in the status strip.")

    combo.currentIndexChanged.connect(lambda _index: _sync_hint())
    _sync_hint()
    layout.addStretch(1)

    result: dict = {}

    def _start():
        session = study_ritual.start_ritual(
            base_dir,
            pour=combo.currentData() or saved,
            minutes=spin.value(),
            note=note.text(),
        )
        result["session"] = session
        dlg.accept()

    primary = primary_button("Start the pour", "Begin this study session now")
    primary.clicked.connect(_start)
    dialog_footer(layout, primary=primary, close=True)

    dlg.exec_()
    session = result.get("session")
    if session:
        refresh = getattr(shell, "refresh_shell", None)
        if callable(refresh):
            refresh()
        flash = getattr(shell, "_flash_status", None)
        if callable(flash):
            flash(study_ritual.ritual_line(session))
    return session if isinstance(session, dict) else None


__all__ = ["show_study_ritual"]
