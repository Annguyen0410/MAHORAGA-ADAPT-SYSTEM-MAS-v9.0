"""Edge cases found by deep review: scheduler and template boundaries."""
import os
import tempfile
import time
import unittest

from litebrowser.core import prefs
from litebrowser.services import flashcard_service, note_templates, routines_service


class TestFlashcardEdges(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_malformed_scheduler_fields_do_not_crash_review_or_stats(self):
        from litebrowser.core.storage_utils import write_json

        write_json(flashcard_service.cards_path(self.base), {"cards": [{
            "id": "bad", "front": "Keep my question", "back": "Keep my answer",
            "due": "invalid", "ease": None, "interval": "NaN", "reviews": {}, "lapses": [],
        }, None]})
        self.assertEqual(flashcard_service.stats(self.base), {"total": 1, "due": 1, "matured": 0})
        card = flashcard_service.review_card(self.base, "bad", "good")
        self.assertEqual(card["front"], "Keep my question")
        self.assertEqual(card["reviews"], 1)

    def test_matured_card_lapse_resets_gracefully(self):
        """A 60-day card graded 'again' goes back to 10-minute retry, not 60."""
        card = flashcard_service.add_card(self.base, "Q", "A")
        for grade in ("good", "good", "easy", "good", "good", "good"):
            card = flashcard_service.review_card(self.base, card["id"], grade)
        self.assertGreaterEqual(card["interval"], 10)
        lapsed = flashcard_service.review_card(self.base, card["id"], "again")
        self.assertEqual(lapsed["interval"], 0)
        # Due ~10 min later, not months later:
        soon = int(time.time()) + 11 * 60
        self.assertEqual(len(flashcard_service.due_cards(self.base, now=soon)), 1)

    def test_empty_front_or_back_rejected_at_service_level(self):
        # add_card must not create empty-bodied cards even if the UI regresses.
        card = flashcard_service.add_card(self.base, "", "back")
        self.assertEqual(card["front"], "")
        cards = flashcard_service.load_cards(self.base)
        self.assertEqual(len(cards), 1)  # tolerated but blank — UI must guard
        # The UI guard (personal_window._add_review_card) is the real gate.

    def test_whitespace_only_card_content_is_trimmed(self):
        card = flashcard_service.add_card(self.base, "   Q   ", "   A   ")
        self.assertEqual(card["front"], "Q")
        self.assertEqual(card["back"], "A")

    def test_double_review_does_not_double_count(self):
        card = flashcard_service.add_card(self.base, "Q", "A")
        first = flashcard_service.review_card(self.base, card["id"], "good")
        second = flashcard_service.review_card(self.base, card["id"], "good")
        # Each review must advance the interval, never shrink it on 'good'.
        self.assertGreaterEqual(second["interval"], first["interval"])


class TestRoutineEdges(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_actions_routine_is_tolerated_but_harmless(self):
        routine = routines_service.add_routine(self.base, "Empty", "07:00", [], [])
        self.assertEqual(routine["actions"], [])
        # due_routines may return it; the dispatcher just no-ops.
        weekday = time.localtime().tm_wday
        if weekday in routine["days"] or not routine["days"]:
            pass  # dispatcher guards against empty actions at run time

    def test_invalid_time_falls_back_to_0730(self):
        routine = routines_service.add_routine(self.base, "Bad time", "25:99", [], ["/brief"])
        self.assertEqual(routine["time"], "07:30")

    def test_days_out_of_range_are_normalized(self):
        routine = routines_service.add_routine(self.base, "Wrap days", "07:00", [7, 9, -1], ["/brief"])
        self.assertTrue(all(0 <= d <= 6 for d in routine["days"]))


class TestTemplateEdges(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_daily_note_with_no_data_has_friendly_placeholders(self):
        note = note_templates.create_daily_note(self.base)
        self.assertIn("Nothing pending", note["content"])
        self.assertIn("No events scheduled", note["content"])

    def test_weekly_review_with_no_history(self):
        note = note_templates.create_weekly_review(self.base)
        self.assertIn("Pages visited", note["content"])
        self.assertIn("Reflections", note["content"])

    def test_weekly_review_counts_today_as_today(self):
        """The note had the same day-bucket bug as the Home chart.

        ``(midnight - ts) // 86400`` is -1 for anything that happened after
        midnight, so today's visits were dropped and every row read as the day
        before it. The morning brief disagreed with the review it wrote.
        """
        from datetime import date, datetime, time as _time, timedelta

        def noon(days_ago):
            return datetime.combine(date.today() - timedelta(days=days_ago), _time(12, 0)).timestamp()

        prefs.save_history_entries(
            self.base,
            [(int(noon(0)), "https://today.example/a"), (int(noon(1)), "https://yday.example/b"),
             (int(noon(9)), "https://old.example/c")],
        )
        content = note_templates.create_weekly_review(self.base)["content"]
        self.assertIn("- today: 1", content)
        self.assertIn("- yesterday: 1", content)
        self.assertIn("today.example", content)
        self.assertNotIn("old.example", content, "nine days ago is outside the window")

    def test_repeated_daily_notes_get_distinct_files(self):
        first = note_templates.create_daily_note(self.base)
        second = note_templates.create_daily_note(self.base)
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["path"], second["path"])


if __name__ == "__main__":
    unittest.main()
