
# Pure data + color logic moved to litebrowser.core.theme_data so the data
# layer can validate theme/accent names without importing Qt. Re-exported
# here so every existing ``theme.<name>`` reference keeps working unchanged.
from litebrowser.core.theme_data import (  # noqa: F401
    _ACCENT_KEYS,
    ACCENTS,
    DEFAULT_THEME,
    DEFAULTS,
    PALETTES,
    THEME_LABELS,
    _accent_override,
    _blend_hex,
    _is_light_color,
    _palette,
    accent_display_name,
    accent_keys,
    palette_tokens,
    theme_display_name,
    valid_accent,
)


def resolved_mode(base_dir: str | None = None) -> str:
    """Theme id the chrome is *currently painting with*.

    ``prefs.get_shell_theme`` returns the *stored* choice; with the auto day/night
    preference on, the shell paints with a sibling the stored name does not tell
    you about. A widget that resolved with the stored name therefore kept its day
    colours after the shell had switched to the night palette — page cards stayed
    light inside a dark window.
    """
    from litebrowser.core import prefs as _prefs

    return _prefs.resolved_auto_theme(base_dir or _prefs.DEFAULT_BASE_DIR) or DEFAULT_THEME


def palette(mode: str | None = None, accent: str | None = None, base_dir: str | None = None) -> dict:
    """Resolved tokens for the active profile when the caller does not say.

    Both defaults are load-bearing, and both were once wrong in the same way —
    hand-painted widgets showing colours the rest of the window did not have:

    * ``mode`` follows the auto day/night *resolution*, not the stored name: a
      widget painted with the stored name kept day colours inside the night
      window (see ``tests/test_theme_follows_shell.py``).
    * ``accent`` follows the profile's accent preset, not the palette's own
      accent. The shell QSS is built with the chosen accent
      (``theme.main_qss(mode, prefs.get_accent(base_dir))``), so a chart that
      resolved the palette alone drew the theme's stock accent — a gold bar on
      a desk whose buttons, chips and active nav row were rose.

    Pass ``base_dir`` for a widget that belongs to a profile other than the
    default one. Pass ``accent=""`` to mean "the palette's own accent".
    """
    from litebrowser.core import prefs as _prefs

    base = base_dir or _prefs.DEFAULT_BASE_DIR
    chosen = _prefs.get_accent(base) if accent is None else accent
    return _palette(mode or resolved_mode(base), chosen)


def accent_bar_color(tokens: dict, is_today: bool):
    """Fill colour for one bar of a hand-painted chart.

    Today gets the accent at full strength; every other day gets the *same*
    accent at reduced opacity, so the bar reads as the theme's colour in every
    palette. The ``ACCENT_SOFT`` token is deliberately not used here: it is a
    surface meant to carry ``ACCENT_HOVER`` text (a dark tone by design on night
    palettes, a paper tint on light ones), and as a chart fill it came out as
    mud — a brown bar inside a near-black card, which is what made the two
    dashboard charts look like they belonged to a different theme.
    """
    from PyQt5.QtGui import QColor

    color = QColor(tokens.get("ACCENT", "#A66A2E"))
    if not is_today:
        color.setAlphaF(0.55)
    return color


# ---------- 6.7 dialog verbs: one action, one row --------------------------
# Dialogs had grown rows of five to seven identical buttons, so the action the
# dialog existed for was indistinguishable from "Delete everything" two pixels
# away. ``ui/dialogs/common.py`` now gives every verb a role: exactly one filled
# primary per dialog, ghosts for the verbs worth keeping visible, subdued quiet
# buttons (Close), and the occasional verbs inside one "⋯ More" menu. Kept as a
# single block appended to both sheets so the dialog chrome cannot drift from
# the full workspace.
_VERB_QSS = """
QPushButton#PrimaryButton {
    background-color: %(ACCENT)s;
    color: %(TEXT_ON_ACCENT)s;
    border: 1px solid %(ACCENT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 16px;
    font-weight: 800;
}
QPushButton#PrimaryButton:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }
QPushButton#PrimaryButton:disabled {
    background-color: %(MAIN_BG_ALT)s; color: %(TEXT_DIM)s; border-color: %(BORDER_SOFT)s;
}
QPushButton#GhostButton {
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 13px;
    font-weight: 700;
}
QPushButton#GhostButton:hover { background-color: %(ITEM_HOVER)s; border-color: %(ACCENT)s; color: %(TEXT)s; }
QPushButton#QuietButton {
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid transparent;
    border-radius: %(RADIUS_SM)s;
    padding: 5px 12px;
    font-weight: 700;
}
QPushButton#QuietButton:hover { background-color: %(ITEM_HOVER)s; color: %(TEXT)s; }
QPushButton#DangerButton {
    background-color: transparent;
    color: %(DANGER)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 13px;
    font-weight: 700;
}
QPushButton#DangerButton:hover { background-color: %(DANGER)s; border-color: %(DANGER)s; color: %(TEXT_ON_DANGER)s; }
QPushButton[compactIcon="true"] { padding: 0; min-width: 0; min-height: 0; font-size: 15px; }
QToolButton[compactIcon="true"] { padding: 0; min-width: 0; min-height: 0; }
QCalendarWidget QAbstractItemView { selection-background-color: %(ACCENT)s; selection-color: %(TEXT_ON_ACCENT)s; outline: none; }
QCalendarWidget QToolButton { color: %(TEXT)s; background-color: %(MAIN_BG_ALT)s; border: none; padding: 0 5px; }
QCalendarWidget QToolButton:hover { background-color: %(ITEM_HOVER)s; }
QMenu#DialogOverflowMenu { padding: 6px; }
QMenu#DialogOverflowMenu::item { padding: 6px 22px 6px 12px; }
QMenu#DialogOverflowMenu::separator { height: 1px; margin: 5px 8px; background-color: %(BORDER_SOFT)s; }
"""


