"""The loop's desktop wiring: Home strip, /flow routing, planner hint, note links.

The service layer is covered by test_study_flow.py; this file pins the four
surfaces that make the loop usable: the Continue button on Home, the routing
table in AppShell.open_flow_step, the study label that hands the student to
Review, and the note→card link the Related panel reads.
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activates the Qt compatibility shim

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget

from litebrowser.core import prefs
from litebrowser.services import (
    flashcard_service,
    focus_service,
    life_service,
    link_service,
    personal_plan,
    personal_service,
    study_flow,
    study_session,
)
from litebrowser.ui import app_shell as app_shell_module
from litebrowser.ui import personal_window as pw_module  # noqa: F401 - QtWebEngine first
from litebrowser.ui.shell import pages as pages_module

_app = QApplication.instance() or QApplication([])


class _StubShell(QWidget):
    """The shell surface Home touches while building and refreshing."""

    def __init__(self, base_dir):
        super().__init__()
        self.profile_dir = base_dir
        self.workspaces = []
        self.flow_steps = []
        self.refreshes = 0
        self.flashed = []
        self.personal_page = _StubPersonal()
        self.browser_page = _StubBrowser()
        self.library_page = _StubLibrary()

    def switch_workspace(self, name):
        self.workspaces.append(name)
        return True

    def open_flow_step(self, action):
        self.flow_steps.append(action)

    def refresh_shell(self, force_deep=False):
        self.refreshes += 1

    def _flash_status(self, message):
        self.flashed.append(message)

    def run_update_check(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _StubPersonal(QWidget):
    def __init__(self):
        super().__init__()
        self.pages = []
        self.selected = []
        self.opened_items = []
        self.refreshes = 0

    def _switch_page(self, name):
        self.pages.append(name)

    def select_note(self, note_id):
        self.selected.append(note_id)

    def open_plan_item(self, item_id):
        self.opened_items.append(item_id)

    def refresh_all(self):
        self.refreshes += 1


class _StubBrowser(QWidget):
    def __init__(self):
        super().__init__()
        self.url_bar = _StubLineEdit()

    def get_current_tab_state(self):
        return {}


class _StubLineEdit(QWidget):
    def setText(self, text):
        self.text = text


class _StubLibrary(QWidget):
    def refresh(self, *args, **kwargs):
        return None


class _HomeBase(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.shell = _StubShell(self.base)
        self.page = pages_module.HomeDashboardPage(self.shell)

    def tearDown(self):
        self.page.deleteLater()
        self.shell.deleteLater()
        self._tmp.cleanup()

    def _agenda_row(self, kind):
        for index in range(self.page.recent_tasks.count()):
            row = self.page.recent_tasks.item(index)
            data = row.data(Qt.UserRole) or {}
            if isinstance(data, dict) and data.get("kind") == kind:
                return row
        return None


class TestHomeFlowStrip(_HomeBase):
    def test_strip_exists_on_the_today_card(self):
        self.assertTrue(hasattr(self.page, "lbl_flow"))
        self.assertEqual(self.page.btn_flow_next.parent() is not None, True)
        self.assertIn("loop", self.page.btn_flow_next.toolTip().lower())

    def test_strip_reports_the_loop_and_offers_the_next_step(self):
        personal_plan.create_item(self.base, "Late essay", due_date="2020-01-01")
        self.page.refresh()
        self.assertIn("1 overdue", self.page.lbl_flow.text())
        self.assertIn("next:", self.page.lbl_flow.text())
        # The margin verb stays short; the recommendation is still carried by
        # its accessible name (and by the filled Next step button).
        self.assertEqual(self.page.btn_flow_next.text(), "Continue")
        self.assertIn("Late essay", self.page.btn_flow_next.accessibleName())
        self.assertTrue(self.page.btn_flow_next.isEnabled())

    def test_continue_button_routes_the_recommendation_through_the_shell(self):
        personal_plan.create_item(self.base, "Late essay", due_date="2020-01-01")
        self.page.refresh()
        self.page._run_flow_next()
        self.assertEqual(len(self.shell.flow_steps), 1)
        action = self.shell.flow_steps[0]
        self.assertEqual(action["step"], "study")
        self.assertEqual(action["kind"], "planner-item")
        self.assertTrue(action["start"])

    def test_continue_falls_back_to_a_fresh_recommendation(self):
        self.page.refresh()
        self.page._flow_next = {}
        self.page._run_flow_next()
        self.assertEqual(self.shell.flow_steps[0]["step"], "plan")

    def test_agenda_rows_still_open_where_they_live(self):
        item = personal_plan.create_item(self.base, "Read ch.5", scheduled_date=personal_plan._today())
        self.page.refresh()
        row = self._agenda_row("planner-item")
        self.assertIsNotNone(row)
        with mock.patch.object(self.shell, "open_library_item", create=True) as opener:
            self.page._open_agenda_item(row)
        self.assertEqual(opener.call_args[0][0]["id"], item["id"])


class TestHomePromote(_HomeBase):
    def test_promote_moves_the_selected_inbox_row_into_the_plan(self):
        task = life_service.add_task(self.base, "Summarise notes", bucket="today")
        self.page.refresh()
        row = self._agenda_row("task")
        self.assertIsNotNone(row)
        self.page.recent_tasks.setCurrentItem(row)

        with mock.patch.object(pages_module.QMessageBox, "information"):
            self.page._promote_agenda_task()

        items = personal_plan.load_plan(self.base)["items"]
        self.assertEqual([item["title"] for item in items], ["Summarise notes"])
        self.assertEqual(link_service.links_for(self.base, "task", task["id"])["total"], 1)
        self.assertEqual(self.shell.refreshes, 1, "Home and the plan must both see the new row")

    def test_promote_with_a_planner_row_selected_explains_itself(self):
        personal_plan.create_item(self.base, "Read ch.5", scheduled_date=personal_plan._today())
        self.page.refresh()
        self.page.recent_tasks.setCurrentItem(self._agenda_row("planner-item"))
        with mock.patch.object(pages_module.QMessageBox, "information") as info:
            self.page._promote_agenda_task()
        info.assert_called_once()
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["title"], "Read ch.5")
        self.assertEqual(len(personal_plan.load_plan(self.base)["items"]), 1)

    def test_promote_with_nothing_selected_is_safe(self):
        self.page.recent_tasks.setCurrentItem(None)
        with mock.patch.object(pages_module.QMessageBox, "information") as info:
            self.page._promote_agenda_task()
        info.assert_called_once()
        self.assertEqual(personal_plan.load_plan(self.base)["items"], [])

    def test_the_promoted_row_leaves_the_today_agenda(self):
        life_service.add_task(self.base, "Summarise notes", bucket="today")
        self.page.refresh()
        self.page.recent_tasks.setCurrentItem(self._agenda_row("task"))
        with mock.patch.object(pages_module.QMessageBox, "information"):
            self.page._promote_agenda_task()
        self.page.refresh()
        self.assertIsNone(self._agenda_row("task"))
        self.assertIsNotNone(self._agenda_row("planner-item"))


class TestOpenFlowStepRouting(unittest.TestCase):
    """AppShell.open_flow_step is duck-typed: the shell owns switching, not state."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.shell = _StubShell(self.base)
        self.open_step = app_shell_module.AppShell.open_flow_step

    def tearDown(self):
        self.shell.deleteLater()
        self._tmp.cleanup()

    def test_study_step_starts_a_pour_and_opens_the_plan(self):
        item = personal_plan.create_item(self.base, "Read ch.5", duration_minutes=30)
        self.open_step(
            self.shell,
            {"step": "study", "kind": "planner-item", "id": item["id"], "minutes": 30, "start": True},
        )
        status = focus_service.focus_status(self.base)
        self.assertTrue(status["running"])
        self.assertEqual(status["session"]["item_id"], item["id"])
        self.assertEqual(status["session"]["minutes"], 30)
        self.assertEqual(self.shell.workspaces, ["personal"])
        self.assertEqual(self.shell.personal_page.pages, ["plan"])
        self.assertTrue(self.shell.flashed and "Read ch.5" in self.shell.flashed[0])

    def test_block_step_starts_a_pour_for_the_block(self):
        item = personal_plan.create_item(self.base, "Physics", duration_minutes=50)
        block = personal_plan.create_time_block(
            self.base, "Tự học", personal_plan._today(), 540, item_id=item["id"]
        )
        self.open_step(
            self.shell,
            {"step": "study", "kind": "planner-block", "id": block["id"], "minutes": 50, "start": True},
        )
        stored = focus_service.focus_status(self.base)["session"]
        self.assertEqual(stored["label"], "Tự học")
        self.assertEqual(stored["item_id"], item["id"])

    def test_running_pour_step_only_navigates(self):
        session = focus_service.start_focus(self.base, minutes=25, label="Deep work")
        self.open_step(self.shell, study_flow.next_step(self.base))
        self.assertEqual(self.shell.personal_page.pages, ["plan"])
        active = focus_service.focus_status(self.base)["session"]
        self.assertEqual(active["id"], session["id"], "the same pour, not a second one")
        self.assertEqual(focus_service.focus_journal(self.base), [])

    def test_review_step_opens_the_deck(self):
        self.open_step(self.shell, {"step": "review", "label": "Review"})
        self.assertEqual(self.shell.workspaces, ["personal"])
        self.assertEqual(self.shell.personal_page.pages, ["review"])

    def test_capture_step_selects_the_note(self):
        note = personal_service.create_note(self.base, "OSI Model", "body")
        self.open_step(self.shell, {"step": "capture", "kind": "note", "id": note["id"]})
        self.assertEqual(self.shell.personal_page.selected, [note["id"]])
        self.assertEqual(self.shell.personal_page.pages, [])

    def test_plan_step_promotes_then_opens_the_planner_on_the_new_row(self):
        task = life_service.add_task(self.base, "Write lab report", bucket="today")
        self.open_step(self.shell, study_flow.next_step(self.base))
        items = personal_plan.load_plan(self.base)["items"]
        self.assertEqual([item["title"] for item in items], ["Write lab report"])
        self.assertEqual(link_service.links_for(self.base, "task", task["id"])["total"], 1)
        self.assertEqual(self.shell.personal_page.pages, ["plan"])
        self.assertEqual(self.shell.personal_page.opened_items, [items[0]["id"]])
        self.assertTrue(
            any("Write lab report" in message for message in self.shell.flashed),
            "the status strip says what was planned",
        )

    def test_plan_step_with_a_stale_row_only_navigates(self):
        self.open_step(self.shell, {"step": "plan", "kind": "task", "id": "gone"})
        self.assertEqual(personal_plan.load_plan(self.base)["items"], [])
        self.assertEqual(self.shell.personal_page.pages, ["plan"])

    def test_a_date_free_plan_step_opens_the_planner(self):
        self.open_step(self.shell, {"step": "plan", "label": "Plan your week"})
        self.assertEqual(self.shell.personal_page.pages, ["plan"])
        self.assertEqual(personal_plan.load_plan(self.base)["items"], [])

    def test_unknown_step_falls_back_to_the_planner(self):
        self.open_step(self.shell, {})
        self.open_step(self.shell, None)
        self.assertEqual(self.shell.personal_page.pages, ["plan", "plan"])

    def test_a_deleted_item_never_starts_a_ghost_pour(self):
        self.open_step(
            self.shell,
            {"step": "study", "kind": "planner-item", "id": "gone", "minutes": 25, "start": True},
        )
        self.assertFalse(focus_service.focus_status(self.base)["running"])
        self.assertEqual(self.shell.workspaces, [], "nothing to show: no switch")

    def test_started_session_matches_the_loop_recommendation(self):
        item = personal_plan.create_item(self.base, "Late essay", due_date="2020-01-01", duration_minutes=45)
        action = study_flow.next_step(self.base)
        self.open_step(self.shell, action)
        session = study_session.active_session(self.base)
        self.assertTrue(session["running"])
        self.assertEqual(session["item"]["id"], item["id"])
        self.assertEqual(session["session"]["minutes"], 45)


