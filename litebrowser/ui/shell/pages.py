"""Shell dashboard pages (Home, Library, Settings, History)."""
import os
import socket
import time

from PyQt5.QtCore import QSize, Qt, QTimer, QUrl
from PyQt5.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from litebrowser.core import app_paths, app_version, prefs, storage_utils
from litebrowser.core import time_utils as _time_utils
from litebrowser.services import (
    android_bridge_service,
    brief_service,
    desk_service,
    diagnostics,
    plugins,
    sync_folder,
    focus_service,
    flashcard_service,
    google_auth,
    history_service,
    life_service,
    page_monitor,
    personal_service,
    retriever,
    security,
    study_flow,
    tab_sets,
)
from litebrowser.ui import components, dialogs, theme
from litebrowser.ui.dialogs.common import _stylesheet, ghost_button, menu_action, more_menu, primary_button, quiet_button


def _ui_versions() -> dict:
    """The component versions only the running GUI can answer.

    Taken from the façade (``litebrowser.qt``) rather than a binding: which one is
    active is decided by the compatibility shim, and a diagnostics bundle that
    reports the wrong Qt is worse than one that reports none.
    """
    info: dict = {}
    try:
        from litebrowser.qt import QtCore

        info["binding"] = str(getattr(QtCore, "__name__", "")).split(".")[0]
        info["qt"] = getattr(QtCore, "QT_VERSION_STR", "")
        info["pyqt"] = getattr(QtCore, "PYQT_VERSION_STR", "")
    except Exception:  # noqa: BLE001 - diagnostics must never break the page
        pass
    try:
        from litebrowser.qt import QtWebEngineCore

        chromium = getattr(QtWebEngineCore, "qWebEngineChromiumVersion", None)
        if callable(chromium):
            info["chromium"] = chromium()
    except Exception:  # noqa: BLE001
        pass
    return info


