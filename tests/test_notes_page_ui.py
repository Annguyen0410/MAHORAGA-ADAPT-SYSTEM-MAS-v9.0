"""Notes page refinement: browsing rows, writing state, save signals, measure.

Exercised on a real offscreen PersonalWindow so the assertions cover the widget
tree the app builds, not a parallel mock of it.
"""
import gc
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activates the Qt shim

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QStyleOptionViewItem, QWidget

from litebrowser.core import prefs
from litebrowser.services import personal_service
from litebrowser.ui import personal_window as pw

LONG_TITLE = "Kien truc he thong va cac tang giao thuc mang may tinh trong thuc te"

# PyQt5 spells the attribute unscoped; PyQt6 (through the shim) scopes it.
Qt_WA_DELETE_ON_CLOSE = getattr(Qt, "WA_DeleteOnClose", None)
if Qt_WA_DELETE_ON_CLOSE is None:  # pragma: no cover - PyQt6 spelling
    Qt_WA_DELETE_ON_CLOSE = Qt.WidgetAttribute.WA_DeleteOnClose


@unittest.skipUnless(sys.platform.startswith("win"), "offscreen smoke on dev machine")
class TestNotesPageUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self._patched = []
        self.window = None

    def tearDown(self):
        for attr, value in self._patched:
            setattr(pw, attr, value)
        if self.window is not None:
            # Drop the window for real. `deleteLater()` alone is not enough:
            # a DeferredDelete posted inside a test cannot run before the test's
            # own event loop returns, so every window stayed alive and a later
            # app-wide stylesheet change re-polished all of them (unrelated
            # paint tests went from 0.2s to a minute). PyQt owns a parentless
            # window, so releasing the last Python reference frees the tree.
            self.window.close()
            self.window.setParent(None)
            self.window = None
            gc.collect()
            QApplication.processEvents()
        self._tmp.cleanup()

    def _window(self, width=1440, height=900, show=False):
        class _FakeSiteView(QWidget):
            def __getattr__(self, name):
                return lambda *a, **k: None

        # Building real WebEngine views in offscreen mode spawns Chromium and
        # hangs; the Sites page is not under test here.
        self._patched.append(("_build_site_view", pw.PersonalWindow._build_site_view))
        pw.PersonalWindow._build_site_view = lambda self: _FakeSiteView()
        self.window = pw.PersonalWindow(self.base, embedded=True)
        self.window.resize(width, height)
        self.window._switch_page("notes")
        if show:
            self.window.show()
            QApplication.processEvents()
        return self.window

    @staticmethod
    def _shown(widget) -> bool:
        """Show/hide intent of a child, without showing the whole window."""
        return not widget.isHidden()

    # ---------------------------------------------------------------- rows

    def test_rows_carry_title_meta_and_a_full_title_tooltip(self):
        win = self._window()
        personal_service.create_note(
            self.base,
            LONG_TITLE,
            "# " + LONG_TITLE + "\n\nTang ung dung, tang van chuyen. " + "body " * 40,
            category="School",
        )
        win._refresh_notes()

        item = win.notes_list.item(0)
        self.assertEqual(item.text(), LONG_TITLE, "the item keeps the note's real title")
        payload = item.data(pw.NOTE_ROW_ROLE)
        self.assertEqual(payload["title"], LONG_TITLE)
        self.assertEqual(payload["category"], "School")
        self.assertIn("words", payload["meta"])

        tooltip = item.toolTip().splitlines()
        self.assertEqual(tooltip[0], LONG_TITLE, "a long title must be readable in full")
        self.assertIn("School", tooltip[1])
        self.assertTrue(tooltip[-1].startswith("Tang ung dung"), "the tooltip previews the note's own text")

    def test_rows_elide_instead_of_clipping_and_keep_a_painted_line(self):
        win = self._window()
        personal_service.create_note(self.base, LONG_TITLE, "body", category="General")
        win._refresh_notes()
        delegate = win.notes_list.itemDelegate()
        self.assertIsInstance(delegate, pw.NoteRowDelegate)

        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 120, delegate.ROW_HEIGHT)
        option.font = QFont()
        index = win.notes_list.model().index(0, 0)
        self.assertEqual(delegate.sizeHint(option, index).height(), delegate.ROW_HEIGHT)

        canvas = QPixmap(120, delegate.ROW_HEIGHT)
        canvas.fill()
        painter = QPainter(canvas)
        try:
            delegate.paint(painter, option, index)
        finally:
            painter.end()
        painted = canvas.toImage()
        ink = 0
        for y in range(painted.height()):
            for x in range(painted.width()):
                if painted.pixelColor(x, y).alpha() > 0:
                    ink += 1
        self.assertGreater(ink, 40, "the row drew its title/meta lines")

    def test_real_view_paint_pass_survives_a_refresh(self):
        """The delegate runs inside the list's own paint pass, not only by hand.

        The first version of this delegate read ``option.state & QStyle.State_Selected``
        and took the whole process down (no traceback) as soon as the view painted a
        row, so the real paint pass is exercised here on purpose.
        """
        win = self._window(show=True)
        note = personal_service.create_note(self.base, LONG_TITLE, "body " * 30)
        win._refresh_notes()
        win.select_note(note["id"])
        QApplication.processEvents()
        win._flash("a message")
        win._back_to_all_notes()
        QApplication.processEvents()
        rect = win.notes_list.visualItemRect(win.notes_list.item(0))
        self.assertGreater(rect.height(), 0)
        self.assertTrue(self._shown(win._note_empty))

    def test_selected_row_draws_with_the_accent_ink(self):
        win = self._window()
        first = personal_service.create_note(self.base, "Alpha", "body")
        personal_service.create_note(self.base, "Beta", "body")
        win._refresh_notes()
        win.select_note(first["id"])
        QApplication.processEvents()
        delegate = win.notes_list.itemDelegate()
        rows = []
        for row in range(win.notes_list.count()):
            index = win.notes_list.model().index(row, 0)
            option = QStyleOptionViewItem()
            option.rect = QRect(0, 0, 220, delegate.ROW_HEIGHT)
            option.widget = win.notes_list
            option.index = index
            canvas = QPixmap(220, delegate.ROW_HEIGHT)
            canvas.fill()
            painter = QPainter(canvas)
            try:
                delegate.paint(painter, option, index)
            finally:
                painter.end()
            image = canvas.toImage()
            rows.append(
                [
                    image.pixelColor(x, y).name()
                    for y in range(image.height())
                    for x in range(image.width())
                    if image.pixelColor(x, y).alpha() > 0
                ]
            )
        self.assertNotEqual(rows[0], rows[1], "the open note must not paint like the rest")

    def test_hint_row_without_a_payload_still_paints(self):
        win = self._window()
        win.ed_note_search.setText("nothing matches this")
        win._refresh_notes()
        self.assertTrue(win.notes_list.count())
        item = win.notes_list.item(0)
        self.assertIsNone(item.data(pw.NOTE_ROW_ROLE))
        delegate = win.notes_list.itemDelegate()
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 220, 40)
        canvas = QPixmap(220, 40)
        canvas.fill()
        painter = QPainter(canvas)
        try:
            delegate.paint(painter, option, win.notes_list.model().index(0, 0))
        finally:
            painter.end()

    def test_header_counts_the_shelf(self):
        win = self._window()
        self.assertEqual(win._notes_header_subtitle.text(), "No notes yet")
        for title in ("One", "Two", "Three"):
            personal_service.create_note(self.base, title, "body")
        win._refresh_notes()
        self.assertEqual(win._notes_header_subtitle.text(), "3 notes")

        win.ed_note_search.setText("Two")
        win._refresh_notes()
        self.assertEqual(win._notes_header_subtitle.text(), "1 of 3 notes")

    # ------------------------------------------------------- writing state

    def test_empty_state_replaces_a_dead_editor(self):
        win = self._window()
        self.assertTrue(self._shown(win._note_empty))
        self.assertIn("empty", win._note_empty_title.text().lower())
        self.assertFalse(self._shown(win.note_editor))
        self.assertTrue(win.note_editor.isReadOnly(), "nothing typed into a note-less editor is kept")
        self.assertFalse(win.btn_save_note.isEnabled())
        self.assertFalse(self._shown(win.btn_empty_search), "there is nothing to search yet")

        personal_service.create_note(self.base, "Alpha", "body")
        win._refresh_notes()
        win._back_to_all_notes()
        QApplication.processEvents()
        self.assertTrue(self._shown(win._note_empty))
        self.assertIn("Pick a note", win._note_empty_title.text())
        self.assertTrue(self._shown(win.btn_empty_search))

    def test_opening_a_note_makes_the_column_writable(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Alpha", "# Alpha\n\nbody")
        win._refresh_notes()
        win.select_note(note["id"])
        QApplication.processEvents()
        self.assertFalse(self._shown(win._note_empty))
        self.assertTrue(self._shown(win.note_editor))
        self.assertFalse(win.note_editor.isReadOnly())
        self.assertTrue(win.btn_save_note.isEnabled())
        self.assertTrue(self._shown(win.btn_note_tools))
        self.assertTrue(self._shown(win._find_bar))

        win._show_no_note_state()
        QApplication.processEvents()
        self.assertTrue(self._shown(win._note_empty))
        self.assertFalse(self._shown(win.note_editor))
        self.assertTrue(win.note_editor.isReadOnly())

    def test_new_note_from_the_empty_state_opens_the_editor(self):
        win = self._window()
        with mock.patch.object(pw.QInputDialog, "getText", return_value=("From the empty state", True)):
            win.btn_empty_new.click()
        QApplication.processEvents()
        self.assertTrue(win.current_note_id)
        self.assertFalse(self._shown(win._note_empty))
        self.assertFalse(win.note_editor.isReadOnly())
        self.assertIn("From the empty state", win.lbl_note_title.text())

    # -------------------------------------------------------- save signals

    def test_save_state_tracks_dirty_autosave_and_failures(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Alpha", "# Alpha\n\nbody")
        win._refresh_notes()
        win.select_note(note["id"])
        self.assertEqual(win.lbl_note_save.property("state"), "saved")
        self.assertFalse(win.btn_save_note.property("dirty"))

        win.note_editor.setPlainText("typed here")
        QApplication.processEvents()
        self.assertEqual(win.lbl_note_save.property("state"), "dirty")
        self.assertTrue(win.btn_save_note.property("dirty"))
        self.assertIn("Unsaved", win.lbl_note_save.text())

        win._on_note_edit_idle()
        self.assertEqual(win.lbl_note_save.property("state"), "saved")
        self.assertFalse(win.btn_save_note.property("dirty"))

        win.note_editor.setPlainText("disk trouble")
        with mock.patch.object(personal_service, "save_note", side_effect=OSError("disk full")):
            self.assertFalse(win._flush_note_edits())
        self.assertEqual(win.lbl_note_save.property("state"), "error")
        self.assertIn("retry", win.lbl_note_save.text())

        with mock.patch.object(
            personal_service, "save_note", side_effect=personal_service.NoteConflictError("newer")
        ):
            self.assertFalse(win._flush_note_edits())
        self.assertEqual(win.lbl_note_save.property("state"), "error")
        self.assertIn("Conflict", win.lbl_note_save.text())

    def test_status_messages_never_rewrite_the_note_title(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Alpha", "# Alpha\n\nbody", category="General")
        win._refresh_notes()
        win.select_note(note["id"])
        title = win.lbl_note_title.text()

        win._flash("Opened [[Beta]]")
        self.assertEqual(win.lbl_note_title.text(), title)
        self.assertEqual(win.lbl_note_status.text(), "Opened [[Beta]]")
        self.assertTrue(self._shown(win.lbl_note_status))

        win._move_notes_to_category([win.current_note_id], "Work")
        self.assertTrue(win.lbl_note_title.text().startswith("Alpha"))
        self.assertIn("Moved 1 note", win.lbl_note_status.text())
        self.assertEqual(win._note_title, "Alpha", "the note's own title is what save/export/delete use")

        win._clear_note_status()
        self.assertFalse(self._shown(win.lbl_note_status))

    def test_selected_text_card_back_names_the_note(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Alpha", "# Alpha\n\nfirst line here")
        win._refresh_notes()
        win.select_note(note["id"])
        win._flash("Opened [[Beta]]")
        win.note_editor.selectAll()
        win._make_flashcard_from_selection()
        from litebrowser.services import flashcard_service

        cards = flashcard_service.load_cards(self.base)
        self.assertTrue(cards)
        self.assertEqual(cards[0]["back"], "From: Alpha")

    # ------------------------------------------------------- typography/measure

    def test_text_size_control_moves_the_editor_font(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Alpha", "long text")
        win._refresh_notes()
        win.select_note(note["id"])
        for value in ("13", "20"):
            win.cmb_note_font.setCurrentText(value)
            QApplication.processEvents()
            self.assertEqual(win.note_editor.font().pixelSize(), int(value))
            self.assertEqual(win.note_editor.document().defaultFont().pixelSize(), int(value))
            self.assertEqual(win.note_editor.property("textSize"), value)

    def test_writing_measure_insets_only_on_a_wide_column(self):
        win = self._window(width=620, height=800, show=True)
        win._apply_compact_layout()
        QApplication.processEvents()
        self.assertEqual(win._editor_layout.contentsMargins().left(), 0)

        win.resize(1600, 900)
        win._notes_splitter.setSizes([240, 1200])
        win._apply_notes_measure()
        QApplication.processEvents()
        inset = win._editor_layout.contentsMargins().left()
        self.assertGreater(inset, 0)
        self.assertLessEqual(inset, 170)
        # Resizing stays the user's: both panes are still draggable afterwards.
        self.assertFalse(win._notes_splitter.childrenCollapsible())
        win._notes_splitter.setSizes([400, 900])
        self.assertEqual(win._notes_splitter.sizes()[0], 400)

    def test_tools_row_keeps_every_verb_and_toggles(self):
        win = self._window()
        note = personal_service.create_note(self.base, "Alpha", "body")
        win._refresh_notes()
        win.select_note(note["id"])
        self.assertFalse(self._shown(win._note_tools))
        win.btn_note_tools.setChecked(True)
        QApplication.processEvents()
        self.assertTrue(self._shown(win._note_tools))
        self.assertIn("▴", win.btn_note_tools.text())
        for widget in (win.btn_note_ai, win.btn_note_flash, win.btn_delete_note, win.cmb_note_font, win.chk_neural_graph):
            self.assertIs(widget.parentWidget().window(), win)
        win.btn_note_tools.setChecked(False)
        QApplication.processEvents()
        self.assertFalse(self._shown(win._note_tools))
        self.assertIn("▾", win.btn_note_tools.text())


if __name__ == "__main__":
    unittest.main()
