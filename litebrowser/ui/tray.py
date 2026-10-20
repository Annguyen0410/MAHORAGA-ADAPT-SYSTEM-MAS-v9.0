"""System tray icon + native notifications (Windows toasts, free).

The tray lives on the primary shell: quick actions (new tab, quick note,
25-min pour, VPN status) plus native QSystemTrayIcon.showMessage toasts for
downloads, focus reminders and routines — visible even when Mei is in the
background. If the desktop has no tray, everything degrades gracefully.
"""
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu, QSystemTrayIcon

from litebrowser.core import prefs
from litebrowser.ui import theme


class MeiTray(QSystemTrayIcon):
    def __init__(self, shell):
        self.shell = shell
        icon = QIcon(shell.app_dir + "/icon.png")
        super().__init__(icon, shell)
        self.setToolTip("Mei — your café")

        menu = QMenu()
        # Tray popups are separate top-levels: style them explicitly so the
        # menu follows the active café theme instead of raw system gray.
        menu.setStyleSheet(theme.main_qss(prefs.resolved_auto_theme(shell.profile_dir), prefs.get_accent(shell.profile_dir)))
        act_note = menu.addAction("✎ Quick note")
        act_note.triggered.connect(self._quick_note)
        act_pour = menu.addAction("☕ Pour 25 min")
        act_pour.triggered.connect(self._quick_pour)
        act_vpn = menu.addAction("🛡 VPN status")
        act_vpn.triggered.connect(self._vpn_status)
        menu.addSeparator()
        act_quit = menu.addAction("✕ Quit Mei")
        act_quit.triggered.connect(self.shell.quit_application)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        # Many Linux setups still render showMessage fine; on systems without
        # a tray, isSystemTrayAvailable() guards construction in the caller.
        self.show()

    # -- actions -------------------------------------------------------
    def _quick_note(self):
        self.shell._open_quick_note_overlay()

    def _quick_pour(self):
        from litebrowser.services import focus_service

        focus_service.start_focus(self.shell.profile_dir, minutes=25, label="Tray pour")
        self.notify("Café Focus", "25-minute pour started — /status to check")

    def _vpn_status(self):
        cfg = prefs.get_proxy_config(self.shell.profile_dir)
        if cfg.get("enabled"):
            self.notify("Mei Shield", f"Protected via {cfg.get('host')}:{cfg.get('port')}")
        else:
            self.notify("Mei Shield", "Direct connection (no proxy)")

    def _on_activated(self, reason):
        # Scoped form (ActivationReason) is required by PyQt6; fall back to
        # the un-scoped PyQt5 shortcut on older bindings.
        trigger = getattr(QSystemTrayIcon, "ActivationReason", None)
        trigger = getattr(trigger, "Trigger", None) or getattr(QSystemTrayIcon, "Trigger", None)
        if trigger is not None and reason == trigger:  # single click → focus a window
            self.shell.showNormal()
            self.shell.raise_()

    # -- native toast --------------------------------------------------
    def notify(self, title: str, message: str, msecs: int = 4000):
        message_icon = getattr(QSystemTrayIcon, "MessageIcon", None)
        message_icon = getattr(message_icon, "Information", None) or getattr(QSystemTrayIcon, "Information", None)
        if self.isVisible():
            self.showMessage(title, message, message_icon, msecs)
