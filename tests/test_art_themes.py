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
            "forest-sanctuary", "ocean-depths", "sunset-dusk",
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

    def test_every_new_family_has_its_own_selectable_palette(self):
        expected = {
            "aurora-glass", "sakura-twilight", "cyberpunk-neon", "midnight-amoled",
            "arctic-aurora", "forest-sanctuary", "ocean-depths", "retro-terminal",
            "paper-studio", "monochrome-pro", "sunset-dusk", "dreamscape",
            "solarized-focus", "high-contrast", "glasshouse",
        }
        signatures = set()
        for name in expected:
            with self.subTest(theme=name):
                self.assertTrue(theme_data.theme_display_name(name))
                signature = tuple(sorted(theme_data.PALETTES[name].items()))
                self.assertNotIn(signature, signatures)
                signatures.add(signature)

    def test_primary_text_keeps_readable_contrast_across_major_surfaces(self):
        families = {
            "aurora-glass", "sakura-twilight", "cyberpunk-neon", "midnight-amoled",
            "arctic-aurora", "forest-sanctuary", "ocean-depths", "retro-terminal",
            "paper-studio", "monochrome-pro", "sunset-dusk", "dreamscape",
            "solarized-focus", "high-contrast", "glasshouse",
        }
        surfaces = ("MAIN_BG", "MAIN_BG_ALT", "SIDEBAR_BG", "CARD_BG", "INPUT_BG", "MENU_BG")
        for family in families:
            palette = theme_data._palette(family)
            for surface in surfaces:
                with self.subTest(theme=family, surface=surface):
                    ratio = theme_data.contrast_ratio(palette["TEXT"], palette[surface])
                    self.assertGreaterEqual(ratio, 4.5)

    def test_muted_text_remains_legible_on_reading_surfaces(self):
        families = {
            "aurora-glass", "sakura-twilight", "cyberpunk-neon", "midnight-amoled",
            "arctic-aurora", "forest-sanctuary", "ocean-depths", "retro-terminal",
            "paper-studio", "monochrome-pro", "sunset-dusk", "dreamscape",
            "solarized-focus", "high-contrast", "glasshouse",
        }
        for family in families:
            palette = theme_data._palette(family)
            for surface in ("MAIN_BG", "CARD_BG", "INPUT_BG"):
                with self.subTest(theme=family, surface=surface):
                    ratio = theme_data.contrast_ratio(palette["TEXT_MUTED"], palette[surface])
                    self.assertGreaterEqual(ratio, 4.5)


if __name__ == "__main__":
    unittest.main()
