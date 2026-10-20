"""Profile RLock + atomic writes: concurrent mutations must not drop records."""
from __future__ import annotations

import concurrent.futures
import os
import tempfile
import unittest

from litebrowser.core import prefs
from litebrowser.services import flashcard_service, focus_service, life_service, personal_plan, study_session
from litebrowser.core.storage_utils import write_json
from litebrowser.services.android_bridge_service import dispatch_ingest


class TestProfileConcurrency(unittest.TestCase):
    def test_concurrent_add_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "profile")
            prefs.ensure_profile_layout(base)
            n = 40

            def add_one(i: int):
                life_service.add_task(base, f"task-{i}", bucket="inbox")

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(add_one, range(n)))

            tasks = life_service.load_tasks(base)
            titles = {t.get("title") for t in tasks}
            self.assertEqual(len(tasks), n, "lost task rows under concurrent add_task")
            self.assertEqual(len(titles), n)

    def test_concurrent_cards_and_pref_updates_keep_every_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = prefs.ensure_profile_layout(os.path.join(tmp, "profile"))

            def change(i):
                flashcard_service.add_card(base, f"Question {i}", "Answer")
                prefs.save_pref(base, f"setting_{i}", i)
                prefs.set_permission(base, f"https://site{i}.example", "camera", "deny")

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(change, range(24)))
            self.assertEqual(len(flashcard_service.load_cards(base)), 24)
            data = prefs.load_prefs(base)
            self.assertTrue(all(data[f"setting_{i}"] == i for i in range(24)))
            self.assertEqual(len(prefs.load_permissions(base)), 24)

    def test_concurrent_reviews_and_focus_credit_are_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = prefs.ensure_profile_layout(os.path.join(tmp, "profile"))
            card = flashcard_service.add_card(base, "Q", "A")
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: flashcard_service.review_card(base, card["id"], "again"), range(16)))
            self.assertEqual(flashcard_service.load_cards(base)[0]["reviews"], 16)
            item = personal_plan.create_item(base, "Study")
            write_json(focus_service.sessions_path(base), {"active": None, "sessions": [{
                "id": "finished-pour", "item_id": item["id"], "minutes": 25,
                "started_at": 1000, "ended_at": 2500, "status": "completed", "credited": False,
            }]})
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                summaries = list(pool.map(lambda _: study_session.credit_pending(base), range(16)))
            self.assertEqual(sum(row["credited"] for row in summaries), 1)
            self.assertEqual(personal_plan.load_plan(base)["items"][0]["studied_minutes"], 25)

    def test_concurrent_android_create_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "profile")
            prefs.ensure_profile_layout(base)
            n = 30

            def ingest_one(i: int):
                out = dispatch_ingest(
                    base,
                    {"action": "create_task", "payload": {"title": f"mob-{i}", "bucket": "Inbox"}},
                )
                self.assertTrue(out.get("ok"), msg=str(out))

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(ingest_one, range(n)))

            tasks = life_service.load_tasks(base)
            mob_titles = [t.get("title") for t in tasks if str(t.get("title", "")).startswith("mob-")]
            self.assertEqual(len(mob_titles), n)
            self.assertEqual(len(set(mob_titles)), n)


if __name__ == "__main__":
    unittest.main()
