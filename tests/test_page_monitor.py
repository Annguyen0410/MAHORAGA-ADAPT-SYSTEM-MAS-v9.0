"""Watched pages: correct URLs, hostile/corrupt rows, and honest failures.

The monitor is a small feature with a large blast radius: its list is a JSON
file a user can edit, its work happens on a background thread, and a wrong
comparison either spams notifications or hides a real change. These tests pin
the parsing rules and the “failed is not unchanged” contract.
"""
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from litebrowser.core import prefs
from litebrowser.services import page_monitor


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200, headers=None):
        self._body = body
        self.status = status
        self.headers = headers or {}
        self._read = False

    def read(self, size=-1):
        if self._read:
            return b""
        self._read = True
        return self._body if size is None or size < 0 else self._body[:size]

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _write_monitors(self, monitors):
        with open(page_monitor._path(self.base), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "monitors": monitors}, handle)


class TestNormalizeUrl(unittest.TestCase):
    def test_query_is_not_turned_into_a_path(self):
        self.assertEqual(
            page_monitor.normalize_url("https://example.com?sort=1"),
            "https://example.com/?sort=1",
        )
        self.assertEqual(
            page_monitor.normalize_url("https://example.com/list?page=2&q=a%20b"),
            "https://example.com/list?page=2&q=a%20b",
        )

    def test_scheme_and_host_are_lowercased_path_case_is_kept(self):
        self.assertEqual(
            page_monitor.normalize_url("HTTPS://Example.COM/Path/"),
            "https://example.com/Path",
        )

    def test_fragment_is_dropped_because_servers_never_receive_it(self):
        self.assertEqual(
            page_monitor.normalize_url("https://example.com/page#section-2"),
            "https://example.com/page",
        )

    def test_default_ports_are_removed_and_explicit_ports_survive(self):
        self.assertEqual(page_monitor.normalize_url("http://example.com:80/a"), "http://example.com/a")
        self.assertEqual(page_monitor.normalize_url("https://example.com:443/a"), "https://example.com/a")
        self.assertEqual(page_monitor.normalize_url("https://example.com:8443/a"), "https://example.com:8443/a")

    def test_bare_host_gets_https(self):
        self.assertEqual(page_monitor.normalize_url("example.com/watch"), "https://example.com/watch")

    def test_root_trailing_slash_is_kept(self):
        self.assertEqual(page_monitor.normalize_url("https://example.com/"), "https://example.com/")
        self.assertEqual(page_monitor.normalize_url("https://example.com"), "https://example.com/")

    def test_unsupported_schemes_are_refused(self):
        for value in (
            "javascript:alert(1)",
            "mailto:someone@example.com",
            "file:///C:/Windows/win.ini",
            "ftp://example.com/file",
            "data:text/html,hello",
        ):
            with self.subTest(value=value):
                with self.assertRaises(page_monitor.MonitorError):
                    page_monitor.normalize_url(value)

    def test_local_and_private_targets_are_refused(self):
        for value in (
            "http://localhost:8080/admin",
            "http://127.0.0.1/",
            "http://[::1]/",
            "http://192.168.1.1/",
            "http://10.0.0.5/",
            "http://169.254.1.2/",
            "http://router.local/",
            "http://printer.internal/",
        ):
            with self.subTest(value=value):
                with self.assertRaises(page_monitor.MonitorError):
                    page_monitor.normalize_url(value)

    def test_credentials_and_spaces_are_refused(self):
        for value in (
            "https://user:pass@example.com/",
            "https://user@example.com/",
            "https://example.com/a b",
            "https://example.com/\nnext",
        ):
            with self.subTest(value=value):
                with self.assertRaises(page_monitor.MonitorError):
                    page_monitor.normalize_url(value)


