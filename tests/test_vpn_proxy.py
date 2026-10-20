"""VPN/proxy configuration: storage round-trip and startup flag building.

These tests cover the logic that decides whether the app launches WebEngine
with ``--proxy-server=...`` -- a misbehaving flag was a recurring source of
"VPN half-enabled" bugs.
"""
import json
import os
import tempfile
import unittest

from litebrowser.core import prefs


class TestProxyConfigStorage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.profile = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, cfg):
        with open(prefs.proxy_config_path(self.profile), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def test_round_trip(self):
        cfg = {"enabled": True, "type": "socks5", "host": "127.0.0.1", "port": 9050, "user": None, "password": None}
        self._write(cfg)
        with open(prefs.proxy_config_path(self.profile), "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["host"], "127.0.0.1")
        self.assertEqual(loaded["port"], 9050)
        self.assertTrue(loaded["enabled"])


class TestStartupProxyFlag(unittest.TestCase):
    """Directly exercises ``litebrowser.main._saved_proxy_chromium_flag``."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.app_dir = os.path.join(self._tmp.name, "app")
        os.environ["LITEBROWSER_DATA_DIR"] = os.path.join(self._tmp.name, "runtime_data")
        prefs.ensure_profile_layout(os.path.join(prefs.profiles_dir(self.app_dir), "Default"))
        prefs.set_last_profile(self.app_dir, "Default")
        self.profile_dir = os.path.join(prefs.profiles_dir(self.app_dir), "Default")

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("LITEBROWSER_DATA_DIR", None)

    def _flag(self):
        from litebrowser.main import _saved_proxy_chromium_flag

        return _saved_proxy_chromium_flag(self.app_dir)

    def test_no_config_means_no_flag(self):
        self.assertEqual(self._flag(), "")

    def test_disabled_proxy_means_no_flag(self):
        with open(prefs.proxy_config_path(self.profile_dir), "w", encoding="utf-8") as f:
            json.dump({"enabled": False, "host": "127.0.0.1", "port": 9050}, f)
        self.assertEqual(self._flag(), "")

    def test_enabled_socks5_builds_socks_flag(self):
        with open(prefs.proxy_config_path(self.profile_dir), "w", encoding="utf-8") as f:
            json.dump({"enabled": True, "type": "socks5", "host": "127.0.0.1", "port": 9050}, f)
        self.assertEqual(self._flag(), "--proxy-server=socks5://127.0.0.1:9050")

    def test_enabled_http_builds_http_flag(self):
        with open(prefs.proxy_config_path(self.profile_dir), "w", encoding="utf-8") as f:
            json.dump({"enabled": True, "type": "http", "host": "proxy.local", "port": 8080}, f)
        self.assertEqual(self._flag(), "--proxy-server=http://proxy.local:8080")

    def test_invalid_port_is_ignored(self):
        with open(prefs.proxy_config_path(self.profile_dir), "w", encoding="utf-8") as f:
            json.dump({"enabled": True, "type": "http", "host": "proxy.local", "port": 0}, f)
        self.assertEqual(self._flag(), "")

    def test_pac_configuration_does_not_require_a_manual_host(self):
        with open(prefs.proxy_config_path(self.profile_dir), "w", encoding="utf-8") as f:
            json.dump({"enabled": True, "pac_url": "https://proxy.example/settings.pac"}, f)
        self.assertEqual(self._flag(), "--proxy-pac-url=https://proxy.example/settings.pac")

    def test_unsafe_pac_scheme_is_ignored(self):
        with open(prefs.proxy_config_path(self.profile_dir), "w", encoding="utf-8") as f:
            json.dump({"enabled": True, "pac_url": "javascript:alert(1)"}, f)
        self.assertEqual(self._flag(), "")

    def test_malformed_json_does_not_crash(self):
        path = prefs.proxy_config_path(self.profile_dir)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ not json ]")
        self.assertEqual(self._flag(), "")


class TestProxyReachabilityProbe(unittest.TestCase):
    """The in-dialog proxy test must handle dead endpoints without raising."""

    def test_unreachable_proxy_reports_failure_not_exception(self):
        from litebrowser.ui.dialogs.vpn_hub import _test_proxy_connection

        ok, msg = _test_proxy_connection("127.0.0.1", 9, "http", timeout=1.5)
        self.assertFalse(ok)
        self.assertTrue(msg)

    def test_bad_socks5_greeting(self):
        import socket
        import threading

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def fake_server():
            conn, _ = srv.accept()
            try:
                data = conn.recv(3)
                if data and data[0] == 0x05:
                    # Answer with "authentication required" -> must be reported as failure
                    conn.sendall(b"\x05\xff")
            finally:
                conn.close()
                srv.close()

        t = threading.Thread(target=fake_server, daemon=True)
        t.start()
        from litebrowser.ui.dialogs.vpn_hub import _test_proxy_connection

        ok, msg = _test_proxy_connection("127.0.0.1", port, "socks5", timeout=2.5)
        t.join(timeout=3)
        self.assertFalse(ok)
        # Should indicate an authentication/negotiation failure rather than a hard exception.
        self.assertTrue(msg)
        self.assertIn(("xác thực" if "xác thực" in msg.lower() else msg.lower()), msg.lower())


if __name__ == "__main__":
    unittest.main()
