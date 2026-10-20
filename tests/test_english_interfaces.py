"""English shipped interfaces, stable identifiers and key-free management QA."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from litebrowser.core import app_paths, commands
from litebrowser.services import study_ritual

ROOT = Path(__file__).resolve().parents[1]
VIETNAMESE = re.compile(r"[đĐăĂơƠưƯạ-ỹ]")


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.hidden += 1
        for name, value in attrs:
            if name in ("title", "placeholder", "aria-label") and value:
                self.text.append(value)

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


class TestEnglishInterfaces(unittest.TestCase):
    def test_display_registry_and_pours_are_english_without_renaming_ids(self):
        for site in app_paths.BUNDLED_SITES:
            self.assertIsNone(VIETNAMESE.search(site["display"]))
        for command in commands.COMMANDS:
            self.assertIsNone(VIETNAMESE.search(command.description))
        self.assertEqual(study_ritual.pour_ids(), ("ca-phe-den", "tra-sen", "ca-phe-sua", "tra-dao", "bac-xiu", "nuoc-cam"))
        for _, display, _ in study_ritual.POURS:
            self.assertIsNone(VIETNAMESE.search(display))
        manifest = json.loads((ROOT / "litebrowser/data/chain.json").read_text(encoding="utf-8"))
        for app in manifest["apps"]:
            self.assertIsNone(VIETNAMESE.search(app["name"] + app["subtitle"]))
        self.assertEqual(next(app["folder"] for app in manifest["apps"] if app["id"] == "cucquanly"), "Cục Quản Lý")

    def test_desktop_string_literals_are_english(self):
        for relative in ("litebrowser/ui/personal_window.py", "litebrowser/ui/main_window/window.py", "litebrowser/ui/shell/pages.py", "litebrowser/services/android_bridge_service.py", "tools/publish_release.py"):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertIsNone(VIETNAMESE.search(node.value), f"{relative}:{node.lineno}: {node.value}")

    def test_public_web_and_extension_visible_labels_are_english(self):
        hub = ROOT / "web_support/Cục Quản Lý"
        files = [ROOT / "Extensions/tab-window-bridge/popup.html", ROOT / "web_support/hub/index.html", ROOT / "web_support/boitoan/index.html", hub / "index.html", *hub.glob("*/index.html")]
        for path in files:
            if not path.exists():
                continue  # Some bundled apps are absent in a clean source checkout.
            text = path.read_text(encoding="utf-8")
            self.assertIn('lang="en"', text, str(path))
            parser = VisibleText()
            parser.feed(text)
            visible = " ".join(parser.text).replace("Ân Nguyễn", "")  # Proper names are not translated.
            self.assertIsNone(VIETNAMESE.search(visible), str(path))

    def test_hub_card_links_do_not_nest_anchors(self):
        path = ROOT / "web_support/hub/index.html"
        if not path.exists():
            self.skipTest("Bundled hub is absent")
        text = path.read_text(encoding="utf-8")
        self.assertIn("'<div class=\"card\"><a class=\"card-main\"", text)
        self.assertIn("+ '</a>'\n            + alt\n            + '</div>'", text)
        self.assertNotIn("'<a class=\"card\"", text)

    @unittest.skipUnless(shutil.which("node"), "Node is required for web regression checks")
    def test_leaderboard_storage_and_scoring(self):
        if not (ROOT / "web_support/World Leaderboard/script.js").is_file():
            self.skipTest("Bundled leaderboard is absent")
        result = subprocess.run([shutil.which("node"), str(ROOT / "tests/js/leaderboard-reliability.test.js")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node is required for web regression checks")
    def test_management_storage_and_rendering(self):
        if not (ROOT / "web_support/Cục Quản Lý/Hệ Thống Toàn Diện Cá Nhân/app.js").is_file():
            self.skipTest("Bundled management app is absent")
        result = subprocess.run([shutil.which("node"), str(ROOT / "tests/js/management-reliability.test.js")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checks passed", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node is required for web regression checks")
    def test_management_export_and_restore(self):
        if not (ROOT / "web_support/Cục Quản Lý/Hệ Thống Trích Xuất/app.js").is_file():
            self.skipTest("Bundled management app is absent")
        result = subprocess.run([shutil.which("node"), str(ROOT / "tests/js/management-export.test.js")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("84 export combinations", result.stdout)