class TestMonitorStore(_Base):
    def test_add_normalizes_and_deduplicates(self):
        first = page_monitor.add_monitor(self.base, "https://example.com?sort=1", "One")
        self.assertTrue(first)
        self.assertEqual(page_monitor.add_monitor(self.base, "https://EXAMPLE.com/?sort=1"), {})
        self.assertEqual(len(page_monitor.load_monitors(self.base)), 1)
        self.assertEqual(first["hash"], "")
        self.assertEqual(first["last_error"], "")

    def test_corrupt_rows_are_skipped_without_disabling_the_rest(self):
        self._write_monitors(
            [
                {"id": "good", "url": "https://example.com/page", "title": "Good", "hash": "abc", "last_checked": "nope"},
                "not a row",
                {"id": "bad-url", "url": "javascript:alert(1)"},
                {"id": "local", "url": "http://127.0.0.1/"},
                {"url": "https://missing-id.example"},
                {"id": "dupe", "url": "https://example.com/page"},
                {"id": "dup-id", "url": "https://example.com/other"},
                {"id": "good", "url": "https://example.com/other"},
                {"id": "future", "url": "https://example.com/future", "last_checked": 10**18, "enabled": "yes", "hash": 42},
            ]
        )
        monitors = page_monitor.load_monitors(self.base)
        self.assertEqual([row["id"] for row in monitors], ["good", "dup-id", "future"])
        self.assertEqual(monitors[0]["last_checked"], 0)
        self.assertGreater(monitors[2]["last_checked"], 0, "a timestamp from the future is clamped to now")
        self.assertLessEqual(monitors[2]["last_checked"], 2**40)
        self.assertEqual(monitors[2]["hash"], "", "a non-string hash is treated as 'never checked'")
        self.assertTrue(monitors[2]["enabled"])

    def test_due_checks_ignore_bad_intervals_and_future_stamps(self):
        self._write_monitors(
            [
                {"id": "old", "url": "https://example.com/old", "last_checked": 1, "enabled": True},
                {"id": "fresh", "url": "https://example.com/fresh", "last_checked": 2**40, "enabled": True},
                {"id": "off", "url": "https://example.com/off", "last_checked": 1, "enabled": False},
            ]
        )
        due = page_monitor.due_monitors(self.base, -10)
        self.assertEqual([row["id"] for row in due], ["old"], "a future stamp is clamped to now, not treated as due")

    def test_remove_requires_a_real_id(self):
        monitor = page_monitor.add_monitor(self.base, "https://example.com/page")
        self.assertFalse(page_monitor.remove_monitor(self.base, ""))
        self.assertFalse(page_monitor.remove_monitor(self.base, "missing"))
        self.assertTrue(page_monitor.remove_monitor(self.base, monitor["id"]))
        self.assertEqual(page_monitor.load_monitors(self.base), [])

    def test_the_watch_list_has_a_cap(self):
        with mock.patch.object(page_monitor, "MAX_MONITORS", 1):
            page_monitor.add_monitor(self.base, "https://example.com/one")
            with self.assertRaises(page_monitor.MonitorError):
                page_monitor.add_monitor(self.base, "https://example.com/two")


