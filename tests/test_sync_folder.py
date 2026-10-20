"""Folder sync: two machines, one folder, and nothing lost in between.

This is the suite that decides whether folder sync is allowed to exist. Every
test here is a promise made to someone who is about to put their notes, their
plan and their deck through it:

* a first sync **publishes**, it does not "merge into" anything;
* a delete travels, and a delete can never eat an edit made elsewhere;
* when both machines edited the same record, both versions survive — and the
  records nobody touched are not rewritten on the way;
* nothing is written before a snapshot exists, and ``compute()`` writes nothing
  at all;
* a file that is not ours (or is from a newer Mei) is refused with the profile
  untouched;
* two machines reach the same state and then stop rewriting the shared file.

Two profiles in one process stand in for two machines; the folder is a third
directory. The 3-way baseline, the per-store policies and the volatile-key rules
all live in ``services/sync_folder.py``.
"""
import json
import os
import tempfile
import unittest
from unittest import mock
from datetime import datetime

from litebrowser.core import prefs
from litebrowser.services import (
    flashcard_service,
    life_service,
    personal_plan,
    personal_service,
    sync_folder,
)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class _TwoMachines(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.folder = os.path.join(self.root, "shared")
        os.makedirs(self.folder, exist_ok=True)
        self.a = prefs.ensure_profile_layout(os.path.join(self.root, "machine-a"))
        self.b = prefs.ensure_profile_layout(os.path.join(self.root, "machine-b"))
        for base in (self.a, self.b):
            sync_folder.set_folder(base, self.folder)

    def tearDown(self):
        self._tmp.cleanup()

    # ----- helpers -----
    def _sync(self, base, apply=True):
        return sync_folder.sync(base, apply=apply)

    def _payload(self, base=None):
        return sync_folder.read_payload(base or self.a)

    def _tasks(self, base):
        return sorted(task.get("title", "") for task in life_service.load_tasks(base))

    def _notes(self, base):
        return sorted(note.get("title", "") for note in personal_service.list_notes(base))

    def _note_titles(self, base, title):
        return [note for note in personal_service.list_notes(base) if note.get("title") == title]

    def _backup_dirs(self, base):
        root = os.path.join(base, "backups")
        if not os.path.isdir(root):
            return []
        return sorted(name for name in os.listdir(root) if name.startswith(sync_folder.BACKUP_PREFIX))


class TestPublishing(_TwoMachines):
    def test_a_first_sync_publishes_and_changes_nothing_locally(self):
        life_service.add_task(self.a, "Buy ink", bucket="today")
        personal_plan.create_item(self.a, "Read chapter 4", scheduled_date=_today())
        flashcard_service.add_card(self.a, "Front", "Back")
        personal_service.create_note(self.a, "Krebs cycle", "citrate")

        report = self._sync(self.a)

        self.assertTrue(report["applied"])
        self.assertEqual(report["changes"], [], "a first publish must not look like a merge")
        self.assertEqual(self._tasks(self.a), ["Buy ink"])
        self.assertTrue(os.path.isfile(sync_folder.payload_path(self.a)))
        records = self._payload()["stores"]["tasks"]["records"]
        self.assertIn("Buy ink", [row.get("title") for row in records.values()])
        self.assertGreaterEqual(report["summary"]["tasks"]["kept"], 1)
        self.assertEqual(self._backup_dirs(self.a), [], "publishing writes no store, so no snapshot is owed")

    def test_a_second_machine_pulls_what_the_first_published(self):
        life_service.add_task(self.a, "Buy ink")
        personal_plan.create_item(self.a, "Read chapter 4", scheduled_date=_today())
        flashcard_service.add_card(self.a, "Front", "Back")
        personal_service.create_note(self.a, "Krebs cycle", "citrate")
        self._sync(self.a)

        report = self._sync(self.b)

        self.assertEqual(self._tasks(self.b), ["Buy ink"])
        self.assertEqual(self._notes(self.b), ["Krebs cycle"])
        self.assertEqual(len(flashcard_service.load_cards(self.b)), 1)
        self.assertEqual(len(personal_plan.load_plan(self.b)["items"]), 1)
        self.assertEqual(report["summary"]["tasks"]["added"], 1)
        self.assertEqual(report["summary"]["notes"]["added"], 1)


class TestEditsAndDeletes(_TwoMachines):
    def test_an_edit_travels_both_ways(self):
        life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        self._sync(self.b)

        rows = life_service.load_tasks(self.b)
        rows[0]["title"] = "Buy black ink"
        life_service.save_tasks(self.b, rows)
        self._sync(self.b)

        report = self._sync(self.a)
        self.assertEqual(self._tasks(self.a), ["Buy black ink"])
        self.assertEqual(report["summary"]["tasks"]["updated"], 1)

    def test_a_delete_travels_as_a_tombstone(self):
        task = life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        self._sync(self.b)

        self.assertTrue(life_service.remove_task(self.a, task["id"]))
        self._sync(self.a)
        self.assertNotIn(task["id"], self._payload()["stores"]["tasks"]["records"], "the tombstone is published")

        report = self._sync(self.b)
        self.assertEqual(self._tasks(self.b), [])
        self.assertEqual(report["summary"]["tasks"]["deleted"], 1)

    def test_a_delete_never_eats_an_edit(self):
        task = life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        self._sync(self.b)

        life_service.remove_task(self.a, task["id"])
        rows = life_service.load_tasks(self.b)
        rows[0]["title"] = "Buy black ink"
        life_service.save_tasks(self.b, rows)
        self._sync(self.b)

        report = self._sync(self.a)
        self.assertEqual(self._tasks(self.a), ["Buy black ink"], "the edit comes back instead of disappearing")
        self.assertEqual(report["summary"]["tasks"]["conflicts"], 1)
        # …and the machine that deleted it does not keep deleting it afterwards.
        self.assertFalse(self._sync(self.a)["applied"])
        self.assertFalse(self._sync(self.b)["applied"])
        self.assertEqual(self._tasks(self.b), ["Buy black ink"])


class TestConflicts(_TwoMachines):
    def test_two_edits_keep_both_versions_and_touch_nothing_else(self):
        personal_service.create_note(self.a, "Krebs cycle", "citrate")
        personal_service.create_note(self.a, "Glycolysis", "glucose")
        personal_service.create_note(self.a, "Photosynthesis", "light reactions")
        self._sync(self.a)
        self._sync(self.b)

        for base, text in ((self.a, "citrate, isocitrate"), (self.b, "citrate and water")):
            note = [n for n in personal_service.list_notes(base) if n["title"] == "Krebs cycle"][0]
            personal_service.update_note(base, note["id"], text, note["category"])
        self._sync(self.a)

        report = self._sync(self.b)
        titles = self._notes(self.b)
        self.assertIn("Krebs cycle", titles)
        self.assertIn("Krebs cycle (other machine)", titles, "the other machine's version survives")
        self.assertEqual(report["summary"]["notes"]["conflicts"], 1)
        self.assertEqual(report["summary"]["notes"]["deleted"], 0)
        self.assertIn("Glycolysis", titles, "a conflict must not rewrite the rest of the store")
        self.assertIn("Photosynthesis", titles)
        glyph = [n for n in personal_service.list_notes(self.b) if n["title"] == "Glycolysis"][0]
        self.assertIn("glucose", glyph["content"])

    def test_a_card_conflict_keeps_the_local_copy_without_duplicating(self):
        card = flashcard_service.add_card(self.a, "Question", "Answer")
        self._sync(self.a)
        self._sync(self.b)

        # Two *different* grades, so the two machines really diverge: the same
        # grade from the same starting state would be two identical records.
        flashcard_service.review_card(self.a, card["id"], "easy")
        flashcard_service.review_card(self.b, card["id"], "hard")
        self._sync(self.a)

        report = self._sync(self.b)
        self.assertEqual(len(flashcard_service.load_cards(self.b)), 1, "the same question must not appear twice")
        self.assertEqual(report["summary"]["cards"]["conflicts"], 1)


class TestSafety(_TwoMachines):
    def test_failed_publication_does_not_advance_the_baseline(self):
        life_service.add_task(self.a, "Do not lose this")
        with mock.patch.object(sync_folder, "_write_payload", return_value=False):
            with self.assertRaises(OSError):
                sync_folder.sync(self.a)
        self.assertFalse(os.path.exists(sync_folder.state_path(self.a)))
        self.assertTrue(sync_folder.sync(self.a)["payload_written"])
        sync_folder.sync(self.b)
        self.assertEqual(life_service.load_tasks(self.b)[0]["title"], "Do not lose this")

    def test_invalid_schema_version_is_a_controlled_error(self):
        path = sync_folder.payload_path(self.a)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"kind": sync_folder.PAYLOAD_KIND, "version": "invalid"}, handle)
        with self.assertRaises(sync_folder.SyncFormatError):
            sync_folder.sync(self.a)

    def test_a_snapshot_holds_the_state_before_the_merge(self):
        life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        self._sync(self.b)
        rows = life_service.load_tasks(self.b)
        rows[0]["title"] = "Buy black ink"
        life_service.save_tasks(self.b, rows)
        self._sync(self.b)

        self._sync(self.a)

        backups = self._backup_dirs(self.a)
        self.assertTrue(backups, "writing a store requires a snapshot first")
        with open(os.path.join(self.a, "backups", backups[-1], "tasks.json"), encoding="utf-8") as handle:
            snapshot = json.load(handle)
        self.assertEqual(snapshot["records"][0]["title"], "Buy ink", "the snapshot is the *before* picture")

    def test_compute_previews_without_writing_anything(self):
        life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        self._sync(self.b)
        rows = life_service.load_tasks(self.b)
        rows[0]["title"] = "Buy black ink"
        life_service.save_tasks(self.b, rows)
        self._sync(self.b)

        before_tasks = life_service.load_tasks(self.a)
        before_payload = self._payload()
        before_backups = self._backup_dirs(self.a)

        report = sync_folder.compute(self.a)

        self.assertEqual([change["action"] for change in report["changes"] if change["store"] == "tasks"], ["updated"])
        self.assertFalse(report["applied"])
        self.assertEqual(life_service.load_tasks(self.a), before_tasks)
        self.assertEqual(self._payload(), before_payload)
        self.assertEqual(self._backup_dirs(self.a), before_backups)

    def test_a_repeat_sync_is_a_no_op(self):
        life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        payload = self._payload()

        report = self._sync(self.a)

        self.assertFalse(report["applied"])
        self.assertEqual(report["reason"], "nothing-new")
        self.assertEqual(self._payload()["payload_id"], payload["payload_id"], "the shared file is not rewritten")
        self.assertEqual(self._backup_dirs(self.a), [])

    def test_a_foreign_file_is_refused_and_nothing_changes(self):
        life_service.add_task(self.a, "Buy ink")
        path = sync_folder.payload_path(self.a)
        for junk in ('{"kind": "something-else", "version": 1}', "{not json at all"):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(junk)
            with self.assertRaises(sync_folder.SyncFormatError):
                self._sync(self.a)
            self.assertEqual(self._tasks(self.a), ["Buy ink"])
            self.assertEqual(self._backup_dirs(self.a), [])

    def test_a_payload_from_a_newer_mei_is_refused(self):
        life_service.add_task(self.a, "Buy ink")
        with open(sync_folder.payload_path(self.a), "w", encoding="utf-8") as handle:
            json.dump({"kind": sync_folder.PAYLOAD_KIND, "version": 99, "stores": {}}, handle)
        with self.assertRaises(sync_folder.SyncFormatError):
            self._sync(self.a)
        self.assertEqual(self._tasks(self.a), ["Buy ink"])

    def test_a_folder_inside_the_profile_is_called_out(self):
        sync_folder.set_folder(self.a, os.path.join(self.a, "somewhere"))
        report = sync_folder.compute(self.a)
        self.assertTrue(any("inside this profile" in note for note in report["warnings"]))

    def test_turning_the_folder_off_stops_merging(self):
        life_service.add_task(self.a, "Buy ink")
        sync_folder.set_folder(self.a, "")
        report = self._sync(self.a)
        self.assertFalse(report["enabled"])
        self.assertFalse(report["applied"])
        self.assertFalse(sync_folder.status(self.a)["enabled"])


