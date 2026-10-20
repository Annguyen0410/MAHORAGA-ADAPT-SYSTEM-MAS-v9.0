"""Dialog helpers for browser and shell."""
import json
import os
import re
import shutil
import time

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtNetwork import QNetworkProxy
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from litebrowser.core import prefs, time_utils
from litebrowser.services import life_service, personal_service, tab_sets
from litebrowser.ui.dialogs.common import (
    _stylesheet,
    dialog_footer,
    ghost_button,
    icon_button,
    primary_button,
)


def show_vpn_dialog(parent):
    base_dir = parent.base_dir
    dialog = QDialog(parent)
    dialog.setWindowTitle("VPN / Proxy")
    dialog.setGeometry(parent.x() + 200, parent.y() + 150, 420, 320)
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    layout.setAlignment(Qt.AlignCenter)
    form = QWidget()
    form_layout = QGridLayout(form)
    form_layout.setSpacing(12)
    lbl_type = QLabel("Type:")
    type_combo = QComboBox()
    type_combo.addItems(["HTTP", "SOCKS5"])
    form_layout.addWidget(lbl_type, 0, 0)
    form_layout.addWidget(type_combo, 0, 1)
    lbl_host = QLabel("Host:")
    host_input = QLineEdit()
    host_input.setPlaceholderText("127.0.0.1")
    form_layout.addWidget(lbl_host, 1, 0)
    form_layout.addWidget(host_input, 1, 1)
    lbl_port = QLabel("Port:")
    port_input = QLineEdit()
    port_input.setPlaceholderText("1080")
    form_layout.addWidget(lbl_port, 2, 0)
    form_layout.addWidget(port_input, 2, 1)
    lbl_user = QLabel("User (optional):")
    user_input = QLineEdit()
    user_input.setPlaceholderText("Leave blank if not needed")
    form_layout.addWidget(lbl_user, 3, 0)
    form_layout.addWidget(user_input, 3, 1)
    lbl_pass = QLabel("Password (optional):")
    pass_input = QLineEdit()
    pass_input.setPlaceholderText("Leave blank if not needed")
    pass_input.setEchoMode(QLineEdit.Password)
    form_layout.addWidget(lbl_pass, 4, 0)
    form_layout.addWidget(pass_input, 4, 1)
    lbl_pac = QLabel("PAC URL (optional):")
    pac_input = QLineEdit()
    pac_input.setPlaceholderText("https://example.com/proxy.pac — overrides host/port")
    form_layout.addWidget(lbl_pac, 5, 0)
    form_layout.addWidget(pac_input, 5, 1)
    layout.addWidget(form, alignment=Qt.AlignCenter)
    _cfg = prefs.get_proxy_config(base_dir)
    if _cfg:
        type_combo.setCurrentIndex(1 if str(_cfg.get("type", "")).upper() == "SOCKS5" else 0)
        host_input.setText(str(_cfg.get("host", "")))
        port_input.setText(str(_cfg.get("port", "")))
        user_input.setText(str(_cfg.get("user") or ""))
        pass_input.setText(str(_cfg.get("password") or ""))
        pac_input.setText(str(_cfg.get("pac_url") or ""))
    # Same three outcomes as before (1 = enable, 2 = disable, 0 = cancel), now
    # with one filled verb instead of three identical boxes.
    btn_apply = primary_button("Enable proxy")
    btn_apply.clicked.connect(lambda: dialog.done(1))
    btn_off = ghost_button("Disable proxy")
    btn_off.clicked.connect(lambda: dialog.done(2))
    dialog_footer(layout, primary=btn_apply, secondary=(btn_off,), close_label="Cancel")
    result = dialog.exec_()
    host = host_input.text().strip()
    port = port_input.text().strip()
    if result == 1:
        if not host:
            QMessageBox.warning(parent, "VPN / Proxy", "Please enter a proxy host.")
            return
        if not port.isdigit():
            QMessageBox.warning(parent, "VPN / Proxy", "Port must be an integer (1–65535).")
            return
        port_n = int(port)
        if port_n < 1 or port_n > 65535:
            QMessageBox.warning(parent, "VPN / Proxy", "Invalid port.")
            return
        # Normalize: HttpProxy only accepts "http", not "HTTP" from the combo; after .lower() -> "http" is fine; SOCKS5 -> "socks5"
        raw_type = type_combo.currentText().strip().upper()
        norm_type = "socks5" if raw_type.startswith("SOCKS") else "http"
        cfg = {
            "enabled": True,
            "type": norm_type,
            "host": host,
            "port": port_n,
            "user": user_input.text().strip() or None,
            "password": pass_input.text().strip() or None,
            "pac_url": pac_input.text().strip() or None,
        }
        prefs.set_proxy_config(base_dir, cfg)
        prefs.set_last_vpn_proxy(base_dir, cfg)
        parent._set_proxy_from_config(cfg)
        relaunch = getattr(parent, "smart_restart", None)
        dialog.done(1)
        if relaunch is not None:
            relaunch(reason=f"VPN connected: {host}:{port_n}")
        else:
            QMessageBox.information(parent, "VPN", f"Proxy {type_combo.currentText()} enabled: {host}:{port_n}\n\nRestart Mei to route all tabs through it.")
    elif result == 2:
        prefs.set_proxy_config(base_dir, {"enabled": False})
        prefs.set_auto_connect_vpn(base_dir, False)
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(
            tok for tok in existing.split() if not tok.startswith("--proxy-server=")
        ).strip()
        relaunch = getattr(parent, "smart_restart", None)
        dialog.done(2)
        if relaunch is not None:
            relaunch(reason="VPN disconnected")
        else:
            QMessageBox.information(
                parent,
                "VPN",
                "Proxy disabled. Restart Mei so web tabs no longer route through the proxy.",
            )


