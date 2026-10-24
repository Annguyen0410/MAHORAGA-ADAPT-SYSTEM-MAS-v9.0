"""Regression checks for malformed self-hosted sync snapshots."""
import os
import tempfile
import unittest
from unittest import mock

from litebrowser.core import prefs
from litebrowser.services import (
    flashcard_service,
    life_service,
    personal_plan,
    personal_service,
    sync_service,
)


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


class TestNoteIdentity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _notes(self):
        return personal_service.list_notes(self.base)

    def test_an_incoming_note_keeps_its_stable_id(self):
        applied = sync_service._apply_bundle(
            self.base,
            {"notes": [{"id": "General/From phone.md", "title": "From phone", "content": "hello"}]},
        )
        self.assertEqual(applied["notes"], 1)
        self.assertEqual([note["id"].replace("\\", "/") for note in self._notes()], ["General/From phone.md"])
        # The next pull of the same snapshot is a no-op, not a second note.
        self.assertEqual(
            sync_service._apply_bundle(
                self.base,
                {"notes": [{"id": "General/From phone.md", "title": "From phone", "content": "hello"}]},
            )["notes"],
            0,
        )
        self.assertEqual(len(self._notes()), 1)

    def test_a_remote_rename_does_not_create_a_duplicate(self):
        note = personal_service.create_note(self.base, "Krebs cycle", "citrate")
        applied = sync_service._apply_bundle(
            self.base,
            {
                "notes": [
                    {
                        "id": note["id"],
                        "title": "Krebs cycle (renamed)",
                        "category": note["category"],
                        "content": "citrate",
                    }
                ]
            },
        )
        self.assertEqual(applied["notes"], 0)
        self.assertEqual([n["id"] for n in self._notes()], [note["id"]])

    def test_two_notes_with_the_same_title_in_different_categories_stay_distinct(self):
        sync_service._apply_bundle(
            self.base,
            {"notes": [{"id": "Math/Same.md", "title": "Same", "category": "Math", "content": "m"}]},
        )
        sync_service._apply_bundle(
            self.base,
            {"notes": [{"id": "Physics/Same.md", "title": "Same", "category": "Physics", "content": "p"}]},
        )
        notes = self._notes()
        self.assertEqual(
            {note["id"].replace("\\", "/") for note in notes}, {"Math/Same.md", "Physics/Same.md"}
        )

    def test_a_divergent_edit_keeps_both_texts_once(self):
        note = personal_service.create_note(self.base, "Krebs cycle", "local text")
        incoming = {
            "id": note["id"],
            "title": note["title"],
            "category": note["category"],
            "content": "remote text",
            "updated_at": "2000-01-01T00:00:00",
        }
        sync_service._apply_bundle(self.base, {"notes": [incoming]})
        titles = sorted(n["title"] for n in self._notes())
        self.assertEqual(titles, ["Krebs cycle", "Krebs cycle (other device)"])
        self.assertEqual(personal_service.read_note(self.base, note["id"])["content"], "local text")

        sync_service._apply_bundle(self.base, {"notes": [incoming]})
        self.assertEqual(len(self._notes()), 2, "a repeated pull must not add another conflict copy")

    def test_a_newer_remote_edit_updates_the_same_note(self):
        note = personal_service.create_note(self.base, "Krebs cycle", "local text")
        sync_service._apply_bundle(
            self.base,
            {
                "notes": [
                    {
                        "id": note["id"],
                        "title": note["title"],
                        "category": note["category"],
                        "content": "newer remote text",
                        "updated_at": "2099-01-01T00:00:00",
                    }
                ]
            },
        )
        self.assertEqual(len(self._notes()), 1)
        self.assertEqual(personal_service.read_note(self.base, note["id"])["content"], "newer remote text")

    def test_a_legacy_note_without_an_id_preserves_both_texts(self):
        personal_service.create_note(self.base, "Legacy", "local text")
        incoming = {"title": "Legacy", "category": "General", "content": "legacy remote"}
        sync_service._apply_bundle(self.base, {"notes": [incoming]})
        self.assertEqual(len(self._notes()), 2)
        sync_service._apply_bundle(self.base, {"notes": [incoming]})
        self.assertEqual(len(self._notes()), 2, "the legacy fallback is idempotent too")


class TestPullLimits(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_an_oversized_snapshot_is_refused_before_any_write(self):
        life_service.add_task(self.base, "Keep me")
        with mock.patch.object(sync_service, "MAX_BUNDLE_ROWS", 1), mock.patch.object(
            sync_service,
            "_request",
            return_value=(True, {"kind": "snapshot", "tasks": [{"id": "a"}, {"id": "b"}]}, ""),
        ):
            ok, message = sync_service.pull(self.base, "https://sync.example", "token")
        self.assertFalse(ok)
        self.assertIn("too large", message)
        self.assertEqual([task["title"] for task in life_service.load_tasks(self.base)], ["Keep me"])

    def test_endpoint_validation_is_explicit(self):
        for value in ("ftp://example.com", "https://user:pass@example.com", "https://example.com/?x=1", ""):
            with self.subTest(value=value):
                _, error = sync_service.validate_endpoint(value)
                self.assertTrue(error)
        base, error = sync_service.validate_endpoint("https://sync.example/mei/")
        self.assertEqual(error, "")
        self.assertEqual(base, "https://sync.example/mei")

    def test_cleartext_lan_endpoints_get_a_warning(self):
        self.assertIn("cleartext", sync_service.endpoint_warning("http://192.168.1.9:8901"))
        self.assertIn("cleartext", sync_service.endpoint_warning("http://sync.example"))
        self.assertEqual(sync_service.endpoint_warning("http://127.0.0.1:8901"), "")
        self.assertEqual(sync_service.endpoint_warning("https://sync.example"), "")


if __name__ == "__main__":
    unittest.main()
