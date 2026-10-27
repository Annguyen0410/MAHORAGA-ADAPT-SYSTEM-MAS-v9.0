"""The desk: Home's four blocks, the search that reaches your content, and the ritual.

Milestone 1.0.0.0 replaced Home's launcher-first layout with a **desk** — Today,
Due, Unfinished, Next — and made the omnibar reach your own records instead of
only app features. Three things have to hold, and each is pinned here:

* the *rules* live in ``desk_service`` (what counts as due, what counts as left
  open), so no UI can invent its own answer;
* the *page* must actually show four blocks, with the launcher grid collapsed —
  a block that is computed but never rendered is the failure a service test
  cannot see;
* the ritual must produce a real pour that the rest of the app already reads
  (focus journal), not a parallel timer nobody counts.
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import litebrowser  # noqa: F401 - activates the Qt compatibility shim

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget

from litebrowser.core import prefs
from litebrowser.services import (
    desk_service,
    flashcard_service,
    focus_service,
    life_service,
    personal_plan,
    personal_service,
    study_flow,
    study_ritual,
)
from litebrowser.ui.dialogs import shell_palette
from litebrowser.ui import personal_window as pw_module  # noqa: F401 - QtWebEngine first
from litebrowser.ui.shell import pages as pages_module

_app = QApplication.instance() or QApplication([])


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class _DeskTmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()


class TestDeskBlocks(_DeskTmp):
    def test_the_desk_always_answers_with_the_same_four_blocks(self):
        desk = desk_service.build_desk(self.base)
        self.assertEqual([block["key"] for block in desk["blocks"]], list(desk_service.DESK_BLOCKS))
        for block in desk["blocks"]:
            self.assertTrue(block["title"], block["key"])
            self.assertIsInstance(block["rows"], list)
            self.assertIn("count", block)
        # An empty profile is a valid desk, not an exception: every block says so.
        self.assertTrue(desk["headline"])
        self.assertEqual(desk_service.block_by_key(desk, "today")["count"], 0)
        self.assertTrue(desk_service.block_by_key(desk, "next")["empty"])

    def test_today_carries_the_plate_and_leaves_late_work_to_due(self):
        personal_plan.create_item(self.base, "Read chapter 4", scheduled_date=_today())
        personal_plan.create_item(self.base, "Essay draft", due_date=_today())
        life_service.add_task(self.base, "Buy ink", bucket="today")
        personal_plan.create_item(self.base, "Late lab report", due_date="2020-01-01")

        desk = desk_service.build_desk(self.base)
        today_titles = [row["title"] for row in desk_service.block_by_key(desk, "today")["rows"]]
        due_titles = [row["title"] for row in desk_service.block_by_key(desk, "due")["rows"]]

        self.assertIn("Read chapter 4", today_titles)
        self.assertIn("Buy ink", today_titles)
        self.assertNotIn("Late lab report", today_titles, "late work belongs in Due, not Today")
        self.assertIn("Late lab report", due_titles)
        late = [row for row in desk_service.block_by_key(desk, "due")["rows"] if row["title"] == "Late lab report"]
        self.assertEqual(len(late), 1)
        self.assertEqual(late[0]["marker"], "⚠ ", "late work is marked")
        self.assertIn("Essay draft", today_titles, "due today is still on today's plate")

    def test_due_only_holds_late_or_near_due_things(self):
        soon = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        far = (datetime.now() + timedelta(days=40)).strftime("%Y-%m-%d")
        personal_plan.create_item(self.base, "Landing this week", due_date=soon)
        personal_plan.create_item(self.base, "Next semester", due_date=far)

        due = desk_service.block_by_key(desk_service.build_desk(self.base), "due")
        titles = [row["title"] for row in due["rows"]]
        self.assertIn("Landing this week", titles)
        self.assertNotIn("Next semester", titles, "40 days out is not 'due'")

    def test_due_cards_show_up_as_a_runnable_row(self):
        flashcard_service.add_card(self.base, "Front", "Back")
        due = desk_service.block_by_key(desk_service.build_desk(self.base), "due")
        card_rows = [row for row in due["rows"] if row["kind"] == "due-cards"]
        self.assertEqual(len(card_rows), 1)
        self.assertIn("1 card due", card_rows[0]["title"])
        self.assertEqual(card_rows[0]["command"], "/review", "the row must be runnable, not decorative")
        self.assertEqual(due["count"], 1)

    def test_unfinished_holds_half_studied_items(self):
        item = personal_plan.create_item(self.base, "Organic chemistry", scheduled_date=_today())
        personal_plan.update_item(self.base, item["id"], studied_minutes=20)

        desk = desk_service.build_desk(self.base)
        open_titles = [row["title"] for row in desk_service.block_by_key(desk, "in_progress")["rows"]]
        self.assertIn("Organic chemistry", open_titles)
        # It is still on the plate too — "left open" is a state, not a move.
        self.assertIn("Organic chemistry", [row["title"] for row in desk_service.block_by_key(desk, "today")["rows"]])

    def test_next_block_mirrors_the_loop(self):
        personal_service.create_note(self.base, "Photosynthesis", "Light reactions")
        desk = desk_service.build_desk(self.base)
        next_block = desk_service.block_by_key(desk, "next")
        self.assertEqual(next_block["flow"], study_flow.next_step(self.base))
        self.assertTrue(next_block["rows"], "the next step is a row as well as a button")
        self.assertEqual(next_block["rows"][0]["title"], next_block["flow"]["label"])
        self.assertEqual(next_block["count"], 1)

    def test_headline_counts_what_the_blocks_hold(self):
        personal_plan.create_item(self.base, "Read chapter 4", scheduled_date=_today())
        personal_plan.create_item(self.base, "Late lab report", due_date="2020-01-01")
        desk = desk_service.build_desk(self.base)
        self.assertIn("1 on the plate", desk["headline"])
        self.assertIn("1 waiting", desk["headline"], "the late report is waiting, not on the plate")


class TestUniversalSearch(_DeskTmp):
    def test_a_note_and_a_card_are_found_by_content(self):
        personal_service.create_note(self.base, "Krebs cycle", "citrate, isocitrate")
        flashcard_service.add_card(self.base, "Krebs cycle input", "acetyl-CoA")
        rows = shell_palette.content_entries(self.base, "krebs")
        kinds = {row["payload"]["kind"] for row in rows}
        self.assertIn("note", kinds)
        self.assertIn("flashcard", kinds)
        self.assertTrue(all(row["kind"] == "content" for row in rows))

    def test_content_payloads_route_somewhere(self):
        personal_service.create_note(self.base, "Krebs cycle", "citrate")
        routed = {
            "note",
            "task",
            "event",
            "board",
            "board-node",
            "saved-page",
            "planner-item",
            "planner-block",
            "planner-course",
            "flashcard",
            "research_workspace",
        }
        for row in shell_palette.content_entries(self.base, "krebs"):
            self.assertIn(row["payload"]["kind"], routed, "a row the shell cannot route is a lie")

    def test_one_letter_does_not_dump_the_whole_profile(self):
        personal_service.create_note(self.base, "Krebs cycle", "citrate")
        self.assertEqual(shell_palette.content_entries(self.base, "k"), [])

    def test_named_research_workspaces_are_searchable_and_routable(self):
        from litebrowser.services import tab_sets

        workspace = tab_sets.add_tab_set(self.base, "workspace", "Chemistry field notes", [
            {"url": "https://example.test/lab", "title": "Lab reference"},
        ])
        rows = shell_palette.content_entries(self.base, "chemistry")
        research = next(row for row in rows if row["payload"]["kind"] == "research_workspace")
        self.assertEqual(research["title"], "Chemistry field notes")
        self.assertEqual(research["payload"]["id"], workspace["id"])

    def test_features_come_first_and_content_follows(self):
        personal_service.create_note(self.base, "review notes", "grading")
        features = shell_palette._build_entries(self.base)
        rows = shell_palette.search_entries(features, self.base, "review")
        self.assertEqual(rows[0]["kind"], "personal_page", "a feature word still lands on the feature")
        self.assertIn("content", [row["kind"] for row in rows])

    def test_search_entries_survives_a_broken_vault(self):
        features = shell_palette._build_entries(self.base)
        with mock.patch.object(personal_service, "list_notes", side_effect=RuntimeError("boom")):
            rows = shell_palette.search_entries(features, self.base, "notes")
        self.assertTrue(rows, "an unreadable note store must not empty the omnibar")


class TestStudyRitual(_DeskTmp):
    def test_a_pour_is_a_real_focus_session_with_the_cup_in_its_name(self):
        session = study_ritual.start_ritual(self.base, pour="ca-phe-sua", note="finish chapter 4")
        self.assertEqual(session["minutes"], 45, "the cup sets the pace")
        self.assertIn("Milk coffee", session["label"])
        self.assertIn("finish chapter 4", session["label"])
        # The ritual has to start the app's *own* pour, not a private timer: the
        # status strip, the focus journal and the weekly review all read this.
        running = focus_service.focus_status(self.base)
        self.assertTrue(running["running"])
        self.assertEqual(running["session"]["id"], session["id"])
        self.assertEqual(focus_service.stop_focus(self.base)["session"]["id"], session["id"])
        self.assertEqual(focus_service.focus_journal(self.base)[0]["id"], session["id"])

    def test_the_cup_is_remembered_and_a_typo_falls_back_to_it(self):
        study_ritual.start_ritual(self.base, pour="tra-dao")
        self.assertEqual(study_ritual.last_pour(self.base), "tra-dao")
        session = study_ritual.start_ritual(self.base, pour="khong-co-ly-nay")
        self.assertIn("Peach tea", session["label"])

    def test_minutes_can_override_the_cup_but_zero_means_the_cup(self):
        short = study_ritual.start_ritual(self.base, pour="bac-xiu", minutes=10)
        self.assertEqual(short["minutes"], 10)
        poured = study_ritual.start_ritual(self.base, pour="bac-xiu")
        self.assertEqual(poured["minutes"], study_ritual.pour_minutes("bac-xiu"))

    def test_the_ritual_line_names_the_sitting(self):
        session = study_ritual.start_ritual(self.base, pour="ca-phe-den")
        line = study_ritual.ritual_line(session)
        self.assertIn("25 minutes", line)
        self.assertIn("Black coffee", line)

    def test_every_pour_has_a_length_and_a_menu_line(self):
        for pour in study_ritual.pour_ids():
            self.assertGreater(study_ritual.pour_minutes(pour), 0)
            self.assertTrue(study_ritual.pour_display(pour))
        self.assertGreaterEqual(len(study_ritual.pour_ids()), 4)


class _StubOmnibar(QWidget):
    def __init__(self):
        super().__init__()
        self.text = ""

    def setText(self, text):
        self.text = text

    def setFocus(self):
        return None

    def setCursorPosition(self, _position):
        return None


class _StubShell(QWidget):
    """The shell surface Home touches while building and refreshing."""

    def __init__(self, base_dir):
        super().__init__()
        self.profile_dir = base_dir
        self.omnibar = _StubOmnibar()
        self.commands = []
        self.opened = []
        self.workspaces = []
        self.personal_page = _StubPersonal()
        self.browser_page = _StubBrowser()
        self.library_page = _StubLibrary()

    def switch_workspace(self, name):
        self.workspaces.append(name)
        return True

    def open_library_item(self, data):
        self.opened.append(data)

    def handle_omnibar(self):
        self.commands.append(self.omnibar.text)

    def refresh_shell(self, force_deep=False):
        return None

    def _flash_status(self, message):
        return None

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _StubPersonal(QWidget):
    def _switch_page(self, name):
        return None


class _StubBrowser(QWidget):
    pass


class _StubLibrary(QWidget):
    pass


class TestHomeDesk(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.shell = _StubShell(self.base)
        self.page = pages_module.HomeDashboardPage(self.shell)

    def tearDown(self):
        self.page.deleteLater()
        self.shell.deleteLater()
        self._tmp.cleanup()

    def test_home_shows_four_desk_blocks(self):
        self.assertEqual(list(self.page._desk_cards.keys()), list(desk_service.DESK_BLOCKS))
        for key, widgets in self.page._desk_cards.items():
            self.assertTrue(self.page.isAncestorOf(widgets["card"]), key)
            self.assertTrue(self.page.isAncestorOf(widgets["list"]), key)

    def test_the_launcher_grid_is_collapsed_by_default(self):
        self.assertTrue(self.page._more_panel.isHidden(), "a menu is not a home page")
        self.assertFalse(self.page.btn_all_features.isChecked())
        self.assertEqual(self.page.btn_all_features.text(), "☰ All features")

    def test_the_toggle_brings_the_launcher_back(self):
        self.page.btn_all_features.setChecked(True)
        self.assertFalse(self.page._more_panel.isHidden())
        self.page.btn_all_features.setChecked(False)
        self.assertTrue(self.page._more_panel.isHidden())

    def test_home_layout_preferences_hide_reorder_and_resize_cards(self):
        prefs.save_pref(self.base, "home_dashboard", {
            "order": ["due", "next", "today", "in_progress"],
            "visible": ["due", "next"],
            "size": "compact",
        })
        self.page._apply_home_preferences()
        self.assertEqual(
            [widget.property("deskBlock") for widget in self.page._desk_grid._widgets],
            ["due", "next", "today", "in_progress"],
        )
        self.assertFalse(self.page._desk_cards["due"]["card"].isHidden())
        self.assertFalse(self.page._desk_cards["today"]["card"].isVisible())
        self.assertEqual(self.page._desk_cards["due"]["list"].minimumHeight(), 76)

    def test_the_blocks_render_what_the_service_reports(self):
        personal_plan.create_item(self.base, "Read chapter 4", scheduled_date=_today())
        personal_plan.create_item(self.base, "Late lab report", due_date="2020-01-01")
        self.page.refresh()
        self.assertEqual(self.page._desk_cards["today"]["badge"].text(), "1")
        self.assertEqual(self.page._desk_cards["due"]["badge"].text(), "1")
        rows = [
            self.page._desk_cards["due"]["list"].item(index)
            for index in range(self.page._desk_cards["due"]["list"].count())
        ]
        routed = [row.data(Qt.UserRole) for row in rows if isinstance(row.data(Qt.UserRole), dict)]
        self.assertIn("planner-item", [row.get("kind") for row in routed])

    def test_a_desk_row_opens_where_the_item_lives(self):
        personal_service.create_note(self.base, "Krebs cycle", "citrate")
        self.page.refresh()
        listing = self.page._desk_cards["next"]["list"]
        # The loop's next step for a fresh note is a card for it: the row carries
        # the entity (kind + id) the shell already knows how to open.
        target = None
        for index in range(listing.count()):
            data = listing.item(index).data(Qt.UserRole)
            if isinstance(data, dict) and data.get("kind") and data.get("id"):
                target = (listing.item(index), data)
                break
        self.assertIsNotNone(target, "the next-step row must carry a routable id")
        self.page._open_desk_row(target[0])
        self.assertEqual(self.shell.opened, [target[1]])

    def test_a_command_row_runs_the_command(self):
        flashcard_service.add_card(self.base, "Front", "Back")
        self.page.refresh()
        listing = self.page._desk_cards["due"]["list"]
        target = None
        for index in range(listing.count()):
            item = listing.item(index)
            data = item.data(Qt.UserRole)
            if isinstance(data, dict) and data.get("command"):
                target = item
                break
        self.assertIsNotNone(target, "the due-cards row should carry a command")
        self.page._open_desk_row(target)
        self.assertEqual(self.shell.commands, ["/review"])

    def test_the_next_step_explains_instead_of_repeating_its_action(self):
        personal_service.create_note(self.base, "Krebs cycle", "citrate")
        self.page.refresh()
        listing = self.page._desk_cards["next"]["list"]
        row_text = "\n".join(listing.item(i).text() for i in range(listing.count()))
        self.assertIn("A captured note has no flashcards yet", row_text)
        self.assertNotIn("Turn “Krebs cycle” into cards", row_text, "the button already says that")
        self.assertIn("Krebs cycle", self.page.btn_desk_continue.text())

    def test_zero_metrics_stay_quiet_and_nonzero_ones_speak_up(self):
        self.page.refresh()
        value = self.page._stat_tiles["task"]._value
        self.assertTrue(value.property("quiet"))
        life_service.add_task(self.base, "One more thing")
        self.page.refresh()
        self.assertFalse(value.property("quiet"))

    def test_empty_research_desk_is_a_sentence_not_an_empty_box(self):
        self.page.refresh()
        self.assertIn("No active research desk", self.page.lbl_research_workspace.text())
        self.assertTrue(self.page.research_items.isHidden())
        self.assertTrue(self.page.btn_research_resume.isHidden())
        self.assertTrue(self.page.btn_research_capture.isEnabled())

    def test_the_study_session_button_opens_the_ritual(self):
        from litebrowser.ui.dialogs import study_ritual as ritual_dialog

        with mock.patch.object(ritual_dialog, "show_study_ritual", return_value={"id": "x"}) as opened:
            self.page.btn_desk_ritual.click()
        self.assertTrue(opened.called)
        desk = opened.call_args[0][1]
        self.assertEqual([block["key"] for block in desk["blocks"]], list(desk_service.DESK_BLOCKS))


if __name__ == "__main__":
    unittest.main()