class TestFlowCommandWiring(unittest.TestCase):
    def test_flow_is_matched_exactly(self):
        from litebrowser.ui.app_shell import AppShell

        self.assertTrue(AppShell._match_cmd(_StubShell("/tmp"), "/flow", "/flow"))
        self.assertTrue(AppShell._match_cmd(_StubShell("/tmp"), "/flow ", "/flow"))
        self.assertFalse(AppShell._match_cmd(_StubShell("/tmp"), "/flowchart", "/flow"))

    def test_flow_branch_reports_then_routes(self):
        import inspect

        src = inspect.getsource(app_shell_module.AppShell._handle_omnibar_text)
        self.assertIn('"/flow"', src)
        branch = src.split('"/flow"')[1].split("if lowered ==")[0]
        self.assertIn("study_flow.build_flow", branch)
        self.assertIn("open_flow_step", branch)
        # The report is generated from the registry, so a new step needs no edit here.
        self.assertIn("step['title']", branch)
        self.assertIn("step['detail']", branch)

    def test_home_strip_and_command_share_one_router(self):
        import inspect

        home = inspect.getsource(pages_module.HomeDashboardPage._run_flow_next)
        self.assertIn("open_flow_step", home)


class TestFlowCommandRunsTheLoop(unittest.TestCase):
    """/flow announces the five steps, then hands over to the same router."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.shell = _StubShell(self.base)
        self.shell._match_cmd = lambda lowered, cmd: app_shell_module.AppShell._match_cmd(
            self.shell, lowered, cmd
        )
        self.shell._normalize_omnibar_cmd = lambda text: text.lower().strip()

    def tearDown(self):
        self.shell.deleteLater()
        self._tmp.cleanup()

    def _run(self, text="/flow"):
        with mock.patch.object(app_shell_module.QMessageBox, "information") as info:
            app_shell_module.AppShell._handle_omnibar_text(self.shell, text)
        return info

    def test_flow_announces_every_step_and_continues(self):
        personal_plan.create_item(self.base, "Late essay", due_date="2020-01-01", duration_minutes=40)
        info = self._run()
        info.assert_called_once()
        title, message = info.call_args[0][1], info.call_args[0][2]
        self.assertEqual(title, "Study loop")
        for step in study_flow.FLOW_STEPS:
            with self.subTest(step=step["key"]):
                self.assertIn(step["title"], message)
        self.assertIn("Late essay", message)
        self.assertEqual(self.shell.flow_steps, [study_flow.next_step(self.base)])

    def test_flow_reports_the_calm_case_too(self):
        info = self._run()
        self.assertIn("Plan your week", info.call_args[0][2])
        self.assertEqual(self.shell.flow_steps[0]["step"], "plan")

    def test_flow_is_not_a_prefix_match(self):
        self._run("/flowchart")
        self.assertEqual(self.shell.flow_steps, [], "only the exact command runs the loop")

    def test_a_running_pour_is_reported_not_restarted(self):
        focus_service.start_focus(self.base, minutes=25, label="Deep work")
        info = self._run()
        self.assertIn("Finish your pour", info.call_args[0][2])
        self.assertEqual(self.shell.flow_steps[0]["start"], False)


class TestBriefNoteKeepsTheLoop(_HomeBase):
    def test_save_as_note_writes_the_next_step_into_the_brief(self):
        personal_plan.create_item(self.base, "Late essay", due_date="2020-01-01")
        self.page.refresh()
        with mock.patch.object(pages_module.QMessageBox, "information"):
            self.page._save_brief_note()
        notes = [note for note in personal_service.list_notes(self.base) if note["category"] == "Brief"]
        self.assertEqual(len(notes), 1)
        self.assertIn("# ☕", notes[0]["content"])
        self.assertIn("## ▶ Next step", notes[0]["content"])
        self.assertIn("Late essay", notes[0]["content"])
        # A saved brief is a reflection artefact, not study material: the capture
        # counter must not start nagging about it.
        self.assertEqual(study_flow.build_flow(self.base)["counts"]["capture"], 0)


@unittest.skipUnless(sys.platform.startswith("win"), "offscreen smoke on dev machine")
class TestPlannerStudyHint(unittest.TestCase):
    """The planner's study label is the Study → Review hand-off."""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self._patched = []
        self.window = None

    def tearDown(self):
        for attr, value in self._patched:
            setattr(pw_module, attr, value)
        if self.window is not None:
            self.window.close()
        self._tmp.cleanup()

    def _window(self):
        class _FakeSiteView(QWidget):
            def __getattr__(self, name):
                return lambda *a, **k: None

        self._patched.append(("_build_site_view", pw_module.PersonalWindow._build_site_view))
        pw_module.PersonalWindow._build_site_view = lambda self: _FakeSiteView()
        self.window = pw_module.PersonalWindow(self.base, embedded=True)
        return self.window

    def test_running_pour_shows_the_clock_and_keeps_the_next_step_for_later(self):
        win = self._window()
        flashcard_service.add_card(self.base, "Q", "A")
        item = personal_plan.create_item(self.base, "Read ch.5", duration_minutes=25)
        study_session.start_for_item(self.base, item["id"])
        win._refresh_plan()
        label = win.lbl_plan_study.text()
        self.assertIn("Studying", label)
        self.assertIn("1 card(s) due", label)
        # While the pour runs, the next step *is* the pour — no second suggestion.
        self.assertNotIn("next:", label)

    def test_credited_pour_points_at_the_deck(self):
        import json
        import time

        win = self._window()
        flashcard_service.add_card(self.base, "Q", "A")
        item = personal_plan.create_item(self.base, "Read ch.5", duration_minutes=25)
        study_session.start_for_item(self.base, item["id"])
        path = focus_service.sessions_path(self.base)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        now = int(time.time())
        data["active"]["started_at"] = now - 1500
        data["active"]["ends_at"] = now - 1
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

        # One refresh is enough: credit_pending closes an expired pour itself.
        win._refresh_plan()
        label = win.lbl_plan_study.text()
        self.assertIn("Study credited", label)
        self.assertIn("25 min", label)
        self.assertIn("next: 🧠 Review 1 due card(s)", label)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["studied_minutes"], 25)

    def test_quiet_planner_shows_no_study_label(self):
        win = self._window()
        win._refresh_plan()
        self.assertEqual(win.lbl_plan_study.text(), "")

    def test_making_a_card_from_a_note_links_both_ways(self):
        win = self._window()
        note = personal_service.create_note(self.base, "OSI Model", "# OSI\n\n7 layers")
        win.make_flashcard_from_note("Layers?", "7", note["id"])
        cards = flashcard_service.load_cards(self.base)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["source_note_id"], note["id"])
        links = link_service.links_for(self.base, "note", note["id"])
        self.assertEqual(links["total"], 1, "the note's Related panel reads this edge")
        self.assertEqual(links["incoming"][0]["from_id"], cards[0]["id"])

    def test_making_a_card_without_a_note_creates_no_edge(self):
        win = self._window()
        win.make_flashcard_from_note("Standalone?", "Yes")
        self.assertEqual(link_service.load_links(self.base), [])


if __name__ == "__main__":
    unittest.main()
