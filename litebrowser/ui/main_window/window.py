# Mei - Search window (main browser UI)
import json
import os
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, quote_plus, urlparse

from PyQt5.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QSize,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
)
from PyQt5.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
)
from PyQt5.QtNetwork import QNetworkProxy
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
from PyQt5.QtWebEngineWidgets import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineView,
)
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from litebrowser.browser import adblock, extension_patterns, new_tab_page, tab_manager
from litebrowser.browser.browser_page import (
    build_text_highlight_js,
    ensure_text_highlight_script,
    ensure_webgl_disable_script,
)
from litebrowser.browser.tab_manager import (
    TAB_GROUP_COLLAPSED_ROLE,
    TAB_GROUP_COLOR_ROLE,
    TAB_GROUP_ROLE,
    TAB_META_ROLE,
    TAB_PINNED_ROLE,
    TAB_WIDGET_ROLE,
)
from litebrowser.core import app_paths, prefs
from litebrowser.services import (
    extension_bridge,
    google_auth,
    history_service,
    life_service,
    personal_service,
    tab_sets,
    workspace_manager,
)
from litebrowser.ui import dialogs, theme, vault_ui, win_titlebar

COMPATIBILITY_HOSTS = (
    "accounts.google.com",
    "claude.ai",
    "chatgpt.com",
    "copilot.microsoft.com",
    "gemini.google.com",
    "perplexity.ai",
)

# Chrome-style memory saver: when the process working set grows past this many
# MB, background tabs are frozen automatically until RAM settles down again.
MEMORY_SAVER_RSS_THRESHOLD_MB = 800


