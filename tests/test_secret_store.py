"""Credentials at rest: protected where the OS can, never leaked where it cannot.

The contract under test is not “we encrypted a string”; it is the user-visible
promise that an upgrade never signs them out, a failed protection attempt keeps
the old value, and no backup, diagnostics bundle or ordinary settings file
carries a live token.
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

from litebrowser.core import prefs, secret_store
from litebrowser.services import diagnostics, history_service

CANARY = "CANARY-live-credential-do-not-export"


class TestSecretStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip_and_delete(self):
        secret_store.set_secret(self.base, "sync_token", "abc123")
        self.assertEqual(secret_store.get_secret(self.base, "sync_token"), "abc123")
        secret_store.set_secret(self.base, "sync_token", "")
        self.assertIsNone(secret_store.get_secret(self.base, "sync_token"))

    def test_status_names_the_backend_without_naming_the_value(self):
        secret_store.set_secret(self.base, "mobile_bridge_token", CANARY)
        status = secret_store.status(self.base)
        self.assertNotIn(CANARY, json.dumps(status))
        self.assertIn(status["backend"], ("dpapi", "file"))
        self.assertIn("mobile_bridge_token", status["entries"])
        if sys.platform.startswith("win"):
            self.assertTrue(status["protected"])
        else:
            self.assertIn("not encrypted", status["warning"])

    def test_invalid_secret_name_is_refused(self):
        with self.assertRaises(secret_store.SecretStorageError):
            secret_store.set_secret(self.base, "../escape", "x")

    def test_legacy_plaintext_token_is_migrated_and_removed(self):
        prefs.save_prefs(self.base, {"sync_token": CANARY})
        self.assertEqual(prefs.get_sync_token(self.base), CANARY)
        self.assertNotIn("sync_token", prefs.load_prefs(self.base))
        self.assertEqual(secret_store.get_secret(self.base, "sync_token"), CANARY)

    def test_failed_protection_keeps_the_legacy_value(self):
        prefs.save_prefs(self.base, {"sync_token": CANARY})
        with mock.patch.object(
            secret_store, "_protect", side_effect=secret_store.SecretStorageError("DPAPI unavailable")
        ):
            self.assertEqual(prefs.get_sync_token(self.base), CANARY)
        self.assertEqual(prefs.load_prefs(self.base)["sync_token"], CANARY)
        self.assertIn("could not be protected", secret_store.status(self.base)["error"])
        self.assertIn("previous value was kept", secret_store.recovery_hint(self.base))

    def test_a_secret_that_cannot_be_unlocked_returns_none_without_crashing(self):
        secret_store.set_secret(self.base, "sync_token", CANARY)
        with mock.patch.object(
            secret_store, "_unprotect", side_effect=secret_store.SecretStorageError("bad key")
        ):
            self.assertIsNone(secret_store.get_secret(self.base, "sync_token"))
        self.assertIn("bad key", secret_store.status(self.base)["error"])

    def test_a_future_secret_store_is_not_silently_rewritten(self):
        with open(secret_store.path(self.base), "w", encoding="utf-8") as handle:
            json.dump({"version": 99, "entries": {}}, handle)
        self.assertIsNone(secret_store.get_secret(self.base, "sync_token"))
        self.assertIn("newer Mei", secret_store.status(self.base)["error"])

    def test_a_damaged_store_is_preserved_instead_of_treated_as_empty(self):
        damaged = '{"version": 1, "entries": {"sync_token": '
        with open(secret_store.path(self.base), "w", encoding="utf-8") as handle:
            handle.write(damaged)
        self.assertIsNone(secret_store.get_secret(self.base, "sync_token"))
        self.assertIn("left untouched", secret_store.status(self.base)["error"])
        with self.assertRaises(secret_store.SecretStorageError):
            secret_store.set_secret(self.base, "mobile_bridge_token", "new")
        with open(secret_store.path(self.base), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), damaged, "a failed write must keep the damaged bytes")


class TestPrefsIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _ai_file(self):
        with open(prefs.ai_settings_path(self.base), encoding="utf-8") as handle:
            return json.load(handle)

    def test_ai_key_moves_out_of_the_settings_file(self):
        with open(prefs.ai_settings_path(self.base), "w", encoding="utf-8") as handle:
            json.dump({"provider": "openrouter", "openrouter_api_key": CANARY}, handle)
        settings = prefs.load_ai_settings(self.base)
        self.assertEqual(settings["openrouter_api_key"], CANARY)
        self.assertNotIn("openrouter_api_key", self._ai_file())
        self.assertEqual(secret_store.get_secret(self.base, "openrouter_api_key"), CANARY)

    def test_saving_ai_settings_stores_the_key_protected(self):
        prefs.save_ai_settings(
            self.base,
            {"provider": "openrouter", "openrouter_api_key": CANARY, "openrouter_model": "m"},
        )
        data = self._ai_file()
        self.assertNotIn("openrouter_api_key", data)
        self.assertEqual(data["openrouter_model"], "m")
        self.assertEqual(secret_store.get_secret(self.base, "openrouter_api_key"), CANARY)
        # Clearing the key really clears it (it must not reappear from a leftover
        # plaintext copy).
        prefs.save_ai_settings(self.base, {"openrouter_api_key": ""})
        self.assertIsNone(secret_store.get_secret(self.base, "openrouter_api_key"))
        self.assertNotIn("openrouter_api_key", self._ai_file())

    def test_ai_key_survives_a_failed_protection_attempt(self):
        prefs.save_ai_settings(self.base, {"openrouter_api_key": CANARY})
        with mock.patch.object(
            secret_store, "_protect", side_effect=secret_store.SecretStorageError("no vault")
        ):
            prefs.save_ai_settings(self.base, {"provider": "rag"})
        self.assertEqual(secret_store.get_secret(self.base, "openrouter_api_key"), CANARY)
        self.assertEqual(prefs.load_ai_settings(self.base)["openrouter_api_key"], CANARY)

    def test_google_token_cache_is_protected(self):
        prefs.set_google_token_cache(self.base, {"access_token": CANARY, "refresh_token": "r"})
        self.assertNotIn("google_token_cache", prefs.load_prefs(self.base))
        self.assertEqual(prefs.get_google_token_cache(self.base)["access_token"], CANARY)
        prefs.clear_google_account(self.base)
        self.assertEqual(prefs.get_google_token_cache(self.base), {})

    def test_proxy_password_is_not_written_to_the_config_file(self):
        prefs.set_proxy_config(self.base, {"enabled": True, "host": "proxy", "port": 8080, "password": CANARY})
        with open(prefs.proxy_config_path(self.base), encoding="utf-8") as handle:
            raw = handle.read()
        self.assertNotIn(CANARY, raw)
        self.assertEqual(prefs.get_proxy_config(self.base)["password"], CANARY)
        prefs.set_proxy_config(self.base, {"enabled": False, "password": None})
        self.assertEqual(prefs.get_proxy_config(self.base)["password"], CANARY)


class TestExportRedaction(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self):
        prefs.set_sync_token(self.base, CANARY)
        prefs.set_mobile_bridge_token(self.base, CANARY)
        prefs.set_google_token_cache(self.base, {"access_token": CANARY})
        prefs.save_ai_settings(self.base, {"openrouter_api_key": CANARY})
        prefs.set_passcode_record(self.base, "salt", "hash", 1000)
        prefs.set_last_vpn_proxy(
            self.base, {"enabled": True, "host": "proxy", "port": 1, "user": "u", "password": CANARY}
        )

    def test_backup_contains_no_live_credential(self):
        self._seed()
        payload = history_service.export_profile_payload(self.base)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(CANARY, text)
        self.assertIn("ai_settings.openrouter_api_key", payload["redacted_fields"])
        self.assertIn("prefs.passcode_hash", payload["redacted_fields"])
        self.assertNotIn("passcode_hash", payload["prefs"])
        self.assertNotIn("sync_token", payload["prefs"])
        self.assertNotIn("mobile_bridge_token", payload["prefs"])

    def test_diagnostics_bundle_contains_no_live_credential(self):
        self._seed()
        out = os.path.join(self._tmp.name, "diag.zip")
        diagnostics.build_bundle(self.base, out, app_dir=self._tmp.name)
        with zipfile.ZipFile(out) as bundle:
            for name in bundle.namelist():
                self.assertNotIn(CANARY, bundle.read(name).decode("utf-8", "replace"), name)

    def test_importing_a_redacted_backup_keeps_the_existing_passcode(self):
        self._seed()
        payload = history_service.export_profile_payload(self.base)
        self.assertTrue(history_service.import_profile_payload(self.base, payload))
        salt, digest, rounds = prefs.get_passcode_record(self.base)
        self.assertEqual((salt, digest, rounds), ("salt", "hash", 1000))

    def test_secrets_dat_is_not_in_the_backup(self):
        secret_store.set_secret(self.base, "sync_token", CANARY)
        out = os.path.join(self._tmp.name, "backup.zip")
        self.assertTrue(history_service.export_profile_to_zip(self.base, out))
        with zipfile.ZipFile(out) as bundle:
            for name in bundle.namelist():
                with bundle.open(name) as handle:
                    self.assertNotIn(CANARY.encode("utf-8"), handle.read(), name)


if __name__ == "__main__":
    unittest.main()
