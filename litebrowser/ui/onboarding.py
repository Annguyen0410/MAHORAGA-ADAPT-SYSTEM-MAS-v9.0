"""First-run onboarding: three quick steps, shown once, always skippable.

1. Pick a theme + accent (live swatches, optional auto day/night) *and the cup
   you usually study over* — the ritual's pace is a first-run decision, because
   it is what the Study session button on Home will offer from now on.
2. Bring your stuff: tabs from Chrome/Edge (the bridge extension) and an Anki
   ``.apkg`` if you already keep cards somewhere else.
3. Pair the Android bridge (QR) — optional.

Completion is recorded in prefs ('onboarding_done'), so it never nags again.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from litebrowser.core import app_version, prefs
from litebrowser.services import anki_service, study_ritual
from litebrowser.ui import theme
from litebrowser.ui.dialogs.common import _stylesheet

STEPS = ("Welcome to your café ☕", "Bring your stuff", "Pair your phone (optional)")


def _swatch_icon(mode_id: str, accent_id: str) -> QPixmap:
    pal = theme._palette(mode_id, accent_id)
    pixmap = QPixmap(64, 34)
    pixmap.fill(QColor(pal["MAIN_BG"]))
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor(pal["BORDER_SOFT"]), 1))
    painter.setBrush(QColor(pal["SIDEBAR_BG"]))
    painter.drawRect(0, 0, 63, 33)
    painter.setBrush(QColor(pal["ACCENT"]))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(6, 8, 20, 18, 4, 4)
    painter.setBrush(QColor(pal["ACCENT_SOFT"]))
    painter.drawRoundedRect(32, 8, 26, 8, 3, 3)
    painter.drawRoundedRect(32, 20, 26, 6, 3, 3)
    painter.end()
    return pixmap


def show_onboarding(shell) -> None:
    if prefs.get_pref(shell.profile_dir, "onboarding_done", False):
        return
    dlg = QDialog(shell)
    dlg.setWindowTitle(f"Welcome to {app_version.APP_NAME} — setup")
    dlg.resize(620, 480)
    dlg.setStyleSheet(_stylesheet(shell))
    layout = QVBoxLayout(dlg)

    title = QLabel(STEPS[0])
    title.setObjectName("HeroTitle")
    layout.addWidget(title)
    step_lbl = QLabel("Step 1 of 3")
    step_lbl.setObjectName("MutedLabel")
    layout.addWidget(step_lbl)

    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(body, 1)

    # --- Step 1: theme ---
    theme_page = QWidget()
    tp_layout = QVBoxLayout(theme_page)
    tp_layout.addWidget(QLabel("Pick the look of your café — you can change it anytime with /theme and /accent."))
    combo_theme = QComboBox()
    combo_accent = QComboBox()
    preview = QLabel()
    preview.setMinimumHeight(60)
    for mode_id in sorted(theme.PALETTES.keys()):
        combo_theme.addItem(theme.theme_display_name(mode_id), mode_id)
    for accent_id in sorted(theme.ACCENTS.keys()):
        combo_accent.addItem(theme.accent_display_name(accent_id), accent_id)

    def _current_ids():
        return combo_theme.currentData() or theme.DEFAULT_THEME, combo_accent.currentData() or "brass"

    def _update_preview():
        mode_id, accent_id = _current_ids()
        preview.setPixmap(_swatch_icon(mode_id, accent_id).scaled(128, 68))

    combo_theme.currentIndexChanged.connect(lambda _i: _update_preview())
    combo_accent.currentIndexChanged.connect(lambda _i: _update_preview())
    combo_theme.setCurrentIndex(max(0, combo_theme.findData(prefs.get_shell_theme(shell.profile_dir))))
    combo_accent.setCurrentIndex(max(0, combo_accent.findData(prefs.get_accent(shell.profile_dir))))
    _update_preview()
    tp_layout.addWidget(QLabel("Theme:"))
    tp_layout.addWidget(combo_theme)
    tp_layout.addWidget(QLabel("Accent:"))
    tp_layout.addWidget(combo_accent)
    tp_layout.addWidget(preview)
    chk_auto = QCheckBox("Auto day / night — day palette by day, night palette after 18:00")
    chk_auto.setChecked(prefs.get_auto_theme(shell.profile_dir))
    tp_layout.addWidget(chk_auto)
    tp_layout.addWidget(
        QLabel(
            "\nWhich cup do you usually study over? Every cup is a pace, and this is "
            "what the Study session button on Home will offer you:"
        )
    )
    combo_pour = QComboBox()
    for pour, line, minutes in study_ritual.POURS:
        combo_pour.addItem(f"{line}  ·  {minutes} min", pour)
    saved_pour = study_ritual.last_pour(shell.profile_dir)
    combo_pour.setCurrentIndex(max(0, combo_pour.findData(saved_pour)))
    combo_pour.setToolTip("Change any time — the Study session dialog remembers your last pick")
    tp_layout.addWidget(combo_pour)
    body_layout.addWidget(theme_page)

    # --- Step 2: import ---
    import_page = QWidget()
    imp_layout = QVBoxLayout(import_page)
    imp_layout.addWidget(QLabel(
        "Mei can pull tabs from your current browser through the Mei bridge extension "
        "(Chrome / Opera GX / Edge). You can also skip and use File → Import later."
    ))
    chk_skip_import = QCheckBox("Skip for now")
    chk_skip_import.setChecked(True)
    imp_layout.addWidget(chk_skip_import)
    imp_layout.addWidget(QLabel("\nAlready keep flashcards in Anki? Import the deck now:"))
    btn_anki = QPushButton("Import an Anki deck (.apkg)…")
    btn_anki.setToolTip("Cards, tags, interval and ease are read out of the package")
    imp_layout.addWidget(btn_anki)

    def _import_anki():
        from PyQt5.QtWidgets import QFileDialog, QMessageBox

        path, _filter = QFileDialog.getOpenFileName(dlg, "Import an Anki deck", "", "Anki packages (*.apkg)")
        if not path:
            return
        try:
            report = anki_service.import_package(shell.profile_dir, path)
        except anki_service.AnkiFormatError as error:
            QMessageBox.warning(dlg, "Import failed", str(error))
            return
        QMessageBox.information(
            dlg,
            "Deck imported",
            f"Imported {report.get('imported', 0)} card(s) from “{report.get('deck', 'Anki')}”"
            + (f" — {report.get('skipped', 0)} skipped" if report.get("skipped") else ""),
        )

    btn_anki.clicked.connect(_import_anki)
    imp_layout.addStretch(1)
    body_layout.addWidget(import_page)
    import_page.hide()

    # --- Step 3: phone ---
    phone_page = QWidget()
    phone_layout = QVBoxLayout(phone_page)
    phone_layout.addWidget(QLabel(
        "The Android bridge lets your phone push links, files and notes into Mei over Wi-Fi. "
        "Enable it later from Settings, or run the VPN / Bridge hub anytime."
    ))
    chk_bridge = QCheckBox("Enable the Android bridge for local testing (localhost only)")
    phone_layout.addWidget(chk_bridge)
    phone_layout.addWidget(QLabel("Phone pairing needs a reachable Wi-Fi address. Configure LAN access explicitly in Settings; it is never enabled automatically."))
    phone_layout.addStretch(1)
    body_layout.addWidget(phone_page)
    phone_page.hide()

    state = {"step": 1}

    nav_row = QHBoxLayout()
    btn_back = QPushButton("Back")
    btn_back.setEnabled(False)
    btn_next = QPushButton("Next")
    btn_next.setObjectName("TopAccentButton")
    btn_skip = QPushButton("Skip setup")
    nav_row.addWidget(btn_skip)
    nav_row.addStretch(1)
    nav_row.addWidget(btn_back)
    nav_row.addWidget(btn_next)
    layout.addLayout(nav_row)

    pages = {1: theme_page, 2: import_page, 3: phone_page}

    def _show_step(n: int):
        state["step"] = n
        for key, page in pages.items():
            page.setVisible(key == n)
        step_lbl.setText(f"Step {n} of 3 — {STEPS[n - 1]}")
        btn_back.setEnabled(n > 1)
        btn_next.setText("Finish ✨" if n == 3 else "Next")

    def _on_next():
        step = state["step"]
        if step == 1:
            theme_id, accent_id = _current_ids()
            prefs.set_shell_theme(shell.profile_dir, theme_id)
            prefs.set_accent(shell.profile_dir, accent_id)
            prefs.set_auto_theme(shell.profile_dir, chk_auto.isChecked())
            pour = combo_pour.currentData() or study_ritual.DEFAULT_POUR
            prefs.save_pref(shell.profile_dir, study_ritual.POUR_PREF_KEY, pour)
            shell._qss_key = None
            shell.refresh_shell()
            _show_step(2)
            return
        if step == 2:
            if not chk_skip_import.isChecked():
                from litebrowser.ui.dialogs import sessions as _sessions

                _sessions.show_extensions_dialog(shell.browser_page)
            _show_step(3)
            return
        if chk_bridge.isChecked():
            prefs.set_mobile_bridge_enabled(shell.profile_dir, True)
        prefs.save_pref(shell.profile_dir, "onboarding_done", True)
        dlg.accept()

    def _on_back():
        _show_step(max(1, state["step"] - 1))

    def _skip_setup():
        prefs.save_pref(shell.profile_dir, "onboarding_done", True)
        dlg.accept()

    for label in dlg.findChildren(QLabel):
        if label is not preview:
            label.setWordWrap(True)
    btn_skip.clicked.connect(_skip_setup)
    btn_next.clicked.connect(_on_next)
    btn_back.clicked.connect(_on_back)
    _show_step(1)
    dlg.exec_()
