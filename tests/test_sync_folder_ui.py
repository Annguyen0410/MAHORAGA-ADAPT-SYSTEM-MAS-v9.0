"""The Settings card for folder sync: the feature has to be reachable, not just correct.

``test_sync_folder.py`` proves the merge itself. This file proves the *card*:
choosing a folder is remembered, Preview is read-only, Sync now applies and says
what it did, and a file that is not ours is reported as a message instead of a
traceback. It exists for the same reason ``test_deck_ui.py`` does — a service
nobody can reach from the UI is a service that does not exist.
"""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activates the Qt compatibility shim

from PyQt5.QtWidgets import QApplication, QWidget

from litebrowser.core import prefs
from litebrowser.services import life_service, sync_folder
from litebrowser.ui import personal_window as pw_module  # noqa: F401 - QtWebEngine first
from litebrowser.ui.shell import pages as pages_module

_app = QApplication.instance() or QApplication([])


class _StubShell(QWidget):
    """Only what SettingsPage reads directly; everything else is a no-op call."""

    def __init__(self, profile_dir, app_dir):
        super().__init__()
        self.profile_dir = profile_dir
        self.app_dir = app_dir
        self.update_status_text = ""
        self.refreshes = 0
        self.browser_page = QWidget()

    def refresh_shell(self, force_deep=False):
        self.refreshes += 1

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _SettingsCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.folder = os.path.join(self.root, "shared")
        os.makedirs(self.folder, exist_ok=True)
        self.base = prefs.ensure_profile_layout(os.path.join(self.root, "profile"))
        self.shell = _StubShell(self.base, self.root)
        self.page = pages_module.SettingsPage(self.shell)

    def tearDown(self):
        self.page.deleteLater()
        self.shell.deleteLater()
        self._tmp.cleanup()

    def test_preview_uses_background_relay_and_keeps_controls_disabled(self):
        from concurrent.futures import Future
        sync_folder.set_folder(self.base, self.folder)
        self.page._refresh_folder_sync()
        submitted = []
        with mock.patch.object(_StubShell, "run_in_background", create=True, side_effect=lambda work, done: submitted.append((work, done))):
            self.page.btn_preview_sync.click()
            self.page._refresh_folder_sync()
            self.page._preview_sync()
        self.assertEqual(len(submitted), 1)
        for button in (self.page.btn_preview_sync, self.page.btn_apply_sync, self.page.btn_choose_sync_folder, self.page.btn_clear_sync_folder):
            self.assertFalse(button.isEnabled())
        future = Future()
        future.set_result(submitted[0][0]())
        with mock.patch.object(pages_module.QMessageBox, "information") as told:
            submitted[0][1](future)
        self.assertIn("already in step", told.call_args[0][2])
        self.assertTrue(self.page.btn_preview_sync.isEnabled())
        self.assertFalse(self.page._folder_sync_running)

    def test_background_preview_failure_recovers_controls(self):
        from concurrent.futures import Future
        sync_folder.set_folder(self.base, self.folder)
        self.page._folder_sync_running = True
        future = Future()
        future.set_exception(OSError("offline drive"))
        with mock.patch.object(pages_module.QMessageBox, "warning") as told:
            self.page._finish_folder_preview(future)
        self.assertIn("offline drive", told.call_args[0][2])
        self.assertTrue(self.page.btn_choose_sync_folder.isEnabled())
        self.assertIn("No data was changed", self.page.lbl_sync_status.text())

    def test_the_card_starts_switched_off(self):
        self.assertEqual(self.page.lbl_sync_folder.text(), "No folder chosen")
        self.assertFalse(self.page.btn_preview_sync.isEnabled())
        self.assertFalse(self.page.btn_apply_sync.isEnabled())
        self.assertFalse(self.page.btn_clear_sync_folder.isEnabled())

    def test_choosing_a_folder_remembers_it_and_switches_the_card_on(self):
        with mock.patch.object(pages_module.QFileDialog, "getExistingDirectory", return_value=self.folder):
            self.page.btn_choose_sync_folder.click()
        self.assertEqual(sync_folder.get_folder(self.base), self.folder)
        self.assertEqual(self.page.lbl_sync_folder.text(), self.folder)
        self.assertTrue(self.page.btn_preview_sync.isEnabled())
        self.assertTrue(self.page.btn_apply_sync.isEnabled())
        self.assertIn("sync file will be written", self.page.lbl_sync_status.text())

    def test_turning_it_off_forgets_the_folder(self):
        sync_folder.set_folder(self.base, self.folder)
        self.page._refresh_folder_sync()
        self.page.btn_clear_sync_folder.click()
        self.assertEqual(sync_folder.get_folder(self.base), "")
        self.assertEqual(self.page.lbl_sync_folder.text(), "No folder chosen")
        self.assertFalse(self.page.btn_apply_sync.isEnabled())


