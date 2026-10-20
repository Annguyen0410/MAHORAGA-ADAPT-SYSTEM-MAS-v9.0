"""Study sessions: pours started from planner entries credit their minutes once."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from litebrowser.core import prefs
from litebrowser.services import focus_service, personal_plan, study_session


class TestStudySessionService(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _expire_active_session(self, seconds: int = 1500):
        """Age the running pour into the past and let focus_service finish it."""
        path = focus_service.sessions_path(self.base)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        active = data["active"]
        now = int(time.time())
        active["started_at"] = now - seconds
        active["ends_at"] = now - 1
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        focus_service.focus_status(self.base)

    def test_item_session_credits_minutes_once(self):
        item = personal_plan.create_item(self.base, "Ôn chương 3", duration_minutes=25)
        session = study_session.start_for_item(self.base, item["id"])
        self.assertEqual(session["item_id"], item["id"])
        self.assertEqual(session["minutes"], 25)
        self.assertEqual(study_session.active_session(self.base)["item"]["id"], item["id"])

        self._expire_active_session(1500)
        first = study_session.credit_pending(self.base)
        self.assertEqual(first["credited"], 1)
        self.assertEqual(first["minutes"], 25)
        stored = personal_plan.load_plan(self.base)["items"][0]
        self.assertEqual(stored["studied_minutes"], 25)
        self.assertTrue(stored["last_studied_at"])

        second = study_session.credit_pending(self.base)
        self.assertEqual(second["credited"], 0)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["studied_minutes"], 25)

    def test_an_expired_pour_is_credited_without_a_status_poll(self):
        """Regression: minutes waited for the next focus_status() to be credited."""
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

        # No focus_status() call in between — credit_pending has to close the pour
        # it finds, or the planner label shows nothing after a session ends.
        summary = study_session.credit_pending(self.base)
        self.assertEqual(summary["credited"], 1)
        self.assertEqual(summary["minutes"], 25)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["studied_minutes"], 25)
        self.assertEqual(focus_service.focus_status(self.base)["running"], False)

    def test_credit_recovers_a_crash_before_journal_acknowledgement(self):
        item = personal_plan.create_item(self.base, "Recovery", duration_minutes=25)
        study_session.start_for_item(self.base, item["id"])
        self._expire_active_session(1500)
        with mock.patch.object(focus_service, "mark_credited", side_effect=OSError("disk busy")):
            with self.assertRaises(OSError):
                study_session.credit_pending(self.base)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["studied_minutes"], 25)
        self.assertEqual(study_session.credit_pending(self.base)["credited"], 0)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["studied_minutes"], 25)
        self.assertTrue(focus_service.focus_journal(self.base)[0]["credited"])

    def test_starting_a_new_pour_preserves_expired_credit(self):
        item = personal_plan.create_item(self.base, "First", duration_minutes=25)
        study_session.start_for_item(self.base, item["id"])
        path = focus_service.sessions_path(self.base)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        now = int(time.time())
        data["active"].update(started_at=now - 1500, ends_at=now - 1)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        focus_service.start_focus(self.base, 10, "Second")
        self.assertEqual(study_session.credit_pending(self.base)["minutes"], 25)
        self.assertEqual(focus_service.focus_journal(self.base)[0]["status"], "completed")

    def test_planner_read_does_not_make_every_item_look_edited(self):
        item = personal_plan.create_item(self.base, "Stable", updated_at="2025-01-01T00:00:00")
        personal_plan.create_item(self.base, "Unrelated")
        stored = next(row for row in personal_plan.load_plan(self.base)["items"] if row["id"] == item["id"])
        self.assertEqual(stored["updated_at"], "2025-01-01T00:00:00")
        changed = personal_plan.update_item(self.base, item["id"], title="Changed")
        self.assertNotEqual(changed["updated_at"], stored["updated_at"])

    def test_abandoned_session_is_not_credited(self):
        item = personal_plan.create_item(self.base, "Essay", duration_minutes=25)
        study_session.start_for_item(self.base, item["id"])
        # Abandoning the pour must not move the item's studied total, even
        # though the session sits in the journal with elapsed time on it.
        study_session.finish(self.base, complete=False)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["studied_minutes"], 0)
        self.assertEqual(study_session.credit_pending(self.base)["credited"], 0)

    def test_block_session_credits_the_linked_item(self):
        item = personal_plan.create_item(self.base, "Physics review", duration_minutes=50)
        block = personal_plan.create_time_block(
            self.base, "Tự học", personal_plan._today(), 540, item_id=item["id"]
        )
        session = study_session.start_for_block(self.base, block["id"])
        self.assertEqual(session["item_id"], item["id"])

        self._expire_active_session(1200)
        summary = study_session.credit_pending(self.base)
        self.assertEqual(summary["minutes"], 20)
        self.assertEqual(personal_plan.load_plan(self.base)["items"][0]["studied_minutes"], 20)

    def test_unknown_ids_are_a_no_op(self):
        self.assertIsNone(study_session.start_for_item(self.base, "nope"))
        self.assertIsNone(study_session.start_for_block(self.base, "nope"))
        self.assertEqual(study_session.credit_pending(self.base)["credited"], 0)

    def test_session_minutes_clamp_to_the_focus_window(self):
        item = personal_plan.create_item(self.base, "Marathon", duration_minutes=1440)
        session = study_session.start_for_item(self.base, item["id"])
        self.assertEqual(session["minutes"], study_session.MAX_SESSION_MINUTES)


if __name__ == "__main__":
    unittest.main()
