"""The AI looks at the browser: the page you are reading plus the open tabs.

`/ask`, the inline panel and the Insights bridge already attached the current
page; the AI workspace did not, so a question typed there saw only the profile
index. This file pins the toggle that closed that gap, and the untrusted-context
shape it produces (the assistant reads the page, it does not obey it).
"""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activates the Qt compatibility shim

from PyQt5.QtWidgets import QApplication, QWidget

from litebrowser.core import prefs
from litebrowser.ui.ai_window import AIWindow

_app = QApplication.instance() or QApplication([])


class _FakePage:
    """A WebEngine page that answers runJavaScript synchronously."""

    def __init__(self, text, private=False):
        self.text = text
        self.scripts = []
        self.private = private

    def profile(self):
        return _FakeProfile(self.private)

    def runJavaScript(self, script, callback):
        self.scripts.append(script)
        if callback is not None:
            callback(self.text)


class _FakeProfile:
    def __init__(self, private=False):
        self.private = private

    def isOffTheRecord(self):
        return self.private


class _FakeBrowser:
    def __init__(self, text="Body of the page", title="Docs", url="https://docs.example/x", private=False):
        self._page = _FakePage(text, private=private)
        self._title = title
        self._url = url

    def page(self):
        return self._page

    def title(self):
        return self._title

    def url(self):
        return _FakeUrl(self._url)


class _FakeUrl:
    def __init__(self, value):
        self._value = value

    def toString(self):
        return self._value


class _FakeBrowserPage(QWidget):
    def __init__(self, browser):
        super().__init__()
        self._browser = browser

    def current_browser(self):
        return self._browser

    def get_current_tab_state(self):
        return [
            {"title": "Docs", "url": "https://docs.example/x", "active": True},
            {"title": "Slides", "url": "https://slides.example/y", "active": False},
        ]


class _HostShell(QWidget):
    def __init__(self, browser):
        super().__init__()
        self.browser_page = _FakeBrowserPage(browser)
        self.refresh_shell = mock.Mock()


class _AICase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.browser = _FakeBrowser()
        self.shell = _HostShell(self.browser)
        self.window = AIWindow(self.base, embedded=True)
        self.window.setParent(self.shell)

    def tearDown(self):
        self.window._executor.shutdown(wait=False, cancel_futures=True)
        self.window.deleteLater()
        self.shell.deleteLater()
        self._tmp.cleanup()

    def _ask(self, question="What is this page about?"):
        self.window.ed_question.setText(question)
        with mock.patch.object(self.window, "run_assistant_query") as ask:
            self.window._ask()
        return ask


