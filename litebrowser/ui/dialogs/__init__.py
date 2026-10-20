"""Modal dialogs: VPN, history, bookmarks, profiles, privacy, control center."""
from litebrowser.ui.dialogs.help_hub import show_browser_control_center
from litebrowser.ui.dialogs.hotkeys import show_hotkeys_hub
from litebrowser.ui.dialogs.navigation import (
    show_downloads_dialog,
    show_export_dialog,
    show_feeds_dialog,
    show_quick_switcher,
    show_routines_dialog,
    show_workspace_dialog,
)
from litebrowser.ui.dialogs.profiles_privacy import (
    ask_master_password,
    show_permissions_manager,
    show_privacy_dialog,
    show_profiles_dialog,
    show_save_password_dialog,
)
from litebrowser.ui.dialogs.sessions import (
    show_bookmarks_dialog,
    show_extensions_dialog,
    show_hibernate_pref_dialog,
    show_history_dialog,
    show_startup_dialog,
    show_save_research_workspace_dialog,
    show_tab_sets_dialog,
    show_vpn_dialog,
)
from litebrowser.ui.dialogs.vpn_hub import show_vpn_hub

__all__ = [
    "ask_master_password",
    "show_bookmarks_dialog",
    "show_browser_control_center",
    "show_downloads_dialog",
    "show_export_dialog",
    "show_extensions_dialog",
    "show_feeds_dialog",
    "show_hibernate_pref_dialog",
    "show_history_dialog",
    "show_hotkeys_hub",
    "show_permissions_manager",
    "show_privacy_dialog",
    "show_profiles_dialog",
    "show_quick_switcher",
    "show_routines_dialog",
    "show_save_password_dialog",
    "show_save_research_workspace_dialog",
    "show_startup_dialog",
    "show_tab_sets_dialog",
    "show_vpn_dialog",
    "show_vpn_hub",
    "show_workspace_dialog",
]
