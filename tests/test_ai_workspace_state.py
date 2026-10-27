"""AI workspace state must match what the thread actions act on."""
import os
import tempfile
import unittest
from concurrent.futures import Future
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activates the Qt compatibility shim

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLabel, QListWidgetItem, QPushButton

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
        self.assertIs(self.window.context_stack.currentWidget(), self.window.context_empty)
        self.assertEqual(self.window._context_empty_title.text(), "Sources hidden")
        self.assertEqual(self.window.txt_context.toPlainText(), "")

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

        self.assertIs(self.window.context_stack.currentWidget(), self.window.context_empty)
        self.assertEqual(self.window._context_empty_title.text(), "Sources hidden")
        self.assertEqual(self.window.txt_context.toPlainText(), "")

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
        self.assertIn("could not answer", self.window.txt_answer.toPlainText().lower())
        self.assertEqual(self.window.lbl_status.text(), "Request failed")
        self.assertEqual(self.window.txt_context.toPlainText(), "")
        self.assertIs(self.window.context_stack.currentWidget(), self.window.context_empty)
        self.assertEqual(self.window._context_empty_title.text(), "No sources collected")
        self.assertIn("request failed", self.window.lbl_context_scope.text().lower())

    def test_an_empty_thread_and_source_region_explain_themselves(self):
        self.assertIs(self.window.thread_stack.currentWidget(), self.window.thread_empty)
        self.assertIs(self.window.context_stack.currentWidget(), self.window.context_empty)
        self.assertTrue(self.window.thread_empty.findChild(QLabel, "AIEmptyTitle").text())
        self.assertIn("nothing is sent", self.window._context_empty_hint.text().lower())
        starters = [
            button.text()
            for button in self.window.thread_empty.findChildren(QPushButton, "AIStarter")
        ]
        library = [self.window.prompt_list.item(row).text() for row in range(self.window.prompt_list.count())]
        self.assertEqual(len(starters), 3)
        self.assertTrue(set(starters).issubset(set(library)))

    def test_a_starter_prompt_fills_the_composer_without_sending(self):
        starter = self.window.thread_empty.findChildren(QPushButton, "AIStarter")[0]
        with mock.patch.object(self.window, "run_assistant_query") as ask:
            starter.click()

        self.assertEqual(self.window.ed_question.text(), starter.text())
        self.assertFalse(ask.called)

    def test_context_options_stay_visible_at_narrow_widths(self):
        self.window.setFixedWidth(656)
        self.window._apply_compact_layout()

        for checkbox in (self.window.chk_browser_context, self.window.chk_research_context, self.window.chk_show_context):
            self.assertFalse(checkbox.isHidden())
        for button in (
            self.window.btn_to_note,
            self.window.btn_to_task,
            self.window.btn_save_set,
            self.window.btn_export_thread,
            self.window.btn_clear_thread,
        ):
            self.assertFalse(button.isHidden())

    def test_the_context_summary_matches_the_enabled_options(self):
        self.window.chk_browser_context.setChecked(True)
        self.window.chk_research_context.setChecked(False)
        summary = self.window.lbl_context_next.text()
        self.assertIn("workspace index", summary)
        self.assertIn("browser page + open tabs", summary)
        self.assertNotIn("research desk", summary)

        self.window.chk_research_context.setChecked(True)
        self.assertIn("research desk", self.window.lbl_context_next.text())

    def test_remote_provider_is_disclosed_and_local_provider_is_not_called_remote(self):
        remote = self.window.cmb_provider.findData("openrouter")
        self.window.cmb_provider.setCurrentIndex(remote)
        self.assertIn("remote", self.window.lbl_privacy.text().lower())
        self.assertIn("openrouter", self.window.lbl_privacy.text().lower())
        self.assertEqual(self.window.ed_api_key.echoMode(), self.window.ed_api_key.Password)

        local = self.window.cmb_provider.findData("ollama")
        self.window.cmb_provider.setCurrentIndex(local)
        self.assertIn("local", self.window.lbl_privacy.text().lower())
        self.assertNotIn("opens the question remotely", self.window.lbl_privacy.text().lower())


if __name__ == "__main__":
    unittest.main()