class TestBrowserContextToggle(_AICase):
    def test_the_toggle_exists_and_starts_on(self):
        self.assertTrue(self.window.chk_browser_context.isChecked())
        tooltip = self.window.chk_browser_context.toolTip().lower()
        self.assertIn("browser", tooltip)
        self.assertIn("untrusted", tooltip, "reading a page must stay untrusted context")
        self.assertIn("remote provider", tooltip)
        self.assertIn("page text and open-tab titles/urls", tooltip)
        self.assertIn("sent to that provider", tooltip)

    def test_research_context_is_off_by_default_and_disclosure_is_visible(self):
        self.assertFalse(self.window.chk_research_context.isChecked())
        self.assertIn("may be sent", self.window.chk_research_context.toolTip())

    def test_research_context_preference_is_remembered(self):
        self.window.chk_research_context.setChecked(True)
        self.window._save_settings()
        self.assertTrue(prefs.load_ai_settings(self.base)["read_research"])

    def test_the_choice_is_remembered_with_the_provider(self):
        self.window.chk_browser_context.setChecked(False)
        self.window._save_settings()
        self.assertEqual(prefs.load_ai_settings(self.base)["read_browser"], False)

    def test_the_browser_context_reaches_the_question(self):
        ask = self._ask()
        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Browser page + open tabs")
        self.assertIn("Body of the page", context)
        self.assertIn("https://docs.example/x", context)
        self.assertIn("[Open tabs in this window]", context)
        self.assertIn("Slides", context, "the assistant sees the session, not one page")

    def test_opted_in_research_context_joins_the_browser_context(self):
        from litebrowser.services import personal_service, tab_sets

        note = personal_service.create_note(self.base, "Lab notes", "Local note body.")
        workspace = tab_sets.add_tab_set(self.base, "workspace", "Chemistry project", [], notes=[note["id"]])
        tab_sets.set_active_research_workspace(self.base, workspace["id"])
        self.window.chk_research_context.setChecked(True)
        ask = self._ask("Summarize the research")
        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Browser page + open tabs + research")
        self.assertIn("Local note body", context)
        self.assertIn("Chemistry project", context)

    def test_one_shot_context_research_and_browser_text_are_all_combined(self):
        from litebrowser.services import personal_service, tab_sets

        note = personal_service.create_note(self.base, "Lab notes", "Research record body.")
        workspace = tab_sets.add_tab_set(self.base, "workspace", "Chemistry project", [], notes=[note["id"]])
        tab_sets.set_active_research_workspace(self.base, workspace["id"])
        self.window.chk_research_context.setChecked(True)
        self.window._external_context_label = "Selected passage"
        self.window._external_context = "Passage selected by the user."

        ask = self._ask("Compare this passage with my desk")

        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Browser page + open tabs + research")
        self.assertIn("Passage selected by the user.", context)
        self.assertIn("Research record body.", context)
        self.assertIn("Body of the page", context)

    def test_ai_save_can_distinguish_full_research_workspace_from_no_workspace(self):
        from litebrowser.services import tab_sets

        workspace = tab_sets.add_tab_set(self.base, "workspace", "Full desk", [])
        tab_sets.set_active_research_workspace(self.base, workspace["id"])
        for index in range(20):
            tab_sets.add_research_reference(self.base, workspace["id"], "note", f"note-{index}")

        self.assertEqual(self.window._link_to_active_research("note", "new-note"), ("Full desk", False))
        tab_sets.set_active_research_workspace(self.base, "")
        self.assertEqual(self.window._link_to_active_research("note", "new-note"), ("", False))

    def test_successful_ai_link_refreshes_the_hosting_home_desk(self):
        from litebrowser.services import tab_sets

        workspace = tab_sets.add_tab_set(self.base, "workspace", "Live desk", [])
        tab_sets.set_active_research_workspace(self.base, workspace["id"])

        linked_to, linked = self.window._link_to_active_research("note", "saved-note")

        self.assertEqual((linked_to, linked), ("Live desk", True))
        self.shell.refresh_shell.assert_called_once_with()

    def test_incognito_page_text_is_never_attached(self):
        self.shell.browser_page._browser = _FakeBrowser(private=True)
        ask = self._ask()
        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Workspace-wide (private page excluded)")
        self.assertEqual(context, "")
        self.assertIn("private page excluded", self.window.lbl_context_scope.text())

    def test_incognito_excludes_private_page_but_keeps_opted_in_research(self):
        from litebrowser.services import personal_service, tab_sets

        note = personal_service.create_note(self.base, "Private-safe notes", "Workspace research stays available.")
        workspace = tab_sets.add_tab_set(self.base, "workspace", "Research desk", [], notes=[note["id"]])
        tab_sets.set_active_research_workspace(self.base, workspace["id"])
        self.window.chk_research_context.setChecked(True)
        self.shell.browser_page._browser = _FakeBrowser(
            text="SECRET PRIVATE PAGE TEXT", url="https://private.example/secret", private=True
        )

        ask = self._ask("Summarize the research")

        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Research: Research desk (private page excluded)")
        self.assertIn("Workspace research stays available.", context)
        self.assertNotIn("SECRET PRIVATE PAGE TEXT", context)
        self.assertNotIn("private.example", context)

    def test_profile_check_failure_fails_closed_without_reading_page(self):
        class _BrokenProfile:
            def isOffTheRecord(self):
                raise ValueError("profile state unavailable")

        self.browser._page.profile = lambda: _BrokenProfile()
        ask = self._ask()

        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Workspace-wide (page privacy unverified)")
        self.assertEqual(context, "")
        self.assertEqual(self.browser._page.scripts, [])
        self.assertIn("privacy could not be verified", self.window.lbl_context_scope.text())

    def test_closing_page_during_context_read_keeps_local_context(self):
        self.browser._page.runJavaScript = mock.Mock(side_effect=RuntimeError("page closed"))
        ask = self._ask()

        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Workspace-wide (browser page unavailable)")
        self.assertEqual(context, "")
        self.assertIn("browser page unavailable", self.window.lbl_context_scope.text())

    def test_the_page_is_read_through_javascript(self):
        self._ask()
        self.assertTrue(self.browser._page.scripts)
        self.assertIn("document.body", self.browser._page.scripts[0])

    def test_turning_the_toggle_off_keeps_the_question_workspace_wide(self):
        self.window.chk_browser_context.setChecked(False)
        ask = self._ask()
        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Workspace-wide")
        self.assertEqual(context, "")

    def test_an_empty_page_falls_back_to_the_plain_context(self):
        self.browser._page.text = ""
        self.browser._page = _FakePage("")
        self.shell.browser_page._browser = _FakeBrowser(text="")
        self.shell.browser_page.get_current_tab_state = lambda: []
        ask = self._ask()
        _question, label, _context = ask.call_args[0]
        self.assertEqual(label, "Workspace-wide")

    def test_a_context_injected_by_a_note_is_not_replaced(self):
        self.window._external_context = "Title: My note\n\nbody"
        self.window._external_context_label = "Current note"
        ask = self._ask()
        _question, label, context = ask.call_args[0]
        self.assertEqual(label, "Current note")
        self.assertEqual(context, "Title: My note\n\nbody")

    def test_an_unembedded_pane_asks_normally(self):
        self.window.setParent(None)
        ask = self._ask()
        _question, label, _context = ask.call_args[0]
        self.assertEqual(label, "Workspace-wide")


class TestPrivacyCallbacks(_AICase):
    def test_late_answer_after_relock_is_discarded_even_after_unlock(self):
        from concurrent.futures import Future
        future = Future()
        future.set_result({"answer": "private old answer", "context": "private source"})
        self.window._active_query = future
        self.window.relock()
        self.window._privacy_locked = False
        self.window._finish_assistant_query(future, "Old context")
        self.assertEqual(self.window.txt_answer.toPlainText(), "")
        self.assertEqual(self.window.txt_context.toPlainText(), "")


class TestIndexCarriesTheWeek(_AICase):
    def test_the_study_week_is_indexed_for_the_assistant(self):
        from litebrowser.services import ai_service

        docs = [doc for doc in ai_service.collect_docs(self.base) if doc.source == "study_week"]
        self.assertEqual(len(docs), 1)
        self.assertIn("Study week", docs[0].title)
        self.assertEqual(docs[0].meta["days"], 7)


if __name__ == "__main__":
    unittest.main()