def show_startup_dialog(parent):
    base_dir = parent.base_dir
    dialog = QDialog(parent)
    dialog.setWindowTitle("On Startup")
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Behavior when Mei starts:"))
    combo = QComboBox()
    combo.addItem("Restore tabs (session)", "restore")
    combo.addItem("New Tab page", "newtab")
    combo.addItem("Home page (custom URL)", "home")
    mode, home_url = prefs.get_startup_prefs(base_dir)
    for i in range(combo.count()):
        if combo.itemData(i) == mode:
            combo.setCurrentIndex(i)
            break
    layout.addWidget(combo)
    layout.addWidget(QLabel("Home page URL (only when \"Home page\" is selected):"))
    home_edit = QLineEdit()
    home_edit.setPlaceholderText("https://google.com")
    home_edit.setText(home_url)
    layout.addWidget(home_edit)
    def save_startup():
        data = prefs.load_prefs(base_dir)
        data["startup_mode"] = combo.currentData()
        data["home_url"] = home_edit.text().strip() or "https://google.com"
        prefs.save_prefs(base_dir, data)
        QMessageBox.information(parent, "Saved", "Applied from the next time Mei opens.")
        dialog.accept()
    btn = primary_button("Save")
    btn.clicked.connect(save_startup)
    dialog_footer(layout, primary=btn)
    dialog.exec_()


def show_hibernate_pref_dialog(parent):
    base_dir = parent.base_dir
    dialog = QDialog(parent)
    dialog.setWindowTitle("Tab Hibernation Time")
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Inactive tabs will hibernate after:"))
    combo = QComboBox()
    combo.addItem("Off", 0)
    combo.addItem("1 minute", 60)
    combo.addItem("5 minutes", 300)
    combo.addItem("15 minutes", 900)
    combo.addItem("30 minutes", 1800)
    current = prefs.get_hibernate_seconds(base_dir)
    for i in range(combo.count()):
        if combo.itemData(i) == current:
            combo.setCurrentIndex(i)
            break
    layout.addWidget(combo)
    btn = primary_button("Save")
    btn.clicked.connect(dialog.accept)
    dialog_footer(layout, primary=btn)
    if dialog.exec_() == QDialog.Accepted:
        val = combo.currentData() if hasattr(combo, "currentData") else combo.itemData(combo.currentIndex())
        prefs.save_hibernate_seconds(base_dir, val)
        QMessageBox.information(parent, "Saved", "Applied to new tabs and the next hibernation.")


