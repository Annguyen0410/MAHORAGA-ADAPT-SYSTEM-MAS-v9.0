"""Release versions are one unambiguous shape: four numeric parts.

Pre-release builds live on GitHub pre-release tags and never enter the stable
channel manifest. The updater must refuse a suffix rather than treating it as a
zero, which is how a preview could otherwise replace a stable install.
"""
import unittest

from litebrowser.services import update_service


class TestVersionScheme(unittest.TestCase):
    def test_normalize_four_part(self):
        self.assertEqual(update_service._normalize_version("0.6.8.0"), (0, 6, 8, 0))

    def test_newer_remote_detected(self):
        self.assertTrue(update_service._version_is_newer("0.6.9.0", "0.6.8.0"))

    def test_older_remote_not_detected(self):
        self.assertFalse(update_service._version_is_newer("0.6.7.0", "0.6.8.0"))

    def test_milestone_jump_detected(self):
        self.assertTrue(update_service._version_is_newer("1.0.0.0", "0.6.8.0"))

    def test_component_width_does_not_create_a_phantom_update(self):
        self.assertFalse(update_service._version_is_newer("0.6.9.0", "0.6.9.0"))
        with self.assertRaises(ValueError):
            update_service._version_is_newer("0.6.9", "0.6.9.0")

    def test_prerelease_suffix_is_refused(self):
        for value in ("0.6.8.0-beta", "1.0.0.0-alpha.1", "1.0.0.0-rc1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    update_service.parse_version(value)

    def test_malformed_values_are_refused(self):
        for value in ("", "1", "1.2", "1.2.3", "1.2.3.4.5", "1.2.3.x", "v1.2.3.4"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    update_service.parse_version(value)


if __name__ == "__main__":
    unittest.main()
