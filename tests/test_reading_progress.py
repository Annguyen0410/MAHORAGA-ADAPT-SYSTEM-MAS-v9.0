import tempfile
import unittest

from litebrowser.services import life_service


class ReadingProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def test_invalid_progress_does_not_overwrite_existing_value(self):
        page = life_service.add_saved_page(self.base, "Long read", "https://example.test/read")
        life_service.set_reading_progress(self.base, page["url"], 42)

        result = life_service.set_reading_progress(self.base, page["url"], "not a percentage")

        self.assertIsNone(result)
        self.assertEqual(life_service.continue_reading_page(self.base)["read_percent"], 42)

    def test_continue_reading_skips_corrupt_percentages(self):
        life_service.save_saved_pages(self.base, [
            {"id": "bad", "title": "Corrupt", "url": "https://example.test/bad", "read_percent": "many"},
            {"id": "good", "title": "Good", "url": "https://example.test/good", "read_percent": 33},
        ])

        self.assertEqual(life_service.continue_reading_page(self.base)["id"], "good")

    def test_progress_clamps_to_valid_range_and_completed_pages_leave_queue(self):
        page = life_service.add_saved_page(self.base, "Boundaries", "https://example.test/boundaries")

        completed = life_service.set_reading_progress(self.base, page["url"], 500)
        self.assertEqual(completed["read_percent"], 100)
        self.assertIsNone(life_service.continue_reading_page(self.base))

        reset = life_service.set_reading_progress(self.base, page["url"], -25)
        self.assertEqual(reset["read_percent"], 0)
        self.assertIsNone(life_service.continue_reading_page(self.base))


if __name__ == "__main__":
    unittest.main()