class TestChecks(_Base):
    def test_a_successful_check_seeds_then_detects_a_change(self):
        monitor = page_monitor.add_monitor(self.base, "https://example.com/page", "Page")
        with mock.patch.object(
            page_monitor, "_open_url", side_effect=lambda *a, **k: _FakeResponse(b"first")
        ):
            self.assertEqual(page_monitor.check_monitor(self.base, monitor["id"])["status"], "seeded")
            unchanged = page_monitor.check_monitor(self.base, monitor["id"])
        self.assertEqual(unchanged["status"], "same")
        self.assertEqual(unchanged["error"], "")

        with mock.patch.object(page_monitor, "_open_url", return_value=_FakeResponse(b"second")):
            changed = page_monitor.check_monitor(self.base, monitor["id"])
        self.assertEqual(changed["status"], "changed")

    def test_a_failed_fetch_keeps_the_old_hash_and_is_not_same(self):
        monitor = page_monitor.add_monitor(self.base, "https://example.com/page", "Page")
        page_monitor.record_check(self.base, monitor["id"], "known-hash")
        failure = urllib.error.URLError("offline")
        with mock.patch.object(page_monitor, "_open_url", side_effect=failure):
            result = page_monitor.check_monitor(self.base, monitor["id"])
        self.assertEqual(result["status"], "error")
        self.assertIn("Could not reach", result["error"])
        stored = page_monitor.load_monitors(self.base)[0]
        self.assertEqual(stored["hash"], "known-hash")
        self.assertIn("Could not reach", stored["last_error"])

    def test_next_success_clears_the_error(self):
        monitor = page_monitor.add_monitor(self.base, "https://example.com/page", "Page")
        with mock.patch.object(page_monitor, "_open_url", side_effect=OSError("boom")):
            page_monitor.check_monitor(self.base, monitor["id"])
        self.assertTrue(page_monitor.load_monitors(self.base)[0]["last_error"])
        with mock.patch.object(page_monitor, "_open_url", return_value=_FakeResponse(b"ok")):
            self.assertEqual(page_monitor.check_monitor(self.base, monitor["id"])["status"], "seeded")
        self.assertEqual(page_monitor.load_monitors(self.base)[0]["last_error"], "")

    def test_oversized_pages_are_refused_before_hashing(self):
        monitor = page_monitor.add_monitor(self.base, "https://example.com/page", "Page")
        with mock.patch.object(page_monitor, "_open_url", return_value=_FakeResponse(b"x" * 64)):
            result = page_monitor.check_monitor(self.base, monitor["id"], max_bytes=16)
        self.assertEqual(result["status"], "error")
        self.assertIn("too large", result["error"])
        self.assertEqual(page_monitor.load_monitors(self.base)[0]["hash"], "")

    def test_declared_oversized_content_length_is_refused(self):
        monitor = page_monitor.add_monitor(self.base, "https://example.com/page", "Page")
        response = _FakeResponse(b"tiny", headers={"Content-Length": str(page_monitor.MAX_RESPONSE_BYTES + 1)})
        with mock.patch.object(page_monitor, "_open_url", return_value=response):
            result = page_monitor.check_monitor(self.base, monitor["id"])
        self.assertEqual(result["status"], "error")
        self.assertIn("too large", result["error"])

    def test_redirect_to_a_local_target_is_blocked(self):
        request = urllib.request.Request("https://example.com/start")
        handler = page_monitor._HttpOnlyRedirect()
        with self.assertRaises(page_monitor.MonitorFetchError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1/admin")

    def test_redirect_to_https_is_followed(self):
        request = urllib.request.Request("http://example.com/start")
        handler = page_monitor._HttpOnlyRedirect()
        with mock.patch.object(
            urllib.request.HTTPRedirectHandler, "redirect_request", return_value="redirected"
        ) as parent:
            self.assertEqual(
                handler.redirect_request(request, None, 301, "Moved", {}, "https://example.com/next"),
                "redirected",
            )
        self.assertEqual(parent.call_args[0][5], "https://example.com/next")

    def test_missing_monitor_is_reported_not_silently_successful(self):
        self.assertEqual(page_monitor.check_monitor(self.base, "nope")["status"], "missing")
        self.assertEqual(page_monitor.record_check(self.base, "nope", "hash"), "missing")

    def test_fetch_and_hash_contract_is_unchanged(self):
        with mock.patch.object(page_monitor, "_open_url", return_value=_FakeResponse(b"abc")):
            digest = page_monitor.fetch_and_hash("https://example.com/")
        self.assertEqual(len(digest), 32)
        with mock.patch.object(page_monitor, "_open_url", side_effect=OSError("no")):
            self.assertIsNone(page_monitor.fetch_and_hash("https://example.com/"))


if __name__ == "__main__":
    unittest.main()