def show_history_dialog(parent):
    base_dir = parent.base_dir
    dialog = QDialog(parent)
    dialog.setWindowTitle("Browsing History")
    dialog.resize(620, 480)
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    search_edit = QLineEdit()
    search_edit.setPlaceholderText("Filter history by title or URL...")
    layout.addWidget(search_edit)
    list_widget = QListWidget()
    entries = prefs.load_history_entries(base_dir)
    entries.sort(key=lambda x: -x[0])
    history_data = list(entries)

    def refresh_list(query=""):
        list_widget.clear()
        ent = prefs.load_history_entries(base_dir)
        ent.sort(key=lambda x: -x[0])
        history_data.clear()
        history_data.extend(ent)
        q = (query or "").strip().lower()
        shown = 0
        for _ts, url in ent:
            if q and q not in url.lower():
                continue
            list_widget.addItem(url)
            shown += 1
            if shown >= 500:
                break
        if not shown:
            list_widget.addItem("No history yet...")

    search_edit.textChanged.connect(refresh_list)

    # Initial fill (unfiltered)
    for _ts, url in entries[:500]:
        list_widget.addItem(url)
    if not entries:
        list_widget.addItem("No history yet...")

    def clear_history(seconds_back):
        ent = prefs.load_history_entries(base_dir)
        now = int(time.time())
        if seconds_back is None:
            ent = []
        else:
            ent = [(t, u) for t, u in ent if now - t > seconds_back]
        prefs.save_history_entries(base_dir, ent)
        refresh_list()
        dialog.setWindowTitle("Browsing History (updated)")

    layout.addWidget(list_widget)

    def open_selected():
        item = list_widget.currentItem()
        if item and item.text() and item.text() != "No history yet...":
            parent.tab_manager.add_tab(QUrl(item.text()))
            dialog.accept()

    # Four look-alike "Delete …" boxes (one of them irreversible) became a single
    # tidy-up menu; opening the selected page is what the dialog is for.
    btn_open = primary_button("Open selected page")
    btn_open.clicked.connect(open_selected)
    dialog_footer(
        layout,
        primary=btn_open,
        menu=(
            ("Delete the last hour", lambda: clear_history(3600)),
            ("Delete the last 24 hours", lambda: clear_history(86400)),
            ("Delete the last 7 days", lambda: clear_history(7 * 86400)),
            (None, None),
            ("🗑  Delete everything", lambda: clear_history(None)),
        ),
    )
    dialog.exec_()