def main_qss(mode: str = "cafe-night", accent: str | None = None):
    p = _palette(mode, accent)
    return """
/* ================= Mei 6.3 — modern chrome ================= */

/* ---------- base: flat minimal layers ---------- */
QMainWindow, QWidget {
    background-color: %(MAIN_BG)s;
    color: %(TEXT)s;
    font-size: 13px;
}
#ShellRoot, #MainWidget {
    background-color: %(MAIN_BG)s;
}
#ShellTopBar {
    background-color: %(CARD_BG)s;
    border-bottom: 1px solid %(BORDER_SOFT)s;
    padding: 6px 12px;
}
#ShellBrand { color: %(TEXT)s; letter-spacing: 0.4px; font-weight: 600; }
#BrandGlyph { color: %(ACCENT_HOVER)s; font-size: 26px; }
#BrandName { color: %(TEXT)s; font-size: 16px; font-weight: 800; letter-spacing: 0.3px; }
#BrandSub { color: %(TEXT_MUTED)s; font-size: 10px; letter-spacing: 0.5px; }
#StatusPill {
    background-color: %(ACCENT_SOFT)s; color: %(ACCENT_HOVER)s;
    border: 1px solid %(INPUT_BORDER)s; border-radius: 999px;
    padding: 2px 12px; font-size: 11px; font-weight: 700;
}

/* ---------- inputs & editors ---------- */
#ShellOmnibar, #UrlBar, QLineEdit, QTextEdit, QListWidget, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
    background-color: %(INPUT_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: %(RADIUS_SM)s;
    padding: 5px 9px;
    selection-background-color: %(MENU_ITEM_SEL)s;
    selection-color: %(TEXT)s;
}
#ShellOmnibar:hover, #UrlBar:hover, QLineEdit:hover, QTextEdit:hover, QListWidget:hover, QComboBox:hover, QSpinBox:hover, QDateEdit:hover, QTimeEdit:hover, QDateTimeEdit:hover {
    border-color: %(ACCENT)s;
}
#ShellOmnibar:focus, #UrlBar:focus, QLineEdit:focus, QTextEdit:focus, QListWidget:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {
    border-color: %(INPUT_FOCUS)s;
    background-color: %(CARD_BG)s;
}
#ShellOmnibar { min-height: 28px; font-size: 12px; padding: 5px 10px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { width: 10px; height: 10px; }
QComboBox QAbstractItemView {
    background-color: %(MENU_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 4px;
    selection-background-color: %(MENU_ITEM_SEL)s;
    selection-color: %(TEXT)s;
}
QScrollArea#SettingsScroll {
    border: none;
    background-color: %(MAIN_BG)s;
}
QScrollArea#SettingsScroll > QWidget > QWidget { background-color: %(MAIN_BG)s; }
QScrollArea#HomeScroll {
    border: none;
    background-color: %(MAIN_BG)s;
}
QScrollArea#HomeScroll > QWidget > QWidget { background-color: %(MAIN_BG)s; }

/* ---------- labels ---------- */
QLabel { color: %(TEXT)s; background: transparent; }
#MutedLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
#SectionTitle { color: %(ACCENT_HOVER)s; font-weight: 700; letter-spacing: 0.4px; font-size: 12px; text-transform: uppercase; }
#HeroTitle { color: %(TEXT)s; font-family: %(TITLE_FONT)s; }
#HeroSubtitle { color: %(TEXT_MUTED)s; font-size: 13px; }
#HeroBadge {
    background-color: %(ACCENT_SOFT)s; color: %(ACCENT_HOVER)s;
    border: 1px solid %(INPUT_BORDER)s; border-radius: %(RADIUS_SM)s;
    padding: 3px 10px; font-size: 11px; font-weight: 700;
}

/* ---------- shared components (ui/components.py) ---------- */
#PageHeader { background: transparent; }
#PageGlyph { color: %(ACCENT_HOVER)s; font-size: 20px; }
#PageTitle { color: %(TEXT)s; }
#PageSubtitle { color: %(TEXT_MUTED)s; font-size: 11px; }

#StatRow { background: transparent; }
#StatTile {
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
}
#StatTile:hover { border-color: %(ACCENT)s; }
#StatValue { color: %(ACCENT_HOVER)s; }
#StatLabel { color: %(TEXT_MUTED)s; font-size: 11px; }

#SectionHeaderRow { background: transparent; }
#EmptyState {
    background-color: %(CARD_BG)s;
    border: 1px dashed %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
}
#EmptyGlyph { color: %(ACCENT_SOFT)s; font-size: 26px; }

/* ---------- action tiles (dashboard launchers) ---------- */
#ActionTile {
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS)s;
    padding: 6px;
}
#ActionTile:hover {
    border-color: %(ACCENT)s;
    background-color: %(ITEM_HOVER)s;
}
#ActionTile:pressed { background-color: %(ITEM_SELECTED)s; }
#ActionGlyph { color: %(ACCENT_HOVER)s; font-size: 25px; font-weight: 700; }
#ActionLabel { color: %(TEXT)s; font-weight: 700; font-size: 13px; }
#ActionHint { color: %(TEXT_MUTED)s; font-size: 10px; }

/* ---------- chips (filter toggles) ---------- */
#Chip {
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 999px;
    padding: 4px 11px;
    font-size: 11px;
    font-weight: 600;
}
#Chip:hover { border-color: %(ACCENT)s; color: %(TEXT)s; background-color: %(ITEM_HOVER)s; }
#Chip:checked {
    background-color: %(ACCENT_SOFT)s;
    color: %(ACCENT_HOVER)s;
    border-color: %(ACCENT)s;
}

/* ---------- badges ---------- */
#Badge {
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 700;
}
#BadgeAccent {
    background-color: %(ACCENT_SOFT)s;
    color: %(ACCENT_HOVER)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 800;
}

/* ---------- rail footer / meta chips ---------- */
#RailMeta {
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 5px 8px;
    font-size: 11px;
    color: %(TEXT_MUTED)s;
}

/* ---------- left rail / nav ---------- */
#LeftRail {
    background-color: %(SIDEBAR_BG)s;
    border-right: 1px solid %(BORDER_SOFT)s;
}
#NavButton {
    text-align: left; padding: 7px 11px; font-weight: 600;
    border: 1px solid transparent; border-radius: %(RADIUS_SM)s;
    color: %(TEXT_MUTED)s; background: transparent;
}
#NavButton:hover { background-color: %(ITEM_HOVER)s; color: %(TEXT)s; }
#NavButton:checked {
    background-color: %(ITEM_SELECTED)s;
    border: 1px solid %(ITEM_SELECTED_BORDER)s;
    color: %(ACCENT_HOVER)s;
}

/* ---------- buttons ---------- */
QPushButton, #CafeButton {
    background-color: %(BUTTON_BG)s;
    color: %(BUTTON_TEXT)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: %(RADIUS_SM)s;
    padding: 5px 10px;
    min-height: 16px;
    font-weight: 600;
}
QPushButton:hover, #CafeButton:hover { background-color: %(BUTTON_HOVER)s; border-color: %(ACCENT)s; }
QPushButton:pressed, #CafeButton:pressed { background-color: %(ITEM_SELECTED)s; }
QPushButton:disabled { color: %(TEXT_DIM)s; background-color: %(MAIN_BG_ALT)s; border-color: %(BORDER_SOFT)s; }
QPushButton#TopAccentButton {
    background-color: %(ACCENT)s;
    color: #141414; border: none; font-weight: 800;
}
QPushButton#TopAccentButton:hover { background-color: %(ACCENT_HOVER)s; }

#StatusStrip {
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 3px 8px;
}

/* ---------- cards / panels: elevated surfaces ---------- */
#InsightPanel, #HeroCard, #SectionCard, #StatCard, #TopBar, #TopBarCluster, #AddressCluster {
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS)s;
}
#InsightPanel { border-left: none; border-radius: 0; border-top-left-radius: 0; border-bottom-left-radius: 0; }
/* WebEngine draws its own surface; avoid rounded card chrome that skews layout perception. */
#WebContainer { background-color: %(MAIN_BG)s; border: none; border-radius: 0; }

#HeroCard {
    background-color: %(CARD_BG)s;
    border: 1px solid %(INPUT_BORDER)s;
}
#StatCard {
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
}
#StatCard:hover { border-color: %(ACCENT)s; }
#StatCard QLabel { font-weight: 600; }

/* ---------- top bar (browser chrome) ---------- */
#TopBar { background-color: %(CARD_BG)s; border: 1px solid %(BORDER_SOFT)s; padding: 4px; }
#TopBarCluster, #AddressCluster { background-color: %(MAIN_BG_ALT)s; border: 1px solid %(BORDER_SOFT)s; }
#AddressCluster #UrlBar { background: transparent; border: none; padding: 6px 8px; font-size: 12px; font-weight: 600; }
#TopBar #SearchEngine, #SearchEngine, #WorkspaceCombo {
    min-height: 30px; background-color: %(INPUT_BG)s; color: %(TEXT)s;
    border: 1px solid %(INPUT_BORDER)s; border-radius: %(RADIUS_SM)s; padding: 4px 22px 4px 10px;
    font-size: 11px; font-weight: 600;
}
#SearchEngine::drop-down, #WorkspaceCombo::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 22px; border: none; background: transparent; }
#SearchEngine::down-arrow, #WorkspaceCombo::down-arrow { width: 10px; height: 10px; }

/* ---------- lists ---------- */
/* Inline omnibar feature finder: a card-popup list under the search box. */
#FeaturePopupList {
    background-color: %(CARD_BG)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 10px;
    padding: 4px;
    outline: none;
}
#FeaturePopupList::item {
    background-color: transparent;
    border-radius: 7px;
    color: %(TEXT)s;
}
#FeaturePopupList::item:hover { background-color: %(ITEM_HOVER)s; }
#FeaturePopupList::item:selected {
    background-color: %(ITEM_SELECTED)s;
    border: 1px solid %(ITEM_SELECTED_BORDER)s;
}

#CafeList, #TabList { background-color: transparent; border: none; outline: none; }
#CafeList::item {
    background-color: transparent; border-radius: %(RADIUS_SM)s;
    padding: 5px 8px; margin: 2px 2px; border-left: 3px solid transparent; color: %(TEXT_MUTED)s;
}
/* #TabList rows are custom item widgets (favicon + title + close); QSS
   padding/margins here shrink the widget rect and slice the title in half
   (rows rendered ~12px tall for a 32px item). The row widget carries its
   own internal margins, so the ::item rule must stay padding-free. */
#TabList::item {
    background-color: transparent; border-radius: %(RADIUS_SM)s;
    border-left: 3px solid transparent; color: %(TEXT_MUTED)s;
}
#CafeList::item:hover, #TabList::item:hover { background-color: %(ITEM_HOVER)s; color: %(TEXT)s; }
#CafeList::item:selected, #TabList::item:selected {
    background-color: %(ITEM_SELECTED)s; color: %(TEXT)s; border-left-color: %(ACCENT)s;
}

/* ---------- browser sidebar ---------- */
#Sidebar { background-color: %(SIDEBAR_BG)s; border-right: 1px solid %(BORDER_SOFT)s; }
#TabCounter, #ZoomLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
#NewTabBtn {
    background-color: %(ACCENT_SOFT)s; color: %(ACCENT_HOVER)s; border: 1px solid %(INPUT_BORDER)s;
    border-radius: %(RADIUS_SM)s; padding: 9px 10px; font-weight: 700;
}
#NewTabBtn:hover { background-color: %(ITEM_SELECTED)s; border-color: %(ACCENT)s; }

#SidebarPanelBtn, #TopBar QToolButton {
    background-color: transparent; color: %(TEXT_MUTED)s; border: none;
    border-radius: %(RADIUS_SM)s; padding: 5px 9px; min-width: 28px; min-height: 28px; font-size: 10px; font-weight: 700;
}
#SidebarPanelBtn:hover, #TopBar QToolButton:hover { background-color: %(ITEM_HOVER)s; color: %(TEXT)s; }
#SidebarPanelBtn:checked { color: %(ACCENT_HOVER)s; background-color: %(ITEM_SELECTED)s; border: 1px solid %(ITEM_SELECTED_BORDER)s; }
#SidebarCollapse {
    background-color: %(MAIN_BG_ALT)s; color: %(TEXT)s;
    border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s;
    min-width: 22px; min-height: 22px; padding: 0 4px; font-size: 13px; font-weight: 700;
}
#SidebarCollapse:hover { background-color: %(ITEM_HOVER)s; border-color: %(ACCENT)s; color: %(ACCENT_HOVER)s; }

#TopIconButton {
    background-color: %(BUTTON_BG)s; color: %(TEXT)s; border: 1px solid %(INPUT_BORDER)s;
    border-radius: %(RADIUS_SM)s; min-width: 30px; min-height: 30px; padding: 3px 6px; font-weight: 700; font-size: 10px;
}
#TopIconButton:hover { background-color: %(BUTTON_HOVER)s; border-color: %(ACCENT)s; }

/* ---------- menus ---------- */
QMenu {
    background-color: %(MENU_BG)s; color: %(TEXT)s;
    border: 1px solid %(INPUT_BORDER)s; padding: 5px; border-radius: %(RADIUS_SM)s;
}
QMenu::item { padding: 6px 12px; border-radius: 6px; margin: 1px 0; }
QMenu::item:selected { background-color: %(MENU_ITEM_SEL)s; color: %(TEXT)s; }
QMenu::item:disabled { color: %(TEXT_DIM)s; }
QMenu::separator { height: 1px; background: %(BORDER_SOFT)s; margin: 5px 7px; }

/* ---------- checkboxes / radios ---------- */
QCheckBox, QRadioButton { color: %(TEXT_MUTED)s; spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px; border-radius: 5px;
    border: 1px solid %(INPUT_BORDER)s; background: %(INPUT_BG)s;
}
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %(ACCENT)s; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: %(ACCENT)s;
    border-color: %(ACCENT)s;
}
QRadioButton::indicator:checked { border: 5px solid %(ACCENT)s; background: %(INPUT_BG)s; }
/* A visible check mark: solid accent fill alone read as a disabled box. */
QCheckBox:checked { color: %(TEXT)s; font-weight: 600; }

/* ---------- progress / slider ---------- */
QProgressBar {
    border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s; background: %(MAIN_BG_ALT)s; text-align: center;
}
QProgressBar::chunk { background-color: %(ACCENT)s; border-radius: %(RADIUS_SM)s; }

/* ---------- splitter / tooltip ---------- */
#ShellTopBar QSplitter::handle, QSplitter::handle { background-color: %(BORDER_SOFT)s; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }
QToolTip {
    background-color: %(MENU_BG)s; color: %(TEXT)s;
    border: 1px solid %(ACCENT)s; border-radius: %(RADIUS_SM)s; padding: 6px 10px;
}

/* ---------- header group boxes ---------- */
QGroupBox {
    border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s; margin-top: 10px; padding-top: 8px;
    color: %(TEXT)s; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; color: %(ACCENT_HOVER)s; }

/* ---------- scrollbars: translucent rounded ---------- */
QScrollBar:vertical {
    width: 9px; margin: 2px; background: transparent; border-radius: 4px;
}
QScrollBar::handle:vertical {
    min-height: 26px; background: %(INPUT_BORDER)s; border-radius: 4px; margin: 1px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:press { background: %(ACCENT)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    height: 9px; margin: 2px; background: transparent; border-radius: 4px;
}
QScrollBar::handle:horizontal {
    min-width: 26px; background: %(INPUT_BORDER)s; border-radius: 4px; margin: 1px;
}
QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:press { background: %(ACCENT)s; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---------- 2026 coffee-house interface refresh ----------
   The rules below deliberately sit at the end of the sheet: a single visual
   language reaches the shell, browser chrome, dashboard, workspaces, and
   standalone windows without making each screen maintain its own palette. */
QMainWindow, QWidget {
    font-family: %(FONT_FAMILY)s;
    background-color: %(MAIN_BG)s;
    color: %(TEXT)s;
}
/* Labels sit directly on their parent surface.  Only named badges/glyphs
   below intentionally paint a background. */
QLabel {
    background-color: transparent;
    border: none;
}

#ShellRoot, #MainWidget, #ContentArea, #HomeDashboard, #SettingsContent,
#AIWorkspace, #PersonalWorkspace, #LibraryWorkspace, #SettingsWorkspace, #HistoryWorkspace {
    background-color: %(MAIN_BG)s;
}

#ShellTopBar {
    min-height: 50px;
    background-color: %(CARD_BG)s;
    border: none;
    border-bottom: 1px solid %(BORDER_SOFT)s;
    padding: 7px 14px;
}
#BrandWrap { background: transparent; }
#BrandGlyph {
    color: %(ACCENT_HOVER)s;
    min-width: 30px;
    min-height: 30px;
    qproperty-alignment: AlignCenter;
    background-color: %(ACCENT_SOFT)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 15px;
    font-size: 17px;
}
#BrandName {
    color: %(TEXT)s;
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 0.7px;
}
#BrandSub {
    color: %(TEXT_MUTED)s;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.3px;
    text-transform: uppercase;
}
#ShellOmnibar {
    min-height: 34px;
    padding: 6px 12px;
    border-radius: 17px;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    font-size: 12px;
}
#ShellOmnibar:focus {
    background-color: %(CARD_BG)s;
    border: 1px solid %(ACCENT)s;
}

#LeftRail, #Sidebar {
    background-color: %(SIDEBAR_BG)s;
    border: none;
    border-right: 1px solid %(SIDEBAR_BORDER)s;
}
#RailSectionLabel {
    color: %(TEXT_MUTED)s;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 1.1px;
    padding: 9px 10px 2px 10px;
}
/* The rail header line: quiet text, not a boxed chip (the box made the profile
   name look like a button and pushed the first nav item down a whole row). */
#RailMeta {
    background: transparent;
    border: none;
    color: %(TEXT_MUTED)s;
    font-size: 10px;
    padding: 2px 4px;
}
#NavButton {
    min-height: 34px;
    text-align: left;
    color: %(TEXT_MUTED)s;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 7px 10px;
    font-size: 12px;
    font-weight: 650;
}
#NavButton:hover {
    color: %(TEXT)s;
    background-color: %(ITEM_HOVER)s;
    border-color: %(BORDER_SOFT)s;
}
#NavButton:checked {
    color: %(ACCENT_HOVER)s;
    background-color: %(ACCENT_SOFT)s;
    border-color: %(INPUT_BORDER)s;
}
#NavToggle {
    color: %(TEXT_MUTED)s;
    background: transparent;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 8px;
    min-width: 25px;
    max-width: 26px;
    min-height: 25px;
    max-height: 26px;
    padding: 0;
    font-size: 11px;
    font-weight: 700;
}
#NavToggle:hover {
    color: %(TEXT)s;
    background-color: %(ITEM_HOVER)s;
    border-color: %(ACCENT)s;
}
#ChipButton {
    color: %(TEXT_MUTED)s;
    background: transparent;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 700;
}
#ChipButton:hover {
    color: %(TEXT)s;
    background-color: %(ITEM_HOVER)s;
    border-color: %(BORDER_SOFT)s;
}
#ChipButton:checked {
    color: %(ACCENT_HOVER)s;
    background-color: %(ACCENT_SOFT)s;
    border-color: %(ACCENT)s;
}

#StatusStrip {
    min-height: 28px;
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 10px;
    padding: 3px 8px;
}
#StatusPill {
    background-color: %(ACCENT_SOFT)s;
    color: %(ACCENT_HOVER)s;
    border: none;
    border-radius: 9px;
    padding: 4px 9px;
    font-size: 10px;
    font-weight: 800;
}

#InsightPanel {
    margin: 4px 4px 4px 0;
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 16px;
}
#InsightPanel #SectionCard {
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 12px;
}

#PageHeader { background: transparent; }
#PageGlyph {
    min-width: 26px;
    min-height: 26px;
    qproperty-alignment: AlignCenter;
    color: %(ACCENT_HOVER)s;
    background-color: %(ACCENT_SOFT)s;
    border-radius: 13px;
    font-size: 14px;
}
#PageTitle {
    color: %(TEXT)s;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.1px;
}
#PageSubtitle, #MutedLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
#SectionTitle {
    color: %(TEXT)s;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.15px;
    text-transform: none;
}

#HeroCard {
    background-color: %(CARD_BG)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 18px;
}
#HeroTitle {
    color: %(TEXT)s;
    font-family: %(TITLE_FONT)s;
    font-size: 27px;
    font-weight: 700;
}
#HeroSubtitle { color: %(TEXT_MUTED)s; font-size: 12px; }
#HeroBadge, #Badge, #BadgeAccent {
    border-radius: 12px;
    padding: 4px 9px;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.7px;
}
#HeroBadge, #BadgeAccent {
    background-color: %(ACCENT_SOFT)s;
    color: %(ACCENT_HOVER)s;
    border: 1px solid %(INPUT_BORDER)s;
}
#Badge {
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(BORDER_SOFT)s;
}

#SectionCard, #StatCard {
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 15px;
}
#SectionCard:hover, #StatCard:hover { border-color: %(INPUT_BORDER)s; }
#StatTile {
    min-height: 56px;
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 14px;
}
#StatTile:hover { border-color: %(ACCENT)s; background-color: %(ITEM_HOVER)s; }
#StatValue { color: %(ACCENT_HOVER)s; font-size: 19px; font-weight: 800; }
#StatLabel { color: %(TEXT_MUTED)s; font-size: 9px; }

#ActionTile {
    min-height: 88px;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 14px;
    padding: 8px;
}
#ActionTile:hover {
    background-color: %(ACCENT_SOFT)s;
    border-color: %(ACCENT)s;
}
#ActionTile:pressed { background-color: %(ITEM_SELECTED)s; }
#ActionGlyph { color: %(ACCENT_HOVER)s; font-size: 24px; font-weight: 700; }
#ActionLabel { color: %(TEXT)s; font-size: 12px; font-weight: 800; }
#ActionHint { color: %(TEXT_MUTED)s; font-size: 9px; }

#Chip {
    min-height: 22px;
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 11px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
}
#Chip:hover { color: %(TEXT)s; border-color: %(INPUT_BORDER)s; background-color: %(ITEM_HOVER)s; }
#Chip:checked { color: %(ACCENT_HOVER)s; background-color: %(ACCENT_SOFT)s; border-color: %(ACCENT)s; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
    min-height: 24px;
    background-color: %(INPUT_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 9px;
    padding: 5px 9px;
    selection-background-color: %(ACCENT_SOFT)s;
}
QTextEdit, QPlainTextEdit { padding: 8px; }
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover, QDateEdit:hover, QTimeEdit:hover, QDateTimeEdit:hover { border-color: %(ACCENT)s; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {
    background-color: %(CARD_BG)s;
    border-color: %(INPUT_FOCUS)s;
}

QPushButton, #CafeButton, #TopIconButton {
    min-height: 24px;
    color: %(BUTTON_TEXT)s;
    background-color: %(BUTTON_BG)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 9px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 700;
}
QPushButton:hover, #CafeButton:hover, #TopIconButton:hover {
    background-color: %(BUTTON_HOVER)s;
    border-color: %(ACCENT)s;
}
QPushButton#TopAccentButton {
    min-height: 26px;
    background-color: %(ACCENT)s;
    color: %(TEXT_ON_ACCENT)s;
    border: 1px solid %(ACCENT)s;
    border-radius: 9px;
    font-weight: 800;
}
QPushButton#TopAccentButton:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }

#CafeList, #TabList, QTreeWidget {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 2px;
}
#CafeList::item, QTreeWidget::item {
    color: %(TEXT_MUTED)s;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    margin: 2px;
    padding: 7px 8px;
}
/* TabList rows use custom widgets: keep the ::item padding-free so the
   title is not sliced in half (see the sidebar tab desk). */
#TabList::item {
    color: %(TEXT_MUTED)s;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
}
#CafeList::item:hover, #TabList::item:hover, QTreeWidget::item:hover {
    color: %(TEXT)s;
    background-color: %(ITEM_HOVER)s;
    border-color: %(BORDER_SOFT)s;
}
#CafeList::item:selected, #TabList::item:selected, QTreeWidget::item:selected {
    color: %(TEXT)s;
    background-color: %(ACCENT_SOFT)s;
    border-color: %(INPUT_BORDER)s;
}

/* Browser surface: a quiet control deck around the live webpage. */
#Sidebar { background-color: %(SIDEBAR_BG)s; }
#SidebarFooter { background-color: transparent; }
#TabCounter, #ZoomLabel { color: %(TEXT_MUTED)s; font-size: 10px; }
#WorkspaceCombo, #SearchEngine {
    min-height: 28px;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 9px;
    padding: 4px 22px 4px 9px;
    font-size: 10px;
    font-weight: 700;
}
#NewTabBtn {
    min-height: 30px;
    background-color: %(ACCENT_SOFT)s;
    color: %(ACCENT_HOVER)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 10px;
    padding: 6px 10px;
    font-weight: 800;
}
#NewTabBtn:hover { background-color: %(ITEM_SELECTED)s; border-color: %(ACCENT)s; }
#SidebarPanelBtn, #TopBar QToolButton, #TopIconButton {
    min-width: 28px;
    min-height: 28px;
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 4px 6px;
    font-weight: 800;
}
#SidebarPanelBtn:hover, #TopBar QToolButton:hover, #TopIconButton:hover {
    color: %(TEXT)s;
    background-color: %(ITEM_HOVER)s;
    border-color: %(BORDER_SOFT)s;
}
#SidebarPanelBtn:checked { color: %(ACCENT_HOVER)s; background-color: %(ACCENT_SOFT)s; border-color: %(INPUT_BORDER)s; }
#SidebarCollapse {
    min-width: 22px;
    min-height: 22px;
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 8px;
    padding: 0 4px;
    font-size: 13px;
    font-weight: 700;
}
#SidebarCollapse:hover {
    color: %(ACCENT_HOVER)s;
    background-color: %(ITEM_HOVER)s;
    border-color: %(ACCENT)s;
}
#TopBar {
    min-height: 42px;
    margin: 2px;
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 14px;
    padding: 3px;
}
#UrlBar {
    min-height: 28px;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 11px;
    padding: 5px 10px;
    font-weight: 600;
}
#UrlBar:focus { background-color: %(INPUT_BG)s; border-color: %(INPUT_FOCUS)s; }
#WebContainer { background-color: %(MAIN_BG)s; border: none; }
#TabFilter {
    min-height: 28px;
    margin: 0 2px 5px 2px;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 10px;
    padding: 5px 9px;
    font-size: 10px;
}
#DormantTabView {
    background-color: %(MAIN_BG)s;
    border: 1px dashed %(BORDER_SOFT)s;
    border-radius: 14px;
}

QGroupBox {
    background-color: %(CARD_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 12px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    color: %(TEXT)s;
    font-weight: 700;
}
QGroupBox::title { color: %(ACCENT_HOVER)s; padding: 0 6px; }
QTableView, QTreeView {
    background-color: %(CARD_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 10px;
    gridline-color: %(BORDER_SOFT)s;
}
QHeaderView::section {
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT_MUTED)s;
    border: none;
    border-bottom: 1px solid %(BORDER_SOFT)s;
    padding: 6px;
    font-size: 10px;
    font-weight: 800;
}
QMenu {
    background-color: %(MENU_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: %(RADIUS)s;
    padding: 5px;
}
QMenu::item { padding: 7px 20px 7px 10px; border-radius: %(RADIUS_XS)s; }
QMenu::item:selected { background-color: %(ACCENT_SOFT)s; color: %(TEXT)s; }

/* ---------- 5.6 refinement: one geometry scale, gentler focus ----------------
   Every radius below resolves through core/theme_data.DEFAULTS, so a surface
   can no longer invent its own corner. */
QPushButton, #CafeButton, #TopIconButton { border-radius: %(RADIUS_SM)s; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit { border-radius: %(RADIUS_SM)s; }
#HeroCard { border-radius: %(RADIUS_LG)s; }
#SectionCard, #StatCard, #ActionTile, #StatTile, #InsightPanel { border-radius: %(RADIUS)s; }
#ShellOmnibar { border-radius: %(RADIUS_LG)s; }
#UrlBar { border-radius: %(RADIUS_SM)s; }
/* Anything pill-shaped (connection state, zoom chip, status pill, café chips)
   uses the pill token instead of spelling out 999px. */
#SiteStatePill, #ZoomLabel, #StatusPill, #Chip, #Pill {
    border-radius: %(RADIUS_PILL)s;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus,
#UrlBar:focus, #ShellOmnibar:focus {
    border: 1px solid %(ACCENT)s;
}
/* Keyboard users get the same "where am I" signal as a mouse hover has always
   had: focus is drawn on every interactive control, not only on text fields. */
QPushButton:focus, QToolButton:focus, #CafeButton:focus, #TopIconButton:focus,
#SidebarPanelBtn:focus, #SidebarCollapse:focus {
    border: 1px solid %(ACCENT)s;
    color: %(ACCENT_HOVER)s;
}

/* ---------- 5.7 browser control deck: one calm, unified toolbar ---------- */
#TopIconButton { font-size: 13px; font-weight: 700; }
#SidebarPanelBtn {
    min-width: 34px; min-height: 32px;
    font-size: 15px;
    border-radius: %(RADIUS_SM)s;
}
#SidebarPanelBtn:hover { background-color: %(ITEM_HOVER)s; border-color: %(BORDER_SOFT)s; color: %(TEXT)s; }
#SidebarPanelBtn:checked {
    background-color: %(ACCENT_SOFT)s;
    border-color: %(INPUT_BORDER)s;
    color: %(ACCENT_HOVER)s;
}
#NewTabBtn { min-height: 32px; border-radius: 10px; }
#OptionsBtn {
    min-height: 32px;
    background-color: %(BUTTON_BG)s;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 10px;
    padding: 5px 12px;
    font-weight: 700;
}
#OptionsBtn:hover { background-color: %(BUTTON_HOVER)s; border-color: %(ACCENT)s; color: %(TEXT)s; }
#TabList::item:selected { border-left: 3px solid %(ACCENT)s; }
#TabCounter { color: %(TEXT_MUTED)s; font-size: 10px; font-weight: 700; letter-spacing: 0.4px; }

/* ---------- 6.5 final visual polish ----------
   Focus rings, hover lifts, dialog buttons and the floating helpers
   (find bar / toast) follow the theme instead of hard-coded colors. */

/* Primary action pop: accent-filled primary buttons stand out on cards. */
QPushButton#TopAccentButton { padding: 6px 14px; }

/* Softer, consistent item selection everywhere (lists, trees, combo popups). */
QListWidget::item:selected, QTreeWidget::item:selected, QComboBox QAbstractItemView::item:selected {
    background-color: %(ITEM_SELECTED)s;
    color: %(TEXT)s;
    border-radius: 8px;
}

/* Tab rows: clearer active state with the accent bar + filled chip. */
#TabList::item:selected {
    background-color: %(ACCENT_SOFT)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-left: 3px solid %(ACCENT)s;
    color: %(TEXT)s;
    font-weight: 700;
}

/* Combo popup rows mirror list rows. */
QComboBox QAbstractItemView { outline: none; }
QComboBox QAbstractItemView::item { min-height: 24px; padding: 4px 8px; border-radius: 6px; }

/* Tooltips: slightly larger padding, softer border. */
QToolTip {
    border: 1px solid %(INPUT_BORDER)s;
    background-color: %(MENU_BG)s;
    color: %(TEXT)s;
    padding: 6px 10px;
    border-radius: 8px;
}

/* Floating helpers styled by the shell, not hard-coded. */
#FindBar {
    background-color: %(CARD_BG)s;
    border: 1px solid %(INPUT_BORDER)s;
    border-radius: 10px;
}
#FindBar QLineEdit {
    background-color: %(INPUT_BG)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 8px;
}
#FindBar QLineEdit:focus { border-color: %(ACCENT)s; }
#ToastLabel {
    background-color: %(MENU_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(ACCENT)s;
    border-radius: 12px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}
/* Chrome-style thin page-load bar under the toolbar. */
#LoadProgress {
    background: transparent;
    border: none;
    max-height: 3px;
    margin: 0;
}
#LoadProgress::chunk {
    background-color: %(ACCENT)s;
    border-radius: 1px;
}
/* Opera GX-style web panel dock beside the page. */
#WebPanelDock {
    background-color: %(CARD_BG)s;
    border-left: 1px solid %(BORDER_SOFT)s;
}
/* Vivaldi/Arc-style split view dock (left side). */
#SplitDock {
    background-color: %(CARD_BG)s;
    border-right: 1px solid %(BORDER_SOFT)s;
}
#WebPanelHeader {
    background-color: %(MAIN_BG_ALT)s;
    border-bottom: 1px solid %(BORDER_SOFT)s;
}
#WebPanelView {
    background-color: %(MAIN_BG)s;
}
/* Chrome-style save-password prompt bar. */
#SavePasswordBar {
    background-color: %(ACCENT_SOFT)s;
    border-top: 1px solid %(ACCENT)s;
}
/* Edge-Copilot-style AI sidebar dock. */
#AISideDock {
    background-color: %(CARD_BG)s;
    border-left: 1px solid %(BORDER_SOFT)s;
}
/* Slim right dock rail (panel + AI toggles). */
#DockRail {
    background-color: %(SIDEBAR_BG)s;
    border-left: 1px solid %(BORDER_SOFT)s;
}
/* Chrome-style link-hover target strip. */
#LinkPreview {
    background-color: %(CARD_BG)s;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
}

/* ---------- 6.6 browser chrome: flat icons, one address field ----------------
   Two reports from a real session drive this block: the toolbar read as a row of
   separate boxes, and the caret on the "Control" button was drawn outside its
   own button.  Both are layout artefacts of styling every control individually. */

/* Icon buttons are flat until touched. The earlier type-level rule
   (QPushButton, #CafeButton, #TopIconButton) put a border and a filled
   background on every glyph, which is what made the toolbar read as a form.
   #TopIconButton is only ever an icon-only control (toolbar glyphs, dock and
   panel headers), so one flat rule is enough — hover and focus still answer. */
#TopIconButton {
    background-color: transparent;
    border: 1px solid transparent;
}
#TopIconButton:hover {
    background-color: %(ITEM_HOVER)s;
    border-color: %(BORDER_SOFT)s;
    color: %(TEXT)s;
}
#TopIconButton:focus {
    background-color: transparent;
    border-color: %(ACCENT)s;
    color: %(ACCENT_HOVER)s;
}
/* A held/checked glyph (dock toggles) keeps a fill so "on" is still readable. */
#TopIconButton:checked {
    background-color: %(ITEM_SELECTED)s;
    border-color: %(ITEM_SELECTED_BORDER)s;
    color: %(ACCENT_HOVER)s;
}

/* Address cluster: the connection pill and the address share one rounded field
   instead of sitting in two adjacent boxes. */
#AddressCluster {
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(BORDER_SOFT)s;
    border-radius: %(RADIUS_SM)s;
}
/* Focus is painted on the frame (the field itself is borderless inside it). The
   property is set in SearchWindow._set_address_cluster_focus. */
#AddressCluster[focused="true"] {
    background-color: %(INPUT_BG)s;
    border-color: %(ACCENT)s;
}
#AddressCluster #UrlBar,
#AddressCluster #UrlBar:hover,
#AddressCluster #UrlBar:focus {
    background: transparent;
    border: none;
}

/* Menu carets: Qt anchors ::menu-indicator to the bottom-right of a styled
   button, so "⚙ Control" grew an arrow below its own edge. The caret now lives
   in the button label (window.py) and the subcontrol is switched off. */
QPushButton::menu-indicator,
QToolButton::menu-indicator {
    image: none;
    width: 0;
    height: 0;
}
""" % p + _VERB_QSS % p


