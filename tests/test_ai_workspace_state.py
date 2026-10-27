"""AI workspace state must match what the thread actions act on."""
import os
import tempfile
import unittest
from concurrent.futures import Future
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activates the Qt compatibility shim

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QListWidgetItem

from litebrowser.core import prefs
from litebrowser.ui.ai_window import AIWindow

_app = QApplication.instance() or QApplication([])


class TestAIWorkspaceState(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.window = AIWindow(self.base, embedded=True)

    def tearDown(self):
        self.window._executor.shutdown(wait=False, cancel_futures=True)
        self.window.deleteLater()
        self._tmp.cleanup()

    def test_clear_thread_clears_the_prompt_history_too(self):
        self.window._prompt_history = ["First question", "Second question"]
        self.window._thread_items = [{"question": "First question", "answer": "A"}]
        self.window.ed_question.setText("A draft")

        self.window._clear_thread()

        self.assertEqual(self.window._prompt_history, [])
        self.assertEqual(self.window._thread_items, [])
        self.assertEqual(self.window.get_current_ai_state(), [])
        self.assertEqual(self.window.ed_question.text(), "")

    def test_relock_clears_private_prompts_even_when_auto_save_fails(self):
        self.window._prompt_history = ["Private prompt"]
        with mock.patch.object(self.window, "_auto_save_set", side_effect=OSError("disk full")):
            self.window.relock()

        self.assertEqual(self.window._prompt_history, [])
        self.assertEqual(self.window.get_current_ai_state(), [])

    def test_show_sources_toggle_hides_existing_evidence_immediately(self):
        self.window._last_context = "[UNTRUSTED note] private source"
        self.window.txt_context.setPlainText(self.window._last_context)

        self.window.chk_show_context.setChecked(False)
        self.assertIn("hidden", self.window.txt_context.toPlainText().lower())
        self.assertNotIn("private source", self.window.txt_context.toPlainText())

        self.window.chk_show_context.setChecked(True)
        self.assertIn("private source", self.window.txt_context.toPlainText())

    def test_loading_history_retargets_save_and_export_to_that_answer(self):
        item = QListWidgetItem("Earlier question")
        item.setData(
            Qt.UserRole,
            {
                "question": "Earlier question",
                "answer": "Earlier answer",
                "context": "Earlier evidence",
                "context_label": "Context: Current note",
            },
        )

        self.window._load_history_item(item)

        self.assertEqual(self.window._last_question, "Earlier question")
        self.assertEqual(self.window._last_answer, "Earlier answer")
        self.assertEqual(self.window._last_context, "Earlier evidence")
        self.assertEqual(self.window.ed_question.text(), "Earlier question")

    def test_loading_history_respects_hidden_sources(self):
        self.window.chk_show_context.setChecked(False)
        item = QListWidgetItem("Earlier question")
        item.setData(
            Qt.UserRole,
            {"question": "Earlier question", "answer": "Earlier answer", "context": "Secret evidence"},
        )

        self.window._load_history_item(item)

        self.assertIn("hidden", self.window.txt_context.toPlainText().lower())
        self.assertNotIn("Secret evidence", self.window.txt_context.toPlainText())

    def test_failed_request_does_not_keep_the_previous_answer_as_save_target(self):
        self.window._last_question = "New question"
        self.window._last_answer = "Old answer"
        self.window._last_context = "Old evidence"
        self.window.txt_answer.setPlainText("Old answer")
        self.window.txt_context.setPlainText("Old evidence")
        future = Future()
        future.set_exception(RuntimeError("provider unavailable"))

        self.window._finish_assistant_query(future, "Workspace-wide", "RAG local only")

        self.assertEqual(self.window._last_answer, "")
        self.assertEqual(self.window._last_context, "")
        self.assertIn("failed", self.window.txt_answer.toPlainText().lower())
        self.assertEqual(self.window.txt_context.toPlainText(), "")
        self.assertIn("request failed", self.window.lbl_context_scope.text().lower())


if __name__ == "__main__":
    unittest.main()
