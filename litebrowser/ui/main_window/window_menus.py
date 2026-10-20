# Mei - window mixins: context menus and the extension import center.
#
# Extracted from window.py (AST-verified cut) so menu logic is reviewable
# separately from browser state. Methods only touch SearchWindow-owned
# attributes (tab_list, base_dir, tab_manager, ...).

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from litebrowser.browser.tab_manager import (
    TAB_GROUP_COLLAPSED_ROLE,
    TAB_GROUP_COLORS,
    TAB_GROUP_ROLE,
    TAB_META_ROLE,
    TAB_PINNED_ROLE,
)
from litebrowser.core import app_paths, app_version
from litebrowser.services import extension_bridge, workspace_manager
from litebrowser.ui import dialogs
from litebrowser.ui.dialogs.common import (
    dialog_footer,
    ghost_button,
    icon_button,
    primary_button,
)


class MenusMixin:
    """Tab/bookmark context menus, options menu, extension import center."""

    def _build_options_menu(self):
        menu = QMenu(self)
        hub_menu = menu.addMenu("Project Hub \u2014 App Chain")
        for site in app_paths.bundled_sites(getattr(self, "app_dir", None)):
            if not site.get("url") and not site.get("remote"):
                continue
            hub_menu.addAction(site["display"]).triggered.connect(
                lambda checked, site_key=site["key"]: self.open_bundled_site(site_key)
            )
        menu.addAction("Open Project Hub").triggered.connect(self.open_project_hub)
        menu.addAction("Help & Browser tools...").triggered.connect(lambda: dialogs.show_browser_control_center(self))
        menu.addAction(f"Check for updates ({app_version.APP_VERSION})...").triggered.connect(self._check_for_updates_from_browser)
        menu.addSeparator()

        sessions_menu = menu.addMenu("Sessions & Spaces")
        sessions_menu.addAction("New Incognito Tab (Ctrl+Shift+N)").triggered.connect(lambda: self.add_new_tab(is_incognito=True))
        sessions_menu.addAction("Workspaces...").triggered.connect(lambda: dialogs.show_workspace_dialog(self))
        sessions_menu.addAction("Profiles...").triggered.connect(lambda: dialogs.show_profiles_dialog(self, getattr(self, "app_dir", self.base_dir)))
        sessions_menu.addAction("On Startup...").triggered.connect(lambda: dialogs.show_startup_dialog(self))
        sessions_menu.addAction("Reopen Closed Tab (Ctrl+Shift+T)").triggered.connect(self.reopen_closed_tab)
        sessions_menu.addAction("Reopen Closed Window").triggered.connect(self.reopen_closed_window)
        sessions_menu.addAction("Quick Switcher (Ctrl+Shift+K)").triggered.connect(lambda: dialogs.show_quick_switcher(self))
        sessions_menu.addAction("Save Research Workspace...").triggered.connect(
            lambda: dialogs.show_save_research_workspace_dialog(self)
        )
        sessions_menu.addAction("Save Current Tab Set...").triggered.connect(self.save_current_tab_set)
        sessions_menu.addAction("Restore Tab Set...").triggered.connect(lambda: dialogs.show_tab_sets_dialog(self))

        tabs_menu = menu.addMenu("Tab Center")
        tabs_menu.addAction("Find tab (Ctrl+Shift+F)").triggered.connect(self.focus_tab_filter)
        tabs_menu.addAction("Suspend background tabs (Ctrl+Shift+M)").triggered.connect(
            lambda: self.tab_manager.optimize_memory()
        )
        tabs_menu.addAction("Close duplicate URLs in this workspace").triggered.connect(self.close_duplicate_tabs)
        tabs_menu.addAction("Copy visible workspace URLs").triggered.connect(self.copy_workspace_urls)
        tabs_menu.addAction("Group tabs by domain").triggered.connect(self.group_tabs_action)

        capture_menu = menu.addMenu("Read & Save")
        capture_menu.addAction("Capture Web Screenshot (Ctrl+S)").triggered.connect(self.capture_screenshot)
        capture_menu.addAction("Extract All Text (Ctrl+Shift+E)").triggered.connect(self.extract_text)
        capture_menu.addAction("Print Page").triggered.connect(self.print_page)
        capture_menu.addAction("Save PDF").triggered.connect(self.save_page_pdf)
        capture_menu.addAction("Save Page to Library").triggered.connect(self.save_current_page_to_library)
        capture_menu.addAction("Create Note from Current Page").triggered.connect(self.capture_page_as_note)

        privacy_menu = menu.addMenu("Privacy & Performance")
        privacy_menu.addAction("Security (HTTPS, Adblock, Passwords)...").triggered.connect(lambda: dialogs.show_privacy_dialog(self))
        privacy_menu.addAction("VPN / Proxy (Quick)...").triggered.connect(lambda: dialogs.show_vpn_hub(self))
        privacy_menu.addAction("VPN / Proxy (Detailed)...").triggered.connect(lambda: dialogs.show_vpn_dialog(self))
        privacy_menu.addAction("Tab Hibernation Timeout...").triggered.connect(lambda: dialogs.show_hibernate_pref_dialog(self))
        self.act_defer_background = privacy_menu.addAction("Background loading priority (lazy-load background tabs)")
        self.act_defer_background.setCheckable(True)
        self.act_defer_background.triggered.connect(self.toggle_defer_background)
        privacy_menu.addAction("Freeze All Background Tabs").triggered.connect(
            lambda: self.tab_manager.optimize_memory()
        )
        privacy_menu.addAction("Performance dashboard").triggered.connect(self.show_performance_dashboard)
        # Follows the shell's light/dark mode until the user flips it once; the
        # tooltip says so, because "Force" no longer describes the default.
        self.act_dark_mode = privacy_menu.addAction("Dark Mode on Web")
        self.act_dark_mode.setCheckable(True)
        self.act_dark_mode.setToolTip(
            "Darken web pages to match the app. Follows the app's light/dark mode "
            "(including auto day/night) until you set it yourself."
        )
        self.act_dark_mode.triggered.connect(self.toggle_dark_web)
        self.act_dynamic_bg = privacy_menu.addAction("Animated Gradient Sidebar")
        self.act_dynamic_bg.setCheckable(True)
        self.act_dynamic_bg.triggered.connect(self.toggle_ui_dynamic_background)
        self.act_data_saver = privacy_menu.addAction("Data Saver (Skip Images on New Pages)")
        self.act_data_saver.setCheckable(True)
        self.act_data_saver.triggered.connect(self.toggle_data_saver)
        self.act_disable_webgl = privacy_menu.addAction("Lite Rendering (Disable WebGL)")
        self.act_disable_webgl.setCheckable(True)
        self.act_disable_webgl.triggered.connect(self.toggle_disable_webgl)
        self.act_block_3p_cookies = privacy_menu.addAction("Block Third-Party Cookies")
        self.act_block_3p_cookies.setCheckable(True)
        self.act_block_3p_cookies.triggered.connect(self.toggle_block_third_party_cookies)
        privacy_menu.addAction("Refresh adblock filters").triggered.connect(self._refresh_adblock_now)
        privacy_menu.addAction("Save Password for This Page").triggered.connect(lambda: dialogs.show_save_password_dialog(self))

        data_menu = menu.addMenu("Data & Tools")
        data_menu.addAction("History").triggered.connect(self.show_history_dialog)
        data_menu.addAction("Bookmarks").triggered.connect(self.show_bookmarks_dialog)
        data_menu.addAction("Downloads").triggered.connect(self.show_downloads_dialog)
        data_menu.addAction("Extensions").triggered.connect(self.show_extensions_dialog)
        data_menu.addAction("Safe Vault").triggered.connect(self.show_vault)
        data_menu.addAction("Open LinkLumina Backup Folder...").triggered.connect(self.open_linklumina_archive_folder)
        data_menu.addAction("Extension Import Center").triggered.connect(self.show_extension_import_center)
        account_menu = data_menu.addMenu("Google account")
        account_menu.addAction("Configure OAuth Client ID...").triggered.connect(self.configure_google_oauth_client_id)
        account_menu.addAction("Test OAuth configuration...").triggered.connect(self.test_google_oauth_configuration)
        account_menu.addAction("Sign in for Mei...").triggered.connect(self.start_google_oauth_sign_in)
        account_menu.addAction("Show signed-in account").triggered.connect(self.show_google_account_status)
        account_menu.addAction("Sign out").triggered.connect(self.sign_out_google_account)
        return menu

    def show_tab_context_menu(self, pos):
        item = self.tab_list.itemAt(pos)
        if not item:
            return
        row = self.tab_list.row(item)
        if row < 0 or row >= len(self.browsers):
            return
        browser = self.browsers[row]
        is_current = browser is not None and browser == self.current_browser()
        is_pinned = bool(item.data(TAB_PINNED_ROLE))
        menu = QMenu(self)  # parented: inherits the shell theme QSS
        copy_url_action = menu.addAction("Copy tab URL")
        split_action = menu.addAction("Show beside (split view)")
        split_action.setEnabled(browser is not None)
        reopen_incognito_action = menu.addAction("Reopen in incognito")
        suspend_action = menu.addAction("Suspend tab")
        suspend_action.setEnabled(browser is not None and not is_current and not is_pinned)
        mute_action = menu.addAction("Mute / Unmute")
        mute_action.setEnabled(browser is not None)
        reload_action = menu.addAction("Auto-Reload (10s)")
        reload_action.setEnabled(browser is not None)
        pin_action = menu.addAction("Pin / Unpin")
        dup_action = menu.addAction("Duplicate Tab")
        # Chrome-style colored tab groups: assign or strip via submenu.
        group_menu = menu.addMenu("Add to group")
        current_group = item.data(TAB_GROUP_ROLE) or ""
        group_actions = {}
        for g_name, g_color in TAB_GROUP_COLORS:
            g_act = group_menu.addAction(f"●  {g_name}")
            g_act.setData(g_color)
            group_actions[g_act] = (g_name, g_color)
        remove_group_action = group_menu.addAction("Remove group")
        remove_group_action.setEnabled(bool(current_group))
        if current_group:
            group_collapsed = bool(item.data(TAB_GROUP_COLLAPSED_ROLE))
            toggle_fold_action = group_menu.addAction("Expand group" if group_collapsed else "Collapse group")
        move_menu = menu.addMenu("Move to workspace")
        workspace_actions = {}
        for workspace in workspace_manager.get_workspaces_list(self.base_dir):
            move_action = move_menu.addAction(workspace.get("name") or "Workspace")
            workspace_actions[move_action] = workspace.get("id")
        menu.addSeparator()
        close_others_action = menu.addAction("Close other tabs in this workspace")
        close_action = menu.addAction("Close Tab")
        close_action.setEnabled(not is_pinned)
        action = menu.exec_(self.tab_list.mapToGlobal(pos))
        metadata = dict(item.data(TAB_META_ROLE) or {})
        if action == copy_url_action:
            url = metadata.get("url", "")
            if not url and browser is not None:
                try:
                    url = browser.url().toString()
                except Exception:
                    url = ""
            if url:
                QApplication.clipboard().setText(url)
        elif action == split_action:
            url = metadata.get("url", "")
            if not url and browser is not None:
                try:
                    url = browser.url().toString()
                except Exception:
                    url = ""
            if url:
                self.open_split_view(url, metadata.get("title") or "Split")
        elif action == reopen_incognito_action:
            url = metadata.get("url", "")
            if not url and browser is not None:
                try:
                    url = browser.url().toString()
                except Exception:
                    url = ""
            if url and url.startswith("http"):
                self.add_new_tab(QUrl(url), metadata.get("title") or "Incognito", is_active=True, is_incognito=True)
                self._flash_status("Reopened in incognito")
        elif action == suspend_action:
            if browser is not None:
                self.tab_manager.hibernate_tab(browser, item)
        elif action in workspace_actions:
            target_workspace = workspace_actions.get(action)
            if target_workspace:
                item.setData(Qt.UserRole + workspace_manager.WORKSPACE_ROLE, target_workspace)
                self._apply_workspace_filter()
        elif action == close_others_action:
            ws_role = Qt.UserRole + workspace_manager.WORKSPACE_ROLE
            current_workspace = item.data(ws_role)
            rows_to_close = [
                idx
                for idx in range(self.tab_list.count())
                if idx != row
                and self.tab_list.item(idx).data(ws_role) == current_workspace
                and not bool(self.tab_list.item(idx).data(TAB_PINNED_ROLE))
            ]
            for idx in reversed(rows_to_close):
                self.tab_manager.close_tab(idx)
        elif action == mute_action:
            if browser is None:
                return
            browser.page().setAudioMuted(not browser.page().isAudioMuted())
            state = "Muted" if browser.page().isAudioMuted() else "Unmuted"
            self._flash_status(f"{state} for this tab")
        elif action == reload_action:
            if browser is None:
                return
            timer = browser.property("auto_reload_timer")
            if timer:
                timer.stop()
                browser.setProperty("auto_reload_timer", None)
                self._flash_status("Auto-reload turned OFF")
            else:
                timer = QTimer(browser)
                timer.timeout.connect(browser.reload)
                timer.start(10000)
                browser.setProperty("auto_reload_timer", timer)
                self._flash_status("This tab will auto-reload every 10 seconds")
        elif action == pin_action:
            is_pinned = bool(item.data(TAB_PINNED_ROLE))
            self.tab_manager.set_tab_pinned(row, not is_pinned)
        elif action in group_actions:
            g_name, g_color = group_actions[action]
            self.tab_manager.set_tab_group(row, g_name, g_color)
            self._flash_status(f"Group '{g_name}' applied")
        elif action == remove_group_action:
            self.tab_manager.set_tab_group(row, "", "")
            self._flash_status("Group removed")
        elif current_group and action == toggle_fold_action:
            self.tab_manager.toggle_group_collapse(current_group)
        elif action == dup_action:
            self.tab_manager.duplicate_tab_at_row(row)
        elif action == close_action:
            self.tab_manager.close_tab(row)

    def _import_extension_batches_as_workspaces(self, batches):
        """Import a multi-screen extension export, one workspace per monitor.

        Screen 0 maps to Workspace 1, screen 1 to Workspace 2, and any further
        screens get a new workspace named after the batch label. Returns the
        total number of tabs imported.
        """
        ordered = sorted(
            batches,
            key=lambda b: (
                int(b.get("screen_index", -1)) if isinstance(b.get("screen_index"), int) else -1,
                b.get("window_id") or "",
            ),
        )
        # Fall back to import order for payloads without screen_index (old
        # single-window JSON or hand-written batches) so behavior is stable.
        if ordered and all(b.get("screen_index", -1) < 0 for b in ordered):
            ordered = list(batches)

        workspaces = workspace_manager.get_workspaces_list(self.base_dir)
        ws_ids = [w.get("id") for w in workspaces if isinstance(w, dict) and w.get("id")]
        used_ws = set()
        total = 0

        for idx, batch in enumerate(ordered):
            tabs = batch.get("tabs") or []
            if not tabs:
                continue
            if idx < len(ws_ids):
                ws_id = ws_ids[idx]
            else:
                label = (batch.get("source_label") or f"Window {batch.get('window_id', idx)}").strip()
                ws_id = workspace_manager.add_workspace(self.base_dir, label)
            used_ws.add(ws_id)
            active_index = next((i for i, tab in enumerate(tabs) if tab.get("active")), 0)
            imported = 0
            for tab_idx, tab in enumerate(tabs):
                url = tab.get("url") or ""
                if not url:
                    continue
                self.tab_manager.add_tab(
                    QUrl(url),
                    tab.get("title") or "Imported tab",
                    is_active=False,
                    session_data={
                        "url": url,
                        "title": tab.get("title") or url,
                        "pinned": bool(tab.get("pinned")),
                        "active": tab_idx == active_index,
                        "workspace_id": ws_id,
                    },
                )
                imported += 1
            if imported:
                extension_bridge.mark_batch_imported(self.base_dir, batch.get("id", ""))
            total += imported

        if used_ws:
            self._refresh_workspace_combo()
            self._apply_workspace_filter()
        return total

    def show_extension_import_center(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Extension Import Center")
        dialog.resize(820, 620)
        dialog.setStyleSheet(self._dialog_stylesheet())
        layout = QVBoxLayout(dialog)

        help_label = QLabel(
            "Paste a JSON payload from a Chrome/Opera GX extension (or open a .json/.zip export), "
            "then import all tabs into the current workspace — or use Import All as Workspaces "
            "to split a multi-screen export back into one Mei workspace per monitor."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        batch_list = QListWidget()
        layout.addWidget(batch_list, 1)

        payload_box = QTextEdit()
        payload_box.setPlaceholderText(
            '{\n'
            '  "batch_id": "chrome_123",\n'
            '  "window_id": 123,\n'
            '  "source_browser": "chrome",\n'
            '  "source_label": "Work Window",\n'
            '  "tabs": [{"url": "https://example.com", "title": "Example", "active": true}]\n'
            '}'
        )
        payload_box.setMaximumHeight(220)
        layout.addWidget(payload_box)

        # Six equal boxes became one import verb, one file picker and a menu for
        # the batch bookkeeping (storing, refreshing, splitting per screen).
        btn_import_selected = primary_button("Import selected batch")
        btn_import_file = ghost_button("Import a file…", "Open a .json / .zip export from the extension")
        btn_refresh = icon_button("↻", "Reload the saved batches from disk")

        def refresh():
            self._refresh_extension_import_list(batch_list)

        def save_payload():
            text = payload_box.toPlainText().strip()
            if not text:
                QMessageBox.information(dialog, "Extension import", "Paste a JSON payload from the extension.")
                return
            try:
                batch = extension_bridge.import_from_json_text(self.base_dir, text)
            except Exception as exc:
                QMessageBox.warning(dialog, "Extension import", str(exc))
                return
            refresh()
            payload_box.clear()
            QMessageBox.information(
                dialog,
                "Extension import",
                f"Saved batch {batch.get('source_label', batch.get('id', ''))} with {batch.get('tab_count', 0)} tabs.",
            )

        def import_file():
            path, _ = QFileDialog.getOpenFileName(
                dialog,
                "Import extension payload",
                "",
                "JSON & ZIP (*.json *.zip);;JSON Files (*.json);;ZIP Archives (*.zip);;All Files (*.*)",
            )
            if not path:
                return
            try:
                batch = extension_bridge.import_from_file(self.base_dir, path)
            except Exception as exc:
                QMessageBox.warning(dialog, "Extension import", str(exc))
                return
            refresh()
            QMessageBox.information(
                dialog,
                "Extension import",
                f"Loaded file into batch {batch.get('source_label', batch.get('id', ''))} with {batch.get('tab_count', 0)} tabs.",
            )

        def import_selected():
            item = batch_list.currentItem()
            if not item:
                QMessageBox.information(dialog, "Extension import", "Please select a batch to import.")
                return
            batch = item.data(Qt.UserRole) or {}
            count = self._import_extension_batch_into_tabs(batch)
            refresh()
            if count:
                QMessageBox.information(dialog, "Extension import", f"Imported {count} tabs into the browser.")

        def import_all_as_workspaces():
            batches = extension_bridge.load_batches(self.base_dir)
            pending = [b for b in batches if not b.get("imported_at")]
            if not pending:
                QMessageBox.information(dialog, "Extension import", "No un-imported batches. Use Import Selected Batch to re-import one.")
                return
            count = self._import_extension_batches_as_workspaces(pending)
            refresh()
            if count:
                QMessageBox.information(
                    dialog,
                    "Extension import",
                    f"Imported {count} tabs across {len(pending)} window(s), one Mei workspace per screen.",
                )

        btn_refresh.clicked.connect(refresh)
        btn_import_file.clicked.connect(import_file)
        btn_import_selected.clicked.connect(import_selected)
        batch_list.itemDoubleClicked.connect(lambda _item: import_selected())
        dialog_footer(
            layout,
            primary=btn_import_selected,
            secondary=(btn_refresh, btn_import_file),
            menu=(
                ("Store the pasted payload", save_payload),
                (None, None),
                ("Import all as workspaces (one per screen)", import_all_as_workspaces),
            ),
            close=dialog.accept,
        )

        refresh()
        dialog.exec_()
        self.invalidate_extension_cache()
