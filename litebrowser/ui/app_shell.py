"""AppShell: the master window that hosts every Mei workspace.

The shell is the outer frame of the app — a left navigation rail, a top bar
with the omnibar (search box + slash commands + the inline feature finder),
an insights panel, and a QStackedWidget of workspaces (Home, Browser,
History, AI, Personal, Library, Settings).

Everything a user types in the omnibar routes through :meth:`handle_omnibar`;
the inline feature finder (:meth:`_show_feature_popup`) turns plain letters
into live feature results without opening a separate dialog.
"""
import os
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import QEvent, QPoint, QRect, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QCompleter,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from litebrowser.core import app_paths, app_version, prefs
from litebrowser.services import (
    history_service,
    life_service,
    personal_service,
    security,
    update_service,
    workspace_manager,
)
from litebrowser.ui import components, dialogs, theme, win_titlebar
from litebrowser.ui.ai_window import AIWindow
from litebrowser.ui.main_window import SearchWindow
from litebrowser.ui.personal_window import PersonalWindow
from litebrowser.ui.shell.pages import (
    HistoryPage,
    HomeDashboardPage,
    LibraryPage,
    SettingsPage,
    _format_ts,
)


class AppShell(QMainWindow):
    update_checked = pyqtSignal(object, bool)
    update_progress = pyqtSignal(int, int)
    update_downloaded = pyqtSignal(object, object)
    sync_finished = pyqtSignal(bool, str)
    monitor_checked = pyqtSignal(object)
    background_done = pyqtSignal(object, object)

    def __init__(self, profile_dir: str, app_dir: str = None, window_slot: str = "primary", browser_workspace_id: str | None = None):
        super().__init__()
        self._closing = False
        self._private_locked = False
        self.profile_dir = prefs.ensure_profile_layout(profile_dir)
        self.app_dir = app_dir or app_paths.project_root()
        self.window_slot = window_slot
        self.browser_workspace_id = browser_workspace_id or workspace_manager.PRIMARY_WORKSPACE_ID
        self._unlocked_spaces = set()
        security.on_lock(self.profile_dir, self._relock_private_spaces)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shell")
        self._update_check_running = False
        self._update_install_running = False
        self._pending_update_info = None
        self.update_status_text = f"Installed version: {app_version.APP_VERSION}"
        self._insight_cache = None
        self._insight_cache_time = 0
        self._insights_user_toggled = False
        self.update_checked.connect(self._finish_update_check)
        self.update_progress.connect(self._on_update_progress)
        self.update_downloaded.connect(self._finish_downloaded_update)
        self.sync_finished.connect(self._show_sync_result)
        self.monitor_checked.connect(self._on_monitor_checked)
        self.background_done.connect(self._deliver_background_result)
        title_suffix = "Workspace 1" if self.window_slot == "primary" else "Workspace 2"
        # Brand comes from core/product.py: the taskbar used to spell out a name
        # the exe, installer and data folder did not share.
        self.setWindowTitle(f"{app_version.APP_NAME} - {title_suffix}")
        self.setWindowIcon(QIcon(os.path.join(self.app_dir, "icon.png")))
        self.resize(1560, 940)
        self.setMinimumSize(760, 560)
        win_titlebar.apply_dark_titlebar(self, enabled=True)

        root = QWidget()
        root.setObjectName("ShellRoot")
        self.setCentralWidget(root)
        shell_layout = QVBoxLayout(root)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self._rail_collapsed = False
        self._topbar_collapsed = False

        # ---------- App top bar: brand + omnibar + actions ----------
        top_bar = QWidget()
        top_bar.setObjectName("ShellTopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 8, 18, 8)
        top_layout.setSpacing(14)

        # Identity, not a logo lockup: a serif monogram, the name, and the house
        # line in clay.  It sits once, in the top-left corner of the desk.
        brand_wrap = QWidget()
        brand_wrap.setObjectName("BrandWrap")
        brand_layout = QHBoxLayout(brand_wrap)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(9)
        brand_glyph = QLabel("M")
        brand_glyph.setObjectName("BrandGlyph")
        brand_layout.addWidget(brand_glyph)
        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(0)
        brand_name = QLabel("Mei")
        brand_name.setObjectName("BrandName")
        brand_text.addWidget(brand_name)
        brand_sub = QLabel("The Quiet Table")
        brand_sub.setObjectName("BrandSub")
        brand_text.addWidget(brand_sub)
        brand_layout.addLayout(brand_text)
        top_layout.addWidget(brand_wrap)

        self.omnibar = QLineEdit()
        self.omnibar.setObjectName("ShellOmnibar")
        self.omnibar.setPlaceholderText("Search, jump, or run a command   ·   /capture   /note   /task")
        # Generated from core.commands: the autocomplete used to be a hand-written
        # list that had drifted six commands behind the registry (/accent,
        # /export, /review, /routines, /template, /theme) with no test able to
        # tell. Adding a command is now a registry edit only.
        from litebrowser.core.commands import completions as _command_completions

        self._omnibar_completer = QCompleter(_command_completions(), self)
        self._omnibar_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._omnibar_completer.setFilterMode(Qt.MatchStartsWith)
        self.omnibar.setCompleter(self._omnibar_completer)
        # Leading search action: custom-drawn magnifier that follows the
        # active theme accent. Clicking it focuses the box and opens the
        # feature list; typing alone also opens the list (see
        # _on_omnibar_text_changed), so the icon is a shortcut, not a gate.
        from litebrowser.ui.icons import search_icon

        self._omnibar_search_action = self.omnibar.addAction(search_icon("#9ca3af"), QLineEdit.LeadingPosition)
        self._omnibar_search_action.setToolTip("Search app features — start typing in the search box")
        self._omnibar_search_action.triggered.connect(self._open_omnibar_feature_finder)
        # Inline feature finder: typing any letters in the omnibar drops a
        # live list of matching workspaces / personal pages / sites / commands
        # right under the box; Enter or a click jumps to the feature.
        from litebrowser.ui.dialogs.shell_palette import (
            _build_entries as _build_feature_entries,
        )

        self._feature_entries = _build_feature_entries(self)
        # A plain child overlay (NOT Qt.Popup — that grabs the keyboard and
        # steals typing focus from the omnibar). Outside clicks are closed via
        # the app-level event filter below.
        self._feature_popup = QListWidget(self)
        self._feature_popup.setObjectName("FeaturePopupList")
        self._feature_popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._feature_popup.setUniformItemSizes(True)
        self._feature_popup.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._feature_popup.itemClicked.connect(lambda _item: self._execute_feature_from_popup())
        self._feature_popup.setFocusPolicy(Qt.NoFocus)
        self.omnibar.installEventFilter(self)
        QApplication.instance().installEventFilter(self)
        top_layout.addWidget(self.omnibar, 1)

        # Keyboard-first shell: Ctrl+K jumps to the omnibar, Ctrl+1..7 switch
        # straight to a workspace without touching the mouse.
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._focus_omnibar)
        _workspace_order = ["home", "browser", "history", "ai", "personal", "library", "settings"]
        for _index, _name in enumerate(_workspace_order, start=1):
            _shortcut = QShortcut(QKeySequence("Ctrl+%d" % _index), self)
            _shortcut.activated.connect(lambda _n=_name: self.switch_workspace(_n))

        # Quiet verbs: the two global actions read as ink on paper, not as
        # filled dashboard buttons competing with the workspace.
        self.btn_sync = QPushButton("↻  Snapshot")
        self.btn_sync.setObjectName("QuietButton")
        self.btn_sync.setAccessibleName("Save a local snapshot")
        self.btn_sync.setToolTip("Save a local snapshot of your profile state (tasks/notes/boards) to disk.")
        self.btn_insights = QPushButton("✦  Insights")
        self.btn_insights.setObjectName("QuietButton")
        self.btn_insights.setAccessibleName("Toggle the insights companion")
        self.btn_insights.setToolTip("Show or hide the contextual companion rail")
        top_layout.addWidget(self.btn_sync)
        top_layout.addWidget(self.btn_insights)
        self.btn_toggle_topbar = QPushButton("▾")
        self.btn_toggle_topbar.setObjectName("TopIconButton")
        self.btn_toggle_topbar.setToolTip("Collapse / expand the top bar")
        self.btn_toggle_topbar.clicked.connect(self._toggle_topbar)
        top_layout.addWidget(self.btn_toggle_topbar)
        self._top_bar = top_bar
        shell_layout.addWidget(top_bar)

        # Omnibar hints come from the shared registry (core.commands) — both the
        # description and the example, so hints cannot drift from the palette or
        # the docs.
        from litebrowser.core.commands import hints as _command_hints

        self._command_hints = _command_hints()

        self.split = QSplitter(Qt.Horizontal)
        shell_layout.addWidget(self.split, 1)

        rail = QWidget()
        rail.setObjectName("LeftRail")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(6, 10, 6, 10)
        rail_layout.setSpacing(4)
        # Rail header row: wordmark on the left fills the corner that used to
        # sit empty above the Profile box (with only the collapse toggle on the
        # right), then the profile chip follows below it.
        # Header row = profile · collapse. The "🍵 Mei" wordmark used to open the
        # rail as well, so the brand appeared twice within ~40px (top bar + rail).
        # The rail now answers "where am I", not "which app is this".
        rail_header = QHBoxLayout()
        rail_header.setSpacing(6)
        profile_name = os.path.basename(self.profile_dir)
        rail_title = QLabel("Mei")
        rail_title.setObjectName("RailBrand")
        rail_header.addWidget(rail_title)
        rail_header.addStretch(1)
        self.btn_rail_toggle = QPushButton("«")
        self.btn_rail_toggle.setObjectName("NavToggle")
        self.btn_rail_toggle.setToolTip("Collapse / expand the navigation rail")
        rail_header.addWidget(self.btn_rail_toggle)
        rail_layout.addLayout(rail_header)
        self.rail_meta = QLabel(f"Profile: {profile_name}")
        self.rail_meta.setObjectName("RailProfile")
        self.rail_meta.setToolTip(f"Active profile: {profile_name}")
        rail_layout.addWidget(self.rail_meta)
        self.nav_buttons = {}
        self.rail_section_labels = []
        nav_sections = (
            (
                "START",
                (
                    ("home", "Home", "◧"),
                    ("browser", "Browser", "↗"),
                    ("history", "History", "◷"),
                ),
            ),
            (
                "MAKE & KEEP",
                (
                    ("ai", "AI", "✦"),
                    ("personal", "Personal", "◍"),
                    ("library", "Library", "▤"),
                ),
            ),
            ("SETUP", (("settings", "Settings", "⚙"),)),
        )
        for section_name, section_items in nav_sections:
            section_label = QLabel(section_name)
            section_label.setObjectName("RailSectionLabel")
            self.rail_section_labels.append(section_label)
            rail_layout.addWidget(section_label)
            for key, label, glyph in section_items:
                button = components.nav_button(label, glyph)
                button.clicked.connect(lambda checked, item=key: self.switch_workspace(item))
                self.nav_buttons[key] = button
                rail_layout.addWidget(button)
        # The rail ends at the last navigation item: account/sync state lives in
        # the status strip at the bottom of the window, where it has room for one
        # readable line instead of a two-line box wedged under the nav.
        rail_layout.addStretch(1)
        self._rail = rail
        self.split.addWidget(rail)
        self.split.setHandleWidth(1)

        center_wrap = QWidget()
        center_layout = QVBoxLayout(center_wrap)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(4)
        self.stack = QStackedWidget()
        center_layout.addWidget(self.stack, 1)

        self.status_strip = QWidget()
        self.status_strip.setObjectName("StatusStrip")
        status_layout = QHBoxLayout(self.status_strip)
        status_layout.setContentsMargins(8, 3, 8, 3)
        status_layout.setSpacing(8)
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("StatusPill")
        self.lbl_status_context = QLabel("")
        self.lbl_status_context.setObjectName("MutedLabel")
        status_layout.addWidget(self.lbl_status)
        status_layout.addWidget(self.lbl_status_context)
        status_layout.addStretch(1)
        # Right side: the profile's sync state. It used to repeat the theme name
        # that the left pill already shows, so the theme+accent pair now appears
        # once (left) and the snapshot/account state once (right).
        self.lbl_sync_pill = QLabel("")
        self.lbl_sync_pill.setObjectName("MutedLabel")
        self.lbl_sync_pill.setToolTip(
            "Local snapshot state for this profile — ↻ Snapshot flushes pending changes to disk."
        )
        status_layout.addWidget(self.lbl_sync_pill)
        center_layout.addWidget(self.status_strip)
        self.split.addWidget(center_wrap)

        self.insights = QFrame()
        self.insights.setObjectName("InsightPanel")
        insights_layout = QVBoxLayout(self.insights)
        insights_layout.setContentsMargins(8, 8, 8, 8)
        insights_layout.setSpacing(6)
        # The companion rail opens like a page margin: a mark, a serif title and
        # the day's quiet facts — not a second dashboard of cards.
        insights_layout.addWidget(components.eyebrow("Companion"))
        insights_title = QLabel("At the table")
        insights_title.setObjectName("DeskTitle")
        insights_layout.addWidget(insights_title)
        self.insight_list = QListWidget()
        self.insight_list.setObjectName("CafeList")
        insights_layout.addWidget(self.insight_list, 1)
        sleeping_card = QFrame()
        sleeping_card.setObjectName("SectionCard")
        sleeping_layout = QVBoxLayout(sleeping_card)
        sleeping_layout.setContentsMargins(10, 10, 10, 10)
        sleeping_layout.setSpacing(4)
        sleeping_layout.addWidget(components.section_header("Sleeping tabs", "Set aside to rest"))
        self.sleeping_tabs_list = QListWidget()
        self.sleeping_tabs_list.setObjectName("CafeList")
        sleeping_layout.addWidget(self.sleeping_tabs_list)
        insights_layout.addWidget(sleeping_card)
        assistant_card = QFrame()
        assistant_card.setObjectName("SectionCard")
        assistant_layout = QVBoxLayout(assistant_card)
        assistant_layout.setContentsMargins(10, 10, 10, 10)
        assistant_layout.setSpacing(5)
        assistant_layout.addWidget(components.section_header("Reading nook", "Ask with context"))
        self.lbl_assistant_scope = QLabel("Context: current workspace")
        self.lbl_assistant_scope.setObjectName("MutedLabel")
        assistant_layout.addWidget(self.lbl_assistant_scope)
        self.ed_ai_quick = QLineEdit()
        self.ed_ai_quick.setPlaceholderText("Ask AI from anywhere...")
        assistant_layout.addWidget(self.ed_ai_quick)
        quick_row = QHBoxLayout()
        self.btn_ai_current = QPushButton("Ask here")
        self.btn_ai_global = QPushButton("Whole profile")
        quick_row.addWidget(self.btn_ai_current)
        quick_row.addWidget(self.btn_ai_global)
        assistant_layout.addLayout(quick_row)
        self.ai_preview = QLabel("Assistant replies will open in AI Workspace.")
        self.ai_preview.setWordWrap(True)
        self.ai_preview.setObjectName("MutedLabel")
        assistant_layout.addWidget(self.ai_preview)
        insights_layout.addWidget(assistant_card)
        self.split.addWidget(self.insights)
        # Collapsible(True) let a 0-width setSizes entry permanently collapse
        # the Insights pane - un-draggable afterwards (pre-1.0 layout bug).
        self.split.setChildrenCollapsible(False)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setStretchFactor(2, 0)
        self.split.setSizes([165, 1160, 235])

        self.home_page = HomeDashboardPage(self)
        self.browser_page = SearchWindow(
            self.profile_dir, app_dir=self.app_dir, embedded=True, window_slot=self.window_slot
        )
        self.browser_page.set_workspace_id(self.browser_workspace_id, persist=False)
        self.history_page = HistoryPage(self)
        self.ai_page = AIWindow(self.profile_dir, app_dir=self.app_dir, embedded=True)
        self.personal_page = PersonalWindow(self.profile_dir, app_dir=self.app_dir, embedded=True)
        self.library_page = LibraryPage(self)
        self.settings_page = SettingsPage(self)
        self.settings_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.browser_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.ai_page)
        self.stack.addWidget(self.personal_page)
        self.stack.addWidget(self.library_page)
        self.stack.addWidget(self.settings_page)
        self.workspace_index = {
            "home": 0,
            "browser": 1,
            "history": 2,
            "ai": 3,
            "personal": 4,
            "library": 5,
            "settings": 6,
        }

        self.omnibar.returnPressed.connect(self._on_omnibar_return)
        self.omnibar.textChanged.connect(self._on_omnibar_text_changed)
        self.btn_sync.clicked.connect(self._run_sync_now)
        self.btn_insights.clicked.connect(self.toggle_insights)
        self.btn_rail_toggle.clicked.connect(self._toggle_rail)
        self.btn_ai_current.clicked.connect(lambda: self.ask_ai_from_shell(scope="current"))
        self.btn_ai_global.clicked.connect(lambda: self.ask_ai_from_shell(scope="global"))
        self.ed_ai_quick.returnPressed.connect(lambda: self.ask_ai_from_shell(scope="current"))

        self._restore_window_state()
        # First-run experience: if there is no persisted session, land on the
        # Home dashboard so users see the hub. Restored sessions already open
        # tabs in the Browser workspace conceptually — keep them on Browser.
        has_persisted_tabs = bool(prefs.session_state_load(self.profile_dir).get("tabs"))
        self.switch_workspace("browser" if has_persisted_tabs else "home")
        # Both app windows need the shared stylesheet immediately.  Previously
        # only the primary workspace ran this deferred pass, leaving the second
        # window looking like an unstyled collection of default Qt controls.
        QTimer.singleShot(50, self._deferred_init)
        # Every visible string is selectable/copyable: labels highlight with
        # the mouse, buttons get a right-click "Copy text" menu.
        from litebrowser.ui.textselect import enable_text_selection

        enable_text_selection(self)
        self._refresh_search_icon()

    def _dialog_stylesheet(self):
        """Themed QSS for modal dialogs spawned from the shell (command
        palette, prompts, etc.). Mirrors SearchWindow._dialog_stylesheet."""
        return theme.dialog_qss(prefs.resolved_auto_theme(self.profile_dir), prefs.get_accent(self.profile_dir))

    def _open_omnibar_feature_finder(self):
        """Search-icon click: focus the omnibar and show the full feature list
        so the user can type to filter or pick directly."""
        self.omnibar.setFocus()
        self.omnibar.selectAll()
        self._show_feature_popup(self.omnibar.text().strip())

    def _execute_shell_palette(self, entry: dict):
        """Run a palette result through the normal shell dispatch, so
        password-protected workspaces prompt for the passcode first (via
        switch_workspace) and then enter automatically."""
        kind = entry.get("kind")
        payload = entry.get("payload")
        try:
            if kind == "workspace":
                self.switch_workspace(payload)
            elif kind == "personal_page":
                if self.switch_workspace("personal"):
                    self.personal_page._switch_page(payload)
            elif kind == "site":
                self.switch_workspace("browser")
                self.browser_page.open_bundled_site(payload)
            elif kind == "hub":
                self.switch_workspace("browser")
                self.browser_page.open_project_hub()
            elif kind == "content":
                # A content row is already an ``open_library_item`` payload, so it
                # lands on the note / card / planner row itself.
                self.open_library_item(payload if isinstance(payload, dict) else {})
            elif kind == "command":
                cmd = payload or ""
                if cmd.endswith(" ") or cmd.startswith("/agent "):
                    self.omnibar.setText(cmd)
                    self.omnibar.setFocus()
                    self.omnibar.setCursorPosition(len(cmd))
                else:
                    self.omnibar.setText(cmd)
                    self.handle_omnibar()
        except Exception:
            pass

    def _refresh_search_icon(self):
        """Re-paint the omnibar search glyph in the current theme accent."""
        try:
            from litebrowser.ui.icons import search_icon

            accent = theme.palette_tokens(prefs.resolved_auto_theme(self.profile_dir), prefs.get_accent(self.profile_dir))["ACCENT"]
            self._omnibar_search_action.setIcon(search_icon(accent))
        except Exception:
            pass

    def _on_omnibar_text_changed(self, text: str):
        """Typing in the omnibar drives the inline feature finder: every
        letter (not just a few) filters workspaces, personal pages, sites and
        commands. Slash-commands keep the existing QCompleter behaviour."""
        self._update_omnibar_hint(text)
        stripped = (text or "").strip()
        if not stripped or stripped.startswith("/"):
            self._hide_feature_popup()
            return
        self._show_feature_popup(stripped)

    def _on_omnibar_return(self):
        """Enter: if the feature popup is open and a row is selected, jump to
        that feature; otherwise the normal omnibar dispatch (web search /
        commands)."""
        if self._feature_popup.isVisible() and self._feature_popup.currentRow() >= 0:
            self._execute_feature_from_popup()
            return
        self.handle_omnibar()

    def _show_feature_popup(self, query: str):
        q = (query or "").strip().lower()
        if not self._feature_entries:
            self._hide_feature_popup()
            return
        from litebrowser.ui.dialogs.shell_palette import (
            add_feature_row,
            clear_feature_rows,
            search_entries,
        )

        clear_feature_rows(self._feature_popup)
        base = getattr(self, "profile_dir", None) or ""
        # Features first, then your own records: the same box that jumps to a
        # workspace also finds the note, card or deadline you half-remember.
        rows = search_entries(self._feature_entries, base, q)
        if not rows:
            self._hide_feature_popup()
            return
        visible = rows[:40]
        for entry in visible:
            item = add_feature_row(self._feature_popup, entry, base)
            item.setData(Qt.UserRole, entry)
        self._feature_popup.setCurrentRow(0)
        # Place it under the omnibar, same width, capped height (shell-local
        # coords: this is a plain child widget, not a top-level popup).
        top_left = self.omnibar.mapTo(self, QPoint(0, self.omnibar.height() + 3))
        width = max(320, self.omnibar.width())
        height = min(420, 44 + len(visible) * 34)
        self._feature_popup.setGeometry(QRect(top_left.x(), top_left.y(), width, height))
        if not self._feature_popup.isVisible():
            self._feature_popup.show()
        self._feature_popup.raise_()

    def _hide_feature_popup(self):
        if getattr(self, "_feature_popup", None) is not None and self._feature_popup.isVisible():
            self._feature_popup.hide()

    def _execute_feature_from_popup(self):
        """Run the highlighted feature row: clear the box (unless it was a
        slash command that still needs an argument) and dispatch through the
        normal shell path, which handles passcode-gated workspaces."""
        row = self._feature_popup.currentRow()
        if row < 0 or row >= self._feature_popup.count():
            self._hide_feature_popup()
            return
        # The entry dict is attached to the item when the row is built, so
        # execution does not depend on re-parsing the visible text.
        item = self._feature_popup.item(row)
        entry = item.data(Qt.UserRole) if item is not None else None
        self._hide_feature_popup()
        if not isinstance(entry, dict):
            return
        if entry.get("kind") != "command":
            self.omnibar.clear()
        self._execute_shell_palette(entry)

    def eventFilter(self, obj, ev):
        if obj is QApplication.instance() and ev.type() == QEvent.Type.Quit:
            windows = [window for window in QApplication.topLevelWidgets() if isinstance(window, AppShell) and not window._closing]
            if not all(window.persist_state() for window in windows):
                return True
        # Arrow keys / Esc steer the inline feature popup while it is open.
        if obj is getattr(self, "omnibar", None) and getattr(self, "_feature_popup", None) is not None and self._feature_popup.isVisible():
            if ev.type() == QEvent.Type.KeyPress:
                key = ev.key()
                if key == Qt.Key_Down:
                    self._feature_popup.setCurrentRow(min(self._feature_popup.count() - 1, self._feature_popup.currentRow() + 1))
                    return True
                if key == Qt.Key_Up:
                    self._feature_popup.setCurrentRow(max(0, self._feature_popup.currentRow() - 1))
                    return True
                if key == Qt.Key_Escape:
                    self._hide_feature_popup()
                    return True
        # Outside click (anywhere but the popup or the omnibar) closes it,
        # mimicking the Qt.Popup dismissal without stealing keyboard focus.
        if (
            obj is not self
            and isinstance(obj, QWidget)
            and getattr(self, "_feature_popup", None) is not None
            and self._feature_popup.isVisible()
            and ev.type() == QEvent.Type.MouseButtonPress
        ):
            if obj is self._feature_popup or obj is self.omnibar or self._feature_popup.isAncestorOf(obj):
                return False
            self._hide_feature_popup()
        return super().eventFilter(obj, ev)

    def _announce_focus(self, status: dict):
        """Show the running focus timer state in the status strip."""
        if status.get("running"):
            remaining = int(status.get("remaining", 0))
            mm, ss = divmod(remaining, 60)
            self.lbl_status.setText("🍵 Focus: %02d:%02d left — %s" % (mm, ss, status.get("session", {}).get("label", "")))
        else:
            self.lbl_status.setText("No café focus pour running. Try /focus 25")

    def _run_sync_now(self):
        """Flush the local change ledger: reset the pending counter and stamp the time.

        There is no remote backend in this build -- "sync" here means committing the
        profile's local state to disk and clearing the pending-changes counter that the
        rail displays, so the user gets honest feedback instead of a dead button.
        """
        try:
            state = life_service.load_sync_state(self.profile_dir)
            state["pending_changes"] = 0
            state["last_sync_at"] = int(time.time())
            life_service.save_sync_state(self.profile_dir, state)
            history_service.log_event(self.profile_dir, "account", "Local sync flush", "Pending changes cleared", {})
        except Exception:
            pass
        # A cheap read-back makes the rail reflect the flush immediately.
        self._insight_cache = None
        self.refresh_shell()

    def toggle_insights(self):
        self._insights_user_toggled = True
        self.insights.setVisible(not self.insights.isVisible())
        if self.insights.isVisible():
            theme.animate_entrance(self.insights)
        self._apply_compact_shell_layout()

    def _toggle_rail(self):
        self._rail_collapsed = not getattr(self, "_rail_collapsed", False)
        self._apply_compact_shell_layout()

    def _toggle_topbar(self):
        self._topbar_collapsed = not getattr(self, "_topbar_collapsed", False)
        self._apply_topbar_collapse()

    def _apply_topbar_collapse(self):
        """Hide every top-bar widget except the collapse toggle, then restore."""
        collapsed = getattr(self, "_topbar_collapsed", False)
        if hasattr(self, "btn_toggle_topbar"):
            self.btn_toggle_topbar.setText("▴" if collapsed else "▾")
        top_bar = getattr(self, "_top_bar", None)
        if top_bar is None:
            return
        layout = top_bar.layout()
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item else None
            if widget is not None and widget is not self.btn_toggle_topbar:
                widget.setVisible(not collapsed)
        top_bar.setMaximumHeight(26 if collapsed else 16777215)
        top_bar.setMinimumHeight(24 if collapsed else 0)

    def _update_omnibar_hint(self, text: str):
        parts = (text or "").strip().split(None, 1)
        command = parts[0].lower() if parts else ""
        hint = self._command_hints.get(command)
        if hint:
            self.lbl_status_context.setText(hint)
        elif parts:
            # Only clear when the user is typing a non-command query; keep the
            # last status line otherwise so it does not flicker on every edit.
            self.lbl_status_context.setText("Web search — press Enter")

    def refresh_shell(self, force_deep: bool = False):
        # Distraction Shield follows the focus session; refresh_shell runs on
        # every command + the auto-theme tick, so the shield flips within ~5 min.
        self._refresh_shield_state()
        # Auto theme: the café flips day/night palettes with the clock when on.
        theme_name = prefs.resolved_auto_theme(self.profile_dir)
        # Re-polishing 8 top-level widgets reparses a ~790-line QSS sheet and
        # repaints every child. Only do it when the theme/accent actually
        # changed (v6.4 did it for every omnibar command — visible lag).
        qss_key = (theme_name, prefs.get_accent(self.profile_dir))
        if force_deep or qss_key != getattr(self, "_qss_key", None):
            self._qss_key = qss_key
            self._refresh_search_icon()
            qss = theme.main_qss(theme_name, prefs.get_accent(self.profile_dir))
            self.setStyleSheet(qss)
            for widget in (
                self.home_page,
                self.browser_page,
                self.history_page,
                self.ai_page,
                self.personal_page,
                self.library_page,
                self.settings_page,
            ):
                widget.setStyleSheet(qss)
            # Popups are separate top-levels: keep the tray menu on-theme.
            tray = getattr(self, "tray", None)
            if tray is not None and tray.contextMenu() is not None:
                tray.contextMenu().setStyleSheet(qss)
            # The browser chrome paints part of itself with inline styles (tab
            # rows, connection pill), which a stylesheet re-apply does not reach.
            browser_page = getattr(self, "browser_page", None)
            if browser_page is not None and hasattr(browser_page, "refresh_chrome_theme"):
                browser_page.refresh_chrome_theme()
            self.personal_page._refresh_calendar()
            # Profile-wide appearance applies to every open workspace window.
            for peer in QApplication.topLevelWidgets():
                if isinstance(peer, AppShell) and peer is not self and peer.profile_dir == self.profile_dir and not peer._closing and getattr(peer, "_qss_key", None) != qss_key:
                    peer.refresh_shell()
        self.home_page.refresh()
        self.history_page.refresh()
        self.library_page.refresh(self.library_page.ed_search.text().strip())
        self.settings_page.refresh()
        account = life_service.load_sync_account(self.profile_dir)
        sync_state = life_service.load_sync_state(self.profile_dir)
        pending = int(sync_state.get("pending_changes", 0) or 0)
        status = account.get("display_name") or "Offline-ready"
        self.lbl_status.setText(self._theme_status_text())
        self.lbl_status_context.setText(f"Last sync: {_format_ts(int(sync_state.get('last_sync_at', 0) or 0))}")
        self.lbl_sync_pill.setText(f"{status} · {pending} pending" if pending else status)
        self._refresh_insights()
        self._apply_compact_shell_layout()
        if self.stack.currentIndex() == self.workspace_index["personal"]:
            self.personal_page.refresh_all()

    def _sync_auto_theme_timer(self):
        """Start/stop the auto-theme watcher to match the saved preference."""
        if prefs.get_auto_theme(self.profile_dir) or prefs.get_pref(self.profile_dir, "appearance_mode", "palette") == "system":
            if getattr(self, "_auto_theme_timer", None) is None:
                self._auto_theme_timer = QTimer(self)
                self._auto_theme_timer.timeout.connect(self._check_appearance_change)
            self._auto_theme_timer.setInterval(2000 if prefs.get_pref(self.profile_dir, "appearance_mode", "palette") == "system" else 5 * 60 * 1000)
            self._auto_theme_timer.start()
        elif getattr(self, "_auto_theme_timer", None) is not None:
            self._auto_theme_timer.stop()
        self.refresh_shell()

    def _check_appearance_change(self):
        # Poll only the small preference/OS state, not every list and draft.
        key = (prefs.resolved_auto_theme(self.profile_dir), prefs.get_accent(self.profile_dir))
        if key != getattr(self, "_qss_key", None):
            self.refresh_shell()

    def _deferred_init(self):
        self.refresh_shell()
        if self.window_slot == "primary":
            QTimer.singleShot(1500, self._startup_update_check)
            # First-run wizard: once per profile, skippable at every step.
            if not prefs.get_pref(self.profile_dir, "onboarding_done", False):
                QTimer.singleShot(900, lambda: self._safe_onboarding())
            self._init_tray()
            self._init_break_reminders()
            self._init_study_reminder()
            self._init_routines_timer()
            self._init_page_monitor()

    def _init_page_monitor(self):
        """Poll watched pages every 15 min on the executor (raw HTML hash)."""
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(5 * 60 * 1000)
        self._monitor_timer.timeout.connect(self._check_page_monitors)
        self._monitor_timer.start()
        self._monitor_check_running = False

    def _check_page_monitors(self):
        """Check a small batch off the GUI thread; never queue overlapping runs."""
        if getattr(self, "_closing", False) or getattr(self, "_monitor_check_running", False):
            return
        from litebrowser.services import page_monitor

        due = page_monitor.due_monitors(self.profile_dir)
        if not due:
            return
        # A slow page must not make the timer stack workers: four per tick keeps
        # the executor free for sync/update work and the queue bounded.
        batch = due[:4]
        self._monitor_check_running = True

        def _run():
            outcomes = []
            for monitor in batch:
                result = page_monitor.check_monitor(self.profile_dir, monitor["id"])
                outcomes.append((monitor["title"], result))
            return outcomes

        # Marshal back to the GUI thread via a queued signal (same pattern as
        # update_checked); AppShell has no _worker_relay - that lives on the
        # browser window.
        future = self._executor.submit(_run)
        future.add_done_callback(lambda f: self.monitor_checked.emit(f))

    def _on_monitor_checked(self, future):
        self._monitor_check_running = False
        if self._closing:
            return
        try:
            outcomes = future.result() or []
        except Exception as exc:
            # A crashed worker must not leave the guard stuck forever.
            from litebrowser.core.log import get_logger

            get_logger("app_shell").debug("page monitor worker failed: %s", exc)
            return
        for title, result in outcomes:
            if result.get("status") == "changed":
                self.system_notify("Page changed 📄", title)

    def _init_routines_timer(self):
        """30s scheduler tick — fires due routines once per day each."""
        self._routines_timer = QTimer(self)
        self._routines_timer.setInterval(30 * 1000)
        self._routines_timer.timeout.connect(self._tick_routines)
        self._routines_timer.start()

    def _tick_routines(self):
        from litebrowser.services import routines_service

        for routine in routines_service.due_routines(self.profile_dir):
            routines_service.mark_fired(self.profile_dir, routine["id"], time.strftime("%Y-%m-%d"))
            self.system_notify("Routine: " + routine["name"], " · ".join(routine["actions"][:3]))
            for action in routine["actions"]:
                if action.startswith("/"):
                    self.omnibar.setText(action)
                    self.handle_omnibar()
                elif " " not in action and "." in action:
                    url = action if action.startswith("http") else "https://" + action
                    self.browser_page.add_new_tab(QUrl(url), routine["name"], is_active=False)

    def _init_tray(self):
        """System tray (primary shell only): quick actions + native toasts."""
        try:
            from PyQt5.QtWidgets import QSystemTrayIcon

            if not QSystemTrayIcon.isSystemTrayAvailable():
                return
            from litebrowser.ui.tray import MeiTray

            self.tray = MeiTray(self)
        except Exception:
            self.tray = None
        self._init_global_hotkey()

    def _init_global_hotkey(self):
        """Ctrl+Alt+M anywhere in Windows opens the quick-note overlay.

        Uses RegisterHotKey via ctypes; if the OS refuses (already taken,
        restricted session) we degrade to tray-only — no crash, no nag."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            import ctypes.wintypes

            self._hotkey_msg_id = 0xB00B  # app-local WM_HOTKEY identifier
            MOD_CONTROL, MOD_ALT = 0x0002, 0x0001
            if not ctypes.windll.user32.RegisterHotKey(None, self._hotkey_msg_id, MOD_CONTROL | MOD_ALT, ord("M")):
                self._hotkey_msg_id = None
                return
            # Poll-based check is heavier than a nativeEventFilter, but ctypes
            # callbacks into a Qt app need a message window; a 1s PeekMessage
            # loop on a timer thread is the pragmatic free route.
            self._hotkey_timer = QTimer(self)
            self._hotkey_timer.setInterval(400)

            def _poll():
                # Guard every tick: an exception escaping a Qt slot can abort
                # the whole process (PyQt5 default excepthook policy).
                try:
                    msg = ctypes.wintypes.MSG()
                    while ctypes.windll.user32.PeekMessageW(
                        ctypes.byref(msg), None, 0x0312, 0x0312, 0x0001
                    ):  # PM_REMOVE, WM_HOTKEY range
                        if msg.message == 0x0312 and msg.wParam == self._hotkey_msg_id:
                            self._open_quick_note_overlay()
                except Exception:
                    self._hotkey_timer.stop()

            self._hotkey_timer.timeout.connect(_poll)
            self._hotkey_timer.start()
        except Exception:
            self._hotkey_msg_id = None

    def _open_quick_note_overlay(self):
        """Global quick capture: focus Mei, jump to a fresh note box."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if not self.switch_workspace("personal"):
            return
        page = self.personal_page
        if not page._flush_note_edits():
            return
        note = personal_service.create_note(self.profile_dir, time.strftime("Quick capture %Y-%m-%d %H-%M"), "", "Inbox")
        page._refresh_notes()
        page.select_note(note["id"])
        if hasattr(page, "_switch_page"):
            page._switch_page("notes")
        if hasattr(page, "note_editor"):
            page.note_editor.setFocus()

    def system_notify(self, title: str, message: str):
        """Native toast via the tray when available; in-app toast otherwise."""
        tray = getattr(self, "tray", None)
        if tray is not None and tray.isVisible():
            tray.notify(title, message)
        else:
            self._flash_status(f"{title} — {message}")

    def _init_study_reminder(self):
        """The loop, out loud: Mei starts the recommendation instead of waiting.

        The break timer watches the pour; this one watches the *day* and asks
        ``study_flow`` whether anything is worth a native toast. Prefs hold the
        gap (0 disables it); quiet hours and the silence during a running pour
        are the loop's own rules, so every surface keeps the same manners.
        """
        self._last_study_nudge = 0.0
        self._study_reminder_timer = QTimer(self)
        self._study_reminder_timer.setInterval(60 * 1000)
        self._study_reminder_timer.timeout.connect(self._check_study_reminder)
        self._study_reminder_timer.start()

    def _check_study_reminder(self):
        try:
            minutes = prefs.get_study_reminder_minutes(self.profile_dir)
            if not minutes:
                return
            from litebrowser.services import study_flow

            nudge = study_flow.reminder(
                self.profile_dir, last_sent=self._last_study_nudge, min_gap_minutes=minutes
            )
            if not nudge:
                return
            self._last_study_nudge = time.time()
            self.system_notify(nudge.get("title", "Study loop"), nudge.get("message", ""))
        except Exception as exc:
            # A timer slot that raises can abort the whole process on PyQt5, and a
            # reminder is never worth that: log it and stay quiet until the next tick.
            from litebrowser.core.log import get_logger

            get_logger("app_shell").debug("study reminder failed: %s", exc)

    def run_in_background(self, work, on_done=None):
        """Run blocking work (network, disk sweeps) off the GUI thread.

        ``on_done`` is invoked back on the GUI thread with the finished future,
        which is the only safe way for a page to touch widgets from work that
        had to leave the main thread (Google sign-in, token refresh, sync).
        """
        future = self._executor.submit(work)
        if on_done is not None:
            future.add_done_callback(lambda done: self.background_done.emit(done, on_done))
        return future

    def _deliver_background_result(self, future, callback):
        if self._closing:
            return
        try:
            callback(future)
        except Exception as exc:  # a page callback must never kill the shell
            from litebrowser.core.log import get_logger

            get_logger("app_shell").debug("background callback failed: %s", exc)

    def _init_break_reminders(self):
        """20-20-20 eye rest + a nudge when a focus pour ends (30s check)."""
        self._break_timer = QTimer(self)
        self._break_timer.setInterval(30 * 1000)
        self._break_timer.timeout.connect(self._check_breaks)
        self._break_timer.start()
        self._last_break_nudge = 0

    def _check_breaks(self):
        from litebrowser.services import focus_service

        now = time.time()
        session = focus_service.focus_status(self.profile_dir)
        if session.get("running"):
            remaining = int(session.get("remaining", 0) or 0)
            # A 20-20-20 nudge every 20 minutes inside a long pour.
            if 0 < remaining and (remaining % 1200) < 30 and now - self._last_break_nudge > 300:
                self._last_break_nudge = now
                self.system_notify("Eye break ☕", "Look 20 feet away for 20 seconds.")
        # Pour just finished → celebrate + suggest a stand-up break.
        if getattr(self, "_pour_was_running", False) and not session.get("running"):
            self.system_notify("Pour finished ☕", "Stand up, stretch, refill your cup.")
        self._pour_was_running = bool(session.get("running"))

    def _safe_onboarding(self):
        try:
            from litebrowser.ui.onboarding import show_onboarding

            show_onboarding(self)
        except Exception:
            pass
        # Auto theme watch: refresh_shell re-evaluates resolved_auto_theme; a
        # cheap no-op when the palette is unchanged (signature-keyed re-polish).
        self._sync_auto_theme_timer()

    def _startup_update_check(self):
        # A self-update keeps the previous build as ``.bak`` and downloads a
        # ~170 MB copy of the installer. Sweep both before polling the channel so
        # an update is space-neutral instead of slowly eating the disk.
        try:
            update_service.cleanup_old_artifacts()
        except Exception:
            pass
        self.run_update_check(manual=False)

    def open_release_page(self, url: str | None = None):
        target = (url or app_version.RELEASES_PAGE_URL or "").strip()
        if not target:
            QMessageBox.information(
                self,
                "Updates",
                "No release page is configured in this build. "
                "Set LITEBROWSER_RELEASES_PAGE_URL when publishing a fork.",
            )
            return
        webbrowser.open(target)

    def run_update_check(self, manual: bool = False):
        if self._update_check_running:
            if manual:
                QMessageBox.information(self, "Update", "Mei is already checking for updates. Please wait a few seconds and try again.")
            return
        self._update_check_running = True
        self.update_status_text = "Checking for updates..."
        self.refresh_shell()
        future = self._executor.submit(update_service.check_for_updates)
        future.add_done_callback(lambda done: self.update_checked.emit(done, manual))

    def install_available_update(self):
        info = self._pending_update_info
        if not info or not info.has_update:
            QMessageBox.information(self, "Update", "There is no update package ready to install yet.")
            return
        if self._update_install_running:
            QMessageBox.information(self, "Update", "Mei is already downloading the update.")
            return
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self,
                "Update",
                "Auto-update that replaces the executable only works in a built .exe. The Python version can only open the release page.",
            )
            self.open_release_page(info.release_url or info.download_url)
            return
        self._update_install_running = True
        self.update_status_text = f"Downloading {info.latest_version} — verifying before install..."
        self.refresh_shell()
        future = self._executor.submit(
            update_service.download_update_package,
            info.download_url,
            info.latest_version,
            info.sha256,
            info.size,
            progress_callback=lambda received, total: self.update_progress.emit(received, total),
        )
        future.add_done_callback(lambda done: self.update_downloaded.emit(done, info))

    def _on_update_progress(self, received: int, total: int):
        if self._closing:
            return
        received = max(0, int(received or 0))
        total = max(0, int(total or 0))
        if not received and not total:
            return
        if total:
            percent = min(100, int(received * 100 / total))
            text = (
                f"Downloading update — {percent}% "
                f"({received / (1024 * 1024):.1f} of {total / (1024 * 1024):.1f} MB). "
                "Verifying after download."
            )
        else:
            text = (
                f"Downloading update — {received / (1024 * 1024):.1f} MB. "
                "Verifying after download."
            )
        if text != self.update_status_text:
            self.update_status_text = text
            self.refresh_shell()

    def _finish_update_check(self, future, manual: bool):
        if self._closing:
            return
        self._update_check_running = False
        try:
            info = future.result() if future is not None else None
        except Exception as exc:
            self.update_status_text = update_service.format_error(exc)
            self.refresh_shell()
            if manual:
                QMessageBox.warning(self, "Update", self.update_status_text)
            return
        if info is None:
            return

        if info.has_update:
            self._pending_update_info = info
            published = f"\nPublished: {info.published_at}" if info.published_at else ""
            notes = f"\n\nNotes:\n{info.notes}" if info.notes else ""
            safe_url = update_service.redact_url(info.download_url)
            self.update_status_text = f"A new version {info.latest_version} is available. You are on {info.current_version}."
            self.refresh_shell()
            # Startup checks are automatic: default to "No" so a stray Enter can
            # never start replacing the executable. Only an explicit
            # "Check for updates" pre-selects Yes.
            default_button = QMessageBox.Yes if manual else QMessageBox.No
            result = QMessageBox.question(
                self,
                "Update available",
                f"Mei {info.latest_version} is available.{published}\nDownload: {safe_url}{notes}\n\nDownload and install now?",
                QMessageBox.Yes | QMessageBox.No,
                default_button,
            )
            if result == QMessageBox.Yes:
                self.install_available_update()
            return

        self._pending_update_info = info
        self.update_status_text = f"You are on the latest version ({info.current_version})."
        self.refresh_shell()
        if manual:
            QMessageBox.information(self, "Update", self.update_status_text)

    def _finish_downloaded_update(self, future, info):
        if self._closing:
            return
        self._update_install_running = False
        try:
            package_path = future.result() if future is not None else None
        except Exception as exc:
            self.update_status_text = update_service.format_error(exc)
            self.refresh_shell()
            QMessageBox.warning(self, "Update", self.update_status_text)
            return
        if package_path is None:
            return

        windows = [window for window in QApplication.topLevelWidgets() if isinstance(window, AppShell) and not window._closing]
        if not all(window.persist_state() for window in windows):
            self.update_status_text = "Update downloaded. Save your pending edits before installing."
            return
        self.update_status_text = f"Update {info.latest_version} verified. Applying update..."
        self.refresh_shell()
        try:
            update_service.install_downloaded_update(
                package_path, update_service.local_channel_packages(), info.sha256, info.size
            )
        except Exception as exc:
            self.update_status_text = update_service.format_error(exc)
            self.refresh_shell()
            QMessageBox.warning(self, "Update", self.update_status_text)
            return

        QMessageBox.information(
            self,
            "Update",
            "Mei will close to replace the new .exe, then reopen automatically. Your current session will be saved before quitting.",
        )
        QApplication.instance().quit()

    def _refresh_insights(self):
        if self._private_locked or security.has_passcode(self.profile_dir) and not (security.is_unlocked(self.profile_dir) or self._unlocked_spaces):
            self.insight_list.clear()
            self.insight_list.addItem("Unlock Personal to see your private workspace")
            self.ai_preview.clear()
            self._insight_cache = None
            return
        now = time.time()
        if self._insight_cache and (now - self._insight_cache_time) < 10:
            cached_snap, cached_texts = self._insight_cache
            self.insight_list.clear()
            for text in cached_texts:
                self.insight_list.addItem(text)
            self.sleeping_tabs_list.clear()
            self.lbl_assistant_scope.setText(f"Context: {self._current_ai_scope_label()}")
            return
        self.insight_list.clear()
        try:
            snapshot = life_service.get_dashboard_snapshot(self.profile_dir)
        except Exception:
            snapshot = {"tasks_pending": 0, "events_upcoming": [], "saved_pages_total": 0}
        suggestions = [
            f"{snapshot['tasks_pending']} pending tasks",
            f"{len(snapshot['events_upcoming'])} upcoming events",
            f"{snapshot['saved_pages_total']} saved pages",
            "/task <title> to create a task",
            "/note <cat>/<title> to create a note",
            "/ask <question> for AI help",
            "/guide for walkthrough",
        ]
        # Insight AI on: surface the page currently open in the browser so the
        # user sees the assistant can read it (its full text is attached to
        # every /ask while the insights panel is visible).
        if self.insights.isVisible():
            browser = self.browser_page.current_browser()
            if browser is not None:
                url = browser.url().toString()
                if url and url not in ("about:blank", "about:newtab"):
                    title = browser.title() or url
                    suggestions.insert(0, f"Reading browser: {title}")
                    suggestions.insert(1, f"Full page text ready for AI · {url[:56]}")
        for text in suggestions:
            self.insight_list.addItem(text)
        self._insight_cache = (snapshot, suggestions)
        self._insight_cache_time = now
        self.sleeping_tabs_list.clear()
        self.lbl_assistant_scope.setText(f"Context: {self._current_ai_scope_label()}")

    def _window_prefs_key(self):
        return "shell_window_primary" if self.window_slot == "primary" else "shell_window_secondary"

    def _restore_window_state(self):
        pref_key = self._window_prefs_key()
        prefs_data = prefs.load_prefs(self.profile_dir)
        state = prefs_data.get(pref_key, {})
        if isinstance(state, dict):
            x = state.get("x")
            y = state.get("y")
            w = state.get("width")
            h = state.get("height")
            if all(isinstance(v, int) for v in (x, y, w, h)):
                # Validate against current screens: after a monitor change the
                # saved geometry could be off-screen entirely (invisible window).
                visible = False
                for screen in QApplication.screens():
                    if screen.availableGeometry().intersects(QRect(x, y, max(w, 1), max(h, 1))):
                        visible = True
                        break
                if visible:
                    self.setGeometry(x, y, w, h)
                    return
        screen = self.screen()
        if not screen:
            return
        available = screen.availableGeometry()
        left_width = available.width() // 2
        right_width = available.width() - left_width
        if self.window_slot == "primary":
            self.setGeometry(available.x(), available.y(), left_width, available.height())
        else:
            self.setGeometry(available.x() + left_width, available.y(), right_width, available.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only re-run the full compact pass when a size class boundary is
        # crossed; v6.4 re-set the splitter and ~15 widget properties on every
        # pixel of a window drag, fighting any manual splitter adjustment.
        width = max(0, self.width())
        bucket = 680 if width < 680 else 900 if width < 900 else 1080 if width < 1080 else 1320 if width < 1320 else 1 << 30
        if bucket != getattr(self, "_compact_bucket", None):
            self._compact_bucket = bucket
            self._apply_compact_shell_layout()

    def _apply_compact_shell_layout(self):
        width = max(0, self.width())
        compact = width < 1320
        narrow = width < 1080
        tiny = width < 900
        xtiny = width < 680
        rail_collapsed = getattr(self, "_rail_collapsed", False)

        rail_width = 46 if rail_collapsed else (62 if xtiny else 92 if tiny else 108 if narrow else 124 if compact else 146)
        # A visible Insights panel keeps its width even in the Browser workspace
        # once the user toggled it on, so "enable AI insights" works while browsing.
        insight_visible = self.insights.isVisible()
        insight_width = 0 if not insight_visible else (120 if xtiny else 140 if tiny else 160 if narrow else 185 if compact else 205)
        middle_width = max(320, width - rail_width - insight_width - 18)
        # Only push sizes when something structural changed (rail collapse /
        # expand, Insights visibility, or a size-class boundary); a blind
        # setSizes on every call fought the user's splitter drags and, with
        # setChildrenCollapsible(True), a 0-width entry could COLLAPSE a pane
        # entirely - dragging it afterwards was impossible (pre-1.0 bug).
        # Tracking only the Insights flag (as an earlier fix did) left the rail
        # toggle with no way to push its new width, so the rail would not
        # compress or expand at all.
        layout_key = (
            rail_collapsed,
            insight_visible,
            getattr(self, "_compact_bucket", None),
        )
        if layout_key != getattr(self, "_last_shell_layout_key", None):
            self._last_shell_layout_key = layout_key
            self.split.setSizes([rail_width, middle_width, insight_width])
        self.split.setChildrenCollapsible(False)

        if hasattr(self, "btn_rail_toggle"):
            self.btn_rail_toggle.setText("»" if rail_collapsed else "«")
        self.omnibar.setMinimumHeight(26 if xtiny else 30 if tiny else 34 if narrow else 36)
        # Keep the top-bar actions exactly as tall as the search field: the row is
        # one line of controls, not three pills of slightly different heights.
        bar_height = self.omnibar.minimumHeight()
        for control in (self.btn_sync, self.btn_insights, self.btn_toggle_topbar):
            control.setMinimumHeight(bar_height)
            control.setMaximumHeight(bar_height)
        self.btn_sync.setText("↻" if tiny else "↻  Snapshot")
        self.btn_insights.setText("✦" if tiny else "✦  Insights")
        self.lbl_status_context.setVisible(not tiny)
        self.lbl_sync_pill.setVisible(not narrow)
        self.lbl_status.setVisible(not xtiny)
        self.omnibar.setPlaceholderText("Search / command..." if not tiny else "Go...")
        self.rail_meta.setVisible(not rail_collapsed and not xtiny)
        for section_label in self.rail_section_labels:
            section_label.setVisible(not tiny and not rail_collapsed)

        for key, button in self.nav_buttons.items():
            labels = {"home": ("Home", "◧"), "browser": ("Browser", "↗"), "history": ("History", "◷"), "ai": ("AI", "◈"), "personal": ("Personal", "◍"), "library": ("Library", "▤"), "settings": ("Settings", "⚙")}
            name, glyph = labels.get(key, (key, "◆"))
            button.setVisible(True)
            button.setAccessibleName(name)
            button.setToolTip(name)
            icon_only = rail_collapsed or xtiny or tiny
            if icon_only:
                button.setText(glyph)
            else:
                # Three spaces reserve one glyph column so every label starts on
                # the same vertical line — the rail reads as a spine, not a list.
                button.setText(glyph + "   " + name)
            # A glyph-only rail needs a larger mark and true centring; at 12px
            # left aligned the spine read as a column of dust at small widths.
            if bool(button.property("iconOnly")) != icon_only:
                button.setProperty("iconOnly", icon_only)
                style = button.style()
                if style is not None:
                    style.unpolish(button)
                    style.polish(button)
            button.setMinimumHeight(32)
            button.setMaximumHeight(38)

        self.btn_ai_global.setVisible(not tiny)
        self.ai_preview.setVisible(not narrow)
        self.insight_list.setSpacing(1)
        self.sleeping_tabs_list.setSpacing(1)

    def _save_window_state(self):
        geom = self.geometry()
        prefs.save_pref(self.profile_dir, self._window_prefs_key(), {
            "x": int(geom.x()),
            "y": int(geom.y()),
            "width": int(geom.width()),
            "height": int(geom.height()),
        })

    def set_sleeping_tabs(self, titles):
        self.sleeping_tabs_list.clear()
        titles = list(titles or [])
        if not titles:
            self.sleeping_tabs_list.addItem("No sleeping tabs")
            return
        for title in titles[:12]:
            self.sleeping_tabs_list.addItem(title)

    def _relock_private_spaces(self):
        self._unlocked_spaces.clear()
        self._private_locked = True
        if not hasattr(self, "stack"):
            return
        # Save pending local edits before hiding private views in every window.
        self.personal_page._flush_note_edits()
        if self.stack.currentWidget() in (self.personal_page, self.ai_page, self.library_page):
            self.switch_workspace("home")
        self.insights.hide()
        self.ai_preview.clear()
        self._insight_cache = None
        self.ai_page.relock()
        self.home_page.refresh()
        self.history_page.refresh()

    def switch_workspace(self, name: str) -> bool:
        if name not in self.workspace_index:
            # Unknown workspace names must not raise inside a UI slot.
            return False
        # Never leave the inline feature list floating over another screen.
        self._hide_feature_popup()
        current_name = next((key for key, index in self.workspace_index.items() if index == self.stack.currentIndex()), "")
        if current_name in ("ai", "personal", "library") and name != current_name and not security.is_unlocked(self.profile_dir):
            self._unlocked_spaces.discard(current_name)
        if name in ("ai", "personal", "library") and name not in self._unlocked_spaces:
            if not security.ensure_unlocked(self, self.profile_dir, title=f"Open {name.title()}"):
                return False
            self._unlocked_spaces.add(name)
            self._private_locked = False
            self.ai_page._privacy_locked = False
            self.home_page.refresh()
        previous = self.stack.currentIndex()
        self.stack.setCurrentIndex(self.workspace_index[name])
        for key, button in self.nav_buttons.items():
            button.setChecked(key == name)
        self.lbl_status.setText(f"Workspace: {name}")
        if name == "library":
            self.library_page.refresh(self.library_page.ed_search.text().strip())
        if name == "history":
            self.history_page.refresh()
        if name == "settings":
            self.settings_page.refresh()
        if name == "personal":
            self.personal_page.refresh_all()
        if name == "browser":
            # Keep browsing full-width on first launch, but respect the user's
            # explicit "✦ Insights" toggle (insight AI reads the browser page).
            if not getattr(self, "_insights_user_toggled", False):
                self.insights.hide()
        elif self.width() < 1180:
            self.insights.hide()
        # The insights list reflects the current workspace + browser page, so
        # drop the cache on every workspace switch and rebuild it when visible.
        self._insight_cache = None
        if self.insights.isVisible():
            self._refresh_insights()
        if previous != self.stack.currentIndex() and name != "browser":  # #[c] avoid compositing a QWebEngine surface.
            theme.animate_entrance(self.stack.currentWidget())
        self._apply_compact_shell_layout()
        return True

    def current_browser_widget(self):
        return self.browser_page

    def quick_task_dialog(self):
        title = self.omnibar.text().strip() or "Quick task"
        if title.startswith("/task"):
            title = title[5:].strip() or "Quick task"
        life_service.add_task(self.profile_dir, title)
        self.refresh_shell()
        self.switch_workspace("personal")
        QMessageBox.information(self, "Task", f"Created task: {title}")

    def _quick_capture_context(self) -> dict:
        """Read optional page context without carrying private-tab data across."""
        from litebrowser.services import tab_sets

        research = tab_sets.get_active_research_workspace(self.profile_dir)
        research_title = research.get("title", "") if research else ""
        browser = self.browser_page.current_browser()
        if browser is None:
            return {"research_workspace_title": research_title} if research_title else {}
        try:
            profile = browser.page().profile()
            if profile is None or profile.isOffTheRecord():
                return {"private": True}
            return {
                "title": browser.title() or "",
                "url": browser.url().toString() or "",
                "selected_text": browser.selectedText() or "",
                "research_workspace_title": research_title,
            }
        except (AttributeError, RuntimeError):
            # If privacy state cannot be verified, do not attach page contents.
            return {"private": True}

    def open_quick_capture(self):
        """Open the review-first capture flow and save through existing stores."""
        from litebrowser.services import flashcard_service, tab_sets
        from litebrowser.ui.dialogs.quick_capture import QuickCaptureDialog

        dialog = QuickCaptureDialog(self.profile_dir, self._quick_capture_context(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.capture_payload
        if not payload:
            return
        kind = payload["kind"]
        research = tab_sets.get_active_research_workspace(self.profile_dir)
        reference_type = {"note": "note", "task": "task", "link": "saved_page", "flashcard": "flashcard"}.get(kind)
        reference_id = ""
        try:
            if kind == "note":
                item = personal_service.create_note(
                    self.profile_dir,
                    payload["title"],
                    payload["content"] or f"# {payload['title']}\n\n",
                    category=payload["category"],
                )
                reference_id = str(item.get("id") or "")
                self.refresh_shell()
                if self.switch_workspace("personal"):
                    self.personal_page.select_note(item["id"])
            elif kind == "task":
                item = life_service.add_task(self.profile_dir, payload["title"], notes=payload["notes"] or None)
                reference_id = str(item.get("id") or "")
                self.refresh_shell()
                if self.switch_workspace("personal"):
                    self.personal_page._switch_page("tasks")
            elif kind == "link":
                item = life_service.add_saved_page(self.profile_dir, payload["title"], payload["url"])
                reference_id = str(item.get("id") or "")
                self.refresh_shell()
                self.switch_workspace("library")
            else:
                item = flashcard_service.add_card(self.profile_dir, payload["front"], payload["back"])
                reference_id = str(item.get("id") or "")
                self.refresh_shell()
                if self.switch_workspace("personal"):
                    self.personal_page._switch_page("review")
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Quick capture", f"The capture could not be saved:\n{exc}")
            return
        if research and reference_type and reference_id:
            try:
                linked = tab_sets.add_research_reference(
                    self.profile_dir, research["id"], reference_type, reference_id
                )
            except (OSError, ValueError, RuntimeError):
                linked = False
            if not linked:
                QMessageBox.warning(
                    self,
                    "Quick capture",
                    f"The {kind} was saved, but could not be linked to research workspace “{research['title']}”.",
                )
            else:
                self.refresh_shell()
        self._insight_cache = None
        self._flash_status(f"Saved {kind}")

    def _focus_omnibar(self):
        """Ctrl+K: focus AND select existing text so typing replaces it (the
        v6.4 binding left the caret mid-string with stale text selected)."""
        self.omnibar.setFocus()
        self.omnibar.selectAll()

    def _normalize_omnibar_cmd(self, text: str):
        return text.lower().strip()

    def _sync_now_worker(self, profile_dir, endpoint, token):
        from litebrowser.services import sync_service

        try:
            ok, msg = sync_service.sync_now(profile_dir, endpoint, token)
        except Exception as exc:
            ok, msg = False, f"Sync failed: {exc}"
        self.sync_finished.emit(bool(ok), str(msg))

    def _show_sync_result(self, ok: bool, msg: str):
        if self._closing:
            return
        self.lbl_status_context.setText(f"Last sync: {time.strftime('%H:%M:%S')}")
        QMessageBox.information(self, "Sync", msg)

    def _theme_status_text(self) -> str:
        """Theme + accent in one indicator — they belong together and the pair
        used to be printed twice (left pill and right side of the status strip)."""
        return f"● {prefs.resolved_auto_theme(self.profile_dir)} · {prefs.get_accent(self.profile_dir)}"

    def _refresh_shield_state(self):
        """Push the current shield (focus running / always-on) into every
        TrackingBlocker instance in this shell."""
        for page in (self.browser_page,):
            for interceptor in [getattr(page, "interceptor", None)] + list(getattr(page, "_incognito_interceptors", []) or []):
                if interceptor is not None:
                    try:
                        interceptor._reload_shield_state()
                    except Exception:
                        pass

    def _flash_status(self, message: str):
        """Transient status-line feedback (mirrors SearchWindow's toast but
        lands in the shell's status strip instead)."""
        self.lbl_status.setText(f"● {message}")
        if getattr(self, "_status_restore_timer", None) is None:
            self._status_restore_timer = QTimer(self)
            self._status_restore_timer.setSingleShot(True)
            self._status_restore_timer.timeout.connect(lambda: self.lbl_status.setText(self._theme_status_text()))
        self._status_restore_timer.start(3000)

    def _match_cmd(self, lowered: str, cmd: str) -> bool:
        """Exact command or command-with-argument; never a prefix of a longer
        command (v6.4: ``/brief`` also matched ``/briefcase``, ``/sync`` ate
        ``/syncfoo``)."""
        return lowered == cmd or lowered.startswith(cmd + " ")

    def handle_omnibar(self):
        try:
            text = (self.omnibar.text() or "").strip()
            if not text:
                return
            self._handle_omnibar_text(text)
        finally:
            # Always clear so the next Enter does not re-run the previous command —
            # otherwise typing ``/task buy milk /task ship report`` fires only once
            # and each following Return keeps re-submitting stale text.
            self.omnibar.clear()

    def _handle_omnibar_text(self, text: str):
        lowered = self._normalize_omnibar_cmd(text)
        private_commands = ("/task", "/note", "/capture", "/board", "/review", "/template", "/cafe", "/agent", "/export")
        if any(self._match_cmd(lowered, cmd) for cmd in private_commands):
            if not self.switch_workspace("personal"):
                return
        if lowered in ("/home", "/browser", "/history", "/ai", "/personal", "/library", "/settings"):
            self.switch_workspace(lowered[1:])
            return
        if lowered in ("/cql", "/cuc-quan-ly", "/cu", "/cuc", "/quanly", "/quan-ly"):
            self.switch_workspace("browser")
            self.browser_page.open_bundled_site("cucquanly")
            return
        if lowered in ("/linklumina", "/link", "/lum"):
            self.switch_workspace("browser")
            self.browser_page.open_bundled_site("linklumina")
            return
        if lowered in ("/mas", "/mahoraga", "/adapt"):
            self.switch_workspace("browser")
            self.browser_page.open_bundled_site("mas")
            return
        if lowered in ("/leaderboard", "/rank", "/world"):
            self.switch_workspace("browser")
            self.browser_page.open_bundled_site("worldleaderboard")
            return
        if lowered in ("/bimat", "/personalfrequency", "/personal-frequency"):
            self.switch_workspace("browser")
            self.browser_page.open_bundled_site("bimat")
            return
        if lowered in ("/boitoan", "/boi-toan", "/fortune"):
            self.switch_workspace("browser")
            self.browser_page.open_bundled_site("boitoan")
            return
        if lowered in ("/hub", "/chain", "/projects"):
            self.switch_workspace("browser")
            self.browser_page.open_project_hub()
            return
        if lowered in ("/guide", "/help"):
            dialogs.show_browser_control_center(self.browser_page)
            return
        if lowered == "/capture":
            self.open_quick_capture()
            return
        if lowered == "/ask" or lowered.startswith("/ask "):
            question = text[4:].strip() or "Summarize my current context"
            self.ask_ai_from_shell(scope="current", question=question)
            return
        if lowered == "/task" or lowered.startswith("/task "):
            title = text[5:].strip() or "Quick task"
            life_service.add_task(self.profile_dir, title)
            self._insight_cache = None
            self.refresh_shell()
            self.switch_workspace("personal")
            return
        if lowered == "/note" or lowered.startswith("/note "):
            raw_note = text[5:].strip()
            category = "General"
            title = raw_note or "Untitled note"
            body = ""
            if "|" in raw_note:
                parts = [part.strip() for part in raw_note.split("|")]
                if len(parts) >= 2:
                    category = parts[0] or "General"
                    title = parts[1] or "Untitled note"
                if len(parts) >= 3:
                    body = parts[2]
            elif "/" in raw_note:
                prefix, suffix = raw_note.split("/", 1)
                if prefix.strip() and suffix.strip():
                    category = prefix.strip()
                    title = suffix.strip()
            note = personal_service.create_note(
                self.profile_dir,
                title,
                body or f"# {title}\n\n",
                category=category,
            )
            self._insight_cache = None
            self.refresh_shell()
            self.switch_workspace("personal")
            self.personal_page.select_note(note["id"])
            return
        if lowered == "/board" or lowered.startswith("/board "):
            title = text[6:].strip() or "Idea board"
            life_service.add_board(self.profile_dir, title)
            self._insight_cache = None
            self.refresh_shell()
            self.switch_workspace("personal")
            return
        if self._match_cmd(lowered, "/brief"):
            from litebrowser.services import brief_service
            brief = brief_service.build_morning_brief(self.profile_dir)
            QMessageBox.information(self, "Morning Brief", brief_service.brief_text(brief))
            self.switch_workspace("home")
            return
        if self._match_cmd(lowered, "/flow"):
            from litebrowser.services import study_flow
            flow = study_flow.build_flow(self.profile_dir)
            lines = [f"{step['title']} — {step['detail']}" for step in flow["steps"]]
            lines.append("")
            lines.append(f"Next — {flow['next']['label']}")
            lines.append(flow["next"]["reason"])
            QMessageBox.information(self, "Study loop", "\n".join(lines))
            self.open_flow_step(flow["next"])
            return
        if lowered == "/agent" or lowered.startswith("/agent "):
            from litebrowser.services import agent_actions
            arg = text[len("/agent"):].strip()
            if arg == "summary" or arg.startswith("summary"):
                browser = self.current_browser_widget()
                tabs = browser.get_current_tab_state()
                note = agent_actions.summarize_tabs_to_note(self.profile_dir, tabs)
                self.switch_workspace("personal")
                self.personal_page.select_note(note["id"])
            elif arg == "tasks" or arg.startswith("tasks"):
                created = agent_actions.extract_tasks_from_text(self.profile_dir, arg[len("tasks"):].strip())
                self.switch_workspace("personal")
                QMessageBox.information(self, "Agent", "Created %d task(s)." % len(created))
            elif arg == "review" or arg.startswith("review"):
                content = agent_actions.weekly_review(self.profile_dir)
                note = personal_service.create_note(
                    self.profile_dir, "Weekly review %s" % time.strftime("%Y-%m-%d"), content, category="AI"
                )
                self.switch_workspace("personal")
                self.personal_page.select_note(note["id"])
            else:
                QMessageBox.information(
                    self, "Agent",
                    "Commands:\n/agent summary — digest open tabs into a note\n/agent tasks <a | b | c> — turn items into tasks\n/agent review — write a weekly review note",
                )
            return
        if self._match_cmd(lowered, "/sync"):
            endpoint = prefs.get_sync_endpoint(self.profile_dir)
            token = prefs.get_sync_token(self.profile_dir)
            # sync_now does two HTTP round-trips (up to ~30 s); never freeze
            # the GUI thread waiting on the network (v6.4 froze the shell).
            self.lbl_status_context.setText("Syncing...")
            self._executor.submit(self._sync_now_worker, self.profile_dir, endpoint, token)
            return
        if self._match_cmd(lowered, "/group-tabs"):
            self.switch_workspace("browser")
            self.browser_page.group_tabs_action()
            return
        if self._match_cmd(lowered, "/save-page"):
            browser = self.current_browser_widget().current_browser()
            if browser:
                life_service.add_saved_page(self.profile_dir, browser.title() or browser.url().toString(), browser.url().toString())
                self._insight_cache = None
                self.refresh_shell()
            return
        if self._match_cmd(lowered, "/freeze"):
            self.switch_workspace("browser")
            self.browser_page.tab_manager.optimize_memory()
            return
        if lowered == "/save-tabs" or lowered.startswith("/save-tabs "):
            name = text[len("/save-tabs"):].strip() or None
            self.switch_workspace("browser")
            self.browser_page.save_tab_set_named(name)
            return
        if lowered == "/summarize" or lowered.startswith("/summarize "):
            browser = self.current_browser_widget().current_browser()
            if not browser:
                return
            if self.insights.isVisible():
                # Insight AI is on: it already reads the whole browser page, so
                # asking for a summary needs no duplicate text grab.
                self.ask_ai_from_shell(scope="current", question="Briefly summarize this webpage.")
                return

            def _summarize_page(page_text):
                body = (page_text or "").strip()
                if not body:
                    QMessageBox.information(self, "Summarize", "No readable text on this page.")
                    return
                self.ask_ai_from_shell(
                    scope="current",
                    question="Briefly summarize this webpage:\n\n" + body[:6000],
                )

            browser.page().toPlainText(_summarize_page)
            return
        if lowered in ("/read", "/reading-list"):
            self.switch_workspace("browser")
            return
        if self._match_cmd(lowered, "/status"):
            from litebrowser.services import focus_service
            status = focus_service.focus_status(self.profile_dir)
            self._announce_focus(status)
            return
        if self._match_cmd(lowered, "/theme"):
            arg = text[len("/theme"):].strip().lower()
            if not arg:
                themes = ", ".join(sorted(theme.PALETTES.keys()))
                QMessageBox.information(self, "Themes", f"Available themes:\n{themes}\n\nUsage: /theme matcha-day")
                return
            if arg in theme.PALETTES:
                prefs.set_shell_theme(self.profile_dir, arg)
                prefs.save_pref(self.profile_dir, "appearance_mode", "palette")
                self._qss_key = None  # force the QSS re-polish
                self.refresh_shell()
                self._flash_status(f"Theme: {theme.theme_display_name(arg)}")
            else:
                QMessageBox.warning(self, "Themes", f"Unknown theme '{arg}'.\n\nAvailable: {', '.join(sorted(theme.PALETTES.keys()))}")
            return
        if self._match_cmd(lowered, "/accent"):
            arg = text[len("/accent"):].strip().lower()
            if not arg:
                accents = ", ".join(sorted(theme.ACCENTS.keys()))
                QMessageBox.information(self, "Accents", f"Available accents:\n{accents}\n\nUsage: /accent matcha")
                return
            if theme.valid_accent(arg):
                prefs.set_accent(self.profile_dir, arg)
                self._qss_key = None
                self.refresh_shell()
                self._flash_status(f"Accent: {theme.accent_display_name(arg)}")
            else:
                QMessageBox.warning(self, "Accents", f"Unknown accent '{arg}'.\n\nAvailable: {', '.join(sorted(theme.ACCENTS.keys()))}")
            return
        if self._match_cmd(lowered, "/cafe"):
            from litebrowser.services import focus_service
            self.switch_workspace("personal")
            session = focus_service.focus_status(self.profile_dir)
            if session.get("running"):
                QMessageBox.information(
                    self, "Café Focus",
                    "A pour is running (%d min left). Use /focus N to start fresh, /status to poll." % (session.get("remaining", 0) // 60),
                )
            else:
                QMessageBox.information(
                    self, "Café Focus",
                    "Welcome to the café.\n/focus 25 — start a 25 min pour\n/status — check the timer\nRecent pours: %d" % len(focus_service.focus_journal(self.profile_dir)),
                )
            return
        if self._match_cmd(lowered, "/review"):
            self.switch_workspace("personal")
            self.personal_page._switch_page("review")
            return
        if self._match_cmd(lowered, "/routines"):
            dialogs.show_routines_dialog(self)
            return
        if self._match_cmd(lowered, "/export"):
            dialogs.show_export_dialog(self)
            return
        if self._match_cmd(lowered, "/template"):
            from litebrowser.services import note_templates

            arg = text[len("/template"):].strip().lower()
            if arg in ("daily", "day"):
                note = note_templates.create_daily_note(self.profile_dir)
            elif arg in ("weekly", "review"):
                note = note_templates.create_weekly_review(self.profile_dir)
            else:
                QMessageBox.information(
                    self, "Templates",
                    "Usage: /template daily   — today's plan (tasks, events, top sites)\n"
                    "/template weekly   — last-7-days review",
                )
                return
            self._insight_cache = None
            self.refresh_shell()
            self.switch_workspace("personal")
            self.personal_page.select_note(note["id"])
            return
        if lowered == "/focus" or lowered.startswith("/focus "):
            from litebrowser.services import focus_service
            raw = text[len("/focus"):].strip()
            minutes = 25
            label = ""
            for token in raw.split():
                if token.isdigit():
                    minutes = int(token)
                else:
                    label = (label + " " + token).strip()
            session = focus_service.start_focus(self.profile_dir, minutes=minutes, label=label)
            self._refresh_shield_state()
            self._insight_cache = None
            self.refresh_shell()
            QMessageBox.information(
                self, "Café Focus",
                "Pour started — %d min «%s».\nUse /status to check remaining time." % (minutes, session.get("label", "")),
            )
            return
        if text.startswith("http://") or text.startswith("https://") or (" " not in text and "." in text):
            self.switch_workspace("browser")
            self.browser_page.url_bar.setText(text)
            self.browser_page.navigate()
            return
        self.library_page.refresh(text)
        self.switch_workspace("library")

    def open_library_item(self, data: dict):
        kind = data.get("kind", "")
        if kind == "research_workspace":
            if not self.switch_workspace("browser"):
                return
            self.browser_page.restore_tab_set(data.get("id", ""), mode="merge")
            return
        if kind in ("bookmark", "history", "download", "saved-page", "personal_site"):
            target = data.get("subtitle") or data.get("id") or data.get("target") or ""
            if target.startswith("http") or target.startswith("file://"):
                self.switch_workspace("browser")
                self.browser_page.url_bar.setText(target)
                self.browser_page.navigate()
                return
        if kind == "note":
            if not self.switch_workspace("personal"):
                return
            self.personal_page.select_note(data.get("id", ""))
            return
        if kind in ("task", "event", "board", "board-node"):
            if not self.switch_workspace("personal"):
                return
            self.personal_page.open_life_item(kind, data.get("id", ""))
            return
        if kind in ("planner-item", "planner-block", "planner-course"):
            if not self.switch_workspace("personal"):
                return
            if kind == "planner-item":
                self.personal_page.open_plan_item(data.get("id", ""))
            elif kind == "planner-block":
                self.personal_page.open_plan_block(data.get("id", ""))
            else:
                self.personal_page.open_plan_course(data.get("id", ""))
            return
        if kind == "flashcard":
            if not self.switch_workspace("personal"):
                return
            self.personal_page.open_flashcard(data.get("id", ""))
            return
        subtitle = data.get("subtitle", "")
        if subtitle.startswith("http"):
            self.switch_workspace("browser")
            self.browser_page.url_bar.setText(subtitle)
            self.browser_page.navigate()

    def open_flow_step(self, action: dict):
        """Route one loop recommendation to the surface that can run it.

        The loop names a step; the shell owns the workspace switch, the study
        session start and the note/card selection — the same wiring the Home
        strip, the ``/flow`` command and the brief's "next" line all use.
        """
        action = action if isinstance(action, dict) else {}
        step = action.get("step", "")
        if step == "study" and action.get("start") and action.get("id"):
            from litebrowser.services import personal_plan
            collection = "time_blocks" if action.get("kind") == "planner-block" else "items"
            if not any(row.get("id") == action["id"] for row in personal_plan.load_plan(self.profile_dir)[collection]):
                return
        if not self.switch_workspace("personal"):
            return
        if step == "study" and action.get("start") and action.get("id"):
            from litebrowser.services import study_session
            if action.get("kind") == "planner-block":
                session = study_session.start_for_block(
                    self.profile_dir, action["id"], action.get("minutes") or None
                )
            else:
                session = study_session.start_for_item(
                    self.profile_dir, action["id"], action.get("minutes") or None
                )
            if session is None:
                return
            self._insight_cache = None
            self.personal_page._switch_page("plan")
            self.personal_page.refresh_all()
            self._flash_status(f"▶ Studying “{session.get('label', '')}”")
            return
        if step == "capture" and action.get("kind") == "note":
            self.personal_page.select_note(action.get("id", ""))
            return
        if step == "plan" and action.get("kind") == "task" and action.get("id"):
            # "Plan “Write lab report”" has to mean it: promote the inbox row now,
            # then open the plan on the row it became (the two stay linked).
            from litebrowser.services import study_flow
            item = study_flow.promote_task(self.profile_dir, action["id"])
            self._insight_cache = None
            self.personal_page._switch_page("plan")
            self.personal_page.refresh_all()
            if item is not None:
                self.personal_page.open_plan_item(item["id"])
            title = (item or {}).get("title") or action.get("label", "")
            self._flash_status(f"Planned “{title}”")
            return
        if step == "review":
            self.personal_page._switch_page("review")
            return
        # "plan" (and the running-pour "study" case) live on the planner page.
        self.personal_page._switch_page("plan")

    def _current_ai_scope_label(self):
        names = {
            "home": "Home overview",
            "browser": "Current browser page",
            "history": "History archive",
            "ai": "AI workspace",
            "personal": "Current personal page",
            "library": "Library results",
            "settings": "Settings profile",
        }
        current = next((name for name, index in self.workspace_index.items() if index == self.stack.currentIndex()), "home")
        return names.get(current, "Current workspace")

    def _current_ai_context(self):
        current = next((name for name, index in self.workspace_index.items() if index == self.stack.currentIndex()), "home")
        if current == "browser":
            browser = self.browser_page.current_browser()
            if browser:
                return (
                    "Current browser page",
                    f"Title: {browser.title()}\nURL: {browser.url().toString()}\nWorkspace: Browser",
                )
        if current == "personal":
            note_title = self.personal_page.lbl_note_title.text() if hasattr(self.personal_page, "lbl_note_title") else ""
            note_body = self.personal_page.note_editor.toPlainText()[:2000] if getattr(self.personal_page, "current_note_id", None) else ""
            if note_body.strip():
                return ("Current note", f"Title: {note_title}\n\n{note_body}")
            return ("Personal Hub", "Use Personal Hub context: tasks, notes, boards, calendar, files, and sites.")
        if current == "history":
            return ("History archive", f"Recent activity records: {len(history_service.list_activity(self.profile_dir)[:30])}")
        if current == "library":
            query = self.library_page.ed_search.text().strip()
            return ("Library", f"Current library query: {query}")
        return ("Workspace", f"Current workspace: {current}")

    def ask_ai_from_shell(self, scope: str = "current", question: str | None = None):
        prompt = (question if question is not None else self.ed_ai_quick.text()).strip()
        if not prompt:
            return
        if scope == "global":
            self._submit_ai_ask(prompt, "Whole profile", "")
            return
        context_label, context_text = self._current_ai_context()
        if self.insights.isVisible():
            # Insight AI is on: attach the FULL text of the page currently open
            # in the browser so the assistant can actually read the webpage.
            browser = self.browser_page.current_browser()
            if browser is not None and browser.page() is not None:
                self.lbl_assistant_scope.setText("Context: insights reading the browser page")

                def _on_page_text(text):
                    if self._closing:
                        return
                    page_text = (text or "").strip()
                    label, combined = context_label, context_text
                    if page_text:
                        title = browser.title() or browser.url().toString() or "Current page"
                        combined = (
                            f"{context_text}\n\n"
                            f"[Page open in browser: {title} — {browser.url().toString()} (full text)]\n"
                            f"{page_text[:12000]}"
                        )
                        label = f"{context_label} + browser page"
                    self._submit_ai_ask(prompt, label, combined)

                browser.page().runJavaScript(
                    "(function(){try{return (document.body && document.body.innerText) || '';}catch(e){return '';}})();",
                    _on_page_text,
                )
                return
        self._submit_ai_ask(prompt, context_label, context_text)

    def _submit_ai_ask(self, prompt: str, context_label: str, context_text: str):
        # If the AI workspace is passcode-locked and the user cancels the
        # unlock, the prompt must not be submitted anyway (v6.4 did).
        if not self.switch_workspace("ai"):
            return
        self.ai_page.ask_with_context(prompt, context_label, context_text)
        # Wire the assistant's reply back to the floating preview through the
        # ``query_finished`` signal so we never display a stale ``_last_answer``.
        if not getattr(self, "_ai_preview_wired", False):
            self.ai_page.query_finished.connect(self._on_ai_answer_ready_for_preview)
            self._ai_preview_wired = True

    def _on_ai_answer_ready_for_preview(self, future, _context_label, _provider_label=""):
        if self._closing or self._private_locked or future is not getattr(self.ai_page, "_active_query", None):
            return
        try:
            result = future.result()
        except Exception as exc:
            self.ai_preview.setText("AI request failed: %s" % (exc,))
            return
        answer = (result or {}).get("answer") or "No answer."
        self.ai_preview.setText(answer[:220])

    def persist_state(self) -> bool:
        if not self.personal_page.persist_state():
            return False
        try:
            self.browser_page.persist_state()
            self.ai_page._auto_save_set()
            self._save_window_state()
        except OSError as exc:
            QMessageBox.warning(self, "Save before closing", f"Close was canceled to protect your session: {exc}")
            return False
        return True

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        for timer in self.findChildren(QTimer):
            timer.stop()
        self.browser_page.shutdown()
        self.ai_page.shutdown()
        self.personal_page.shutdown()
        QApplication.instance().removeEventFilter(self)
        if getattr(self, "_hotkey_msg_id", None) is not None:
            try:
                import ctypes
                ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_msg_id)
            except (AttributeError, OSError):
                pass
        self._executor.shutdown(wait=False, cancel_futures=True)

    def quit_application(self):
        """Preflight every open shell before closing any of them."""
        windows = [window for window in QApplication.topLevelWidgets() if isinstance(window, AppShell) and not window._closing]
        if not all(window.persist_state() for window in windows):
            return False
        for window in windows:
            window.close()
        return True

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        # Embedded child windows do not receive closeEvent when their parent
        # closes. Persist them explicitly, without recursive widget closes.
        if not self.persist_state():
            event.ignore()
            return
        self.shutdown()
        # Hide the tray icon promptly so quitting does not leave a ghost entry.
        tray = getattr(self, "tray", None)
        if tray is not None:
            try:
                tray.hide()
            except Exception:
                pass
        event.accept()
