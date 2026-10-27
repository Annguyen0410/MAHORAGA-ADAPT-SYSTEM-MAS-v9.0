"""New-tab desk layout and link-label checks.

These assertions cover the parts a screenshot review cannot: the page keeps
its responsive grid, uses existing title/URL data for labels, and never lets a
rejected URL become a link.
"""

import os
import tempfile
import unittest

from litebrowser.browser import new_tab_page
from litebrowser.core import prefs


class TestNewTabDeskLayout(unittest.TestCase):
    def _html(self, bookmarks=None, history=None, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            base = prefs.ensure_profile_layout(os.path.join(tmp, "profile"))
            if bookmarks:
                prefs.save_bookmarks(base, bookmarks)
            if history:
                prefs.save_history_entries(base, history)
            return new_tab_page.build_new_tab_html(base, **kwargs)

    def test_wide_page_has_a_main_column_and_a_recent_rail(self):
        html = self._html()
        self.assertIn('class="desk-main"', html)
        self.assertIn('class="desk-side"', html)
        self.assertIn('class="tiles hub-grid"', html)
        self.assertIn('class="tiles shelf-grid"', html)
        self.assertIn("grid-template-columns: 1fr", html)
        self.assertIn("Project Hub", html)

    def test_bookmark_title_and_host_are_both_scannable(self):
        html = self._html(
            bookmarks=[{"title": "Reading <list>", "url": "https://www.example.com/notes/reading-list?x=1"}],
        )
        self.assertIn('class="tile shelf-tile"', html)
        self.assertIn("example.com", html)
        self.assertIn("Reading &lt;list&gt;", html)
        self.assertIn("https://www.example.com/notes/reading-list?x=1", html)

    def test_recent_rows_use_url_path_labels_without_inventing_metadata(self):
        html = self._html(history=[(2, "https://docs.example.test/guide/getting-started?x=1")])
        self.assertIn('class="recent-row"', html)
        self.assertIn("getting started", html)
        self.assertIn("docs.example.test/guide/getting-started", html)

    def test_invalid_bookmark_scheme_never_renders_as_a_link(self):
        html = self._html(
            bookmarks=[
                {"title": "Bad", "url": "javascript:alert(1)"},
                {"title": "Good", "url": "https://safe.example.test/page"},
            ],
        )
        self.assertNotIn("javascript:", html.lower())
        self.assertIn("https://safe.example.test/page", html)

    def test_search_is_a_real_submit_with_an_accessible_label(self):
        html = self._html(search_engine="DuckDuckGo")
        self.assertIn('action="https://duckduckgo.com/"', html)
        self.assertIn('role="search"', html)
        self.assertIn('type="submit"', html)
        self.assertIn('aria-label="Search the web or enter a URL"', html)


if __name__ == "__main__":
    unittest.main()
