# Mei - window mixins: the browser toolbar (nav buttons, engine picker, address
# bar, connection pill, page menu) and its collapse behaviour.
#
# Split out of window.py (still ~3900 lines) so the chrome is one reviewable
# unit. SearchWindow inherits this mixin; it only touches attributes SearchWindow
# owns (content_layout, base_dir, embedded, current_browser, ...) and imports
# nothing back from window.py.
#
# Qt comes from the façade (litebrowser.qt) rather than PyQt5 directly, so this
# file stays out of the binding allowlist in tests/test_qt_facade.py.

from litebrowser.core import prefs
from litebrowser.qt import QtCore, QtGui, QtWidgets
from litebrowser.ui import dialogs

Qt = QtCore.Qt
QApplication = QtWidgets.QApplication
QComboBox = QtWidgets.QComboBox
QLineEdit = QtWidgets.QLineEdit
QMenu = QtWidgets.QMenu
QPushButton = QtWidgets.QPushButton
QToolButton = QtWidgets.QToolButton
QWidget = QtWidgets.QWidget
QFont = QtGui.QFont
QFrame = QtWidgets.QFrame
QUrl = QtCore.QUrl
QHBoxLayout = QtWidgets.QHBoxLayout
QLabel = QtWidgets.QLabel
QStyle = QtWidgets.QStyle

# The connection pill shows one of five states. Keeping the labels in one table
# is what lets the widget be sized once from the widest of them (see
# _build_site_pill) instead of resizing itself on every navigation.
SITE_PILL_LABELS = {
    "secure": "🔒 Secure",
    "insecure": "⚠ HTTP",
    "local": "Local",
    "file": "File",
    "search": "Search",
}

# Only two of the five states carry information the address bar does not already
# show. "Local" sat in the toolbar while the page was about:newtab and "Search"
# sat there on every empty tab — a chip that answers a question nobody asked.
# The pill appears when the *connection* has something to say: encrypted, or
# not. The labels stay in the table so the width reservation is unchanged.
SITE_PILL_INFORMATIVE_STATES = ("secure", "insecure")

# state -> (text colour, background) palette keys.
SITE_PILL_COLORS = {
    "secure": ("SUCCESS", "ACCENT_SOFT"),
    "insecure": ("DANGER", "MAIN_BG_ALT"),
    "local": ("TEXT_MUTED", "MAIN_BG_ALT"),
    "file": ("TEXT_MUTED", "MAIN_BG_ALT"),
    "search": ("TEXT_MUTED", "MAIN_BG_ALT"),
}

SITE_PILL_TIPS = {
    "secure": "Connected over HTTPS — traffic to this site is encrypted.",
    "insecure": "Not secure — this page is served over plain HTTP.",
    "local": "An internal Mei / about: page.",
    "file": "A file on this computer.",
    "search": "Type a URL or a search term and press Enter.",
}

# Horizontal room the pill needs besides its text (7px padding each side plus
# slack for the emoji glyphs, which font metrics under-report).
SITE_PILL_SLACK_PX = 20


def site_state_key(url_str: str) -> str:
    """Classify an address for the connection pill.

    Pure and Qt-free so the mapping can be tested without building a window.
    """
    url = (url_str or "").strip().lower()
    if url.startswith("https://"):
        return "secure"
    if url.startswith("http://"):
        return "insecure"
    if url.startswith("about:"):
        return "local"
    if url.startswith("file:"):
        return "file"
    return "search"


