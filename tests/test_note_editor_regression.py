"""v6.5 regression: note editor must survive list refresh (data-loss fix)."""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Activate the Qt shim before importing the binding (and before QApplication
# exists). Importing PyQt5 first loads the *other* Qt runtime when PyQt6 is
# installed, and mixing two runtimes in one process crashes rather than failing.
import litebrowser  # noqa: F401 - litebrowser/__init__ activates the Qt shim

# QtWebEngine must be imported BEFORE QApplication is created (Qt hard
# requirement) — personal_window pulls it in transitively.
from PyQt5.QtWidgets import QApplication

from litebrowser.core import prefs
from litebrowser.services import personal_service
from litebrowser.ui import personal_window as _pw_module  # noqa: F401 - pulls QtWebEngine in before QApplication exists


@unittest.skipUnless(sys.platform.startswith("win"), "offscreen smoke on dev machine")
class TestNoteEditorSurvivesRefresh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self._patched = []

    def tearDown(self):
        # Restore any patched symbols before the temp dir goes away.
        import litebrowser.ui.personal_window as pw

        for attr, value in self._patched:
            setattr(pw, attr, value)
        self._tmp.cleanup()

    def _window(self):
        from PyQt5.QtWidgets import QWidget

        import litebrowser.ui.personal_window as pw

        # Stub the site preview builder: constructing real WebEngine objects
        # in offscreen mode spawns Chromium and hangs; the Sites page is not
        # under test here.
        class _FakeSiteView(QWidget):
            def __getattr__(self, name):
                return lambda *a, **k: None

        self._patched.append(("_build_site_view", pw.PersonalWindow._build_site_view))
        pw.PersonalWindow._build_site_view = lambda self: _FakeSiteView()

        win = pw.PersonalWindow(self.base, embedded=True)
        return win

    def test_refresh_keeps_open_note_and_content(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Alpha", "# Alpha\n\nbody", category="General")
        win._refresh_notes()
        win.select_note(note["id"])
        self.assertEqual(win.current_note_id, note["id"])

        # Simulate the user typing (marks dirty + schedules autosave).
        win.note_editor.setPlainText("# Alpha\n\nbody plus edits")
        self.assertTrue(win._note_dirty)

        # A search keystroke triggers _refresh_notes: the note must stay open.
        win.ed_note_search.setText("alp")
        win._notes_search_timer.start(); win._notes_search_timer.stop()  # emit timeout
        win._refresh_notes()  # what the debounce timer would run
        self.assertEqual(win.current_note_id, note["id"], "selection must survive refresh")
        self.assertIn("edits", win.note_editor.toPlainText())

    def test_immediate_note_switch_flushes_the_previous_edit(self):
        win = self._window()
        first = personal_service.create_note(self.base, "First", "original")
        second = personal_service.create_note(self.base, "Second", "other")
        win._refresh_notes()
        win.select_note(first["id"])
        win.note_editor.setPlainText("typed just before switching")
        win.select_note(second["id"])
        self.assertEqual(personal_service.read_note(self.base, first["id"])["content"], "typed just before switching")
        self.assertEqual(win.current_note_id, second["id"])
        win.deleteLater()

    def test_failed_autosave_keeps_text_and_cancels_navigation(self):
        win = self._window()
        first = personal_service.create_note(self.base, "First", "original")
        second = personal_service.create_note(self.base, "Second", "other")
        win._refresh_notes()
        win.select_note(first["id"])
        win.note_editor.setPlainText("must not lose this")
        with mock.patch.object(personal_service, "save_note", side_effect=OSError("disk full")):
            win._on_note_edit_idle()
            win.select_note(second["id"])
            win._back_to_all_notes()
        self.assertTrue(win._note_dirty)
        self.assertEqual(win.current_note_id, first["id"])
        self.assertEqual(win.note_editor.toPlainText(), "must not lose this")
        self.assertTrue(win._flush_note_edits())
        win.deleteLater()

    def test_deep_link_opens_a_note_hidden_by_search(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Target", "body", "School")
        win.ed_note_search.setText("not a match")
        win._refresh_notes()
        win.select_note(note["id"])
        self.assertEqual(win.current_note_id, note["id"])
        self.assertEqual(win.ed_note_search.text(), "")
        win.deleteLater()

    def test_conflicting_edit_keeps_both_versions(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Shared", "original")
        win._refresh_notes()
        win.select_note(note["id"])
        personal_service.save_note(self.base, note["id"], "newer edit from another window")
        win.note_editor.setPlainText("my unsaved draft")
        self.assertFalse(win._flush_note_edits())
        self.assertTrue(win._note_dirty)
        self.assertEqual(personal_service.read_note(self.base, note["id"])["content"], "newer edit from another window")
        win._save_note()
        self.assertNotEqual(win.current_note_id, note["id"])
        self.assertEqual(personal_service.read_note(self.base, win.current_note_id)["content"], "my unsaved draft")
        self.assertFalse(win._note_dirty)
        win.shutdown()
        win.deleteLater()

    def test_move_notes_updates_open_note_id(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Mover", "content", category="General")
        win._refresh_notes()
        win.select_note(note["id"])

        win._move_notes_to_category([note["id"]], "Work")
        new_note = personal_service.list_notes(self.base, "Mover")[0]
        self.assertEqual(win.current_note_id, new_note["id"], "open note must follow the moved file")
        # And a later save must succeed (v6.4 silently failed here).
        win.note_editor.setPlainText("updated body")
        win._save_note()
        saved = personal_service.read_note(self.base, win.current_note_id)
        self.assertEqual(saved["content"], "updated body")


if __name__ == "__main__":
    unittest.main()