class _TwoMachines(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.folder = os.path.join(self.root, "shared")
        os.makedirs(self.folder, exist_ok=True)
        self.a = prefs.ensure_profile_layout(os.path.join(self.root, "machine-a"))
        self.b = prefs.ensure_profile_layout(os.path.join(self.root, "machine-b"))
        for base in (self.a, self.b):
            sync_folder.set_folder(base, self.folder)
        life_service.add_task(self.a, "Buy ink", bucket="today")
        sync_folder.sync(self.a)
        self.shell = _StubShell(self.b, self.root)
        self.page = pages_module.SettingsPage(self.shell)

    def tearDown(self):
        self.page.deleteLater()
        self.shell.deleteLater()
        self._tmp.cleanup()

    def _titles(self, base):
        return sorted(task.get("title", "") for task in life_service.load_tasks(base))

    def test_preview_shows_the_coming_change_and_writes_nothing(self):
        payload_before = sync_folder.read_payload(self.b)
        with mock.patch.object(pages_module.QMessageBox, "information") as told:
            self.page.btn_preview_sync.click()
        self.assertEqual(self._titles(self.b), [], "preview must not apply anything")
        self.assertEqual(sync_folder.read_payload(self.b), payload_before)
        message = told.call_args[0][2]
        self.assertIn("Buy ink", message)
        self.assertIn("writes nothing", message)
        self.assertIn("added", message)

    def test_sync_now_applies_and_says_what_it_did(self):
        self.page.btn_apply_sync.click()
        self.assertEqual(self._titles(self.b), ["Buy ink"])
        self.assertIn("Synced", self.page.lbl_sync_status.text())
        self.assertGreaterEqual(self.shell.refreshes, 1, "the shell is refreshed so the desk notices")
        backups = os.path.join(self.b, "backups")
        self.assertTrue(os.path.isdir(backups), "writing a store takes a snapshot first")

    def test_an_empty_preview_reports_being_in_step(self):
        self.page.btn_apply_sync.click()
        with mock.patch.object(pages_module.QMessageBox, "information") as told:
            self.page.btn_preview_sync.click()
        self.assertIn("already in step", told.call_args[0][2])

    def test_a_foreign_file_is_reported_instead_of_crashing(self):
        path = sync_folder.payload_path(self.b)
        cases = (
            ("{not a mei payload", "could not be read"),
            ('{"kind": "something-else", "version": 1}', "not a Mei sync file"),
        )
        for junk, expected in cases:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(junk)
            for button in (self.page.btn_preview_sync, self.page.btn_apply_sync):
                with mock.patch.object(pages_module.QMessageBox, "warning") as warned:
                    button.click()
                message = warned.call_args[0][2]
                self.assertIn(expected, message)
                self.assertIn("Nothing was changed", message)
        self.assertEqual(self._titles(self.b), [])
        self.assertEqual(self._titles(self.a), ["Buy ink"])


if __name__ == "__main__":
    unittest.main()
