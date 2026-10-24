"""The web_support ZIP is the only payload extracted beside the executable.

These tests hold the release writer to the same allow-list as the build copy:
private folders, secrets, tests and traversal entries must never ship, and a
bundle without its hub entry point must fail without destroying the previous
good ZIP.
"""
import os
import tempfile
import unittest
import zipfile

from tools import publish_release, sync_web_support


def _write(root: str, relative: str, text: str = "x") -> None:
    path = os.path.join(root, *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class TestPublicRelative(unittest.TestCase):
    def test_accepts_public_assets_with_unicode_folders(self):
        self.assertTrue(sync_web_support.is_public_relative("hub/index.html"))
        self.assertTrue(sync_web_support.is_public_relative("Cục Quản Lý/index.html"))
        self.assertTrue(sync_web_support.is_public_relative("assets/app.js"))

    def test_rejects_private_and_traversal_entries(self):
        for name in (
            "server/secret.json",
            "node_modules/pkg/index.js",
            "profiles/Default/prefs.json",
            "config.local.json",
            "package.json",
            "notes.txt",
            "app.log",
            ".git/config",
            "hub/../app.js",
            "../app.js",
            "/etc/passwd",
            "C:\\Mei\\profile.json",
        ):
            with self.subTest(name=name):
                self.assertFalse(sync_web_support.is_public_relative(name))


class TestZipWebSupport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = os.path.join(self.tmp.name, "web_support")
        self.out = os.path.join(self.tmp.name, "Mei-web_support.zip")
        _write(self.source, "hub/index.html", "<html>hub</html>")
        _write(self.source, "hub/app.js", "console.log(1)")
        _write(self.source, "Cục Quản Lý/index.html", "<html>unicode</html>")
        _write(self.source, "server/secret.json", '{"token": "do-not-ship"}')
        _write(self.source, "node_modules/pkg/index.js", "x")
        _write(self.source, "config.local.json", "{}")
        _write(self.source, "package.json", "{}")
        _write(self.source, "notes.txt", "private")
        _write(self.source, ".hidden", "x")

    def test_bundle_contains_only_public_assets(self):
        publish_release.zip_web_support(self.source, self.out)
        with zipfile.ZipFile(self.out) as bundle:
            names = sorted(bundle.namelist())
        self.assertEqual(
            names,
            ["Cục Quản Lý/index.html", "hub/app.js", "hub/index.html"],
        )
        self.assertTrue(all(sync_web_support.is_public_relative(name) for name in names))

    def test_missing_entry_point_preserves_the_previous_bundle(self):
        with open(self.out, "wb") as handle:
            handle.write(b"previous good bundle")
        empty = os.path.join(self.tmp.name, "empty")
        _write(empty, "README.md", "not a site")
        with self.assertRaises(ValueError):
            publish_release.zip_web_support(empty, self.out)
        with open(self.out, "rb") as handle:
            self.assertEqual(handle.read(), b"previous good bundle")

    def test_verify_rejects_a_handcrafted_private_archive(self):
        bad = os.path.join(self.tmp.name, "bad.zip")
        with zipfile.ZipFile(bad, "w") as bundle:
            bundle.writestr("hub/index.html", "<html></html>")
            bundle.writestr("../escape.js", "x")
            bundle.writestr("server/secret.json", "{}")
        with self.assertRaises(ValueError) as caught:
            publish_release.verify_web_support_zip(bad)
        self.assertIn("non-public", str(caught.exception))

    def test_verify_rejects_an_archive_without_hub(self):
        bad = os.path.join(self.tmp.name, "nohub.zip")
        with zipfile.ZipFile(bad, "w") as bundle:
            bundle.writestr("other/index.html", "<html></html>")
        with self.assertRaises(ValueError) as caught:
            publish_release.verify_web_support_zip(bad)
        self.assertIn("hub/index.html", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