def _dedupe_library_items(items: list) -> list:
    """First occurrence wins; same kind+id from search_everything vs retriever counts once.

    Imperfect: same entity may appear under different ids (e.g. URL vs saved_page id).
    """
    seen: set[tuple[str, str]] = set()
    out = []
    for item in items:
        key = (str(item.get("kind") or "").strip().lower(), str(item.get("id") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _format_ts(ts_value: int) -> str:
    """Backward-compatible alias; the canonical helper lives in core.time_utils."""
    return _time_utils.format_ts(ts_value)


def _panel(title: str, subtitle: str = "", action: QPushButton | None = None) -> tuple[QFrame, QVBoxLayout]:
    """Create a roomy, card-like section used by the calm secondary screens."""
    card = QFrame()
    card.setObjectName("SectionCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 14)
    layout.setSpacing(8)
    layout.addWidget(components.section_header(title, subtitle, action))
    return card, layout


def _activity_item(kind: str, title: str, detail: str = "", meta: str = "") -> QListWidgetItem:
    """Build a scan-friendly two-line list row while retaining normal list semantics."""
    kind_label = (kind or "item").replace("-", " ").upper()
    raw_heading = (title or "Untitled").strip()
    raw_secondary = "  ·  ".join(part for part in (meta.strip(), detail.strip()) if part)
    heading = raw_heading if len(raw_heading) <= 108 else raw_heading[:105].rstrip() + "..."
    secondary = raw_secondary if len(raw_secondary) <= 168 else raw_secondary[:165].rstrip() + "..."
    text = f"{kind_label}  {heading}"
    if secondary:
        text += f"\n{secondary}"
    row = QListWidgetItem(text)
    row.setToolTip("\n".join(part for part in (raw_heading, raw_secondary) if part))
    row.setSizeHint(QSize(0, 54 if secondary else 34))
    return row





def _chart_tokens(page) -> dict:
    """Palette for the profile hosting a hand-painted chart.

    The dashboard belongs to the *active* profile, which is not always the
    default one, and it has to paint with the accent the shell QSS around it is
    already using — see ``theme.palette`` for why the accent default matters.
    """
    from litebrowser.ui import theme as _theme

    base_dir = getattr(getattr(page, "shell", None), "profile_dir", None)
    return _theme.palette(base_dir=base_dir) if base_dir else _theme.palette()


class _DomainWeekChart(QWidget):
    """Top domains this week as horizontal theme bars — the wellbeing view.

    Distraction domains tint with DANGER so the balance is honest at a glance."""

    _SCARY = ("facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com", "reddit.com", "netflix.com", "youtube.com")

    def __init__(self, page):
        super().__init__()
        self._page = page
        self._rows = []  # (domain, count, scary?)
        self.setMinimumHeight(200)

    def refresh(self):
        from urllib.parse import urlparse as _urlparse

        from litebrowser.core import prefs as _prefs

        entries = _prefs.load_history_entries(self._page.shell.profile_dir)
        midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        counts = {}
        for ts, url in entries:
            ts = int(ts or 0)
            if ts < midnight - 6 * 86400:
                continue
            host = _urlparse(url).netloc.removeprefix("www.").lower() if "://" in url else ""
            if host:
                counts[host] = counts.get(host, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
        self._rows = [
            (d, c, any(d == s or d.endswith("." + s) for s in self._SCARY))
            for d, c in ranked
        ]
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        p = _chart_tokens(self._page)
        # No surface here on purpose: the surrounding #SectionCard paints the
        # card colour and this widget stays transparent on top of it. Filling the
        # rect with MAIN_BG_ALT painted the chart as a second, slightly different
        # surface inside the card — a pink block on light themes and an
        # off-black block on night ones (reported twice).
        if not self._rows:
            painter.setPen(QColor(p["TEXT_MUTED"]))
            painter.drawText(self.rect(), Qt.AlignCenter, "No browsing this week yet.")
            painter.end()
            return
        top = 8
        row_h = max(18, (h - 16) // max(1, len(self._rows)))
        max_count = max(c for _d, c, _s in self._rows) or 1
        label_w = int(min(150, w * 0.4))
        bar_x = label_w + 10
        bar_w_max = max(30, w - bar_x - 46)
        for i, (domain, count, scary) in enumerate(self._rows):
            y = top + i * row_h
            painter.setPen(QColor(p["TEXT"]))
            painter.drawText(6, y, label_w, row_h, Qt.AlignVCenter | Qt.AlignLeft, domain[:22])
            bar_w = int(bar_w_max * count / max_count)
            color = QColor(p["DANGER"]) if scary else QColor(p["ACCENT"])
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(bar_x, y + (row_h - 12) // 2, max(4, bar_w), 12, 4, 4)
            painter.setPen(QColor(p["TEXT_MUTED"]))
            painter.drawText(bar_x + max(4, bar_w) + 6, y, 40, row_h, Qt.AlignVCenter, str(count))
        painter.end()


class _WeekActivityChart(QWidget):
    """A quiet 7-day bar chart of browsing counts, painted with the theme.

    Pure QWidget painting: no chart dependency, follows the accent, and the
    today bar highlights so 'how much did I browse today' answers itself."""

    def __init__(self, page):
        super().__init__()
        self._page = page
        self._counts = [0] * 7
        self._day_labels = [""] * 7
        self.setMinimumHeight(200)

    def refresh(self):
        """Bucket the last seven *calendar days*, today included.

        The bucket used to be ``(midnight_today - ts) // 86400``, and a visit
        made today is *after* midnight, so that subtraction is negative and
        floor-divides to -1: every one of today's visits fell out of the window.
        The chart was a day late across the board — the reported week showed
        Friday's 40 on Thursday's bar, put Friday's 9 on today's bar, and never
        showed the 30 visits that had actually happened (the morning brief said
        "9 pages yesterday", which is what gave it away).
        """
        from datetime import date, timedelta

        from litebrowser.core import prefs as _prefs

        base_dir = self._page.shell.profile_dir
        counts = [0] * 7
        today = date.today()
        for ts, _url in _prefs.load_history_entries(base_dir):
            try:
                age_days = (today - date.fromtimestamp(int(ts or 0))).days
            except (OSError, OverflowError, ValueError):
                continue
            if 0 <= age_days < 7:
                counts[6 - age_days] += 1
        self._counts = counts
        self._day_labels = [(today - timedelta(days=6 - i)).strftime("%a") for i in range(7)]
        self.update()

    def paintEvent(self, _event):
        from litebrowser.ui import theme as _theme

        painter = QPainter(self)
        w, h = self.width(), self.height()
        p = _chart_tokens(self._page)
        # Transparent by design: the chart must read as part of its
        # #SectionCard, never as a second coloured panel inside it (see
        # _DomainWeekChart.paintEvent for the full story).
        # Vertical zones that never overlap or clip, bottom to top:
        #   [day labels] 4px .. bars .. [value labels above the bars]
        # The day labels keep a generous clear margin under them so the text
        # never touches (or looks sliced by) the card's bottom border.
        value_zone = 16  # counts drawn above each bar
        label_zone = 22  # day-of-week labels (with room under the descenders)
        top = 6 + value_zone  # tallest bar tops stop here (labels sit above)
        bottom = max(top + 4, h - label_zone - 4)  # bar baseline
        max_count = max(self._counts or [0]) or 1
        side = 12
        bar_w = max(10, min(52, (w - side * 2 - 6 * 8) // 7))
        step = (w - side * 2) / 7.0
        for i, count in enumerate(self._counts):
            x = side + int(i * step + (step - bar_w) / 2.0)
            is_today = i == 6
            if count <= 0:
                # No visits: draw a faint baseline dot instead of a stub bar,
                # so empty days do not masquerade as activity.
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(p["BORDER_SOFT"]))
                painter.drawRoundedRect(x + (bar_w - 5) // 2, bottom - 5, 5, 5, 2, 2)
                continue
            bar_h = int((count / max_count) * max(8, bottom - top))
            y = bottom - bar_h
            color = _theme.accent_bar_color(p, is_today)
            painter.setPen(QPen(QColor(p["INPUT_BORDER"]), 1))
            painter.setBrush(color)
            painter.drawRoundedRect(x, y, bar_w, max(4, bar_h), 4, 4)
            painter.setPen(QColor(p["TEXT"]))
            painter.drawText(x, max(0, y - 14), bar_w, 13, Qt.AlignCenter, str(count))
        # Day labels sit comfortably above the card edge (never flush/cut).
        painter.setPen(QColor(p["TEXT_MUTED"]))
        label_y = h - label_zone
        for i in range(7):
            x = side + int(i * step + (step - bar_w) / 2.0)
            label = self._day_labels[i] if i < len(self._day_labels) else ""
            painter.drawText(x, label_y + 2, bar_w, label_zone - 6, Qt.AlignCenter, label[:3])
        painter.end()


class HomeDashboardPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("HomeDashboard")
        # The dashboard is ~1050px tall at its natural size.  Without a scroll
        # area a shorter viewport (half-screen shell, small laptop) squeezed
        # every row below its minimum: launcher tiles collapsed into glued
        # strips with their labels clipped away.  Scrolling keeps every tile
        # at full size and lets the page breathe at any window height.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.home_scroll = QScrollArea()
        self.home_scroll.setObjectName("HomeScroll")
        self.home_scroll.setWidgetResizable(True)
        self.home_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.home_scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("HomeScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 22, 24, 22)
        content_layout.setSpacing(18)
        self.home_scroll.setWidget(content)
        layout.addWidget(self.home_scroll)
        layout = content_layout

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(20, 18, 20, 18)
        hero_layout.setSpacing(12)

        brand_row = QHBoxLayout()
        # Time-of-day greeting: the home hero greets like the new-tab page
        # does (v6.4 used a static tagline on Home only).
        try:
            from litebrowser.core.greetings import cafe_greeting

            _eyebrow, headline = cafe_greeting()
        except Exception:
            headline = "Your quiet corner of the web"
        brand = QLabel(headline)
        brand.setObjectName("HeroTitle")
        brand.setFont(components._font(26, components.WEIGHT_BOLD))
        # Wrap instead of forcing a ~1000px minimum width: the long greeting
        # used to make the whole dashboard min-width wider than most shell
        # viewports, so narrow windows clipped the right edge.
        brand.setWordWrap(True)
        brand_row.addWidget(brand, 1)
        self.lbl_today = QLabel(time.strftime("%A, %d %B · %H:%M"))
        self.lbl_today.setObjectName("HeroBadge")
        brand_row.addWidget(self.lbl_today, 0, Qt.AlignVCenter)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(60000)
        self.lbl_home_version = QLabel(f"v{app_version.APP_VERSION}")
        self.lbl_home_version.setObjectName("HeroBadge")
        brand_row.addWidget(self.lbl_home_version, 0, Qt.AlignVCenter)
        hero_layout.addLayout(brand_row)

        subtitle = QLabel(
            "A small local-first workspace for browsing, thinking, and keeping the things worth returning to."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("HeroSubtitle")
        hero_layout.addWidget(subtitle)

        command_row = QHBoxLayout()
        command_row.setSpacing(8)
        self.ed_home_command = QLineEdit()
        self.ed_home_command.setObjectName("HomeCommand")
        self.ed_home_command.setPlaceholderText("Find something, open a link, or /note your next idea")
        self.ed_home_command.setAccessibleName("Search or command")
        self.ed_home_command.setMinimumWidth(0)
        self.ed_home_command.setMinimumHeight(36)
        command_row.addWidget(self.ed_home_command, 1)
        self.btn_home_command = QPushButton("Go")
        self.btn_home_command.setObjectName("TopAccentButton")
        command_row.addWidget(self.btn_home_command)
        hero_layout.addLayout(command_row)
        self.btn_home_command.clicked.connect(self._run_home_command)
        self.ed_home_command.returnPressed.connect(self._run_home_command)

        launcher = QWidget()
        launcher.setObjectName("HomeLaunchGrid")
        self._launcher = launcher
        launcher_grid = QGridLayout(launcher)
        launcher_grid.setContentsMargins(0, 2, 0, 0)
        launcher_grid.setHorizontalSpacing(9)
        launcher_grid.setVerticalSpacing(9)
        launch_specs = (
            ("↗", "Browser", "Tabs & web", "browser"),
            ("✦", "Ask AI", "RAG assistant", "ai"),
            ("◌", "Personal", "Life hub", "personal"),
            ("✓", "Quick Task", "Add a task", "task"),
            ("☕", "Café Focus", "25-min pour", "focus"),
            ("▦", "Library", "Everything", "library"),
            ("◷", "History", "All activity", "history"),
            ("⚙", "Settings", "Tune it all", "settings"),
            ("?", "Help", "Guide & tools", "guide"),
        )
        self._launch_tiles = []
        for index, (glyph, label, hint, _key) in enumerate(launch_specs):
            tile = components.action_tile(glyph, label, hint)
            self._launch_tiles.append(tile)
            row, column = divmod(index, 3)
            launcher_grid.addWidget(tile, row, column)
            launcher_grid.setColumnStretch(column, 1)
        # The launcher grid and the quick-command chips used to *be* the home
        # page: nine tiles as the first thing you see, which is a menu. The desk
        # answers "what do I do now" instead, so both moved into this panel —
        # still one click away, no longer the default view.
        self._more_panel = QWidget()
        more_layout = QVBoxLayout(self._more_panel)
        more_layout.setContentsMargins(0, 6, 0, 0)
        more_layout.setSpacing(10)
        more_layout.addWidget(launcher)

        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(6)
        self.lbl_quick_commands = QLabel("Quick commands")
        self.lbl_quick_commands.setObjectName("MutedLabel")
        cmd_row.addWidget(self.lbl_quick_commands)
        for cmd, tip in (("/task ", "Create task"), ("/note ", "Create note"), ("/board ", "New board"), ("/focus 25", "Start pour"), ("/hub", "Project Hub"), ("/cql", "Management Hub")):
            chip = components.chip(cmd, checkable=False)
            chip.setToolTip(tip)
            chip.clicked.connect(lambda checked=False, c=cmd, s=shell: self._send_quick_command(c, s))
            cmd_row.addWidget(chip)
        cmd_row.addStretch(1)
        more_layout.addLayout(cmd_row)
        self._more_panel.setVisible(False)
        hero_layout.addWidget(self._more_panel)

        self.btn_all_features = components.chip("☰ All features", checkable=True, checked=False)
        self.btn_all_features.setToolTip("Show the launcher grid and the quick-command chips")
        self.btn_all_features.toggled.connect(self._toggle_all_features)
        hero_layout.addWidget(self.btn_all_features, 0, Qt.AlignLeft)
        layout.addWidget(hero)

        layout.addWidget(self._desk_section(), 0)
        layout.addWidget(self._research_workspace_card(), 0)
        home_actions = QHBoxLayout()
        home_actions.setSpacing(8)
        self.btn_customize_home = components.chip("⚙ Customize Home", checkable=False)
        self.btn_customize_home.clicked.connect(self._customize_home)
        home_actions.addWidget(self.btn_customize_home)

        self.btn_home_details = components.chip("Week & recent activity", checkable=True, checked=False)
        self.btn_home_details.setAccessibleName("Show week and recent activity")
        home_actions.addWidget(self.btn_home_details)
        home_actions.addStretch(1)
        layout.addLayout(home_actions)
        self._details_panel = QWidget()
        details_layout = QVBoxLayout(self._details_panel)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(16)
        self._details_panel.hide()
        self.btn_home_details.toggled.connect(self._details_panel.setVisible)
        layout.addWidget(self._details_panel)
        # Keep spare viewport height below the content, not inside desk cards.
        layout.addStretch(1)
        # Secondary reporting remains available, but no longer competes with
        # the one next step when you sit down to study.
        layout = details_layout
        stats_row = QHBoxLayout()
        stat_specs = [
            (self, "task", "pending tasks"),
            (self, "events", "upcoming events"),
            (self, "pages", "saved pages"),
            (self, "boards", "boards"),
            (self, "focus", "min focused today"),
        ]
        self._stat_labels = {}
        tiles = []
        for _owner, key, label in stat_specs:
            tile = components.stat_tile("0", label)
            tiles.append(tile)
            self._stat_labels[key] = tile._value
        stats_row.addWidget(components.stat_row(tiles), 1)
        layout.addLayout(stats_row)

        # Dashboard 2.0: 7-day browsing activity mini bar chart (pure paint,
        # no chart lib) driven straight from history timestamps.
        self.week_chart = _WeekActivityChart(self)
        self.domain_chart = _DomainWeekChart(self)
        chart_cards = []
        for title_text, subtitle, chart in (
            ("Your Week", "Pages visited per day (last 7 days)", self.week_chart),
            ("Where time goes", "Top domains this week — your digital wellbeing", self.domain_chart),
        ):
            card = QFrame()
            card.setObjectName("SectionCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            card_layout.addWidget(components.section_header(title_text, subtitle))
            card_layout.addWidget(chart, 1)
            chart_cards.append(card)
        layout.addWidget(components.ResponsiveGrid(chart_cards, minimum_width=310, maximum_columns=2))

        self.btn_brief_refresh = QPushButton("↻ Refresh")
        self.btn_brief_refresh.clicked.connect(self._refresh_brief)
        self.brief_card = QFrame()
        self.brief_card.setObjectName("SectionCard")
        brief_layout = QVBoxLayout(self.brief_card)
        brief_layout.setContentsMargins(14, 12, 14, 12)
        brief_layout.setSpacing(8)
        brief_layout.addWidget(
            components.section_header("Morning Brief", "A local digest of your day", self.btn_brief_refresh)
        )
        self.lbl_brief = QLabel("Pouring your brief...")
        self.lbl_brief.setObjectName("HeroSubtitle")
        self.lbl_brief.setWordWrap(True)
        brief_layout.addWidget(self.lbl_brief)
        self.btn_brief_save = QPushButton("📝 Save as note")
        self.btn_brief_save.setToolTip("Save this briefing as a Markdown note in the vault")
        self.btn_brief_save.clicked.connect(self._save_brief_note)
        brief_layout.addWidget(self.btn_brief_save)
        layout.addWidget(self.brief_card)

        self.recent_notes = QListWidget()
        self.recent_notes.setObjectName("CafeList")
        self.recent_tasks = QListWidget()
        self.recent_tasks.setObjectName("CafeList")
        self.recent_closed = QListWidget()
        self.recent_closed.setObjectName("CafeList")
        notes_card = self._card_with_list("Recent Notes", "From SafeVault", self.recent_notes)
        tasks_card = self._today_card()
        closed_card = self._card_with_list("Recently Closed", "Tabs you closed", self.recent_closed)
        layout.addWidget(components.ResponsiveGrid([notes_card, tasks_card, closed_card], minimum_width=280, maximum_columns=3))
        layout.addWidget(self._reflect_card())

        self.btn_browser, self.btn_ai, self.btn_personal, self.btn_task, self.btn_focus, self.btn_library, self.btn_history, self.btn_settings, self.btn_guide = self._launch_tiles

        self.btn_browser.clicked.connect(lambda: self.shell.switch_workspace("browser"))
        self.btn_ai.clicked.connect(lambda: self.shell.switch_workspace("ai"))
        self.btn_personal.clicked.connect(lambda: self.shell.switch_workspace("personal"))
        self.btn_task.clicked.connect(self.shell.quick_task_dialog)
        self.btn_focus.clicked.connect(self._start_focus)
        self.recent_tasks.itemDoubleClicked.connect(self._open_agenda_item)
        self.btn_library.clicked.connect(lambda: self.shell.switch_workspace("library"))
        self.btn_history.clicked.connect(lambda: self.shell.switch_workspace("history"))
        self.btn_settings.clicked.connect(lambda: self.shell.switch_workspace("settings"))
        self.btn_guide.clicked.connect(lambda: dialogs.show_browser_control_center(self.shell.browser_page))
        self.recent_closed.itemDoubleClicked.connect(self._open_recent_closed)
        self.recent_notes.itemDoubleClicked.connect(self._open_agenda_item)

        self._apply_home_preferences()

    def _home_preference(self):
        default_order = ["next", *[key for key in desk_service.DESK_BLOCKS if key != "next"]]
        value = prefs.get_pref(self.shell.profile_dir, "home_dashboard", {})
        if not isinstance(value, dict):
            value = {}
        raw_order = value.get("order", [])
        raw_order = raw_order if isinstance(raw_order, list) else []
        order = [key for key in raw_order if key in default_order]
        order.extend(key for key in default_order if key not in order)
        raw_visible = value.get("visible", default_order)
        raw_visible = raw_visible if isinstance(raw_visible, list) else default_order
        visible = [key for key in raw_visible if key in default_order]
        if not visible:
            visible = default_order
        size = value.get("size", "comfortable")
        if size not in {"compact", "comfortable", "spacious"}:
            size = "comfortable"
        return {"order": order, "visible": visible, "size": size}

    def _apply_home_preferences(self):
        if not getattr(self, "_desk_cards", None):
            return
        config = self._home_preference()
        self._desk_grid._widgets = [self._desk_cards[key]["card"] for key in config["order"]]
        self._desk_grid._columns = 0
        self._desk_grid._reflow()
        for key, widgets in self._desk_cards.items():
            widgets["card"].setVisible(key in config["visible"])
            listing = widgets["list"]
            minimum, maximum = {
                "compact": (76, 108),
                "comfortable": (118, 168),
                "spacious": (176, 248),
            }[config["size"]]
            listing.setMinimumHeight(minimum)
            listing.setMaximumHeight(maximum)

    def _customize_home(self):
        config = self._home_preference()
        dialog = QDialog(self)
        dialog.setWindowTitle("Customize Home")
        dialog.resize(430, 390)
        dialog.setStyleSheet(_stylesheet(self.shell))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Show the cards you use, move them into your preferred order, and choose their reading height. These settings apply to this profile."))
        listing = QListWidget()
        listing.setAccessibleName("Home dashboard widgets")
        listing.setDragDropMode(QListWidget.InternalMove)
        for key in config["order"]:
            title = desk_service.BLOCK_TITLES[key]
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked if key in config["visible"] else Qt.Unchecked)
            listing.addItem(item)
        layout.addWidget(listing, 1)
        size_combo = QComboBox()
        for label, value in (("Compact", "compact"), ("Comfortable", "comfortable"), ("Spacious", "spacious")):
            size_combo.addItem(label, value)
        size_combo.setCurrentIndex(max(0, size_combo.findData(config["size"])))
        layout.addWidget(QLabel("Card content height"))
        layout.addWidget(size_combo)
        buttons = QHBoxLayout()
        reset = QPushButton("Reset to default")
        save = primary_button("Save layout")
        close = quiet_button("Cancel")
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        reset_requested = [False]

        def reset_layout():
            prefs.save_pref(self.shell.profile_dir, "home_dashboard", {})
            reset_requested[0] = True
            dialog.accept()

        reset.clicked.connect(reset_layout)
        close.clicked.connect(dialog.reject)

        def save_layout():
            order = [listing.item(i).data(Qt.UserRole) for i in range(listing.count())]
            visible = [listing.item(i).data(Qt.UserRole) for i in range(listing.count()) if listing.item(i).checkState() == Qt.Checked]
            if not visible:
                QMessageBox.information(dialog, "Customize Home", "Keep at least one Home card visible.")
                return
            prefs.save_pref(self.shell.profile_dir, "home_dashboard", {
                "order": order, "visible": visible, "size": size_combo.currentData(),
            })
            dialog.accept()
            self._apply_home_preferences()

        save.clicked.connect(save_layout)
        dialog.exec_()
        if reset_requested[0]:
            self._apply_home_preferences()

    def _run_home_command(self):
        text = self.ed_home_command.text().strip()
        if not text:
            self.ed_home_command.setFocus()
            return
        self._send_quick_command(text, self.shell)
        self.ed_home_command.clear()

    def _tick_clock(self):
        self.lbl_today.setText(time.strftime("%A, %d %B · %H:%M"))

    def _toggle_all_features(self, shown: bool):
        """Show/hide the launcher grid + quick commands (collapsed by default)."""
        self._more_panel.setVisible(bool(shown))

    def _desk_section(self):
        """The desk: four blocks that answer "what do I do now".

        Home is the first thing a person sees and it used to be a menu — tiles,
        stats, charts. The desk replaces that default view with the four things
        a working session actually needs: today's plate, what is due, what was
        left half-finished, and the loop's one next step.
        """
        section = QWidget()
        section.setObjectName("HomeDesk")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.lbl_desk = QLabel("Setting the desk...")
        self.lbl_desk.setObjectName("MutedLabel")
        self.lbl_desk.setWordWrap(True)
        layout.addWidget(self.lbl_desk)
        self._desk_cards = {}
        for key in desk_service.DESK_BLOCKS:
            self._desk_card(key)
        self._desk_grid = components.ResponsiveGrid(
            [self._desk_cards[key]["card"] for key in ("next", *[value for value in desk_service.DESK_BLOCKS if value != "next"])],
            minimum_width=260, maximum_columns=4,
        )
        self._desk_grid.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout.addWidget(self._desk_grid)
        return section

    def _research_workspace_card(self):
        card = QFrame()
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)
        layout.addWidget(components.section_header("Research desk", "Continue a saved line of work across browser, notes, and tasks"))
        self.lbl_research_workspace = QLabel("No active research workspace")
        self.lbl_research_workspace.setObjectName("HeroSubtitle")
        self.lbl_research_workspace.setWordWrap(True)
        layout.addWidget(self.lbl_research_workspace)
        self.lbl_research_links = QLabel("")
        self.lbl_research_links.setObjectName("MutedLabel")
        self.lbl_research_links.setWordWrap(True)
        layout.addWidget(self.lbl_research_links)
        self.research_items = QListWidget()
        self.research_items.setObjectName("CafeList")
        self.research_items.setMaximumHeight(94)
        self.research_items.setToolTip("Double-click a linked item to open it where it lives")
        self.research_items.itemDoubleClicked.connect(self._open_research_item)
        layout.addWidget(self.research_items)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.btn_research_resume = QPushButton("Resume tabs")
        self.btn_research_ai = QPushButton("Ask AI with context")
        self.btn_research_capture = QPushButton("Capture to desk")
        self.btn_research_manage = quiet_button("Manage")
        self.btn_research_resume.clicked.connect(self._resume_research_workspace)
        self.btn_research_ai.clicked.connect(self._ask_research_workspace)
        self.btn_research_capture.clicked.connect(self.shell.open_quick_capture)
        self.btn_research_manage.clicked.connect(self._manage_research_workspaces)
        for button in (self.btn_research_resume, self.btn_research_ai, self.btn_research_capture, self.btn_research_manage):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return card

    def _refresh_research_workspace(self):
        workspace = tab_sets.get_active_research_workspace(self.shell.profile_dir)
        self._active_research = workspace
        active = bool(workspace)
        self.btn_research_resume.setEnabled(active)
        self.btn_research_ai.setEnabled(active)
        self.btn_research_manage.setEnabled(True)
        if not workspace:
            self.lbl_research_workspace.setText("No active research workspace. Save one from Browser → Options → Sessions & Spaces.")
            self.lbl_research_links.clear()
            self.research_items.clear()
            self.research_items.addItem(components.hint_list_item("Captures and linked items will appear here", "○"))
            return
        counts = [f"{len(workspace.get('tabs', []))} tabs"]
        self.research_items.clear()
        reference_kinds = {"notes": "note", "tasks": "task", "saved_pages": "saved-page", "flashcards": "flashcard"}
        note_map = {str(note.get("id")): note.get("title", "Note") for note in personal_service.list_notes(self.shell.profile_dir)}
        task_map = {str(task.get("id")): task.get("title", "Task") for task in life_service.load_tasks(self.shell.profile_dir)}
        page_map = {str(page.get("id")): page.get("title", "Saved page") for page in life_service.load_saved_pages(self.shell.profile_dir)}
        card_map = {str(card.get("id")): card.get("front", "Flashcard") for card in flashcard_service.load_cards(self.shell.profile_dir)}
        for field, label, mapping in (
            ("notes", "notes", note_map), ("tasks", "tasks", task_map),
            ("saved_pages", "saved links", page_map), ("flashcards", "cards", card_map),
        ):
            ids = workspace.get(field, [])
            if ids:
                counts.append(f"{len(ids)} {label}")
                for item_id in ids:
                    title = mapping.get(item_id)
                    if not title:
                        continue
                    item = QListWidgetItem(f"{label.rstrip('s')}: {str(title)[:140]}")
                    item.setData(Qt.UserRole, {"kind": reference_kinds[field], "id": item_id})
                    self.research_items.addItem(item)
        self.lbl_research_workspace.setText(f"{workspace.get('title', 'Research workspace')}  ·  " + "  ·  ".join(counts))
        self.lbl_research_links.setText("Double-click a linked item to open it." if self.research_items.count() else "No linked items yet. Capture something to this desk to start the chain.")
        if not self.research_items.count():
            self.research_items.addItem(components.hint_list_item("No linked items", "○"))

    def _open_research_item(self, item):
        payload = item.data(Qt.UserRole) if item is not None else None
        if isinstance(payload, dict) and payload.get("id"):
            self.shell.open_library_item(payload)

    def _resume_research_workspace(self):
        workspace = getattr(self, "_active_research", None)
        if not workspace or not self.shell.switch_workspace("browser"):
            return
        self.shell.browser_page.restore_tab_set(workspace["id"], mode="merge")

    def _ask_research_workspace(self):
        if not getattr(self, "_active_research", None) or not self.shell.switch_workspace("ai"):
            return
        checkbox = getattr(self.shell.ai_page, "chk_research_context", None)
        if checkbox is not None:
            checkbox.setChecked(True)
        self.shell.ai_page.ed_question.setFocus()

    def _manage_research_workspaces(self):
        if self.shell.switch_workspace("browser"):
            dialogs.show_tab_sets_dialog(self.shell.browser_page)

    def _desk_card(self, key: str):
        card = QFrame()
        card.setObjectName("SectionCard")
        card.setProperty("deskBlock", key)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header_row.addWidget(
            components.section_header(desk_service.BLOCK_TITLES[key], desk_service.BLOCK_SUBTITLES[key]),
            1,
        )
        badge = components.badge("0", "accent")
        header_row.addWidget(badge, 0, Qt.AlignTop)
        layout.addLayout(header_row)
        listing = QListWidget()
        listing.setObjectName("CafeList")
        listing.setMinimumHeight(118)
        listing.setMaximumHeight(168)
        listing.setToolTip("Double-click a row to open where it lives")
        listing.itemDoubleClicked.connect(self._open_desk_row)
        layout.addWidget(listing, 1)
        buttons = QVBoxLayout() if key == "next" else QHBoxLayout()
        buttons.setSpacing(6)
        if key == "next":
            self.btn_desk_continue = QPushButton("▶ Continue")
            self.btn_desk_continue.setObjectName("TopAccentButton")
            self.btn_desk_continue.setMinimumWidth(0)
            self.btn_desk_continue.setToolTip("Run the next step of the loop")
            self.btn_desk_continue.clicked.connect(self._run_flow_next)
            buttons.addWidget(self.btn_desk_continue)
            self.btn_desk_ritual = QPushButton("☕ Study session")
            self.btn_desk_ritual.setToolTip("Sit down properly: pick a pour, set the timer, study")
            self.btn_desk_ritual.clicked.connect(self._start_ritual)
            buttons.addWidget(self.btn_desk_ritual)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._desk_cards[key] = {"card": card, "list": listing, "badge": badge}
        return card

    def _refresh_desk(self):
        """One service call fills the four blocks; the UI only renders."""
        if not getattr(self, "_desk_cards", None):
            return
        desk = desk_service.build_desk(self.shell.profile_dir)
        self._desk = desk
        self.lbl_desk.setText(f"{desk.get('headline', '')}   ·   {desk.get('pulse', '')}".strip(" ·"))
        for key, widgets in self._desk_cards.items():
            block = desk_service.block_by_key(desk, key)
            listing = widgets["list"]
            listing.clear()
            widgets["badge"].setText(str(block.get("count", 0)))
            rows = block.get("rows", [])
            for row in rows:
                item = QListWidgetItem(f"{row.get('marker', '')}{row.get('title', '')}")
                item.setToolTip(row.get("subtitle", "") or row.get("title", ""))
                item.setData(Qt.UserRole, row)
                listing.addItem(item)
            if not rows:
                listing.addItem(components.hint_list_item(block.get("empty") or "Nothing here", "○"))
            if key == "next":
                action = block.get("flow") or {}
                label = action.get("label") or "▶ Continue"
                self.btn_desk_continue.setAccessibleName(label)
                self.btn_desk_continue.setText(label if len(label) <= 28 else label[:25] + "…")
                self.btn_desk_continue.setEnabled(bool(action))
                self.btn_desk_continue.setToolTip(action.get("reason") or "The loop is clear")

    def _open_desk_row(self, item):
        """A desk row either runs a command or routes to wherever it lives."""
        data = item.data(Qt.UserRole) if item is not None else None
        if not isinstance(data, dict):
            return
        command = (data.get("command") or "").strip()
        if command:
            self._send_quick_command(command, self.shell)
            return
        self.shell.open_library_item(data)

    def _start_ritual(self):
        """Open the study-session dialog — the ritual front door to a pour.

        The desk is recomputed when it is missing so the dialog can always offer
        the loop's next step as the default thing to finish.
        """
        from litebrowser.ui.dialogs import study_ritual

        desk = getattr(self, "_desk", None) or desk_service.build_desk(self.shell.profile_dir)
        study_ritual.show_study_ritual(self.shell, desk)

    def resizeEvent(self, event):
        """Trim secondary hero chrome on narrow viewports.

        The hero keeps its natural (wrap-friendly) width, so at small shell
        sizes these extras would be the only things forcing horizontal
        overflow; dropping them lets the dashboard fit without a sideways
        scrollbar."""
        super().resizeEvent(event)
        width = max(0, self.width())
        if hasattr(self, "lbl_today"):
            self.lbl_today.setVisible(width >= 700)
        if hasattr(self, "lbl_home_version"):
            self.lbl_home_version.setVisible(width >= 1150)
        if hasattr(self, "lbl_quick_commands"):
            self.lbl_quick_commands.setVisible(width >= 1000)

    def _open_recent_closed(self, item):
        url = item.data(Qt.UserRole) or ""
        if not url:
            return
        self.shell.switch_workspace("browser")
        self.shell.browser_page.add_new_tab(QUrl(url), item.text())

    def _send_quick_command(self, cmd: str, shell):
        shell.omnibar.setText(cmd)
        if cmd.endswith(" "):
            shell.omnibar.setFocus()
            shell.omnibar.setCursorPosition(len(cmd))
            return
        shell.handle_omnibar()

    def _today_card(self):
        """Today's plate plus the loop: what is on it, and what to do about it.

        The agenda list answers "what is on my plate"; the strip above it answers
        "what is next" by reading every store (planner, cards, captures, links) —
        so Home is a doorway into the process, not a report about it.
        """
        card = QFrame()
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(
            components.section_header("Today", "Planner deadlines · quick tasks · the study loop")
        )
        self.lbl_flow = QLabel("")
        self.lbl_flow.setObjectName("MutedLabel")
        self.lbl_flow.setWordWrap(True)
        layout.addWidget(self.lbl_flow)
        flow_row = QHBoxLayout()
        flow_row.setSpacing(6)
        self.btn_flow_next = QPushButton("▶ Continue")
        self.btn_flow_next.setToolTip("Run the next step of the loop")
        self.btn_flow_next.clicked.connect(self._run_flow_next)
        self.btn_agenda_promote = QPushButton("→ Planner")
        self.btn_agenda_promote.setToolTip(
            "Promote the selected inbox task into the Weekly Plan (the two stay linked)"
        )
        self.btn_agenda_promote.clicked.connect(self._promote_agenda_task)
        flow_row.addWidget(self.btn_flow_next)
        flow_row.addWidget(self.btn_agenda_promote)
        flow_row.addStretch(1)
        layout.addLayout(flow_row)
        # A slightly lower floor than the other cards leaves room for the strip
        # without pushing the dashboard past the viewport.
        self.recent_tasks.setMinimumHeight(180)
        layout.addWidget(self.recent_tasks, 1)
        return card

    def _reflect_card(self):
        """The week's evidence: what was poured, what the streak is, what was skipped.

        The loop's last station used to be prose in the brief; reading the four
        stores that study, review and plan already write lets the dashboard say
        what *happened* instead of only what is due — and name the one row that
        has been waiting the longest.
        """
        card = QFrame()
        card.setObjectName("SectionCard")
        card.setMaximumHeight(230)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        self.btn_reflect_study = QPushButton("▶ Study the oldest one")
        self.btn_reflect_study.setToolTip("Pour a focus session for the item that has waited longest")
        self.btn_reflect_study.clicked.connect(self._study_neglected)
        layout.addWidget(
            components.section_header(
                "This Week", "Reflect — poured minutes, streaks, and what got skipped", self.btn_reflect_study
            )
        )
        self.lbl_reflect = QLabel("")
        self.lbl_reflect.setObjectName("MutedLabel")
        self.lbl_reflect.setWordWrap(True)
        layout.addWidget(self.lbl_reflect)
        self.reflect_items = QListWidget()
        self.reflect_items.setObjectName("CafeList")
        self.reflect_items.setMaximumHeight(96)
        self.reflect_items.setToolTip("Double-click a row to open it in the Weekly Plan")
        self.reflect_items.itemDoubleClicked.connect(self._open_reflect_item)
        layout.addWidget(self.reflect_items)
        return card

    def _refresh_reflect(self):
        """One call fills the reflection: the line, the list, and the button."""
        review = study_flow.weekly_review(self.shell.profile_dir)
        self._reflect = review
        self.lbl_reflect.setText(study_flow.review_line(review))
        self.reflect_items.clear()
        for row in review.get("neglected", []):
            item = QListWidgetItem(f"{row.get('title', '')} — {row.get('detail', '')}")
            item.setData(Qt.UserRole, {"kind": row.get("kind", "planner-item"), "id": row.get("id", "")})
            self.reflect_items.addItem(item)
        if self.reflect_items.count() == 0:
            self.reflect_items.addItem(components.hint_list_item("Nothing was skipped this week", "✓"))
        self.btn_reflect_study.setEnabled(self.reflect_items.count() > 0 and bool(review.get("neglected")))

    def _study_neglected(self):
        """Reflect → study: the row at the top of the list becomes the next pour."""
        rows = (getattr(self, "_reflect", None) or {}).get("neglected") or []
        if not rows:
            return
        top = rows[0]
        self.shell.open_flow_step(
            {
                "step": "study",
                "label": f"▶ Study “{top.get('title', '')}”",
                "reason": top.get("detail", ""),
                "kind": top.get("kind", "planner-item"),
                "id": top.get("id", ""),
                "minutes": int(top.get("minutes", 0) or 0),
                "start": True,
            }
        )

    def _open_reflect_item(self, row):
        data = row.data(Qt.UserRole) if row is not None else None
        if isinstance(data, dict) and data.get("id"):
            self.shell.open_library_item(data)

    def _refresh_flow(self):
        flow = study_flow.build_flow(self.shell.profile_dir)
        action = flow.get("next") or {}
        self.lbl_flow.setText(flow.get("pulse", ""))
        self.lbl_flow.setToolTip(" → ".join(step["title"] for step in flow.get("steps", [])))
        self._flow_next = action
        label = action.get("label") or "▶ Continue"
        self.btn_flow_next.setAccessibleName(label)
        self.btn_flow_next.setText(label if len(label) <= 24 else label[:21] + "…")
        self.btn_flow_next.setToolTip(action.get("reason") or "The loop is clear")
        self.btn_flow_next.setEnabled(bool(action))

    def _run_flow_next(self):
        action = getattr(self, "_flow_next", None) or study_flow.next_step(self.shell.profile_dir)
        self.shell.open_flow_step(action)

    def _promote_agenda_task(self):
        """Capture → plan hand-off for the row selected in Today."""
        row = self.recent_tasks.currentItem()
        data = row.data(Qt.UserRole) if row is not None else None
        data = data if isinstance(data, dict) else {}
        if data.get("kind") != "task":
            QMessageBox.information(
                self,
                "Weekly Plan",
                "Select an inbox row in Today first, then promote it into the planner.",
            )
            return
        item = study_flow.promote_task(self.shell.profile_dir, data.get("id", ""))
        if item is None:
            return
        self.shell.refresh_shell()
        QMessageBox.information(
            self,
            "Weekly Plan",
            f"“{item.get('title', '')}” is on the weekly plan now — inbox and planner stay linked.",
        )

    def _card_with_list(self, title_text: str, subtitle: str, list_widget: QListWidget):
        card = QFrame()
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        header = components.section_header(title_text, subtitle)
        layout.addWidget(header)
        # A generous floor keeps the Recent Notes / Today's Focus / Recently
        # Closed cards from collapsing into a single cramped row on shorter
        # viewports; extra window height then grows them further.
        list_widget.setMinimumHeight(150)
        layout.addWidget(list_widget, 1)
        return card

    def _start_focus(self):
        from litebrowser.services import focus_service
        focus_service.start_focus(self.shell.profile_dir, minutes=25, label="Home quick pour")
        self.shell.refresh_shell()
        QMessageBox.information(self, "Café Focus", "25-minute pour started. Track it with /status or /focus.")

    def refresh(self):
        locked = getattr(self.shell, "_private_locked", False) is True or (
            security.has_passcode(self.shell.profile_dir) and not (
                security.is_unlocked(self.shell.profile_dir) or getattr(self.shell, "_unlocked_spaces", set())
            )
        )
        if locked:
            # Home is public chrome, not a bypass around Personal's passcode.
            for label in self._stat_labels.values():
                label.setText("—")
            for listing in (self.recent_notes, self.recent_tasks, self.recent_closed, self.reflect_items):
                listing.clear()
                listing.addItem(components.hint_list_item("Unlock Personal to continue", "○"))
            for widgets in self._desk_cards.values():
                widgets["list"].clear()
                widgets["list"].addItem(components.hint_list_item("Your private desk is locked", "○"))
                widgets["badge"].setText("—")
            self._flow_next = {}
            self._desk = {}
            self.lbl_desk.setText("Your quiet corner is ready. Open Personal to unlock your desk.")
            self.lbl_flow.setText("Private workspace locked")
            self.lbl_reflect.clear()
            self.lbl_brief.setText("Unlock Personal to see your morning brief.")
            self.lbl_research_workspace.setText("Unlock Personal to see your research desk.")
            self.lbl_research_links.clear()
            self.research_items.clear()
            self.research_items.addItem(components.hint_list_item("Unlock Personal to see linked research items", "○"))
            self._active_research = None
            for button in (self.btn_research_resume, self.btn_research_ai, self.btn_research_capture):
                button.setEnabled(False)
            self.btn_desk_continue.setEnabled(False)
            self.btn_flow_next.setEnabled(False)
            self.week_chart._counts = [0] * 7
            self.domain_chart._rows = []
            self.week_chart.update()
            self.domain_chart.update()
            return
        snapshot = life_service.get_dashboard_snapshot(self.shell.profile_dir)
        self._refresh_research_workspace()
        self.btn_research_capture.setEnabled(True)
        self._stat_labels["task"].setText(str(snapshot["tasks_pending"]))
        self._stat_labels["events"].setText(str(len(snapshot["events_upcoming"])))
        self._stat_labels["pages"].setText(str(snapshot["saved_pages_total"]))
        self._stat_labels["boards"].setText(str(snapshot["boards_total"]))
        self._stat_labels["focus"].setText(f"{focus_service.today_focus_seconds(self.shell.profile_dir) // 60}")
        if getattr(self, "week_chart", None) is not None:
            self.week_chart.refresh()
        if getattr(self, "domain_chart", None) is not None:
            self.domain_chart.refresh()

        self.recent_notes.clear()
        for note in personal_service.list_notes(self.shell.profile_dir)[:8]:
            row = QListWidgetItem(note["title"])
            row.setToolTip(note.get("snippet", ""))
            row.setData(Qt.UserRole, {"kind": "note", "id": note["id"]})
            self.recent_notes.addItem(row)
        if self.recent_notes.count() == 0:
            self.recent_notes.addItem(components.hint_list_item("No notes yet"))

        self.recent_tasks.clear()
        # One day across both systems: planner deadlines + planner blocks + the
        # legacy quick-task inbox, overdue first.
        agenda = life_service.today_agenda(self.shell.profile_dir)
        for entry in agenda["items"][:10]:
            prefix = "Planner" if entry.get("source") == "planner" else "Inbox"
            marker = "⚠ " if entry.get("overdue") else ""
            subtitle = entry.get("subtitle", "")
            row = QListWidgetItem(
                f"{marker}[{prefix}] {entry.get('title', '')}" + (f" · {subtitle}" if subtitle else "")
            )
            row.setToolTip(f"{entry.get('title', '')} — double-click to open")
            row.setData(
                Qt.UserRole,
                {"kind": entry.get("kind", ""), "id": entry.get("id", ""), "subtitle": subtitle},
            )
            self.recent_tasks.addItem(row)
        if self.recent_tasks.count() == 0:
            self.recent_tasks.addItem(components.hint_list_item("Nothing scheduled today", "○"))

        self.recent_closed.clear()
        state = prefs.session_state_load(self.shell.profile_dir)
        closed = [entry for entry in state.get("recently_closed", []) if entry.get("kind") == "tab" and entry.get("url")][:10]
        for entry in closed:
            row = QListWidgetItem((entry.get("title") or entry.get("url") or "").strip() or entry.get("url"))
            row.setToolTip(entry.get("url", ""))
            row.setData(Qt.UserRole, entry.get("url", ""))
            self.recent_closed.addItem(row)
        if self.recent_closed.count() == 0:
            self.recent_closed.addItem(components.hint_list_item("Nothing closed recently", "○"))

        self._refresh_flow()
        self._refresh_desk()
        self._refresh_reflect()
        self.brief_card.setVisible(prefs.get_show_morning_brief(self.shell.profile_dir))
        self._refresh_brief()

    def _refresh_brief(self):
        brief = brief_service.build_morning_brief(self.shell.profile_dir)
        self.lbl_brief.setText(brief_service.brief_text(brief))

    def _open_agenda_item(self, row: QListWidgetItem):
        """Home agenda row -> wherever the item actually lives."""
        data = row.data(Qt.UserRole) or {}
        if data:
            self.shell.open_library_item(data)

    def _save_brief_note(self):
        """Keep today's briefing in the vault as Markdown (the export format)."""
        brief = brief_service.build_morning_brief(self.shell.profile_dir)
        title = f"Morning Brief — {time.strftime('%Y-%m-%d')}"
        personal_service.create_note(
            self.shell.profile_dir, title, brief_service.brief_markdown(brief), category="Brief"
        )
        QMessageBox.information(self, "Morning Brief", "Saved to your vault as a Markdown note.")


class LibraryPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("LibraryWorkspace")
        self._last_results = []
        self._library_filter = "all"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(10)
        heading = QHBoxLayout()
        page = components.page_header("Library", "A calm shelf for pages, notes, tasks, and ideas")
        heading.addWidget(page, 1)
        self.lbl_library_scope = components.badge("PRIVATE SHELF", "accent")
        heading.addWidget(self.lbl_library_scope, 0, Qt.AlignTop)
        hero_layout.addLayout(heading)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Search your saved pages, notes, tasks, boards, and calendar...")
        self.ed_search.setMinimumWidth(0)
        self.ed_search.setAccessibleName("Search the library")
        search_row.addWidget(self.ed_search, 1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("TopAccentButton")
        search_row.addWidget(self.btn_refresh)
        hero_layout.addLayout(search_row)

        filter_row = QGridLayout()
        filter_row.setHorizontalSpacing(6)
        filter_row.setVerticalSpacing(6)
        filter_label = QLabel("SHOW")
        filter_label.setObjectName("MutedLabel")
        filter_row.addWidget(filter_label, 0, 0)
        self.library_filter_buttons = {}
        for key, label in (
            ("all", "Everything"),
            ("pages", "Pages"),
            ("notes", "Notes"),
            ("tasks", "Tasks"),
            ("events", "Events"),
            ("boards", "Boards"),
            ("planner", "Planner"),
            ("cards", "Cards"),
        ):
            button = components.chip(label, checked=key == "all")
            button.clicked.connect(lambda checked=False, value=key: self._set_library_filter(value))
            self.library_filter_buttons[key] = button
            index = len(self.library_filter_buttons) - 1
            filter_row.addWidget(button, index // 4, index % 4 + 1)
        filter_row.setColumnStretch(5, 1)
        hero_layout.addLayout(filter_row)
        layout.addWidget(hero)

        self.library_stats = {
            "results": components.stat_tile("0", "on this shelf"),
            "pages": components.stat_tile("0", "saved pages"),
            "notes": components.stat_tile("0", "notes"),
            "tasks": components.stat_tile("0", "tasks"),
        }
        layout.addWidget(components.stat_row(list(self.library_stats.values())))

        shelf_card, shelf_layout = _panel("Browse your shelf", "Open any item to continue where you left off")
        self.lbl_summary = QLabel("Preparing your shelf...")
        self.lbl_summary.setObjectName("MutedLabel")
        shelf_layout.addWidget(self.lbl_summary)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("CafeList")
        self.list_widget.setSpacing(2)
        shelf_layout.addWidget(self.list_widget, 1)
        layout.addWidget(shelf_card, 1)

        self.ed_search.returnPressed.connect(self.refresh)
        self.btn_refresh.clicked.connect(self.refresh)
        self.list_widget.itemDoubleClicked.connect(self._open_item)

    def _set_library_filter(self, value: str):
        self._library_filter = value
        for key, button in self.library_filter_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == value)
            button.blockSignals(False)
        self.refresh()

    @staticmethod
    def _matches_library_filter(item: dict, value: str) -> bool:
        if value == "all":
            return True
        kind = (item.get("kind") or "").lower()
        mapping = {
            "pages": {"saved-page", "browser-visit", "bookmark"},
            "notes": {"note", "vault_note"},
            "tasks": {"task"},
            "events": {"event", "calendar"},
            "boards": {"board", "board-node"},
            "planner": {"planner-item", "planner-course", "planner-block"},
            "cards": {"flashcard"},
        }
        return kind in mapping.get(value, set())

    def refresh(self, query: str | None = None):
        q = query if isinstance(query, str) else self.ed_search.text().strip()
        self.ed_search.setText(q)
        items = []
        if q:
            items.extend(life_service.search_everything(self.shell.profile_dir, q))
            for _score, doc in retriever.search(self.shell.profile_dir, q, top_k=10):
                mapped_kind = doc.source
                mapped_id = doc.url
                subtitle = doc.url or doc.snippet
                if doc.source == "vault_note":
                    mapped_kind = "note"
                    mapped_id = doc.meta.get("note_id", "")
                    subtitle = doc.snippet
                elif doc.source == "task":
                    mapped_kind = "task"
                    mapped_id = doc.meta.get("task_id", "")
                elif doc.source == "calendar":
                    mapped_kind = "event"
                    mapped_id = doc.meta.get("event_id", "")
                elif doc.source == "board":
                    mapped_kind = "board"
                    mapped_id = doc.meta.get("board_id", "")
                elif doc.source == "board_note":
                    mapped_kind = "board-node"
                    mapped_id = doc.meta.get("board_id", "")
                elif doc.source == "saved_page":
                    mapped_kind = "saved-page"
                    mapped_id = doc.meta.get("saved_page_id", "")
                elif doc.source == "planner_item":
                    mapped_kind = "planner-item"
                    mapped_id = doc.meta.get("plan_item_id", "")
                    subtitle = doc.snippet
                elif doc.source == "planner_course":
                    mapped_kind = "planner-course"
                    mapped_id = doc.meta.get("course_id", "")
                    subtitle = doc.snippet
                elif doc.source == "planner_block":
                    mapped_kind = "planner-block"
                    mapped_id = doc.meta.get("plan_block_id", "")
                    subtitle = doc.snippet
                elif doc.source == "flashcard":
                    mapped_kind = "flashcard"
                    mapped_id = doc.meta.get("card_id", "")
                    subtitle = doc.snippet
                items.append({"kind": mapped_kind, "title": doc.title or doc.url, "id": mapped_id, "subtitle": subtitle})
            items = _dedupe_library_items(items)
        else:
            for page in life_service.load_saved_pages(self.shell.profile_dir)[:20]:
                items.append({"kind": "saved-page", "title": page.get("title", ""), "id": page.get("id", ""), "subtitle": page.get("url", "")})
            for note in personal_service.list_notes(self.shell.profile_dir)[:20]:
                items.append({"kind": "note", "title": note.get("title", ""), "id": note.get("id", ""), "subtitle": note.get("snippet", "")})
            for task in life_service.load_tasks(self.shell.profile_dir)[:20]:
                items.append({"kind": "task", "title": task.get("title", ""), "id": task.get("id", ""), "subtitle": task.get("bucket", "")})
            for event in life_service.load_events(self.shell.profile_dir)[:20]:
                items.append({"kind": "event", "title": event.get("title", ""), "id": event.get("id", ""), "subtitle": _format_ts(event.get("starts_at", 0))})
            for board in life_service.load_boards(self.shell.profile_dir)[:20]:
                items.append({"kind": "board", "title": board.get("title", ""), "id": board.get("id", ""), "subtitle": "Idea board"})
            from litebrowser.services import flashcard_service, personal_plan
            plan = personal_plan.load_plan(self.shell.profile_dir)
            for collection, kind, title_key in (("items", "planner-item", "title"), ("courses", "planner-course", "name"), ("time_blocks", "planner-block", "title")):
                for row in plan[collection][:20]:
                    items.append({"kind": kind, "id": row["id"], "title": row[title_key], "subtitle": row.get("notes") or row.get("date") or "Weekly plan"})
            for card in flashcard_service.load_cards(self.shell.profile_dir)[:20]:
                items.append({"kind": "flashcard", "id": card.get("id", ""), "title": card.get("front", ""), "subtitle": card.get("back", "")[:160]})
        items = [item for item in items if self._matches_library_filter(item, self._library_filter)]
        self._last_results = items
        self.list_widget.clear()
        for item in items:
            list_item = _activity_item(
                item.get("kind", ""),
                item.get("title", ""),
                item.get("subtitle", ""),
            )
            list_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(list_item)
        if self.list_widget.count() == 0:
            empty = QListWidgetItem("No items matched this view.\nTry another shelf or a shorter search.")
            empty.setFlags(Qt.NoItemFlags)
            empty.setSizeHint(QSize(0, 54))
            self.list_widget.addItem(empty)
            self.lbl_summary.setText("No items matched this view.")
        else:
            scope = self.library_filter_buttons.get(self._library_filter).text().lower()
            self.lbl_summary.setText(f"{len(items)} {scope} ready to reopen")
        self.library_stats["results"]._value.setText(str(len(items)))
        self.library_stats["pages"]._value.setText(str(len(life_service.load_saved_pages(self.shell.profile_dir))))
        self.library_stats["notes"]._value.setText(str(len(personal_service.list_notes(self.shell.profile_dir))))
        self.library_stats["tasks"]._value.setText(str(len(life_service.load_tasks(self.shell.profile_dir))))

    def _open_item(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole) or {}
        if data:
            self.shell.open_library_item(data)


class SettingsPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("SettingsWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.addWidget(
            components.page_header(
                "Settings",
                "Appearance, privacy, and your local workspace",
            ),
            1,
        )
        self.lbl_settings_profile = components.badge("LOCAL PROFILE", "accent")
        title_row.addWidget(self.lbl_settings_profile, 0, Qt.AlignTop)
        hero_layout.addLayout(title_row)
        hero_note = QLabel("Your choices are saved to this profile. Changes to the theme take effect across the entire workspace.")
        hero_note.setObjectName("HeroSubtitle")
        hero_note.setWordWrap(True)
        hero_note.hide()
        layout.addWidget(hero)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName("SettingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("SettingsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 2, 0)
        content_layout.setSpacing(12)
        self.settings_scroll.setWidget(content)
        layout.addWidget(self.settings_scroll, 1)

        account_card = QFrame()
        account_card.setObjectName("SectionCard")
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(12, 12, 12, 12)
        account_layout.setSpacing(6)
        account_layout.addWidget(components.section_header("Account", "Profile identity & local sync readiness"))
        account_summary = QHBoxLayout()
        self.lbl_account_initial = QLabel("LB")
        self.lbl_account_initial.setObjectName("HeroBadge")
        self.lbl_account_initial.setMinimumWidth(42)
        self.lbl_account_initial.setAlignment(Qt.AlignCenter)
        account_summary.addWidget(self.lbl_account_initial, 0, Qt.AlignTop)
        account_copy = QVBoxLayout()
        self.lbl_account_summary = QLabel("Personal workspace")
        self.lbl_account_summary.setFont(components._font(13, components.WEIGHT_BOLD))
        account_copy.addWidget(self.lbl_account_summary)
        self.lbl_account_detail = QLabel("Stored locally on this device")
        self.lbl_account_detail.setObjectName("MutedLabel")
        account_copy.addWidget(self.lbl_account_detail)
        account_summary.addLayout(account_copy, 1)
        account_layout.addLayout(account_summary)
        self.ed_display_name = QLineEdit()
        self.ed_display_name.setPlaceholderText("Display name")
        self.ed_email = QLineEdit()
        self.ed_email.setPlaceholderText("Email")
        self.chk_local_snapshot = QCheckBox("Keep a local profile snapshot")
        account_layout.addWidget(self.ed_display_name)
        account_layout.addWidget(self.ed_email)
        account_layout.addWidget(self.chk_local_snapshot)
        self.btn_save_account = QPushButton("Save account")
        self.btn_save_account.setObjectName("TopAccentButton")
        account_layout.addWidget(self.btn_save_account, 0, Qt.AlignLeft)
        content_layout.addWidget(account_card)

        ui_card = QFrame()
        ui_card.setObjectName("SectionCard")
        ui_layout = QVBoxLayout(ui_card)
        ui_layout.setContentsMargins(12, 12, 12, 12)
        ui_layout.setSpacing(6)
        ui_layout.addWidget(components.section_header("Interface", "Theme, density, motion, and performance"))
        self.cmb_appearance = QComboBox()
        for label, value in (("System", "system"), ("Light", "light"), ("Dark", "dark"), ("Palette / scheduled", "palette")):
            self.cmb_appearance.addItem(label, value)
        self.cmb_appearance.setAccessibleName("Appearance mode")
        self.cmb_density = QComboBox()
        self.cmb_density.addItems(["compact", "comfortable", "tablet"])
        self.cmb_motion = QComboBox()
        for label, value in (("System", "system"), ("Reduce", "reduce"), ("Allow", "allow")):
            self.cmb_motion.addItem(label, value)
        self.cmb_motion.setToolTip(
            "System follows Windows' reduced-animation setting when available. "
            "Reduce disables Mei's nonessential motion; Allow keeps it on."
        )
        self.cmb_theme = QComboBox()
        # Pretty display names + a live color swatch per entry (a bare key
        # list like 'sand-day' told users nothing about the vibe).
        self._theme_ids = []
        for mode_id in sorted(theme.PALETTES.keys()):
            pal = theme._palette(mode_id, None)
            self.cmb_theme.addItem(theme.theme_display_name(mode_id))
            self._theme_ids.append(mode_id)
            pixmap = QPixmap(34, 18)
            pixmap.fill(QColor(pal["CARD_BG"]))
            painter = QPainter(pixmap)
            painter.setPen(QPen(QColor(pal["BORDER_SOFT"]), 1))
            painter.drawRect(0, 0, 33, 17)
            painter.setBrush(QColor(pal["ACCENT"]))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(3, 4, 12, 10, 2, 2)
            painter.setBrush(QColor(pal["MAIN_BG_ALT"]))
            painter.drawRoundedRect(18, 4, 12, 10, 2, 2)
            painter.end()
            self.cmb_theme.setItemIcon(self.cmb_theme.count() - 1, QIcon(pixmap))
        self.cmb_accent = QComboBox()
        for accent_id in sorted(theme.ACCENTS.keys()):
            self.cmb_accent.addItem(theme.accent_display_name(accent_id), accent_id)
            pixmap = QPixmap(24, 18)
            pixmap.fill(QColor("transparent"))
            painter = QPainter(pixmap)
            painter.setPen(QPen(QColor(theme._palette(theme.DEFAULT_THEME, None)["BORDER_SOFT"]), 1))
            painter.setBrush(QColor(theme.ACCENTS[accent_id][0]))
            painter.drawRoundedRect(3, 3, 18, 12, 4, 4)
            painter.end()
            self.cmb_accent.setItemIcon(self.cmb_accent.count() - 1, QIcon(pixmap))
        self.btn_custom_accent = ghost_button("Custom accent…", "Choose any accent color; text contrast adapts automatically")
        self.btn_custom_accent.clicked.connect(self._choose_custom_accent)
        self.spin_max_live_tabs = QSpinBox()
        self.spin_max_live_tabs.setRange(1, 32)
        self.spin_max_live_tabs.setToolTip("Fewer live tabs = lighter RAM/CPU when hundreds of tabs are open.")
        self.chk_auto_theme = QCheckBox("Day / night schedule (06:00–18:00)")
        self.chk_auto_theme.setToolTip(
            "On: day palettes from 6:00 to 18:00, their night siblings otherwise.\n"
            "Pairs: Latte Cream ↔ Midnight Mocha, Sakura ↔ Ember Night, Matcha ↔ Matcha Night..."
        )
        controls_grid = QGridLayout()
        controls_grid.setContentsMargins(0, 0, 0, 0)
        controls_grid.setHorizontalSpacing(10)
        controls_grid.setVerticalSpacing(5)
        for column, (label, control) in enumerate(
            (
                ("Appearance", self.cmb_appearance),
                ("Palette family", self.cmb_theme),
                ("Accent", self.cmb_accent),
                ("Density", self.cmb_density),
                ("Motion", self.cmb_motion),
                ("Live tab limit", self.spin_max_live_tabs),
            )
        ):
            field = QWidget()
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(4)
            field_label = QLabel(label)
            field_label.setObjectName("MutedLabel")
            field_layout.addWidget(field_label)
            field_layout.addWidget(control)
            control.setAccessibleName(label)
            control.setMinimumWidth(0)
            control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            controls_grid.addWidget(field, column // 2, column % 2)
            controls_grid.setColumnStretch(column % 2, 1)
        ui_layout.addLayout(controls_grid)
        ui_layout.addWidget(self.btn_custom_accent, 0, Qt.AlignLeft)
        ui_layout.addWidget(self.chk_auto_theme)
        self.cmb_appearance.currentIndexChanged.connect(lambda: self.chk_auto_theme.setEnabled(self.cmb_appearance.currentData() == "palette"))
        self.btn_save_ui = QPushButton("Apply UI preferences")
        self.btn_save_ui.setObjectName("TopAccentButton")
        ui_layout.addWidget(self.btn_save_ui, 0, Qt.AlignLeft)
        content_layout.addWidget(ui_card)

        extras_card = QFrame()
        extras_card.setObjectName("SectionCard")
        extras_layout = QVBoxLayout(extras_card)
        extras_layout.setContentsMargins(12, 12, 12, 12)
        extras_layout.setSpacing(6)
        extras_layout.addWidget(components.section_header("Interface extras", "Little touches you can turn on or off"))
        self.chk_new_tab_steam = QCheckBox("Animated steam on the new-tab café cup")
        self.chk_new_tab_greeting = QCheckBox("Café time-greeting on the new-tab hero")
        self.chk_show_brief = QCheckBox("Show Morning Brief card on Home")
        self.chk_shield = QCheckBox("🛡 Distraction Shield — always block social/autoplay hosts (also auto-on during focus pours)")
        extras_layout.addWidget(self.chk_new_tab_steam)
        extras_layout.addWidget(self.chk_new_tab_greeting)
        extras_layout.addWidget(self.chk_show_brief)
        extras_layout.addWidget(self.chk_shield)
        content_layout.addWidget(extras_card)

        # The loop, out loud: the shell can start the next step instead of only
        # answering when the Home card is opened.
        study_card = QFrame()
        study_card.setObjectName("SectionCard")
        study_layout = QVBoxLayout(study_card)
        study_layout.setContentsMargins(12, 12, 12, 12)
        study_layout.setSpacing(6)
        study_layout.addWidget(
            components.section_header("Study reminders", "Mei tells you the next step instead of waiting to be asked")
        )
        reminder_help = QLabel(
            "A native toast with the loop's next step — an overdue deadline, cards that are due, "
            "or a day with nothing poured. Quiet from 22:00 to 08:00, and never while a pour is running."
        )
        reminder_help.setWordWrap(True)
        reminder_help.setObjectName("MutedLabel")
        study_layout.addWidget(reminder_help)
        self.cmb_study_reminder = QComboBox()
        for label, minutes in (
            ("Off", 0),
            ("At most every 30 minutes", 30),
            ("At most every hour", 60),
            ("At most every 2 hours", 120),
            ("At most every 4 hours", 240),
            ("At most every 8 hours", 480),
        ):
            self.cmb_study_reminder.addItem(label, minutes)
        self.cmb_study_reminder.setToolTip("How often Mei may start a nudge for the current next step")
        self.cmb_study_reminder.currentIndexChanged.connect(self._save_study_reminder)
        study_layout.addWidget(self.cmb_study_reminder)
        content_layout.addWidget(study_card)

        google_card = QFrame()
        google_card.setObjectName("SectionCard")
        google_layout = QVBoxLayout(google_card)
        google_layout.setContentsMargins(12, 12, 12, 12)
        google_layout.setSpacing(6)
        google_layout.addWidget(
            components.section_header("Google account", "Device-code sign-in — no password ever reaches Mei")
        )
        self.lbl_google_status = QLabel("")
        self.lbl_google_status.setWordWrap(True)
        self.lbl_google_status.setObjectName("MutedLabel")
        google_layout.addWidget(self.lbl_google_status)
        # Four equal boxes became: the verb you came for, the token check beside
        # it, and one menu holding the setup and the sign-out.
        google_row = QHBoxLayout()
        self.btn_google_sign_in = primary_button("Sign in with Google")
        self.btn_google_verify = ghost_button("Verify token", "Re-check the cached access token")
        # The card's occasional verbs (the client ID, the sign-out) live in one
        # menu; its sign-out action is kept by name so refresh() can grey it out
        # — a session with no account has nothing to sign out of.
        self.btn_google_more = more_menu(
            (
                ("Set the client ID…", self._set_google_client_id),
                (None, None),
                ("Sign out of Google", self._google_sign_out),
            ),
            tooltip="Google account chores",
        )
        self.google_sign_out_action = menu_action(self.btn_google_more, "Sign out of Google")
        google_row.addWidget(self.btn_google_sign_in)
        google_row.addWidget(self.btn_google_more)
        google_row.addWidget(self.btn_google_verify)
        google_row.addStretch(1)
        google_layout.addLayout(google_row)
        content_layout.addWidget(google_card)

        security_card = QFrame()
        security_card.setObjectName("SectionCard")
        security_layout = QVBoxLayout(security_card)
        security_layout.setContentsMargins(12, 12, 12, 12)
        security_layout.setSpacing(6)
        security_layout.addWidget(
            components.section_header("Passcode lock", "Personal and AI ask for the passcode once per session")
        )
        self.lbl_lock_status = QLabel("")
        self.lbl_lock_status.setWordWrap(True)
        self.lbl_lock_status.setObjectName("MutedLabel")
        security_layout.addWidget(self.lbl_lock_status)
        self.btn_lock_now = ghost_button("Lock now", "Re-lock Personal and AI without restarting Mei")
        security_layout.addWidget(self.btn_lock_now, 0, Qt.AlignLeft)
        self.lbl_secret_status = QLabel("")
        self.lbl_secret_status.setWordWrap(True)
        self.lbl_secret_status.setObjectName("MutedLabel")
        self.lbl_secret_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        security_layout.addWidget(self.lbl_secret_status)
        content_layout.addWidget(security_card)

        monitors_card = QFrame()
        monitors_card.setObjectName("SectionCard")
        monitors_layout = QVBoxLayout(monitors_card)
        monitors_layout.setContentsMargins(12, 12, 12, 12)
        monitors_layout.setSpacing(6)
        monitors_layout.addWidget(
            components.section_header("Watched pages", "One toast when a watched page changes (~every 15 min)")
        )
        self.monitors_list = QListWidget()
        self.monitors_list.setObjectName("CafeList")
        self.monitors_list.setMaximumHeight(150)
        monitors_layout.addWidget(self.monitors_list)
        self.btn_monitor_remove = ghost_button("Stop watching selected", "Remove the highlighted page from the watch list")
        monitors_layout.addWidget(self.btn_monitor_remove, 0, Qt.AlignLeft)
        content_layout.addWidget(monitors_card)

        sync_card = QFrame()
        sync_card.setObjectName("SectionCard")
        sync_layout = QVBoxLayout(sync_card)
        sync_layout.setContentsMargins(12, 12, 12, 12)
        sync_layout.setSpacing(6)
        sync_layout.addWidget(components.section_header("Self-hosted sync", "Push / pull your profile to your own endpoint"))
        sync_help = QLabel(
            "Point both machines at the same HTTP endpoint (a tiny API you run — see README). "
            "Data travels with a Bearer token; nothing is sent to any cloud."
        )
        sync_help.setWordWrap(True)
        sync_help.setObjectName("MutedLabel")
        sync_layout.addWidget(sync_help)
        self.chk_sync_enabled = QCheckBox("Enable sync")
        sync_layout.addWidget(self.chk_sync_enabled)
        sync_layout.addWidget(QLabel("Endpoint (e.g. http://192.168.1.10:8901)"))
        self.ed_sync_endpoint = QLineEdit()
        self.ed_sync_endpoint.setPlaceholderText("http://127.0.0.1:8901")
        sync_layout.addWidget(self.ed_sync_endpoint)
        sync_layout.addWidget(QLabel("Bearer token"))
        self.ed_sync_token = QLineEdit()
        self.ed_sync_token.setPlaceholderText("Shared secret")
        self.ed_sync_token.setEchoMode(QLineEdit.Password)
        sync_layout.addWidget(self.ed_sync_token)
        sync_row = QHBoxLayout()
        self.btn_sync_now = QPushButton("Sync now (push + pull)")
        self.btn_save_sync = QPushButton("Save sync settings")
        self.btn_save_sync.setObjectName("TopAccentButton")
        sync_row.addWidget(self.btn_sync_now)
        sync_row.addWidget(self.btn_save_sync)
        sync_row.addStretch(1)
        sync_layout.addLayout(sync_row)
        self.lbl_sync_status = QLabel("")
        self.lbl_sync_status.setWordWrap(True)
        self.lbl_sync_status.setObjectName("MutedLabel")
        sync_layout.addWidget(self.lbl_sync_status)
        content_layout.addWidget(sync_card)

        mobile_card = QFrame()
        mobile_card.setObjectName("SectionCard")
        mobile_layout = QVBoxLayout(mobile_card)
        mobile_layout.setContentsMargins(12, 12, 12, 12)
        mobile_layout.setSpacing(6)
        mobile_layout.addWidget(
            components.section_header("Mobile / Android bridge", "Phone ↔ desktop sync over HTTP + JSON")
        )
        mobile_help = QLabel(
            "Loopback mode is reachable only from this PC. “Listen on LAN” opens the bridge to "
            "your Wi‑Fi/LAN using unencrypted HTTP: anyone who can capture traffic or read the "
            "token can act as a paired device. Enable it only on a network you trust (or through "
            "a VPN), and use your PC’s IPv4 in the app (e.g. 192.168.x.x)."
        )
        mobile_help.setWordWrap(True)
        mobile_help.setObjectName("MutedLabel")
        mobile_layout.addWidget(mobile_help)
        self.chk_mobile_bridge = QCheckBox("Enable mobile bridge receiver")
        mobile_layout.addWidget(self.chk_mobile_bridge)
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port"))
        self.spin_mobile_port = QSpinBox()
        self.spin_mobile_port.setRange(1, 65535)
        self.spin_mobile_port.setValue(prefs.MOBILE_BRIDGE_DEFAULT_PORT)
        port_row.addWidget(self.spin_mobile_port)
        port_row.addStretch(1)
        mobile_layout.addLayout(port_row)
        self.chk_mobile_lan = QCheckBox("Listen on LAN (0.0.0.0 — reachable from Wi‑Fi devices)")
        mobile_layout.addWidget(self.chk_mobile_lan)
        mobile_layout.addWidget(QLabel("Shared token (Bearer)"))
        self.ed_mobile_token = QLineEdit()
        self.ed_mobile_token.setPlaceholderText("Paste token or generate below")
        mobile_layout.addWidget(self.ed_mobile_token)
        self.lbl_mobile_status = QLabel("")
        self.lbl_mobile_status.setWordWrap(True)
        self.lbl_mobile_status.setObjectName("MutedLabel")
        self.lbl_mobile_status.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lbl_mobile_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_mobile_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.lbl_mobile_status.setMinimumHeight(76)
        mobile_layout.addWidget(self.lbl_mobile_status)
        mobile_layout.addSpacing(4)
        token_row = QHBoxLayout()
        self.btn_mobile_token_gen = QPushButton("Generate token")
        self.btn_save_mobile = QPushButton("Save mobile bridge settings")
        self.btn_save_mobile.setObjectName("TopAccentButton")
        token_row.addWidget(self.btn_mobile_token_gen)
        token_row.addWidget(self.btn_save_mobile)
        token_row.addStretch(1)
        mobile_layout.addLayout(token_row)

        mobile_layout.addSpacing(6)
        mobile_layout.addWidget(
            components.section_header("Quick pairing", "Scan with Mei Remote, or paste the code into the Mei Bridge extension")
        )
        self.btn_copy_pairing = QPushButton("Copy pairing code")
        self.btn_copy_pairing.setObjectName("TopAccentButton")
        mobile_layout.addWidget(self.btn_copy_pairing, 0, Qt.AlignLeft)
        self.lbl_pairing_code = QLabel("")
        self.lbl_pairing_code.setObjectName("MutedLabel")
        self.lbl_pairing_code.setWordWrap(True)
        self.lbl_pairing_code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mobile_layout.addWidget(self.lbl_pairing_code)
        self.lbl_pairing_qr = QLabel()
        self.lbl_pairing_qr.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lbl_pairing_qr.setMinimumSize(220, 220)
        mobile_layout.addWidget(self.lbl_pairing_qr)
        content_layout.addWidget(mobile_card)

        backup_card = QFrame()
        backup_card.setObjectName("SectionCard")
        backup_layout = QVBoxLayout(backup_card)
        backup_layout.setContentsMargins(12, 12, 12, 12)
        backup_layout.setSpacing(6)
        backup_layout.addWidget(components.section_header("Data location & backup", "Where your profile lives"))
        self.lbl_backup_paths = QLabel("")
        self.lbl_backup_paths.setWordWrap(True)
        self.lbl_backup_paths.setObjectName("MutedLabel")
        self.lbl_backup_paths.setTextInteractionFlags(Qt.TextSelectableByMouse)
        backup_layout.addWidget(self.lbl_backup_paths)
        backup_hint = QLabel(
            "Use History → Export backup: .zip with profile.json + vault/; tick “Include BrowserData” "
            "there to pack WebEngine state in the same zip."
        )
        backup_hint.setWordWrap(True)
        backup_hint.setObjectName("MutedLabel")
        backup_layout.addWidget(backup_hint)
        open_row = QHBoxLayout()
        self.btn_open_profile_folder = QPushButton("Open profile folder")
        self.btn_open_data_folder = QPushButton("Open runtime data folder")
        open_row.addWidget(self.btn_open_profile_folder)
        open_row.addWidget(self.btn_open_data_folder)
        open_row.addStretch(1)
        backup_layout.addLayout(open_row)
        content_layout.addWidget(backup_card)

        guide_card = QFrame()
        guide_card.setObjectName("SectionCard")
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setContentsMargins(12, 12, 12, 12)
        guide_layout.setSpacing(6)
        guide_layout.addWidget(components.section_header("Help & Browser Tools", "Consolidated help panel"))
        guide_copy = QLabel("Open one consolidated help panel for shell commands, browser tools, AI workflow, and Personal Hub usage.")
        guide_copy.setWordWrap(True)
        guide_copy.setObjectName("MutedLabel")
        guide_layout.addWidget(guide_copy)
        self.btn_open_help_tools = QPushButton("Open help & browser tools")
        guide_layout.addWidget(self.btn_open_help_tools, 0, Qt.AlignLeft)
        content_layout.addWidget(guide_card)

        updates_card = QFrame()
        updates_card.setObjectName("SectionCard")
        updates_layout = QVBoxLayout(updates_card)
        updates_layout.setContentsMargins(12, 12, 12, 12)
        updates_layout.setSpacing(6)
        updates_layout.addWidget(components.section_header("App Updates", "Compare your installed build"))
        self.lbl_app_version = QLabel("")
        self.lbl_app_version.setObjectName("MutedLabel")
        updates_layout.addWidget(self.lbl_app_version)
        self.lbl_update_status = QLabel("Check for updates to compare your installed build with the latest published release.")
        self.lbl_update_status.setWordWrap(True)
        self.lbl_update_status.setObjectName("MutedLabel")
        updates_layout.addWidget(self.lbl_update_status)
        self.btn_check_updates = primary_button("Check for updates")
        self.btn_install_update = ghost_button("Download and install update")
        self.btn_open_release_page = quiet_button("Open release page")
        update_actions = QHBoxLayout()
        update_actions.addWidget(self.btn_check_updates)
        update_actions.addWidget(self.btn_install_update)
        update_actions.addWidget(self.btn_open_release_page)
        update_actions.addStretch(1)
        updates_layout.addLayout(update_actions)
        content_layout.addWidget(updates_card)

        folder_card = QFrame()
        folder_card.setObjectName("SectionCard")
        folder_layout = QVBoxLayout(folder_card)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(6)
        folder_layout.addWidget(
            components.section_header("Folder sync", "Two machines, one folder you own")
        )
        folder_copy = QLabel(
            "Pick a folder you already have — OneDrive, a network share, Syncthing — and Mei keeps "
            "your notes, plan, deck, tasks and saved pages in step through it. No account, no server. "
            "Merging is per record against the last agreed state, a delete travels only when the other "
            "machine did not edit since, and anything ambiguous keeps both copies. Preview first: it "
            "writes nothing. Browser history, bookmarks, cookies and passwords never travel."
        )
        folder_copy.setWordWrap(True)
        folder_copy.setObjectName("MutedLabel")
        folder_layout.addWidget(folder_copy)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.lbl_sync_folder = QLabel("No folder chosen")
        self.lbl_sync_folder.setObjectName("MutedLabel")
        self.lbl_sync_folder.setWordWrap(True)
        folder_row.addWidget(self.lbl_sync_folder, 1)
        self.btn_choose_sync_folder = ghost_button("Choose folder…")
        self.btn_clear_sync_folder = quiet_button("Turn off")
        folder_row.addWidget(self.btn_choose_sync_folder)
        folder_row.addWidget(self.btn_clear_sync_folder)
        folder_layout.addLayout(folder_row)
        folder_actions = QHBoxLayout()
        folder_actions.setSpacing(8)
        self.btn_preview_sync = ghost_button("Preview", "Show what a sync would change — writes nothing")
        self.btn_apply_sync = primary_button("Sync now", "Merge with the folder (a snapshot is taken first)")
        folder_actions.addWidget(self.btn_preview_sync)
        folder_actions.addWidget(self.btn_apply_sync)
        folder_actions.addStretch(1)
        folder_layout.addLayout(folder_actions)
        self.lbl_sync_status = QLabel("")
        self.lbl_sync_status.setObjectName("MutedLabel")
        self.lbl_sync_status.setWordWrap(True)
        folder_layout.addWidget(self.lbl_sync_status)
        content_layout.addWidget(folder_card)

        plugins_card = QFrame()
        plugins_card.setObjectName("SectionCard")
        plugins_layout = QVBoxLayout(plugins_card)
        plugins_layout.setContentsMargins(12, 12, 12, 12)
        plugins_layout.setSpacing(6)
        plugins_layout.addWidget(
            components.section_header("Plugins", "Doors for other apps — declared, never executed")
        )
        plugins_copy = QLabel(
            "A plugin is a JSON manifest, not a program: it says which store it reads or writes and "
            "Mei does the work, so there is no code to sandbox and nothing to trust. Drop a folder "
            "with plugin.json into your plugins directory to add one (CSV import/export in API 1)."
        )
        plugins_copy.setWordWrap(True)
        plugins_copy.setObjectName("MutedLabel")
        plugins_layout.addWidget(plugins_copy)
        self.plugins_list = QListWidget()
        self.plugins_list.setObjectName("CafeList")
        self.plugins_list.setMaximumHeight(120)
        self.plugins_list.setToolTip("Select a plugin, then run it")
        plugins_layout.addWidget(self.plugins_list)
        plugins_actions = QHBoxLayout()
        plugins_actions.setSpacing(8)
        self.btn_run_plugin = primary_button("Run…", "Import a file, or export one, with the selected plugin")
        self.btn_open_plugins_folder = ghost_button("Open plugins folder", "Where your own manifest folders live")
        plugins_actions.addWidget(self.btn_run_plugin)
        plugins_actions.addWidget(self.btn_open_plugins_folder)
        plugins_actions.addStretch(1)
        plugins_layout.addLayout(plugins_actions)
        self.lbl_plugin_problems = QLabel("")
        self.lbl_plugin_problems.setObjectName("MutedLabel")
        self.lbl_plugin_problems.setWordWrap(True)
        plugins_layout.addWidget(self.lbl_plugin_problems)
        content_layout.addWidget(plugins_card)

        diagnostics_card = QFrame()
        diagnostics_card.setObjectName("SectionCard")
        diag_layout = QVBoxLayout(diagnostics_card)
        diag_layout.setContentsMargins(12, 12, 12, 12)
        diag_layout.setSpacing(6)
        diag_layout.addWidget(
            components.section_header("Diagnostics", "Evidence for a bug report")
        )
        diag_copy = QLabel(
            "Pack the log tail, the version of every component and the size/schema of each store "
            "into one zip. Note text, passwords, vault files and browsing history are never included."
        )
        diag_copy.setWordWrap(True)
        diag_copy.setObjectName("MutedLabel")
        diag_layout.addWidget(diag_copy)
        # The engine is the product surface of a browser and it was invisible
        # here: everything else in this card was only readable inside the zip.
        self.lbl_engine = QLabel("")
        self.lbl_engine.setObjectName("MutedLabel")
        self.lbl_engine.setWordWrap(True)
        diag_layout.addWidget(self.lbl_engine)
        self.btn_export_diagnostics = primary_button("Export diagnostics zip")
        self.btn_open_log_folder = ghost_button("Open log folder", "Where mei.log lives")
        diag_actions = QHBoxLayout()
        diag_actions.addWidget(self.btn_export_diagnostics)
        diag_actions.addWidget(self.btn_open_log_folder)
        diag_actions.addStretch(1)
        diag_layout.addLayout(diag_actions)
        content_layout.addWidget(diagnostics_card)
        content_layout.addStretch(1)

        self.btn_save_account.clicked.connect(self.save_account)
        self.btn_save_ui.clicked.connect(self.save_ui)
        self.btn_sync_now.clicked.connect(self.sync_now)
        self.btn_save_sync.clicked.connect(self.save_sync)
        self.btn_mobile_token_gen.clicked.connect(self._generate_mobile_token)
        self.btn_save_mobile.clicked.connect(self.save_mobile_bridge)
        self.btn_copy_pairing.clicked.connect(self._copy_pairing)
        self.btn_google_sign_in.clicked.connect(self._google_sign_in)
        self.btn_google_verify.clicked.connect(self._google_verify)
        self.btn_lock_now.clicked.connect(self._lock_now)
        self.btn_monitor_remove.clicked.connect(self._remove_monitor)
        self.btn_open_help_tools.clicked.connect(lambda: dialogs.show_browser_control_center(self.shell.browser_page))
        self.btn_check_updates.clicked.connect(lambda: self.shell.run_update_check(manual=True))
        self.btn_install_update.clicked.connect(self.shell.install_available_update)
        self.btn_open_release_page.clicked.connect(lambda: self.shell.open_release_page())
        self.btn_export_diagnostics.clicked.connect(self._export_diagnostics)
        self.btn_choose_sync_folder.clicked.connect(self._choose_sync_folder)
        self.btn_clear_sync_folder.clicked.connect(self._clear_sync_folder)
        self.btn_preview_sync.clicked.connect(self._preview_sync)
        self.btn_apply_sync.clicked.connect(self._apply_sync)
        self.btn_run_plugin.clicked.connect(self._run_selected_plugin)
        self.btn_open_plugins_folder.clicked.connect(self._open_plugins_folder)
        self.btn_open_log_folder.clicked.connect(self._open_log_folder)
        self.btn_open_profile_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.shell.profile_dir))
        )
        self.btn_open_data_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(app_paths.data_root(self.shell.app_dir)))
        )
        # Paint the folder and plugin cards once at build time, so a profile
        # without a folder cannot show an enabled "Sync now" for a sync that has
        # nowhere to go, and the plugin list is never empty-but-claimed.
        self._refresh_folder_sync()
        self._refresh_plugins()
        self._refresh_engine_notice()
        # Keep all capabilities, but show one focused settings category at a time.
        groups = {
            "Appearance": (ui_card, extras_card, study_card),
            "Account & privacy": (account_card, google_card, security_card),
            "Sync & devices": (sync_card, mobile_card),
        }
        assigned = {card for cards in groups.values() for card in cards}
        groups["Tools & maintenance"] = tuple(content_layout.itemAt(i).widget() for i in range(content_layout.count()) if content_layout.itemAt(i).widget() and content_layout.itemAt(i).widget() not in assigned)
        self._settings_groups = groups
        self.cmb_settings_section = QComboBox()
        self.cmb_settings_section.addItems(groups.keys())
        self.cmb_settings_section.setAccessibleName("Settings category")
        layout.insertWidget(1, self.cmb_settings_section)
        self.cmb_settings_section.currentTextChanged.connect(self._show_settings_section)
        self._show_settings_section(self.cmb_settings_section.currentText())
        self._form_baseline = {}

    def _show_settings_section(self, section):
        for name, cards in self._settings_groups.items():
            for card in cards:
                card.setVisible(name == section)
        self.settings_scroll.verticalScrollBar().setValue(0)

    def _choose_custom_accent(self):
        current = self.cmb_accent.currentData() or "brass"
        value = current if str(current).startswith("#") else theme.ACCENTS[current][0]
        color = QColorDialog.getColor(QColor(value), self, "Custom accent")
        if color.isValid():
            index = self.cmb_accent.findData(color.name())
            if index < 0:
                pixmap = QPixmap(24, 18)
                pixmap.fill(color)
                self.cmb_accent.addItem(QIcon(pixmap), color.name().upper(), color.name())
                index = self.cmb_accent.count() - 1
            self.cmb_accent.setCurrentIndex(index)

    def _form_values(self):
        result = {}
        for widget in self.findChildren((QLineEdit, QComboBox, QCheckBox, QSpinBox)):
            if widget is getattr(self, "cmb_settings_section", None):
                continue
            if isinstance(widget, QLineEdit):
                result[widget] = widget.text()
            elif isinstance(widget, QComboBox):
                result[widget] = widget.currentIndex()
            elif isinstance(widget, QCheckBox):
                result[widget] = widget.isChecked()
            else:
                result[widget] = widget.value()
        return result

    def refresh(self):
        values = self._form_values()
        drafts = {w: value for w, value in values.items() if w in self._form_baseline and value != self._form_baseline[w]}
        account = life_service.load_sync_account(self.shell.profile_dir)
        state = life_service.load_sync_state(self.shell.profile_dir)
        prefs_data = prefs.load_prefs(self.shell.profile_dir)
        self.ed_display_name.setText(account.get("display_name", ""))
        self.ed_email.setText(account.get("email", ""))
        self.chk_local_snapshot.setChecked(bool(state.get("enabled")))
        display_name = (account.get("display_name") or "").strip()
        email = (account.get("email") or "").strip()
        identity = display_name or email or "Mei user"
        initials = "".join(part[0] for part in identity.replace("@", " ").split()[:2]).upper() or "LB"
        self.lbl_account_initial.setText(initials[:2])
        self.lbl_account_summary.setText(identity)
        sync_label = "Local snapshot enabled" if state.get("enabled") else "Stored locally on this device"
        self.lbl_account_detail.setText(sync_label)
        self.lbl_settings_profile.setText("LOCAL SNAPSHOT" if state.get("enabled") else "LOCAL PROFILE")
        density = prefs_data.get("shell_density", "comfortable")
        theme_name = prefs_data.get("shell_theme", theme.DEFAULT_THEME)
        accent = prefs_data.get("accent", "brass")
        idx = self.cmb_density.findText(density)
        if idx >= 0:
            self.cmb_density.setCurrentIndex(idx)
        motion_idx = self.cmb_motion.findData(prefs_data.get("reduced_motion", "system"))
        self.cmb_motion.setCurrentIndex(max(0, motion_idx))
        # Theme/accent combos store pretty labels; map back through ids.
        try:
            theme_idx = self._theme_ids.index(theme_name)
            self.cmb_theme.setCurrentIndex(theme_idx)
        except (ValueError, AttributeError):
            pass
        appearance = prefs_data.get("appearance_mode", "palette")
        self.cmb_appearance.setCurrentIndex(max(0, self.cmb_appearance.findData(appearance)))
        accent_id = accent if theme.valid_accent(accent) else "brass"
        accent_idx = self.cmb_accent.findData(accent_id)
        if accent_idx < 0 and str(accent_id).startswith("#"):
            pixmap = QPixmap(24, 18)
            pixmap.fill(QColor(accent_id))
            self.cmb_accent.addItem(QIcon(pixmap), accent_id.upper(), accent_id)
            accent_idx = self.cmb_accent.count() - 1
        if accent_idx >= 0:
            self.cmb_accent.setCurrentIndex(accent_idx)
        self.spin_max_live_tabs.setValue(prefs.get_max_live_tabs(self.shell.profile_dir))
        self.chk_new_tab_steam.setChecked(prefs.get_new_tab_steam(self.shell.profile_dir))
        self.chk_new_tab_greeting.setChecked(prefs.get_new_tab_greeting(self.shell.profile_dir))
        self.chk_show_brief.setChecked(prefs.get_show_morning_brief(self.shell.profile_dir))
        self.chk_shield.setChecked(prefs.get_pref(self.shell.profile_dir, "shield_always_on", False))
        self.chk_auto_theme.setChecked(prefs.get_auto_theme(self.shell.profile_dir))
        self._load_study_reminder()
        self._refresh_google()
        self._refresh_security()
        self._refresh_monitors()
        self._refresh_folder_sync()
        self._refresh_plugins()
        self._refresh_engine_notice()
        self.chk_sync_enabled.setChecked(prefs.get_sync_enabled(self.shell.profile_dir))
        self.ed_sync_endpoint.setText(prefs.get_sync_endpoint(self.shell.profile_dir))
        self.ed_sync_token.setText(prefs.get_sync_token(self.shell.profile_dir))
        self._refresh_sync_status()
        self.lbl_app_version.setText(f"Installed version: {app_version.APP_VERSION}")
        self.lbl_update_status.setText(self.shell.update_status_text)
        self.btn_install_update.setEnabled(bool(getattr(self.shell, "_pending_update_info", None) and self.shell._pending_update_info.has_update))
        self.chk_mobile_bridge.setChecked(prefs.get_mobile_bridge_enabled(self.shell.profile_dir))
        self.spin_mobile_port.setValue(prefs.get_mobile_bridge_port(self.shell.profile_dir))
        self.chk_mobile_lan.setChecked(prefs.get_mobile_bridge_lan(self.shell.profile_dir))
        self.ed_mobile_token.setText(prefs.get_mobile_bridge_token(self.shell.profile_dir))
        self._refresh_mobile_bridge_status()
        self._refresh_pairing()
        profiles_root = app_paths.profiles_root(self.shell.app_dir)
        data_root = app_paths.data_root(self.shell.app_dir)
        self.lbl_backup_paths.setText(
            f"Active profile (notes, prefs, SafeVault, BrowserData, sessions):\n{self.shell.profile_dir}\n\n"
            f"Profiles root:\n{profiles_root}\n\n"            f"Runtime data root:\n{data_root}"
        )
        self._form_baseline = self._form_values()
        for widget, value in drafts.items():
            widget.blockSignals(True)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            else:
                widget.setValue(value)
            widget.blockSignals(False)
        self.chk_auto_theme.setEnabled(self.cmb_appearance.currentData() == "palette")

    # -- study reminders, Google account, passcode lock, watched pages -------
    def _load_study_reminder(self):
        minutes = prefs.get_study_reminder_minutes(self.shell.profile_dir)
        index = self.cmb_study_reminder.findData(minutes)
        # Loading must not look like the user choosing: the combo writes prefs.
        self.cmb_study_reminder.blockSignals(True)
        self.cmb_study_reminder.setCurrentIndex(index if index >= 0 else self.cmb_study_reminder.findData(120))
        self.cmb_study_reminder.blockSignals(False)

    def _save_study_reminder(self, _index: int = 0):
        prefs.set_study_reminder_minutes(self.shell.profile_dir, self.cmb_study_reminder.currentData() or 0)

    def _google_client_id(self) -> str:
        stored = prefs.get_google_oauth_client_id(self.shell.profile_dir)
        return (stored or os.environ.get("LITEBROWSER_GOOGLE_CLIENT_ID", "")).strip()

    def _set_google_client_id(self):
        current = prefs.get_google_oauth_client_id(self.shell.profile_dir)
        value, ok = QInputDialog.getText(
            self,
            "Google OAuth",
            "OAuth client ID (a 'Desktop app' id from Google Cloud Console,\nending in .apps.googleusercontent.com):",
            text=current,
        )
        if not ok:
            return ""
        client_id = (value or "").strip()
        prefs.set_google_oauth_client_id(self.shell.profile_dir, client_id)
        self._refresh_google()
        return client_id

    def _log_dir(self) -> str:
        return os.path.join(app_paths.data_root(self.shell.app_dir), "logs")

    def _export_diagnostics(self):
        """Write the support bundle where the user asks, then say what it holds.

        The dialog names the exclusions on purpose: a person attaching a file to a
        public issue should know what is *not* in it before they send it.
        """
        # The profile's own downloads folder, not QStandardPaths: Qt 5 and Qt 6
        # spell that enum differently (`DownloadLocation` vs
        # `StandardLocation.DownloadLocation`) and this page runs on both.
        suggested = os.path.join(
            app_paths.downloads_dir(self.shell.profile_dir), diagnostics.default_bundle_name()
        )
        path, _selected = QFileDialog.getSaveFileName(
            self, "Save diagnostics bundle", suggested, "Zip archive (*.zip)"
        )
        if not path:
            return
        try:
            result = diagnostics.build_bundle(
                self.shell.profile_dir, path, app_dir=self.shell.app_dir, ui=_ui_versions()
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the page
            QMessageBox.warning(self, "Diagnostics", f"Could not write the bundle:\n{exc}")
            return
        size_kb = max(1, result["bytes"] // 1024)
        QMessageBox.information(
            self,
            "Diagnostics",
            f"Wrote {os.path.basename(result['path'])} ({size_kb} KB, {len(result['members'])} files).\n\n"
            "It holds the log tail, the component versions and the shape of your stores — "
            "no note text, no passwords, no browsing history. Read the log inside it if you "
            "had private pages open: Mei logs page titles at debug level.",
        )

    def _refresh_folder_sync(self):
        """Paint the folder card from the service's own status."""
        state = sync_folder.status(self.shell.profile_dir)
        if getattr(self, "_folder_sync_running", False):
            for button in (self.btn_apply_sync, self.btn_preview_sync, self.btn_choose_sync_folder, self.btn_clear_sync_folder):
                button.setEnabled(False)
            return
        if not state["enabled"]:
            self.lbl_sync_folder.setText("No folder chosen")
            self.lbl_sync_status.setText("")
            self.btn_preview_sync.setEnabled(False)
            self.btn_apply_sync.setEnabled(False)
            self.btn_clear_sync_folder.setEnabled(False)
            return
        folder = state["folder"]
        self.lbl_sync_folder.setText(folder)
        self.lbl_sync_folder.setToolTip(folder)
        self.btn_preview_sync.setEnabled(True)
        self.btn_apply_sync.setEnabled(True)
        self.btn_clear_sync_folder.setEnabled(True)
        bits = []
        if not state["folder_exists"]:
            bits.append("that folder is not reachable right now")
        elif state["payload_exists"]:
            bits.append("a sync file is already there")
        else:
            bits.append("the sync file will be written on the first sync")
        if state["last_sync"]:
            bits.append(f"last merged {state['last_sync']}")
        bits.append(f"{state['tracked_records']} record(s) tracked")
        self.lbl_sync_status.setText(" · ".join(bits))

    def _choose_sync_folder(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose the folder Mei syncs through", self.lbl_sync_folder.text() or ""
        )
        if not chosen:
            return
        try:
            sync_folder.set_folder(self.shell.profile_dir, chosen)
        except OSError as exc:  # noqa: BLE001 - report, never crash the page
            QMessageBox.warning(self, "Folder sync", f"That folder cannot be used:\n{exc}")
            return
        self._refresh_folder_sync()

    def _clear_sync_folder(self):
        sync_folder.set_folder(self.shell.profile_dir, "")
        self._refresh_folder_sync()

    def _preview_sync(self):
        """Read-only merge computation uses the same background relay as Apply."""
        if getattr(self, "_folder_sync_running", False):
            return
        if getattr(type(self.shell), "run_in_background", None) is not None:
            self._folder_sync_running = True
            self._refresh_folder_sync()
            self.lbl_sync_status.setText("Checking the shared folder… No data will be changed.")
            try:
                self.shell.run_in_background(lambda: sync_folder.compute(self.shell.profile_dir), self._finish_folder_preview)
            except RuntimeError as exc:
                self._folder_sync_running = False
                self.btn_choose_sync_folder.setEnabled(True)
                self._refresh_folder_sync()
                QMessageBox.warning(self, "Folder sync", str(exc))
            return
        try:
            report = sync_folder.compute(self.shell.profile_dir)
        except (sync_folder.SyncFormatError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Folder sync", str(exc))
            return
        self._show_folder_preview(report)

    def _finish_folder_preview(self, future):
        self._folder_sync_running = False
        self.btn_choose_sync_folder.setEnabled(True)
        self._refresh_folder_sync()
        try:
            report = future.result()
        except (sync_folder.SyncFormatError, OSError, ValueError) as exc:
            self.lbl_sync_status.setText("Preview could not be completed. No data was changed.")
            QMessageBox.warning(self, "Folder sync", str(exc))
            return
        self._show_folder_preview(report)

    def _show_folder_preview(self, report):
        self.lbl_sync_status.setText(sync_folder.summary_line(report))
        changes = report.get("changes", [])
        warnings = report.get("warnings") or []
        if not changes and not warnings:
            QMessageBox.information(self, "Folder sync", "Nothing to merge — this machine is already in step.")
            return
        lines = [f"{change['action']}: {change['title']}  ({change['store_label']})" for change in changes[:12]]
        if len(changes) > 12:
            lines.append(f"… and {len(changes) - 12} more")
        if warnings:
            lines.append("")
            lines.extend(f"⚠ {warning}" for warning in warnings[:6])
        QMessageBox.information(
            self,
            "Folder sync — preview",
            "A sync would do this (it writes nothing until you press Sync now):\n\n" + "\n".join(lines),
        )

    def _apply_sync(self):
        """Merge off the GUI thread; keep controls stable until it finishes."""
        if getattr(self, "_folder_sync_running", False):
            return
        runner = getattr(type(self.shell), "run_in_background", None)
        if runner is not None:
            self._folder_sync_running = True
            for button in (self.btn_apply_sync, self.btn_preview_sync, self.btn_choose_sync_folder, self.btn_clear_sync_folder):
                button.setEnabled(False)
            self.lbl_sync_status.setText("Syncing locally… Your previous data is backed up first.")
            try:
                self.shell.run_in_background(lambda: sync_folder.sync(self.shell.profile_dir), self._finish_folder_sync)
            except RuntimeError as exc:
                self._folder_sync_running = False
                self._refresh_folder_sync()
                QMessageBox.warning(self, "Folder sync", str(exc))
            return
        # Small non-executor hosts (tests/embedded pages) remain synchronous.
        try:
            report = sync_folder.sync(self.shell.profile_dir)
        except (sync_folder.SyncFormatError, sync_folder.SyncApplyError) as exc:
            QMessageBox.warning(self, "Folder sync", str(exc))
            return
        except OSError as exc:  # noqa: BLE001 - a missing folder drive is not a crash
            QMessageBox.warning(self, "Folder sync", f"The sync folder could not be written:\n{exc}")
            return
        self._show_folder_sync_report(report)

    def _finish_folder_sync(self, future):
        self._folder_sync_running = False
        self.btn_choose_sync_folder.setEnabled(True)
        self._refresh_folder_sync()
        try:
            report = future.result()
        except (sync_folder.SyncFormatError, sync_folder.SyncApplyError, OSError, ValueError) as exc:
            self.lbl_sync_status.setText("Sync was not completed. Your backup is retained.")
            QMessageBox.warning(self, "Folder sync", str(exc))
            return
        self._show_folder_sync_report(report)

    def _show_folder_sync_report(self, report):
        line = sync_folder.summary_line(report)
        self.lbl_sync_status.setText(line)
        self._refresh_folder_sync()
        conflicts = sum(int(counts.get("conflicts", 0) or 0) for counts in report.get("summary", {}).values())
        self.lbl_sync_status.setText(
            line + (" · both copies were kept for the conflicts" if conflicts else "")
        )
        if report.get("snapshot"):
            self.lbl_sync_status.setToolTip(f"Backup before this merge: {report['snapshot']}")
        if report.get("applied"):
            self.shell.refresh_shell(force_deep=True)

    def _refresh_engine_notice(self):
        """Say which engine this build is running, and flag the old branch."""
        line = diagnostics.engine_notice(_ui_versions())
        self.lbl_engine.setText(line)
        self.lbl_engine.setToolTip(
            "Chromium is the engine under the tabs. The PyQt6-WebEngine package "
            "brings the newer one; Qt 5.15 pins Chromium 87."
        )

    def _refresh_plugins(self):
        """List every accepted manifest, and name every refused one."""
        found = plugins.load_plugins(self.shell.profile_dir)
        self.plugins_list.clear()
        for plugin in found["plugins"]:
            origin = "shipped with Mei" if plugin.builtin else "yours"
            row = QListWidgetItem(f"{plugin.name}  ·  v{plugin.version}  ·  {plugin.kind}")
            row.setToolTip(f"{plugin.touches()}\nAPI {plugin.api} · {origin}\n{plugin.path}")
            # The manifest rides on the row itself (a QListWidgetItem cannot be a
            # dict key — PyQt makes it unhashable).
            row.setData(Qt.UserRole, plugin)
            self.plugins_list.addItem(row)
        self.btn_run_plugin.setEnabled(bool(found["plugins"]))
        problems = found.get("problems", [])
        if problems:
            first = problems[0]
            more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
            self.lbl_plugin_problems.setText(
                f"{len(problems)} manifest(s) refused — {os.path.basename(os.path.dirname(first['path']))}: "
                f"{first['reason']}{more}"
            )
            self.lbl_plugin_problems.setToolTip("\n".join(f"{item['path']}: {item['reason']}" for item in problems))
        else:
            self.lbl_plugin_problems.setText(f"{len(found['plugins'])} plugin(s) ready.")
            self.lbl_plugin_problems.setToolTip("")

    def _selected_plugin(self):
        row = self.plugins_list.currentItem()
        chosen = row.data(Qt.UserRole) if row is not None else None
        return chosen if isinstance(chosen, plugins.Plugin) else None

    def _run_selected_plugin(self):
        """One file dialog, one service call, one honest report."""
        plugin = self._selected_plugin()
        if plugin is None:
            QMessageBox.information(self, "Plugins", "Select a plugin in the list first.")
            return
        if plugin.kind == "importer":
            path, _filter = QFileDialog.getOpenFileName(
                self, f"Import with {plugin.name}", "", "CSV / TSV (*.csv *.tsv *.txt);;All files (*)"
            )
        else:
            suggested = os.path.join(app_paths.downloads_dir(self.shell.profile_dir), f"{plugin.id}.csv")
            path, _filter = QFileDialog.getSaveFileName(
                self, f"Export with {plugin.name}", suggested, "CSV (*.csv)"
            )
        if not path:
            return
        try:
            report = plugins.run_plugin(plugin, self.shell.profile_dir, path)
        except plugins.PluginError as exc:
            QMessageBox.warning(self, "Plugins", f"{plugin.name} could not run:\n{exc}")
            return
        except OSError as exc:  # noqa: BLE001 - a locked or missing file is not a crash
            QMessageBox.warning(self, "Plugins", f"The file could not be used:\n{exc}")
            return
        self.lbl_plugin_problems.setText(plugins.report_line(report, plugin))
        if plugin.kind == "importer":
            self.shell.refresh_shell(force_deep=True)
        QMessageBox.information(self, "Plugins", plugins.report_line(report, plugin))

    def _open_plugins_folder(self):
        folder = plugins.plugins_dir(self.shell.profile_dir)
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _open_log_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._log_dir()))

    def _refresh_google(self):
        account = prefs.get_google_account(self.shell.profile_dir)
        cached = prefs.get_google_token_cache(self.shell.profile_dir)
        if account:
            label = account.get("email") or account.get("name") or "a Google account"
            token_note = "token cached" if cached.get("access_token") else "no cached token"
            self.lbl_google_status.setText(f"Signed in as {label} · {token_note}.")
        elif self._google_client_id():
            self.lbl_google_status.setText("Client ID set — use “Sign in with Google” to mint a device-code token.")
        else:
            self.lbl_google_status.setText(
                "Not signed in yet. Set a client ID, then sign in with a device code — no password is typed into Mei."
            )
        self.btn_google_verify.setEnabled(bool(cached.get("access_token")))
        if self.google_sign_out_action is not None:
            self.google_sign_out_action.setEnabled(bool(account))

    def _google_sign_in(self):
        client_id = self._google_client_id()
        if not client_id:
            client_id = self._set_google_client_id()
            if not client_id:
                return
        self.btn_google_sign_in.setEnabled(False)
        self.lbl_google_status.setText("Waiting for Google — finish the sign-in in the browser window that just opened…")
        self.shell.run_in_background(
            lambda: google_auth.sign_in_via_device_code(client_id), self._finish_google_sign_in
        )

    def _finish_google_sign_in(self, future):
        self.btn_google_sign_in.setEnabled(True)
        try:
            result = future.result()
        except Exception as exc:
            self.lbl_google_status.setText(f"Sign-in failed: {exc}")
            return
        if not result:
            self.lbl_google_status.setText("Sign-in was denied or timed out — try again.")
            return
        prefs.set_google_account(self.shell.profile_dir, result.get("account", {}))
        prefs.set_google_token_cache(self.shell.profile_dir, result.get("tokens", {}))
        self._refresh_google()

    def _google_verify(self):
        client_id = self._google_client_id()
        cached = prefs.get_google_token_cache(self.shell.profile_dir)
        self.lbl_google_status.setText("Checking the cached token (refreshing only if it is stale)…")

        def _work():
            token = google_auth.ensure_valid_token(client_id, dict(cached) if cached else None)
            if token:
                prefs.set_google_token_cache(self.shell.profile_dir, token)
            return token

        self.shell.run_in_background(_work, self._finish_google_verify)

    def _finish_google_verify(self, future):
        try:
            token = future.result()
        except Exception as exc:
            self.lbl_google_status.setText(f"Token check failed: {exc}")
            return
        self._refresh_google()
        self.lbl_google_status.setText(
            "Token is valid — reused without a network call, refreshed when stale."
            if token
            else "No usable token left. Sign in again."
        )

    def _google_sign_out(self):
        from litebrowser.core import secret_store

        try:
            prefs.clear_google_account(self.shell.profile_dir)
        except secret_store.SecretStorageError as exc:
            QMessageBox.warning(
                self,
                "Google account",
                "The saved Google token could not be removed from the OS credential store. "
                f"Nothing else was changed. Details: {exc}",
            )
            return
        self._refresh_google()

    def _refresh_security(self):
        has_passcode = security.has_passcode(self.shell.profile_dir)
        locked = not security.is_unlocked(self.shell.profile_dir)
        if has_passcode:
            state = "locked" if locked else "unlocked for this session"
            self.lbl_lock_status.setText(f"A passcode is set — Personal and AI are currently {state}.")
        else:
            self.lbl_lock_status.setText("No passcode yet: the first visit to Personal or AI offers to set one.")
        self.btn_lock_now.setEnabled(has_passcode and not locked)
        from litebrowser.core import secret_store

        info = secret_store.status(self.shell.profile_dir)
        hint = secret_store.recovery_hint(self.shell.profile_dir)
        if hint:
            self.lbl_secret_status.setText(hint)
        elif info.get("protected"):
            self.lbl_secret_status.setText(
                "Saved credentials (AI key, sync and bridge tokens, proxy password) are "
                "protected by Windows for this user account. They are not part of sync or backups."
            )
        else:
            self.lbl_secret_status.setText(
                info.get("warning")
                or "Saved credentials are stored in this profile; this platform has no OS vault."
            )

    def _lock_now(self):
        security.lock(self.shell.profile_dir)
        self._refresh_security()
        QMessageBox.information(
            self, "Passcode", "Locked — Personal and AI ask for the passcode again on the next visit."
        )

    def _refresh_monitors(self):
        monitors = page_monitor.load_monitors(self.shell.profile_dir)
        self.monitors_list.clear()
        for monitor in monitors:
            row = QListWidgetItem(monitor.get("title") or monitor.get("url", ""))
            tip = monitor.get("url", "")
            if monitor.get("last_error"):
                tip += "\nLast check failed: " + monitor["last_error"]
            row.setToolTip(tip)
            row.setData(Qt.UserRole, monitor.get("id", ""))
            self.monitors_list.addItem(row)
        if not monitors:
            self.monitors_list.addItem(
                components.hint_list_item("Nothing watched yet — right-click a page and watch it", "○")
            )
        self.btn_monitor_remove.setEnabled(bool(monitors))

    def _remove_monitor(self):
        row = self.monitors_list.currentItem()
        monitor_id = row.data(Qt.UserRole) if row is not None else ""
        if not monitor_id:
            return
        page_monitor.remove_monitor(self.shell.profile_dir, monitor_id)
        self._refresh_monitors()

    def _local_ipv4_hint(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return ""

    def _refresh_mobile_bridge_status(self):
        port = prefs.get_mobile_bridge_port(self.shell.profile_dir)
        lan = prefs.get_mobile_bridge_lan(self.shell.profile_dir)
        if android_bridge_service.is_running():
            ip_hint = self._local_ipv4_hint()
            if lan and ip_hint:
                self.lbl_mobile_status.setText(
                    f"Running — point the Android app at http://{ip_hint}:{port}/ (LAN). Emulator: http://10.0.2.2:{port}/"
                )
            elif lan:
                self.lbl_mobile_status.setText(f"Running on 0.0.0.0:{port} — use this PC’s LAN IPv4 in the app.")
            else:
                self.lbl_mobile_status.setText(f"Running on 127.0.0.1:{port} — phone must use LAN mode + firewall if testing from another device.")
        else:
            self.lbl_mobile_status.setText("Stopped — enable and save, or fix port conflict.")
        self.lbl_mobile_status.updateGeometry()
        parent = self.lbl_mobile_status.parentWidget()
        if parent and parent.layout():
            parent.layout().activate()

    def _refresh_pairing(self):
        self._current_pairing_code = android_bridge_service.pairing_code(
            self.shell.profile_dir, lan_ip=self._local_ipv4_hint()
        )
        self.lbl_pairing_code.setText(
            "Pairing code — paste into Mei Remote (Settings) or the Mei Bridge extension "
            "in Chrome / Opera GX. It contains your access token, so treat it like a password "
            "and never post it publicly:\n" + self._current_pairing_code
        )
        try:
            png = android_bridge_service.pairing_qr_png(self._current_pairing_code)
            image = QImage.fromData(png, "PNG")
            self.lbl_pairing_qr.setPixmap(QPixmap.fromImage(image))
        except Exception:
            self.lbl_pairing_qr.clear()

    def _copy_pairing(self):
        code = getattr(self, "_current_pairing_code", "")
        if code:
            QGuiApplication.clipboard().setText(code)
            QMessageBox.information(
                self,
                "Quick pairing",
                "Pairing code copied — paste it into Mei Remote, or into the Mei Bridge extension "
                "(Extensions/tab-window-bridge) for “send this tab to Mei”.",
            )

    def _generate_mobile_token(self):
        self.ed_mobile_token.setText(prefs.generate_mobile_bridge_token())
        QMessageBox.information(
            self,
            "Mobile bridge token",
            "A new token is ready. It takes effect only when you save — and saving it "
            "disconnects every phone and extension that was paired with the old token.",
        )

    def save_mobile_bridge(self):
        was_lan = prefs.get_mobile_bridge_lan(self.shell.profile_dir)
        enabling_lan = self.chk_mobile_lan.isChecked() and not was_lan
        if enabling_lan:
            answer = QMessageBox.warning(
                self,
                "Enable LAN mode?",
                "LAN mode uses plain HTTP. The bearer token and the data you send travel "
                "unencrypted across the network, and anyone who reads the token can act as "
                "a paired device.\n\nUse this only on a network you trust, or through a VPN. "
                "Keep loopback mode for this PC only.\n\nEnable LAN mode?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self.chk_mobile_lan.setChecked(False)
                return
        token = self.ed_mobile_token.text().strip()
        if self.chk_mobile_bridge.isChecked() and not token:
            token = prefs.generate_mobile_bridge_token()
            self.ed_mobile_token.setText(token)
        existing_token = prefs.get_mobile_bridge_token(self.shell.profile_dir)
        if existing_token and token and token != existing_token:
            answer = QMessageBox.question(
                self,
                "Replace the bridge token?",
                "Saving this new token disconnects every phone and browser extension paired "
                "with the old one; they will need the new pairing code.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self.ed_mobile_token.setText(existing_token)
                return
        prefs.set_mobile_bridge_enabled(self.shell.profile_dir, self.chk_mobile_bridge.isChecked())
        prefs.set_mobile_bridge_port(self.shell.profile_dir, self.spin_mobile_port.value())
        prefs.set_mobile_bridge_lan(self.shell.profile_dir, self.chk_mobile_lan.isChecked())
        from litebrowser.core import secret_store

        try:
            prefs.set_mobile_bridge_token(self.shell.profile_dir, token)
        except secret_store.SecretStorageError as exc:
            QMessageBox.warning(
                self,
                "Mobile bridge",
                "The bridge token could not be protected on this device, so the previous "
                f"token was kept and the listener was not restarted. Details: {exc}",
            )
            return
        ok = android_bridge_service.restart(self.shell.profile_dir)
        self.shell.refresh_shell()
        self._refresh_mobile_bridge_status()
        self._refresh_pairing()
        if self.chk_mobile_bridge.isChecked() and not ok:
            QMessageBox.warning(self, "Mobile bridge", "Could not start the listener (port may be in use).")
        else:
            QMessageBox.information(self, "Mobile bridge", "Mobile bridge settings saved.")

    def save_account(self):
        life_service.save_sync_account(
            self.shell.profile_dir,
            self.ed_email.text().strip(),
            self.ed_display_name.text().strip(),
            enabled=self.chk_local_snapshot.isChecked(),
        )
        self.shell.refresh_shell()
        QMessageBox.information(self, "Settings", "Profile account state saved.")

    def _refresh_sync_status(self):
        from litebrowser.services import sync_service
        last = sync_service.last_sync(self.shell.profile_dir)
        if last:
            self.lbl_sync_status.setText("Last sync: %s" % _time_utils.format_ts(last))
        else:
            self.lbl_sync_status.setText("Never synced yet — save settings, then press \u201cSync now\u201d.")

    def save_sync(self):
        from litebrowser.services import sync_service

        endpoint = self.ed_sync_endpoint.text().strip()
        _, error = sync_service.validate_endpoint(endpoint)
        if endpoint and error:
            QMessageBox.warning(self, "Sync", error)
            return
        warning = sync_service.endpoint_warning(endpoint)
        if warning:
            answer = QMessageBox.question(
                self,
                "Sync endpoint is not encrypted",
                warning + "\n\nSave this endpoint anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        from litebrowser.core import secret_store

        prefs.set_sync_enabled(self.shell.profile_dir, self.chk_sync_enabled.isChecked())
        prefs.set_sync_endpoint(self.shell.profile_dir, endpoint)
        try:
            prefs.set_sync_token(self.shell.profile_dir, self.ed_sync_token.text())
        except secret_store.SecretStorageError as exc:
            QMessageBox.warning(
                self,
                "Sync",
                "The bearer token could not be protected on this device, so the previous "
                f"token was kept. The endpoint and switch were saved. Details: {exc}",
            )
            self._refresh_sync_status()
            return
        self.shell.refresh_shell()
        QMessageBox.information(self, "Sync", "Sync settings saved.")

    def sync_now(self):
        from litebrowser.services import sync_service
        endpoint = self.ed_sync_endpoint.text().strip()
        token = self.ed_sync_token.text().strip()
        ok, msg = sync_service.sync_now(self.shell.profile_dir, endpoint, token)
        self._refresh_sync_status()
        QMessageBox.information(self, "Sync", msg if ok else msg)

    def save_ui(self):
        # Combos carry display labels; map back to stable theme/accent ids.
        try:
            theme_id = self._theme_ids[self.cmb_theme.currentIndex()]
        except (AttributeError, IndexError):
            theme_id = theme.DEFAULT_THEME
        accent_id = self.cmb_accent.currentData() or "brass"
        prefs.save_pref(self.shell.profile_dir, "appearance_mode", self.cmb_appearance.currentData() or "system")
        prefs.set_shell_theme(self.shell.profile_dir, theme_id)
        prefs.set_accent(self.shell.profile_dir, accent_id)
        prefs.save_pref(self.shell.profile_dir, "reduced_motion", self.cmb_motion.currentData() or "system")
        prefs.set_max_live_tabs(self.shell.profile_dir, self.spin_max_live_tabs.value())
        prefs.set_new_tab_steam(self.shell.profile_dir, self.chk_new_tab_steam.isChecked())
        prefs.set_new_tab_greeting(self.shell.profile_dir, self.chk_new_tab_greeting.isChecked())
        prefs.set_show_morning_brief(self.shell.profile_dir, self.chk_show_brief.isChecked())
        prefs.save_pref(self.shell.profile_dir, "shield_always_on", self.chk_shield.isChecked())
        prefs.set_auto_theme(self.shell.profile_dir, self.chk_auto_theme.isChecked())
        # Keep the shell's auto-theme watcher in sync with the new setting.
        if hasattr(self.shell, "_sync_auto_theme_timer"):
            self.shell._sync_auto_theme_timer()
        data = prefs.load_prefs(self.shell.profile_dir)
        data["shell_density"] = self.cmb_density.currentText()
        prefs.save_prefs(self.shell.profile_dir, data)
        self.shell.refresh_shell()
        QMessageBox.information(self, "Settings", "UI preferences saved.")


class HistoryPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("HistoryWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(8)
        title_row = QHBoxLayout()
        page = components.page_header("Activity History", "Every saved action, kept readable and close at hand")
        title_row.addWidget(page, 1)
        self.lbl_history_scope = components.badge("ALL ACTIVITY", "accent")
        title_row.addWidget(self.lbl_history_scope, 0, Qt.AlignTop)
        hero_layout.addLayout(title_row)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems(["all", "browser-visit", "bookmark", "note", "task", "calendar", "board", "download", "saved-page", "ai-question", "account"])
        controls_row.addWidget(self.cmb_kind)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Search URLs, notes, tasks, AI questions, downloads, boards...")
        self.ed_search.setMinimumWidth(0)
        self.cmb_kind.setMaximumWidth(150)
        controls_row.addWidget(self.ed_search, 1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_export = QPushButton("Export backup")
        self.btn_import = QPushButton("Import backup")
        self.btn_clear_activity = QPushButton("Clear all")
        self.btn_refresh.setObjectName("TopAccentButton")
        controls_row.addWidget(self.btn_refresh)
        hero_layout.addLayout(controls_row)
        backup_row = QHBoxLayout()
        backup_row.addWidget(self.btn_export)
        backup_row.addWidget(self.btn_import)
        backup_row.addStretch(1)
        self.btn_clear_activity.setObjectName("DangerButton")
        backup_row.addWidget(self.btn_clear_activity)
        hero_layout.addLayout(backup_row)
        layout.addWidget(hero)

        self.history_stats = {
            "all": components.stat_tile("0", "activity records"),
            "visits": components.stat_tile("0", "browser visits"),
            "workspace": components.stat_tile("0", "workspace updates"),
        }
        layout.addWidget(components.stat_row(list(self.history_stats.values())))

        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("MutedLabel")
        self.lbl_summary.setWordWrap(True)
        activity_card, activity_layout = _panel(
            "Your activity",
            "A readable timeline of browser visits and workspace changes",
        )
        activity_layout.addWidget(self.lbl_summary)

        self.chk_zip_include_browser_data = QCheckBox(
            "Include browser state in backup (larger export)"
        )
        self.chk_zip_include_browser_data.setObjectName("MutedLabel")
        layout.addWidget(self.chk_zip_include_browser_data)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("CafeList")
        self.list_widget.setSpacing(2)
        activity_layout.addWidget(self.list_widget, 1)
        layout.addWidget(activity_card, 1)

        self.ed_search.returnPressed.connect(self.refresh)
        self.cmb_kind.currentIndexChanged.connect(self.refresh)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_export.clicked.connect(self.export_backup)
        self.btn_import.clicked.connect(self.import_backup)
        self.btn_clear_activity.clicked.connect(self.clear_activity)

    def clear_activity(self):
        if QMessageBox.question(
            self,
            "History",
            "Delete ALL activity records? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        removed = history_service.clear_activity(self.shell.profile_dir)
        self.refresh()
        QMessageBox.information(self, "History", "Cleared %d activity records." % removed)

    def refresh(self):
        kind = self.cmb_kind.currentText()
        query = self.ed_search.text().strip()
        items = history_service.list_activity(self.shell.profile_dir, query=query, kind="" if kind == "all" else kind)
        private_access = security.is_unlocked(self.shell.profile_dir) or bool(getattr(self.shell, "_unlocked_spaces", set()))
        if security.has_passcode(self.shell.profile_dir) and not private_access:
            # Activity descriptions can include note titles and AI answers.
            items = [item for item in items if item.get("kind") in ("page", "browser", "tab", "download")]
            self.btn_export.setEnabled(False)
            self.btn_import.setEnabled(False)
        else:
            self.btn_export.setEnabled(True)
            self.btn_import.setEnabled(True)
        self.list_widget.clear()
        for item in items:
            stamp = _format_ts(int(item.get("ts", 0) or 0))
            row = _activity_item(item.get("kind", ""), item.get("title", ""), item.get("detail", ""), stamp)
            row.setData(Qt.UserRole, item)
            self.list_widget.addItem(row)
        if self.list_widget.count() == 0:
            self.list_widget.addItem("No activity matched your search.")
        self.lbl_summary.setText(f"{len(items)} activity records · Backups include your profile and notes.")
        self.chk_zip_include_browser_data.setToolTip("Includes WebEngine cache and site storage. Larger and slower; restart after importing browser state.")

    def export_backup(self):
        if not self.shell.switch_workspace("library"):
            return
        default = os.path.join(self.shell.profile_dir, f"litebrowser-profile-backup-{time.strftime('%Y%m%d-%H%M')}.zip")
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export profile backup", default, "Zip bundle (*.zip);;JSON (*.json)"
        )
        if not file_path:
            return
        lower = file_path.lower()
        if lower.endswith(".json"):
            payload = history_service.export_profile_payload(self.shell.profile_dir, inline_vault_files=True)
            storage_utils.write_json(file_path, payload)
        else:
            if not lower.endswith(".zip"):
                file_path = file_path + ".zip"
            inc_bd = self.chk_zip_include_browser_data.isChecked()
            if inc_bd:
                confirm = QMessageBox.question(
                    self,
                    "Export backup",
                    "Including BrowserData can create a very large archive and take a long time. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if confirm != QMessageBox.Yes:
                    return
            if not history_service.export_profile_to_zip(
                self.shell.profile_dir, file_path, include_browser_data=inc_bd
            ):
                QMessageBox.warning(self, "History", "Could not write the backup zip file.")
                return
        QMessageBox.information(self, "History", "Profile backup exported successfully.")

    def import_backup(self):
        if not self.shell.switch_workspace("library"):
            return
        if not self.shell.personal_page._flush_note_edits():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import profile backup", "", "Backup (*.zip *.json);;Zip (*.zip);;JSON (*.json)"
        )
        if not file_path:
            return
        if not history_service.import_profile_from_path(self.shell.profile_dir, file_path):
            QMessageBox.warning(self, "History", "Backup file is not valid.")
            return
        self.shell.refresh_shell()
        self.refresh()
        msg = "Profile backup imported. Your data has been restored into this profile."
        if file_path.lower().endswith(".zip"):
            msg += "\n\nIf this backup included BrowserData, close and restart Mei so WebEngine loads the restored profile cleanly."
        QMessageBox.information(self, "History", msg)
