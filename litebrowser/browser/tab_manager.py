import hashlib
import os
import time

from PyQt5.QtCore import QSignalBlocker, QSize, Qt, QTimer, QUrl
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineView
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from litebrowser.browser import browser_page
from litebrowser.browser.adblock import TrackingBlocker
from litebrowser.core import app_version, prefs
from litebrowser.services import workspace_manager

TAB_WIDGET_ROLE = Qt.UserRole
TAB_PINNED_ROLE = Qt.UserRole + 1
TAB_META_ROLE = Qt.UserRole + 10
TAB_GROUP_ROLE = Qt.UserRole + 11  # group name ("" = no group)
TAB_GROUP_COLOR_ROLE = Qt.UserRole + 12  # hex color or ""
TAB_GROUP_COLLAPSED_ROLE = Qt.UserRole + 13  # bool: group folded on the desk

# Chrome-style tab group palette: saturated but theme-agnostic accent chips.
TAB_GROUP_COLORS = (
    ("Blue", "#4c8bf5"),
    ("Red", "#ea6a5e"),
    ("Yellow", "#f2c14e"),
    ("Green", "#5fae7b"),
    ("Purple", "#a06ee1"),
    ("Orange", "#f0964f"),
    ("Pink", "#e2719e"),
    ("Cyan", "#48b8c9"),
    ("Gray", "#8d8578"),
)

_FAVICON_CACHE = {}


class DormantTabView(QWidget):
    """A nearly-free stack entry retained for a suspended tab.

    Keeping a QWidget instead of a QWebEngineView is the key to large tab
    collections: the renderer, JS heap, media buffers, and page cache are
    released until the tab is selected again.
    """

    def __init__(self, title: str = "", url: str = ""):
        super().__init__()
        self.setObjectName("DormantTabView")
        self.setProperty("tab_title", title)
        self.setProperty("tab_url", url)
        # One small label (not a renderer): hundreds of dormant tabs still use
        # only a few KB each, but the page no longer looks like a dead void.
        try:
            from PyQt5.QtWidgets import QLabel, QVBoxLayout

            lay = QVBoxLayout(self)
            lay.setContentsMargins(24, 24, 24, 24)
            lay.setAlignment(Qt.AlignCenter)
            glyph = QLabel("💤")
            glyph.setAlignment(Qt.AlignCenter)
            glyph.setStyleSheet("font-size: 42px; background: transparent;")
            lay.addWidget(glyph)
            t = QLabel(title or "Suspended tab")
            t.setAlignment(Qt.AlignCenter)
            t.setStyleSheet("font-size: 15px; font-weight: 700; background: transparent;")
            lay.addWidget(t)
            u = QLabel((url or "")[:70])
            u.setAlignment(Qt.AlignCenter)
            u.setStyleSheet("font-size: 11px; background: transparent;")
            lay.addWidget(u)
            hint = QLabel("Select this tab to wake it up instantly.")
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet("font-size: 11px; background: transparent;")
            lay.addWidget(hint)
        except Exception:
            pass


class TabMemoryTip(QLabel):
    """Non-native hover popup for tab memory info.

    The previous implementation used ``QToolTip.showText()``, which creates a
    native top-level window. On Windows, popping a native window while a
    QWebEngine surface is compositing can knock the shared GPU compositor off
    its backing store and leave the other windows rendering black. This overlay
    is a plain child widget of the browser sidebar, so it never creates a
    native window and never disturbs the WebEngine compositing pipeline.
    """

    def __init__(self, parent, pal):
        super().__init__(parent)
        self.setObjectName("TabMemoryTip")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setMaximumWidth(280)
        self.setStyleSheet(
            "QLabel#TabMemoryTip { background: %s; color: %s; border: 1px solid %s;"
            " border-radius: 6px; padding: 6px 9px; font-size: 11px; font-weight: 600; }"
            % (
                pal.get("CARD_BG", "#1F1810"),
                pal.get("TEXT", "#F7EDD9"),
                pal.get("ITEM_SELECTED_BORDER", "#D9A94F"),
            )
        )
        self.hide()


