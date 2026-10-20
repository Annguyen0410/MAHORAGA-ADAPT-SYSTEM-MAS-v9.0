"""Profile backup: JSON and ZIP bundle."""
import json
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from litebrowser.core import prefs
from litebrowser.services import flashcard_service, history_service, personal_plan, personal_service


class TestBackupExport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_includes_session_state_vault_files(self):
        personal_service.create_note(self.base, "T", "b", category="C")
        payload = history_service.export_profile_payload(self.base)
        self.assertEqual(payload.get("backup_format_version"), 3)
        self.assertIn("session_state", payload)
        self.assertIsInstance(payload["session_state"], dict)
        self.assertIn("tabs", payload["session_state"])
        self.assertIn("vault_files", payload)
        self.assertIsInstance(payload["vault_files"], list)

    def test_zip_export_empty_vault_files_in_json(self):
        personal_service.create_note(self.base, "N", "body", category="X")
        zpath = os.path.join(self._tmp.name, "b.zip")
        self.assertTrue(history_service.export_profile_to_zip(self.base, zpath))
        with zipfile.ZipFile(zpath, "r") as zf:
            names = zf.namelist()
            self.assertIn(history_service.PROFILE_ZIP_JSON_MEMBER, names)
            raw = zf.read(history_service.PROFILE_ZIP_JSON_MEMBER).decode("utf-8")
        data = json.loads(raw)
        self.assertEqual(data.get("backup_format_version"), 4)
        self.assertEqual(data.get("backup_bundle"), "zip")
        self.assertEqual(data.get("vault_files"), [])

    def test_zip_roundtrip_restores_vault_file_and_note(self):
        vault = prefs.vault_path(self.base)
        os.makedirs(os.path.join(vault, "misc"), exist_ok=True)
        with open(os.path.join(vault, "misc", "blob.bin"), "wb") as f:
            f.write(b"\x00\x01\xFE")
        personal_service.create_note(self.base, "Keep", "hello", category="Cat")

        zpath = os.path.join(self._tmp.name, "full.zip")
        self.assertTrue(history_service.export_profile_to_zip(self.base, zpath))

        dest = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile2"))
        self.assertTrue(history_service.import_profile_from_path(dest, zpath))

        blob_path = os.path.join(prefs.vault_path(dest), "misc", "blob.bin")
        self.assertTrue(os.path.isfile(blob_path))
        with open(blob_path, "rb") as f:
            self.assertEqual(f.read(), b"\x00\x01\xFE")
        notes = personal_service.list_notes(dest)
        self.assertTrue(any(n.get("title") == "Keep" for n in notes))

    def test_zip_with_browser_data_roundtrip(self):
        from litebrowser.core import app_paths

        bd = app_paths.browser_data_path(self.base)
        os.makedirs(os.path.join(bd, "sub"), exist_ok=True)
        with open(os.path.join(bd, "sub", "marker.txt"), "w", encoding="utf-8") as f:
            f.write("webengine-test")

        zpath = os.path.join(self._tmp.name, "with-bd.zip")
        self.assertTrue(
            history_service.export_profile_to_zip(self.base, zpath, include_browser_data=True)
        )

        dest = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile-bd"))
        self.assertTrue(history_service.import_profile_from_path(dest, zpath))

        marker = os.path.join(app_paths.browser_data_path(dest), "sub", "marker.txt")
        self.assertTrue(os.path.isfile(marker))
        with open(marker, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "webengine-test")

    def test_browser_data_restore_rolls_back_if_final_swap_is_blocked(self):
        """A blocked directory rename must leave the pre-import profile intact."""
        from litebrowser.core import app_paths

        source_data = app_paths.browser_data_path(self.base)
        with open(os.path.join(source_data, "new.txt"), "w", encoding="utf-8") as f:
            f.write("new")
        zpath = os.path.join(self._tmp.name, "browser-data.zip")
        self.assertTrue(history_service.export_profile_to_zip(self.base, zpath, include_browser_data=True))

        dest = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile-swap-rollback"))
        dest_data = app_paths.browser_data_path(dest)
        old_marker = os.path.join(dest_data, "old.txt")
        with open(old_marker, "w", encoding="utf-8") as f:
            f.write("old")

        real_replace = history_service.os.replace

        def block_staging_swap(src, target):
            if (
                os.path.abspath(target) == os.path.abspath(dest_data)
                and os.path.basename(os.path.abspath(src)).startswith(".BrowserData.import-")
            ):
                raise PermissionError("simulated transient lock")
            return real_replace(src, target)

        with zipfile.ZipFile(zpath, "r") as zf, mock.patch.object(
            history_service.os, "replace", side_effect=block_staging_swap
        ):
            self.assertFalse(history_service._import_browser_data_from_zip(dest, zf))

        self.assertTrue(os.path.isfile(old_marker))
        self.assertFalse(os.path.exists(os.path.join(dest_data, "new.txt")))

    def test_zip_roundtrip_restores_planner_and_flashcards(self):
        course = personal_plan.create_course(self.base, "Giải tích", code="MA101")
        personal_plan.create_item(
            self.base, "Ôn chương 3", kind="assignment", course_id=course["id"], due_date="2026-10-01"
        )
        personal_plan.create_time_block(self.base, "Tự học", "2026-10-01", 540)
        flashcard_service.add_card(self.base, "Đạo hàm của sin?", "cos")

        zpath = os.path.join(self._tmp.name, "study.zip")
        self.assertTrue(history_service.export_profile_to_zip(self.base, zpath))

        dest = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile-study"))
        self.assertTrue(history_service.import_profile_from_path(dest, zpath))

        plan = personal_plan.load_plan(dest)
        self.assertEqual([item["title"] for item in plan["items"]], ["Ôn chương 3"])
        self.assertEqual([course["name"] for course in plan["courses"]], ["Giải tích"])
        self.assertEqual([block["title"] for block in plan["time_blocks"]], ["Tự học"])
        self.assertEqual([card["front"] for card in flashcard_service.load_cards(dest)], ["Đạo hàm của sin?"])

    def test_import_of_an_older_backup_keeps_existing_study_data(self):
        """A v<=3 backup has no planner/flashcard keys; importing it must not
        wipe the study data this build already has."""
        personal_plan.create_item(self.base, "Keep me")
        flashcard_service.add_card(self.base, "Q", "A")
        payload = history_service.export_profile_payload(self.base)
        payload.pop("personal_plan")
        payload.pop("flashcards")

        dest = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile-old"))
        personal_plan.create_item(dest, "Survives")
        flashcard_service.add_card(dest, "Old", "Card")
        self.assertTrue(history_service.import_profile_payload(dest, payload))

        self.assertEqual(
            [item["title"] for item in personal_plan.load_plan(dest)["items"]], ["Survives"]
        )
        self.assertEqual([card["front"] for card in flashcard_service.load_cards(dest)], ["Old"])

    def test_empty_and_malformed_backups_do_not_change_live_data(self):
        from litebrowser.services import life_service

        note = personal_service.create_note(self.base, "Keep", "Original")
        task = life_service.add_task(self.base, "Keep task")
        for payload in ({}, {"tasks": [], "notes": [None]}, {"prefs": {}, "notes": [{"id": "General/a.md", "content": {}}]}):
            self.assertFalse(history_service.import_profile_payload(self.base, payload))
            self.assertEqual(personal_service.read_note(self.base, note["id"])["content"], "Original")
            self.assertEqual(life_service.load_tasks(self.base)[0]["id"], task["id"])

    def test_sparse_backup_preserves_unsupplied_collections(self):
        from litebrowser.services import life_service

        note = personal_service.create_note(self.base, "Keep", "Original")
        life_service.add_task(self.base, "Replaced")
        prefs.save_pref(self.base, "custom", "keep")
        self.assertTrue(history_service.import_profile_payload(self.base, {"tasks": []}))
        self.assertEqual(life_service.load_tasks(self.base), [])
        self.assertEqual(personal_service.read_note(self.base, note["id"])["content"], "Original")
        self.assertEqual(prefs.get_pref(self.base, "custom"), "keep")

    def test_failed_import_rolls_back_previous_store_writes(self):
        from litebrowser.services import life_service

        life_service.add_task(self.base, "Original task")
        note = personal_service.create_note(self.base, "Keep", "Original note")
        prefs.save_pref(self.base, "custom", "original")
        with mock.patch.object(life_service, "save_tasks", side_effect=OSError("disk full")):
            self.assertFalse(history_service.import_profile_payload(self.base, {
                "prefs": {"custom": "changed"}, "tasks": [],
                "notes": [{"id": "General/new.md", "content": "Replacement"}],
            }))
        self.assertEqual(prefs.get_pref(self.base, "custom"), "original")
        self.assertEqual(life_service.load_tasks(self.base)[0]["title"], "Original task")
        self.assertEqual(personal_service.read_note(self.base, note["id"])["content"], "Original note")

    def test_failed_export_does_not_replace_an_existing_backup(self):
        zpath = os.path.join(self._tmp.name, "keep.zip")
        with open(zpath, "wb") as handle:
            handle.write(b"previous backup")
        with mock.patch.object(history_service, "_add_vault_tree_to_zip", side_effect=OSError("read failure")):
            self.assertFalse(history_service.export_profile_to_zip(self.base, zpath))
        with open(zpath, "rb") as handle:
            self.assertEqual(handle.read(), b"previous backup")

    def test_import_rejects_path_traversal_note_ids(self):
        """A crafted backup must not write outside the notes dir (v6.5 fix)."""
        payload = history_service.export_profile_payload(self.base)
        payload["notes"] = [
            {"id": "../escaped.md", "content": "evil"},
            {"id": "C:/Windows/temp-evil.md", "content": "evil2"},
            {"id": "ok/note.md", "content": "fine"},
        ]
        zpath = os.path.join(self._tmp.name, "evil.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(history_service.PROFILE_ZIP_JSON_MEMBER, json.dumps(payload, ensure_ascii=False))

        dest = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile-traversal"))
        self.assertTrue(history_service.import_profile_from_path(dest, zpath))

        notes_root = os.path.abspath(personal_service.notes_dir(dest))
        escaped = os.path.abspath(os.path.join(notes_root, "..", "escaped.md"))
        self.assertFalse(os.path.isfile(escaped))
        self.assertFalse(os.path.isfile(os.path.join(notes_root, "escaped.md")))
        self.assertFalse(os.path.isfile(os.path.join(notes_root, "C:", "Windows", "temp-evil.md")))
        good = os.path.join(notes_root, "ok", "note.md")
        self.assertTrue(os.path.isfile(good))
        with open(good, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "fine")


if __name__ == "__main__":
    unittest.main()