def show_bookmarks_dialog(parent):
    base_dir = parent.base_dir
    dialog = QDialog(parent)
    dialog.setWindowTitle("Bookmarks")
    dialog.resize(640, 480)
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    list_widget = QListWidget()
    bookmarks = list(prefs.load_bookmarks(base_dir))

    def refresh_list():
        list_widget.clear()
        bookmarks.clear()
        bookmarks.extend(prefs.load_bookmarks(base_dir))
        for bm in bookmarks:
            # .get: a malformed entry must not crash the dialog (v6.4 KeyError).
            title = (bm.get("title") if isinstance(bm, dict) else "") or ""
            url = (bm.get("url") if isinstance(bm, dict) else "") or ""
            list_widget.addItem(f"{title} - {url}")
        if not bookmarks:
            list_widget.addItem("No bookmarks yet...")

    for bm in bookmarks:
        title = (bm.get("title") if isinstance(bm, dict) else "") or ""
        url = (bm.get("url") if isinstance(bm, dict) else "") or ""
        list_widget.addItem(f"{title} - {url}")
    if not bookmarks:
        list_widget.addItem("No bookmarks yet...")
    layout.addWidget(list_widget)

    def export_json():
        path, _ = QFileDialog.getSaveFileName(dialog, "Export bookmarks", "", "JSON (*.json)")
        if path:
            prefs.save_bookmarks(base_dir, bookmarks)
            shutil.copy(prefs.bookmarks_path(base_dir), path)
            QMessageBox.information(dialog, "Export", "JSON file saved.")

    def export_html():
        path, _ = QFileDialog.getSaveFileName(dialog, "Export bookmarks (Chrome)", "", "HTML (*.html)")
        if path:
            lines = ["<!DOCTYPE NETSCAPE-Bookmark-file-1>", "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">", "<TITLE>Bookmarks</TITLE>", "<H1>Bookmarks</H1>", "<DL><p>"]
            for b in bookmarks:
                title = b.get("title", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                url = b.get("url", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                lines.append('    <DT><A HREF="%s">%s</A>' % (url, title))
            lines.append("</DL><p>")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(dialog, "Export", "HTML file saved.")

    def import_file():
        path, _ = QFileDialog.getOpenFileName(dialog, "Import bookmarks", "", "JSON (*.json);;HTML (*.html);;All (*.*)")
        if not path:
            return
        new_bms = []
        try:
            if path.lower().endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    new_bms = json.load(f)
                if not isinstance(new_bms, list):
                    new_bms = []
            else:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    html = f.read()
                for m in re.finditer(r'<A[^>]+HREF="([^"]+)"[^>]*>([^<]*)</A>', html, re.IGNORECASE):
                    new_bms.append({"url": m.group(1), "title": m.group(2).strip() or m.group(1)})
        except Exception as e:
            QMessageBox.warning(dialog, "Error", "Could not read file: " + str(e))
            return
        if not new_bms:
            QMessageBox.information(dialog, "Import", "No bookmarks found in the file.")
            return
        existing_urls = {b["url"] for b in bookmarks}
        added = 0
        for b in new_bms:
            if b.get("url") and b["url"] not in existing_urls:
                bookmarks.append({"title": b.get("title", b["url"]), "url": b["url"]})
                existing_urls.add(b["url"])
                added += 1
        prefs.save_bookmarks(base_dir, bookmarks)
        refresh_list()
        QMessageBox.information(dialog, "Import", "Added %d bookmark(s)." % added)

    def open_selected():
        idx = list_widget.currentRow()
        if idx >= 0 and 0 <= idx < len(bookmarks):
            url = bookmarks[idx].get("url") if isinstance(bookmarks[idx], dict) else ""
            if url:
                parent.tab_manager.add_tab(QUrl(url))
                dialog.accept()

    # Three file verbs (two exports that differ only by format) live behind one
    # menu; double-clicking a row still opens it.
    btn_open = primary_button("Open selected page")
    btn_open.clicked.connect(open_selected)
    list_widget.itemDoubleClicked.connect(lambda _item: open_selected())
    dialog_footer(
        layout,
        primary=btn_open,
        menu=(
            ("Export as JSON", export_json),
            ("Export as HTML", export_html),
            (None, None),
            ("Import from file…", import_file),
        ),
    )
    dialog.exec_()


def show_extensions_dialog(parent):
    ext_path = parent.ext_path
    dialog = QDialog(parent)
    dialog.setWindowTitle("Extensions (.JS)")
    dialog.resize(560, 400)
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    info = QLabel("Place .js files in the Extensions folder. Each file runs on every page unless it starts with a ==UserScript== header declaring @match / @exclude URL patterns.")
    info.setWordWrap(True)
    layout.addWidget(info)
    list_widget = QListWidget()
    layout.addWidget(list_widget)
    ext_conf_file = os.path.join(ext_path, "extensions.json")
    ext_config = {}
    if os.path.exists(ext_conf_file):
        try:
            with open(ext_conf_file, "r", encoding="utf-8") as f:
                ext_config = json.load(f)
        except Exception:
            pass
    for file_name in os.listdir(ext_path) if os.path.exists(ext_path) else []:
        if file_name.endswith(".js"):
            item = QListWidgetItem(file_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if ext_config.get(file_name, False) else Qt.Unchecked)
            list_widget.addItem(item)

    def save_extensions():
        new_config = {}
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            new_config[item.text()] = (item.checkState() == Qt.Checked)
        with open(ext_conf_file, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4)
        if hasattr(parent, "invalidate_extension_cache"):
            parent.invalidate_extension_cache()
        if hasattr(parent, "browsers"):
            for browser in getattr(parent, "browsers", []):
                try:
                    if browser.url().toString().startswith("http"):
                        browser.reload()
                except Exception:
                    pass
        QMessageBox.information(dialog, "Saved", "Your extensions were saved and will apply to reloaded pages.")
        dialog.accept()

    def make_sample():
        sample_path = os.path.join(ext_path, "SimpleAdblock.js")
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write("""// ==UserScript==
// @name        Simple Adblock
// @match       *://*/*
// ==/UserScript==
(function() {
    var badElems = document.querySelectorAll('iframe, .ads, [id*=\"ad-\"], [class*=\"banner\"]');
    badElems.forEach(e => e.style.display = \"none\");
})();""")
        list_widget.addItem(QListWidgetItem("SimpleAdblock.js"))
        item = list_widget.item(list_widget.count() - 1)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)

    # Saving is the only thing that must be pressed; the sample script, the
    # script gallery and the folder are all occasional detours.
    btn_save = primary_button("Save options")
    btn_save.clicked.connect(save_extensions)
    dialog_footer(
        layout,
        primary=btn_save,
        menu=(
            ("Create an adblock sample (.js)", make_sample),
            ("Browse GreasyFork…", lambda: [dialog.accept(), parent.tab_manager.add_tab(QUrl("https://greasyfork.org/vi"), "GreasyFork", is_active=True)]),
            ("Open the extensions folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(ext_path))),
        ),
    )
    dialog.exec_()


def show_tab_sets_dialog(parent):
    """List saved tab collections; open or delete them."""
    base_dir = parent.base_dir
    dialog = QDialog(parent)
    dialog.setWindowTitle("Tab Sets")
    dialog.resize(560, 420)
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    info = QLabel("Saved tab and research collections. Opening adds tabs to the current workspace; inactive tabs start suspended.")
    info.setWordWrap(True)
    layout.addWidget(info)
    list_widget = QListWidget()
    layout.addWidget(list_widget)

    def refresh():
        list_widget.clear()
        for item in tab_sets.list_tab_sets(base_dir):
            count = len(item.get("tabs", []))
            updated = time_utils.format_ts(item.get("updated_at"))
            label = f"{item.get('title', 'Untitled')}  ·  {count} tab(s)  ·  {updated}"
            related = []
            if item.get("notes"):
                related.append(f"{len(item['notes'])} note(s)")
            if item.get("tasks"):
                related.append(f"{len(item['tasks'])} task(s)")
            if related:
                label += "  ·  " + ", ".join(related)
            if item.get("kind"):
                label += f"  ·  {item.get('kind')}"
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.UserRole, item.get("id"))
            list_widget.addItem(list_item)

    refresh()

    def open_selected(mode="merge"):
        current = list_widget.currentItem()
        if not current:
            return
        set_id = current.data(Qt.UserRole)
        dialog.accept()
        if hasattr(parent, "restore_tab_set"):
            parent.restore_tab_set(set_id, mode=mode)

    def replace_selected():
        current = list_widget.currentItem()
        if not current:
            return
        data = tab_sets.get_tab_set(base_dir, current.data(Qt.UserRole))
        if not data:
            return
        if QMessageBox.warning(
            dialog,
            "Replace current tabs?",
            f"Close the tabs in this browser workspace and open \"{data.get('title', '')}\"?\n\n"
            "Closed tabs remain available through Reopen Closed Tab.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        open_selected("replace")

    def delete_selected():
        current = list_widget.currentItem()
        if not current:
            return
        set_id = current.data(Qt.UserRole)
        data = tab_sets.get_tab_set(base_dir, set_id)
        title = data.get("title", "") if data else "this tab set"
        if QMessageBox.question(dialog, "Delete", f"Delete \"{title}\"?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            tab_sets.remove_tab_set(base_dir, set_id)
            refresh()

    def rename_selected():
        current = list_widget.currentItem()
        if not current:
            return
        set_id = current.data(Qt.UserRole)
        existing = tab_sets.get_tab_set(base_dir, set_id)
        if not existing:
            return
        title, ok = QInputDialog.getText(
            dialog, "Rename tab set", "Name this collection:", text=existing.get("title", "")
        )
        if not ok or not tab_sets.rename_tab_set(base_dir, set_id, title):
            return
        refresh()

    list_widget.itemDoubleClicked.connect(lambda _item: open_selected())

    # Five flat buttons became: open (what you came for), a refresh glyph that
    # belongs to the list, and one menu holding rename/delete.
    btn_open = primary_button("Open & merge")
    btn_open.clicked.connect(lambda: open_selected("merge"))
    btn_refresh = icon_button("↻", "Reload the list from disk")
    btn_refresh.clicked.connect(refresh)
    dialog_footer(
        layout,
        primary=btn_open,
        secondary=(btn_refresh,),
        menu=(
            ("Replace current workspace…", replace_selected),
            (None, None),
            ("Rename…", rename_selected),
            (None, None),
            ("🗑  Delete this tab set", delete_selected),
        ),
        close=dialog.accept,
    )
    dialog.exec_()


def show_save_research_workspace_dialog(parent):
    """Save current browser tabs with references to existing notes and tasks."""
    base_dir = parent.base_dir
    tabs = parent.get_current_tab_state()
    active_workspace = str(getattr(parent, "current_workspace_id", "") or "")
    if active_workspace:
        tabs = [tab for tab in tabs if str(tab.get("workspace_id") or "") == active_workspace]
    if not tabs:
        QMessageBox.information(parent, "Research workspace", "There are no regular tabs in this browser workspace to save.")
        return
    dialog = QDialog(parent)
    dialog.setWindowTitle("Save Research Workspace")
    dialog.resize(480, 300)
    dialog.setStyleSheet(_stylesheet(parent))
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Save these tabs as a named research workspace. Related items are references to your existing profile data."))
    title_edit = QLineEdit()
    title_edit.setPlaceholderText("Workspace name")
    layout.addWidget(title_edit)
    note_combo = QComboBox()
    note_combo.addItem("No linked note", "")
    notes = personal_service.list_notes(base_dir)[:300]
    for note in notes:
        note_combo.addItem(str(note.get("title") or "Untitled note"), str(note.get("id") or ""))
    layout.addWidget(QLabel("Related note"))
    layout.addWidget(note_combo)
    task_combo = QComboBox()
    task_combo.addItem("No linked task", "")
    tasks = [row for row in life_service.load_tasks(base_dir) if not row.get("archived")][:300]
    for task in tasks:
        task_combo.addItem(str(task.get("title") or "Untitled task"), str(task.get("id") or ""))
    layout.addWidget(QLabel("Related task"))
    layout.addWidget(task_combo)
    btn_save = primary_button("Save workspace")

    def save():
        title = title_edit.text().strip()
        if not title:
            title_edit.setFocus()
            return
        try:
            saved = tab_sets.add_tab_set(
                base_dir,
                "workspace",
                title,
                tabs,
                workspace_id=str(getattr(parent, "current_workspace_id", "") or ""),
                notes=[note_combo.currentData()] if note_combo.currentData() else [],
                tasks=[task_combo.currentData()] if task_combo.currentData() else [],
            )
            tab_sets.set_active_research_workspace(base_dir, saved["id"])
        except (OSError, ValueError) as exc:
            QMessageBox.warning(dialog, "Research workspace", f"Could not save workspace:\n{exc}")
            return
        dialog.accept()
        QMessageBox.information(parent, "Research workspace", f"Saved {len(tabs)} tab(s) with linked context.")

    btn_save.clicked.connect(save)
    dialog_footer(layout, primary=btn_save, close=dialog.reject)
    dialog.exec_()

