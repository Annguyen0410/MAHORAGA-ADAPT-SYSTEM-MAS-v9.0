"""Tests for Android mobile bridge (no Qt)."""
import base64
import http.client
import json
import os
import socket
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request

from litebrowser.core import app_paths, prefs
from litebrowser.services import (
    android_bridge_service,
    extension_bridge,
    personal_service,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestDispatchIngest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_note(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "create_note",
                "source": "test",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {"category": "Mobile", "title": "Hello", "body": "World", "tags": ["a", "b"]},
            },
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "create_note")
        notes = personal_service.list_notes(self.base)
        self.assertEqual(len(notes), 1)
        self.assertIn("World", personal_service.read_note(self.base, notes[0]["id"])["content"])
        self.assertIn("# a", personal_service.read_note(self.base, notes[0]["id"])["content"])

    def test_create_note_keeps_unicode_title_and_body(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "create_note",
                "source": "test",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {
                    "category": "Cá nhân",
                    "title": "Ghi chú tiếng Việt ẹm ơi",
                    "body": "Nội dung có dấu: á à ả ã ạ — emoji 🎨 và chữ Hán 中文.",
                },
            },
        )
        self.assertTrue(out["ok"])
        notes = personal_service.list_notes(self.base)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "Ghi chú tiếng Việt ẹm ơi")
        self.assertIn("中文", personal_service.read_note(self.base, notes[0]["id"])["content"])

    def test_create_drawing(self):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"fakepixels"
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "create_drawing",
                "source": "android.draw",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {
                    "title": "Bản vẽ đầu tiên",
                    "category": "Drawings",
                    "image_base64": base64.b64encode(png_bytes).decode("ascii"),
                    "body": "Phác thảo",
                    "tags": ["sketch"],
                },
            },
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "create_drawing")
        self.assertTrue(out["result"]["image_path"].startswith("files/Drawings/"))
        self.assertNotIn("..", out["result"]["image_path"].split("/"))
        self.assertIn("Drawings", out["result"]["image_path"])
        saved = os.path.join(prefs.vault_path(self.base), out["result"]["image_path"])
        self.assertTrue(os.path.isfile(saved))
        with open(saved, "rb") as f:
            self.assertEqual(f.read(), png_bytes)
        notes = personal_service.list_notes(self.base)
        self.assertEqual(len(notes), 1)
        content = personal_service.read_note(self.base, notes[0]["id"])["content"]
        self.assertIn("Attachment: files/Drawings", content)

    def test_create_drawing_rejects_bad_base64(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "create_drawing",
                "source": "t",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {"title": "X", "image_base64": "!!!not-base64!!!"},
            },
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "invalid_payload")

    def test_create_drawing_requires_title(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "create_drawing",
                "source": "t",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {"image_base64": base64.b64encode(b"x").decode("ascii")},
            },
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "invalid_payload")

    def test_pairing_code_roundtrip(self):
        prefs.set_mobile_bridge_token(self.base, "tok123")
        code = android_bridge_service.pairing_code(self.base, lan_ip="192.168.1.5")
        parsed = android_bridge_service.parse_pairing_code(code)
        self.assertEqual(
            parsed,
            {"host": "192.168.1.5", "port": str(prefs.get_mobile_bridge_port(self.base)), "token": "tok123"},
        )
        self.assertIsNone(android_bridge_service.parse_pairing_code("not-a-code"))
        self.assertIsNone(android_bridge_service.parse_pairing_code("MEI1|x|notaport|y"))
        png = android_bridge_service.pairing_qr_png(code)
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_unknown_action(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {"action": "not_real", "source": "t", "timestamp": "2026-01-01T00:00:00Z", "payload": {}},
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "unknown_action")

    def test_dispatch_rejects_oversized_field(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {"action": "create_note", "payload": {"category": "Mobile", "title": "T", "body": "x" * (android_bridge_service.MAX_FIELD_CHARS + 1)}},
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "invalid_payload")

    def test_import_tabs_batch(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "import_tabs_batch",
                "source": "android.tab_batch",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {
                    "source_browser": "android_remote",
                    "source_label": "Test",
                    "tabs": [{"url": "https://example.com", "title": "Ex", "active": True, "pinned": False}],
                },
            },
        )
        self.assertTrue(out["ok"])
        batches = extension_bridge.load_batches(self.base)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["tab_count"], 1)

    def test_import_tabs_batch_from_zip(self):
        import zipfile

        # Multi-screen export shape the Mei bridge extension writes.
        workspace = {
            "format": "mei-multi-window",
            "version": 1,
            "source_browser": "chrome",
            "created_at": 1700000000000,
            "window_count": 2,
            "batches": [
                {
                    "batch_id": "chrome_window_11",
                    "window_id": "11",
                    "screen_index": 0,
                    "source_browser": "chrome",
                    "source_label": "Screen 1",
                    "tabs": [{"url": "https://a.example", "title": "A", "active": True, "pinned": False}],
                },
                {
                    "batch_id": "chrome_window_22",
                    "window_id": "22",
                    "screen_index": 1,
                    "source_browser": "chrome",
                    "source_label": "Screen 2",
                    "tabs": [
                        {"url": "https://b.example", "title": "B", "active": True, "pinned": False},
                        {"url": "https://c.example", "title": "C tiếng Việt", "active": False, "pinned": True},
                    ],
                },
            ],
        }
        zip_path = os.path.join(self._tmp.name, "mei-workspace.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("workspace.json", json.dumps(workspace, ensure_ascii=False))
            zf.writestr("screen-1.json", json.dumps(workspace["batches"][0], ensure_ascii=False))
            zf.writestr("screen-2.json", json.dumps(workspace["batches"][1], ensure_ascii=False))

        last = extension_bridge.import_from_zip(self.base, zip_path)
        batches = extension_bridge.load_batches(self.base)
        self.assertEqual(last["source_label"], "Screen 2")
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0]["screen_index"], 1)
        self.assertEqual(batches[1]["screen_index"], 0)
        self.assertEqual(batches[1]["tab_count"], 1)
        self.assertEqual(batches[0]["tab_count"], 2)
        self.assertEqual(batches[0]["tabs"][1]["title"], "C tiếng Việt")

    def test_import_tabs_batch_zip_rejects_no_json(self):
        import zipfile

        zip_path = os.path.join(self._tmp.name, "empty.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "no tabs here")
        with self.assertRaises(ValueError):
            extension_bridge.import_from_zip(self.base, zip_path)

    def test_create_task_iso_due(self):
        from litebrowser.services import life_service

        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "create_task",
                "source": "t",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {
                    "title": "Task1",
                    "bucket": "Inbox",
                    "due_at": "2026-06-15T12:00:00Z",
                    "notes": "hello",
                },
            },
        )
        self.assertTrue(out["ok"])
        tasks = life_service.load_tasks(self.base)
        self.assertEqual(len(tasks), 1)
        self.assertGreater(int(tasks[0].get("due_at", 0)), 0)
        self.assertEqual(tasks[0].get("notes"), "hello")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class TestAndroidBridgeHTTP(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        prefs.set_mobile_bridge_enabled(self.base, True)
        prefs.set_mobile_bridge_host(self.base, "127.0.0.1")
        prefs.set_mobile_bridge_port(self.base, _pick_free_port())
        prefs.set_mobile_bridge_token(self.base, "secret-test-token")
        android_bridge_service.stop()
        self.assertTrue(android_bridge_service.start(self.base))
        addr = android_bridge_service.listen_address()
        self.assertIsNotNone(addr)
        self.port = addr[1]

    def tearDown(self):
        android_bridge_service.stop()
        self._tmp.cleanup()

    def _req(self, path, method="GET", data=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        h = dict(headers or {})
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        r = urllib.request.Request(url, data=body, method=method, headers=h)
        return urllib.request.urlopen(r, timeout=5)

    def test_ping_unauthorized(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._req("/api/mobile/ping")
        self.assertEqual(ctx.exception.code, 401)

    def test_cleared_running_token_rejects_requests(self):
        prefs.set_mobile_bridge_token(self.base, "")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._req("/api/mobile/ping")
        self.assertEqual(ctx.exception.code, 401)

    def test_ping_ok(self):
        res = self._req("/api/mobile/ping", headers={"Authorization": "Bearer secret-test-token"})
        self.assertEqual(res.status, 200)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res.headers.get("Cache-Control"), "no-store")
        self.assertIn("default-src 'none'", res.headers.get("Content-Security-Policy", ""))
        j = json.loads(res.read().decode("utf-8"))
        self.assertTrue(j["ok"])
        self.assertIn("create_note", j.get("capabilities", []))

    def test_ingest_create_note(self):
        res = self._req(
            "/api/mobile/ingest",
            method="POST",
            data={
                "action": "create_note",
                "source": "curl",
                "timestamp": "2026-04-09T12:00:00Z",
                "payload": {"category": "Mobile", "title": "T", "body": "B"},
            },
            headers={"Authorization": "Bearer secret-test-token"},
        )
        self.assertEqual(res.status, 200)
        j = json.loads(res.read().decode("utf-8"))
        self.assertTrue(j["ok"])
        self.assertEqual(len(personal_service.list_notes(self.base)), 1)

    def test_start_generates_missing_token_and_requires_auth(self):
        android_bridge_service.stop()
        prefs.set_mobile_bridge_token(self.base, "")
        prefs.set_mobile_bridge_port(self.base, _pick_free_port())

        self.assertTrue(android_bridge_service.start(self.base))
        generated = prefs.get_mobile_bridge_token(self.base)
        self.assertTrue(generated)

        addr = android_bridge_service.listen_address()
        self.assertIsNotNone(addr)
        self.port = addr[1]

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._req("/api/mobile/ping")
        self.assertEqual(ctx.exception.code, 401)

        res = self._req("/api/mobile/ping", headers={"Authorization": f"Bearer {generated}"})
        self.assertEqual(res.status, 200)
        j = json.loads(res.read().decode("utf-8"))
        self.assertTrue(j["ok"])

    def test_ingest_rejects_oversized_body_before_reading(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/api/mobile/ingest")
        conn.putheader("Authorization", "Bearer secret-test-token")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(android_bridge_service.MAX_BODY_BYTES + 1))
        conn.endheaders()
        res = conn.getresponse()
        self.assertEqual(res.status, 413)
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(body["error"]["code"], "payload_too_large")
        conn.close()

    def _multipart(self, fields, file_field, filename, file_bytes, mime="image/png"):
        boundary = "----MeiTestBoundary"
        out = bytearray()
        for name, value in fields.items():
            out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8")
        enc = urllib.parse.quote(filename)
        out += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename*={enc}\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        out += file_bytes
        out += f"\r\n--{boundary}--\r\n".encode("utf-8")
        return bytes(out), f"multipart/form-data; boundary={boundary}"

    def test_upload_multipart_utf8_filename(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03"
        body, content_type = self._multipart(
            {"relative_target": "Photos", "caption": "Ảnh chụp từ điện thoại"},
            "file",
            "ghi chú ảnh-đẹp.png",
            png,
        )
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/mobile/upload",
            data=body,
            method="POST",
            headers={"Authorization": "Bearer secret-test-token", "Content-Type": content_type},
        )
        res = urllib.request.urlopen(req, timeout=5)
        self.assertEqual(res.status, 200)
        j = json.loads(res.read().decode("utf-8"))
        self.assertTrue(j["ok"])
        self.assertEqual(j["result"]["filename"], "ghi chú ảnh-đẹp.png")
        saved = os.path.join(prefs.vault_path(self.base), j["result"]["path"])
        self.assertTrue(os.path.isfile(saved))
        self.assertIn("Photos", j["result"]["path"])
        self.assertEqual(j["result"]["path"].split("/")[:2], ["files", "Photos"])
        self.assertEqual(j["result"]["relative_target"], "Photos")
        with open(saved, "rb") as f:
            self.assertEqual(f.read(), png)

    def test_upload_requires_file_part(self):
        body, content_type = self._multipart(
            {"relative_target": "Photos"}, "file", "x.png", b""
        )
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/mobile/upload",
            data=body,
            method="POST",
            headers={"Authorization": "Bearer secret-test-token", "Content-Type": content_type},
        )
        res = urllib.request.urlopen(req, timeout=5)
        j = json.loads(res.read().decode("utf-8"))
        self.assertFalse(j["ok"])
        self.assertEqual(j["error"]["code"], "invalid_payload")

    def test_upload_rejects_path_traversal(self):
        body, content_type = self._multipart(
            {"relative_target": "../../escape"}, "file", "x.png", b"abc"
        )
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/mobile/upload",
            data=body,
            method="POST",
            headers={"Authorization": "Bearer secret-test-token", "Content-Type": content_type},
        )
        res = urllib.request.urlopen(req, timeout=5)
        j = json.loads(res.read().decode("utf-8"))
        self.assertFalse(j["ok"])
        self.assertEqual(j["error"]["code"], "invalid_payload")

    def test_ingest_create_drawing_http(self):
        png = b"\x89PNG\r\n\x1a\n" + b"draw"
        res = self._req(
            "/api/mobile/ingest",
            method="POST",
            data={
                "action": "create_drawing",
                "source": "android.draw",
                "timestamp": "2026-04-09T12:00:00Z",
                "payload": {
                    "title": "Sketch",
                    "image_base64": base64.b64encode(png).decode("ascii"),
                },
            },
            headers={"Authorization": "Bearer secret-test-token"},
        )
        self.assertEqual(res.status, 200)
        j = json.loads(res.read().decode("utf-8"))
        self.assertTrue(j["ok"])
        self.assertEqual(len(personal_service.list_notes(self.base)), 1)

    def test_capabilities_advertises_upload(self):
        res = self._req("/api/mobile/capabilities", headers={"Authorization": "Bearer secret-test-token"})
        j = json.loads(res.read().decode("utf-8"))
        self.assertTrue(j["ok"])
        self.assertIn("create_drawing", j["actions"])
        self.assertIn("open_app", j["actions"])
        self.assertTrue(j["upload"]["multipart"])
        self.assertEqual(j["upload"]["endpoint"], "/api/mobile/upload")

    def test_open_app_writes_request_file(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "open_app",
                "source": "android.mei_remote",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {"id": "mas", "label": "MAS"},
            },
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "open_app")
        manifest_mas = next(s["url"] for s in app_paths.chain_remote_sites() if s["key"] == "mas")
        self.assertEqual(out["result"]["url"], manifest_mas)
        from litebrowser.services import open_request
        reqs = open_request.drain_open_requests(self.base)
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["kind"], "mas")
        self.assertTrue(reqs[0]["url"])

    def test_open_all_six_chain_apps_resolves_deployed_urls(self):
        expected = {
            "linklumina": "https://graceful-kangaroo-4ebbee.netlify.app",
            "cucquanly": "https://starlit-lily-f90e23.netlify.app",
            "mas": "https://mahoraga-adapt-system-mas-v9-0.onrender.com",
            "worldleaderboard": "https://worldleaderboard.netlify.app",
            "bimat": "https://personalfrequencys.netlify.app",
            "boitoan": "https://boitoanzaigame.netlify.app",
        }
        for app_id, expected_url in expected.items():
            out = android_bridge_service.dispatch_ingest(
                self.base,
                {
                    "action": "open_app",
                    "source": "android.mei_remote",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "payload": {"id": app_id, "label": app_id},
                },
            )
            self.assertTrue(out["ok"], app_id)
            self.assertEqual(out["result"]["url"], expected_url)
        from litebrowser.services import open_request

        self.assertEqual(len(open_request.drain_open_requests(self.base)), len(expected))

    @unittest.skipUnless(
        os.path.isdir(os.path.join(ROOT, "web_support")),
        "web_support/ is a build artefact: the Project Hub copy only exists next to a build",
    )
    def test_open_hub_resolves_local_project_hub_url(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "open_app",
                "source": "android.mei_remote",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {"id": "hub", "label": "Project Hub"},
            },
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["url"], app_paths.project_hub_url())
        self.assertTrue(out["result"]["url"].startswith("file://"))

    def test_open_app_rejects_bad_url(self):
        out = android_bridge_service.dispatch_ingest(
            self.base,
            {
                "action": "open_app",
                "source": "android.mei_remote",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {"url": "javascript:alert(1)"},
            },
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "invalid_payload")

    def test_open_request_queue_is_isolated_per_profile(self):
        from litebrowser.services import open_request
        other = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "other_profile"))
        android_bridge_service.dispatch_ingest(
            self.base,
            {"action": "open_app", "source": "t", "timestamp": "2026-01-01T00:00:00Z", "payload": {"url": "https://example.com"}},
        )
        self.assertEqual(len(open_request.drain_open_requests(self.base)), 1)
        self.assertEqual(len(open_request.drain_open_requests(other)), 0)

    def test_drain_empty_queue_does_not_touch_disk(self):
        """The GUI polls every 2.5 s: an empty queue must not rewrite the file."""
        from litebrowser.services import open_request
        # No file at all yet.
        self.assertEqual(open_request.drain_open_requests(self.base), [])
        self.assertFalse(os.path.exists(open_request.requests_path(self.base)))
        # Empty queue file on disk: still no write churn (mtime unchanged).
        path = open_request.requests_path(self.base)
        open_request.push_open_request(self.base, {"url": "https://example.com", "source": "t"})
        self.assertEqual(len(open_request.drain_open_requests(self.base)), 1)  # clears it
        mtime_before = os.path.getmtime(path)
        self.assertEqual(open_request.drain_open_requests(self.base), [])
        self.assertEqual(os.path.getmtime(path), mtime_before)


if __name__ == "__main__":
    unittest.main()
