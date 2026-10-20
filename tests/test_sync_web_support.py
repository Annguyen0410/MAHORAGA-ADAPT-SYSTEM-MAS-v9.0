"""The build ships web_support without the dead legacy hub copy.

``build_exe.bat`` used to ``xcopy`` all of ``web_support`` into ``dist`` and then
``rmdir`` the ``Cục Quản Lý - Bản Đầy Đủ 1`` duplicate. cmd.exe decodes a UTF-8
batch file in the OEM code page, so that name never matched the folder on disk:
~600 MB / 29k files of dead payload were copied on *every* build and shipped next
to Mei.exe. These tests pin the Python mirror that replaced it — skip while
copying, prune what older builds left behind — and the fact that the batch file
is pure ASCII again so it cannot rot the same way.
"""
import os
import tempfile
import unittest
from unittest import mock

import litebrowser  # noqa: F401  activates the Qt compatibility shim
from litebrowser.core import app_paths

from tools import sync_web_support

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_SCRIPT = os.path.join(ROOT, "build_exe.bat")
LEGACY = app_paths.LEGACY_BUNDLED_FOLDER_MARKERS[0]

QUIET = lambda *args, **kwargs: None  # noqa: E731 - log sink for the tests


def _write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class TestDeadPayloadIsSkipped(unittest.TestCase):
    def test_skip_list_comes_from_the_app(self):
        self.assertEqual(
            tuple(sync_web_support.SKIP_DIRS),
            tuple(app_paths.LEGACY_BUNDLED_FOLDER_MARKERS),
        )

    def test_legacy_folder_is_never_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "web_support")
            dest = os.path.join(tmp, "dist", "web_support")
            _write(os.path.join(source, "Cục Quản Lý", "index.html"), "<html>")
            _write(os.path.join(source, LEGACY, "index.html"), "<html>")
            _write(os.path.join(source, LEGACY, "assets", "big.js"), "x" * 4096)

            files, total = sync_web_support.sync(source, dest, log=QUIET)

            self.assertEqual(files, 1)
            self.assertEqual(total, len("<html>"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "Cục Quản Lý", "index.html")))
            self.assertFalse(os.path.exists(os.path.join(dest, LEGACY)))

    def test_stale_copy_already_in_dist_is_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "web_support")
            dest = os.path.join(tmp, "dist", "web_support")
            _write(os.path.join(source, "hub", "index.html"))
            _write(os.path.join(dest, LEGACY, "index.html"))
            _write(os.path.join(dest, "hub", "dev.log"))

            sync_web_support.sync(source, dest, log=QUIET)

            self.assertFalse(os.path.exists(os.path.join(dest, LEGACY)))
            self.assertFalse(os.path.isfile(os.path.join(dest, "hub", "dev.log")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "hub", "index.html")))

    def test_dev_logs_are_not_shipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "web_support")
            dest = os.path.join(tmp, "dist", "web_support")
            _write(os.path.join(source, "MAS - Mahoraga Adapt System", "index.html"), "<html>")
            _write(os.path.join(source, "MAS - Mahoraga Adapt System", "server_test.log"))

            files, _ = sync_web_support.sync(source, dest, log=QUIET)

            self.assertEqual(files, 1)
            self.assertFalse(
                os.path.exists(os.path.join(dest, "MAS - Mahoraga Adapt System", "server_test.log"))
            )

    def test_private_sources_and_secrets_never_enter_a_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = os.path.join(tmp, "src"), os.path.join(tmp, "out")
            for relative in ("hub/index.html", "hub/style.css", "app/vendor/font.woff2", "app/server/.env", "app/server/sessions.json", "app/.env", "app/sessions.json", "app/config.local.json", "app/node_modules/x.js", "profiles/p/index.html", "app/tests/test.js"):
                _write(os.path.join(source, relative))
            files, _ = sync_web_support.sync(source, dest, log=QUIET)
            self.assertEqual(files, 3)
            actual = {os.path.relpath(os.path.join(root, name), dest).replace(os.sep, '/') for root, _, names in os.walk(dest) for name in names}
            self.assertEqual(actual, {"hub/index.html", "hub/style.css", "app/vendor/font.woff2"})

    def test_stale_private_payload_is_pruned_without_reading_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = os.path.join(tmp, "src"), os.path.join(tmp, "out")
            _write(os.path.join(source, "hub", "index.html"), "fresh")
            for relative in ("hub/index.html", "app/server/.env", "app/server/sessions.json", "app/.env", "app/config.local.json", "app/node_modules/x.js", "profiles/p/index.html", "app/old.log", ".hidden/secret.json"):
                _write(os.path.join(dest, relative), "old")
            sync_web_support.sync(source, dest, log=QUIET)
            actual = {os.path.relpath(os.path.join(root, name), dest).replace(os.sep, '/') for root, _, names in os.walk(dest) for name in names}
            self.assertEqual(actual, {"hub/index.html"})
            with open(os.path.join(dest, "hub", "index.html"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "fresh")

    def test_failed_private_cleanup_fails_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = os.path.join(tmp, "src"), os.path.join(tmp, "out")
            _write(os.path.join(source, "index.html"))
            _write(os.path.join(dest, "app", "server", ".env"))
            with mock.patch.object(sync_web_support.shutil, "rmtree", side_effect=PermissionError("locked")):
                self.assertEqual(sync_web_support.main([source, dest]), 1)
            self.assertFalse(os.path.exists(os.path.join(dest, "index.html")))

    def test_failed_copy_fails_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "src")
            _write(os.path.join(source, "index.html"))
            with mock.patch.object(sync_web_support.shutil, "copy2", side_effect=OSError("disk full")):
                self.assertEqual(sync_web_support.main([source, os.path.join(tmp, "out")]), 1)

    def test_public_bundle_sources_survive_ignore_rules(self):
        import subprocess
        git_dir = os.path.join(ROOT, '.git')
        if not os.path.exists(git_dir):
            self.skipTest('Git metadata absent')
        paths = [str(path).replace(os.sep, '/') for path in sync_web_support.public_files(os.path.join(ROOT, 'web_support')) if not any(part in ('extension',) for part in path.parts) and path.name != 'replace_colors.js']
        result = subprocess.run(['git', 'check-ignore', '-z', '--stdin'], input='\0'.join('web_support/' + path for path in paths).encode('utf-8') + b'\0', capture_output=True, cwd=ROOT, timeout=30)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertEqual(result.stdout, b'', 'Public bundle assets must not disappear from a clean checkout')
        for private in ('web_support/MAS - Mahoraga Adapt System/server/.env', 'web_support/MAS - Mahoraga Adapt System/server/sessions.json'):
            result = subprocess.run(['git', 'check-ignore', private], capture_output=True, cwd=ROOT, timeout=30)
            self.assertEqual(result.returncode, 0, 'Private stores must stay ignored')

    def test_nested_or_identical_destinations_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for dest in (tmp, os.path.join(tmp, "out")):
                with self.assertRaises(ValueError):
                    sync_web_support.sync(tmp, dest, log=QUIET)

    def test_prune_reports_nothing_for_a_missing_dest(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sync_web_support.prune(os.path.join(tmp, "nope"), log=QUIET), 0)


class TestCommandLine(unittest.TestCase):
    def test_explicit_paths_are_synced(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "src")
            dest = os.path.join(tmp, "out")
            _write(os.path.join(source, "chain.json"), "{}")

            self.assertEqual(sync_web_support.main([source, dest]), 0)
            self.assertTrue(os.path.isfile(os.path.join(dest, "chain.json")))

    def test_missing_source_fails_instead_of_shipping_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sync_web_support.main([os.path.join(tmp, "missing")]), 1)


class TestBuildScriptDelegates(unittest.TestCase):
    def test_build_script_is_pure_ascii(self):
        # The bug itself: cmd.exe reads the batch file in the OEM code page, so a
        # non-ASCII byte in a path there can never match what is on disk.
        with open(BUILD_SCRIPT, "rb") as handle:
            data = handle.read()
        self.assertEqual([byte for byte in data if byte > 127], [])

    def test_build_script_calls_the_sync_tool(self):
        with open(BUILD_SCRIPT, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("tools\\sync_web_support.py", text)
        self.assertNotIn("xcopy", text)


if __name__ == "__main__":
    unittest.main()
