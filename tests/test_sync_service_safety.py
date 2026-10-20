"""Regression checks for malformed self-hosted sync snapshots."""
import os
import tempfile
import unittest
from unittest import mock

from litebrowser.core import prefs
from litebrowser.services import flashcard_service, life_service, personal_plan, sync_service


class TestSyncServiceSafety(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_malformed_rows_are_ignored_without_crashing_pull(self):
        local = life_service.add_task(self.base, "Keep me")
        applied = sync_service._apply_bundle(
            self.base,
            {
                "tasks": ["invalid", {"id": "remote", "title": "Remote task"}],
                "events": [None],
                "boards": {"not": "a list"},
                "saved_pages": [42],
                "notes": ["invalid"],
                "bookmarks": ["invalid"],
                "history": ["invalid", ["not-a-time", "https://bad.example"], [123, "https://ok.example"]],
            },
        )

        self.assertEqual(applied["tasks"], 1)
        self.assertEqual(applied["events"], 0)
        self.assertEqual(applied["history"], 1)
        self.assertEqual({task["id"] for task in life_service.load_tasks(self.base)}, {local["id"], "remote"})

    def test_sync_reads_and_merges_before_publishing(self):
        life_service.add_task(self.base, "Local")
        calls = []

        def request(url, token, method="GET", payload=None):
            calls.append(method)
            if method == "GET":
                return True, {"kind": "snapshot", "tasks": [{"id": "remote", "title": "Remote"}]}, ""
            self.assertEqual({row["title"] for row in payload["tasks"]}, {"Local", "Remote"})
            return True, {}, ""

        with mock.patch.object(sync_service, "_request", side_effect=request):
            self.assertTrue(sync_service.sync_now(self.base, "http://localhost:12345", "fixture-token")[0])
        self.assertEqual(calls, ["GET", "POST"])

    def test_failed_pull_does_not_overwrite_the_remote_snapshot(self):
        with mock.patch.object(sync_service, "_request", return_value=(False, None, "unavailable")) as request:
            self.assertFalse(sync_service.sync_now(self.base, "http://localhost:12345", "fixture-token")[0])
        self.assertEqual(request.call_count, 1)

    def test_upsert_ignores_unhashable_ids_and_older_edits(self):
        local = {"id": "keep", "title": "New", "updated_at": "2026-09-01T10:00:00"}
        merged = sync_service._upsert([local], [
            {"id": {}, "title": "Invalid"}, {"id": [], "title": "Invalid"},
            {"id": "keep", "title": "Old", "updated_at": "2025-01-01T10:00:00"},
        ])
        self.assertEqual(merged, [local])

    def test_sparse_bundle_does_not_rewrite_unchanged_stores(self):
        with mock.patch.object(life_service, "save_events") as save:
            sync_service._apply_bundle(self.base, {"tasks": []})
        save.assert_not_called()

    def test_upsert_does_not_mutate_remote_rows(self):
        incoming = [{"id": "remote", "title": "Remote task"}]
        merged = sync_service._upsert([], incoming)
        merged[0]["title"] = "Changed locally"
        self.assertEqual(incoming[0]["title"], "Remote task")

    def test_planner_and_flashcards_sync_without_losing_local_rows(self):
        local_course = personal_plan.create_course(self.base, "Local course")
        local_item = personal_plan.create_item(self.base, "Local item", course_id=local_course["id"])
        local_card = flashcard_service.add_card(self.base, "Local Q", "Local A")

        applied = sync_service._apply_bundle(
            self.base,
            {
                "personal_plan": {
                    "items": [{"id": "remote-item", "title": "Remote item"}],
                    "courses": [{"id": "remote-course", "name": "Remote course"}],
                    "time_blocks": [],
                    "semester": {"name": "HK2"},
                },
                "flashcards": [
                    {"id": "remote-card", "front": "Remote Q", "back": "Remote A"},
                    "invalid",
                ],
            },
        )

        self.assertEqual(applied["planner"], 2)
        self.assertEqual(applied["flashcards"], 1)
        plan = personal_plan.load_plan(self.base)
        self.assertEqual(
            {item["id"] for item in plan["items"]}, {local_item["id"], "remote-item"}
        )
        self.assertEqual(
            {course["id"] for course in plan["courses"]}, {local_course["id"], "remote-course"}
        )
        self.assertEqual(plan["semester"]["name"], "HK2")
        cards = flashcard_service.load_cards(self.base)
        self.assertEqual({card["id"] for card in cards}, {local_card["id"], "remote-card"})

    def test_a_sparse_planner_pull_does_not_blank_the_semester(self):
        personal_plan.update_plan_settings(self.base, semester={"name": "HK1"})
        sync_service._apply_bundle(self.base, {"personal_plan": {"items": [], "semester": {"name": ""}}})
        self.assertEqual(personal_plan.load_plan(self.base)["semester"]["name"], "HK1")


if __name__ == "__main__":
    unittest.main()