def dialog_qss(mode: str = "cafe-night", accent: str | None = None):
    """Stylesheet shared by all modal dialogs — consistent with the modern main shell."""
    p = _palette(mode, accent)
    return """
    QDialog {
        background-color: %(MAIN_BG)s; color: %(TEXT)s; font-size: 13px;
    }
    QLabel { color: %(TEXT)s; font-size: 13px; }
    QLabel#MutedLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
    QPushButton {
        background-color: %(BUTTON_BG)s; color: %(BUTTON_TEXT)s;
        border: 1px solid %(INPUT_BORDER)s; border-radius: %(RADIUS_SM)s;
        padding: 6px 12px; font-size: 13px; font-weight: 600;
    }
    QPushButton:hover { background-color: %(BUTTON_HOVER)s; border-color: %(ACCENT)s; }
    QPushButton:pressed { background-color: %(ITEM_SELECTED)s; }
    QPushButton:disabled { color: %(TEXT_DIM)s; background-color: %(MAIN_BG_ALT)s; border-color: %(BORDER_SOFT)s; }
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
        background-color: %(INPUT_BG)s; color: %(TEXT)s;
        border: 1px solid %(INPUT_BORDER)s; border-radius: %(RADIUS_SM)s;
        padding: 5px 9px; font-size: 13px; selection-background-color: %(MENU_ITEM_SEL)s;
        selection-color: %(TEXT)s;
    }
    QLineEdit:hover, QTextEdit:hover, QComboBox:hover { border-color: %(ACCENT)s; }
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: %(INPUT_FOCUS)s; }
    QListWidget, QTreeWidget {
        background-color: %(CARD_BG)s; color: %(TEXT)s;
        border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s; padding: 4px; font-size: 13px;
    }
    QListWidget::item, QTreeWidget::item { padding: 6px 7px; border-radius: 6px; }
    QListWidget::item:hover, QTreeWidget::item:hover { background-color: %(ITEM_HOVER)s; border-radius: 6px; }
    QListWidget::item:selected, QTreeWidget::item:selected { background-color: %(MENU_ITEM_SEL)s; color: %(TEXT)s; border-radius: 6px; }
    QCheckBox, QRadioButton { color: %(TEXT_MUTED)s; spacing: 8px; }
    QCheckBox::indicator, QRadioButton::indicator {
        width: 16px; height: 16px; border-radius: 5px;
        border: 1px solid %(INPUT_BORDER)s; background: %(INPUT_BG)s;
    }
    QRadioButton::indicator { border-radius: 8px; }
    QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %(ACCENT)s; }
    QCheckBox::indicator:checked { background: %(ACCENT)s; border-color: %(ACCENT)s; }
    QRadioButton::indicator:checked { border: 5px solid %(ACCENT)s; background: %(INPUT_BG)s; }
    QComboBox QAbstractItemView {
        background-color: %(MENU_BG)s; color: %(TEXT)s;
        border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s;
        selection-background-color: %(MENU_ITEM_SEL)s; selection-color: %(TEXT)s;
    }
    QGroupBox {
        border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s; margin-top: 10px; padding-top: 8px;
    }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; color: %(ACCENT_HOVER)s; }

    /* shared components */
    #PageHeader { background: transparent; }
    #PageGlyph { color: %(ACCENT_HOVER)s; font-size: 20px; }
    #PageTitle { color: %(TEXT)s; }
    #PageSubtitle { color: %(TEXT_MUTED)s; font-size: 11px; }
    #StatTile { background-color: %(CARD_BG)s; border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s; }
    #StatValue { color: %(ACCENT_HOVER)s; }
    #StatLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
    #SectionHeaderRow { background: transparent; }
    #EmptyState { background-color: %(CARD_BG)s; border: 1px dashed %(BORDER_SOFT)s; border-radius: %(RADIUS_SM)s; }
    #EmptyGlyph { color: %(ACCENT_SOFT)s; font-size: 26px; }
    #ActionTile { background-color: %(CARD_BG)s; border: 1px solid %(BORDER_SOFT)s; border-radius: %(RADIUS)s; padding: 6px; }
    #ActionTile:hover { border-color: %(ACCENT)s; background-color: %(ITEM_HOVER)s; }
    #ActionGlyph { color: %(ACCENT_HOVER)s; font-size: 22px; }
    #ActionLabel { color: %(TEXT)s; font-weight: 700; }
    #Chip { background-color: %(MAIN_BG_ALT)s; color: %(TEXT_MUTED)s; border: 1px solid %(BORDER_SOFT)s; border-radius: 999px; padding: 5px 13px; font-size: 11px; font-weight: 600; }
    #Chip:hover { border-color: %(ACCENT)s; color: %(TEXT)s; }
    #Chip:checked { background-color: %(ACCENT_SOFT)s; color: %(ACCENT_HOVER)s; border-color: %(ACCENT)s; }
    #Badge { background-color: %(MAIN_BG_ALT)s; color: %(TEXT_MUTED)s; border: 1px solid %(BORDER_SOFT)s; border-radius: 999px; padding: 2px 10px; font-size: 10px; font-weight: 700; }
    #BadgeAccent { background-color: %(ACCENT_SOFT)s; color: %(ACCENT_HOVER)s; border: 1px solid %(INPUT_BORDER)s; border-radius: 999px; padding: 2px 10px; font-size: 10px; font-weight: 800; }

    /* Dialogs use the same paper-card rhythm as the full workspace. */
    QDialog { background-color: %(MAIN_BG)s; }
    QDialog QWidget { font-family: %(FONT_FAMILY)s; }
    QPushButton { min-height: 25px; border-radius: 9px; padding: 5px 11px; }
    /* The dialog's default action (QMessageBox Yes/OK) pops with the accent. */
    QPushButton:default {
        background-color: %(ACCENT)s;
        color: %(TEXT_ON_ACCENT)s;
        border-color: %(ACCENT)s;
        font-weight: 800;
    }
    QPushButton:default:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit { min-height: 24px; border-radius: 9px; }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: %(ACCENT)s; }
    QListWidget, QTreeWidget { background-color: %(CARD_BG)s; border: 1px solid %(BORDER_SOFT)s; border-radius: 12px; padding: 3px; }
    QListWidget::item, QTreeWidget::item { border-radius: 8px; padding: 7px; }
    QListWidget::item:selected, QTreeWidget::item:selected {
        background-color: %(ITEM_SELECTED)s; color: %(TEXT)s; border-left: 3px solid %(ACCENT)s;
    }
    QGroupBox { background-color: %(CARD_BG)s; border-radius: 12px; padding: 11px 9px 9px 9px; }
    QToolTip {
        background-color: %(MENU_BG)s; color: %(TEXT)s;
        border: 1px solid %(INPUT_BORDER)s; border-radius: 8px; padding: 6px 10px;
    }
    """ % p + _VERB_QSS % p


