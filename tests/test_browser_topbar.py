"""Browser chrome: address-bar connection pill, zoom chip and toolbar collapse.

The toolbar lives in ``ui/main_window/window_topbar.py`` (TopBarMixin). Building a
real SearchWindow needs a live QWebEngine surface, so these tests drive the *real*
mixin methods on a minimal host that mirrors the attributes the chrome touches —
the same approach ``tests/test_sidebar_collapse.py`` uses for the tab desk.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Activate the Qt shim before touching the binding, then import Qt through the
# façade. Importing PyQt5 first would load the *other* Qt runtime when PyQt6 is
# installed (the shim only redirects later imports), and mixing two runtimes in
# one process crashes the interpreter instead of failing a test.
import litebrowser  # noqa: F401 - litebrowser/__init__ activates the shim
from litebrowser.qt import QtWidgets
from litebrowser.ui.main_window.window_topbar import (
    SITE_PILL_COLORS,
    SITE_PILL_INFORMATIVE_STATES,
    SITE_PILL_LABELS,
    SITE_PILL_TIPS,
    TopBarMixin,
    site_state_key,
)

QApplication = QtWidgets.QApplication
QWidget = QtWidgets.QWidget
QHBoxLayout = QtWidgets.QHBoxLayout

_app = QApplication.instance() or QApplication([])

import litebrowser.ui.main_window.window as _wm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PALETTE_STUB = {
    "SUCCESS": "#57803e",
    "DANGER": "#a33333",
    "ACCENT_SOFT": "#eee8dd",
    "MAIN_BG_ALT": "#f7f2e8",
    "TEXT_MUTED": "#7a6952",
}


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class _StubBrowser:
    def __init__(self, factor):
        self._factor = factor

    def zoomFactor(self):
        return self._factor


def _stub(*_args, **_kwargs):
    """Stand-in for a SearchWindow method the toolbar only wires to signals."""
    return None


class _TopBarHost(QWidget, TopBarMixin):
    """Host for the real toolbar code.

    Every collaborator is declared here: an undeclared one fails the test with
    AttributeError, so this list is also the answer to "what may the chrome
    depend on?".
    """

    _add_to_reading_list = _stub
    _copy_page_address = _stub
    _go_home = _stub
    _monitor_current_page = _stub
    _on_clipboard_changed = _stub
    _on_search_engine_changed = _stub
    _save_selection_to_vault = _stub
    _translate_page = _stub
    ask_ai_about_current_page = _stub
    find_text = _stub
    navigate = _stub
    open_current_in_external_browser = _stub
    open_current_in_incognito = _stub
    open_url_in_external_browser = _stub
    save_bookmark = _stub
    show_dev_tools = _stub
    show_web_panel_menu = _stub
    toggle_disable_webgl = _stub
    toggle_reader_mode = _stub
    toggle_text_highlight = _stub
    zoom_in = _stub
    zoom_out = _stub
    zoom_reset = _stub

    def __init__(self, ai_actions_available=False):
        super().__init__()
        self.embedded = False
        self.base_dir = ROOT
        self.ai_actions_available = ai_actions_available
        self.zoom_factor = None
        self.responsive_calls = 0
        self._topbar_collapsed = False
        self.content_layout = QHBoxLayout(self)
        self._build_topbar()
        # Mirrors SearchWindow.__init__: a window without AI actions does not show
        # the AI button.
        if not ai_actions_available:
            self.btn_ai.hide()
        self._apply_responsive_layout()

    # -- the parts of SearchWindow the chrome reads -----------------------
    def current_browser(self):
        return _StubBrowser(self.zoom_factor) if self.zoom_factor else None

    def _palette_lookup(self, key):
        return _PALETTE_STUB[key]

    def _apply_responsive_layout(self):
        self.responsive_calls += 1


class TestSitePill(unittest.TestCase):
    def test_every_connection_state_has_a_label_colour_and_tip(self):
        states = {
            site_state_key(url)
            for url in (
                "https://example.com",
                "http://example.com",
                "",
                "about:blank",
                "file:///C:/x.html",
                "linklumina.local",
            )
        }
        self.assertEqual(states, set(SITE_PILL_LABELS))
        self.assertEqual(set(SITE_PILL_LABELS), set(SITE_PILL_COLORS))
        self.assertEqual(set(SITE_PILL_LABELS), set(SITE_PILL_TIPS))

    def test_scheme_classification(self):
        cases = (
            ("https://a.test/x", "secure"),
            ("HTTP://a.test", "insecure"),
            ("about:cuc-quan-ly", "local"),
            ("file:///C:/index.html", "file"),
            ("mei browser", "search"),
            (None, "search"),
        )
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(site_state_key(url), expected)

    def test_pill_keeps_one_width_across_states_and_clips_nothing(self):
        host = _TopBarHost()
        try:
            host.show()
            _app.processEvents()
            pill = host.lbl_site_state
            widths = set()
            for url in ("https://a.test", "http://a.test", "about:blank", "file:///C:/x.html", ""):
                host._apply_site_state_pill(url)
                widths.add((pill.minimumWidth(), pill.maximumWidth()))
            # One width, so navigating never reflows the address bar.
            self.assertEqual(len(widths), 1)
            # ...and wide enough that no label is clipped (7px padding each side).
            # Measured from the reserved width, not the laid-out one: a hidden
            # state (see TestConnectionPillOnlySpeaks...) has no width yet.
            metrics = pill.fontMetrics()
            room = pill.minimumWidth() - 14
            for label in SITE_PILL_LABELS.values():
                self.assertLessEqual(metrics.horizontalAdvance(label), room, label)
        finally:
            host.close()


class TestConnectionPillOnlySpeaksWhenItHasSomethingToSay(unittest.TestCase):
    """The chip used to sit in the toolbar showing "Local" for about:newtab and
    "Search" on every empty tab — chrome that answers a question nobody asked.
    It now appears only where it carries the security state."""

    def setUp(self):
        self.host = _TopBarHost()
        self.host.show()
        _app.processEvents()

    def tearDown(self):
        self.host.close()

    def test_hidden_for_internal_and_empty_addresses(self):
        for url in ("about:newtab", "about:cuc-quan-ly", "", "  ", "google search"):
            with self.subTest(url=url):
                self.host._apply_site_state_pill(url)
                self.assertFalse(self.host.lbl_site_state.isVisible(), url)

    def test_shown_with_the_security_state_of_web_pages(self):
        for url, label in (("https://example.com", SITE_PILL_LABELS["secure"]), ("http://example.com", SITE_PILL_LABELS["insecure"])):
            with self.subTest(url=url):
                self.host._apply_site_state_pill(url)
                self.assertTrue(self.host.lbl_site_state.isVisible(), url)
                self.assertEqual(self.host.lbl_site_state.text(), label)

    def test_a_narrow_window_still_hides_it_and_re_shows_it(self):
        self.host._apply_site_state_pill("https://example.com")
        self.host._site_pill_fits = False
        self.host._sync_site_pill_visibility()
        self.assertFalse(self.host.lbl_site_state.isVisible())
        self.host._site_pill_fits = True
        self.host._sync_site_pill_visibility()
        self.assertTrue(self.host.lbl_site_state.isVisible())

    def test_a_collapsed_toolbar_hides_it_even_on_https(self):
        self.host._apply_site_state_pill("https://example.com")
        self.host._toggle_topbar()
        self.assertFalse(self.host.lbl_site_state.isVisible())
        self.host._toggle_topbar()
        self.assertTrue(self.host.lbl_site_state.isVisible())

    def test_the_labels_table_still_covers_every_state(self):
        # The pill's width reservation is measured from all five labels even though
        # only two of them are ever shown.
        self.assertTrue(set(SITE_PILL_INFORMATIVE_STATES) <= set(SITE_PILL_LABELS))
        for state in SITE_PILL_INFORMATIVE_STATES:
            with self.subTest(state=state):
                self.assertIn(state, SITE_PILL_COLORS)
                self.assertIn(state, SITE_PILL_TIPS)


class TestToolbarCollapse(unittest.TestCase):
    def test_round_trip_restores_only_what_the_chrome_showed(self):
        host = _TopBarHost(ai_actions_available=False)
        try:
            host.show()
            _app.processEvents()
            self.assertTrue(host.btn_ai.isHidden(), "unavailable AI button starts hidden")
            self.assertTrue(host.lbl_zoom.isHidden(), "zoom chip starts hidden at 100%")

            host._toggle_topbar()
            self.assertTrue(host._topbar_collapsed)
            self.assertTrue(host.btn_back.isHidden())
            # The address field lives inside #AddressCluster (one rounded frame),
            # so collapsing hides the frame it sits in: isVisible(), not isHidden().
            self.assertFalse(host.url_bar.isVisible())
            self.assertTrue(host.btn_toggle_topbar.isVisible())

            host._toggle_topbar()
            self.assertFalse(host._topbar_collapsed)
            self.assertTrue(host.btn_back.isVisible())
            self.assertTrue(host.url_bar.isVisible())
            # The two controls the chrome hides on purpose stay hidden: expanding
            # used to resurrect an AI button this window does not offer and a
            # "100%" chip that says nothing.
            self.assertTrue(host.btn_ai.isHidden())
            self.assertTrue(host.lbl_zoom.isHidden())
            # ...and the responsive pass runs again, so narrow-window hiding is
            # not undone by the expand either.
            self.assertGreaterEqual(host.responsive_calls, 2)
        finally:
            host.close()

    def test_ai_button_returns_when_the_window_has_ai_actions(self):
        host = _TopBarHost(ai_actions_available=True)
        try:
            host.show()
            _app.processEvents()
            host._toggle_topbar()
            host._toggle_topbar()
            self.assertTrue(host.btn_ai.isVisible())
        finally:
            host.close()


class TestZoomChip(unittest.TestCase):
    def test_chip_appears_only_away_from_the_default(self):
        host = _TopBarHost()
        try:
            host.show()
            _app.processEvents()
            _wm.SearchWindow.update_zoom_label(host)
            self.assertTrue(host.lbl_zoom.isHidden(), "no chip for a 100% page")

            host.zoom_factor = 1.5
            _wm.SearchWindow.update_zoom_label(host)
            self.assertEqual(host.lbl_zoom.text(), "150%")
            self.assertTrue(host.lbl_zoom.isVisible())

            host.zoom_factor = 1.0
            _wm.SearchWindow.update_zoom_label(host)
            self.assertEqual(host.lbl_zoom.text(), "100%")
            self.assertTrue(host.lbl_zoom.isHidden())
        finally:
            host.close()

    def test_a_zoomed_page_does_not_unhide_a_collapsed_toolbar(self):
        host = _TopBarHost()
        try:
            host.show()
            _app.processEvents()
            host.zoom_factor = 2.0
            host._toggle_topbar()
            self.assertFalse(host.url_bar.isVisible())
            _wm.SearchWindow.update_zoom_label(host)
            self.assertTrue(host.lbl_zoom.isHidden(), "collapsed chrome stays collapsed")
            host._toggle_topbar()
            self.assertTrue(host.lbl_zoom.isVisible())
        finally:
            host.close()


class TestChromeStaysExtracted(unittest.TestCase):
    """Structurally: the toolbar is one module, not ~110 lines inside __init__."""

    def test_window_delegates_to_the_mixin(self):
        source = _read(os.path.join("litebrowser", "ui", "main_window", "window.py"))
        self.assertIn("self._build_topbar()", source)
        self.assertIn("class SearchWindow(TopBarMixin,", source)
        for gone in ("self.lbl_site_state = QLabel", "def _build_page_menu", "def _apply_topbar_collapse"):
            with self.subTest(symbol=gone):
                self.assertNotIn(gone, source)

    def test_the_retired_address_hint_style_stays_retired(self):
        # The pill paints itself from the palette now, so the QSS selector that
        # styled two of its five states inconsistently is gone.
        self.assertNotIn("#AddressHint", _read(os.path.join("litebrowser", "ui", "theme.py")))

    def test_the_address_field_is_one_frame(self):
        # The pill and the address share #AddressCluster; the QSS rule that makes
        # the inner field borderless only pays off while that object exists.
        source = _read(os.path.join("litebrowser", "ui", "main_window", "window_topbar.py"))
        self.assertIn('setObjectName("AddressCluster")', source)
        self.assertIn("self.address_cluster", source)
        qss = _read(os.path.join("litebrowser", "ui", "theme.py"))
        self.assertIn("#AddressCluster #UrlBar", qss)
        self.assertIn('#AddressCluster[focused="true"]', qss)

    def test_vpn_is_a_quiet_utility_not_a_second_primary_button(self):
        host = _TopBarHost()
        try:
            self.assertEqual(host.btn_vpn_hub.objectName(), "ToolbarChip")
            self.assertEqual(host.btn_vpn_hub.accessibleName(), "VPN and proxy presets")
        finally:
            host.close()
        qss = _read(os.path.join("litebrowser", "ui", "theme.py"))
        self.assertIn("#ToolbarChip", qss)

    def test_qt_menu_carets_stay_switched_off(self):
        # Qt anchors ::menu-indicator to the bottom-right of a styled button,
        # which drew the "Control" caret below its own edge. The caret is part of
        # the button label now, so the subcontrol must not come back.
        qss = _read(os.path.join("litebrowser", "ui", "theme.py"))
        self.assertIn("QPushButton::menu-indicator", qss)
        self.assertIn("QToolButton::menu-indicator", qss)
        self.assertIn("image: none", qss)

    def test_the_new_module_uses_the_qt_facade(self):
        source = _read(os.path.join("litebrowser", "ui", "main_window", "window_topbar.py"))
        self.assertIn("from litebrowser.qt import", source)
        self.assertNotIn("from PyQt5", source)


if __name__ == "__main__":
    unittest.main()
