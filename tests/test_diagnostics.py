"""The diagnostics bundle: enough evidence to debug, nothing private to leak.

A support archive is only useful if a stranger can read it, so the contract is
two-sided: it must prove which build ran and what the profile looks like, and it
must not carry a single note, task title, password or history URL. These tests
put canaries in every one of those places and fail if one comes back out.
"""
import json
import logging
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from litebrowser.core import log, prefs, product, secret_store
from litebrowser.services import diagnostics

CANARY = "CANARY-secret-value-do-not-ship"


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


class TestBundleContents(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        self.out = os.path.join(self._tmp.name, "diag.zip")
        # A profile with something in every private place the bundle must avoid.
        _write_json(
            os.path.join(self.base, "personal_plan.json"),
            {
                "version": 2,
                "items": [{"id": "i1", "title": CANARY}, {"id": "i2", "title": CANARY}],
                "courses": [{"id": "c1", "name": CANARY}],
                "time_blocks": [],
            },
        )
        _write_json(
            os.path.join(self.base, "tasks.json"),
            {"version": 1, "items": [{"id": "t1", "title": CANARY}]},
        )
        with open(os.path.join(self.base, "history.txt"), "w", encoding="utf-8") as handle:
            handle.write(f"12345\thttps://example.com/{CANARY}\n")
        with open(os.path.join(self.base, "passwords.vault"), "wb") as handle:
            handle.write(CANARY.encode("utf-8"))
        with open(os.path.join(self.base, "secrets.dat"), "wb") as handle:
            handle.write(CANARY.encode("utf-8"))
        notes = os.path.join(self.base, "SafeVault", "notes")
        os.makedirs(notes, exist_ok=True)
        with open(os.path.join(notes, "a-note.md"), "w", encoding="utf-8") as handle:
            handle.write(CANARY)
        self.result = diagnostics.build_bundle(self.base, self.out, app_dir=self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _members(self):
        with zipfile.ZipFile(self.out) as bundle:
            return {name: bundle.read(name) for name in bundle.namelist()}

    def test_the_expected_files_are_there(self):
        members = self._members()
        self.assertIn("README.txt", members)
        self.assertIn("versions.json", members)
        self.assertIn("inventory.json", members)
        self.assertEqual(sorted(self.result["members"]), sorted(members))

    def test_no_private_content_travels(self):
        for name, data in self._members().items():
            with self.subTest(member=name):
                self.assertNotIn(CANARY, data.decode("utf-8", "replace"), f"{name} leaked profile data")

    def test_versions_name_the_build_that_ran(self):
        payload = json.loads(self._members()["versions.json"].decode("utf-8"))
        self.assertEqual(payload["app"]["version"], product.APP_VERSION)
        self.assertEqual(payload["app"]["name"], product.APP_NAME)
        self.assertIn("python", payload)
        self.assertIn("collected_at", payload)

    def test_ui_facts_are_whatever_the_caller_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "diag.zip")
            diagnostics.build_bundle(self.base, out, ui={"binding": "PyQt6", "chromium": "122"})
            with zipfile.ZipFile(out) as bundle:
                payload = json.loads(bundle.read("versions.json").decode("utf-8"))
        self.assertEqual(payload["ui"]["binding"], "PyQt6")

    def test_the_inventory_counts_records_without_describing_them(self):
        inventory = json.loads(self._members()["inventory.json"].decode("utf-8"))
        stores = {store["name"]: store for store in inventory["stores"]}
        planner = stores["personal_plan.json"]
        self.assertEqual(planner["version"], 2)
        self.assertEqual(planner["counts"], {"items": 2, "courses": 1, "time_blocks": 0})
        self.assertGreater(planner["bytes"], 0)
        self.assertTrue(inventory["profile"])
        self.assertNotIn("secrets.dat", stores, "the credential store is not described at all")

    def test_folders_are_summarised_not_walked_into_the_bundle(self):
        inventory = json.loads(self._members()["inventory.json"].decode("utf-8"))
        self.assertIn("SafeVault", inventory["folders"])
        self.assertEqual(inventory["folders"]["SafeVault"]["files"], 1)

    def test_a_bundle_is_small_enough_to_attach(self):
        self.assertLess(self.result["bytes"], 200 * 1024)


class TestLogTail(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = os.path.join(self._tmp.name, "profile")
        os.makedirs(self.base)
        self.logs = os.path.join(self._tmp.name, "data", "logs")
        os.makedirs(self.logs)

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self, **kwargs):
        out = os.path.join(self._tmp.name, "diag.zip")
        with mock.patch.object(
            diagnostics.app_paths, "data_root", return_value=os.path.join(self._tmp.name, "data")
        ):
            return diagnostics.build_bundle(self.base, out, **kwargs), out

    def test_without_a_log_the_archive_still_builds(self):
        result, out = self._build()
        self.assertEqual(result["log_bytes"], 0)
        with zipfile.ZipFile(out) as bundle:
            self.assertFalse([name for name in bundle.namelist() if name.startswith("logs/")])

    def test_only_the_tail_of_a_large_log_is_kept(self):
        with open(os.path.join(self.logs, "mei.log"), "w", encoding="utf-8") as handle:
            handle.write("x" * 400_000)
            handle.write("LAST-LINE")
        result, out = self._build(max_log_bytes=1024)
        self.assertEqual(result["log_bytes"], 1024)
        with zipfile.ZipFile(out) as bundle:
            tail = bundle.read("logs/mei.log").decode("utf-8")
        self.assertTrue(tail.endswith("LAST-LINE"))
        self.assertLess(len(tail), 1024 + 16)

    def test_the_bundle_name_carries_the_version(self):
        name = diagnostics.default_bundle_name()
        self.assertIn(product.APP_VERSION, name)
        self.assertTrue(name.endswith(".zip"))


class TestLogRedaction(unittest.TestCase):
    """The log tail is the one bundle member that can carry free text.

    Provider errors and redirect URLs are the usual way a bearer token reaches
    a log. Masking happens in the file handler, before the bytes exist, so a
    support archive cannot contain a credential even if a caller logged one.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = os.path.join(self._tmp.name, "profile")
        os.makedirs(self.base)
        # Use the real file handler (the redaction filter lives on it) without
        # touching the process-wide logger other tests may rely on.
        self.logs = os.path.join(self._tmp.name, "runtime_data", "logs")
        self.handler = log._open_handler(self.logs)
        self.logger = logging.getLogger("litebrowser.redaction-test")
        self.logger.handlers = [self.handler]
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        self.logger.removeHandler(self.handler)
        self.handler.close()

    def test_recognisable_credentials_are_masked(self):
        self.assertEqual(log.redact("Authorization: Bearer abcDEF123456"), "Authorization: Bearer [redacted]")
        self.assertNotIn("hunter2", log.redact("proxy password=hunter2 host=x"))
        self.assertNotIn("hunter2", log.redact("https://mei:hunter2@example.com/path"))
        self.assertNotIn("AIza", log.redact("key sk-or-v1-AIzaSyDummyDummyDummy"))
        self.assertNotIn("abc123", log.redact("token ya29.abc123.def456"))

    def test_known_secret_values_are_masked_even_without_context(self):
        secret_store._remember(CANARY)
        self.assertEqual(log.redact(f"opaque provider text {CANARY}"), "opaque provider text [redacted]")

    def test_the_diagnostics_log_tail_contains_no_credential(self):
        bearer = "Bearer " + CANARY
        self.logger.warning("request failed with %s", bearer)
        self.logger.warning("api_key=%s", CANARY)
        secret_store._remember(CANARY)
        self.logger.warning("opaque echo %s", CANARY)
        out = os.path.join(self._tmp.name, "diag.zip")
        result = diagnostics.build_bundle(self.base, out, app_dir=self._tmp.name)
        self.assertGreater(result["log_bytes"], 0)
        with zipfile.ZipFile(out) as bundle:
            for name in bundle.namelist():
                with self.subTest(member=name):
                    self.assertNotIn(CANARY, bundle.read(name).decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