def dynamic_main_widget_css(mode: str, phase: int, accent: str | None = None) -> str:
    """Subtle shifting gradient on #MainWidget when user enables dynamic background."""
    p = _palette(mode, accent)
    a, b = (p["MAIN_BG"], p["MAIN_BG_ALT"]) if (phase % 2) == 0 else (p["MAIN_BG_ALT"], p["MAIN_BG"])
    return (
        "#MainWidget {\n"
        "  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(a)s, stop:1 %(b)s);\n"
        "}"
        % {"a": a, "b": b}
    )


def collapse_btn_qss(mode: str = "cafe-night", accent: str | None = None):
    p = _palette(mode, accent)
    return """
    QToolButton {
        background: transparent; color: %(TEXT_MUTED)s; border: 1px solid transparent;
        border-radius: 8px; min-width: 32px; min-height: 32px; font-size: 14px;
        font-weight: 700; padding: 0;
    }
    QToolButton:hover { color: %(ACCENT_HOVER)s; background: %(ITEM_HOVER)s; border-color: %(BORDER_SOFT)s; }
    QToolButton[collapsed="true"] {
        background: %(ACCENT_SOFT)s; color: %(ACCENT_HOVER)s;
        border: 2px solid %(ACCENT)s; border-radius: 10px;
    }
    QToolButton[collapsed="true"]:hover {
        background: %(ITEM_SELECTED)s; color: %(ACCENT_HOVER)s; border-color: %(ACCENT_HOVER)s;
    }
    """ % p


def animate_entrance(widget, duration: int = 160) -> None:
    """Present immediately; never composite native controls into an opacity layer.

    Removing QGraphicsOpacityEffect in its animation-finished callback can
    delete the emitting native object mid-signal and crash during rapid teardown.
    Such effects also interfere with native popup hit testing. Keep the shared
    presentation hook without sacrificing interaction reliability for a fade.
    """
    if widget is not None:
        widget.update()



