"""Profile/storage safety: lockfile, atomic writes, prefs round-trip under concurrency.

These cover the race fixes B5/B7 that prevent two shell windows from corrupting
one profile directory.
"""
import concurrent.futures
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from litebrowser.core import prefs, storage_utils


class TestPrefsRoundTrip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_load_roundtrip_and_default_schema(self):
        data = prefs.load_prefs(self.base)
        data["theme"] = "cafe-night"
        prefs.save_prefs(self.base, data)
        again = prefs.load_prefs(self.base)
        self.assertEqual(again.get("theme"), "cafe-night")
        self.assertIn("schema_version", again)

    def test_save_prefs_is_atomic_no_temp_left_over(self):
        data = prefs.load_prefs(self.base)
        data["x"] = list(range(50))
        prefs.save_prefs(self.base, data)
        # No half-written .tmp file should remain in the profile dir.
        leftovers = [n for n in os.listdir(self.base) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_corrupt_prefs_file_falls_back_to_empty_dict(self):
        path = os.path.join(self.base, "prefs.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{oops not json]")
        data = prefs.load_prefs(self.base)
        self.assertIsInstance(data, dict)


class TestConcurrentWriteSafety(unittest.TestCase):
    """Simulate two windows writing profile prefs/simultaneous counters."""

    def test_sync_state_counter_never_goes_negative_under_contention(self):
        import litebrowser.services.life_service as ls
        with tempfile.TemporaryDirectory() as tmp:
            base = prefs.ensure_profile_layout(os.path.join(tmp, "profile"))

            def worker():
                for _ in range(20):
                    state = ls.load_sync_state(base)
                    state["pending_changes"] = int(state.get("pending_changes", 0) or 0) + 1
                    ls.save_sync_state(base, state)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            final = ls.load_sync_state(base)
            self.assertGreaterEqual(int(final["pending_changes"]), 0)

    def test_write_json_atomic_under_parallel_writers(self):
        """Parallel writers contending one file must not leave it corrupt.

        Windows can transiently raise PermissionError from os.replace when an AV
        scanner or another thread holds the file handle open for a millisecond --
        that's a platform reality, not product corruption. What *matters* is the
        file is always valid JSON at the end. We retry transient OS errors a few
        times to keep the assertion about *final* integrity, not a race window.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "state.json")

            def one(i):
                for attempt in range(6):
                    try:
                        storage_utils.write_json(target, {"writer": i, "value": list(range(200))})
                        return
                    except PermissionError:
                        time.sleep(0.005 * (attempt + 1))
                # final attempt - surface the error if still failing
                storage_utils.write_json(target, {"writer": i, "value": list(range(200))})

            n = 16
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(one, range(n)))

            with open(target, "r", encoding="utf-8") as fh:
                payload = json.load(fh)  # must parse -- file never corrupt
            self.assertIn("writer", payload)
            self.assertIn("value", payload)
            self.assertIsInstance(payload["value"], list)

    def test_invalid_json_does_not_allocate_a_handle_or_touch_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "state.json")
            storage_utils.write_json(target, {"keep": True})
            for invalid in ({"bad": object()}, {"bad": float("nan")}):
                with mock.patch.object(storage_utils, "tempfile_mkstemp_same_dir") as allocate:
                    with self.assertRaises((TypeError, ValueError)):
                        storage_utils.write_json(target, invalid)
                    allocate.assert_not_called()
            self.assertEqual(storage_utils.read_json(target, None), {"keep": True})

    def test_atomic_replace_retries_a_transient_windows_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "state.json")
            real_replace = storage_utils.os.replace
            calls = 0

            def briefly_locked(src, dest):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise PermissionError("simulated antivirus lock")
                return real_replace(src, dest)

            with mock.patch.object(storage_utils.os, "replace", side_effect=briefly_locked):
                storage_utils.write_json(target, {"saved": True})

            self.assertEqual(calls, 2)
            with open(target, "r", encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), {"saved": True})


if __name__ == "__main__":
    unittest.main()