class TopBarMixin:
    """Builds the browser toolbar and owns its collapse/expand behaviour."""

    def _build_topbar(self):
        self.topbar = QWidget()
        self.topbar.setObjectName("TopBar")
        self.topbar.setMinimumHeight(40 if self.embedded else 44)
        self.topbar_layout = QHBoxLayout(self.topbar)
        if self.embedded:
            self.topbar_layout.setContentsMargins(4, 3, 4, 3)
            self.topbar_layout.setSpacing(3)
        else:
            self.topbar_layout.setContentsMargins(4, 3, 4, 3)
            self.topbar_layout.setSpacing(2)
        self.btn_back = QToolButton()
        self.btn_back.setObjectName("TopIconButton")
        self.btn_back.setText("←")
        self.btn_back.setToolTip("Back (Alt+Left)")
        # Accessible names: the toolbar buttons are glyph-only (←, →, ↻), which a
        # screen reader would otherwise announce as "left arrow".
        self.btn_back.setAccessibleName("Back")
        self.btn_back.clicked.connect(lambda: self.current_browser().back() if self.current_browser() else None)
        self.btn_forward = QToolButton()
        self.btn_forward.setObjectName("TopIconButton")
        self.btn_forward.setText("→")
        self.btn_forward.setToolTip("Forward (Alt+Right)")
        self.btn_forward.setAccessibleName("Forward")
        self.btn_forward.clicked.connect(lambda: self.current_browser().forward() if self.current_browser() else None)
        self.btn_reload = QToolButton()
        self.btn_reload.setObjectName("TopIconButton")
        self.btn_reload.setText("↻")
        self.btn_reload.setToolTip("Reload (F5)")
        self.btn_reload.setAccessibleName("Reload")
        self.btn_reload.clicked.connect(self._reload_or_stop)
        self.btn_back.setEnabled(False)
        self.btn_forward.setEnabled(False)
        self.topbar_layout.addWidget(self.btn_back)
        self.topbar_layout.addWidget(self.btn_forward)
        self.topbar_layout.addWidget(self.btn_reload)
        self.btn_vpn_hub = QPushButton()
        self.btn_vpn_hub.setObjectName("TopAccentButton")
        self.btn_vpn_hub.setText("VPN")
        self.btn_vpn_hub.setToolTip("Quick VPN / proxy presets")
        self.btn_vpn_hub.clicked.connect(lambda: dialogs.show_vpn_hub(self))
        self.topbar_layout.addWidget(self.btn_vpn_hub)
        self.topbar_layout.addSpacing(4)
        self.search_engine = QComboBox()
        self.search_engine.setObjectName("SearchEngine")
        self.search_engine.addItems(list(prefs.SEARCH_ENGINE_NAMES))
        self.search_engine.setEditable(False)
        saved_engine = prefs.get_search_engine(self.base_dir)
        saved_index = self.search_engine.findText(saved_engine)
        if saved_index >= 0:
            self.search_engine.setCurrentIndex(saved_index)
        self.search_engine.setMinimumWidth(78)
        self.search_engine.setMaximumWidth(118)
        self.search_engine.currentIndexChanged.connect(self._on_search_engine_changed)
        self.topbar_layout.addWidget(self.search_engine)
        # One address field: the connection pill and the address used to be two
        # separate boxes side by side, which is most of why a 40px toolbar read
        # as a row of unrelated controls.
        self.address_cluster = QFrame()
        self.address_cluster.setObjectName("AddressCluster")
        self.address_cluster.setProperty("focused", False)
        cluster_layout = QHBoxLayout(self.address_cluster)
        cluster_layout.setContentsMargins(0, 0, 0, 0)
        cluster_layout.setSpacing(0)
        self._build_site_pill(cluster_layout)
        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("UrlBar")
        # Plain language first: the old placeholder was a developer example
        # ("about:cuc-quan-ly") sitting in the busiest control in the window.
        self.url_bar.setPlaceholderText("Search or enter an address  ·  Ctrl+L")
        self.url_bar.setFont(QFont("Segoe UI", 11))
        self.url_bar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.url_bar.setMinimumWidth(120)
        self.url_bar.setClearButtonEnabled(False)
        self.url_bar.setToolTip("Type a URL or search and press Enter")
        self.url_bar.setAccessibleName("Search or enter an address")
        self.url_bar.returnPressed.connect(self.navigate)
        self.url_clear_action = self.url_bar.addAction(
            self.style().standardIcon(QStyle.SP_DialogCloseButton),
            QLineEdit.TrailingPosition,
        )
        self.url_clear_action.triggered.connect(self.url_bar.clear)
        self.url_clear_action.setVisible(False)
        self.url_bar.textChanged.connect(lambda text: self.url_clear_action.setVisible(bool(text)))
        # Chrome standard: middle-click pastes the clipboard and navigates.
        self.url_bar.installEventFilter(self)
        # Clipboard history: track the last 20 text entries (dedup, QoL).
        self._clipboard_history = []
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)
        cluster_layout.addWidget(self.url_bar, 1)
        self.topbar_layout.addWidget(self.address_cluster, 1)
        # Opera GX-style web panels: messenger/media dock beside the page.
        self.btn_panels = QToolButton()
        self.btn_panels.setObjectName("TopIconButton")
        self.btn_panels.setText("◫")
        self.btn_panels.setToolTip("Web panels — Telegram, WhatsApp, Discord, Spotify... (docked beside the page)")
        self.btn_panels.setAccessibleName("Web panels")
        self.btn_panels.clicked.connect(self.show_web_panel_menu)
        self.topbar_layout.addWidget(self.btn_panels)
        self._build_zoom_label()
        self.btn_ai = QToolButton()
        self.btn_ai.setObjectName("TopIconButton")
        self.btn_ai.setText("AI")
        self.btn_ai.setToolTip("Ask AI about this page")
        self.btn_ai.setAccessibleName("Ask AI about this page")
        self.btn_ai.clicked.connect(self.ask_ai_about_current_page)
        self.topbar_layout.addWidget(self.btn_ai)
        self.btn_page_menu = QToolButton()
        self.btn_page_menu.setObjectName("TopIconButton")
        self.btn_page_menu.setText("\u2022\u2022\u2022")
        self.btn_page_menu.setToolTip("Page actions")
        self.btn_page_menu.setAccessibleName("Page actions")
        self.page_menu = self._build_page_menu()
        self.btn_page_menu.setMenu(self.page_menu)
        self.btn_page_menu.setPopupMode(QToolButton.InstantPopup)
        self.topbar_layout.addWidget(self.btn_page_menu)
        self.btn_toggle_topbar = QToolButton()
        self.btn_toggle_topbar.setObjectName("TopIconButton")
        self.btn_toggle_topbar.setText("▾")
        self.btn_toggle_topbar.setToolTip("Collapse / expand the toolbar (Ctrl+Shift+B)")
        self.btn_toggle_topbar.setAccessibleName("Collapse or expand the toolbar")
        self.btn_toggle_topbar.clicked.connect(self._toggle_topbar)
        self.topbar_layout.addWidget(self.btn_toggle_topbar)
        self.topbar_layout.setStretchFactor(self.address_cluster, 1)
        self.content_layout.addWidget(self.topbar, 0)

    def _reload_or_stop(self):
        browser = self.current_browser()
        if browser is not None:
            if browser.property("mei_loading"):
                browser.stop()
            else:
                browser.reload()

    def sync_navigation(self, browser=None):
        browser = browser or self.current_browser()
        if browser is not self.current_browser():
            return
        if browser is None:
            self.btn_back.setEnabled(False)
            self.btn_forward.setEnabled(False)
            self.btn_reload.setEnabled(False)
            return
        history = browser.history()
        self.btn_back.setEnabled(history.canGoBack())
        self.btn_forward.setEnabled(history.canGoForward())
        self.btn_reload.setEnabled(True)
        loading = bool(browser.property("mei_loading"))
        self.btn_reload.setText("×" if loading else "↻")
        self.btn_reload.setAccessibleName("Stop loading" if loading else "Reload")
        self.btn_reload.setToolTip("Stop loading (Esc)" if loading else "Reload (F5)")

    def on_load_started(self, browser):
        browser.setProperty("mei_loading", True)
        self.sync_navigation(browser)
        if browser is self.current_browser():
            self.load_progress.setValue(1)
            self.load_progress.show()

    def _build_site_pill(self, cluster_layout):
        """Address-bar connection pill: 🔒 Secure / ⚠ HTTP / Local / File / Search.

        One fixed width for all five states — the label used to be as wide as
        whatever text it currently held, so every navigation nudged the address
        bar sideways by a few pixels.
        """
        self.lbl_site_state = QLabel(SITE_PILL_LABELS["search"])
        self.lbl_site_state.setObjectName("SiteStatePill")
        self.lbl_site_state.setAlignment(Qt.AlignCenter)
        # The font lives here (not in QSS) because the width below is measured
        # from it — a stylesheet font would only land after the first polish.
        pill_font = QFont("Segoe UI", 8)
        pill_font.setBold(True)
        self.lbl_site_state.setFont(pill_font)
        metrics = self.lbl_site_state.fontMetrics()
        widest = max(metrics.horizontalAdvance(text) for text in SITE_PILL_LABELS.values())
        self.lbl_site_state.setFixedWidth(widest + SITE_PILL_SLACK_PX)
        self.lbl_site_state.setToolTip(SITE_PILL_TIPS["search"])
        # The pill leads the address field: a little air before the text, a hair
        # after it so it never touches the address itself.
        cluster_layout.setContentsMargins(4, 0, 2, 0)
        cluster_layout.addWidget(self.lbl_site_state)
        cluster_layout.setSpacing(3)
        self._site_pill_state = "search"
        self._apply_site_state_pill("")

    def _apply_site_state_pill(self, url_str: str):
        """Paint the pill for ``url_str``.

        Every state gets the same pill treatment (text + tinted background); the
        two 'plain' states used to fall back to the generic ``#AddressHint`` QSS
        and rendered as bare uppercase accent text, so the indicator changed shape
        depending on the scheme of whatever was open.

        States that repeat what the address bar already shows (an ``about:`` page,
        an empty omnibar) hide the chip entirely: see
        ``SITE_PILL_INFORMATIVE_STATES``.
        """
        state = site_state_key(url_str)
        self._site_pill_state = state
        self.lbl_site_state.setText(SITE_PILL_LABELS[state])
        text_key, bg_key = SITE_PILL_COLORS[state]
        # Pill, not a rounded box: same value as the RADIUS_PILL token in the
        # stylesheet, so state chip and zoom chip have the same silhouette.
        self.lbl_site_state.setStyleSheet(
            "color: %s; background-color: %s; border-radius: 999px; padding: 2px 9px;"
            % (self._palette_lookup(text_key), self._palette_lookup(bg_key))
        )
        self.lbl_site_state.setToolTip(SITE_PILL_TIPS[state])
        self._sync_site_pill_visibility()

    def _sync_site_pill_visibility(self):
        """Show the connection pill only where it adds something.

        A hidden control still has to respect the toolbar's own rules: the
        responsive pass hides it in a narrow window, and a collapsed toolbar
        hides everything but its toggle.  Both are re-applied on top of the
        state test instead of being overwritten by it.
        """
        if not hasattr(self, "lbl_site_state"):
            return
        informative = getattr(self, "_site_pill_state", "search") in SITE_PILL_INFORMATIVE_STATES
        self.lbl_site_state.setVisible(
            informative
            and bool(getattr(self, "_site_pill_fits", True))
            and not getattr(self, "_topbar_collapsed", False)
        )

    def refresh_chrome_theme(self):
        """Re-paint the chrome that carries its colours in an inline stylesheet.

        Tab rows, the connection pill and the tab-desk state chips read their
        palette once, when they are built.  With auto day/night on, the resolved
        theme flips at 06:00 and 18:00 — without this, every one of them kept
        yesterday's colours (dark labels on the night desk).
        """
        if hasattr(self, "lbl_site_state"):
            self._apply_site_state_pill(self.url_bar.text() if hasattr(self, "url_bar") else "")
        manager = getattr(self, "tab_manager", None)
        if manager is not None and hasattr(manager, "refresh_theme"):
            manager.refresh_theme()
        self.refresh_internal_pages_theme()

    def refresh_internal_pages_theme(self):
        """Bring the pages Mei renders itself in line with the shell's theme.

        Two things have to follow the resolved theme rather than the stored one:
        the speed dial (its colours are baked into the HTML when it is generated,
        so switching to night while a new tab is open used to leave a bright page
        inside a dark window) and the forced-dark treatment of web pages.
        """
        for browser in list(getattr(self, "browsers", []) or []):
            if browser is None:
                continue
            try:
                if browser.url().toString() != "about:newtab":
                    continue
                browser.page().setHtml(self.get_new_tab_html(), QUrl("about:newtab"))
            except Exception:
                continue
        sync_dark = getattr(self, "_sync_dark_web_with_theme", None)
        if callable(sync_dark):
            sync_dark()

    def _build_zoom_label(self):
        """Zoom chip: hidden at 100%, shown only once the page is actually zoomed.

        A permanent '100%' is chrome that never carries information; the zoom
        level matters exactly when it differs from the default. Still click-to-reset.
        """
        self.lbl_zoom = QToolButton()
        self.lbl_zoom.setText("100%")
        self.lbl_zoom.setAccessibleName("Reset page zoom")
        self.lbl_zoom.setObjectName("ZoomLabel")
        self.lbl_zoom.setMinimumWidth(42)
        self.lbl_zoom.setMinimumHeight(32)
        self.lbl_zoom.setToolTip("Zoom level — click to reset (Ctrl+0)")
        self.lbl_zoom.setCursor(Qt.PointingHandCursor)
        self.lbl_zoom.clicked.connect(self.zoom_reset)
        self._zoom_at_default = True
        self.lbl_zoom.setVisible(False)
        self.topbar_layout.addWidget(self.lbl_zoom)

    def _set_zoom_label(self, percent: int):
        """Zoom chip carries the zoom level only while it differs from default.

        It used to sit at a permanent "100%", which is chrome that never says
        anything; Chrome shows the indicator only when the page is zoomed. Still
        click-to-reset, and Ctrl+0 / the page menu remain.
        """
        self._zoom_at_default = percent == 100
        self.lbl_zoom.setText(f"{percent}%")
        if not getattr(self, "_topbar_collapsed", False):
            self.lbl_zoom.setVisible(not self._zoom_at_default)

    def _build_page_menu(self):
        # Shortcut text after a tab is drawn in the menu's shortcut column without
        # registering a second shortcut (the real ones are QShortcuts on the
        # window) — discoverability without Qt "ambiguous shortcut" warnings.
        menu = QMenu(self)
        menu.addAction("Home").triggered.connect(self._go_home)
        menu.addAction("Open in incognito tab").triggered.connect(self.open_current_in_incognito)
        menu.addAction("Copy page address").triggered.connect(self._copy_page_address)
        menu.addAction("Bookmark page\tCtrl+D").triggered.connect(lambda: self.save_bookmark(None))
        menu.addAction("Save to reading list").triggered.connect(self._add_to_reading_list)
        menu.addAction("Save selection to SafeVault").triggered.connect(self._save_selection_to_vault)
        menu.addAction("Monitor this page for changes").triggered.connect(self._monitor_current_page)
        menu.addAction("Find in page\tCtrl+F").triggered.connect(self.find_text)
        menu.addAction("Reader mode").triggered.connect(self.toggle_reader_mode)
        menu.addSeparator()
        self.act_text_highlight = menu.addAction("✎ Highlight text to copy")
        self.act_text_highlight.setCheckable(True)
        self.act_text_highlight.setToolTip("Select any text to highlight it; a copy bubble appears next to the selection.")
        self.act_text_highlight.setChecked(prefs.get_text_highlight_enabled(self.base_dir))
        self.act_text_highlight.triggered.connect(self.toggle_text_highlight)
        menu.addSeparator()
        menu.addAction("Open externally").triggered.connect(self.open_current_in_external_browser)
        menu.addAction("Site permissions...").triggered.connect(lambda: dialogs.show_permissions_manager(self))
        menu.addAction("Help & guide\tF1").triggered.connect(lambda: dialogs.show_browser_control_center(self))
        menu.addAction("Hotkeys...").triggered.connect(lambda: dialogs.show_hotkeys_hub(self))
        menu.addAction("Open accounts.google.com in Chrome / Edge").triggered.connect(
            lambda: self.open_url_in_external_browser("https://accounts.google.com/")
        )
        menu.addSeparator()
        menu.addAction("Zoom in\tCtrl+=").triggered.connect(self.zoom_in)
        menu.addAction("Zoom out\tCtrl+-").triggered.connect(self.zoom_out)
        menu.addAction("Reset zoom\tCtrl+0").triggered.connect(self.zoom_reset)
        menu.addSeparator()
        trans_menu = menu.addMenu("Translate")
        trans_menu.addAction("Translate this page (Google)").triggered.connect(lambda: self._translate_page("google"))
        trans_menu.addAction("Translate this page (Bing)").triggered.connect(lambda: self._translate_page("bing"))
        menu.addSeparator()
        self.act_page_disable_webgl = menu.addAction("Lite Rendering (Disable WebGL)")
        self.act_page_disable_webgl.setCheckable(True)
        self.act_page_disable_webgl.triggered.connect(self.toggle_disable_webgl)
        menu.addAction("Developer tools\tF12").triggered.connect(self.show_dev_tools)
        menu.addAction("More browser options").triggered.connect(lambda: self.btn_options.showMenu())
        return menu

    def _toggle_topbar(self):
        self._topbar_collapsed = not getattr(self, "_topbar_collapsed", False)
        self._apply_topbar_collapse()

    def _widget_hidden_by_design(self, widget) -> bool:
        """Controls the chrome hides on purpose, whatever the collapse state is.

        Re-expanding used to call ``setVisible(True)`` on every control, which
        resurrected two buttons the toolbar had deliberately hidden: AI (absent in
        a window without AI actions) and the zoom chip (hidden while the page sits
        at 100%).
        """
        if widget is getattr(self, "btn_ai", None):
            return not getattr(self, "ai_actions_available", False)
        if widget is getattr(self, "lbl_zoom", None):
            return bool(getattr(self, "_zoom_at_default", True))
        return False

    def _apply_topbar_collapse(self):
        """Hide everything in the toolbar except its collapse toggle so the
        page gets the maximum vertical space, then restore it on re-expand."""
        collapsed = getattr(self, "_topbar_collapsed", False)
        if hasattr(self, "btn_toggle_topbar"):
            self.btn_toggle_topbar.setText("▴" if collapsed else "▾")
        if not hasattr(self, "topbar_layout"):
            return
        for index in range(self.topbar_layout.count()):
            item = self.topbar_layout.itemAt(index)
            widget = item.widget() if item else None
            if widget is None or widget is self.btn_toggle_topbar:
                continue
            widget.setVisible(not collapsed and not self._widget_hidden_by_design(widget))
        # The connection pill owns a visibility rule of its own (see
        # _sync_site_pill_visibility) — re-run it so the two agree.
        self._sync_site_pill_visibility()
        self.topbar.setMaximumHeight(26 if collapsed else 16777215)
        self.topbar.setMinimumHeight(24 if collapsed else (40 if self.embedded else 44))
        if not collapsed:
            # Re-run the responsive pass so controls this window is simply too
            # narrow for (engine picker, connection pill, page menu) stay hidden
            # instead of blinking back in until the next resize.
            self._apply_responsive_layout()