class TestConvergence(_TwoMachines):
    def test_planner_timestamp_churn_is_not_a_change(self):
        personal_plan.create_item(self.a, "Read chapter 4", scheduled_date=_today())
        self._sync(self.a)

        # Saving the plan again is what every unrelated edit does, and it stamps
        # ``updated_at = now`` on every record.
        personal_plan.save_plan(self.a, personal_plan.load_plan(self.a))

        self.assertFalse(self._sync(self.a)["applied"], "a rewritten clock is not a change")

    def test_two_machines_converge_and_stop_rewriting_the_file(self):
        life_service.add_task(self.a, "Buy ink", bucket="today")
        personal_service.create_note(self.a, "Krebs cycle", "citrate")
        flashcard_service.add_card(self.a, "Front", "Back")
        personal_plan.create_item(self.a, "Read chapter 4", scheduled_date=_today())

        self._sync(self.a)
        self._sync(self.b)

        payload_id = self._payload()["payload_id"]
        self.assertFalse(self._sync(self.b)["applied"], "B has nothing new to say after pulling")
        self.assertFalse(self._sync(self.a)["applied"], "A has nothing new either")
        self.assertEqual(self._payload()["payload_id"], payload_id, "neither machine rewrote the shared file")

        self.assertEqual(self._tasks(self.b), ["Buy ink"])
        self.assertEqual(len(flashcard_service.load_cards(self.b)), 1)
        self.assertEqual(self._notes(self.b), ["Krebs cycle"])
        self.assertEqual(len(personal_plan.load_plan(self.b)["items"]), 1)

    def test_the_shared_file_names_the_product_and_its_version(self):
        life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        payload = self._payload()
        self.assertEqual(payload["kind"], sync_folder.PAYLOAD_KIND)
        self.assertEqual(payload["version"], sync_folder.PAYLOAD_VERSION)
        self.assertEqual(payload["product"], "mei")
        self.assertTrue(payload["device"])

    def test_the_report_reads_like_a_sentence(self):
        life_service.add_task(self.a, "Buy ink")
        self._sync(self.a)
        self._sync(self.b)
        rows = life_service.load_tasks(self.b)
        rows[0]["title"] = "Buy black ink"
        life_service.save_tasks(self.b, rows)
        self._sync(self.b)

        report = self._sync(self.a)
        line = sync_folder.summary_line(report)
        self.assertIn("Synced", line)
        self.assertIn("updated", line)
        self.assertIn("Folder sync is off", sync_folder.summary_line({"enabled": False}))


if __name__ == "__main__":
    unittest.main()