class _BrowserContentArea(QWidget):
    """Browser pane sitting to the right of the workspace tab desk.

    Nested docks and QWebEngineView advertise large minimumSizeHints. On Windows
    with PyQt6, QSplitter re-applies those hints on a bare click of its handle
    (press+release with no drag), which steals width from the tab desk until it
    looks like the sidebar vanished and can no longer be resized. Report a zero
    minimum to the *outer* workspace splitter; the inner panel_split still
    honors each dock's own minimum when that dock is actually visible.
    """

    def minimumSizeHint(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(640, 480)


def _process_rss_mb():
    """Current process working-set size in MB (Windows), or None if unknown."""
    global _RSS_DLL_CACHE
    try:
        import ctypes
        from ctypes import wintypes

        if _RSS_DLL_CACHE is None:
            _RSS_DLL_CACHE = (ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi"))

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32, psapi = _RSS_DLL_CACHE
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if ok:
            return int(counters.WorkingSetSize // (1024 * 1024))
    except Exception:
        pass
    return None


_RSS_DLL_CACHE = None


from litebrowser.ui.main_window.window_menus import MenusMixin
from litebrowser.ui.main_window.window_mixins import DockingMixin
from litebrowser.ui.main_window.window_tools import WindowToolsMixin, _WorkerRelay
from litebrowser.ui.main_window.window_topbar import TopBarMixin


class SearchWindow(TopBarMixin, DockingMixin, MenusMixin, WindowToolsMixin, QMainWindow):
    def __init__(self, base_dir=None, start_tabs=None, app_dir=None, embedded=False, window_slot=None):
        super().__init__()
        self._closing = False
        # Set BEFORE QWebEngineProfile is constructed so the two shell windows
        # get isolated disk caches/cookies instead of fighting over one dir.
        self._window_slot_hint = window_slot or "shared"
        self.embedded = embedded
        self.setWindowTitle("Mei - Browser")
        self.setGeometry(100, 100, 1300, 850)
        self.setMinimumSize(520 if embedded else 900, 420 if embedded else 600)
        self.base_dir = prefs.ensure_profile_layout(base_dir or app_paths.project_root())
        self.app_dir = app_dir or app_paths.project_root()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._worker_relay = _WorkerRelay(self)
        self._google_auth_running = False
        self.setWindowIcon(QIcon(os.path.join(self.app_dir, "icon.png")))

        # Native title bar color (Windows) - using shared helper.
        if not self.embedded:
            win_titlebar.apply_dark_titlebar(self, enabled=True)

        self.central_widget = QWidget()
        self.central_widget.setObjectName("MainWidget")
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(lambda: self.add_new_tab())
        QShortcut(QKeySequence("Ctrl+Shift+N"), self).activated.connect(lambda: self.add_new_tab(is_incognito=True))
        QShortcut(QKeySequence("Ctrl+Shift+E"), self).activated.connect(self.extract_text)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.capture_screenshot)
        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(lambda: self.tab_manager.close_tab(self.tab_list.currentRow()))
        QShortcut(QKeySequence("F5"), self).activated.connect(lambda: self.current_browser().reload() if self.current_browser() else None)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(lambda: self.current_browser().reload() if self.current_browser() else None)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.find_text)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self).activated.connect(self.focus_tab_filter)
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self.show_history_dialog)
        QShortcut(QKeySequence("Ctrl+J"), self).activated.connect(self.show_downloads_dialog)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self.focus_url_bar)
        QShortcut(QKeySequence("Ctrl+Shift+B"), self).activated.connect(self._toggle_topbar)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self.save_bookmark)
        QShortcut(QKeySequence("Alt+Left"), self).activated.connect(lambda: self.current_browser().back() if self.current_browser() else None)
        QShortcut(QKeySequence("Alt+Right"), self).activated.connect(lambda: self.current_browser().forward() if self.current_browser() else None)
        QShortcut(QKeySequence("F11"), self).activated.connect(self.toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+Shift+D"), self).activated.connect(lambda: self.tab_manager.duplicate_current_tab())
        QShortcut(QKeySequence("Ctrl+Shift+T"), self).activated.connect(self.reopen_closed_tab)
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(self._cycle_tab_next)
        QShortcut(QKeySequence("Ctrl+PgDown"), self).activated.connect(self._cycle_tab_next)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(self._cycle_tab_prev)
        QShortcut(QKeySequence("Ctrl+PgUp"), self).activated.connect(self._cycle_tab_prev)
        QShortcut(QKeySequence("Ctrl+Shift+K"), self).activated.connect(lambda: dialogs.show_quick_switcher(self))
        # F1 is the convention every app trained users on; the guide is generated
        # from the same registries the shortcuts come from.
        QShortcut(QKeySequence("F1"), self).activated.connect(lambda: dialogs.show_browser_control_center(self))
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self.zoom_reset)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.zoom_out)
        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(self.print_page)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(self.save_page_pdf)
        QShortcut(QKeySequence("Ctrl+Shift+M"), self).activated.connect(
            lambda: getattr(self, "tab_manager", None) and self.tab_manager.optimize_memory()
        )
        QShortcut(QKeySequence("F12"), self).activated.connect(self.show_dev_tools)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self.toggle_zen_mode)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self).activated.connect(self.hard_reload)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self).activated.connect(self.show_clipboard_history)
        # Esc exits Zen mode first (then closes the find bar if that was open).
        QShortcut(QKeySequence(Qt.Key_Escape), self).activated.connect(self._escape_in_browser)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_layout.addWidget(self.main_splitter)

        self.sidebarWidget = QWidget()
        self.sidebarWidget.setObjectName("Sidebar")
        # Start with the useful, readable tab desk open.  The compact handler
        # still turns this into a slim rail on narrow embedded windows.
        self.sidebar_collapsed = False
        self._topbar_collapsed = False
        self.sidebarWidget.setMinimumWidth(190)
        self.sidebarWidget.setMaximumWidth(800)
        self.sidebar_layout = QVBoxLayout(self.sidebarWidget)
        self.sidebar_layout.setContentsMargins(8, 10, 8, 10)
        self.sidebar_layout.setSpacing(6)
        self.sidebar_layout.setAlignment(Qt.AlignTop)
        self._sidebar_anim = None
        # One header line: the collapse toggle on the left, the live/sleeping
        # counter on the right. The "🍵 Mei" wordmark used to sit here too, which
        # made the brand the third "Mei" on screen (shell top bar, rail, desk) —
        # the tab column is about tab state, so it no longer repeats the name.
        sidebar_title_row = QHBoxLayout()
        sidebar_title_row.setSpacing(6)
        self.btn_collapse_sidebar = QToolButton()
        self.btn_collapse_sidebar.setObjectName("SidebarCollapse")
        self.btn_collapse_sidebar.setToolTip("Collapse / expand the tab desk")
        self.btn_collapse_sidebar.setText("‹")
        self.btn_collapse_sidebar.clicked.connect(self._toggle_sidebar_collapse)
        sidebar_title_row.addWidget(self.btn_collapse_sidebar)
        sidebar_title_row.addStretch(1)
        self.lbl_tab_count = QLabel("0 live · 0 sleeping")
        self.lbl_tab_count.setObjectName("TabCounter")
        self.lbl_tab_count.setToolTip("Live tabs use a browser renderer. Sleeping tabs reopen only when selected.")
        self.lbl_tab_count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sidebar_title_row.addWidget(self.lbl_tab_count)
        self.sidebar_layout.addLayout(sidebar_title_row)
        self.current_workspace_id = workspace_manager.get_current_id(self.base_dir)
        self.workspace_combo = QComboBox()
        self.workspace_combo.setObjectName("WorkspaceCombo")
        self.workspace_combo.setMinimumHeight(28)
        self._refresh_workspace_combo()
        self.workspace_combo.currentIndexChanged.connect(self._on_workspace_changed)
        self.sidebar_layout.addWidget(self.workspace_combo)
        self.sidebar_panel_buttons = QGridLayout()
        self.sidebar_panel_buttons.setSpacing(4)
        self.sidebar_panel_buttons.setAlignment(Qt.AlignCenter)
        self.btn_panel_tabs = QToolButton()
        self.btn_panel_tabs.setObjectName("SidebarPanelBtn")
        self.btn_panel_tabs.setText("◉")
        self.btn_panel_tabs.setToolTip("Tab list")
        self.btn_panel_tabs.setCheckable(True)
        self.btn_panel_tabs.setChecked(True)
        self.btn_panel_bookmarks = QToolButton()
        self.btn_panel_bookmarks.setObjectName("SidebarPanelBtn")
        self.btn_panel_bookmarks.setText("★")
        self.btn_panel_bookmarks.setToolTip("Bookmarks")
        self.btn_panel_bookmarks.setCheckable(True)
        self.btn_panel_history = QToolButton()
        self.btn_panel_history.setObjectName("SidebarPanelBtn")
        self.btn_panel_history.setText("◷")
        self.btn_panel_history.setToolTip("History")
        self.btn_panel_history.setCheckable(True)
        self.btn_panel_downloads = QToolButton()
        self.btn_panel_downloads.setObjectName("SidebarPanelBtn")
        self.btn_panel_downloads.setText("↓")
        self.btn_panel_downloads.setToolTip("Downloads")
        self.btn_panel_downloads.setCheckable(True)
        self.btn_panel_reading = QToolButton()
        self.btn_panel_reading.setObjectName("SidebarPanelBtn")
        self.btn_panel_reading.setText("☰")
        self.btn_panel_reading.setToolTip("Reading list")
        self.btn_panel_reading.setCheckable(True)
        self.sidebar_panel_group = QButtonGroup(self)
        self.sidebar_panel_group.setExclusive(True)
        self.sidebar_panel_group.addButton(self.btn_panel_tabs)
        self.sidebar_panel_group.addButton(self.btn_panel_bookmarks)
        self.sidebar_panel_group.addButton(self.btn_panel_history)
        self.sidebar_panel_group.addButton(self.btn_panel_downloads)
        self.sidebar_panel_group.addButton(self.btn_panel_reading)
        for index, button in enumerate((self.btn_panel_tabs, self.btn_panel_bookmarks, self.btn_panel_history, self.btn_panel_downloads, self.btn_panel_reading)):
            button.setAccessibleName(button.toolTip())
            self.sidebar_panel_buttons.addWidget(button, 0, index)
        self.sidebar_layout.addLayout(self.sidebar_panel_buttons)
        self.sidebar_stack = QStackedWidget()
        self.sidebar_stack.setObjectName("SidebarStack")
        tab_page = QWidget()
        tab_page_layout = QVBoxLayout(tab_page)
        tab_page_layout.setContentsMargins(0, 0, 0, 0)
        tab_page_layout.setSpacing(0)
        self.tab_filter = QLineEdit()
        self.tab_filter.setObjectName("TabFilter")
        # The full filter syntax used to be the placeholder, which the narrow
        # sidebar clipped mid-word ("group:…"). Keep the box quiet and teach the
        # syntax on hover instead.
        self.tab_filter.setPlaceholderText("Search tabs…")
        self.tab_filter.setToolTip(
            "Filter the tab list\n"
            "    is:sleeping   is:pinned   is:live\n"
            "    site:example.com\n"
            "    group:youtube.com"
        )
        self.tab_filter.setClearButtonEnabled(True)
        self._tab_filter_timer = QTimer(self)
        self._tab_filter_timer.setSingleShot(True)
        self._tab_filter_timer.setInterval(65)
        self._tab_filter_timer.timeout.connect(self._filter_tab_list)
        self.tab_filter.textChanged.connect(self._queue_tab_filter)
        tab_page_layout.addWidget(self.tab_filter)
        self.tab_list = QListWidget()
        self.tab_list.setObjectName("TabList")
        self.tab_list.currentRowChanged.connect(self._on_change_tab)
        self.tab_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_list.customContextMenuRequested.connect(self.show_tab_context_menu)
        self.tab_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.tab_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tab_list.setUniformItemSizes(True)
        # Double-click the empty desk below the tabs → new tab (standard UX).
        class _TabDeskClickFilter(QObject):
            def eventFilter(_self, obj, ev):
                from PyQt5.QtCore import QEvent

                # QEvent.Type.* scoped form works on both PyQt5 and PyQt6;
                # the un-scoped shortcut crashes under PyQt6.
                if ev.type() == QEvent.Type.MouseButtonDblClick:
                    # Only when the click lands on empty space, not a tab row.
                    if self.tab_list.itemAt(ev.pos()) is None:
                        self.add_new_tab()
                        ev.accept()
                        return True
                return False

        self._tab_desk_filter = _TabDeskClickFilter(self)
        self.tab_list.installEventFilter(self._tab_desk_filter)
        tab_page_layout.addWidget(self.tab_list, 1)
        self.sidebar_stack.addWidget(tab_page)
        bookmarks_page = QWidget()
        bookmarks_page_layout = QVBoxLayout(bookmarks_page)
        bookmarks_page_layout.setContentsMargins(0, 0, 0, 0)
        bookmarks_page_layout.setSpacing(2)
        bm_toolbar = QHBoxLayout()
        bm_toolbar.setContentsMargins(4, 2, 4, 2)
        self.btn_add_bm_folder = QToolButton()
        self.btn_add_bm_folder.setText("+Folder")
        self.btn_add_bm_folder.setToolTip("Add bookmark folder")
        self.btn_add_bm_folder.clicked.connect(self._add_bookmark_folder)
        bm_toolbar.addWidget(self.btn_add_bm_folder)
        self.btn_add_bm = QToolButton()
        self.btn_add_bm.setText("+BM")
        self.btn_add_bm.setToolTip("Bookmark current page here")
        self.btn_add_bm.clicked.connect(lambda: self.save_bookmark(None))
        bm_toolbar.addWidget(self.btn_add_bm)
        bm_toolbar.addStretch()
        bookmarks_page_layout.addLayout(bm_toolbar)
        self.bookmarks_tree = QTreeWidget()
        self.bookmarks_tree.setObjectName("TabList")
        self.bookmarks_tree.setHeaderHidden(True)
        self.bookmarks_tree.setDragDropMode(self.bookmarks_tree.DragDropMode.InternalMove)
        self.bookmarks_tree.itemDoubleClicked.connect(lambda item, col: self._on_bookmark_clicked(item))
        self.bookmarks_tree.viewport().installEventFilter(self)
        self.bookmarks_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bookmarks_tree.customContextMenuRequested.connect(self._show_bookmark_context_menu)
        self.bookmarks_tree.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        bookmarks_page_layout.addWidget(self.bookmarks_tree, 1)
        self.sidebar_stack.addWidget(bookmarks_page)
        self.history_list = QListWidget()
        self.history_list.setObjectName("TabList")
        self.history_list.itemDoubleClicked.connect(self._on_history_clicked)
        self.history_list.viewport().installEventFilter(self)
        self.history_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar_stack.addWidget(self.history_list)
        self.downloads_list = QListWidget()
        self.downloads_list.setObjectName("TabList")
        self.downloads_list.itemDoubleClicked.connect(self._on_download_clicked)
        self.downloads_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.downloads_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar_stack.addWidget(self.downloads_list)
        self.reading_list = QListWidget()
        self.reading_list.setObjectName("TabList")
        self.reading_list.itemDoubleClicked.connect(self._on_reading_clicked)
        self.reading_list.viewport().installEventFilter(self)
        self.reading_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.reading_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar_stack.addWidget(self.reading_list)
        self.sidebar_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sidebar_layout.addWidget(self.sidebar_stack, 1)
        self.btn_panel_tabs.clicked.connect(lambda: self._switch_sidebar_panel(0))
        self.btn_panel_bookmarks.clicked.connect(lambda: self._switch_sidebar_panel(1))
        self.btn_panel_history.clicked.connect(lambda: self._switch_sidebar_panel(2))
        self.btn_panel_downloads.clicked.connect(lambda: self._switch_sidebar_panel(3))
        self.btn_panel_reading.clicked.connect(lambda: self._switch_sidebar_panel(4))
        self.btn_new_tab = QPushButton("+  New Tab")
        self.btn_new_tab.setObjectName("NewTabBtn")
        self.btn_new_tab.setToolTip("Ctrl+T")
        self.btn_new_tab.clicked.connect(lambda: self.add_new_tab(None, "New Tab"))
        # The caret is part of the label, not Qt's ::menu-indicator subcontrol:
        # the subcontrol anchors itself to the bottom-right of a *styled*
        # button, which drew the arrow half outside the button.
        self.btn_options = QPushButton("⚙  Control  ▾")
        self.btn_options.setObjectName("OptionsBtn")
        self.options_menu = self._build_options_menu()
        self.btn_options.setMenu(self.options_menu)
        self._master_password = None
        self.btn_new_tab.setAccessibleName("New tab")
        self.btn_options.setAccessibleName("Browser control menu")
        self.sidebar_footer = QWidget()
        self.sidebar_footer.setObjectName("SidebarFooter")
        self.sidebar_footer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sidebar_footer_layout = QVBoxLayout(self.sidebar_footer)
        sidebar_footer_layout.setContentsMargins(0, 4, 0, 0)
        sidebar_footer_layout.setSpacing(6)
        # Same width for both actions: two buttons of different lengths centred in
        # a column read as an accident, an even pair reads as a toolbar.
        self.btn_new_tab.setMinimumWidth(98)
        self.btn_options.setMinimumWidth(98)
        sidebar_footer_layout.addWidget(self.btn_new_tab)
        sidebar_footer_layout.addWidget(self.btn_options)
        self.sidebar_layout.addWidget(self.sidebar_footer)
        self.main_splitter.addWidget(self.sidebarWidget)

        self.content_widget = _BrowserContentArea()
        self.content_widget.setObjectName("ContentArea")
        self.content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Explicit floor for layouts that read minimumWidth rather than the
        # overridden minimumSizeHint above.
        self.content_widget.setMinimumWidth(0)
        self.content_layout = QVBoxLayout(self.content_widget)
        if self.embedded:
            self.content_layout.setContentsMargins(2, 2, 2, 2)
            self.content_layout.setSpacing(3)
        else:
            self.content_layout.setContentsMargins(2, 2, 2, 2)
            self.content_layout.setSpacing(2)
        # The toolbar itself lives in TopBarMixin (window_topbar.py) — this used
        # to be ~110 lines of widget construction inline here.
        self._build_topbar()
        # Chrome-style load progress: a 3px accent bar directly under the
        # toolbar (v6.5 audit: zero loadProgress feedback anywhere in the app).
        self.load_progress = QProgressBar(self.content_widget)
        self.load_progress.setObjectName("LoadProgress")
        self.load_progress.setRange(0, 100)
        self.load_progress.setTextVisible(False)
        self.load_progress.setFixedHeight(3)
        self.load_progress.hide()
        self.content_layout.addWidget(self.load_progress, 0)
        self.inline_ai_panel = QFrame()
        self.inline_ai_panel.setObjectName("SectionCard")
        inline_ai_layout = QVBoxLayout(self.inline_ai_panel)
        inline_ai_layout.setContentsMargins(12, 12, 12, 12)
        inline_ai_layout.setSpacing(8)
        ai_row = QHBoxLayout()
        self.inline_ai_input = QLineEdit()
        self.inline_ai_input.setPlaceholderText("Ask about this page...")
        self.inline_ai_ask = QPushButton("Ask")
        self.inline_ai_close = QPushButton("Hide")
        ai_row.addWidget(self.inline_ai_input, 1)
        ai_row.addWidget(self.inline_ai_ask)
        ai_row.addWidget(self.inline_ai_close)
        inline_ai_layout.addLayout(ai_row)
        self.inline_ai_answer = QTextEdit()
        self.inline_ai_answer.setReadOnly(True)
        self.inline_ai_answer.setPlaceholderText("The page-aware assistant will answer here.")
        inline_ai_layout.addWidget(self.inline_ai_answer)
        self.inline_ai_panel.hide()
        self.inline_ai_input.returnPressed.connect(self._run_inline_ai)
        self.inline_ai_ask.clicked.connect(self._run_inline_ai)
        self.inline_ai_close.clicked.connect(self.inline_ai_panel.hide)
        # Kept out of the layout: the widgets move into the AI side dock below
        # (v6.5 replaced the cramped top strip with a Copilot-style sidebar).
        self.ai_actions_available = embedded
        if not self.ai_actions_available:
            self.btn_ai.hide()
            self.inline_ai_panel.hide()
        self.web_container = QWidget()
        self.web_container.setObjectName("WebContainer")
        self.web_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.web_container.setMinimumWidth(0)
        self.web_container_layout = QVBoxLayout(self.web_container)
        self.web_container_layout.setContentsMargins(0, 0, 0, 0)
        self.web_container_layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stack.setMinimumWidth(0)
        self.web_container_layout.addWidget(self.stack, 1)
        # Opera GX-style web panels: a right dock holding a slim WebEngine view
        # that shares the main profile (logins persist across sessions). The
        # dock frame is built here; its view is created lazily because the
        # QWebEngineProfile does not exist yet at this point.
        self._build_web_panel_dock()
        # Vivaldi/Arc-style split view: a LEFT dock holding a second live view
        # so two pages sit side by side in one workspace.
        self._build_split_dock()
        self.panel_split = QSplitter(Qt.Horizontal)
        self.panel_split.setChildrenCollapsible(False)
        self.panel_split.setHandleWidth(2)
        self.panel_split.setMinimumWidth(0)
        self.panel_split.addWidget(self.split_dock)
        self.panel_split.addWidget(self.web_container)
        self.panel_split.addWidget(self.panel_dock)
        # stretch the live page, not the optional left split dock
        self.panel_split.setStretchFactor(0, 0)
        self.panel_split.setStretchFactor(1, 1)
        self.panel_dock.setMinimumWidth(0)
        self.panel_dock.hide()
        # Edge-Copilot-style AI sidebar: chat with the visible page without
        # leaving the browser workspace. Reuses the inline AI widgets, but as
        # a docked pane with room for a real answer.
        self.ai_dock = QFrame()
        self.ai_dock.setObjectName("AISideDock")
        ai_dock_layout = QVBoxLayout(self.ai_dock)
        ai_dock_layout.setContentsMargins(0, 0, 0, 0)
        ai_dock_layout.setSpacing(0)
        ai_header = QFrame()
        ai_header.setObjectName("WebPanelHeader")
        ai_header_layout = QHBoxLayout(ai_header)
        ai_header_layout.setContentsMargins(8, 3, 6, 3)
        ai_lbl = QLabel("✦ AI — this page")
        ai_lbl.setObjectName("PageTitle")
        ai_font = ai_lbl.font()
        ai_font.setPointSize(9)
        ai_font.setBold(True)
        ai_lbl.setFont(ai_font)
        ai_header_layout.addWidget(ai_lbl, 1)
        self.btn_ai_dock_close = QToolButton()
        self.btn_ai_dock_close.setObjectName("TopIconButton")
        self.btn_ai_dock_close.setText("✕")
        self.btn_ai_dock_close.setToolTip("Close AI sidebar")
        self.btn_ai_dock_close.clicked.connect(self.close_ai_sidebar)
        ai_header_layout.addWidget(self.btn_ai_dock_close)
        ai_dock_layout.addWidget(ai_header, 0)
        ai_body = QWidget()
        ai_body_layout = QVBoxLayout(ai_body)
        ai_body_layout.setContentsMargins(8, 8, 8, 8)
        ai_body_layout.setSpacing(6)
        self.inline_ai_input.setParent(None)
        self.inline_ai_answer.setParent(None)
        self.inline_ai_input.setMinimumHeight(30)
        self.inline_ai_answer.setMaximumHeight(16777215)
        ai_body_layout.addWidget(self.inline_ai_answer, 1)
        ai_body_layout.addWidget(self.inline_ai_input, 0)
        ask_row = QHBoxLayout()
        ask_row.addStretch(1)
        self.inline_ai_ask.setParent(None)
        self.inline_ai_close.setParent(None)
        self.inline_ai_close.hide()
        ask_row.addWidget(self.inline_ai_ask)
        ai_body_layout.addLayout(ask_row)
        ai_dock_layout.addWidget(ai_body, 1)
        # Keep the closed AI dock out of QSplitter's minimum math; restore the
        # readable width only while the dock is actually shown.
        self.ai_dock.setMinimumWidth(0)
        self.ai_dock.setMaximumWidth(560)
        self.panel_split.addWidget(self.ai_dock)
        self.ai_dock.hide()
        # Slim vertical strip: the GX-way of docking controls without eating
        # horizontal space — two icon toggles manage both docks from one place.
        self.dock_rail = QFrame()
        self.dock_rail.setObjectName("DockRail")
        rail_layout = QVBoxLayout(self.dock_rail)
        rail_layout.setContentsMargins(3, 6, 3, 6)
        rail_layout.setSpacing(4)
        self.btn_rail_panels = QToolButton()
        self.btn_rail_panels.setObjectName("SidebarPanelBtn")
        self.btn_rail_panels.setText("◫")
        self.btn_rail_panels.setToolTip("Toggle web panel (Telegram, Discord, ...)")
        self.btn_rail_panels.setCheckable(True)
        self.btn_rail_panels.clicked.connect(lambda: self.show_web_panel_menu())
        self.btn_rail_ai = QToolButton()
        self.btn_rail_ai.setObjectName("SidebarPanelBtn")
        self.btn_rail_ai.setText("✦")
        self.btn_rail_ai.setToolTip("Toggle AI sidebar (chat with this page)")
        self.btn_rail_ai.setCheckable(True)
        self.btn_rail_ai.clicked.connect(self.toggle_ai_sidebar)
        rail_layout.addWidget(self.btn_rail_panels)
        rail_layout.addWidget(self.btn_rail_ai)
        # Mini media player: appears when a tab is audible — play/pause and
        # mute without hunting for the tab (Edge/Opera-style).
        self.btn_media_play = QToolButton()
        self.btn_media_play.setObjectName("SidebarPanelBtn")
        self.btn_media_play.setText("⏸")
        self.btn_media_play.setToolTip("Play / pause the audible tab")
        self.btn_media_play.clicked.connect(self._toggle_media_playback)
        self.btn_media_play.hide()
        self.btn_media_mute = QToolButton()
        self.btn_media_mute.setObjectName("SidebarPanelBtn")
        self.btn_media_mute.setText("🔇")
        self.btn_media_mute.setToolTip("Mute / unmute the audible tab")
        self.btn_media_mute.clicked.connect(self._toggle_media_mute)
        self.btn_media_mute.hide()
        rail_layout.addWidget(self.btn_media_play)
        rail_layout.addWidget(self.btn_media_mute)
        rail_layout.addStretch(1)
        self.dock_rail.setFixedWidth(34)
        self.panel_split.addWidget(self.dock_rail)
        self.panel_split.setStretchFactor(2, 0)
        self.panel_split.setStretchFactor(3, 0)
        self.panel_split.setStretchFactor(4, 0)
        self.content_layout.addWidget(self.panel_split, 1)
        # Chrome-style link-hover preview: the target URL shows in a slim strip
        # at the bottom-left while hovering links (never blocks the page — it
        # is transparent for mouse events).
        self.link_preview = QLabel(self.content_widget)
        self.link_preview.setObjectName("LinkPreview")
        self.link_preview.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.link_preview.hide()
        self.main_splitter.addWidget(self.content_widget)
        # Set this per child after both widgets exist.  PyQt6's splitter can
        # otherwise retain a child-specific default even when the global flag
        # was set before addWidget(), especially after nested dock layouts
        # update their size hints.
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        initial_sidebar = self._sidebar_expanded_nominal_width()
        self.main_splitter.setSizes([initial_sidebar, max(420, (1216 if self.embedded else 1228) - initial_sidebar)])
        # Dragging the divider is the natural way users expect to bring the
        # collapsed sidebar back; wire it up so a collapsed rail
        # can always be widened back by hand, not only via the tiny toggle.
        self.main_splitter.splitterMoved.connect(self._on_main_splitter_moved)
        # Give the divider a real grab-area (the app-wide QSS handle is only
        # 3px). It is resize-only: collapse/expand belongs to the explicit
        # sidebar arrow, never an accidental click on this divider.
        self.main_splitter.setHandleWidth(8)
        self._sidebar_split_press = None
        _split_handle = self.main_splitter.handle(1)
        if _split_handle is not None:
            _split_handle.installEventFilter(self)
        self.lbl_tab_count.setVisible(False)
        self.workspace_combo.setVisible(False)

        self.browsers = []
        self._incognito_profiles = []
        self._dev_windows = []
        self._cookie_filter = None
        self._trusted_site_profiles = {}
        self.ext_path = prefs.ext_path(self.base_dir)
        if not os.path.exists(self.ext_path):
            os.makedirs(self.ext_path)
        self._user_extension_scripts_cache = None
        data_path = app_paths.browser_data_path(self.base_dir)
        if not os.path.exists(data_path):
            os.makedirs(data_path)
        slot = self._shell_slot()
        profile_name = "MeiProfile-%s" % slot
        os.makedirs(os.path.join(data_path, slot), exist_ok=True)
        self.profile = QWebEngineProfile(profile_name, self)
        self._configure_web_profile(self.profile)
        # Highlight-selected-text + copy bubble: profile-level so it covers every
        # page of this browser AND embedded previews that share the profile.
        try:
            ensure_text_highlight_script(self.profile, prefs.get_text_highlight_enabled(self.base_dir), self.base_dir)
        except Exception:
            pass
        self.interceptor = adblock.TrackingBlocker(self, self.base_dir)
        self.interceptor.https_only = prefs.get_https_only(self.base_dir)
        self.interceptor.reload_filter_file()
        self.profile.setUrlRequestInterceptor(self.interceptor)
        # Auto-refresh subscribed filter lists in the background so the
        # blocklist keeps itself fresh without blocking startup.
        self._refresh_adblock_subscriptions_async()

        self.tab_manager = tab_manager.TabManager(self)
        self._apply_workspace_filter()
        self._apply_saved_proxy()
        self._load_block_third_party_cookies_pref()
        self._load_dark_web_pref()
        self._load_data_saver_pref()
        self._load_disable_webgl_pref()
        self._load_defer_background_pref()
        self._dynamic_bg_phase = 0
        self._dynamic_bg_timer = QTimer(self)
        self._dynamic_bg_timer.timeout.connect(self._tick_dynamic_background)
        self._load_ui_dynamic_background_pref()
        self.apply_styles()
        self._apply_responsive_layout()
        # Restore the last web panel if it was open when the app closed.
        _panel_title, panel_url = prefs.get_last_web_panel(self.base_dir)
        if prefs.get_web_panel_visible(self.base_dir) and panel_url:
            QTimer.singleShot(400, lambda: self.toggle_web_panel(_panel_title, panel_url))
        self._audio_indicator_timer = QTimer(self)
        self._audio_indicator_timer.timeout.connect(self._update_audio_indicators)
        self._audio_indicator_timer.start(5000)
        # Chrome-style auto memory saver: every 30s, freeze background tabs when
        # the process working set is above the threshold.
        self._memory_saver_timer = QTimer(self)
        self._memory_saver_timer.timeout.connect(self._auto_memory_saver_tick)
        self._memory_saver_timer.start(30_000)
        # Android bridge → real tabs: MeiRemote can ask the desktop to open a web
        # app (or any URL). The bridge thread writes a request file; drain it here.
        self._open_request_timer = QTimer(self)
        self._open_request_timer.timeout.connect(self._drain_open_requests)
        self._open_request_timer.start(2500)
        # Crash-safe session autosave: tabs survive a power loss / crash, not
        # just a clean quit. Cheap: reuses the same payload as closeEvent.
        self._session_autosave_timer = QTimer(self)
        self._session_autosave_timer.timeout.connect(self._autosave_session)
        self._session_autosave_timer.start(5 * 60 * 1000)
        if start_tabs:
            # Start from saved tab set (listtab)
            self.tab_manager.begin_batch()
            try:
                active_index = next(
                    (idx for idx, tab in enumerate(start_tabs) if tab.get("active") and tab.get("url")),
                    next((idx for idx, tab in enumerate(start_tabs) if tab.get("url")), 0),
                )
                for idx, t in enumerate(start_tabs):
                    url = t.get("url") or ""
                    if not url:
                        continue
                    is_active = idx == active_index
                    self.tab_manager.add_tab(QUrl(url), t.get("title") or "Loading...", is_active=is_active, session_data=t)
            finally:
                self.tab_manager.end_batch()
        else:
            mode, home_url = prefs.get_startup_prefs(self.base_dir)
            session_path = prefs.session_path(self.base_dir)
            if mode == "restore" and os.path.exists(session_path):
                try:
                    session_state = prefs.session_state_load(self.base_dir)
                    tabs = session_state.get("tabs", [])
                    if self._window_slot_hint in ("primary", "secondary"):
                        legacy_ws = "ws2" if self._window_slot_hint == "secondary" else "ws1"
                        tabs = [tab for tab in tabs if isinstance(tab, dict) and (
                            tab.get("window_slot") == self._window_slot_hint if tab.get("window_slot") else
                            tab.get("workspace_id", "ws1") == legacy_ws
                        )]
                    if not tabs:
                        # No saved tabs (mode still "restore"): fall back to the
                        # configured startup page. v6.4 tested mode == "newtab"
                        # here — always false inside a "restore" branch — so the
                        # new-tab path was dead code.
                        self.add_new_tab(None, "New Tab")
                    else:
                        active_index = next((idx for idx, tab in enumerate(tabs) if tab.get("active")), 0)
                        self.tab_manager.begin_batch()
                        try:
                            for idx, tab in enumerate(tabs):
                                url = tab.get("url") or home_url or "https://google.com"
                                self.tab_manager.add_tab(QUrl(url), tab.get("title") or "Loading...", is_active=(idx == active_index), session_data=tab)
                        finally:
                            self.tab_manager.end_batch()
                except Exception:
                    self.tab_manager.add_tab(QUrl(home_url or "https://google.com"), "Home")
            else:
                if mode == "newtab":
                    self.add_new_tab(None, "New Tab")
                else:
                    self.add_new_tab(QUrl(home_url or "https://google.com"), "Home")

        self._check_bootstrap_import_payload()
        # Every visible string is selectable/copyable: labels highlight with
        # the mouse, buttons get a right-click "Copy text" menu.
        from litebrowser.ui.textselect import enable_text_selection

        enable_text_selection(self)

    def _escape_in_browser(self):
        if getattr(self, "_zen_mode", False):
            self.toggle_zen_mode()
            return
        browser = self.current_browser()
        if browser is not None and browser.property("mei_loading"):
            browser.stop()
            return
        bar = getattr(self, "_find_bar", None)
        if bar is not None and bar.isVisible():
            self._close_find_bar()

    def _autosave_session(self):
        if getattr(self, "_closing", False):
            self._session_autosave_timer.stop()
            return
        try:
            current = self.current_browser()
            tabs = []
            for i, browser in enumerate(self.browsers):
                payload = self._tab_state_payload(i, browser, current)
                if payload:
                    tabs.append(payload)
            prefs.session_state_save(self.base_dir, {"tabs": tabs}, window_slot=self._session_slot())
        except Exception:
            pass

    def _session_slot(self):
        return self._window_slot_hint if self._window_slot_hint in ("primary", "secondary") else None

    def persist_state(self):
        prefs.session_state_save(self.base_dir, {"tabs": self.get_current_tab_state()}, window_slot=self._session_slot())
        self._auto_save_tab_set()
        return True

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        for timer in self.findChildren(QTimer):
            timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
        QApplication.instance().removeEventFilter(self)

    def set_workspace_id(self, workspace_id, persist=False):
        if not workspace_id:
            return
        self.current_workspace_id = workspace_id
        self._refresh_workspace_combo()
        if persist:
            workspace_manager.set_current_id(self.base_dir, workspace_id)
        self._apply_workspace_filter()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()
        # Keep the hover-preview strip pinned to the bottom edge.
        preview = getattr(self, "link_preview", None)
        if preview is not None and preview.isVisible():
            preview.move(8, self.content_widget.height() - preview.height() - 4)

    def _sidebar_expanded_nominal_width(self):
        """Preferred sidebar width when expanded (not collapsed rail)."""
        width = max(0, self.width())
        tiny = width < 900
        tight = width < 1120
        compact = width < 1400
        if tiny:
            return 200
        if tight:
            return 220
        if compact:
            return 240
        return 260

    def _collapsed_rail_width(self):
        """Width of the rail while the sidebar is collapsed.

        Never returns 0 and the rail is never hidden: the expand toggle lives
        inside the sidebar, so a 0-width/hidden rail would make the collapsed
        state irreversible (the tab desk vanishes until a full restart).  The
        rail is wide enough (~50px) to read as a real interactive strip with
        the expand button clearly visible - a 26-30px sliver just looked like
        the sidebar had disappeared.
        """
        return 54 if max(0, self.width()) >= 640 else 46

    def _apply_responsive_layout(self):
        width = max(0, self.width())
        compact = width < 1400
        tight = width < 1120
        tiny = width < 900
        xtiny = width < 640
        rail = self._collapsed_rail_width()

        _anim = getattr(self, "_sidebar_anim", None)
        _sidebar_anim_idle = _anim is None or _anim.state() != QAbstractAnimation.Running
        if hasattr(self, "sidebarWidget") and _sidebar_anim_idle:
            if self.sidebar_collapsed:
                # Rail stays visible and wide-open for the splitter handle
                # (minimum only), so the sidebar can always be pulled back out
                # by dragging - never locked at zero or at a dead 30px.
                self.sidebarWidget.setMinimumWidth(rail)
                self.sidebarWidget.setMaximumWidth(800)
                self.sidebarWidget.setVisible(True)
                # If a prior interrupted anim or parent resize left the pane
                # narrower than the rail, snap it back so the › toggle stays
                # reachable without needing a shell re-layout workaround.
                if self.sidebarWidget.width() < rail:
                    sw = max(0, self.main_splitter.width())
                    if sw > 0:
                        self.main_splitter.setSizes([rail, max(280, sw - rail)])
            else:
                self.sidebarWidget.setMinimumWidth(120)
                self.sidebarWidget.setMaximumWidth(800)
                # Nested shell/dock splitters can briefly force this child to
                # zero while they recalculate.  Also heal a stuck min==max lock
                # left by older animation code.
                if (
                    self.sidebarWidget.width() < 120
                    or self.sidebarWidget.isHidden()
                    or self.sidebarWidget.maximumWidth() <= self.sidebarWidget.minimumWidth() + 1
                ):
                    self._queue_expanded_sidebar_recovery()
        self._apply_sidebar_collapse_visibility()

        if hasattr(self, "topbar_layout"):
            self.topbar_layout.setSpacing(2 if xtiny else 3 if tight else 4)
        panel_columns = 3 if getattr(self, "sidebarWidget", self).width() < 190 else 5
        for index, attr in enumerate(("btn_panel_tabs", "btn_panel_bookmarks", "btn_panel_history", "btn_panel_downloads", "btn_panel_reading")):
            button = getattr(self, attr, None)
            if button is not None:
                button.setProperty("compactIcon", True)
                button.setMinimumSize(32, 32)
                button.setMaximumWidth(16777215)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                if hasattr(self, "sidebar_panel_buttons"):
                    self.sidebar_panel_buttons.addWidget(button, index // panel_columns, index % panel_columns)

        for button in (
            getattr(self, "btn_back", None),
            getattr(self, "btn_forward", None),
            getattr(self, "btn_reload", None),
            getattr(self, "btn_vpn_hub", None),
            getattr(self, "btn_ai", None),
            getattr(self, "btn_page_menu", None),
        ):
            if button:
                button.setMinimumWidth(24 if xtiny else 26 if tiny else 28)
                button.setMaximumWidth(34 if xtiny else 40 if tiny else 46 if tight else 52)
                button.setMinimumHeight(32)
                button.setMaximumHeight(36)
                button.setProperty("compactIcon", True)
                if button is getattr(self, "btn_vpn_hub", None):
                    button.setMinimumWidth(48)
                    button.setMaximumWidth(60)

        if hasattr(self, "search_engine"):
            self.search_engine.setVisible(not tiny)
            self.search_engine.setMaximumWidth(90 if tight else 112)
        if hasattr(self, "lbl_site_state"):
            # Connection pill keeps one fixed width (see _apply_site_state_pill), so
            # this only decides whether it fits at all. It also has to be an
            # informative state to show at any width — see
            # _sync_site_pill_visibility, which the flag below feeds.
            self._site_pill_fits = not tight
            self._sync_site_pill_visibility()

        if hasattr(self, "url_bar"):
            self.url_bar.setMinimumWidth(100 if xtiny else 160 if tiny else 240 if tight else 320 if compact else 400)

        if hasattr(self, "btn_page_menu"):
            self.btn_page_menu.setVisible(not xtiny)

        if getattr(self, "_topbar_collapsed", False):
            self._apply_topbar_collapse()


    def _check_for_updates_from_browser(self):
        shell = self.window()
        if hasattr(shell, "run_update_check"):
            shell.run_update_check(manual=True)

    def configure_google_oauth_client_id(self):
        current = prefs.get_google_oauth_client_id(self.base_dir) or os.environ.get("LITEBROWSER_GOOGLE_CLIENT_ID", "")
        text, ok = QInputDialog.getText(
            self,
            "Google OAuth Client ID",
            "Paste your Google OAuth Desktop Client ID "
            "(must be a 'Desktop app' type in Google Cloud Console, "
            "ends with .apps.googleusercontent.com):",
            text=current,
        )
        if not ok:
            return
        cid = (text or "").strip()
        prefs.set_google_oauth_client_id(self.base_dir, cid)

        bad_format_hint = ""
        if cid and not cid.endswith(".apps.googleusercontent.com"):
            bad_format_hint = (
                "\n\nNote: this Client ID does not end with '.apps.googleusercontent.com'  "
                "you may have pasted a client_secret by mistake or copied incompletely. Double-check it in Google Cloud Console."
            )

        QMessageBox.information(
            self,
            "Google OAuth",
            "Client ID saved."
            "\n\nMei uses the Device Code flow to sign in to Google  "
            "you only need a Client ID, no Redirect URI configuration."
            f"\n\n{bad_format_hint}",
        )

    def test_google_oauth_configuration(self):
        """Check if the Google OAuth client ID looks valid."""
        client_id = prefs.get_google_oauth_client_id(self.base_dir) or os.environ.get("LITEBROWSER_GOOGLE_CLIENT_ID", "")
        lines = []
        if not client_id:
            lines.append("No Client ID set. Use 'Configure OAuth Client ID' to add one.")
        elif not client_id.endswith(".apps.googleusercontent.com"):
            lines.append(
                f"Invalid Client ID: '{client_id[:30]}'"
                "\n   It must end with .apps.googleusercontent.com "
                "('Desktop app' type in Google Cloud Console)."
            )
        else:
            lines.append(f"Client ID looks valid: {client_id[:30]}")
            lines.append("\nMei uses Device Code flow (no Redirect URI needed).")
        QMessageBox.information(self, "Google OAuth check", "\n".join(lines))

    def start_google_oauth_sign_in(self):
        if self._google_auth_running:
            QMessageBox.information(self, "Google OAuth", "Sign-in already in progress.")
            return
        client_id = prefs.get_google_oauth_client_id(self.base_dir) or os.environ.get("LITEBROWSER_GOOGLE_CLIENT_ID", "")
        if not client_id:
            self.configure_google_oauth_client_id()
            client_id = prefs.get_google_oauth_client_id(self.base_dir) or os.environ.get("LITEBROWSER_GOOGLE_CLIENT_ID", "")
            if not client_id:
                return
        self._google_auth_running = True
        self._google_client_id = client_id
        future = self._executor.submit(google_auth.request_device_code, client_id)
        future.add_done_callback(lambda done: self._worker_relay.post(lambda: self._on_device_code_ready(done)))

    def _on_device_code_ready(self, future):
        try:
            device = future.result()
        except google_auth.GoogleAuthError as exc:
            self._google_auth_running = False
            QMessageBox.warning(self, "Google OAuth", str(exc))
            return
        except Exception as exc:
            self._google_auth_running = False
            QMessageBox.warning(self, "Google OAuth", f"Error:\n{exc}")
            return
        verification_url = device.get("verification_url", "https://www.google.com/device")
        user_code = device.get("user_code", "")
        minutes = int(device.get("expires_in", 1800) or 1800) // 60
        QMessageBox.information(
            self,
            "Google Sign-In — Device Code",
            "Step 1: Open this URL in any browser (Chrome, Edge, phone):\n"
            f"    {verification_url}\n\n"
            "Step 2: Enter this code when prompted:\n"
            f"    {user_code}\n\n"
            "Step 3: Sign in to your Google account.\n\n"
            "Mei will detect when you've completed sign-in.\n"
            f"Code expires in {minutes} minutes.",
        )
        future = self._executor.submit(google_auth.poll_device_token, self._google_client_id or "", device)
        future.add_done_callback(lambda done: self._worker_relay.post(lambda: self._finish_google_auth(done)))

    def _finish_google_auth(self, future):
        self._google_auth_running = False
        try:
            result = future.result()
        except google_auth.GoogleAuthError as exc:
            QMessageBox.warning(self, "Google OAuth", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "Google OAuth", f"Error:\n{exc}")
            return
        if result:
            prefs.set_google_account(self.base_dir, result.get("account", {}))
            prefs.set_google_token_cache(self.base_dir, result.get("tokens", {}))
            account = result.get("account", {})
            label = account.get("email") or account.get("name") or "Google account"
            QMessageBox.information(self, "Google OAuth", f"Signed in as {label}.")

    def show_google_account_status(self):
        account = prefs.get_google_account(self.base_dir)
        if not account:
            QMessageBox.information(self, "Google account", "Mei is not signed in to a Google account.")
            return
        label = account.get("name") or "(no name)"
        email = account.get("email") or "(no email)"
        verified = "Yes" if account.get("email_verified") else "No"
        QMessageBox.information(
            self,
            "Google account",
            f"Name: {label}\nEmail: {email}\nEmail verified: {verified}",
        )

    def sign_out_google_account(self):
        prefs.clear_google_account(self.base_dir)
        QMessageBox.information(self, "Google account", "Cleared the saved Google account from this profile.")

    @staticmethod
    def _build_clean_ua(profile):
        raw_ua = profile.httpUserAgent() or ""
        m = re.search(r"Chrome/(\d+)", raw_ua)
        ver = m.group(1) if m else "122"
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{ver}.0.0.0 Safari/537.36"
        )

    def _shell_slot(self):
        slot = (getattr(self, "_window_slot_hint", "") or "").strip()
        return slot if slot in ("primary", "secondary") else "shared"

    def _configure_web_profile(self, profile, off_the_record=False):
        data_path = app_paths.browser_data_path(self.base_dir)
        slot = self._shell_slot()
        slot_dir = os.path.join(data_path, slot)
        os.makedirs(slot_dir, exist_ok=True)
        chrome_ua = self._build_clean_ua(profile)
        profile.setHttpUserAgent(chrome_ua)
        if hasattr(profile, "setHttpAcceptLanguage"):
            profile.setHttpAcceptLanguage("en-US,en;q=0.9")
        if off_the_record:
            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
            if hasattr(profile, "setHttpCacheType"):
                profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
        else:
            profile.setPersistentStoragePath(slot_dir)
            cache_path = os.path.join(slot_dir, "Cache")
            try:
                os.makedirs(cache_path, exist_ok=True)
                profile.setCachePath(cache_path)
            except Exception as exc:
                print("Warning: failed to initialize disk cache, falling back to memory cache:", exc)
                if hasattr(profile, "setHttpCacheType"):
                    profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
            profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        profile.downloadRequested.connect(self.handle_download_request)
        settings = profile.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(QWebEngineSettings.XSSAuditingEnabled, False)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, False)
        # NPAPI-style plug-ins are legacy and keep unnecessary helpers alive.
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, False)
        settings.setAttribute(QWebEngineSettings.AutoLoadImages, not prefs.get_browser_data_saver(self.base_dir))
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.ErrorPageEnabled, True)
        settings.setAttribute(QWebEngineSettings.FocusOnNavigationEnabled, True)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, not prefs.get_disable_webgl(self.base_dir))
        if hasattr(QWebEngineSettings, "Accelerated2dCanvasEnabled"):
            # Canvas-heavy local apps (LinkLumina) paint much smoother on the GPU.
            settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        if hasattr(QWebEngineSettings, "DnsPrefetchEnabled"):
            # Warm DNS lookups reduce the perceived lag when a site first opens.
            settings.setAttribute(QWebEngineSettings.DnsPrefetchEnabled, True)
        if hasattr(QWebEngineSettings, "PlaybackRequiresUserGesture"):
            # Background tabs should never wake a renderer simply to autoplay.
            settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, True)
        if hasattr(QWebEngineSettings, "ServiceWorkersEnabled"):
            settings.setAttribute(QWebEngineSettings.ServiceWorkersEnabled, True)
        if hasattr(QWebEngineSettings, "NavigateOnDropEnabled"):
            settings.setAttribute(QWebEngineSettings.NavigateOnDropEnabled, True)
        if hasattr(profile, "setHttpCacheMaximumSize"):
            # Keep cache useful without allowing two shell windows to reserve a
            # large chunk of memory/disk for speculative page data.
            profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
        if hasattr(QWebEngineSettings, "HyperlinkAuditingEnabled"):
            settings.setAttribute(QWebEngineSettings.HyperlinkAuditingEnabled, False)
        # Chrome-style save-password capture: profile script stashes submitted
        # login credentials in sessionStorage; on_load_finished reads them on
        # the next page and offers to save (only when password manager is on).
        if not off_the_record and prefs.get_password_manager_enabled(self.base_dir):
            try:
                from litebrowser.services import password_manager as _pm
                script = QWebEngineScript()
                script.setName("MeiPasswordCapture")
                script.setInjectionPoint(QWebEngineScript.DocumentCreation)
                script.setWorldId(QWebEngineScript.MainWorld)
                script.setRunsOnSubFrames(False)
                script.setSourceCode(_pm.CAPTURE_INSTALL_SCRIPT)
                profile.scripts().insert(script)
            except Exception:
                pass

    def get_profile_for_url(self, qurl=None, is_incognito=False):
        return self.profile

    def _host_from_url(self, value) -> str:
        try:
            if isinstance(value, QUrl):
                return (value.host() or "").lower()
            return (urlparse(value).netloc or "").lower()
        except Exception:
            return ""

    def is_compatibility_host(self, value) -> bool:
        host = self._host_from_url(value)
        return any(host == item or host.endswith("." + item) for item in COMPATIBILITY_HOSTS)

    def _should_preserve_site_native_ui(self, value) -> bool:
        host = self._host_from_url(value)
        if not host:
            return False
        native_ui_hosts = (
            "accounts.google.com",
            "gemini.google.com",
            "google.com",
            "www.google.com",
            "youtube.com",
            "www.youtube.com",
            "bing.com",
            "www.bing.com",
        )
        return any(host == item or host.endswith("." + item) for item in native_ui_hosts)

    def get_new_tab_html(self):
        engine = prefs.get_search_engine(self.base_dir)
        # The page must open in the mode the shell is showing right now: with auto
        # day/night on, using the stored name opened a bright daytime speed dial
        # inside a dark window.
        mode = prefs.resolved_auto_theme(self.base_dir)
        accent = prefs.get_accent(self.base_dir)
        # build_new_tab_html re-reads history + bookmarks and formats ~30 KB of
        # HTML per tab open; cache it briefly so rapid tab creation stays snappy.
        cache = getattr(self, "_new_tab_html_cache", None)
        key = (engine, mode, accent)
        now = time.time()
        if cache and cache[0] == key and (now - cache[1]) < 30.0:
            return cache[2]
        html = new_tab_page.build_new_tab_html(
            self.base_dir,
            getattr(self, "app_dir", None),
            engine,
            mode=mode,
            accent=accent,
        )
        self._new_tab_html_cache = (key, now, html)
        return html

    def add_new_tab(self, qurl=None, label="New Tab", is_active=True, is_incognito=False):
        self.tab_manager.add_tab(qurl, label, is_active, is_incognito)
        self._apply_workspace_filter()

    def current_browser(self):
        return self.tab_manager.current_browser()

    def _on_change_tab(self, i):
        self.tab_manager.change_tab(i)

    def _refresh_workspace_combo(self):
        self.workspace_combo.blockSignals(True)
        self.workspace_combo.clear()
        for w in workspace_manager.get_workspaces_list(self.base_dir):
            self.workspace_combo.addItem(w["name"], w["id"])
        idx = self.workspace_combo.findData(self.current_workspace_id)
        if idx >= 0:
            self.workspace_combo.setCurrentIndex(idx)
        self.workspace_combo.blockSignals(False)

    def _on_workspace_changed(self, index):
        if index < 0:
            return
        ws_id = self.workspace_combo.currentData()
        if ws_id is None:
            return
        self.current_workspace_id = ws_id
        workspace_manager.set_current_id(self.base_dir, ws_id)
        self._apply_workspace_filter()

    def focus_tab_filter(self):
        """Open the tab desk and put keyboard focus straight into its filter."""
        if self.sidebar_collapsed:
            self._toggle_sidebar_collapse()
        self._switch_sidebar_panel(0)
        self.tab_filter.setFocus()
        self.tab_filter.selectAll()

    def _tab_url_at(self, index):
        item = self.tab_list.item(index)
        metadata = dict(item.data(TAB_META_ROLE) or {}) if item else {}
        url = metadata.get("url", "")
        browser = self.browsers[index] if 0 <= index < len(self.browsers) else None
        if browser is not None:
            try:
                live_url = browser.url().toString()
                if live_url and live_url != "about:blank":
                    url = live_url
            except Exception:
                pass
        return (url or "").strip()

    def copy_workspace_urls(self):
        ws_role = Qt.UserRole + workspace_manager.WORKSPACE_ROLE
        urls = []
        for index in range(self.tab_list.count()):
            item = self.tab_list.item(index)
            if not item or item.data(ws_role) != self.current_workspace_id:
                continue
            url = self._tab_url_at(index)
            if url and url not in ("about:blank", "about:newtab"):
                urls.append(url)
        if not urls:
            QMessageBox.information(self, "Tab Center", "No page URLs in this workspace yet.")
            return
        QApplication.clipboard().setText("\n".join(urls))
        QMessageBox.information(self, "Tab Center", f"Copied {len(urls)} URLs.")

    def close_duplicate_tabs(self):
        """Close duplicate page URLs without touching the active or pinned tab."""
        ws_role = Qt.UserRole + workspace_manager.WORKSPACE_ROLE
        current_row = self.tab_list.currentRow()
        seen = set()
        if current_row >= 0:
            current_url = self._tab_url_at(current_row).split("#", 1)[0].rstrip("/").lower()
            if current_url:
                seen.add(current_url)
        duplicates = []
        for index in range(self.tab_list.count() - 1, -1, -1):
            if index == current_row:
                continue
            item = self.tab_list.item(index)
            if not item or item.data(ws_role) != self.current_workspace_id or item.data(TAB_PINNED_ROLE):
                continue
            normalized = self._tab_url_at(index).split("#", 1)[0].rstrip("/").lower()
            if not normalized or normalized in ("about:blank", "about:newtab"):
                continue
            if normalized in seen:
                duplicates.append(index)
            else:
                seen.add(normalized)
        for index in duplicates:
            self.tab_manager.close_tab(index)
        if duplicates:
            QMessageBox.information(self, "Tab Center", f"Closed {len(duplicates)} duplicate tabs.")
        else:
            QMessageBox.information(self, "Tab Center", "No duplicate URLs found in this workspace.")

    def _queue_tab_filter(self, _text=""):
        """Debounce filter work so a 400-tab workspace stays responsive while typing."""
        if hasattr(self, "_tab_filter_timer"):
            self._tab_filter_timer.start()

    def _tab_matches_filter(self, index, item, query):
        if not query:
            return True
        metadata = dict(item.data(TAB_META_ROLE) or {})
        browser = self.browsers[index] if 0 <= index < len(self.browsers) else None
        hibernated = bool(metadata.get("hibernated"))
        if browser is not None:
            try:
                hibernated = bool(browser.property("hibernated"))
            except Exception:
                pass
        title = (metadata.get("title") or "").lower()
        url = (metadata.get("url") or "").lower()
        widget = item.data(Qt.UserRole)
        if not title and widget:
            try:
                title = widget.text().lower()
            except Exception:
                pass
        host = self._host_from_url(url)
        haystack = " ".join((title, url, host))
        for term in (part.strip().lower() for part in query.split() if part.strip()):
            if term in ("is:sleeping", "is:hibernated", "sleeping", "hibernated"):
                if not hibernated:
                    return False
            elif term in ("is:active", "active"):
                if hibernated:
                    return False
            elif term in ("is:pinned", "pinned"):
                if not bool(item.data(TAB_PINNED_ROLE)):
                    return False
            elif term.startswith("site:"):
                if term[5:] not in host:
                    return False
            elif term.startswith("group:"):
                if term[6:] not in (metadata.get("group") or "").lower():
                    return False
            elif term not in haystack:
                return False
        return True

    def _apply_tab_list_visibility(self):
        """Apply the current workspace and filter together; never let one undo the other."""
        ws_role = Qt.UserRole + workspace_manager.WORKSPACE_ROLE
        query = self.tab_filter.text().strip().lower() if hasattr(self, "tab_filter") else ""
        current_ws = self.current_workspace_id
        visible_rows = []
        # First pass: workspace + filter, as before.
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            tab_ws = item.data(ws_role) if item else None
            if tab_ws is None:
                tab_ws = workspace_manager.PRIMARY_WORKSPACE_ID
            visible = bool(item and tab_ws == current_ws and self._tab_matches_filter(i, item, query))
            item.setHidden(not visible)
            if visible:
                visible_rows.append(i)
        # Second pass: folded groups hide their member rows (the currently
        # selected tab of a folded group stays visible — Chrome keeps the
        # active tab on screen too).
        collapsed_members = {}
        for i in visible_rows:
            item = self.tab_list.item(i)
            if item is None:
                continue
            group = item.data(TAB_GROUP_ROLE) or ""
            if group and bool(item.data(TAB_GROUP_COLLAPSED_ROLE)):
                if item is self.tab_list.currentItem():
                    continue  # active member of a folded group stays visible
                collapsed_members.setdefault(group, []).append(i)
        for _group, rows in collapsed_members.items():
            for i in rows:
                self.tab_list.item(i).setHidden(True)
                if i in visible_rows:
                    visible_rows.remove(i)
        current_row = self.tab_list.currentRow()
        if visible_rows and (current_row not in visible_rows):
            # Only auto-switch when the current tab was hidden by a *workspace*
            # change, not by typing in the filter: switching rows loads a whole
            # different page, which is jarring mid-search (v6.4 UX bug).
            if not query:
                self.tab_list.setCurrentRow(visible_rows[0])
        return visible_rows

    def _apply_workspace_filter(self):
        self._apply_tab_list_visibility()
        self.tab_manager.update_tab_count()

    def _switch_sidebar_panel(self, index):
        self.sidebar_stack.setCurrentIndex(index)
        self._lazy_panel_refresh(index)

    def _lazy_panel_refresh(self, panel_index, force=False):
        current = self.sidebar_stack.currentIndex()
        if current == 1 and (force or self.bookmarks_tree.topLevelItemCount() == 0):
            self._load_bookmarks_panel()
        elif current == 2 and (force or self.history_list.count() == 0):
            self._load_history_panel()
        elif current == 3 and (force or self.downloads_list.count() == 0):
            self._load_downloads_panel()
        elif current == 4:
            self._load_reading_list()

    def _load_reading_list(self):
        self.reading_list.clear()
        pages = life_service.load_saved_pages(self.base_dir)
        cont = life_service.continue_reading_page(self.base_dir)
        for p in pages:
            title = (p.get("title") or p.get("url", ""))[:50]
            pct = int(p.get("read_percent", 0) or 0)
            label = f"({pct}%) {title}" if pct else title
            if cont is not None and p.get("url") == cont.get("url"):
                label = "▶ " + label
            # UserRole now carries the clean URL; row text stays display-only.
            self.reading_list.addItem(label)
            self.reading_list.item(self.reading_list.count() - 1).setData(Qt.UserRole, p.get("url", ""))
        if not pages:
            self.reading_list.addItem("No saved pages yet. Use Page menu > Save to reading list.")

    def _on_reading_clicked(self, item):
        url = item.data(Qt.UserRole)
        if url:
            title = (item.text() or url)[:40]
            self.tab_manager.add_tab(QUrl(url), title, is_active=True)
            self._load_reading_list()

    def _add_to_reading_list(self):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        title = browser.title() or url
        life_service.add_saved_page(self.base_dir, title, url)
        self._load_reading_list()
        self._flash_status("Added to your reading list")

    def _filter_tab_list(self, text=""):
        self._apply_tab_list_visibility()
        self.tab_manager.update_tab_count()

    def _load_bookmarks_panel(self):
        self.bookmarks_tree.clear()
        folders = prefs.load_bookmark_folders(self.base_dir)
        folder_map = {f["id"]: f for f in folders}
        tree_folders = {}
        for f in folders:
            item = QTreeWidgetItem([f.get("name", "Unnamed")])
            item.setData(0, Qt.UserRole, ("folder", f["id"]))
            item.setIcon(0, self.style().standardIcon(type(self.style()).StandardPixmap.SP_DirIcon))
            tree_folders[f["id"]] = item
        for fid, item in tree_folders.items():
            parent_id = folder_map[fid].get("parent_id", "")
            if parent_id and parent_id in tree_folders:
                tree_folders[parent_id].addChild(item)
            else:
                self.bookmarks_tree.addTopLevelItem(item)
        for b in prefs.load_bookmarks(self.base_dir):
            title = (b.get("title") or "")[:40]
            url = (b.get("url") or "")[:60]
            bm_item = QTreeWidgetItem([f"{title}  {url}"])
            bm_item.setData(0, Qt.UserRole, ("bookmark", b.get("url", "")))
            bm_item.setIcon(0, self.style().standardIcon(type(self.style()).StandardPixmap.SP_FileIcon))
            folder_id = b.get("folder_id", "")
            if folder_id and folder_id in tree_folders:
                tree_folders[folder_id].addChild(bm_item)
            else:
                self.bookmarks_tree.addTopLevelItem(bm_item)
        self.bookmarks_tree.expandAll()
        if self.bookmarks_tree.topLevelItemCount() == 0:
            # Empty state instead of a blank panel. The row carries no UserRole
            # data and is not draggable, so the click / context-menu handlers
            # treat it as nothing at all.
            hint = QTreeWidgetItem(["No bookmarks yet — press Ctrl+D on a page to save it."])
            hint.setFlags(Qt.ItemIsEnabled)
            self.bookmarks_tree.addTopLevelItem(hint)

    def _add_bookmark_folder(self):
        name, ok = QInputDialog.getText(self, "Bookmark folder", "Folder name:")
        if ok and name.strip():
            folders = prefs.load_bookmark_folders(self.base_dir)
            fid = "folder_" + uuid.uuid4().hex[:8]
            current_item = self.bookmarks_tree.currentItem()
            parent_id = ""
            if current_item:
                kind, data = current_item.data(0, Qt.UserRole) or ("", "")
                if kind == "folder":
                    parent_id = data
            folders.append({"id": fid, "name": name.strip(), "parent_id": parent_id})
            prefs.save_bookmark_folders(self.base_dir, folders)
            self._load_bookmarks_panel()

    def _show_bookmark_context_menu(self, pos):
        item = self.bookmarks_tree.itemAt(pos)
        menu = QMenu(self)  # parented: inherits the shell theme QSS
        add_folder_action = menu.addAction("+ Add subfolder" if item else "+ Add folder")
        add_bm_action = menu.addAction("+ Add bookmark here")
        menu.addSeparator()
        rename_action = None
        delete_action = None
        if item:
            kind, data = item.data(0, Qt.UserRole) or ("", "")
            if kind == "folder":
                rename_action = menu.addAction("Rename folder")
                delete_action = menu.addAction("Delete folder")
            else:
                delete_action = menu.addAction("Delete bookmark")
        action = menu.exec_(self.bookmarks_tree.viewport().mapToGlobal(pos))
        if action == add_folder_action:
            self._add_bookmark_folder()
        elif action == add_bm_action:
            self.save_bookmark()
        if delete_action and action == delete_action:
            kind, data = item.data(0, Qt.UserRole) or ("", "")
            if kind == "folder":
                folders = [f for f in prefs.load_bookmark_folders(self.base_dir) if f["id"] != data]
                bookmarks = [b for b in prefs.load_bookmarks(self.base_dir) if b.get("folder_id") != data]
                prefs.save_bookmark_folders(self.base_dir, folders)
                prefs.save_bookmarks(self.base_dir, bookmarks)
            else:
                bookmarks = [b for b in prefs.load_bookmarks(self.base_dir) if b.get("url") != data]
                prefs.save_bookmarks(self.base_dir, bookmarks)
            self._load_bookmarks_panel()
        if rename_action and action == rename_action:
            kind, data = item.data(0, Qt.UserRole) or ("", "")
            if kind == "folder":
                name, ok = QInputDialog.getText(self, "Rename", "New name:", text=item.text(0))
                if ok and name.strip():
                    folders = prefs.load_bookmark_folders(self.base_dir)
                    for f in folders:
                        if f["id"] == data:
                            f["name"] = name.strip()
                            break
                    prefs.save_bookmark_folders(self.base_dir, folders)
                    self._load_bookmarks_panel()

    def _load_history_panel(self):
        self.history_list.clear()
        session_state = prefs.session_state_load(self.base_dir)
        for item in session_state.get("recently_closed", [])[:12]:
            if item.get("kind") == "window":
                tabs = item.get("tabs", [])
                if not tabs:
                    continue
                title = item.get("title") or f"Window with {len(tabs)} tabs"
                self.history_list.addItem(f"[Recent] {title}")
                self.history_list.item(self.history_list.count() - 1).setData(Qt.UserRole, item)
                continue
            title = item.get("title") or item.get("url", "")
            url = item.get("url", "")
            if not url:
                continue
            self.history_list.addItem(f"[Recent] {title[:48]}")
            self.history_list.item(self.history_list.count() - 1).setData(Qt.UserRole, item)
        entries = prefs.load_history_entries(self.base_dir)
        entries.sort(key=lambda x: -x[0])
        seen = set()
        for _ts, url in entries[:100]:
            if url in seen or not url.startswith("http"):
                continue
            seen.add(url)
            short = url.replace("https://", "").replace("http://", "")[:55]
            self.history_list.addItem(short)
            self.history_list.item(self.history_list.count() - 1).setData(Qt.UserRole, url)
        if self.history_list.count() == 0:
            # Same empty-state treatment as the reading list, so a fresh profile
            # does not show five blank panels.
            self.history_list.addItem("No history yet — pages you open are listed here.")

    def _load_downloads_panel(self):
        from litebrowser.services import download_mgr
        self.downloads_list.clear()
        for i, d in enumerate(download_mgr.load_list(self.base_dir)):
            self.downloads_list.addItem(f"{d.get('status', '?')}  {d.get('filename', '')[:50]}")
            self.downloads_list.item(self.downloads_list.count() - 1).setData(Qt.UserRole, (i, d.get("path", "")))
        if self.downloads_list.count() == 0:
            self.downloads_list.addItem("No downloads yet — files you save appear here.")

    def _on_bookmark_clicked(self, item):
        kind, data = item.data(0, Qt.UserRole) or ("", "")
        if kind == "bookmark" and data:
            self.tab_manager.add_tab(QUrl(data), item.text(0)[:30], is_active=True)

    def _on_history_clicked(self, item):
        data = item.data(Qt.UserRole)
        if isinstance(data, dict) and data.get("kind") == "window":
            tabs = data.get("tabs", [])
            if not tabs:
                return
            for idx, tab in enumerate(tabs):
                url = tab.get("url", "")
                if not url:
                    continue
                self.tab_manager.add_tab(QUrl(url), tab.get("title") or "Loading...", is_active=(idx == 0), session_data=tab)
            return
        if isinstance(data, dict):
            url = data.get("url", "")
        else:
            url = data
        if url:
            self.tab_manager.add_tab(QUrl(url), item.text()[:30], is_active=True, session_data=(data if isinstance(data, dict) else None))

    def _on_download_clicked(self, item):
        data = item.data(Qt.UserRole)
        if data and isinstance(data, (list, tuple)) and len(data) >= 2:
            path = data[1]
            if path and os.path.exists(path):
                try:
                    os.startfile(path)
                except Exception:
                    pass

    def apply_styles(self):
        theme_name = prefs.resolved_auto_theme(self.base_dir)
        accent = prefs.get_accent(self.base_dir)
        qss = theme.main_qss(theme_name, accent)
        self.btn_collapse_sidebar.setStyleSheet(theme.collapse_btn_qss(theme_name, accent))
        self.setStyleSheet(qss)
        # Chrome that carries inline colours (tab rows, connection pill) does not
        # come back through the stylesheet above — re-resolve it explicitly.
        self.refresh_chrome_theme()
        self._apply_collapse_btn_state()
        # Override the app-wide 3px divider only for the sidebar splitter so
        # the collapse/expand rail has a handle that is easy to grab.
        try:
            self.main_splitter.setStyleSheet("QSplitter::handle { width: 8px; }")
        except Exception:
            pass
        self._apply_dynamic_background_overlay()

    def _load_ui_dynamic_background_pref(self):
        self.act_dynamic_bg.blockSignals(True)
        self.act_dynamic_bg.setChecked(prefs.get_ui_dynamic_background(self.base_dir))
        self.act_dynamic_bg.blockSignals(False)
        if self.act_dynamic_bg.isChecked() and not self._dynamic_bg_timer.isActive():
            self._dynamic_bg_timer.start(7200)

    def _load_data_saver_pref(self):
        if not hasattr(self, "act_data_saver"):
            return
        self.act_data_saver.blockSignals(True)
        self.act_data_saver.setChecked(prefs.get_browser_data_saver(self.base_dir))
        self.act_data_saver.blockSignals(False)

    def toggle_data_saver(self):
        enabled = bool(self.act_data_saver.isChecked())
        prefs.set_browser_data_saver(self.base_dir, enabled)
        profiles = [self.profile] + list(getattr(self, "_incognito_profiles", [])) + list(
            getattr(self, "_trusted_site_profiles", {}).values()
        )
        seen = set()
        for profile in profiles:
            if profile is None or id(profile) in seen:
                continue
            seen.add(id(profile))
            try:
                profile.settings().setAttribute(QWebEngineSettings.AutoLoadImages, not enabled)
            except Exception:
                pass

    def _load_disable_webgl_pref(self):
        value = prefs.get_disable_webgl(self.base_dir)
        for act in (getattr(self, "act_disable_webgl", None), getattr(self, "act_page_disable_webgl", None)):
            if act is None:
                continue
            act.blockSignals(True)
            act.setChecked(value)
            act.blockSignals(False)

    def toggle_disable_webgl(self, checked=None):
        # Qt passes the new checked state of the triggering action; fall back to
        # the sidebar action's state when invoked programmatically.
        if checked is None:
            checked = bool(getattr(self, "act_disable_webgl", None) and self.act_disable_webgl.isChecked())
        enabled = bool(checked)
        prefs.set_disable_webgl(self.base_dir, enabled)
        # Keep both menu actions in sync.
        for act in (getattr(self, "act_disable_webgl", None), getattr(self, "act_page_disable_webgl", None)):
            if act is None:
                continue
            act.blockSignals(True)
            act.setChecked(enabled)
            act.blockSignals(False)
        profiles = [self.profile] + list(getattr(self, "_incognito_profiles", [])) + list(
            getattr(self, "_trusted_site_profiles", {}).values()
        )
        seen = set()
        for profile in profiles:
            if profile is None or id(profile) in seen:
                continue
            seen.add(id(profile))
            try:
                profile.settings().setAttribute(QWebEngineSettings.WebGLEnabled, not enabled)
                # Runtime toggling also needs the page-level shim: WebGLEnabled is
                # only read at renderer creation, but this script kills the WebGL
                # entry points on every page and works immediately after reload.
                ensure_webgl_disable_script(profile, enabled)
            except Exception:
                pass
        # Apply to every open tab too (profile defaults don't affect live views),
        # then reload the current page so the change is visible right away.
        for browser in list(getattr(self, "browsers", []) or []):
            if browser is None:
                continue
            try:
                browser.settings().setAttribute(QWebEngineSettings.WebGLEnabled, not enabled)
            except Exception:
                pass
        current = self.current_browser()
        if current is not None:
            try:
                current.reload()
            except Exception:
                pass

    def _load_defer_background_pref(self):
        if not hasattr(self, "act_defer_background"):
            return
        self.act_defer_background.blockSignals(True)
        self.act_defer_background.setChecked(prefs.get_defer_background_tabs(self.base_dir))
        self.act_defer_background.blockSignals(False)

    def toggle_defer_background(self):
        enabled = bool(self.act_defer_background.isChecked())
        prefs.set_defer_background_tabs(self.base_dir, enabled)
        # Existing open tabs are unaffected; the setting governs tabs opened from
        # now on. Freeze the current background tabs immediately if turned on so
        # the choice has an instant effect.
        if enabled:
            self.tab_manager.optimize_memory(notify=False)

    def _refresh_adblock_subscriptions_async(self):
        if not prefs.get_adblock_subscriptions(self.base_dir):
            return

        def _run():
            try:
                adblock.fetch_and_update_subscriptions(self.base_dir)
                return True
            except Exception:
                return False

        def _done(future):
            try:
                if future.result() and getattr(self, "interceptor", None) is not None:
                    self.interceptor.reload_filter_file()
            except Exception:
                pass

        future = self._executor.submit(_run)
        future.add_done_callback(lambda f: self._worker_relay.post(lambda: _done(f)))

    def _refresh_adblock_now(self):
        def _run():
            try:
                adblock.fetch_and_update_subscriptions(self.base_dir)
                return True
            except Exception:
                return False

        def _done(future):
            try:
                ok = bool(future.result())
            except Exception:
                ok = False
            if getattr(self, "interceptor", None) is not None:
                self.interceptor.reload_filter_file()
            QMessageBox.information(
                self,
                "Adblock",
                "Ad-blocking filters updated." if ok else "No filter subscriptions, or the update failed.",
            )

        future = self._executor.submit(_run)
        future.add_done_callback(lambda f: self._worker_relay.post(lambda: _done(f)))

    def _auto_memory_saver_tick(self):
        """Chrome-style memory saver: freeze background tabs when RAM runs hot."""
        rss = _process_rss_mb()
        if rss is None or rss < MEMORY_SAVER_RSS_THRESHOLD_MB:
            return
        self.tab_manager.optimize_memory(notify=False)

    def _drain_open_requests(self):
        """Open URLs requested by the Android bridge (MeiRemote "open app")."""
        try:
            from litebrowser.services import open_request

            requests = open_request.drain_open_requests(self.base_dir)
        except Exception:
            return
        for req in requests:
            url = str(req.get("url") or "").strip()
            if not url.startswith(("http://", "https://", "file://")):
                continue
            label = str(req.get("label") or "").strip() or url
            try:
                self.add_new_tab(QUrl(url), label, is_active=True)
            except Exception:
                pass

    def _live_sleeping_counts(self):
        live = 0
        sleeping = 0
        for browser in self.browsers:
            if browser is None or browser.property("hibernated"):
                sleeping += 1
            else:
                live += 1
        return live, sleeping

    def show_performance_dashboard(self):
        """GX-style control center: live RAM graph, live-tab limiter and one
        click freeze — the resource cockpit Mei's hibernation engine already
        has the machinery for."""
        from litebrowser.ui import theme as _th

        pal = _th._palette(prefs.resolved_auto_theme(self.base_dir), prefs.get_accent(self.base_dir))
        dlg = QDialog(self)
        dlg.setWindowTitle("Mei Control Center")
        dlg.resize(520, 420)
        layout = QVBoxLayout(dlg)
        title = QLabel("⚡ Control Center")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # --- Live RAM mini graph (custom paint, no deps) ---
        class _RamGraph(QWidget):
            def __init__(self, _parent=None):
                super().__init__()
                self.samples = []
                self.limit_mb = MEMORY_SAVER_RSS_THRESHOLD_MB
                self.setMinimumHeight(90)

            def add(self, mb):
                self.samples.append(max(0.0, float(mb or 0)))
                self.samples = self.samples[-60:]
                self.update()

            def paintEvent(self, _event):
                painter = QPainter(self)
                w, h = self.width(), self.height()
                painter.fillRect(self.rect(), QColor(pal["MAIN_BG_ALT"]))
                peak = max([self.limit_mb] + self.samples or [self.limit_mb]) * 1.15 or 1.0
                line_y = int(h - (self.limit_mb / peak) * h)
                painter.setPen(QPen(QColor(pal["DANGER"]), 1, Qt.DashLine))
                painter.drawLine(0, line_y, w, line_y)
                if len(self.samples) >= 2:
                    painter.setPen(QPen(QColor(pal["ACCENT"]), 2))
                    step = w / max(1, len(self.samples) - 1)
                    prev = None
                    for idx, mb in enumerate(self.samples):
                        y = int(h - (mb / peak) * h)
                        x = int(idx * step)
                        if prev is not None:
                            painter.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)
                painter.setPen(QColor(pal["TEXT_MUTED"]))
                painter.drawText(8, 14, f"Process RAM · limit {self.limit_mb} MB")
                if self.samples:
                    painter.drawText(8, h - 8, f"now: {self.samples[-1]:.0f} MB")
                painter.end()

        ram_graph = _RamGraph(dlg)
        ram_graph.setObjectName("SectionCard")
        layout.addWidget(ram_graph, 1)
        lbl_tabs = QLabel("")
        lbl_ram = QLabel("")
        lbl_heap = QLabel("Current tab JS heap: measuring…")
        layout.addWidget(lbl_ram)
        layout.addWidget(lbl_tabs)
        layout.addWidget(lbl_heap)

        # --- Live-tab limiter (real effect: auto_hibernate_threshold) ---
        limit_row = QHBoxLayout()
        limit_lbl = QLabel("")
        limit_combo = QComboBox()
        for label, value in (("6 tabs (default)", 6), ("8 tabs", 8), ("10 tabs", 10), ("14 tabs", 14), ("Unlimited", 99)):
            limit_combo.addItem(label, value)
        current_limit = prefs.get_max_live_tabs(self.base_dir)

        def _apply_limit(index):
            value = limit_combo.itemData(index)
            if value is None:
                return
            try:
                prefs.set_max_live_tabs(self.base_dir, int(value))
                limit_lbl.setText(f"Max live tabs: {value}" if value < 90 else "Max live tabs: unlimited")
                # Background tabs over the new limit hibernate on the next tick;
                # also enforce immediately for instant feedback.
                self.tab_manager._enforce_background_hibernation(active_index=self.tab_list.currentRow())
            except Exception:
                pass

        try:
            limit_combo.setCurrentIndex(max(0, limit_combo.findData(current_limit)))
        except Exception:
            pass
        limit_combo.currentIndexChanged.connect(_apply_limit)
        limit_row.addWidget(QLabel("Max live tabs:"))
        limit_row.addWidget(limit_combo, 1)
        limit_lbl.setText(f"Max live tabs: {current_limit}")
        limit_row.addWidget(limit_lbl)
        layout.addLayout(limit_row)

        # --- RAM-saver threshold ---
        thresh_row = QHBoxLayout()
        thresh_spin = QSpinBox()
        thresh_spin.setRange(200, 8000)
        thresh_spin.setSingleStep(50)
        thresh_spin.setSuffix(" MB")
        thresh_spin.setValue(MEMORY_SAVER_RSS_THRESHOLD_MB)

        def _apply_threshold(v):
            global MEMORY_SAVER_RSS_THRESHOLD_MB
            MEMORY_SAVER_RSS_THRESHOLD_MB = int(v)

        thresh_spin.valueChanged.connect(_apply_threshold)
        thresh_row.addWidget(QLabel("Auto-freeze when RAM exceeds:"))
        thresh_row.addWidget(thresh_spin)
        thresh_row.addStretch(1)
        layout.addLayout(thresh_row)

        def _on_heap(value):
            try:
                val = float(value)
                if val >= 0:
                    lbl_heap.setText(f"Current tab JS heap: {val:.1f} MB")
                else:
                    lbl_heap.setText("Current tab JS heap: unavailable")
            except Exception:
                lbl_heap.setText("Current tab JS heap: unavailable")

        def refresh():
            rss = _process_rss_mb()
            live, sleeping = self._live_sleeping_counts()
            if rss is not None:
                lbl_ram.setText(
                    f"Process RAM: {rss} MB (Memory Saver activates above {MEMORY_SAVER_RSS_THRESHOLD_MB} MB)"
                )
                ram_graph.add(rss)
            else:
                lbl_ram.setText("Process RAM: unavailable on this operating system")
            lbl_tabs.setText(f"Tab: {live} live · {sleeping} sleeping")
            lbl_heap.setText("Current tab JS heap: measuring…")
            current = self.current_browser()
            if current is not None:
                current.page().runJavaScript(
                    "(function(){try{return (performance&&performance.memory)?(performance.memory.usedJSHeapSize/1048576):-1;}catch(e){return -1;}})();",
                    _on_heap,
                )

        refresh()
        graph_timer = QTimer(dlg)
        graph_timer.timeout.connect(refresh)
        graph_timer.start(1000)
        row = QHBoxLayout()
        btn_refresh = QPushButton("Measure again")
        btn_refresh.clicked.connect(refresh)
        btn_freeze = QPushButton("Freeze all background tabs")
        btn_freeze.clicked.connect(lambda: (self.tab_manager.optimize_memory(notify=False), refresh()))
        row.addWidget(btn_refresh)
        row.addWidget(btn_freeze)
        layout.addLayout(row)
        dlg.exec_()

    def _tick_dynamic_background(self):
        self._dynamic_bg_phase += 1
        self._apply_dynamic_background_overlay()

    def _apply_dynamic_background_overlay(self):
        if not getattr(self, "act_dynamic_bg", None) or not self.act_dynamic_bg.isChecked():
            if hasattr(self, "central_widget"):
                self.central_widget.setStyleSheet("")
            return
        # A setStyleSheet with a new string re-polishes the whole widget tree
        # (sidebar + tabs + content). Skip the churn when the window is hidden
        # or minimized so background windows cost nothing.
        if not self.isVisible() or self.windowState() & (Qt.WindowMinimized | Qt.WindowMaximized) == Qt.WindowMinimized:
            return
        # resolved_auto_theme, not get_shell_theme: the dynamic background has to
        # paint the palette the shell is actually showing, or the gradient goes
        # light behind a night window (same root cause as the light chart cards).
        theme_name = prefs.resolved_auto_theme(self.base_dir)
        self.central_widget.setStyleSheet(
            theme.dynamic_main_widget_css(theme_name, self._dynamic_bg_phase, prefs.get_accent(self.base_dir))
        )

    def toggle_ui_dynamic_background(self):
        on = self.act_dynamic_bg.isChecked()
        prefs.set_ui_dynamic_background(self.base_dir, on)
        if on:
            if not self._dynamic_bg_timer.isActive():
                self._dynamic_bg_timer.start(7200)
        else:
            self._dynamic_bg_timer.stop()
            self.central_widget.setStyleSheet("")
        self.apply_styles()

    def open_linklumina_archive_folder(self):
        path = app_paths.linklumina_archive_dir(getattr(self, "app_dir", None))
        app_paths.ensure_linklumina_user_layout(getattr(self, "app_dir", None))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _maybe_local_workspace_perf_hints(self, browser):
        url = (browser.url().toString() or "").lower()
        if not url.startswith("file:"):
            return
        if "/link/" not in url and "cucquanly" not in url and "c%E1%BB%A5c" not in url:
            return
        browser.page().runJavaScript(
            "(function(){try{document.documentElement.style.textRendering='optimizeSpeed';}catch(e){}})();"
        )

    def _dialog_stylesheet(self):
        return theme.dialog_qss(prefs.resolved_auto_theme(self.base_dir), prefs.get_accent(self.base_dir))

    def _palette_lookup(self, key):
        from litebrowser.ui import theme as _th
        return _th._palette(prefs.resolved_auto_theme(self.base_dir), prefs.get_accent(self.base_dir))[key]



    def _on_clipboard_changed(self):
        text = QApplication.clipboard().text().strip()
        if not text or len(text) > 4000:
            return
        if self._clipboard_history and self._clipboard_history[0] == text:
            return
        if text in self._clipboard_history:
            self._clipboard_history.remove(text)
        self._clipboard_history.insert(0, text)
        self._clipboard_history = self._clipboard_history[:20]

    def show_clipboard_history(self):
        """Ctrl+Shift+V: pick one of the last 20 clipboard entries; it goes
        back to the clipboard and (URLs) can paste&go right away."""
        entries = list(getattr(self, "_clipboard_history", []))
        if not entries:
            self._flash_status("Clipboard history is empty")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Clipboard history — Ctrl+Shift+V")
        dialog.resize(520, 420)
        dialog.setStyleSheet(self._dialog_stylesheet())
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for text in entries:
            list_widget.addItem(text.splitlines()[0][:90] if text.splitlines() else "(empty)")
        layout.addWidget(list_widget, 1)
        hint = QLabel("Pick an entry → it returns to the clipboard. URLs offer paste & go.")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)
        row = QHBoxLayout()
        btn_paste = QPushButton("Paste into page")
        btn_paste.setObjectName("TopAccentButton")
        btn_close = QPushButton("Close")
        row.addStretch(1)
        row.addWidget(btn_paste)
        row.addWidget(btn_close)
        layout.addLayout(row)

        def _restore():
            row_ = list_widget.currentRow()
            if row_ < 0:
                return
            text = entries[row_]
            QApplication.clipboard().setText(text)
            dialog.accept()
            if "://" in text and " " not in text:
                self.url_bar.setText(text)
                self.navigate()
            else:
                self._flash_status("Clipboard restored")

        btn_paste.clicked.connect(_restore)
        list_widget.itemDoubleClicked.connect(lambda _i: _restore())
        btn_close.clicked.connect(dialog.accept)
        dialog.exec_()

    def eventFilter(self, obj, ev):
        # Middle-click on the URL bar: paste & go (browser standard).
        from PyQt5.QtCore import QEvent
        from PyQt5.QtCore import Qt as _Qt

        # Workspace divider: resize by drag only. A bare click (or nested
        # layout settling that looks like a click) must never leave the tab
        # desk stuck at a locked/narrow width.
        splitter = getattr(self, "main_splitter", None)
        handle = splitter.handle(1) if splitter is not None else None
        if handle is not None and obj is handle:
            et = ev.type()
            if et == QEvent.Type.MouseButtonPress and ev.button() == _Qt.LeftButton:
                self._sidebar_split_press = (ev.pos(), list(splitter.sizes()))
            elif et in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
                press = getattr(self, "_sidebar_split_press", None)
                self._sidebar_split_press = None
                if press is not None and ev.button() == _Qt.LeftButton:
                    press_pos, press_sizes = press
                    moved = (ev.pos() - press_pos).manhattanLength()
                    if moved < 4 and press_sizes:
                        # Click without drag: keep the pre-click widths.
                        splitter.setSizes(press_sizes)
                    self._ensure_sidebar_splitter_healthy()
            return False
        if obj is getattr(self, "url_bar", None) and ev.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            # The address field and the connection pill share one rounded frame
            # (see TopBarMixin._build_topbar), so focus is shown on the frame —
            # otherwise the "where am I" signal would be a border inside a border.
            self._set_address_cluster_focus(ev.type() == QEvent.Type.FocusIn)
        if obj is getattr(self, "url_bar", None) and ev.type() == QEvent.Type.MouseButtonRelease:
            if ev.button() == _Qt.MiddleButton:
                clipboard = QApplication.clipboard().text().strip()
                if clipboard:
                    self.url_bar.setText(clipboard)
                    self.navigate()
                    self._flash_status("Pasted & navigated")
                ev.accept()
                return True
        # Middle-click a bookmark / history / reading row: open in a new tab.
        if ev.type() == QEvent.Type.MouseButtonRelease and ev.button() == _Qt.MiddleButton:
            if obj is getattr(self, "bookmarks_tree", None).viewport():
                item = self.bookmarks_tree.itemAt(ev.pos())
                if item is not None:
                    self._open_bookmark_in_new_tab(item)
                    ev.accept()
                    return True
            elif obj is getattr(self, "history_list", None).viewport():
                item = self.history_list.itemAt(ev.pos())
                if item is not None and item.text() != "No history yet...":
                    self.tab_manager.add_tab(QUrl(item.text()), item.text()[:40], is_active=False)
                    self._flash_status("Opened history page in a background tab")
                    ev.accept()
                    return True
            elif obj is getattr(self, "reading_list", None).viewport():
                item = self.reading_list.itemAt(ev.pos())
                if item is not None and item.data(Qt.UserRole):
                    self.tab_manager.add_tab(QUrl(item.data(Qt.UserRole)), item.text()[:40], is_active=False)
                    self._flash_status("Opened reading page in a background tab")
                    ev.accept()
                    return True
        return super().eventFilter(obj, ev)

    def _set_address_cluster_focus(self, focused: bool):
        """Mirror address-field focus onto the frame that draws the border."""
        cluster = getattr(self, "address_cluster", None)
        if cluster is None:
            return
        if bool(cluster.property("focused")) == bool(focused):
            return
        cluster.setProperty("focused", bool(focused))
        style = cluster.style()
        style.unpolish(cluster)
        style.polish(cluster)
        cluster.update()

    def _open_bookmark_in_new_tab(self, item):
        data = item.data(0, Qt.UserRole)
        kind, url = data if isinstance(data, tuple) and len(data) == 2 else ("", data)
        if kind == "folder" or not url:
            return
        title = item.text(0) or url[:40]
        self.tab_manager.add_tab(QUrl(url), title[:40], is_active=False)
        self._flash_status("Opened bookmark in a background tab")

    def smart_restart(self, reason: str = ""):
        """Relaunch Mei without losing the session.

        The 5-minute autosave and closeEvent already persist tabs; setting the
        restart marker tells the launcher this exit is intentional so it comes
        straight back up. Used by VPN connect/disconnect and profile switching
        (Chromium reads proxy flags only at process start)."""
        try:
            os.environ["MEI_SMART_RESTART"] = "1"
            if reason:
                os.environ["MEI_RESTART_REASON"] = reason
            # Persist every shell, including a note edited in the other
            # window. Do not hand off the profile while old writers are alive.
            for window in QApplication.topLevelWidgets():
                if hasattr(window, "persist_state") and not window.persist_state():
                    os.environ.pop("MEI_SMART_RESTART", None)
                    os.environ.pop("MEI_RESTART_REASON", None)
                    return
        except OSError:
            os.environ.pop("MEI_SMART_RESTART", None)
            os.environ.pop("MEI_RESTART_REASON", None)
            QMessageBox.warning(self, "Restart", "Your data could not be saved. Restart was canceled.")
            return
        try:
            if getattr(sys, "frozen", False):
                args = [sys.executable]
            else:
                args = [sys.executable, os.path.join(app_paths.project_root(), "browser.py")]
            # The replacement waits for our lifetime lock at startup. Releasing
            # it here allowed two WebEngines/writers into the profile at once.
            # Inherit the environment so MEI_SMART_RESTART / MEI_RESTART_REASON
            # reach the new instance (Popen copies os.environ by default).
            subprocess.Popen(args, close_fds=True)
        except Exception:
            os.environ.pop("MEI_SMART_RESTART", None)
            os.environ.pop("MEI_RESTART_REASON", None)
            QMessageBox.warning(self, "Restart", "Could not relaunch Mei automatically. Please start it again manually.")
            return
        QApplication.instance().quit()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def open_current_in_incognito(self):
        browser = self.current_browser()
        if browser is None:
            return
        url = browser.url().toString()
        if url.startswith("http"):
            self.add_new_tab(QUrl(url), browser.title() or "Incognito", is_active=True, is_incognito=True)
            self._flash_status("Opened in incognito")

    def _copy_page_address(self):
        browser = self.current_browser()
        if browser is None:
            return
        url = browser.url().toString()
        if url:
            QApplication.clipboard().setText(url)
            self._flash_status("Page address copied")

    def hard_reload(self):
        browser = self.current_browser()
        if browser is None:
            return
        try:
            browser.page().triggerAction(QWebEnginePage.ReloadAndBypassCache)
        except Exception:
            browser.reload()
        self._flash_status("Hard reload — cache bypassed")

    def toggle_zen_mode(self):
        """Zen mode: hide every chrome surface (sidebar, toolbar, shells)
        so the page fills the window — reading/presenting without clutter.
        Toggle again (or Esc) to restore exactly what was visible."""
        if getattr(self, "_zen_mode", False):
            self._zen_mode = False
            # Restore prior visibilities captured on entry.
            vis = getattr(self, "_zen_restore", {}) or {}
            self.sidebarWidget.setVisible(vis.get("sidebar", True))
            self.topbar.setVisible(vis.get("topbar", True))
            if getattr(self, "load_progress", None) is not None:
                self.load_progress.setVisible(vis.get("progress", False))
            if self.inline_ai_panel.isVisible() is False and vis.get("panel_split", True):
                pass  # panel_dock manages itself via its own toggle
            self._apply_responsive_layout()
            self._flash_status("Zen mode off")
            return
        self._zen_mode = True
        self._zen_restore = {
            "sidebar": self.sidebarWidget.isVisible(),
            "topbar": self.topbar.isVisible(),
            "progress": getattr(self, "load_progress", None) is not None and self.load_progress.isVisible(),
        }
        self.sidebarWidget.hide()
        self.topbar.hide()
        self._flash_status("Zen mode — Ctrl+Shift+Z to exit")

    def on_link_hovered(self, url, browser=None):
        """Chrome-style bottom-left strip: the link target while hovering."""
        if browser is not None and browser is not self.current_browser():
            return
        preview = getattr(self, "link_preview", None)
        if preview is None:
            return
        url = (url or "").strip()
        if not url:
            preview.hide()
            return
        preview.setText(url[:160])
        preview.adjustSize()
        preview.move(8, self.content_widget.height() - preview.height() - 4)
        preview.show()
        preview.raise_()

    def _track_reading_progress(self, browser):
        """Record scroll % for pages saved to the reading list (auto, silent)."""
        url = browser.url().toString()
        if not url or not url.startswith("http"):
            return
        known = any(p.get("url") == url for p in life_service.load_saved_pages(self.base_dir))
        if not known:
            return

        def _store(pct):
            try:
                life_service.set_reading_progress(self.base_dir, url, pct)
            except Exception:
                pass

        browser.page().runJavaScript(
            "(function(){var d=document.documentElement;"
            "var max=d.scrollHeight-d.clientHeight;if(max<=0)return 0;"
            "return Math.round((d.scrollTop||0)/max*100);})();",
            _store,
        )

    def on_load_progress(self, progress, browser=None):
        """Drive the thin load bar from the *current* tab only."""
        if browser is not None and browser is not self.current_browser():
            return
        try:
            value = int(progress or 0)
        except (TypeError, ValueError):
            value = 0
        if value >= 100 or value <= 0:
            self.load_progress.hide()
            return
        self.load_progress.setValue(value)
        self.load_progress.show()
        self.load_progress.raise_()

    def _flash_status(self, message: str):
        """Non-modal toast: transient feedback without dialog spam (v6.4 used
        a modal QMessageBox for routine actions like mute/auto-reload).
        Styling comes from the shell QSS (#ToastLabel) so it follows the theme."""
        if getattr(self, "_toast_label", None) is None:
            self._toast_label = QLabel(self.central_widget)
            self._toast_label.setObjectName("ToastLabel")
            self._toast_label.hide()
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(self._toast_label.hide)
        toast = self._toast_label
        toast.setText(message)
        toast.adjustSize()
        margin = 24
        x = self.central_widget.width() - toast.width() - margin
        y = self.central_widget.height() - toast.height() - margin
        toast.move(max(margin, x), max(margin, y))
        toast.raise_()
        toast.show()
        self._toast_timer.start(2200)

    def update_urlbar(self, q, browser=None):
        if browser != self.current_browser():
            return
        url_str = q.toString()
        self.sync_navigation(browser)
        self.url_bar.setText(url_str)
        self.url_bar.setCursorPosition(0)
        if hasattr(self, "lbl_site_state"):
            # Glyph + tinted pill: security state readable at a glance (see
            # TopBarMixin._apply_site_state_pill).
            self._apply_site_state_pill(url_str)
        tt = url_str if url_str else "URL or search..."
        if url_str.startswith("http://") and not url_str.startswith("https://"):
            tt += "\n\nWarning: unencrypted connection (HTTP)."
        self.url_bar.setToolTip(tt)

    def record_history(self, qurl, browser=None):
        url_str = qurl.toString()
        if url_str.startswith("http"):
            prefs.append_history_entry(self.base_dir, url_str)
            # Attribute the visit to the tab that actually navigated; v6.4 read
            # the *current* tab's title, so background-tab redirects were logged
            # under whatever page the user was viewing.
            title = ""
            if browser is not None:
                try:
                    title = browser.title()
                except Exception:
                    title = ""
            if not title:
                try:
                    current = self.current_browser()
                    title = current.title() if current is not None else ""
                except Exception:
                    title = ""
            history_service.log_event(self.base_dir, "browser-visit", title or url_str, url_str, {"url": url_str})

    def _extension_cache_signature(self):
        """Fingerprint of Extensions/ so edits invalidate the cache by themselves.

        The cache used to live until the app restarted: editing a user script or
        toggling it in extensions.json changed nothing for already-open tabs.
        """
        entries = []
        try:
            for file_name in sorted(os.listdir(self.ext_path)):
                if not file_name.endswith(".js") and file_name != "extensions.json":
                    continue
                try:
                    entries.append((file_name, os.path.getmtime(os.path.join(self.ext_path, file_name))))
                except OSError:
                    continue
        except OSError:
            return ()
        return tuple(entries)

    def _get_cached_user_extension_scripts(self):
        signature = self._extension_cache_signature()
        cached = self._user_extension_scripts_cache
        if cached is not None and cached[0] == signature:
            return cached[1]
        scripts = []
        try:
            ext_conf_file = os.path.join(self.ext_path, "extensions.json")
            ext_config = {}
            if os.path.exists(ext_conf_file):
                with open(ext_conf_file, "r", encoding="utf-8") as f:
                    ext_config = json.load(f)
            ext_dir = self.ext_path
            for file_name in sorted(os.listdir(ext_dir)):
                if file_name.endswith(".js") and ext_config.get(file_name, False):
                    fpath = os.path.join(ext_dir, file_name)
                    with open(fpath, "r", encoding="utf-8") as f:
                        source = f.read()
                    matches, excludes, name = extension_patterns.parse_user_script_metadata(source)
                    scripts.append({
                        "name": name or file_name,
                        "source": source,
                        "matches": matches,
                        "excludes": excludes,
                    })
        except Exception as e:
            print("Extension load error:", e)
        self._user_extension_scripts_cache = (signature, scripts)
        return scripts

    def invalidate_extension_cache(self):
        """Drop the cached user scripts; the next page load re-reads Extensions/.

        The cache already re-reads when the folder/config changes, but the
        extension dialogs call this explicitly so a toggle or import takes effect
        on the spot instead of waiting for the file mtime to settle.
        """
        self._user_extension_scripts_cache = None

    def on_load_finished(self, ok, browser):
        browser.setProperty("mei_loading", False)
        self.sync_navigation(browser)
        if browser is self.current_browser():
            self.load_progress.hide()
            if not ok and browser.url().scheme() in ("http", "https"):
                self._flash_status("Page did not finish loading · reload to retry")
        if not ok:
            return
        host = (browser.url().host() or "").lower()
        saved_zoom = prefs.get_site_zoom(self.base_dir, host)
        if saved_zoom:
            browser.setZoomFactor(float(saved_zoom))
        preserve_native_ui = self._should_preserve_site_native_ui(browser.url())
        js_queue = []
        if not preserve_native_ui:
            js_queue.append(self._browser_compat_patch_js())
        if self.act_dark_mode.isChecked():
            js_queue.append(self._dark_mode_js(True))
        if not preserve_native_ui:
            page_url = browser.url().toString()
            js_queue.extend(
                ext["source"]
                for ext in self._get_cached_user_extension_scripts()
                if extension_patterns.script_matches(page_url, ext["matches"], ext["excludes"])
            )
        for js in js_queue:
            browser.page().runJavaScript(js)
        if prefs.get_password_manager_enabled(self.base_dir) and prefs.get_autofill_passwords(self.base_dir):
            try:
                from litebrowser.services import password_manager
                if password_manager.HAS_CRYPTO:
                    url_str = browser.url().toString()
                    if url_str.startswith("http"):
                        master = getattr(self, "_master_password", None)
                        if master is None:
                            master = dialogs.ask_master_password(self)
                            if master is not None:
                                self._master_password = master
                        if master:
                            cred = password_manager.get_credentials_for(self.base_dir, url_str, master)
                            if cred:
                                browser.page().runJavaScript(password_manager.build_autofill_script(cred["username"], cred["password"]))
            except Exception:
                pass
        if browser is self.current_browser():
            self._maybe_offer_saved_password(browser)
        host_l = (browser.url().host() or "").lower()
        on_accounts_google = host_l == "accounts.google.com" or host_l.endswith(".accounts.google.com")
        if self.is_compatibility_host(browser.url()) or on_accounts_google:
            title_now = (browser.title() or "").lower()
            url_now = browser.url().toString().lower()
            hay = title_now + " " + url_now
            bot_tokens = ("security verification", "verify you are human", "captcha", "challenge")
            google_block_tokens = (
                "not be secure",
                "couldn't sign you",
                "couldnt sign you",
                "try using a different browser",
                "browser or app may not be secure",
            )
            # Once per host per session: repeated redirects/loads must not nag
            # the user with the same modal every time (v6.4 did).
            if not hasattr(self, "_compat_notified_hosts"):
                self._compat_notified_hosts = set()
            already_notified = host_l in self._compat_notified_hosts
            if any(token in hay for token in bot_tokens):
                if not already_notified:
                    self._compat_notified_hosts.add(host_l)
                    self._flash_status("Anti-bot verification: use Page menu > Open externally")
            elif on_accounts_google and any(token in hay for token in google_block_tokens):
                if not already_notified:
                    self._compat_notified_hosts.add(host_l)
                    QMessageBox.information(
                        self,
                        "Google sign-in",
                        "Google often blocks sign-in inside embedded browsers (Qt WebEngine).\n\n"
                        "Use the page menu (Page) > Open externally to sign in with Chrome or Edge, "
                        "then use Mei for everything else if you prefer.",
                    )

                    if QMessageBox.question(
                        self,
                        "Open externally",
                        "Mei cannot complete Google sign-in here.\n\nOpen this page in Chrome or Edge now?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes,
                    ) == QMessageBox.Yes:
                        self.open_url_in_external_browser(browser.url().toString())
        self._maybe_local_workspace_perf_hints(browser)
        self._track_reading_progress(browser)

    def _browser_compat_patch_js(self):
        return """
        (function() {
            var host = (location.hostname || '').toLowerCase();
            var href = (location.href || '').toLowerCase();
            if (
                host.indexOf('accounts.google.com') >= 0 ||
                host.indexOf('claude.ai') >= 0 ||
                host.indexOf('chatgpt.com') >= 0 ||
                host.indexOf('copilot.microsoft.com') >= 0 ||
                host.indexOf('gemini.google.com') >= 0 ||
                host.indexOf('perplexity.ai') >= 0 ||
                href.indexOf('security verification') >= 0 ||
                href.indexOf('captcha') >= 0 ||
                href.indexOf('challenge') >= 0
            ) {
                return;
            }
            function upgrade(value) {
                if (!value || typeof value !== 'string') return value;
                if (value.indexOf('http://img.youtube.com/') === 0) return value.replace('http://', 'https://');
                if (value.indexOf('http://www.youtube.com/') === 0) return value.replace('http://', 'https://');
                return value;
            }
            ['img', 'source', 'iframe'].forEach(function(tag) {
                document.querySelectorAll(tag).forEach(function(el) {
                    ['src', 'data-src', 'data-thumb'].forEach(function(attr) {
                        if (el.hasAttribute(attr)) {
                            var next = upgrade(el.getAttribute(attr));
                            if (next !== el.getAttribute(attr)) {
                                el.setAttribute(attr, next);
                                if (attr === 'src') el.src = next;
                            }
                        }
                    });
                });
            });
        })();
        """

    def _dark_mode_js(self, enabled):
        if enabled:
            return """
            (function() {
                var host = (location.hostname || '').toLowerCase();
                var href = (location.href || '').toLowerCase();
                if (
                    host.indexOf('claude.ai') >= 0 ||
                    host.indexOf('chatgpt.com') >= 0 ||
                    host.indexOf('copilot.microsoft.com') >= 0 ||
                    host.indexOf('gemini.google.com') >= 0 ||
                    host.indexOf('perplexity.ai') >= 0 ||
                    host.indexOf('google.') >= 0 ||
                    host.indexOf('youtube.') >= 0 ||
                    host.indexOf('bing.') >= 0 ||
                    href.indexOf('security verification') >= 0 ||
                    href.indexOf('captcha') >= 0 ||
                    href.indexOf('challenge') >= 0
                ) {
                    var old = document.getElementById('lite-dark-mode');
                    if (old) old.remove();
                    return;
                }
                if (!document.getElementById('lite-dark-mode')) {
                    var style = document.createElement('style');
                    style.id = 'lite-dark-mode';
                    style.type = 'text/css';
                    style.innerHTML = 'html, body { background: #16110d !important; color: #eadfcd !important; } body { filter: none !important; } img, video, iframe, canvas, svg, picture { filter: none !important; }';
                    document.head.appendChild(style);
                }
            })();
            """
        return "var el = document.getElementById('lite-dark-mode'); if (el) el.parentNode.removeChild(el);"

    def _update_audio_indicators(self):
        """Mark playing tabs with a 🔊 badge in the state slot.

        v6.4 prefixed the tab title with '[Sound] ' (persisting into saved
        sessions and reading a role nothing set); the state column is the
        right home — Pin/Zz live there too."""
        changed = False
        for i in range(len(self.browsers)):
            browser = self.browsers[i]
            if browser is None:
                continue
            item = self.tab_list.item(i)
            if not item:
                continue
            widget = item.data(TAB_WIDGET_ROLE)
            if not widget:
                continue
            try:
                page = browser.page()
                if not page or not hasattr(page, "recentlyAudible"):
                    continue
                audible = bool(page.recentlyAudible())
                # Clean any legacy '[Sound] ' prefix left in titles by old builds.
                text = widget.lbl_title.text()
                if text.startswith("[Sound] "):
                    widget.lbl_title.setText(text.removeprefix("[Sound] "))
                if bool(browser.property("audible")) != audible:
                    browser.setProperty("audible", audible)
                    changed = True
            except Exception:
                pass
        if changed:
            self.tab_manager.refresh_row_state_labels()

    def _go_home(self):
        _, home_url = prefs.get_startup_prefs(self.base_dir)
        url = home_url or "https://google.com"
        if self.current_browser():
            self.current_browser().setUrl(QUrl(url))

    def focus_url_bar(self):
        self.url_bar.setFocus()
        self.url_bar.selectAll()

    def _apply_sidebar_collapse_visibility(self):
        """Thorough collapse: hide the whole tab desk except the expand toggle
        so the web view gets every spare pixel (Opera-GX-style thin rail)."""
        collapsed = bool(getattr(self, "sidebar_collapsed", False))
        tiny = self.width() < 900
        if hasattr(self, "lbl_tab_count"):
            self.lbl_tab_count.setVisible(not tiny and not collapsed)
        if hasattr(self, "workspace_combo"):
            self.workspace_combo.setVisible(not tiny and not collapsed)
        for attr in (
            "sidebar_stack",
            "sidebar_footer",
            "btn_panel_tabs",
            "btn_panel_bookmarks",
            "btn_panel_history",
            "btn_panel_downloads",
            "btn_panel_reading",
        ):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(not collapsed)
        if hasattr(self, "btn_collapse_sidebar"):
            # Always keep the expand toggle visible & tappable in the rail.
            self.btn_collapse_sidebar.setVisible(True)

    def _toggle_sidebar_collapse(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.btn_collapse_sidebar.setText("›" if self.sidebar_collapsed else "‹")
        self._apply_collapse_btn_state()
        self._apply_sidebar_collapse_visibility()
        # Swap to snug margins while collapsed so the toggle actually fits in
        # the narrow rail; restore the normal padding when expanding.
        self.sidebar_layout.setContentsMargins(6 if self.sidebar_collapsed else 8, 10, 6 if self.sidebar_collapsed else 8, 10)
        rail = self._collapsed_rail_width()
        end_open = self._sidebar_expanded_nominal_width()
        start_w = max(rail, self.sidebarWidget.width())
        end_w = rail if self.sidebar_collapsed else min(end_open, max(rail + 20, self.main_splitter.width() // 3))

        # CRITICAL: never animate by locking minimumWidth == maximumWidth.
        # That lock is what made the tab desk "vanish" and refuse to resize
        # until an unrelated shell re-layout (profile rail toggle) unlocked it.
        if self._sidebar_anim is not None:
            try:
                self._sidebar_anim.valueChanged.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._sidebar_anim.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._sidebar_anim.stop()
            self._sidebar_anim = None

        self._release_sidebar_width_lock(rail)

        duration_ms = prefs.motion_duration_ms(getattr(self, "base_dir", None), "workspace")
        if duration_ms == 0:
            sw = max(0, self.main_splitter.width())
            if sw > 0:
                self.main_splitter.setSizes([end_w, max(280, sw - end_w)])
            self._sidebar_anim = None
            self._release_sidebar_width_lock(rail)
            self._apply_responsive_layout()
            return

        self._sidebar_anim = QVariantAnimation(self)
        self._sidebar_anim.setDuration(duration_ms)
        self._sidebar_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._sidebar_anim.setStartValue(float(start_w))
        self._sidebar_anim.setEndValue(float(end_w))

        def _on_sidebar_width(v):
            w = max(rail, round(v))
            sw = max(0, self.main_splitter.width())
            if sw > 0:
                self.main_splitter.setSizes([w, max(280, sw - w)])

        def _on_sidebar_finished():
            self._sidebar_anim = None
            self._release_sidebar_width_lock(rail)
            target = rail if self.sidebar_collapsed else max(120, end_w)
            sw = max(0, self.main_splitter.width())
            if sw > 0:
                self.main_splitter.setSizes([target, max(280, sw - target)])
            self._apply_responsive_layout()

        self._sidebar_anim.valueChanged.connect(_on_sidebar_width)
        self._sidebar_anim.finished.connect(_on_sidebar_finished)
        self._sidebar_anim.start()

    def _release_sidebar_width_lock(self, rail=None):
        """Keep min/max in a resizable range (never min == max)."""
        if rail is None:
            rail = self._collapsed_rail_width()
        if self.sidebar_collapsed:
            self.sidebarWidget.setMinimumWidth(rail)
            self.sidebarWidget.setMaximumWidth(800)
        else:
            self.sidebarWidget.setMinimumWidth(120)
            self.sidebarWidget.setMaximumWidth(800)

    def _ensure_sidebar_splitter_healthy(self):
        """Unlock a stuck desk and restore a usable width if needed.

        The historic bug locked minimumWidth == maximumWidth during the
        collapse animation.  Drag then does nothing; a bare divider click can
        look like the workspace tab vanished.  Profile-rail toggles only
        appeared to "fix" it because they forced a parent resize that ran
        _apply_responsive_layout and unlocked max width.
        """
        sidebar = getattr(self, "sidebarWidget", None)
        splitter = getattr(self, "main_splitter", None)
        if sidebar is None or splitter is None:
            return
        anim = getattr(self, "_sidebar_anim", None)
        if anim is not None and anim.state() == QAbstractAnimation.Running:
            return

        rail = self._collapsed_rail_width()
        self._release_sidebar_width_lock(rail)
        sidebar.show()

        sizes = splitter.sizes()
        if len(sizes) < 2:
            return
        total = max(0, sum(sizes))
        if total <= 0:
            total = max(0, splitter.width())
        if total <= 0:
            return

        if getattr(self, "sidebar_collapsed", False):
            if sizes[0] < rail:
                splitter.setSizes([rail, max(280, total - rail)])
            return

        if sizes[0] < 120 or sidebar.width() < 120:
            target = min(self._sidebar_expanded_nominal_width(), max(120, total - 160))
            splitter.setSizes([target, max(0, total - target)])

    def _on_main_splitter_moved(self, _pos, _index):
        """Keep the tab desk resizable; never collapse from a divider event.

        QSplitter emits splitterMoved for layout changes and harmless clicks
        on some Windows styles, so this signal must never collapse an
        expanded sidebar.  The explicit arrow button is the only collapse
        control.
        """
        anim = getattr(self, "_sidebar_anim", None)
        if anim is not None and anim.state() == QAbstractAnimation.Running:
            return
        if not hasattr(self, "sidebarWidget") or not hasattr(self, "sidebar_layout"):
            return

        # Always unlock first — a stuck min==max is why drag felt broken.
        if self.sidebarWidget.maximumWidth() <= self.sidebarWidget.minimumWidth() + 1:
            self._ensure_sidebar_splitter_healthy()
            return

        rail = self._collapsed_rail_width()
        width = self.sidebarWidget.width()
        if not getattr(self, "sidebar_collapsed", False):
            if width < 120 or self.sidebarWidget.isHidden():
                self._ensure_sidebar_splitter_healthy()
            return
        if width <= rail + 14:
            return
        # User pulled the rail open: restore the full tab desk at once.
        self.sidebar_collapsed = False
        self.btn_collapse_sidebar.setText("‹")
        self._apply_collapse_btn_state()
        self.sidebar_layout.setContentsMargins(8, 10, 8, 10)
        self._apply_sidebar_collapse_visibility()
        self._release_sidebar_width_lock(rail)
        self._apply_responsive_layout()

    def _queue_expanded_sidebar_recovery(self):
        """Restore an expanded desk after a nested splitter squeezes it out."""
        if getattr(self, "_sidebar_recovery_queued", False):
            return
        self._sidebar_recovery_queued = True

        def _recover():
            self._sidebar_recovery_queued = False
            self._ensure_sidebar_splitter_healthy()

        QTimer.singleShot(0, _recover)

    def _apply_collapse_btn_state(self):
        """Repaint the ‹/› toggle for its current state: when collapsed it is
        the only thing on the rail, so it gets a filled accent look that is
        impossible to miss ("did the sidebar disappear?" -> no, tap the ›)."""
        btn = getattr(self, "btn_collapse_sidebar", None)
        if btn is None:
            return
        btn.setProperty("collapsed", bool(getattr(self, "sidebar_collapsed", False)))
        style = btn.style()
        style.unpolish(btn)
        style.polish(btn)
        btn.update()

    def open_cuc_quan_ly_support_page(self):
        self.open_bundled_site("cucquanly")

    def open_bundled_site(self, key: str):
        """Open one of the six chained apps by stable key.

        Prefer the local bundled copy for offline apps, but use the deployed
        URL when a packaged build does not contain that app locally.
        """
        site = next((item for item in app_paths.bundled_sites(getattr(self, "app_dir", None)) if item["key"] == key), None)
        url = (site or {}).get("url") or (site or {}).get("remote")
        if not url:
            QMessageBox.warning(
                self,
                "Project Hub",
                "App '%s' not found locally or online.\n"
                "Place the app folder next to the exe or check its deployed URL." % key,
            )
            return
        self.url_bar.setText(url)
        browser = self.current_browser()
        if browser:
            browser.setUrl(QUrl(url))

    def open_project_hub(self):
        """Open the shared Project Hub landing page (fallback: the new-tab hub)."""
        url = app_paths.project_hub_url(getattr(self, "app_dir", None))
        if url:
            self.url_bar.setText(url)
            browser = self.current_browser()
            if browser:
                browser.setUrl(QUrl(url))
            return
        if self.current_browser():
            self.current_browser().page().setHtml(self.get_new_tab_html(), QUrl("about:newtab"))

    def navigate(self):
        raw = (self.url_bar.text() or "").strip()
        if not raw:
            return
        if raw.lower() in ("newtab", "about:newtab"):
            if self.current_browser():
                self.current_browser().page().setHtml(self.get_new_tab_html(), QUrl("about:newtab"))
            return
        if raw.lower() in ("about:hub", "hub", "about:chain", "chain"):
            self.open_project_hub()
            return
        low = raw.strip().lower()
        if low in ("about:cuc-quan-ly", "cuc-quan-ly", "cql", "cu:", "cu", "cuc", "quanly", "quan-ly"):
            self.open_bundled_site("cucquanly")
            return
        if low in ("about:linklumina", "linklumina", "lum:", "lumina"):
            self.open_bundled_site("linklumina")
            return
        if low in ("about:mas", "mas", "mahoraga", "mahoraga-adapt-system", "adapt-system"):
            self.open_bundled_site("mas")
            return
        if low in ("about:leaderboard", "about:world-leaderboard", "leaderboard", "world-leaderboard", "worldleaderboard"):
            self.open_bundled_site("worldleaderboard")
            return
        if low in ("about:bimat", "bimat", "personalfrequency", "personal-frequency"):
            self.open_bundled_site("bimat")
            return
        if low in ("about:boitoan", "boitoan", "boi-toan", "fortune"):
            self.open_bundled_site("boitoan")
            return
        engine = self.search_engine.currentText()
        url = raw
        if not (raw.startswith("http://") or raw.startswith("https://") or raw.startswith("file://")):
            if "." not in raw or " " in raw:
                url = self._engine_search_url(engine, raw)
            else:
                url = QUrl.fromUserInput(raw).toString()
        if self.current_browser():
            self.current_browser().setUrl(QUrl(url))
            self._maybe_import_from_url(url, show_feedback=True)

    def _check_bootstrap_import_payload(self):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        if not url:
            pending = browser.property("pending_url")
            if pending:
                url = pending.toString()
        self._maybe_import_from_url(url, show_feedback=False)

    def _maybe_import_from_url(self, value: str, show_feedback: bool = False):
        text = (value or "").strip()
        if not text or "importBatchData=" not in text:
            return False
        try:
            parsed = urlparse(text)
            params = parse_qs(parsed.query or "")
            encoded = (params.get("importBatchData") or [""])[0]
            if not encoded:
                return False
            batch = extension_bridge.import_from_encoded_query(self.base_dir, encoded)
        except Exception as exc:
            if show_feedback:
                QMessageBox.warning(self, "Extension import", f"Could not decode importBatchData.\n{exc}")
            return False
        if show_feedback:
            QMessageBox.information(
                self,
                "Extension import",
                f"Received {batch.get('tab_count', 0)} tabs from {batch.get('source_label', 'extension')}.",
            )
        return True

    def _format_extension_batch_label(self, batch):
        source = batch.get("source_browser") or "extension"
        label = batch.get("source_label") or f"Window {batch.get('window_id', '?')}"
        count = int(batch.get("tab_count") or len(batch.get("tabs") or []))
        imported = "Imported" if batch.get("imported_at") else "Stored"
        return f"[{source}] {label} | {count} tab | {imported}"

    def _refresh_extension_import_list(self, widget):
        widget.clear()
        for batch in extension_bridge.load_batches(self.base_dir):
            item = QListWidgetItem(self._format_extension_batch_label(batch))
            item.setData(Qt.UserRole, batch)
            widget.addItem(item)

    def _import_extension_batch_into_tabs(self, batch):
        tabs = batch.get("tabs") or []
        if not tabs:
            QMessageBox.information(self, "Extension import", "This batch has no tabs.")
            return 0
        imported = 0
        active_index = next((idx for idx, tab in enumerate(tabs) if tab.get("active")), 0)
        for idx, tab in enumerate(tabs):
            url = tab.get("url") or ""
            if not url:
                continue
            self.tab_manager.add_tab(
                QUrl(url),
                tab.get("title") or "Imported tab",
                is_active=(idx == active_index and imported == 0),
                session_data={
                    "url": url,
                    "title": tab.get("title") or url,
                    "pinned": bool(tab.get("pinned")),
                    "active": idx == active_index,
                    "workspace_id": self.current_workspace_id,
                },
            )
            imported += 1
        if imported:
            extension_bridge.mark_batch_imported(self.base_dir, batch.get("id", ""))
            self._apply_workspace_filter()
        return imported



    def _engine_home_url(self, engine_name: str) -> str:
        return prefs.search_engine_home_url(engine_name)

    def _engine_search_url(self, engine_name: str, query: str) -> str:
        return prefs.search_engine_query_url(engine_name, query)

    def _looks_like_search_query(self, text: str) -> bool:
        value = (text or "").strip()
        if not value:
            return False
        lowered = value.lower()
        if lowered.startswith(("http://", "https://", "file://", "about:")):
            return False
        return "." not in value or " " in value

    def _on_search_engine_changed(self, index):
        if index < 0:
            return
        # Persist the user's choice so every window and future session uses it.
        try:
            prefs.set_search_engine(self.base_dir, self.search_engine.currentText())
        except Exception:
            pass
        # v6.5 UX: merely switching engines must not navigate the tab the user
        # is reading (v6.4 re-ran the last query and could yank them away).
        # The next new tab / search picks the new engine automatically.
        browser = self.current_browser()
        if browser is not None:
            current_url = browser.url().toString()
            if current_url in ("", "about:blank"):
                browser.setUrl(QUrl(self._engine_home_url(self.search_engine.currentText())))

    def save_bookmark(self, folder_id=None):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        title = browser.title()
        bookmarks = prefs.load_bookmarks(self.base_dir)
        # Guard against malformed entries (v6.4 raised KeyError on one).
        if any((b or {}).get("url") == url for b in bookmarks):
            self._flash_status("This page is already in your Bookmarks")
            return
        if folder_id is None:
            current_item = self.bookmarks_tree.currentItem()
            if current_item:
                data = current_item.data(0, Qt.UserRole)
                kind, data = data if isinstance(data, tuple) and len(data) == 2 else ("", data)
                if kind == "folder":
                    folder_id = data
        bookmarks.append({"title": title, "url": url, "folder_id": folder_id or ""})
        prefs.save_bookmarks(self.base_dir, bookmarks)
        history_service.log_event(self.base_dir, "bookmark", title or url, url, {"url": url})
        self._load_bookmarks_panel()
        self._flash_status("Page saved to Bookmarks")

    def open_current_in_external_browser(self):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        self.open_url_in_external_browser(url)

    def open_url_in_external_browser(self, url):
        if not url.startswith("http"):
            return
        browser_candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for browser_path in browser_candidates:
            if os.path.exists(browser_path):
                try:
                    subprocess.Popen([browser_path, url])
                    return
                except Exception:
                    pass
        try:
            os.startfile(url)
        except Exception:
            QMessageBox.warning(self, "Open externally", "Could not launch Chrome, Edge, or the default browser.")

    def _apply_saved_proxy(self):
        path = prefs.proxy_config_path(self.base_dir)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg.get("enabled", False):
                self._set_proxy_from_config(cfg, prompt_restart=False)
        except Exception:
            pass

    def _set_proxy_from_config(self, cfg, prompt_restart: bool = True):
        """Apply a proxy to BOTH Qt's QNetworkAccessManager and (via env var) the
        next QtWebEngine launch. WebEngine reads --proxy-server only at startup,
        so live page loads keep the previous proxy until the user restarts."""
        host = (cfg.get("host") or "").strip()
        port = int(cfg.get("port") or 0)
        valid = bool(host) and 0 < port < 65536
        proxy_type = QNetworkProxy.HttpProxy if cfg.get("type", "http").lower() == "http" else QNetworkProxy.Socks5Proxy
        if valid:
            proxy = QNetworkProxy(proxy_type, host, port)
            if cfg.get("user"):
                proxy.setUser(cfg["user"])
            if cfg.get("password"):
                proxy.setPassword(cfg["password"])
            QNetworkProxy.setApplicationProxy(proxy)
        else:
            # Never install a half-configured proxy (empty host/port) — that
            # would silently break every QNetworkAccessManager request.
            QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))

        scheme = "socks5" if (cfg.get("type") or "http").lower().startswith("socks") else "http"
        if valid:
            from urllib.parse import quote
            user = (cfg.get("user") or "").strip()
            password = (cfg.get("password") or "").strip()
            auth = ""
            if user:
                auth = quote(user, safe="") + (":" + quote(password, safe="") if password else "") + "@"
            flag = "--proxy-server=%s://%s%s:%d" % (scheme, auth, host, port)
            existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
            existing = " ".join(tok for tok in existing.split() if not tok.startswith("--proxy-server="))
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (existing + " " + flag).strip()
            if prompt_restart:
                QMessageBox.information(
                    self,
                    "VPN / Proxy",
                    "Proxy saved for Mei.\n\n"
                    "Important: QtWebEngine only reads proxy settings at startup.\n"
                    "Close and reopen Mei for all web tabs to go through the proxy.",
                )

    def _load_block_third_party_cookies_pref(self):
        self.act_block_3p_cookies.setChecked(prefs.get_block_third_party_cookies(self.base_dir))
        self._apply_cookie_policy(show_message=False)

    def _load_dark_web_pref(self):
        # effective, not the stored flag: until the user flips this item the value
        # follows the shell's light/dark mode (see prefs.effective_force_dark_web),
        # so the checkbox has to show what pages are actually getting.
        self.act_dark_mode.setChecked(prefs.effective_force_dark_web(self.base_dir))

    def _apply_cookie_policy(self, show_message=True):
        checked = self.act_block_3p_cookies.isChecked()
        store = self.profile.cookieStore()
        if checked:
            def cookie_filter(req):
                first_party_url = ""
                try:
                    first_party = req.firstPartyUrl()
                    if first_party:
                        first_party_url = first_party.toString().lower()
                except Exception:
                    first_party_url = ""
                if self.is_compatibility_host(first_party_url):
                    return True
                third_party = getattr(req, "thirdParty", False)
                if callable(third_party):
                    try:
                        third_party = third_party()
                    except Exception:
                        third_party = False
                return not bool(third_party)

            self._cookie_filter = cookie_filter
            if hasattr(store, "setCookieFilter"):
                store.setCookieFilter(self._cookie_filter)
                if show_message:
                    self._flash_status("Third-party cookies blocked for this profile")
            elif show_message:
                self._flash_status("Preference saved — this Qt build cannot filter cookies")
        else:
            # Qt has no unsetCookieFilter: install a pass-through instead
            # (v6.4 approach, kept).
            if hasattr(store, "setCookieFilter"):
                self._cookie_filter = lambda _req: True
                store.setCookieFilter(self._cookie_filter)
            else:
                self._cookie_filter = None
            if show_message:
                self._flash_status("Third-party cookie blocking turned off")

    def toggle_block_third_party_cookies(self):
        checked = self.act_block_3p_cookies.isChecked()
        prefs.set_block_third_party_cookies(self.base_dir, checked)
        self._apply_cookie_policy(show_message=True)

    def update_zoom_label(self):
        browser = self.current_browser()
        if browser:
            # Rendering rule lives with the chip itself (TopBarMixin).
            self._set_zoom_label(round(browser.zoomFactor() * 100))

    def zoom_in(self):
        browser = self.current_browser()
        if browser:
            factor = round(min(browser.zoomFactor() + 0.1, 3.0), 2)
            browser.setZoomFactor(factor)
            self._remember_current_zoom(factor)
            self.update_zoom_label()

    def zoom_out(self):
        browser = self.current_browser()
        if browser:
            factor = round(max(browser.zoomFactor() - 0.1, 0.3), 2)
            browser.setZoomFactor(factor)
            self._remember_current_zoom(factor)
            self.update_zoom_label()

    def zoom_reset(self):
        browser = self.current_browser()
        if browser:
            host = (browser.url().host() or "").lower()
            browser.setZoomFactor(1.0)
            prefs.set_site_zoom(self.base_dir, host, None)
            self.update_zoom_label()

    def _remember_current_zoom(self, factor):
        browser = self.current_browser()
        if browser:
            host = (browser.url().host() or "").lower()
            if host:
                prefs.set_site_zoom(self.base_dir, host, factor)

    def _translate_page(self, service="google"):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        if not url or not url.startswith("http"):
            QMessageBox.information(self, "Translate", "Could not translate this page.")
            return
        if service == "google":
            self.tab_manager.add_tab(QUrl(f"https://translate.google.com/translate?sl=auto&tl=vi&u={quote_plus(url)}"), "Google Translate", is_active=True)
        elif service == "bing":
            self.tab_manager.add_tab(QUrl(f"https://www.bing.com/translator?ref=This&text=&from=auto&to=vi&url={quote_plus(url)}"), "Bing Translate", is_active=True)

    def toggle_reader_mode(self):
        browser = self.current_browser()
        if not browser:
            return
        # Reader palette follows the shell theme (v6.4 forced a dark scheme
        # even in light themes, then dark-forced sites double-inverted).
        p = theme.palette()
        bg, fg = p["MAIN_BG"], p["TEXT"]
        js = """
        var elements = document.querySelectorAll('header, footer, nav, aside, .sidebar, .ads, script, style, iframe');
        for (var i=0; i<elements.length; i++) elements[i].style.display = 'none';
        document.body.style.maxWidth = '800px';
        document.body.style.margin = '0 auto';
        document.body.style.padding = '20px';
        document.body.style.backgroundColor = '%s';
        document.body.style.color = '%s';
        document.body.style.fontSize = '18px';
        document.body.style.lineHeight = '1.6';
        """ % (bg, fg)
        browser.page().runJavaScript(js)
        self._flash_status("Reader mode — colors follow your theme")

    def toggle_text_highlight(self, checked=None):
        """Enable/disable the highlight-text-to-copy helper on every open page.

        The profile-level script covers all future loads (tabs + embedded
        previews); the per-page JS pass updates pages that are already open.
        """
        if checked is None:
            checked = bool(self.act_text_highlight.isChecked())
        checked = bool(checked)
        prefs.set_text_highlight_enabled(self.base_dir, checked)
        try:
            ensure_text_highlight_script(self.profile, checked, self.base_dir)
        except Exception:
            pass
        js = build_text_highlight_js(checked)
        for browser in self.browsers:
            if browser is not None and browser.page():
                try:
                    browser.page().runJavaScript(js)
                except Exception:
                    pass

    def show_dev_tools(self):
        if not self.current_browser():
            return
        # Reuse the existing devtools window: v6.4 stacked a fresh orphan
        # window (holding a whole renderer view) on every F12 press.
        existing = getattr(self, "_dev_windows", None)
        if existing:
            dev_window = existing[-1]
            if dev_window.isVisible():
                dev_window.raise_()
                dev_window.activateWindow()
                return
            dev_window.close()
            self._dev_windows.remove(dev_window)
        dev_view = QWebEngineView()
        self.current_browser().page().setDevToolsPage(dev_view.page())
        dev_window = QMainWindow(self)
        dev_window.setWindowTitle("Developer Tools - F12")
        dev_window.resize(800, 600)
        dev_window.setCentralWidget(dev_view)
        if not hasattr(self, "_dev_windows"):
            self._dev_windows = []
        self._dev_windows.append(dev_window)
        dev_window.destroyed.connect(lambda *_: self._dev_windows.remove(dev_window) if dev_window in self._dev_windows else None)
        dev_window.show()

    def toggle_dark_web(self):
        """User flipped "Force Dark Mode on Web": store the explicit choice."""
        self._apply_dark_web(self.act_dark_mode.isChecked(), persist=True)

    def _apply_dark_web(self, enabled: bool, persist: bool = True):
        """Install/remove the forced-dark script and apply it to the open tabs.

        ``persist=False`` is the automatic path (the theme flipped): it must not
        write the pref, or the very first day/night flip would freeze the
        follow-the-theme behaviour into an explicit value.
        """
        if persist:
            prefs.set_force_dark_web(self.base_dir, enabled)
        if hasattr(self, "act_dark_mode") and self.act_dark_mode.isChecked() != bool(enabled):
            self.act_dark_mode.setChecked(bool(enabled))
        try:
            from litebrowser.browser.browser_page import ensure_forced_dark_script
            ensure_forced_dark_script(self.profile, enabled, self.base_dir)
        except Exception:
            pass
        js = self._dark_mode_js(enabled)
        for browser in self.browsers:
            if browser is not None and browser.page():
                browser.page().runJavaScript(js)

    def _sync_dark_web_with_theme(self):
        """Keep web pages in step with the shell's light/dark mode.

        Only acts while the user has not made an explicit choice, and never
        persists — see _apply_dark_web.
        """
        act = getattr(self, "act_dark_mode", None)
        if act is None:
            return
        enabled = prefs.effective_force_dark_web(self.base_dir)
        if act.isChecked() == enabled:
            return
        self._apply_dark_web(enabled, persist=False)

    def show_history_dialog(self):
        dialogs.show_history_dialog(self)

    def remember_closed_tab(self, metadata):
        if bool((metadata or {}).get("incognito")):
            return
        state = prefs.session_state_load(self.base_dir)
        recently_closed = state.get("recently_closed", [])
        entry = {
            "kind": metadata.get("kind", "tab"),
            "url": metadata.get("url", ""),
            "title": metadata.get("title", ""),
            "icon": metadata.get("icon", ""),
            "hibernated": bool(metadata.get("hibernated", True)),
            "pinned": bool(metadata.get("pinned")),
            "workspace_id": metadata.get("workspace_id") or metadata.get("workspace") or self.current_workspace_id,
        }
        if entry["url"]:
            recently_closed = [item for item in recently_closed if item.get("url") != entry["url"]]
            recently_closed.insert(0, entry)
            state["recently_closed"] = recently_closed[:50]
            prefs.session_state_save(self.base_dir, state)

    def reopen_closed_tab(self):
        """Reopen the most recently closed tab (or window) via Ctrl+Shift+T.

        Consumes the last ``kind == "tab"`` entry in the session's recently-closed
        list so an empty history produces a clear message instead of silently doing
        nothing. Windows (multi-tab) are surfaced through the History panel.
        """
        state = prefs.session_state_load(self.base_dir)
        recently_closed = state.get("recently_closed", [])
        tab_index = next((i for i, e in enumerate(recently_closed) if e.get("kind") == "tab" and e.get("url")), None)
        if tab_index is None:
            QMessageBox.information(self, "Reopen Closed Tab", "No recently closed tab to reopen.")
            return
        entry = recently_closed.pop(tab_index)
        state["recently_closed"] = recently_closed
        prefs.session_state_save(self.base_dir, state)
        url = entry.get("url", "")
        if not url:
            return
        self.tab_manager.add_tab(
            QUrl(url),
            entry.get("title") or "Reopened",
            is_active=True,
            session_data=entry,
        )
        # add_tab already inserts + selects the row; the panel switch re-applies
        # the workspace filter so the restored tab is visible. (There is no
        # ``SearchWindow.refresh`` — the old call here raised AttributeError.)
        self.switch_to_browser_panel()

    def switch_to_browser_panel(self):
        try:
            self._switch_sidebar_panel(0)
            self._apply_workspace_filter()
        except Exception:
            pass

    def reopen_closed_window(self):
        """Reopen the most recently closed multi-tab window (from session state)."""
        state = prefs.session_state_load(self.base_dir)
        recently_closed = state.get("recently_closed", [])
        window_index = next(
            (i for i, entry in enumerate(recently_closed) if entry.get("kind") == "window" and entry.get("tabs")),
            None,
        )
        if window_index is None:
            QMessageBox.information(self, "Reopen Closed Window", "No recently closed window to reopen.")
            return
        entry = recently_closed.pop(window_index)
        state["recently_closed"] = recently_closed
        prefs.session_state_save(self.base_dir, state)
        tabs = [tab for tab in entry.get("tabs", []) if tab.get("url")]
        if not tabs:
            return
        self.tab_manager.begin_batch()
        try:
            for tab in tabs:
                self.tab_manager.add_tab(
                    QUrl(tab.get("url")),
                    tab.get("title") or "Reopened",
                    is_active=bool(tab.get("active")),
                    session_data=tab,
                )
        finally:
            self.tab_manager.end_batch()
        self.switch_to_browser_panel()

    def _cycle_tab_next(self):
        self._cycle_tab(1)

    def _cycle_tab_prev(self):
        self._cycle_tab(-1)

    def _cycle_tab(self, direction):
        """Move keyboard focus to the next/previous visible tab in this workspace."""
        count = self.tab_list.count()
        if count == 0:
            return
        rows = [i for i in range(count) if not self.tab_list.item(i).isHidden()]
        if not rows:
            return
        current = self.tab_list.currentRow()
        try:
            position = rows.index(current)
        except ValueError:
            position = -1 if direction > 0 else 0
        target = rows[(position + direction) % len(rows)]
        self.tab_list.setCurrentRow(target)

    def remember_closed_window(self, tabs):
        tabs = [dict(tab) for tab in (tabs or []) if tab.get("url")]
        if len(tabs) < 2:
            return
        state = prefs.session_state_load(self.base_dir)
        recently_closed = state.get("recently_closed", [])
        entry = {
            "kind": "window",
            "title": f"Window with {len(tabs)} tabs",
            "tabs": tabs,
        }
        recently_closed.insert(0, entry)
        state["recently_closed"] = recently_closed[:30]
        prefs.session_state_save(self.base_dir, state)

    def refresh_insight_summary(self):
        host = self._host_shell()
        if host is None or not hasattr(host, "set_sleeping_tabs"):
            return
        sleeping = []
        for i, browser in enumerate(self.browsers):
            item = self.tab_list.item(i)
            meta = dict(item.data(TAB_META_ROLE) or {}) if item else {}
            hibernated = bool(meta.get("hibernated"))
            if browser is not None:
                try:
                    hibernated = bool(browser.property("hibernated"))
                except Exception:
                    pass
            if hibernated:
                sleeping.append(meta.get("title") or meta.get("url") or f"Tab {i+1}")
        host.set_sleeping_tabs(sleeping)

    def show_bookmarks_dialog(self):
        dialogs.show_bookmarks_dialog(self)

    def show_extensions_dialog(self):
        dialogs.show_extensions_dialog(self)

    def show_vault(self):
        vault_ui.show_vault_dialog(self, prefs.vault_path(self.base_dir), self._dialog_stylesheet)

    def show_downloads_dialog(self):
        dialogs.show_downloads_dialog(self)

    def print_page(self):
        browser = self.current_browser()
        if not browser:
            return
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec_() == QDialog.Accepted:
            def on_print_finished(ok):
                # Qt5's QWebEnginePage.printFinished(bool) — the old handler
                # declared (path, ok) and would TypeError if it ever fired.
                self._flash_status("Sent to the printer" if ok else "Print failed")

            page = browser.page()
            if hasattr(page, "print"):
                try:
                    page.print(printer, on_print_finished)
                    return
                except TypeError:
                    pass
            # Qt 6.8+ removed QWebEnginePage.print(): fall back to PDF-then-print
            # so the feature never breaks under the PyQt6 shim.
            if hasattr(page, "printToPdf"):
                tmp_path = os.path.join(prefs.favicon_cache_dir(self.base_dir), "_print_preview.pdf")
                page.pdfPrintingFinished.connect(lambda _path, ok: self._flash_status("PDF saved — open it to print") if ok else None)
                page.printToPdf(tmp_path)
                self._flash_status("Printing to PDF fallback...")
                return
            self._flash_status("Printing is not available for this page")

    def save_page_pdf(self):
        browser = self.current_browser()
        if not browser:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if not file_path:
            return
        if not file_path.endswith(".pdf"):
            file_path += ".pdf"
        page = browser.page()
        page.pdfPrintingFinished.connect(
            lambda path, ok: self._flash_status("PDF saved: " + os.path.basename(path or file_path)) if ok else self._flash_status("PDF export failed")
        )
        page.printToPdf(file_path)
        self._flash_status("Generating PDF...")

    def save_current_page_to_library(self):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        if not url or url in ("about:blank", "about:newtab"):
            return
        title = browser.title() or url
        life_service.add_saved_page(self.base_dir, title, url)
        shell = self._host_shell()
        if shell and hasattr(shell, "refresh_shell"):
            shell.refresh_shell()
        QMessageBox.information(self, "Library", "Current page saved to Library.")

    def ask_ai_about_current_page(self):
        browser = self.current_browser()
        if not browser:
            return
        self.toggle_ai_sidebar()
        if not self.inline_ai_input.text().strip():
            self.inline_ai_input.setText("What can you see on this page?")
        self._run_inline_ai()

    def _run_inline_ai(self):
        browser = self.current_browser()
        if not browser:
            return
        shell = self._host_shell()
        if not shell or not hasattr(shell, "ask_ai_from_shell"):
            return
        question = (self.inline_ai_input.text() or "").strip() or "What can you see on this page?"
        self._inline_last_question = question
        self.inline_ai_answer.setPlainText("Reading the visible page and asking AI...")
        # Wire the answer back through the AIWorkspace signal so the inline panel
        # does not depend on a stale, synchronously-read ``_last_answer``.
        # Connect at most once: PyQt adds a new connection on every connect(),
        # so repeated asks would let an older answer overwrite the newest one.
        if not getattr(self, "_inline_ai_wired", False):
            shell.ai_page.query_finished.connect(self._on_inline_ai_answer)
            self._inline_ai_wired = True
        browser.page().runJavaScript(
            "(function(){var text=(document.body && document.body.innerText)||''; return text.slice(0,5000);})();",
            lambda text: self._handle_inline_ai_context(shell, browser, question, text or ""),
        )

    def _on_inline_ai_answer(self, future, _context_label, _provider_label=""):
        if self._closing:
            return
        try:
            result = future.result()
        except Exception as exc:
            self.inline_ai_answer.setPlainText("AI request failed: %s" % (exc,))
            return
        answer = (result or {}).get("answer") or "No answer returned."
        question = getattr(self, "_inline_last_question", "")
        self.inline_ai_answer.setPlainText(
            (f"Q: {question}\n\n" if question else "") + answer
        )

    def _handle_inline_ai_context(self, shell, browser, question: str, page_text: str):
        if self._closing:
            return
        title = browser.title() or browser.url().toString() or "Current page"
        url = browser.url().toString()
        context = f"Title: {title}\nURL: {url}\n\nVisible page text:\n{page_text[:5000]}"
        shell.ed_ai_quick.setText(question)
        shell.ai_page.ask_with_context(question, "Current browser page", context)

    def capture_page_as_note(self):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        title = browser.title() or url or "Web note"
        note = personal_service.create_note(self.base_dir, title[:60], "# " + title + "\n\nURL: " + url + "\n\n")
        QMessageBox.information(self, "Personal", "Created new note: " + note["title"])

    def capture_screenshot(self):
        browser = self.current_browser()
        if not browser:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Web Image", "", "PNG Files (*.png);;JPEG Files (*.jpg)")
        if file_path:
            browser.grab().save(file_path)
            QMessageBox.information(self, "Screenshot", f"Web page screenshot saved to:\n{file_path}")

    def _host_shell(self):
        current = self.parent()
        while current is not None:
            if hasattr(current, "switch_workspace") and hasattr(current, "ai_page"):
                return current
            current = current.parent()
        win = self.window()
        if hasattr(win, "switch_workspace") and hasattr(win, "ai_page"):
            return win
        return None

    def extract_text(self):
        browser = self.current_browser()
        if not browser:
            return
        def process_text(text):
            dialog = QDialog(self)
            dialog.setWindowTitle("Extract Text")
            dialog.resize(720, 520)
            dialog.setStyleSheet(self._dialog_stylesheet())
            layout = QVBoxLayout(dialog)
            text_edit = QTextEdit()
            text_edit.setPlainText(text)
            layout.addWidget(text_edit)
            btn_copy = QPushButton("Copy All")
            btn_copy.clicked.connect(lambda: [QApplication.clipboard().setText(text_edit.toPlainText()), QMessageBox.information(dialog, "Copy", "Copied to clipboard.")])
            layout.addWidget(btn_copy)
            dialog.exec_()
        browser.page().toPlainText(process_text)

    def _monitor_current_page(self):
        browser = self.current_browser()
        if not browser:
            return
        url = browser.url().toString()
        if not url.startswith("http"):
            self._flash_status("Monitor needs a real http(s) page")
            return
        from litebrowser.services import page_monitor

        try:
            monitor = page_monitor.add_monitor(self.base_dir, url, browser.title() or url)
        except page_monitor.MonitorError as exc:
            self._flash_status(f"Not watching that page — {exc}")
            return
        shell = self._host_shell()
        if not monitor:
            self._flash_status("That page is already in the watch list")
            return
        if shell is not None and hasattr(shell, "system_notify"):
            shell.system_notify("Watching page 👀", "You'll get a toast when it changes (checked ~every 15 min).")

    def _save_selection_to_vault(self):
        """Save the highlighted page text into SafeVault as a dated clipping.

        Clippings live in one rolling 'Clippings' note per day, so studying a
        topic keeps its sources (title + URL) attached to every excerpt."""
        browser = self.current_browser()
        if not browser:
            return

        def _grab_selection(selected):
            text = (selected or "").strip()
            if not text:
                self._flash_status("Select some text on the page first")
                return
            title = browser.title() or browser.url().toString() or "Untitled page"
            url = browser.url().toString()
            day = time.strftime("%Y-%m-%d")
            note_title = f"Clippings — {day}"
            excerpt = f"> {text.replace(chr(10), chr(10) + '> ')}\n\n— [{title}]({url}) · {time.strftime('%H:%M')}\n\n---\n\n"
            from litebrowser.services import personal_service
            existing = [
                n for n in personal_service.list_notes(self.base_dir, note_title)
                if n["title"] == note_title and n.get("category") == "Clippings"
            ]
            if existing:
                note = personal_service.read_note(self.base_dir, existing[0]["id"])
                personal_service.update_note(
                    self.base_dir, existing[0]["id"],
                    (note["content"] if note else "") + "\n\n" + excerpt,
                )
            else:
                personal_service.create_note(self.base_dir, note_title, "# " + note_title + "\n\n" + excerpt, category="Clippings")
            self._flash_status("Clipped to SafeVault ✓")

        browser.page().runJavaScript(
            "(function(){var s=window.getSelection&&window.getSelection();"
            "return s?s.toString():'';})();",
            _grab_selection,
        )

    def _tab_state_payload(self, index, browser, active_browser):
        item = self.tab_list.item(index)
        meta = dict(item.data(TAB_META_ROLE) or {}) if item else {}
        if bool(meta.get("incognito")):
            return None
        if browser is not None:
            try:
                if browser.property("is_incognito") or browser.page().profile().isOffTheRecord():
                    return None
            except Exception:
                # Never persist a page when its private state cannot be verified.
                return None
        url = meta.get("url", "")
        if browser is not None:
            try:
                live_url = browser.url().toString()
                if live_url and live_url != "about:blank":
                    url = live_url
                elif not url:
                    pending = browser.property("pending_url")
                    if pending:
                        url = pending.toString()
            except Exception:
                pass
        if not url or url in ("about:blank", "about:newtab"):
            return None
        workspace_id = item.data(Qt.UserRole + workspace_manager.WORKSPACE_ROLE) if item else self.current_workspace_id
        hibernated = bool(meta.get("hibernated"))
        if browser is not None:
            try:
                hibernated = bool(browser.property("hibernated"))
            except Exception:
                pass
        return {
            "kind": "tab",
            "url": url,
            "title": meta.get("title") or (browser.title() if browser is not None else "") or url,
            "icon": meta.get("icon", ""),
            "hibernated": hibernated,
            "active": (browser is active_browser),
            "pinned": bool(item.data(TAB_PINNED_ROLE)) if item else False,
            "workspace_id": workspace_id or self.current_workspace_id,
            "group": (item.data(TAB_GROUP_ROLE) or "") if item else "",
            "group_color": (item.data(TAB_GROUP_COLOR_ROLE) or "") if item else "",
        }

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        try:
            tabs = []
            current = self.current_browser()
            for i, browser in enumerate(self.browsers):
                payload = self._tab_state_payload(i, browser, current)
                if payload:
                    tabs.append(payload)
            prefs.session_state_save(self.base_dir, {"tabs": tabs}, window_slot=self._session_slot())
            # "Reopen Closed Window" must not offer the session that is live at
            # app exit (v6.4 recorded it on every quit). Only remember the
            # window when another shell window is still open, i.e. the user
            # closed one of the two browser windows.
            other_visible = 0
            for w in QApplication.topLevelWidgets():
                if w is not self and w.isVisible() and w.inherits("QMainWindow") and w.windowTitle():
                    other_visible += 1
            if other_visible > 0:
                self.remember_closed_window(tabs)
            # Auto snapshot tab set (listtab)
            self._auto_save_tab_set()
        except Exception:
            pass
        finally:
            self.shutdown()
            event.accept()

    def get_current_tab_state(self):
        tabs = []
        current = self.current_browser()
        for i, b in enumerate(self.browsers):
            # Incognito pages must never leak into persistent saved collections.
            try:
                if b is not None and b.page().profile().isOffTheRecord():
                    continue
            except Exception:
                # If privacy state cannot be proven, exclude the tab.
                continue
            payload = self._tab_state_payload(i, b, current)
            if payload:
                tabs.append(payload)
        return tabs

    def _auto_save_tab_set(self):
        tabs = self.get_current_tab_state()
        if not tabs:
            return
        import time
        title = time.strftime("Search auto %Y-%m-%d %H:%M")
        try:
            tab_sets.add_tab_set(self.base_dir, "search", title, tabs)
        except Exception:
            pass

    def save_current_tab_set(self):
        from PyQt5.QtWidgets import QInputDialog
        tabs = self.get_current_tab_state()
        if not tabs:
            QMessageBox.information(self, "Tab set", "No tabs to save.")
            return
        import time
        default = time.strftime("Search manual %Y-%m-%d %H:%M")
        name, ok = QInputDialog.getText(self, "Save Current Tab Set", "Tab set name:", text=default)
        if not ok:
            return
        try:
            tab_sets.add_tab_set(self.base_dir, "search", name or default, tabs)
            QMessageBox.information(self, "Tab set", "Current tab set saved.")
        except Exception as e:
            QMessageBox.warning(self, "Tab set", "Could not save tab set:\n%s" % (str(e),))

    def save_tab_set_named(self, name=None):
        """Save the current workspace's tabs under a name without prompting.
        Used by the ``/save-tabs`` omnibar macro."""
        tabs = self.get_current_tab_state()
        if not tabs:
            QMessageBox.information(self, "Tab set", "No tabs to save.")
            return
        import time
        default = time.strftime("Search manual %Y-%m-%d %H:%M")
        title = (name or default).strip() or default
        try:
            tab_sets.add_tab_set(self.base_dir, "search", title, tabs)
            QMessageBox.information(self, "Tab set", f"Saved tab set \"{title}\" ({len(tabs)} tabs).")
        except Exception as e:
            QMessageBox.warning(self, "Tab set", "Could not save tab set:\n%s" % (str(e),))

    def restore_tab_set(self, set_id, mode="merge"):
        """Open a saved tab collection. Tabs reopen in a hibernated state so
        restoring a large research session stays cheap until you select a tab.
        Replace only closes this browser workspace after an explicit UI choice."""
        data = tab_sets.get_tab_set(self.base_dir, set_id)
        if not data:
            QMessageBox.warning(self, "Tab set", "Tab set not found.")
            return
        if data.get("kind") == "workspace":
            tab_sets.set_active_research_workspace(self.base_dir, data["id"])
        tabs = [tab for tab in data.get("tabs", []) if tab.get("url")]
        if not tabs:
            QMessageBox.information(self, "Tab set", "This tab set is empty.")
            return
        if mode == "replace":
            ws_role = Qt.UserRole + workspace_manager.WORKSPACE_ROLE
            rows = [
                i for i in range(self.tab_list.count())
                if self.tab_list.item(i) and self.tab_list.item(i).data(ws_role) == self.current_workspace_id
            ]
            for index in reversed(rows):
                item = self.tab_list.item(index)
                if item and item.data(TAB_PINNED_ROLE):
                    self.tab_manager.set_tab_pinned(index, False)
                self.tab_manager.close_tab(index)
        self.tab_manager.begin_batch()
        try:
            for tab in tabs:
                session_data = dict(tab)
                session_data["workspace_id"] = self.current_workspace_id
                self.tab_manager.add_tab(
                    QUrl(tab.get("url")),
                    tab.get("title") or "Tab",
                    is_active=bool(tab.get("active")),
                    session_data=session_data,
                )
        finally:
            self.tab_manager.end_batch()
        self.switch_to_browser_panel()
        QMessageBox.information(
            self,
            "Tab set",
            "Opened %d tab(s) from \"%s\"." % (len(tabs), data.get("title", "")),
        )

    def group_tabs_by_domain(self):
        """Label every tab in this workspace with a domain-based group.

        The label is stored in tab metadata so it survives hibernation and can
        be filtered with ``group:domain`` in the tab search. Returns a
        ``{group: count}`` mapping.
        """
        from urllib.parse import urlparse
        ws_role = Qt.UserRole + workspace_manager.WORKSPACE_ROLE
        counts = {}
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            if not item or item.data(ws_role) != self.current_workspace_id:
                continue
            metadata = dict(item.data(TAB_META_ROLE) or {})
            url = metadata.get("url") or ""
            host = ""
            if url.startswith("http"):
                host = (urlparse(url).netloc or "").lower()
                host = host.removeprefix("www.")
            group = host or "ungrouped"
            metadata["group"] = group
            item.setData(TAB_META_ROLE, metadata)
            counts[group] = counts.get(group, 0) + 1
        return counts

    def group_tabs_action(self):
        counts = self.group_tabs_by_domain()
        if not counts:
            QMessageBox.information(self, "Tab groups", "No tabs to group.")
            return
        lines = "\n".join(
            "%s: %d tab(s)" % (domain, count)
            for domain, count in sorted(counts.items(), key=lambda kv: -kv[1])
        )
        QMessageBox.information(
            self,
            "Tab groups",
            "Tabs grouped by domain:\n\n%s\n\nFilter with: group:domain (e.g. group:youtube.com)" % lines,
        )


# Backward-compatible alias (older imports expect Browser).
Browser = SearchWindow
