"""Tab-desk state and count regressions.

The browser chrome is exercised without a live QWebEngine surface: these tests
use the real TabListItemWidget and TabManager state methods on a minimal host,
the same pattern as tests/test_browser_topbar.py.
"""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activate the Qt shim before importing PyQt5
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication, QLabel, QListWidget, QListWidgetItem, QStackedWidget, QWidget

from litebrowser.browser.tab_manager import (
    TAB_META_ROLE,
    TAB_PINNED_ROLE,
    TAB_WIDGET_ROLE,
    TabListItemWidget,
    TabManager,
)
from litebrowser.core import prefs

_app = QApplication.instance() or QApplication([])


class _FakeBrowser:
    def __init__(self):
        self._values = {}

    def property(self, name):
        if name == "hibernate_timer":
            return None
        return self._values.get(name, False)

    def setProperty(self, name, value):
        self._values[name] = value


class _TabHost:
    def __init__(self, base_dir):
        self.stack = QStackedWidget()
        self.tab_list = QListWidget()
        self.browsers = []
        self.lbl_tab_count = QLabel()
        self.base_dir = base_dir
        self._incognito_profiles = []
        self.ext_path = base_dir
        self.profile = object()
        self.interceptor = object()
        # Rows in this unit test carry no workspace metadata; counting every
        # row is the behavior under test.
        self.current_workspace_id = None
        self.counts = None

    def set_tab_count(self, active, sleeping):
        self.counts = (active, sleeping)
        self.lbl_tab_count.setText(f"{active} live · {sleeping} sleeping")


class TestTabDeskStates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.host = _TabHost(self.base)
        self.manager = TabManager(self.host)
        self.widgets = []
        for title, hibernated in (("Reading desk", False), ("Sleeping notes", True)):
            item = QListWidgetItem()
            item.setSizeHint(QSize(224, 32))
            widget = TabListItemWidget(self.manager, item, title)
            self.host.tab_list.addItem(item)
            self.host.tab_list.setItemWidget(item, widget)
            item.setData(TAB_WIDGET_ROLE, widget)
            item.setData(TAB_PINNED_ROLE, False)
            item.setData(TAB_META_ROLE, {"title": title, "url": "https://example.test", "hibernated": hibernated})
            self.widgets.append((item, widget))
        self.host.browsers[:] = [_FakeBrowser(), None]

    def tearDown(self):
        self.host.tab_list.deleteLater()
        self.host.stack.deleteLater()
        self._tmp.cleanup()

    def test_count_does_not_double_the_sleeping_tab(self):
        self.manager.update_tab_count()
        self.assertEqual(self.host.counts, (1, 1))
        self.assertEqual(self.host.lbl_tab_count.text(), "1 live · 1 sleeping")

    def test_active_row_is_weighted_apart_from_resting_rows(self):
        self.manager.refresh_active_rows(0)
        self.assertTrue(self.widgets[0][1]._active)
        self.assertIn("font-weight: 700", self.widgets[0][1].lbl_title.styleSheet())
        self.assertFalse(self.widgets[1][1]._active)
        self.assertNotIn("font-weight: 700", self.widgets[1][1].lbl_title.styleSheet())

    def test_pin_uses_the_state_chip_without_prefixing_the_title(self):
        item, widget = self.widgets[0]
        self.manager.set_tab_pinned(0, True)
        self.assertEqual(widget.lbl_state.text(), "Pin")
        self.assertEqual(widget.text(), "Reading desk")
        self.assertTrue(widget._state_style)
        self.manager.set_tab_pinned(0, False)
        self.assertEqual(widget.lbl_state.text(), "")
        self.assertEqual(widget.text(), "Reading desk")

    def test_compact_count_is_readable_in_a_narrow_desk(self):
        from litebrowser.ui.main_window import window as window_module

        class _CountHost:
            def __init__(self):
                self.sidebarWidget = QWidget()
                self.lbl_tab_count = QLabel()
                self._tab_counts = (2, 1)

        host = _CountHost()
        try:
            host.sidebarWidget.setFixedWidth(280)
            window_module.SearchWindow._render_tab_count(host)
            self.assertEqual(host.lbl_tab_count.text(), "2 live · 1 sleeping")

            host.sidebarWidget.setFixedWidth(150)
            window_module.SearchWindow._render_tab_count(host)
            self.assertEqual(host.lbl_tab_count.text(), "2 · 1z")
            self.assertIn("sleeping", host.lbl_tab_count.toolTip())
        finally:
            host.sidebarWidget.deleteLater()
            host.lbl_tab_count.deleteLater()


if __name__ == "__main__":
    unittest.main()
