# Pure data + color logic moved to litebrowser.core.theme_data so the data
# layer can validate theme/accent names without importing Qt. Re-exported
# here so every existing ``theme.<name>`` reference keeps working unchanged.
from litebrowser.core.theme_data import (  # noqa: F401
    _ACCENT_KEYS,
    ACCENTS,
    DEFAULT_ACCENT,
    DEFAULT_THEME,
    DEFAULTS,
    PALETTES,
    THEME_LABELS,
    _accent_override,
    _blend_hex,
    _derive_semantics,
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

    color = QColor(tokens.get("ACCENT", "#5F6E55"))
    if not is_today:
        color.setAlphaF(0.55)
    return color


# ---------- dialog verbs: one action, one row -------------------------------
# Dialogs had grown rows of five to seven identical buttons, so the action the
# dialog existed for was indistinguishable from "Delete everything" two pixels
# away. ``ui/dialogs/common.py`` gives every verb a role: exactly one filled
# primary per dialog, quiet ghosts for the verbs worth keeping visible, subdued
# buttons for Close, and the occasional verbs inside one "⋯ More" menu. Kept as
# a single block appended to both sheets so the dialog chrome cannot drift from
# the full workspace.
_VERB_QSS = """
QPushButton#PrimaryButton {
    background-color: %(ACCENT)s;
    color: %(TEXT_ON_ACCENT)s;
    border: 1px solid %(ACCENT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 16px;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }
QPushButton#PrimaryButton:disabled {
    background-color: %(MAIN_BG_ALT)s; color: %(TEXT_DIM)s; border-color: %(RULE)s;
}
QPushButton#GhostButton {
    background-color: transparent;
    color: %(TEXT)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 13px;
    font-weight: 600;
}
QPushButton#GhostButton:hover { background-color: %(ITEM_HOVER)s; border-color: %(RULE_STRONG)s; color: %(TEXT)s; }
QPushButton#QuietButton {
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid transparent;
    border-radius: %(RADIUS_SM)s;
    padding: 5px 12px;
    font-weight: 600;
}
QPushButton#QuietButton:hover { background-color: %(ITEM_HOVER)s; color: %(TEXT)s; }
QPushButton#DangerButton {
    background-color: transparent;
    color: %(DANGER)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 13px;
    font-weight: 600;
}
QPushButton#DangerButton:hover { background-color: %(DANGER_SOFT)s; border-color: %(DANGER)s; color: %(DANGER)s; }
QPushButton[compactIcon="true"] { padding: 0; min-width: 0; min-height: 0; font-size: 15px; }
QToolButton[compactIcon="true"] { padding: 0; min-width: 0; min-height: 0; }
QCalendarWidget QAbstractItemView { selection-background-color: %(ACCENT)s; selection-color: %(TEXT_ON_ACCENT)s; outline: none; }
QCalendarWidget QToolButton { color: %(TEXT)s; background-color: transparent; border: none; padding: 0 5px; }
QCalendarWidget QToolButton:hover { background-color: %(ITEM_HOVER)s; }
QMenu#DialogOverflowMenu { padding: 6px; }
QMenu#DialogOverflowMenu::item { padding: 6px 22px 6px 12px; }
QMenu#DialogOverflowMenu::separator { height: 1px; margin: 5px 8px; background-color: %(RULE)s; }
"""


def main_qss(mode: str = "minimal", accent: str | None = None):
    p = _palette(mode, accent)
    return """
/* ==========================================================================
   MEI — THE QUIET TABLE
   --------------------------------------------------------------------------
   One grammar for the whole application: warm paper surfaces, hairline rules
   instead of boxes-in-boxes, a serif display voice over a plain working sans,
   and a single accent used like ink (a mark, a seal, a filled primary) rather
   than as decoration.  Radii, spacing and type come from core/theme_data so a
   page cannot invent a second design.
   Palette accent ink: %(ACCENT_BASE)s
   ========================================================================== */

/* ---------- foundation ---------- */
QMainWindow, QWidget {
    background-color: %(MAIN_BG)s;
    color: %(TEXT)s;
    font-family: %(FONT_FAMILY)s;
    font-size: 13px;
}
#ShellRoot, #MainWidget, #ContentArea, #HomeDashboard, #SettingsContent,
#AIWorkspace, #PersonalWorkspace, #LibraryWorkspace, #SettingsWorkspace,
#HistoryWorkspace, #HomeScrollContent {
    background-color: %(MAIN_BG)s;
}
QMainWindow::separator { background-color: %(RULE)s; width: 1px; height: 1px; }
QLabel { color: %(TEXT)s; background: transparent; border: none; }
QWidget#qt_scrollarea_viewport { background-color: %(MAIN_BG)s; }

QToolTip {
    background-color: %(MENU_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(RULE_STRONG)s;
    border-radius: %(RADIUS_XS)s;
    padding: 6px 10px;
    font-size: 11px;
}
QScrollBar:vertical { width: 10px; margin: 2px; background: transparent; }
QScrollBar::handle:vertical {
    min-height: 28px; background: %(RULE_STRONG)s; border-radius: 5px; margin: 2px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed { background: %(TEXT_MUTED)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { height: 10px; margin: 2px; background: transparent; }
QScrollBar::handle:horizontal {
    min-width: 28px; background: %(RULE_STRONG)s; border-radius: 5px; margin: 2px;
}
QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed { background: %(TEXT_MUTED)s; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QSplitter::handle { background-color: transparent; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }
QSplitter::handle:hover { background-color: %(ACCENT_QUIET)s; }

QScrollArea { border: none; background: transparent; }
QScrollArea#HomeScroll, QScrollArea#SettingsScroll { border: none; background-color: %(MAIN_BG)s; }
QScrollArea#HomeScroll > QWidget > QWidget, QScrollArea#SettingsScroll > QWidget > QWidget { background-color: %(MAIN_BG)s; }
QStackedWidget { background-color: %(MAIN_BG)s; }

/* ---------- the masthead voice: serif display, clay marks ---------- */
#Masthead, #HomeMasthead { background: transparent; }
#Eyebrow, #MastheadEyebrow {
    color: %(CLAY)s;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
}
#DisplayTitle, #MastheadTitle {
    color: %(TEXT)s;
    font-family: %(FONT_DISPLAY)s;
    font-size: 31px;
    font-weight: 600;
}
#DisplayDeck, #MastheadDeck { color: %(TEXT_MUTED)s; font-size: 13px; }
#MastheadDate { color: %(TEXT_MUTED)s; font-size: 11px; }
#MastheadRule { background-color: %(RULE_STRONG)s; border: none; }
#HeroTitle {
    color: %(TEXT)s;
    font-family: %(FONT_DISPLAY)s;
    font-size: 26px;
    font-weight: 600;
}
#HeroSubtitle { color: %(TEXT_MUTED)s; font-size: 12px; }
#QuietRule { background-color: %(RULE)s; border: none; }
#PageHeader { background: transparent; }
#PageGlyph {
    color: %(ACCENT_HOVER)s;
    background-color: transparent;
    font-size: 13px;
}
#PageTitle {
    color: %(TEXT)s;
    font-family: %(FONT_DISPLAY)s;
    font-size: 23px;
    font-weight: 600;
}
#PageSubtitle, #MutedLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
#SectionTitle { color: %(TEXT)s; font-size: 12px; font-weight: 700; }
#SectionHeaderRow, #SectionActions { background: transparent; }
#SectionKicker { color: %(TEXT_MUTED)s; font-size: 10px; }
#Numeric, #StatValue { font-family: %(FONT_DISPLAY)s; color: %(TEXT)s; }

/* ---------- shell top bar ---------- */
#ShellTopBar {
    min-height: 54px;
    background-color: %(SURFACE)s;
    border: none;
    border-bottom: 1px solid %(RULE)s;
    padding: 8px 18px;
}
#BrandWrap { background: transparent; }
#BrandGlyph {
    color: %(TEXT)s;
    font-family: %(FONT_DISPLAY)s;
    font-size: 19px;
    font-weight: 700;
    background: transparent;
    border: none;
    min-width: 30px;
    min-height: 30px;
    qproperty-alignment: AlignCenter;
}
#BrandName {
    color: %(TEXT)s;
    font-family: %(FONT_DISPLAY)s;
    font-size: 19px;
    font-weight: 700;
}
#BrandSub {
    color: %(CLAY)s;
    font-size: 9px;
    font-weight: 800;
    text-transform: uppercase;
}
#ShellOmnibar {
    min-height: 36px;
    padding: 7px 12px;
    border-radius: %(RADIUS_SM)s;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(RULE)s;
    color: %(TEXT)s;
    font-size: 12px;
}
#ShellOmnibar:hover { background-color: %(SURFACE)s; border-color: %(RULE_STRONG)s; }
#ShellOmnibar:focus { background-color: %(SURFACE)s; border: 1px solid %(ACCENT)s; }
QPushButton#TopAccentButton {
    min-height: 26px;
    background-color: %(ACCENT)s;
    color: %(TEXT_ON_ACCENT)s;
    border: 1px solid %(ACCENT)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 14px;
    font-weight: 700;
}
QPushButton#TopAccentButton:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }
QPushButton#TopAccentButton:disabled { background-color: %(MAIN_BG_ALT)s; color: %(TEXT_DIM)s; border-color: %(RULE)s; }

/* ---------- the wayfinding spine (left rail) ---------- */
#LeftRail, #Sidebar {
    background-color: %(NAV_BG)s;
    border: none;
    border-right: 1px solid %(RULE)s;
}
#RailSectionLabel {
    color: %(TEXT_MUTED)s;
    font-size: 9px;
    font-weight: 800;
    text-transform: uppercase;
    padding: 14px 10px 4px 10px;
}
#RailMeta { background: transparent; border: none; color: %(TEXT_MUTED)s; font-size: 10px; padding: 0 2px; }
#RailBrand {
    color: %(TEXT)s;
    font-family: %(FONT_DISPLAY)s;
    font-size: 17px;
    font-weight: 700;
    padding: 2px 6px 0 6px;
}
#RailProfile { color: %(TEXT_MUTED)s; font-size: 10px; padding: 0 6px 6px 6px; }
#NavButton {
    min-height: 32px;
    text-align: left;
    color: %(TEXT_MUTED)s;
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 0;
    padding: 7px 10px;
    font-size: 12px;
    font-weight: 600;
}
#NavButton:hover {
    color: %(TEXT)s;
    background-color: %(ITEM_HOVER)s;
    border-left-color: %(RULE_STRONG)s;
}
#NavButton:checked {
    color: %(ACCENT_HOVER)s;
    background-color: %(ACCENT_WASH)s;
    border-left: 2px solid %(ACCENT)s;
    font-weight: 700;
}
#NavButton:focus { border-left-color: %(ACCENT)s; color: %(TEXT)s; }
#NavButton[iconOnly="true"] {
    padding: 7px 0;
    text-align: center;
    font-size: 15px;
    font-weight: 600;
}
#NavButton[iconOnly="true"]:checked { border-left-width: 2px; }
#NavToggle {
    color: %(TEXT_MUTED)s;
    background: transparent;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
    min-width: 24px;
    max-width: 26px;
    min-height: 24px;
    max-height: 26px;
    padding: 0;
    font-size: 11px;
    font-weight: 700;
}
#NavToggle:hover { color: %(TEXT)s; background-color: %(ITEM_HOVER)s; border-color: %(RULE_STRONG)s; }

/* ---------- status strip: a footnote, not a card ---------- */
#StatusStrip {
    min-height: 26px;
    background-color: transparent;
    border: none;
    border-top: 1px solid %(RULE)s;
    border-radius: 0;
    padding: 4px 6px;
}
#StatusPill {
    background-color: transparent;
    color: %(CLAY)s;
    border: none;
    padding: 3px 2px;
    font-size: 10px;
    font-weight: 700;
}
#TabCounter, #ZoomLabel { color: %(TEXT_MUTED)s; font-size: 10px; font-weight: 600; }
#TabDeskTitle { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 12px; font-weight: 600; }
#SiteStatePill, #Pill { background-color: %(MAIN_BG_ALT)s; color: %(TEXT_MUTED)s; border: 1px solid %(RULE)s; padding: 3px 10px; font-size: 10px; font-weight: 700; }
#ZoomLabel { background-color: transparent; border: none; padding: 2px 6px; }
#SiteStatePill, #ZoomLabel, #StatusPill, #Chip, #Pill { border-radius: %(RADIUS_PILL)s; }

/* ---------- companion rail (insights) ---------- */
#InsightPanel {
    background-color: %(NAV_BG)s;
    border: none;
    border-left: 1px solid %(RULE)s;
    border-radius: 0;
    padding: 4px;
}
#InsightPanel #SectionCard {
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
}
#InsightPanel QLabel#SectionTitle { font-size: 12px; }
#InsightPanel QListWidget { background: transparent; border: none; }

/* ---------- surfaces ---------- */
#SectionCard, #StatCard, #ActionTile, #StatTile, #InsightPanel { border-radius: %(RADIUS)s; }
#SectionCard {
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
}
#SectionCard:hover { border-color: %(RULE_STRONG)s; }
#StatCard { background-color: %(SURFACE)s; border: 1px solid %(RULE)s; }
#StatCard:hover { border-color: %(RULE_STRONG)s; }
#StatCard QLabel { font-weight: 600; }
#HeroCard {
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_LG)s;
}
#HeroBadge, #Badge, #BadgeAccent {
    border-radius: %(RADIUS_PILL)s;
    padding: 3px 10px;
    font-size: 9px;
    font-weight: 700;
}
#HeroBadge, #BadgeAccent {
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s;
}
#Badge {
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s;
}
#StatTile {
    min-height: 54px;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: %(RADIUS_XS)s;
}
#StatTile:hover { border-color: %(RULE)s; background-color: %(ITEM_HOVER)s; }
#StatValue { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 22px; font-weight: 600; }
/* A zero is still a fact, but it should not compete with a number that matters. */
#StatValue[quiet="true"] { color: %(TEXT_MUTED)s; font-weight: 500; }
#StatLabel { color: %(TEXT_MUTED)s; font-size: 10px; }
#StatRow { background: transparent; }
#EmptyState {
    background-color: %(SURFACE_SUNK)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
}
#EmptyGlyph { color: %(TEXT_DIM)s; font-size: 16px; }

/* The desk: one emphasised panel, open groupings for the rest. */
#DeskPanel {
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE)s;
    border-left: 3px solid %(ACCENT)s;
    border-radius: %(RADIUS)s;
}
#DeskPanel[emphasis="quiet"] {
    border-left: 1px solid %(RULE)s;
    background-color: %(SURFACE)s;
}
#DeskPanel[emphasis="open"] {
    border: none;
    border-radius: 0;
    background-color: transparent;
}
#DeskEyebrow { color: %(CLAY)s; font-size: 9px; font-weight: 800; text-transform: uppercase; }
#DeskTitle { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 19px; font-weight: 600; }
#DeskLine { color: %(TEXT_MUTED)s; font-size: 12px; }
#DeskHint { color: %(TEXT_MUTED)s; font-size: 11px; }
#QuietPanel { background: transparent; border: none; }
#RowTitle { color: %(TEXT)s; font-size: 12px; font-weight: 600; }
#RowMeta { color: %(TEXT_MUTED)s; font-size: 10px; }

/* ---------- chips / filters ---------- */
#Chip, #ChipButton, #SettingsTab {
    min-height: 22px;
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_PILL)s;
    padding: 3px 11px;
    font-size: 10px;
    font-weight: 600;
}
#Chip:hover, #ChipButton:hover, #SettingsTab:hover { color: %(TEXT)s; border-color: %(RULE_STRONG)s; background-color: %(ITEM_HOVER)s; }
#Chip:checked, #ChipButton:checked, #SettingsTab:checked { color: %(ACCENT_HOVER)s; background-color: %(ACCENT_WASH)s; border-color: %(ACCENT)s; }
#SettingsTab { min-height: 26px; padding: 5px 15px; font-size: 11px; }

/* ---------- buttons ---------- */
QPushButton, #CafeButton {
    min-height: 24px;
    background-color: %(BUTTON_BG)s;
    color: %(BUTTON_TEXT)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover, #CafeButton:hover { background-color: %(BUTTON_HOVER)s; border-color: %(RULE_STRONG)s; }
QPushButton:pressed, #CafeButton:pressed { background-color: %(ITEM_SELECTED)s; }
QPushButton:disabled { color: %(TEXT_DIM)s; background-color: transparent; border-color: %(RULE)s; }
QPushButton:focus, QToolButton:focus, #CafeButton:focus, #TopIconButton:focus,
#SidebarPanelBtn:focus, #SidebarCollapse:focus {
    border: 1px solid %(ACCENT)s;
    color: %(TEXT)s;
}
QPushButton:default {
    background-color: %(ACCENT)s;
    color: %(TEXT_ON_ACCENT)s;
    border-color: %(ACCENT)s;
}
QPushButton:default:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }
QPushButton::menu-indicator, QToolButton::menu-indicator { image: none; width: 0; height: 0; }

#TopIconButton {
    min-width: 28px;
    min-height: 28px;
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid transparent;
    border-radius: %(RADIUS_XS)s;
    padding: 4px 6px;
    font-size: 13px;
    font-weight: 700;
}
#TopIconButton:hover { background-color: %(ITEM_HOVER)s; border-color: %(RULE)s; color: %(TEXT)s; }
#TopIconButton:checked { background-color: %(ACCENT_WASH)s; border-color: %(ACCENT)s; color: %(ACCENT_HOVER)s; }
#ToolbarChip {
    min-height: 26px;
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
    padding: 5px 10px;
    font-size: 10px;
    font-weight: 800;
}
#ToolbarChip:hover { color: %(TEXT)s; background-color: %(ITEM_HOVER)s; border-color: %(RULE_STRONG)s; }
#SidebarPanelBtn {
    min-width: 32px; min-height: 30px;
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid transparent;
    border-radius: %(RADIUS_XS)s;
    padding: 4px 6px;
    font-size: 14px;
    font-weight: 700;
}
#SidebarPanelBtn:hover { color: %(TEXT)s; background-color: %(ITEM_HOVER)s; border-color: %(RULE)s; }
#SidebarPanelBtn:checked { color: %(ACCENT_HOVER)s; background-color: %(ACCENT_WASH)s; border-color: %(ACCENT)s; }
#SidebarCollapse {
    min-width: 22px; min-height: 22px;
    background-color: transparent; color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s; border-radius: %(RADIUS_XS)s;
    padding: 0 4px; font-size: 12px; font-weight: 700;
}
#SidebarCollapse:hover { color: %(TEXT)s; background-color: %(ITEM_HOVER)s; border-color: %(RULE_STRONG)s; }
#OptionsBtn {
    min-height: 30px;
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
    padding: 5px 12px;
    font-weight: 600;
}
#OptionsBtn:hover { background-color: %(ITEM_HOVER)s; border-color: %(RULE_STRONG)s; color: %(TEXT)s; }
QPushButton, #CafeButton, #TopIconButton { border-radius: %(RADIUS_SM)s; }

/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
    min-height: 24px;
    background-color: %(INPUT_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 10px;
    selection-background-color: %(ACCENT_WASH)s;
    selection-color: %(TEXT)s;
}
QTextEdit, QPlainTextEdit { padding: 8px; }
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover,
QDateEdit:hover, QTimeEdit:hover, QDateTimeEdit:hover { border-color: %(RULE_STRONG)s; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {
    background-color: %(INPUT_BG)s;
    border: 1px solid %(ACCENT)s;
}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled { color: %(TEXT_DIM)s; background-color: %(MAIN_BG_ALT)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { width: 9px; height: 9px; }
QComboBox QAbstractItemView {
    background-color: %(MENU_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(RULE_STRONG)s;
    border-radius: %(RADIUS_XS)s;
    padding: 4px;
    outline: none;
    selection-background-color: %(ACCENT_WASH)s;
    selection-color: %(TEXT)s;
}
QComboBox QAbstractItemView::item { min-height: 24px; padding: 4px 8px; border-radius: 6px; }
QComboBox QAbstractItemView::item:selected { background-color: %(ACCENT_WASH)s; color: %(TEXT)s; }
#SearchEngine, #WorkspaceCombo {
    min-height: 28px;
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid transparent;
    border-radius: %(RADIUS_XS)s;
    padding: 4px 22px 4px 9px;
    font-size: 11px;
    font-weight: 600;
}
#SearchEngine:hover, #WorkspaceCombo:hover { background-color: %(ITEM_HOVER)s; border-color: %(RULE)s; color: %(TEXT)s; }
#SearchEngine::drop-down, #WorkspaceCombo::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 22px; border: none; background: transparent; }
#SearchEngine::down-arrow, #WorkspaceCombo::down-arrow { width: 9px; height: 9px; }
#TabFilter {
    min-height: 28px;
    margin: 0 2px 6px 2px;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
    padding: 5px 9px;
    font-size: 11px;
}
#TabFilter:focus { background-color: %(INPUT_BG)s; border-color: %(ACCENT)s; }

/* ---------- lists ---------- */
#CafeList, #TabList, QListWidget, QTreeWidget {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 2px;
}
QListWidget::item, QTreeWidget::item {
    color: %(TEXT)s;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: %(RADIUS_XS)s;
    margin: 1px;
    padding: 7px 9px;
}
#TabList::item {
    color: %(TEXT_MUTED)s;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: %(RADIUS_XS)s;
    margin: 0;
    padding: 0;
}
QListWidget::item:hover, QTreeWidget::item:hover, #TabList::item:hover {
    color: %(TEXT)s;
    background-color: %(ITEM_HOVER)s;
    border-color: transparent;
}
QListWidget::item:selected, QTreeWidget::item:selected, #TabList::item:selected {
    color: %(TEXT)s;
    background-color: %(ACCENT_WASH)s;
    border: 1px solid transparent;
    border-left: 2px solid %(ACCENT)s;
}
QListView#CafeList, QListView#TabList { background-color: transparent; }
#CafeList::item:selected, #TabList::item:selected { background-color: %(ACCENT_WASH)s; color: %(TEXT)s; }
/* Where the keyboard is: the open row's left rule thickens while the shelf has
   focus, so tabbing into the note list is visible without a second outline. */
#CafeList:focus::item:selected { border-left: 3px solid %(ACCENT)s; }
#TabList:focus {
    border: 1px solid %(ACCENT)s;
    border-radius: %(RADIUS_XS)s;
}
#TabList:focus::item:selected { border-left: 3px solid %(ACCENT)s; }

/* Inline omnibar feature finder: a card popped under the command bar. */
#FeaturePopupList {
    background-color: %(MENU_BG)s;
    border: 1px solid %(RULE_STRONG)s;
    border-radius: %(RADIUS)s;
    padding: 6px;
    outline: none;
}
#FeaturePopupList::item { background-color: transparent; border-radius: 6px; color: %(TEXT)s; padding: 7px 9px; }
#FeaturePopupList::item:hover { background-color: %(ITEM_HOVER)s; }
#FeaturePopupList::item:selected { background-color: %(ACCENT_WASH)s; border: 1px solid transparent; border-left: 2px solid %(ACCENT)s; }

/* ---------- tables ---------- */
QTableView, QTreeView {
    background-color: %(SURFACE)s;
    color: %(TEXT)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
    gridline-color: %(RULE)s;
    alternate-background-color: %(MAIN_BG_ALT)s;
}
QHeaderView::section {
    background-color: %(MAIN_BG_ALT)s;
    color: %(TEXT_MUTED)s;
    border: none;
    border-bottom: 1px solid %(RULE)s;
    padding: 6px;
    font-size: 10px;
    font-weight: 700;
}

/* ---------- the reading desk: browser chrome ---------- */
#TopBar {
    min-height: 42px;
    margin: 4px 4px 2px 4px;
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
    padding: 3px;
}
#TopBarCluster, #AddressCluster {
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
}
#AddressCluster[focused="true"] { background-color: %(INPUT_BG)s; border-color: %(ACCENT)s; }
#AddressCluster #UrlBar,
#AddressCluster #UrlBar:hover,
#AddressCluster #UrlBar:focus { background: transparent; border: none; padding: 6px 8px; font-size: 12px; font-weight: 500; }
#UrlBar {
    min-height: 28px;
    background-color: %(MAIN_BG_ALT)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px 10px;
    font-weight: 500;
}
#UrlBar:focus { background-color: %(INPUT_BG)s; border-color: %(ACCENT)s; }
#TopBar QToolButton {
    min-width: 26px; min-height: 26px;
    background-color: transparent; color: %(TEXT_MUTED)s;
    border: 1px solid transparent; border-radius: %(RADIUS_XS)s;
    padding: 4px 6px; font-size: 12px; font-weight: 700;
}
#TopBar QToolButton:hover { background-color: %(ITEM_HOVER)s; color: %(TEXT)s; border-color: %(RULE)s; }
#WebContainer { background-color: %(MAIN_BG)s; border: none; border-radius: 0; }
#NewTabBtn {
    min-height: 32px;
    background-color: %(ACCENT_WASH)s;
    color: %(ACCENT_HOVER)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
    padding: 7px 12px;
    font-weight: 700;
}
#NewTabBtn:hover { background-color: %(ACCENT_SOFT)s; border-color: %(ACCENT)s; }
#OptionsBtn { border-color: transparent; }
#OptionsBtn:hover { border-color: %(RULE_STRONG)s; }
#SidebarFooter { background-color: transparent; border-top: 1px solid %(RULE)s; }
#DormantTabView { background-color: %(SURFACE_SUNK)s; border: 1px dashed %(RULE_STRONG)s; border-radius: %(RADIUS)s; }
#WebPanelDock { background-color: %(SURFACE)s; border-left: 1px solid %(RULE)s; }
#SplitDock { background-color: %(SURFACE)s; border-right: 1px solid %(RULE)s; }
#WebPanelHeader { background-color: %(MAIN_BG_ALT)s; border-bottom: 1px solid %(RULE)s; }
#WebPanelView { background-color: %(MAIN_BG)s; }
#SavePasswordBar { background-color: %(ACCENT_WASH)s; border-top: 1px solid %(ACCENT)s; }
#AISideDock { background-color: %(SURFACE)s; border-left: 1px solid %(RULE)s; }
#DockRail { background-color: %(NAV_BG)s; border-left: 1px solid %(RULE)s; }
#LinkPreview {
    background-color: %(SURFACE)s; color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s; border-radius: 6px;
    padding: 3px 10px; font-size: 11px;
}
#FindBar { background-color: %(SURFACE)s; border: 1px solid %(RULE_STRONG)s; border-radius: %(RADIUS)s; }
#FindBar QLineEdit { background-color: %(INPUT_BG)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS_XS)s; }
#FindBar QLineEdit:focus { border-color: %(ACCENT)s; }
#ToastLabel {
    background-color: %(MENU_BG)s; color: %(TEXT)s;
    border: 1px solid %(RULE_STRONG)s; border-radius: %(RADIUS_SM)s;
    padding: 7px 14px; font-size: 12px; font-weight: 600;
}
#LoadProgress { background: transparent; border: none; max-height: 2px; margin: 0; }
#LoadProgress::chunk { background-color: %(ACCENT)s; }

/* ---------- the reading nook: AI workspace ---------- */
#AIThread, #AIEvidence {
    background-color: %(EDITOR_BG)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
    font-size: 13px;
    padding: 0;
}
#AIComposer {
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE_STRONG)s;
    border-radius: %(RADIUS)s;
}
#AISide { background-color: %(SURFACE)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS)s; }
#AIContextBar { background-color: transparent; border: none; }
#AIQuestion { min-height: 32px; font-size: 14px; padding: 8px 13px; }
#AIContextOptions, #AIActions { background-color: transparent; border: none; }
#AIContextScope { color: %(TEXT_MUTED)s; font-size: 10px; }
#AIContextSummary, #AIHint { color: %(TEXT_MUTED)s; font-size: 10px; }
#AIPrivacy { color: %(TEXT_MUTED)s; font-size: 10px; }
#AIPrivacy[remote="true"] { color: %(DANGER)s; }
#AIStatus { color: %(TEXT_MUTED)s; font-size: 10px; font-weight: 700; }
#AIStatus[state="busy"] { color: %(ACCENT_HOVER)s; }
#AIStatus[state="error"] { color: %(DANGER)s; }
#AIEmptyState, #AIEvidenceEmpty {
    background-color: %(SURFACE_SUNK)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
}
#AIEmptyTitle {
    color: %(TEXT)s;
    font-family: %(FONT_DISPLAY)s;
    font-size: 19px;
    font-weight: 600;
}
#AIEmptyHint { color: %(TEXT_MUTED)s; font-size: 11px; }
#AIStarter {
    background-color: transparent;
    color: %(ACCENT_HOVER)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_XS)s;
    padding: 7px 10px;
    font-size: 11px;
    font-weight: 600;
}
#AIStarter:hover { background-color: %(ACCENT_WASH)s; border-color: %(ACCENT)s; color: %(ACCENT_HOVER)s; }
#AIStarter:focus { border-color: %(ACCENT)s; }

/* ---------- notes / planner / review ---------- */
#NoteCanvas {
    background-color: %(EDITOR_BG)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
    padding: 18px 22px;
    font-size: 14px;
}
#NoteCanvas:focus { border-color: %(ACCENT)s; }
/* The writing size is a control, so it lives in the one place Qt actually
   paints a plain-text edit from: the stylesheet font set here (a widget
   setFont is re-polished away, and a document font alone left the widget and
   the layout disagreeing). personal_window._apply_note_font_size sets the
   textSize property and re-polishes — the old point-size call was a no-op. */
QPlainTextEdit#NoteEditor, #NoteEditor {
    background-color: %(EDITOR_BG)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
    padding: 18px 22px;
    font-size: 15px;
    selection-background-color: %(ACCENT_WASH)s;
    selection-color: %(TEXT)s;
}
QPlainTextEdit#NoteEditor[textSize="13"], #NoteEditor[textSize="13"] { font-size: 13px; }
QPlainTextEdit#NoteEditor[textSize="14"], #NoteEditor[textSize="14"] { font-size: 14px; }
QPlainTextEdit#NoteEditor[textSize="16"], #NoteEditor[textSize="16"] { font-size: 16px; }
QPlainTextEdit#NoteEditor[textSize="18"], #NoteEditor[textSize="18"] { font-size: 18px; }
QPlainTextEdit#NoteEditor[textSize="20"], #NoteEditor[textSize="20"] { font-size: 20px; }
QPlainTextEdit#NoteEditor:focus { border-color: %(ACCENT)s; background-color: %(EDITOR_BG)s; }
#NoteTitleLabel { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 20px; font-weight: 600; }
/* Transient writing-column notices (a move, a wiki-link open). Clay, not the
   note's title: these used to overwrite the title label itself. */
#NoteStatus { color: %(CLAY)s; font-size: 11px; }
/* Save gains the accent fill only while a note is actually unsaved, so the one
   accent in the writing column always means "there is work to keep". */
QPushButton#NoteSave {
    background-color: transparent;
    color: %(TEXT_MUTED)s;
    border: 1px solid %(RULE)s;
    padding: 5px 12px;
}
QPushButton#NoteSave:hover { color: %(TEXT)s; background-color: %(ITEM_HOVER)s; border-color: %(RULE_STRONG)s; }
QPushButton#NoteSave[dirty="true"] {
    background-color: %(ACCENT)s; color: %(TEXT_ON_ACCENT)s;
    border-color: %(ACCENT)s; font-weight: 600;
}
QPushButton#NoteSave[dirty="true"]:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }
QPushButton#NoteSave:disabled { color: %(TEXT_DIM)s; border-color: %(RULE)s; background-color: transparent; }
#NoteSaveState { color: %(TEXT_MUTED)s; font-size: 11px; }
#NoteSaveState[state="dirty"] { color: %(CLAY)s; }
#NoteSaveState[state="error"] { color: %(DANGER)s; }
#NoteEmptyTitle { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 18px; font-weight: 600; }
#NoteEmptyHint { color: %(TEXT_MUTED)s; font-size: 12px; }
#NoteFindBar { background: transparent; }
#NoteFind {
    min-height: 22px;
    background-color: transparent;
    border: none;
    border-bottom: 1px solid %(RULE)s;
    border-radius: 0;
    padding: 4px 2px;
    font-size: 11px;
    color: %(TEXT_MUTED)s;
}
#NoteFind:focus { border-bottom: 1px solid %(ACCENT)s; color: %(TEXT)s; }
#FindStep {
    min-width: 22px;
    max-width: 24px;
    min-height: 22px;
    padding: 0;
    background: transparent;
    border: 1px solid transparent;
    color: %(TEXT_MUTED)s;
    font-size: 12px;
}
#FindStep:hover { border-color: %(RULE)s; color: %(TEXT)s; }
#NoteMeta { color: %(TEXT_MUTED)s; font-size: 10px; }
#NoteListPane { background-color: transparent; }
#PlanToolbar {
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
    padding: 8px;
}
#PlanToolbar QLineEdit { border-color: transparent; background-color: %(MAIN_BG_ALT)s; }
#PlanToolbar QLineEdit:focus { border-color: %(ACCENT)s; background-color: %(INPUT_BG)s; }
#PlanColumn { background-color: transparent; border: none; }
#PlanDayHead { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 14px; font-weight: 600; }
#PlanWeek { color: %(TEXT_MUTED)s; font-size: 11px; font-weight: 600; }
#PlanDayDate { color: %(TEXT_MUTED)s; font-size: 10px; }
#PlanColumnBody {
    background-color: %(SURFACE_SUNK)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
}
#ReviewStage {
    background-color: %(SURFACE)s;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS_LG)s;
}
#ReviewFront { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 24px; font-weight: 600; }
#ReviewMeta { color: %(TEXT_MUTED)s; font-size: 11px; }
#ReviewActions { background-color: transparent; }
#CalendarMonth { background-color: %(SURFACE)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS)s; }
#CalendarSide { background-color: transparent; }
#BoardToolbar { background-color: %(SURFACE)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS)s; padding: 6px; }
/* The board page keeps the quiet table chrome around the paper: one toolbar
   card, a hairline between verbs and ink settings, and no boxes of its own. */
#BoardToolRule { background-color: %(RULE)s; border: none; }
#BoardToolLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
#BoardSettings, #BoardToolField, #BoardListPane, #BoardCanvasPane, #BoardHead, #BoardStage { background-color: transparent; }
#BoardTitle { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 15px; font-weight: 600; }
#BoardEmptyTitle { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 18px; font-weight: 600; }
#BoardEmptyHint { color: %(TEXT_MUTED)s; font-size: 12px; }
#BoardHint { color: %(TEXT_MUTED)s; font-size: 11px; }
#SettingsNav { background-color: transparent; }
#SettingsSection { background-color: transparent; border: none; }
#LibraryToolbar { background-color: transparent; }
#HistoryToolbar { background-color: transparent; }

/* ---------- menus, checkboxes, progress ---------- */
QMenu {
    background-color: %(MENU_BG)s;
    color: %(TEXT)s;
    border: 1px solid %(RULE_STRONG)s;
    border-radius: %(RADIUS_SM)s;
    padding: 6px;
}
QMenu::item { padding: 7px 24px 7px 12px; border-radius: 6px; margin: 1px 0; }
QMenu::item:selected { background-color: %(ACCENT_WASH)s; color: %(TEXT)s; }
QMenu::item:disabled { color: %(TEXT_DIM)s; }
QMenu::separator { height: 1px; background: %(RULE)s; margin: 5px 8px; }

QCheckBox, QRadioButton { color: %(TEXT)s; spacing: 8px; font-size: 12px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid %(RULE_STRONG)s; background: %(INPUT_BG)s;
}
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %(ACCENT)s; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: %(ACCENT)s;
    border-color: %(ACCENT)s;
}
QRadioButton::indicator:checked { border: 4px solid %(ACCENT)s; background: %(INPUT_BG)s; }
QCheckBox:checked { color: %(TEXT)s; font-weight: 600; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border-color: %(RULE)s; background: %(MAIN_BG_ALT)s; }

QProgressBar {
    border: 1px solid %(RULE)s; border-radius: %(RADIUS_PILL)s;
    background: %(SURFACE_SUNK)s; text-align: center; max-height: 8px;
    color: transparent;
}
QProgressBar::chunk { background-color: %(ACCENT)s; border-radius: %(RADIUS_PILL)s; }
QSlider::groove:horizontal { height: 4px; background: %(RULE)s; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; margin: -6px 0; border-radius: 7px;
    background: %(ACCENT)s; border: 1px solid %(ACCENT)s;
}
QSlider::sub-page:horizontal { background: %(ACCENT)s; border-radius: 2px; }

QGroupBox {
    background-color: transparent;
    border: 1px solid %(RULE)s;
    border-radius: %(RADIUS)s;
    margin-top: 14px;
    padding: 14px 12px 10px 12px;
    color: %(TEXT)s;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 6px; color: %(CLAY)s; font-size: 10px; font-weight: 700;
}

QCalendarWidget QWidget#qt_calendar_navigationbar { background-color: %(MAIN_BG_ALT)s; }
QCalendarWidget QAbstractItemView:enabled {
    background-color: %(SURFACE)s; color: %(TEXT)s;
    selection-background-color: %(ACCENT)s; selection-color: %(TEXT_ON_ACCENT)s;
}
""" % p + _VERB_QSS % p


def dialog_qss(mode: str = "minimal", accent: str | None = None):
    """Stylesheet shared by all modal dialogs — the same paper as the shell.

    Dialogs are where a design system usually falls apart: one padding here, a
    bare button there.  They get the same surfaces, the same two text sizes and
    the same single filled primary as the workspaces behind them.
    """
    p = _palette(mode, accent)
    return """
    QDialog { background-color: %(MAIN_BG)s; color: %(TEXT)s; font-size: 13px; }
    QDialog QWidget { background-color: transparent; font-family: %(FONT_FAMILY)s; }
    QLabel { color: %(TEXT)s; font-size: 13px; background: transparent; border: none; }
    QLabel#MutedLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
    QLabel#DialogTitle {
        color: %(TEXT)s;
        font-family: %(FONT_DISPLAY)s;
        font-size: 20px;
        font-weight: 600;
    }
    QLabel#DialogEyebrow { color: %(CLAY)s; font-size: 9px; font-weight: 800; text-transform: uppercase; }
    QLabel#DialogBody { color: %(TEXT_MUTED)s; font-size: 12px; }
    QFrame#DialogHeader { border: none; border-bottom: 1px solid %(RULE)s; }
    QFrame#DialogFooter { border: none; border-top: 1px solid %(RULE)s; }
    QPushButton {
        background-color: %(BUTTON_BG)s; color: %(BUTTON_TEXT)s;
        border: 1px solid %(RULE)s; border-radius: %(RADIUS_SM)s;
        padding: 7px 14px; font-size: 12px; font-weight: 600; min-height: 24px;
    }
    QPushButton:hover { background-color: %(BUTTON_HOVER)s; border-color: %(RULE_STRONG)s; }
    QPushButton:pressed { background-color: %(ITEM_SELECTED)s; }
    QPushButton:disabled { color: %(TEXT_DIM)s; background-color: transparent; border-color: %(RULE)s; }
    QPushButton:default {
        background-color: %(ACCENT)s; color: %(TEXT_ON_ACCENT)s;
        border-color: %(ACCENT)s; font-weight: 700;
    }
    QPushButton:default:hover { background-color: %(ACCENT_FILL_HOVER)s; border-color: %(ACCENT_FILL_HOVER)s; }
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
        background-color: %(INPUT_BG)s; color: %(TEXT)s;
        border: 1px solid %(RULE)s; border-radius: %(RADIUS_SM)s;
        padding: 6px 10px; font-size: 13px; min-height: 24px;
        selection-background-color: %(ACCENT_WASH)s; selection-color: %(TEXT)s;
    }
    QLineEdit:hover, QTextEdit:hover, QComboBox:hover { border-color: %(RULE_STRONG)s; }
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: %(ACCENT)s; }
    QListWidget, QTreeWidget {
        background-color: %(SURFACE)s; color: %(TEXT)s;
        border: 1px solid %(RULE)s; border-radius: %(RADIUS)s; padding: 4px; font-size: 13px;
    }
    QListWidget::item, QTreeWidget::item { padding: 7px 8px; border-radius: 6px; }
    QListWidget::item:hover, QTreeWidget::item:hover { background-color: %(ITEM_HOVER)s; }
    QListWidget::item:selected, QTreeWidget::item:selected {
        background-color: %(ACCENT_WASH)s; color: %(TEXT)s; border-left: 2px solid %(ACCENT)s;
    }
    QCheckBox, QRadioButton { color: %(TEXT)s; spacing: 8px; }
    QCheckBox::indicator, QRadioButton::indicator {
        width: 15px; height: 15px; border-radius: 4px;
        border: 1px solid %(RULE_STRONG)s; background: %(INPUT_BG)s;
    }
    QRadioButton::indicator { border-radius: 8px; }
    QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %(ACCENT)s; }
    QCheckBox::indicator:checked { background: %(ACCENT)s; border-color: %(ACCENT)s; }
    QRadioButton::indicator:checked { border: 4px solid %(ACCENT)s; background: %(INPUT_BG)s; }
    QComboBox QAbstractItemView {
        background-color: %(MENU_BG)s; color: %(TEXT)s;
        border: 1px solid %(RULE_STRONG)s; border-radius: %(RADIUS_XS)s;
        selection-background-color: %(ACCENT_WASH)s; selection-color: %(TEXT)s;
    }
    QGroupBox {
        background-color: transparent; border: 1px solid %(RULE)s;
        border-radius: %(RADIUS)s; margin-top: 12px; padding: 12px 10px 10px 10px;
    }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; color: %(CLAY)s; }
    QScrollArea { border: none; background: transparent; }
    QToolTip {
        background-color: %(MENU_BG)s; color: %(TEXT)s;
        border: 1px solid %(RULE_STRONG)s; border-radius: %(RADIUS_XS)s; padding: 6px 10px;
    }

    /* shared components */
    #PageHeader { background: transparent; }
    #PageTitle { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; font-size: 20px; font-weight: 600; }
    #PageSubtitle, #MutedLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
    #SectionTitle { color: %(TEXT)s; font-weight: 700; }
    #StatTile { background-color: %(SURFACE)s; border: 1px solid %(RULE)s; }
    #StatValue { color: %(TEXT)s; font-family: %(FONT_DISPLAY)s; }
    #StatLabel { color: %(TEXT_MUTED)s; font-size: 11px; }
    #SectionHeaderRow { background: transparent; }
    #EmptyState { background-color: %(SURFACE_SUNK)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS)s; }
    #EmptyGlyph { color: %(TEXT_DIM)s; font-size: 18px; }
    #ActionTile { background-color: transparent; border: 1px solid %(RULE)s; border-radius: %(RADIUS)s; padding: 8px; }
    #ActionTile:hover { border-color: %(ACCENT)s; background-color: %(ITEM_HOVER)s; }
    #ActionGlyph { color: %(ACCENT_HOVER)s; font-size: 20px; }
    #ActionLabel { color: %(TEXT)s; font-weight: 600; }
    #Chip { background-color: transparent; color: %(TEXT_MUTED)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS_PILL)s; padding: 5px 13px; font-size: 11px; font-weight: 600; }
    #Chip:hover { border-color: %(RULE_STRONG)s; color: %(TEXT)s; }
    #Chip:checked { background-color: %(ACCENT_WASH)s; color: %(ACCENT_HOVER)s; border-color: %(ACCENT)s; }
    #Badge { background-color: transparent; color: %(TEXT_MUTED)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS_PILL)s; padding: 2px 10px; font-size: 10px; font-weight: 700; }
    #BadgeAccent { background-color: %(MAIN_BG_ALT)s; color: %(TEXT_MUTED)s; border: 1px solid %(RULE)s; border-radius: %(RADIUS_PILL)s; padding: 2px 10px; font-size: 10px; font-weight: 700; }
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
    QToolButton:hover { color: %(TEXT)s; background: %(ITEM_HOVER)s; border-color: %(RULE)s; }
    QToolButton[collapsed="true"] {
        background: %(ACCENT_WASH)s; color: %(ACCENT_HOVER)s;
        border: 1px solid %(ACCENT)s; border-radius: 8px;
    }
    QToolButton[collapsed="true"]:hover {
        background: %(ACCENT_WASH)s; color: %(ACCENT_HOVER)s; border-color: %(ACCENT)s;
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
