import unittest

from litebrowser.core import theme_data


class ArtThemeTests(unittest.TestCase):
    def test_new_theme_families_have_complete_palette_tokens(self):
        required = {
            "MAIN_BG", "MAIN_BG_ALT", "SIDEBAR_BG", "SIDEBAR_BORDER", "CARD_BG",
            "INPUT_BG", "INPUT_BORDER", "INPUT_FOCUS", "TEXT", "TEXT_MUTED",
            "ACCENT", "ACCENT_HOVER", "ACCENT_SOFT", "ITEM_HOVER", "ITEM_SELECTED",
            "ITEM_SELECTED_BORDER", "BUTTON_BG", "BUTTON_HOVER", "BUTTON_TEXT",
            "MENU_BG", "MENU_ITEM_SEL", "BORDER_SOFT", "DANGER", "SUCCESS",
        }
        expected = {
            "aurora-glass", "sakura-twilight", "cyberpunk-neon", "midnight-amoled",
            "arctic-aurora", "retro-terminal", "paper-studio", "monochrome-pro",
            "dreamscape", "solarized-focus", "high-contrast", "glasshouse",
        }
        self.assertTrue(expected.issubset(theme_data.PALETTES))
        for name in expected:
            with self.subTest(theme=name):
                self.assertTrue(required.issubset(theme_data.PALETTES[name]))
                resolved = theme_data._palette(name)
                self.assertGreaterEqual(
                    theme_data.contrast_ratio(resolved["TEXT"], resolved["MAIN_BG"]), 4.5
                )
                self.assertEqual(theme_data.theme_variant(name, dark=False), name)


if __name__ == "__main__":
    unittest.main()
