"""Export center: HTML site is well-formed, MD bundle round-trips."""
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from litebrowser.core import prefs
from litebrowser.services import export_service, personal_service


class TestExport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "profile"))
        personal_service.create_note(self.base, "Alpha", "# Alpha\n\nbody one", category="General")
        personal_service.create_note(self.base, "Beta", "# Beta\n\n[[Alpha]] link", category="Work")

    def tearDown(self):
        self._tmp.cleanup()

    def test_md_zip_contains_notes(self):
        out = os.path.join(self._tmp.name, "notes-md.zip")
        count = export_service.export_notes_md_zip(self.base, out)
        self.assertEqual(count, 2)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            self.assertIn("index.md", names)
            self.assertTrue(any(n.endswith(".md") and "Alpha" in n for n in names))

    def test_html_site_is_wellformed(self):
        out = os.path.join(self._tmp.name, "notes-site.zip")
        count = export_service.export_notes_html(self.base, out)
        self.assertEqual(count, 2)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            self.assertIn("index.html", names)
            index = zf.read("index.html").decode("utf-8")
        # The list must be INSIDE the document, not appended after </html>.
        self.assertIn("Alpha", index)
        self.assertIn("Beta", index)
        self.assertTrue(index.rstrip().endswith("</html>"), "index must end with </html>")
        self.assertEqual(index.count("</html>"), 1)

    def test_unsafe_links_are_not_executable(self):
        tokens = {key: "#222222" for key in ("MAIN_BG", "TEXT", "ACCENT_HOVER", "ACCENT", "MAIN_BG_ALT", "BORDER_SOFT", "TEXT_MUTED")}
        page = export_service._render_html_page("Test", "[bad](javascript:alert(1)) [data](data:text/html,hi) [good](https://example.com)", tokens)
        self.assertNotIn('href="javascript:', page)
        self.assertNotIn('href="data:', page)
        self.assertIn('href="https://example.com"', page)

    def test_failed_export_retains_previous_archive(self):
        out = os.path.join(self._tmp.name, "existing.zip")
        with open(out, "wb") as handle:
            handle.write(b"original archive")
        with mock.patch.object(export_service.zipfile.ZipFile, "writestr", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                export_service.export_notes_md_zip(self.base, out)
        with open(out, "rb") as handle:
            self.assertEqual(handle.read(), b"original archive")

    def test_html_reexport_does_not_include_deleted_pages(self):
        out = os.path.join(self._tmp.name, "site.zip")
        export_service.export_notes_html(self.base, out)
        beta = next(note for note in personal_service.list_notes(self.base) if note["title"] == "Beta")
        personal_service.delete_note(self.base, beta["id"])
        export_service.export_notes_html(self.base, out)
        with zipfile.ZipFile(out) as archive:
            self.assertFalse(any("Beta" in name for name in archive.namelist()))

    def test_empty_vault_exports_zero(self):
        empty = prefs.ensure_profile_layout(os.path.join(self._tmp.name, "empty"))
        out = os.path.join(self._tmp.name, "e.zip")
        self.assertEqual(export_service.export_notes_html(empty, out), 0)
        self.assertEqual(export_service.export_notes_md_zip(empty, out), 0)


if __name__ == "__main__":
    unittest.main()