class TabListItemWidget(QWidget):
    def __init__(self, manager, item, title):
        super().__init__()
        self.manager = manager
        self.item = item
        # Most tab rows are never hovered. Allocate a timer only for the
        # handful the user inspects instead of one QTimer per open tab.
        self._memory_timer = None

        self.setAttribute(Qt.WA_Hover, True)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        # Slim 32px rows: tighter margins + spacing for a denser, professional desk.
        layout.setContentsMargins(6, 2, 3, 2)
        layout.setSpacing(5)

        self.lbl_group = QLabel("")  # Chrome-style group color dot
        self.lbl_group.setFixedWidth(7)
        self.lbl_group.setAlignment(Qt.AlignCenter)
        self.lbl_group.setStyleSheet("background: transparent; border-radius: 3px;")
        self.lbl_group.setVisible(False)
        layout.addWidget(self.lbl_group)
        self.lbl_icon = QLabel("•")
        self.lbl_icon.setFixedWidth(16)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.lbl_title = QLabel(title)
        # No native setToolTip here: native tooltips near a QWebEngine surface
        # can trigger the black-screen compositor bug on Windows. The tab
        # memory overlay (TabMemoryTip) already shows the title on hover.
        self.lbl_title.setWordWrap(False)
        self.lbl_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._base_title_style = ""
        self.lbl_state = QLabel("")
        self.lbl_state.setFixedWidth(26)
        self.lbl_state.setAlignment(Qt.AlignCenter)
        self.btn_close = QToolButton()
        self.btn_close.setText("x")
        self.btn_close.setFixedSize(18, 18)
        self.btn_close.setCursor(Qt.PointingHandCursor)

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_title, 1)
        layout.addWidget(self.lbl_state)
        layout.addWidget(self.btn_close)
        # Colours are resolved once here and re-resolved by TabManager.refresh_theme
        # on every theme change (see apply_theme).
        self.apply_theme()

    def apply_theme(self):
        """Re-resolve this row's inline colours for the theme in effect now.

        The row paints its own glyph/state/close colours, so re-applying the
        window stylesheet never reaches it: with auto day/night on, rows built at
        night kept light-theme label colours after the shell flipped (and the
        other way round in the morning).
        """
        pal = self._palette()
        self.lbl_icon.setStyleSheet(
            f"color: {pal['ACCENT']}; font-size: 12px; font-weight: 700; background: transparent;"
        )
        self.lbl_state.setStyleSheet(
            f"color: {pal['TEXT_MUTED']}; font-size: 10px; font-weight: 700; background: transparent;"
        )
        self.btn_close.setStyleSheet(
            "QToolButton { background: transparent; border: none; color: %(MUTED)s; font-size: 12px;}"
            " QToolButton:hover { color: #d06a5a; background: %(HOVER)s; border-radius: 4px; }"
            % {"MUTED": pal["TEXT_MUTED"], "HOVER": pal["ITEM_HOVER"]}
        )
        self._base_title_style = f"color: {pal['TEXT']}; font-size: 11px; font-weight: 600; background: transparent;"
        self.lbl_title.setStyleSheet(self._base_title_style)

    def _palette(self):
        base_dir = getattr(self.manager, "base_dir", None)
        mode = "cafe-night"
        accent = None
        if base_dir:
            try:
                # resolved_auto_theme, not get_shell_theme: with auto day/night on,
                # the stored name paints day colours on a night sidebar, which is
                # how tab titles became invisible (dark text on a dark panel).
                mode = prefs.resolved_auto_theme(base_dir)
                accent = prefs.get_accent(base_dir)
            except Exception:
                pass
        from litebrowser.core import theme_data
        return theme_data._palette(mode, accent)

    def set_icon(self, icon_value):
        if isinstance(icon_value, QIcon) and not icon_value.isNull():
            self.lbl_icon.setPixmap(icon_value.pixmap(14, 14))
            self.lbl_icon.setText("")
            return
        if isinstance(icon_value, str) and icon_value and os.path.exists(icon_value):
            pix = QPixmap(icon_value)
            if not pix.isNull():
                self.lbl_icon.setPixmap(pix.scaled(14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.lbl_icon.setText("")
                return
        self.lbl_icon.setPixmap(QPixmap())
        self.lbl_icon.setText("•")

    def text(self):
        return self.lbl_title.text()

    def setText(self, value):
        self.lbl_title.setText(value)

    def set_title_style(self, style):
        self.lbl_title.setStyleSheet(style)

    def mouseReleaseEvent(self, event):
        # Chrome/Firefox standard: middle-click anywhere on the row closes the
        # tab (v6.5 audit: not implemented anywhere).
        from PyQt5.QtCore import Qt as _Qt

        if event.button() == _Qt.MiddleButton and self.item is not None:
            self.manager.close_tab_item(self.item)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self.manager._hovered_item = self.item
        if self._memory_timer is None:
            self._memory_timer = QTimer(self)
            self._memory_timer.setSingleShot(True)
            self._memory_timer.timeout.connect(self._show_memory_tooltip)
        # Chrome-like: show the MB bubble almost immediately on hover.
        self._memory_timer.start(700)
        return super().enterEvent(event)

    def leaveEvent(self, event):
        self.manager._hovered_item = None
        if self._memory_timer is not None:
            self._memory_timer.stop()
        self.manager.hide_tab_memory_tooltip()
        return super().leaveEvent(event)

    def _show_memory_tooltip(self):
        self.manager.show_tab_memory_tooltip(self.item)


class TabManager:
    # A full QWebEngine renderer is expensive. Once a workspace grows past
    # this count, inactive tabs are dehydrated to lightweight placeholders.
    # Users can override via the "Max live tabs" performance setting.
    AUTO_HIBERNATE_THRESHOLD = 6

    @property
    def auto_hibernate_threshold(self):
        try:
            return prefs.get_max_live_tabs(self.base_dir)
        except Exception:
            return self.AUTO_HIBERNATE_THRESHOLD

    def __init__(self, window):
        self.window = window
        self.stack = window.stack
        self.tab_list = window.tab_list
        self.browsers = window.browsers
        self.lbl_tab_count = window.lbl_tab_count
        self.base_dir = window.base_dir
        self._incognito_profiles = window._incognito_profiles
        self.ext_path = window.ext_path
        self.profile = window.profile
        self.interceptor = window.interceptor
        # Session restore can create hundreds of lightweight rows.  Avoid
        # repeatedly repainting and recounting the entire tab desk while the
        # batch is still being assembled.
        self._batch_depth = 0
        self._tab_stats_dirty = False
        self._mem_tip = None
        self._hovered_item = None
        # Hide the non-native memory popup when the tab desk scrolls so it never
        # lingers over the wrong row.
        try:
            self.tab_list.verticalScrollBar().valueChanged.connect(self.hide_tab_memory_tooltip)
        except Exception:
            pass
        from litebrowser.core import theme_data
        mode = prefs.resolved_auto_theme(self.base_dir) if self.base_dir else theme_data.DEFAULT_THEME
        self._pal = theme_data._palette(mode, prefs.get_accent(self.base_dir) if self.base_dir else None)

    def get_hibernate_seconds(self):
        return prefs.get_hibernate_seconds(self.base_dir)

    def _live_browser_count(self):
        return sum(1 for browser in self.browsers if browser is not None)

    def begin_batch(self):
        """Coalesce tab-desk work during session/tab-set restore."""
        self._batch_depth += 1
        if self._batch_depth == 1:
            self.tab_list.setUpdatesEnabled(False)
            self.stack.setUpdatesEnabled(False)

    def end_batch(self):
        """Finish a coalesced tab restore and present one settled UI state."""
        if self._batch_depth <= 0:
            return
        self._batch_depth -= 1
        if self._batch_depth:
            return
        self.tab_list.setUpdatesEnabled(True)
        self.stack.setUpdatesEnabled(True)
        self._tab_stats_dirty = False
        self.update_tab_count()

    def _make_dormant_view(self, title="", url=""):
        return DormantTabView(title, url)

    def _metadata_for_item(self, item):
        return dict(item.data(TAB_META_ROLE) or {}) if item else {}

    def _set_metadata(self, item, **changes):
        if not item:
            return {}
        metadata = self._metadata_for_item(item)
        metadata.update(changes)
        item.setData(TAB_META_ROLE, metadata)
        return metadata

    def _dispose_browser(self, browser):
        """Release a disposable renderer and any private profile behind it."""
        if browser is None:
            return
        private_interceptor = getattr(browser, "_lite_incognito_interceptor", None)
        private_profile = getattr(browser, "_lite_incognito_profile", None)
        browser.deleteLater()
        if private_profile is not None:
            try:
                self._incognito_profiles.remove(private_profile)
            except ValueError:
                pass
            try:
                private_profile.deleteLater()
            except Exception:
                pass

        if private_interceptor is not None:
            try:
                self.window._incognito_interceptors.remove(private_interceptor)
            except (AttributeError, ValueError):
                pass

    def _build_browser(self, qurl, is_incognito=False):
        if is_incognito:
            profile = QWebEngineProfile(self.window)
            if hasattr(self.window, "_configure_web_profile"):
                self.window._configure_web_profile(profile, off_the_record=True)
            interceptor = TrackingBlocker(profile, self.base_dir)
            interceptor.https_only = prefs.get_https_only(self.base_dir)
            profile.setUrlRequestInterceptor(interceptor)
            self._incognito_profiles.append(profile)
            if not hasattr(self.window, "_incognito_interceptors"):
                self.window._incognito_interceptors = []
            self.window._incognito_interceptors.append(interceptor)
            browser = QWebEngineView()
            browser.setPage(browser_page.BrowserPage(profile, browser, self.base_dir, host=self.window))
            browser._lite_incognito_interceptor = interceptor
            # Incognito profiles have no downloadRequested wiring otherwise —
            # downloads from private tabs silently did nothing (v6.4 bug).
            if hasattr(self.window, "handle_download_request"):
                profile.downloadRequested.connect(self.window.handle_download_request)
                browser._lite_incognito_download_conn = True
        else:
            profile = self.profile
            if hasattr(self.window, "get_profile_for_url"):
                profile = self.window.get_profile_for_url(qurl, is_incognito=False)
            browser = QWebEngineView()
            browser.setPage(browser_page.BrowserPage(profile, browser, self.base_dir, host=self.window))
        browser._lite_incognito_profile = profile if is_incognito else None
        # Neutral white: themed beige (#f4ead8) tinted many sites (transparent roots / compositing).
        browser.page().setBackgroundColor(QColor(Qt.white))
        browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return browser

    def _create_tab_item(self, label, browser):
        item = QListWidgetItem()
        widget = TabListItemWidget(self, item, label)
        item.setSizeHint(QSize(224, 32))
        self.tab_list.addItem(item)
        self.tab_list.setItemWidget(item, widget)
        item.setData(TAB_WIDGET_ROLE, widget)
        item.setData(TAB_PINNED_ROLE, False)
        item.setData(TAB_META_ROLE, {"title": label, "url": "", "icon": "", "hibernated": False})
        ws_id = getattr(self.window, "current_workspace_id", workspace_manager.PRIMARY_WORKSPACE_ID)
        item.setData(Qt.UserRole + workspace_manager.WORKSPACE_ROLE, ws_id)
        widget.btn_close.clicked.connect(lambda _, i_item=item: self.close_tab_item(i_item))
        return item, widget

    def _favicon_path_for_url(self, url: str) -> str:
        global _FAVICON_CACHE
        if url in _FAVICON_CACHE:
            return _FAVICON_CACHE[url]
        safe = hashlib.sha1((url or "blank").encode("utf-8", errors="ignore")).hexdigest()
        result = os.path.join(prefs.favicon_cache_dir(self.base_dir), f"{safe}.png")
        _FAVICON_CACHE[url] = result
        if len(_FAVICON_CACHE) > 512:
            _FAVICON_CACHE.clear()
        return result

    def _refresh_hibernate_timers(self, active_index=None):
        """Arm idle timers only for background renderers.

        A repeating timer started when a tab was created counted foreground time
        as background idle time and woke the UI every interval even for the
        active tab.  Keep one single-shot timer per live background tab; it is
        started when the tab leaves the foreground and stopped when selected.
        """
        if active_index is None:
            active_index = self.tab_list.currentRow()
        sec = self.get_hibernate_seconds()
        interval_ms = max(0, int(sec or 0)) * 1000
        for i, browser in enumerate(self.browsers):
            if browser is None:
                continue
            timer = browser.property("hibernate_timer")
            if timer is None:
                continue
            item = self.tab_list.item(i)
            is_active = i == active_index
            is_pinned = bool(item and item.data(TAB_PINNED_ROLE))
            is_hibernated = bool(browser.property("hibernated"))
            if interval_ms <= 0 or is_active or is_pinned or is_hibernated:
                timer.stop()
                continue
            if not timer.isActive() or timer.interval() != interval_ms:
                timer.start(interval_ms)

    def _wire_browser(self, browser, item):
        """Attach the normal browser lifecycle to a freshly materialized view."""
        browser.setProperty("memory_hint_mb", 0.0)
        browser.setProperty("icon_url", "")
        browser.setProperty("hibernated", False)
        hibernate_timer = QTimer(browser)
        hibernate_timer.setSingleShot(True)
        hibernate_timer.timeout.connect(lambda b=browser, i=item: self.hibernate_tab(b, i))
        browser.setProperty("hibernate_timer", hibernate_timer)
        browser.urlChanged.connect(lambda q, b=browser: self.window.update_urlbar(q, b))
        browser.urlChanged.connect(lambda q, b=browser: self.window.record_history(q, b))
        browser.titleChanged.connect(lambda title, b=browser: self.on_title_changed(title, b))
        browser.iconChanged.connect(lambda icon, b=browser: self.on_icon_changed(icon, b))
        browser.loadFinished.connect(lambda ok, b=browser: self._on_load_finished_wire(ok, b))
        browser.loadStarted.connect(lambda b=browser: self.window.on_load_started(b))
        # Load progress → the thin accent bar under the toolbar (v6.5: the app
        # had zero loadProgress feedback between navigation start and finish).
        browser.loadProgress.connect(
            lambda progress, b=browser: self.window.on_load_progress(progress, b)
        )
        # Chrome-style hover preview: show link targets in the bottom strip.
        browser.page().linkHovered.connect(
            lambda url, b=browser: self.window.on_link_hovered(url, b)
        )
        # Signal-based audible tracking (replaces the v6.5 5s poll): the rail
        # mini-player appears the moment a tab starts playing.
        if hasattr(browser.page(), "recentlyAudibleChanged"):
            browser.page().recentlyAudibleChanged.connect(
                lambda audible, b=browser: self.window.on_audible_changed(bool(audible), b)
            )
        # Renderer crash recovery: a dead renderer used to leave a white tab
        # with no way back (v6.4 had no renderProcessTerminated handler).
        browser.renderProcessTerminated.connect(
            lambda status, code, b=browser, i=item: self._on_render_process_terminated(b, i, status, code)
        )

    def _on_load_finished_wire(self, ok, browser):
        if ok:
            # A successful load proves the renderer is healthy again; reset the
            # crash-reload budget so a later crash still gets its auto-retry.
            browser.setProperty("crash_reload_count", 0)
        self.window.on_load_finished(ok, browser)

    def _on_render_process_terminated(self, browser, item, status, code):
        """Reload a crashed tab once, then surface a status note instead of a
        blank white page."""
        url = ""
        try:
            url = browser.url().toString()
        except Exception:
            url = ""
        crash_count = browser.property("crash_reload_count") or 0
        if crash_count < 1 and url and url != "about:blank":
            # One automatic reload recovers most OOM/renderer hiccups.
            browser.setProperty("crash_reload_count", crash_count + 1)
            QTimer.singleShot(250, lambda: self._safe_reload(browser, url))
            return
        try:
            item.setText("[Crashed] " + (self._metadata_for_item(item).get("title") or "Tab"))
        except Exception:
            pass
        status_bar = getattr(self.window, "lbl_status_context", None)
        if status_bar is not None:
            status_bar.setText(f"Tab crashed (code {code}) — reload to recover")

    def _safe_reload(self, browser, url):
        try:
            if browser.url().toString() in ("", "about:blank"):
                browser.setUrl(QUrl(url))
            else:
                browser.reload()
        except Exception:
            pass

    def _materialize_tab(self, index):
        """Recreate a renderer only when a dormant tab is actually selected."""
        if index < 0 or index >= len(self.browsers):
            return None
        existing = self.browsers[index]
        if existing is not None:
            return existing
        item = self.tab_list.item(index)
        if not item:
            return None
        metadata = self._metadata_for_item(item)
        target_url = metadata.get("url") or "https://google.com"
        browser = self._build_browser(QUrl(target_url), is_incognito=bool(metadata.get("incognito")))
        self._wire_browser(browser, item)
        placeholder = self.stack.widget(index)
        if placeholder is not None:
            self.stack.removeWidget(placeholder)
            placeholder.deleteLater()
        self.stack.insertWidget(index, browser)
        self.browsers[index] = browser
        self._set_metadata(item, hibernated=False)
        self._clear_hibernated_visual(item)
        if target_url == "about:newtab":
            browser.page().setHtml(self.window.get_new_tab_html(), QUrl("about:newtab"))
        else:
            browser.setUrl(QUrl(target_url))
        return browser

    def add_tab(self, qurl=None, label="New Tab", is_active=True, is_incognito=False, session_data=None):
        session_data = session_data or {}
        show_new_tab_page = qurl is None and not is_incognito and not session_data
        if qurl is None:
            # Incognito Ctrl+T must not silently load Google: a fresh private
            # tab starts blank so no request leaves the machine (v6.4 bug).
            qurl = QUrl("about:blank") if is_incognito else QUrl("https://google.com")
        target_url = session_data.get("url") or ("about:newtab" if show_new_tab_page else qurl.toString())
        saved_workspace = (
            session_data.get("workspace_id")
            or session_data.get("workspace")
            or getattr(self.window, "current_workspace_id", workspace_manager.PRIMARY_WORKSPACE_ID)
        )
        is_pinned = bool(session_data.get("pinned"))
        # Restored tabs never need a renderer until selected. For ordinary
        # background tabs, start deferring once the desk has several live pages
        # — or always, when "background loading priority" is enabled so the
        # active tab keeps full network/CPU while background tabs stay dormant.
        try:
            defer_background = prefs.get_defer_background_tabs(self.base_dir)
        except Exception:
            defer_background = True
        should_defer = not is_active and (
            defer_background
            or bool(session_data)
            or bool(session_data.get("hibernated"))
            or self._live_browser_count() >= self.auto_hibernate_threshold
        )

        item, widget = self._create_tab_item(session_data.get("title") or label, None)
        item.setData(Qt.UserRole + workspace_manager.WORKSPACE_ROLE, saved_workspace)
        item.setData(TAB_PINNED_ROLE, is_pinned)
        self._set_metadata(
            item,
            title=session_data.get("title") or label,
            url=target_url,
            icon=session_data.get("icon", ""),
            hibernated=should_defer,
            incognito=bool(is_incognito),
        )
        if is_pinned:
            widget.lbl_state.setText("Pin")
            widget.lbl_title.setStyleSheet(
                f"color: {self._pal['ACCENT_HOVER']}; font-size: 11px; font-weight: 700; background: transparent;"
            )
        if session_data.get("icon"):
            widget.set_icon(session_data.get("icon"))
        # Restore the colored group across sessions (stored in metadata).
        group_name = session_data.get("group") or ""
        group_color = session_data.get("group_color") or ""
        if group_name:
            item.setData(TAB_GROUP_ROLE, group_name)
            item.setData(TAB_GROUP_COLOR_ROLE, group_color)
            row_now = self.tab_list.row(item)
            if row_now >= 0:
                self.set_tab_group(row_now, group_name, group_color)

        browser = None
        if should_defer:
            dormant = self._make_dormant_view(session_data.get("title") or label, target_url)
            self.browsers.append(None)
            self.stack.addWidget(dormant)
            self._apply_hibernated_visual(item)
        else:
            browser = self._build_browser(qurl, is_incognito=is_incognito)
            self.browsers.append(browser)
            self.stack.addWidget(browser)
            self._wire_browser(browser, item)
            if show_new_tab_page:
                browser.page().setHtml(self.window.get_new_tab_html(), QUrl("about:newtab"))
            elif is_active:
                browser.setUrl(QUrl(target_url))
            else:
                browser.setProperty("pending_url", QUrl(target_url))

        if is_active:
            self.tab_list.setCurrentItem(item)
            if browser is None:
                browser = self._materialize_tab(self.tab_list.row(item))
            if browser is not None:
                self.stack.setCurrentWidget(browser)

        self._refresh_hibernate_timers(self.tab_list.row(item) if is_active else None)
        self._enforce_background_hibernation()
        self.update_tab_count()
        return browser

    def current_browser(self):
        index = self.stack.currentIndex()
        if 0 <= index < len(self.browsers):
            return self.browsers[index] or None
        return None

    def _item_for_browser(self, browser):
        try:
            idx = self.browsers.index(browser)
        except ValueError:
            return None
        return self.tab_list.item(idx)

    def _widget_for_item(self, item):
        return item.data(TAB_WIDGET_ROLE) if item else None

    def on_title_changed(self, title, browser):
        item = self._item_for_browser(browser)
        widget = self._widget_for_item(item)
        if not widget:
            return
        metadata = dict(item.data(TAB_META_ROLE) or {})
        metadata["title"] = title or metadata.get("title") or "Tab"
        metadata["url"] = browser.url().toString() or metadata.get("url", "")
        item.setData(TAB_META_ROLE, metadata)
        widget.setText(metadata["title"])
        if browser == self.current_browser() and title:
            self.window.setWindowTitle(f"{title} - {app_version.APP_NAME}")

    def on_icon_changed(self, icon, browser):
        item = self._item_for_browser(browser)
        widget = self._widget_for_item(item)
        if not widget:
            return
        if isinstance(icon, QIcon) and not icon.isNull():
            widget.set_icon(icon)
            metadata = dict(item.data(TAB_META_ROLE) or {})
            icon_path = self._favicon_path_for_url(metadata.get("url") or browser.url().toString())
            try:
                pix = icon.pixmap(32, 32)
                if not pix.isNull():
                    pix.save(icon_path, "PNG")
                    metadata["icon"] = icon_path
            except Exception:
                pass
            item.setData(TAB_META_ROLE, metadata)
        else:
            widget.set_icon("")

    def row_state_text(self, i):
        """Priority order for the per-row state chip: hibernated > pinned >
        audible. Collapsed-group counts live in the same slot when applied by
        the window's visibility pass."""
        item = self.tab_list.item(i)
        if item is None:
            return ""
        browser = self.browsers[i] if i < len(self.browsers) else None
        try:
            if browser is None or browser.property("hibernated"):
                return "Zz"
        except Exception:
            pass
        if item.data(TAB_PINNED_ROLE):
            return "Pin"
        if browser is not None:
            try:
                if bool(browser.property("audible")):
                    return "🔊"
            except Exception:
                pass
        return ""

    def refresh_row_state_labels(self):
        """Recompute every row's state chip from current facts."""
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            if item is None:
                continue
            widget = self._widget_for_item(item)
            if widget is None:
                continue
            widget.lbl_state.setText(self.row_state_text(i))

    def update_tab_count(self):
        if self._batch_depth:
            self._tab_stats_dirty = True
            return
        active = 0
        sleeping = 0
        ws_role = Qt.UserRole + workspace_manager.WORKSPACE_ROLE
        current_ws = getattr(self.window, "current_workspace_id", workspace_manager.PRIMARY_WORKSPACE_ID)
        for i, browser in enumerate(self.browsers):
            item = self.tab_list.item(i) if i < self.tab_list.count() else None
            if item and item.data(ws_role) != current_ws:
                continue
            metadata = self._metadata_for_item(item)
            hibernated = bool(metadata.get("hibernated"))
            if browser is not None:
                try:
                    hibernated = bool(browser.property("hibernated"))
                except Exception:
                    pass
            if hibernated:
                sleeping += 1
            else:
                active += 1
        self.lbl_tab_count.setText(f"{active} live · {sleeping} sleeping")
        self.refresh_row_state_labels()
        if hasattr(self.window, "refresh_insight_summary"):
            self.window.refresh_insight_summary()

    def change_tab(self, i):
        if i == -1 or i >= len(self.browsers):
            return
        browser = self.browsers[i]
        if browser is None:
            browser = self._materialize_tab(i)
            if browser is None:
                return
        # Reset the find bar: highlights belong to the previous tab (v6.5
        # find bar carried stale matches across tab switches).
        close_find = getattr(self.window, "_close_find_bar", None)
        if close_find is not None:
            try:
                close_find()
            except Exception:
                pass
        self.stack.setCurrentWidget(browser)
        pending = browser.property("pending_url")
        if pending:
            browser.setProperty("pending_url", None)
            browser.setProperty("hibernated", False)
            url_str = pending.toString()
            if url_str == "about:newtab":
                browser.page().setHtml(self.window.get_new_tab_html(), QUrl("about:newtab"))
            else:
                browser.setUrl(pending)
            item = self.tab_list.item(i)
            self._clear_hibernated_visual(item)
        self._refresh_hibernate_timers(active_index=i)
        self.window.update_urlbar(browser.url(), browser)
        self.window.update_zoom_label()
        self.window.sync_navigation(browser)
        self.window.on_load_progress(1 if browser.property("mei_loading") else 100, browser)
        self._enforce_background_hibernation(active_index=i)

    def _apply_hibernated_visual(self, item):
        widget = self._widget_for_item(item)
        if not widget:
            return
        metadata = dict(item.data(TAB_META_ROLE) or {})
        metadata["hibernated"] = True
        item.setData(TAB_META_ROLE, metadata)
        row = self.tab_list.row(item)
        widget.lbl_state.setText("Zz" if row < 0 else self.row_state_text(row))
        widget.lbl_title.setStyleSheet(
            f"color: {self._pal['TEXT_MUTED']}; font-size: 11px; font-weight: 600; background: transparent;"
        )

    def _clear_hibernated_visual(self, item):
        widget = self._widget_for_item(item)
        if not widget:
            return
        metadata = dict(item.data(TAB_META_ROLE) or {})
        metadata["hibernated"] = False
        item.setData(TAB_META_ROLE, metadata)
        row = self.tab_list.row(item)
        widget.lbl_state.setText(self.row_state_text(row) if row >= 0 else "")
        widget.lbl_title.setStyleSheet(
            (
                f"color: {self._pal['ACCENT_HOVER']}; font-size: 11px; font-weight: 700; background: transparent;"
            )
            if item.data(TAB_PINNED_ROLE)
            else (f"color: {self._pal['TEXT']}; font-size: 11px; font-weight: 600; background: transparent;")
        )
        # The group dot lives outside hibernation styling — re-apply it.
        row = self.tab_list.row(item)
        if row >= 0:
            self._apply_group_visual(row)

    def hibernate_tab(self, browser, item, refresh=True):
        if (
            not item
            or browser is None
            or browser == self.current_browser()
            or browser.property("hibernated")
            or item.data(TAB_PINNED_ROLE)
        ):
            return
        pending = browser.property("pending_url")
        current_url = pending.toString() if isinstance(pending, QUrl) and pending.isValid() else browser.url().toString()
        if current_url == "about:blank":
            logical_url = self._metadata_for_item(item).get("url", "")
            if logical_url == "about:newtab":
                current_url = logical_url
        if current_url == "about:blank":
            return
        try:
            browser.stop()
        except Exception:
            pass
        row = self.tab_list.row(item)
        if row < 0 or row >= len(self.browsers):
            return
        timer = browser.property("hibernate_timer")
        if timer:
            timer.stop()
        self._set_metadata(item, url=current_url, hibernated=True)
        dormant = self._make_dormant_view(
            self._metadata_for_item(item).get("title") or browser.title(),
            current_url,
        )
        self.stack.removeWidget(browser)
        self.stack.insertWidget(row, dormant)
        self.browsers[row] = None
        self._dispose_browser(browser)
        self._apply_hibernated_visual(item)
        if refresh:
            self.update_tab_count()

    def _enforce_background_hibernation(self, active_index=None):
        if len(self.browsers) <= self.auto_hibernate_threshold:
            return
        if active_index is None:
            active_index = self.tab_list.currentRow()
        changed = False
        for i, browser in enumerate(self.browsers):
            if i == active_index:
                continue
            if browser is not None and not browser.property("hibernated"):
                item = self.tab_list.item(i)
                self.hibernate_tab(browser, item, refresh=False)
                changed = True
        if changed:
            self.update_tab_count()

    def close_tab_item(self, item):
        self.hide_tab_memory_tooltip()
        row = self.tab_list.row(item)
        if row != -1:
            if item.data(TAB_PINNED_ROLE):
                # Chrome/Edge/FF UX: clicking the close button on a pinned tab
                # unpins it instead of nagging with a modal (v6.4 blocked close).
                self.set_tab_pinned(row, False)
                return
            self.close_tab(row)

    def set_tab_group(self, i, name: str = "", color: str = ""):
        """Assign/remove a Chrome-style colored group for row ``i``.

        The group shows as a colored dot in the left gutter (title stays
        clean — a text prefix wasted horizontal space in a slim desk)."""
        item = self.tab_list.item(i)
        if item is None:
            return
        item.setData(TAB_GROUP_ROLE, str(name or ""))
        item.setData(TAB_GROUP_COLOR_ROLE, str(color or ""))
        widget = item.data(TAB_WIDGET_ROLE)
        if widget is None:
            return
        dot = getattr(widget, "lbl_group", None)
        if dot is None:
            return
        if name:
            dot.setStyleSheet(
                f"background: {color or self._pal.get('ACCENT', '')}; border-radius: 3px; border: none;"
            )
            dot.setVisible(True)
            dot.setToolTip(f"Group: {name}")
        else:
            dot.setStyleSheet("background: transparent; border-radius: 3px; border: none;")
            dot.setVisible(False)
            dot.setToolTip("")

    def _apply_group_visual(self, i):
        item = self.tab_list.item(i)
        if item is None:
            return
        name = item.data(TAB_GROUP_ROLE) or ""
        color = item.data(TAB_GROUP_COLOR_ROLE) or ""
        if name:
            self.set_tab_group(i, name, color)

    def toggle_group_collapse(self, group_name: str):
        """Fold/unfold a colored group on the desk.

        Collapsed hides every member row except the currently-selected one;
        expanding shows them all. Per-window, non-persistent by design."""
        if not group_name:
            return
        members = []
        collapsed_now = False
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            if item is None or (item.data(TAB_GROUP_ROLE) or "") != group_name:
                continue
            members.append(item)
            collapsed_now = bool(item.data(TAB_GROUP_COLLAPSED_ROLE))
        new_state = not collapsed_now
        for item in members:
            item.setData(TAB_GROUP_COLLAPSED_ROLE, new_state)
        # Re-run the visibility pass so hidden/show applies immediately.
        apply_visibility = getattr(self.window, "_apply_tab_list_visibility", None)
        if apply_visibility is not None:
            apply_visibility()
        self.update_tab_count()
        state_lbl = "folded" if new_state else "unfolded"
        flash = getattr(self.window, "_flash_status", None)
        if flash is not None:
            flash(f"Group '{group_name}' {state_lbl}")

    def set_tab_pinned(self, i, pinned):
        """Toggle pin state for row ``i``; keeps visuals in sync.

        v6.4's context-menu handler read the label from ``Qt.UserRole`` which
        nothing ever set, so "Pin / Unpin" silently did nothing."""
        item = self.tab_list.item(i)
        if item is None:
            return
        widget = item.data(TAB_WIDGET_ROLE)
        item.setData(TAB_PINNED_ROLE, bool(pinned))
        if widget is None:
            return
        lbl = getattr(widget, "lbl_title", None)
        state_lbl = getattr(widget, "lbl_state", None)
        pal = getattr(self, "_pal", None) or {}
        accent = pal.get("ACCENT_HOVER", "#f0b84a")
        text_color = pal.get("TEXT", "#4a4037")
        if state_lbl is not None:
            state_lbl.setText("Pin" if pinned else "")
        if lbl is None:
            return
        if pinned:
            if not lbl.text().startswith("Pin  "):
                lbl.setText("Pin  " + lbl.text())
            lbl.set_title_style(
                f"color: {accent}; font-size: 11px; font-weight: 700; background: transparent;"
            )
        else:
            lbl.setText(lbl.text().replace("Pin  ", ""))
            lbl.set_title_style(
                f"color: {text_color}; font-size: 11px; font-weight: 600; background: transparent;"
            )
        self._refresh_hibernate_timers()

    def close_tab(self, i):
        if i < 0 or i >= len(self.browsers):
            return
        item = self.tab_list.item(i)
        if item and item.data(TAB_PINNED_ROLE):
            # Chrome/Edge/FF UX: clicking the close button on a pinned tab
            # unpins it instead of nagging with a modal (v6.4 blocked close).
            self.set_tab_pinned(i, False)
            return
        if self.tab_list.count() < 2:
            # Standard browser behaviour: closing the last tab lands on a fresh
            # new-tab page instead of silently refusing to close (v6.4 UX).
            browser = self.browsers[i]
            if browser is not None:
                browser.page().setHtml(self.window.get_new_tab_html(), QUrl("about:newtab"))
                item = self.tab_list.item(i)
                if item is not None:
                    item.setText("New Tab")
                    self._set_metadata(item, url="about:newtab")
            return
        metadata = dict(item.data(TAB_META_ROLE) or {})
        metadata["pinned"] = bool(item.data(TAB_PINNED_ROLE))
        metadata["workspace_id"] = item.data(Qt.UserRole + workspace_manager.WORKSPACE_ROLE)
        browser_at_row = self.browsers[i]
        metadata["hibernated"] = bool(
            metadata.get("hibernated")
            if browser_at_row is None
            else browser_at_row.property("hibernated")
        )
        self.window.remember_closed_tab(metadata)
        current_row = self.tab_list.currentRow()
        if i < current_row:
            next_row = current_row - 1
        elif i == current_row:
            next_row = min(i, self.tab_list.count() - 2)
        else:
            next_row = current_row
        browser = self.browsers.pop(i)
        # QListWidget emits currentRowChanged synchronously.  Keep the list
        # and stack aligned first, then select the replacement tab once.
        blocker = QSignalBlocker(self.tab_list)
        self.tab_list.takeItem(i)
        del blocker
        stack_widget = self.stack.widget(i)
        if stack_widget is not None:
            self.stack.removeWidget(stack_widget)
        if browser is not None:
            self._dispose_browser(browser)
        elif stack_widget is not None:
            stack_widget.deleteLater()
        if self.tab_list.count():
            blocker = QSignalBlocker(self.tab_list)
            self.tab_list.setCurrentRow(max(0, next_row))
            del blocker
            self.change_tab(self.tab_list.currentRow())
        self.update_tab_count()

    def duplicate_current_tab(self):
        i = self.tab_list.currentRow()
        if i >= 0:
            self.duplicate_tab_at_row(i)

    def duplicate_tab_at_row(self, row):
        if row < 0 or row >= len(self.browsers):
            return
        item = self.tab_list.item(row)
        metadata = dict(item.data(TAB_META_ROLE) or {})
        url = metadata.get("url") or "https://google.com"
        metadata["pinned"] = bool(item.data(TAB_PINNED_ROLE))
        metadata["workspace_id"] = item.data(Qt.UserRole + workspace_manager.WORKSPACE_ROLE)
        self.add_tab(QUrl(url), metadata.get("title") or "Tab", is_active=True, session_data=metadata)

    def optimize_memory(self, notify=True):
        current_i = self.tab_list.currentRow()
        count = 0
        for i in range(self.tab_list.count()):
            if i != current_i:
                browser = self.browsers[i]
                if browser is not None and not browser.property("hibernated"):
                    self.hibernate_tab(browser, self.tab_list.item(i), refresh=False)
                    count += 1
        if count > 0:
            self.update_tab_count()
            if notify:
                QMessageBox.information(self.window, "Memory Saver", f"Suspended {count} background tabs.")
        return count

    def refresh_theme(self):
        """Re-paint the tab desk for the theme that is in effect now.

        Rows carry inline styles (glyph, state chip, close button, plus the
        pinned/hibernated title tints), so a stylesheet re-apply on the window is
        not enough: every existing row is re-resolved from the new palette.
        Called by SearchWindow.refresh_chrome_theme when the resolved theme
        changes (auto day/night at 06:00 and 18:00, or a theme picked in Settings).
        """
        from litebrowser.core import theme_data

        mode = prefs.resolved_auto_theme(self.base_dir) if self.base_dir else theme_data.DEFAULT_THEME
        self._pal = theme_data._palette(mode, prefs.get_accent(self.base_dir) if self.base_dir else None)
        for row in range(self.tab_list.count()):
            item = self.tab_list.item(row)
            widget = item.data(TAB_WIDGET_ROLE) if item is not None else None
            if widget is None or not hasattr(widget, "apply_theme"):
                continue
            widget.apply_theme()
            metadata = dict(item.data(TAB_META_ROLE) or {})
            if metadata.get("hibernated"):
                # Re-applies the muted title tint and the "Zz" chip.
                self._apply_hibernated_visual(item)
            else:
                # Re-applies pinned (accent) vs normal (body) title colours.
                self._clear_hibernated_visual(item)
        if self._mem_tip is not None:
            # The overlay was built with the previous palette; drop it so the next
            # hover rebuilds it on-theme instead of reusing stale colours.
            self._mem_tip.hide()
            self._mem_tip.deleteLater()
            self._mem_tip = None

    def _memory_tip(self):
        if self._mem_tip is None:
            parent = getattr(self.window, "sidebarWidget", self.window)
            self._mem_tip = TabMemoryTip(parent, self._pal)
        return self._mem_tip

    def hide_tab_memory_tooltip(self):
        if self._mem_tip is not None:
            self._mem_tip.hide()

    def _position_memory_tip(self, item):
        """Move the non-native overlay next to the hovered row, inside the sidebar."""
        tip = self._memory_tip()
        parent = tip.parentWidget()
        if parent is None:
            return
        row_rect = self.tab_list.visualItemRect(item)
        if row_rect.isNull():
            return
        pos = self.tab_list.viewport().mapTo(parent, row_rect.topLeft())
        tip.adjustSize()
        width = tip.width()
        height = tip.height()
        x = max(4, min(pos.x(), max(4, parent.width() - width - 4)))
        y = pos.y() - height - 6
        if y < 4:
            y = pos.y() + row_rect.height() + 6
        tip.move(x, y)
        tip.raise_()
        tip.show()

    def show_tab_memory_tooltip(self, item):
        row = self.tab_list.row(item)
        if row < 0 or row >= len(self.browsers):
            return
        browser = self.browsers[row]
        metadata = dict(item.data(TAB_META_ROLE) or {})
        if browser is None or browser.property("hibernated"):
            self._memory_tip().setText(
                f"{(metadata.get('title') or 'Tab')[:60]}\nSuspended tab · RAM: ~0 MB\nReloads when you select it"
            )
            self._position_memory_tip(item)
            return

        # Throttle the JS-heap probe: v6.4 fired a runJavaScript round-trip on
        # every hover; 10 s per tab is plenty for an estimate bubble.
        now_ms = time.monotonic() * 1000.0
        last = browser.property("heap_probe_at") or 0.0
        cached_hint = browser.property("memory_hint_mb") or 0.0
        if now_ms - last < 10_000.0 and cached_hint:
            self._show_memory_estimate(item, browser, metadata, cached_hint)
            return
        browser.setProperty("heap_probe_at", now_ms)
        browser.page().runJavaScript(
            "(function(){try{return (performance && performance.memory) ? (performance.memory.usedJSHeapSize/1048576) : 0;}catch(e){return 0;}})();",
            lambda result, b=browser, m=metadata, i=item: self._show_memory_result(result, b, m, i),
        )

    def _show_memory_result(self, result, browser, metadata, item):
        # The cursor may have left the row while the page answered.
        if self._hovered_item is not item:
            return
        try:
            heap_mb = float(result or 0.0)
        except Exception:
            heap_mb = 0.0
        rough_ram = max(24.0, heap_mb * 2.4)
        browser.setProperty("memory_hint_mb", rough_ram)
        self._show_memory_estimate(item, browser, metadata, rough_ram, heap_mb)

    def _show_memory_estimate(self, item, browser, metadata, rough_ram, heap_mb=None):
        title = (metadata.get("title") or "Tab")[:60]
        host = ""
        url = metadata.get("url") or ""
        if url and url.startswith("http"):
            from urllib.parse import urlparse
            host = (urlparse(url).netloc or "")[:40]
        if heap_mb is None:
            self._memory_tip().setText(
                f"{title}\n{host}\nEstimated RAM: ~{rough_ram:.1f} MB"
            )
        else:
            self._memory_tip().setText(
                f"{title}\n{host}\nJS heap: {heap_mb:.1f} MB · Estimated RAM: {rough_ram:.1f} MB"
            )
        self._position_memory_tip(item)
