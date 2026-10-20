"""Regression tests for this round's UX features:

* app-wide text selection (selectable labels + button copy menu)
* the custom theme-colored search icon
* the shell feature palette registry ("b" surfaces browser/site/personal hits)
* the bundled-sites option in Personal -> Sites (visible toggle, never deletes)
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The shim must be active before the binding is imported: doing it the other way
# round loads whichever Qt runtime PyQt5 points at directly, and mixing it with
# the façade's runtime crashes the interpreter (see test_browser_topbar).
import litebrowser  # noqa: F401 - litebrowser/__init__ activates the Qt shim

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from litebrowser.core import prefs

# QtWebEngine needs a non-empty program name in argv, otherwise Chromium's
# CommandLine fails to initialize and AppShell construction hangs.
_app = QApplication.instance() or QApplication(["mei-tests"])


class _DummyParent:
    """Minimal shell stand-in for palette entry building (no QtWebEngine)."""

    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.profile_dir = ""


class TestTextSelection(unittest.TestCase):
    def test_labels_become_selectable(self):
        from litebrowser.ui.textselect import enable_text_selection

        host = QWidget()
        layout = QVBoxLayout(host)
        layout.addWidget(QLabel("Alpha"))
        layout.addWidget(QLabel("Beta"))
        host.show()
        enable_text_selection(host)
        for label in host.findChildren(QLabel):
            with self.subTest(text=label.text()):
                self.assertTrue(label.textInteractionFlags() & Qt.TextSelectableByMouse)

    def test_buttons_get_copy_filter(self):
        from litebrowser.ui.textselect import _ButtonCopyFilter, enable_text_selection

        host = QWidget()
        layout = QVBoxLayout(host)
        btn = QPushButton("Copy me")
        layout.addWidget(btn)
        enable_text_selection(host)
        self.assertIsNotNone(_ButtonCopyFilter._shared)


class TestSearchIcon(unittest.TestCase):
    def test_search_icon_is_drawn(self):
        from litebrowser.ui.icons import search_icon

        icon = search_icon("#ff8800")
        self.assertFalse(icon.isNull())

    def test_icon_colors_differ_by_input(self):
        from litebrowser.ui.icons import search_icon

        # Different accent colors must produce distinct icons (theme-following).
        self.assertNotEqual(search_icon("#ff8800").cacheKey(), search_icon("#2288ff").cacheKey())


class TestShellPaletteEntries(unittest.TestCase):
    def test_registry_covers_workspaces_sites_commands(self):
        from litebrowser.ui.dialogs.shell_palette import _build_entries

        entries = _build_entries(_DummyParent(app_dir=os.getcwd()))
        kinds = {}
        for entry in entries:
            kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
        self.assertGreaterEqual(kinds.get("workspace", 0), 7)
        self.assertGreaterEqual(kinds.get("site", 0), 4)
        self.assertGreaterEqual(kinds.get("command", 0), 15)
        self.assertGreaterEqual(kinds.get("personal_page", 0), 8)

    def test_typing_b_surfaces_browser_and_sites(self):
        from litebrowser.ui.dialogs.shell_palette import _build_entries

        entries = _build_entries(_DummyParent(app_dir=os.getcwd()))
        hits = [
            e
            for e in entries
            if "b" in ("%s %s %s" % (e["title"], e.get("category", ""), e.get("keywords", ""))).lower()
        ]
        titles = [e["title"].lower() for e in hits]
        self.assertTrue(any("browser" in t for t in titles))
        self.assertTrue(any(k in " ".join(titles) for k in ("bí mật", "bói toán", "boards")))
        # Every hit must be executable through the shell dispatch kinds.
        for entry in hits:
            self.assertIn(entry["kind"], ("workspace", "personal_page", "site", "hub", "command"))


class TestFeatureFilterEveryLetter(unittest.TestCase):
    """Typing any letter must surface features (fallback shows the registry)."""

    def test_every_letter_matches_something(self):
        from litebrowser.ui.dialogs.shell_palette import (
            _build_entries,
            filter_feature_entries,
        )

        entries = _build_entries(_DummyParent(app_dir=os.getcwd()))
        for letter in "abcdefghijklmnopqrstuvwxyz":
            with self.subTest(letter=letter):
                self.assertGreaterEqual(len(filter_feature_entries(entries, letter)), 1)

    def test_multi_letter_narrowing(self):
        from litebrowser.ui.dialogs.shell_palette import (
            _build_entries,
            filter_feature_entries,
        )

        entries = _build_entries(_DummyParent(app_dir=os.getcwd()))
        wide = len(filter_feature_entries(entries, "b"))
        narrow = len(filter_feature_entries(entries, "boi"))
        self.assertGreater(wide, narrow)
        self.assertGreaterEqual(narrow, 1)


class TestOmnibarPopupEventFilter(unittest.TestCase):
    """The app-level event filter receives QWindow objects too; it must not
    call QWidget-only APIs on them (regression: TypeError crash on startup).

    Runs in a subprocess: constructing AppShell brings up QtWebEngine, whose
    Chromium children wedge the offscreen event loop for any later test in the
    same pytest process, so the real window is exercised in isolation."""

    _PROBE = r'''
import os, sys, tempfile
from unittest import mock
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu --no-sandbox --disable-software-rasterizer"
)
import litebrowser  # noqa: F401
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QWindow
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QPushButton
from litebrowser.core import prefs
from litebrowser.ui.app_shell import AppShell
app = QApplication(["mei-tests"])
tmp = tempfile.mkdtemp(prefix="mei_filter_probe_")
base = os.path.join(tmp, "p")
prefs.ensure_profile_layout(base)
prefs.save_pref(base, "onboarding_done", True)
# This probe owns only event-filter interactions; first-run setup, network
# updates, tray integration and global hotkeys must not enter its event loop.
with mock.patch.object(AppShell, "_startup_update_check"), mock.patch.object(AppShell, "_init_tray"), mock.patch.object(AppShell, "_init_global_hotkey"):
    shell = AppShell(base, app_dir=tmp, window_slot="secondary")
shell.show()
app.processEvents()
# 1) QWindow objects through the filter must not raise.
win = QWindow()
for ev_type in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.WindowActivate):
    shell.eventFilter(win, QEvent(ev_type))
# 2) Typing still opens the popup and keeps omnibar focus.
shell.omnibar.setFocus()
QTest.keyClicks(shell.omnibar, "home")
app.processEvents()
assert shell._feature_popup.isVisible(), "popup did not open"
assert shell.omnibar.hasFocus(), "omnibar lost focus to popup"
# 3) Outside click hides it; clicking a row still executes.
shell._feature_popup.setCurrentRow(0)
outside = QPushButton("x", shell)
outside.show()
app.processEvents()
QTest.mouseClick(outside, Qt.LeftButton)
app.processEvents()
assert not shell._feature_popup.isVisible(), "outside click did not hide popup"
shell.close()
print("ALL_OK")
'''

    def _run_probe(self):
        import subprocess
        import sys as _sys

        proc = subprocess.run(
            [_sys.executable, "-c", self._PROBE],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getcwd(),
        )
        # QtWebEngine needs a real GL context. On a machine/CI without one the
        # probe process dies with an access violation (0xC0000005) before any of
        # our code runs — an environment failure, not a regression, so skip with
        # the reason instead of reporting a red test nobody can act on.
        gl_failures = (-1073741819, 3221225477, -1073741795, 3221225595)
        gl_signature = ("Failed to create GLES", "ContextResult::kFatalFailure", "gpu_channel")
        if proc.returncode != 0 and (
            proc.returncode in gl_failures or any(sig in proc.stderr for sig in gl_signature)
        ):
            self.skipTest("no GL context for QtWebEngine here: %s" % proc.stderr.strip()[-160:])
        self.assertEqual(proc.returncode, 0, msg="probe failed:\n%s\n%s" % (proc.stdout, proc.stderr))
        self.assertIn("ALL_OK", proc.stdout)

    def test_qwindow_events_do_not_crash_filter(self):
        self._run_probe()


class TestTabRowHeights(unittest.TestCase):
    """Workspace tab rows must render at full height — QSS padding on
    ::item + setItemWidget used to slice each row to ~12px (title cut in
    half). Uses the real row widget + the app stylesheet."""

    def test_rows_are_not_clipped(self):
        import types

        from PyQt5.QtCore import QSize
        from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

        from litebrowser.browser.tab_manager import TabListItemWidget
        from litebrowser.ui import theme

        tmp = tempfile.mkdtemp(prefix="mei_tabrows_test_")
        base = os.path.join(tmp, "p")
        prefs.ensure_profile_layout(base)
        host = QWidget()
        host.setStyleSheet(theme.main_qss(prefs.get_shell_theme(base), prefs.get_accent(base)))
        layout = QVBoxLayout(host)
        lst = QListWidget()
        lst.setObjectName("TabList")
        lst.setUniformItemSizes(True)
        layout.addWidget(lst)
        host.resize(240, 300)
        host.show()
        fake_manager = types.SimpleNamespace(base_dir=base)
        for title in ("A fairly long workspace tab title", "Home"):
            item = QListWidgetItem()
            widget = TabListItemWidget(fake_manager, item, title)
            item.setSizeHint(QSize(224, 32))
            lst.addItem(item)
            lst.setItemWidget(item, widget)
        _app.processEvents()
        for i in range(lst.count()):
            widget = lst.itemWidget(lst.item(i))
            rect = lst.visualItemRect(lst.item(i))
            with self.subTest(row=i):
                self.assertGreaterEqual(widget.height(), 24)
                self.assertLessEqual(widget.height(), rect.height() + 2)
                # The title label must be tall enough for its 11px font.
                self.assertGreaterEqual(widget.lbl_title.height(), 12)


class TestBundledSitesPreference(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="mei_sites_test_")
        self.base = os.path.join(self._tmp, "profile")
        prefs.ensure_profile_layout(self.base)
        from litebrowser.core import app_paths

        remote = [s for s in app_paths.chain_remote_sites(os.getcwd()) if s.get("url")]
        self.bundled_url = remote[0]["url"] if remote else "https://example-bundled.test/"

    def test_defaults_off_for_fresh_profiles(self):
        # Only auto-seeded links -> bundled sites hidden on first entry.
        prefs.add_personal_site(self.base, self.bundled_url, "BundledApp")
        self.assertFalse(prefs.get_show_bundled_sites(self.base))

    def test_defaults_on_for_curated_profiles(self):
        prefs.add_personal_site(self.base, self.bundled_url, "BundledApp")
        prefs.add_personal_site(self.base, "https://example.com/mine", "My Site")
        self.assertTrue(prefs.get_show_bundled_sites(self.base))

    def test_roundtrip_and_data_safety(self):
        prefs.set_show_bundled_sites(self.base, False)
        self.assertFalse(prefs.get_show_bundled_sites(self.base))
        prefs.set_show_bundled_sites(self.base, True)
        self.assertTrue(prefs.get_show_bundled_sites(self.base))
        # The preference change must never remove user data.
        prefs.add_personal_site(self.base, "https://example.com/mine", "My Site")
        prefs.set_show_bundled_sites(self.base, False)
        urls = {s.get("url") for s in prefs.get_personal_sites(self.base)}
        self.assertIn("https://example.com/mine", urls)


if __name__ == "__main__":
    unittest.main()