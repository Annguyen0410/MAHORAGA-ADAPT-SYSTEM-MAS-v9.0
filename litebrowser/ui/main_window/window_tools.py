# Mei - window mixins: find bar, media mini-player, downloads, password capture.
#
# Extracted from window.py so each concern stays reviewable; the methods only
# touch SearchWindow-owned attributes (browsers, tab_manager, base_dir, ...).

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QShortcut,
    QToolButton,
)

from litebrowser.core import prefs
from litebrowser.ui import dialogs


class _FindBar(QFrame):
    """Chrome-style find bar: sticky row with next/prev, match count, Esc to
    close. Replaces the v6.4 modal QInputDialog that reopened on every Ctrl+F.
    Styling comes from the shell QSS (#FindBar) so it follows the theme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FindBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)
        self.ed_query = QLineEdit()
        self.ed_query.setPlaceholderText("Find in page")
        self.ed_query.setClearButtonEnabled(True)
        self.ed_query.setFixedWidth(260)
        self.btn_prev = QToolButton()
        self.btn_prev.setText("▲")
        self.btn_prev.setToolTip("Previous match (Shift+F3)")
        self.btn_next = QToolButton()
        self.btn_next.setText("▼")
        self.btn_next.setToolTip("Next match (F3)")
        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Close (Esc)")
        for b in (self.btn_prev, self.btn_next, self.btn_close):
            b.setAutoRaise(True)
            b.setCursor(Qt.PointingHandCursor)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("MutedLabel")
        lay.addWidget(self.ed_query, 1)
        lay.addWidget(self.lbl_count)
        lay.addWidget(self.btn_prev)
        lay.addWidget(self.btn_next)
        lay.addWidget(self.btn_close)
        self.setFixedHeight(36)


class _WorkerRelay(QObject):
    """Queued-call bridge from executor threads to the GUI thread.

    QObjects/QTimers must not be created from worker threads (v6.4 used
    QTimer.singleShot inside future callbacks, which is unsafe); emit the
    callable instead and it runs on the GUI thread via a queued connection.
    """

    run_on_gui = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.run_on_gui.connect(self._exec)

    def post(self, fn):
        self.run_on_gui.emit(fn)

    def _exec(self, fn):
        try:
            fn()
        except Exception:
            pass


class WindowToolsMixin:
    """Find-in-page, media mini-player, downloads pipeline, password capture."""

    def _first_audible_browser(self):
        for browser in self.browsers:
            if browser is None:
                continue
            try:
                if browser.page().recentlyAudible():
                    return browser
            except Exception:
                continue
        return None

    def on_audible_changed(self, audible: bool, browser=None):
        """Show/hide the mini-player; the flag also drives the row chip."""
        try:
            if browser is not None:
                browser.setProperty("audible", bool(audible))
        except Exception:
            pass
        has_audio = audible or self._first_audible_browser() is not None
        self.btn_media_play.setVisible(has_audio)
        self.btn_media_mute.setVisible(has_audio)
        if browser is not None:
            self.tab_manager.refresh_row_state_labels()

    def _toggle_media_playback(self):
        browser = self._first_audible_browser()
        if browser is None:
            return
        # Qt5's QWebEnginePage lacks a PlayOrPause action; toggle every media
        # element on the page (works for YouTube/Spotify embeds and players).
        js = (
            "(function(){var els=document.querySelectorAll('video,audio');"
            "if(!els.length)return 'no media';"
            "var any=false;"
            "for(var i=0;i<els.length;i++){var e=els[i];"
            "if(!e.paused){e.pause();any=true;}else if(any){continue;}else{e.play().catch(function(){});any=true;}}"
            "return 'toggled';})()"
        )

        def _done(result):
            self._flash_status("Media play/pause" if result == "toggled" else "No media element found")

        browser.page().runJavaScript(js, _done)

    def _toggle_media_mute(self):
        browser = self._first_audible_browser()
        if browser is None:
            return
        page = browser.page()
        muted = not page.isAudioMuted()
        page.setAudioMuted(muted)
        self.btn_media_mute.setText("🔊" if muted else "🔇")
        self._flash_status("Media muted" if muted else "Media unmuted")


    def find_text(self):
        if not self.current_browser():
            return
        bar = self._ensure_find_bar()
        bar.show()
        bar.raise_()
        bar.ed_query.setFocus()
        bar.ed_query.selectAll()
        self._find_browser = self.current_browser()

    def _ensure_find_bar(self):
        if getattr(self, "_find_bar", None) is None:
            self._find_bar = _FindBar(self)
            lay = self.central_widget.layout()
            lay.addWidget(self._find_bar)
            # Hidden until first use; sits above the web area like Chrome.
            self._find_bar.hide()
            self._find_bar.ed_query.textChanged.connect(self._on_find_text_changed)
            self._find_bar.ed_query.returnPressed.connect(self._find_next)
            self._find_bar.btn_next.clicked.connect(self._find_next)
            self._find_bar.btn_prev.clicked.connect(self._find_prev)
            self._find_bar.btn_close.clicked.connect(self._close_find_bar)
            QShortcut(QKeySequence(Qt.Key_Escape), self._find_bar).activated.connect(self._close_find_bar)
            QShortcut(QKeySequence("F3"), self._find_bar).activated.connect(self._find_next)
            QShortcut(QKeySequence("Shift+F3"), self._find_bar).activated.connect(self._find_prev)
        return self._find_bar

    def _find_next(self):
        bar = getattr(self, "_find_bar", None)
        if bar and bar.isVisible() and self.current_browser():
            self.current_browser().findText(bar.ed_query.text(), self._find_flags_forward())

    def _find_prev(self):
        bar = getattr(self, "_find_bar", None)
        if bar and bar.isVisible() and self.current_browser():
            self.current_browser().findText(bar.ed_query.text(), self._find_flags_backward())

    def _find_flags_forward(self):
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        return QWebEnginePage.FindFlags() if hasattr(QWebEnginePage, "FindFlags") else 0

    def _find_flags_backward(self):
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        try:
            return QWebEnginePage.FindFlag.FindBackward
        except AttributeError:
            return QWebEnginePage.FindBackward

    def _on_find_text_changed(self, text):
        browser = self.current_browser()
        if not browser:
            return
        if not text:
            browser.findText("")
            bar = self._find_bar
            if bar:
                bar.lbl_count.setText("")
            return
        browser.findText(text, self._find_flags_forward(), self._on_find_result)

    def _on_find_result(self, result):
        bar = getattr(self, "_find_bar", None)
        if bar is None:
            return
        count, index = result.numberOfMatches(), result.activeMatch()
        bar.lbl_count.setText(f"{index}/{count}" if count else "0/0")

    def _close_find_bar(self):
        bar = getattr(self, "_find_bar", None)
        if bar is not None:
            bar.hide()
            browser = self.current_browser()
            if browser:
                browser.findText("")


    def handle_download_request(self, download):
        suggested = (download.suggestedFileName() or "").strip()
        suggested_lower = suggested.lower()
        dangerous = (".exe", ".bat", ".cmd", ".scr", ".msi", ".vbs", ".js", ".jar", ".pif", ".com")
        is_risky = suggested_lower.endswith(dangerous)
        msg = QMessageBox(self)
        msg.setWindowTitle("Download request")
        if is_risky:
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"This page is trying to download a file that can execute:\n{suggested or '(unnamed)'}\n\nOnly accept if you trust the source. Allow download?")
        else:
            msg.setText(f"This page is trying to download a file:\n{suggested or '(unnamed)'}\n\nAllow download?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        if msg.exec_() == QMessageBox.Yes:
            path, _ = QFileDialog.getSaveFileName(self, "Save file", suggested or "download")
            if path:
                download.setPath(path)
                download.accept()
                try:
                    from litebrowser.services import download_mgr
                    download_id = download_mgr.add_download(self.base_dir, download.url().toString(), path, download.suggestedFileName(), "downloading")
                    # Qt6 and Qt5 both expose stateChanged; use it as the primary signal so
                    # status always lands even when .finished / .isFinishedChanged are absent.
                    if hasattr(download, "stateChanged"):
                        download.stateChanged.connect(
                            lambda _state=None, did=download_id, item=download: self._finalize_download(did, item)
                        )
                    if hasattr(download, "finished"):
                        download.finished.connect(lambda did=download_id, item=download: self._finalize_download(did, item))
                    elif hasattr(download, "isFinishedChanged"):
                        download.isFinishedChanged.connect(
                            lambda done, did=download_id, item=download: self._finalize_download(did, item) if done else None
                        )
                except Exception:
                    pass
            else:
                download.cancel()
        else:
            download.cancel()

    def _finalize_download(self, download_id, download):
        # stateChanged and finished both fire per download; only the first
        # terminal event may be recorded or statuses get overwritten.
        if not hasattr(self, "_finalized_downloads"):
            self._finalized_downloads = set()
        if download_id in self._finalized_downloads:
            return
        try:
            from litebrowser.services import download_mgr
            state = download.state() if hasattr(download, "state") else None
            completed = getattr(download, "DownloadCompleted", None)
            cancelled = getattr(download, "DownloadCancelled", None)
            interrupted = getattr(download, "DownloadInterrupted", None)
            terminal_states = [s for s in (completed, cancelled, interrupted) if s is not None]
            if state is None:
                return  # unknown state — do not mark anything yet
            if terminal_states and state not in terminal_states:
                return  # still requested/in-progress; keep "downloading" status
            status = "completed"
            if cancelled is not None and state == cancelled:
                status = "cancelled"
            elif interrupted is not None and state == interrupted:
                status = "interrupted"
            download_mgr.update_status(self.base_dir, download_id, status)
            self._finalized_downloads.add(download_id)
            self._load_downloads_panel()
            if status == "completed":
                fname = (download.suggestedFileName() or "").strip() or "file"
                self._flash_status(f"✓ Downloaded {fname}")
                shell = self._host_shell()
                if shell is not None and hasattr(shell, "system_notify"):
                    shell.system_notify("Download complete", fname)
            elif status == "interrupted":
                self._flash_status("⚠ Download interrupted")
            elif status == "cancelled":
                self._flash_status("Download cancelled")
        except Exception:
            pass

    def _maybe_offer_saved_password(self, browser):
        """Chrome-style save-password prompt after a login page navigates away.

        The profile capture script stashes submitted credentials in
        sessionStorage; this reads them once per successful load and offers to
        store them in the vault (deduped per host)."""
        if not prefs.get_password_manager_enabled(self.base_dir):
            return
        try:
            from litebrowser.services import password_manager
            if not password_manager.HAS_CRYPTO:
                return
            url_str = browser.url().toString()
            if not url_str.startswith("http"):
                return
            host = password_manager._normalize_origin(url_str)
            if not host or host in getattr(self, "_password_prompt_hosts", set()):
                return
            browser.page().runJavaScript(
                password_manager.READ_CAPTURED_SCRIPT,
                lambda result, b=browser, h=host: self._on_captured_credentials(result, b, h),
            )
        except Exception:
            pass

    def _on_captured_credentials(self, result, browser, host):
        if not result or not isinstance(result, dict):
            return
        password = result.get("pass") or ""
        username = result.get("user") or ""
        if not password:
            return
        self._password_prompt_hosts = getattr(self, "_password_prompt_hosts", set()) | {host}

        bar = QFrame(self.content_widget)
        bar.setObjectName("SavePasswordBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        lbl = QLabel(f"Save login for {host}?")
        lbl.setObjectName("PageTitle")
        bar_layout.addWidget(lbl, 1)
        result_box = {"master": None, "saved": False}

        def _with_master(save: bool):
            master = getattr(self, "_master_password", None)
            if master is None:
                master = dialogs.ask_master_password(self)
            if not master:
                if master is None:
                    bar.setParent(None)
                    bar.deleteLater()
                return
            self._master_password = master
            try:
                from litebrowser.services import password_manager
                if save:
                    if password_manager._normalize_origin(browser.url().toString()) != host:
                        raise ValueError("The page changed before saving this login. Nothing was saved.")
                    if not password_manager.add_password(self.base_dir, host, username, password, master):
                        raise OSError("The login could not be saved. Check disk access and retry.")
                    self._flash_status(f"Login saved for {host}")
                result_box["saved"] = save
            except Exception as exc:
                QMessageBox.warning(self, "Passwords", str(exc))
            bar.setParent(None)
            bar.deleteLater()

        yes_btn = QPushButton("Save")
        yes_btn.setObjectName("TopAccentButton")
        yes_btn.clicked.connect(lambda: _with_master(True))
        no_btn = QPushButton("Never")
        no_btn.clicked.connect(lambda: _with_master(False))
        bar_layout.addWidget(yes_btn)
        bar_layout.addWidget(no_btn)
        self.content_layout.addWidget(bar, 0)
