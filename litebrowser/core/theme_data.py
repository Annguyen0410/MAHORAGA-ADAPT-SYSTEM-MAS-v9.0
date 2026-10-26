"""Pure theme data and color logic (no Qt imports).

Palettes, accent presets, display labels and the hex-blending helpers live
here so the data layer (core/services) can validate theme + accent names
without importing the Qt UI. ``litebrowser.ui.theme`` re-exports everything
below; new code should import from here when it needs no widgets.
"""


PALETTES = {
    # ============================ LIGHT — day café ============================
    "minimal": {
        # Quiet Table (default): warm paper, espresso ink, muted sage, a line of
        # clay.  Deliberately low-chroma: the page should read as paper on a
        # table in daylight, not as a tinted dashboard.
        "MAIN_BG": "#F7F3EA",
        "MAIN_BG_ALT": "#EFE8DB",
        "SIDEBAR_BG": "#F2ECDF",
        "SIDEBAR_BORDER": "#DED3C0",
        "CARD_BG": "#FCF9F2",
        "INPUT_BG": "#FFFDF8",
        "INPUT_BORDER": "#D9CEBC",
        "INPUT_FOCUS": "#5F6E55",
        "TEXT": "#302D27",
        "TEXT_MUTED": "#6B6459",
        "ACCENT": "#5F6E55",
        "ACCENT_HOVER": "#47543D",
        "ACCENT_SOFT": "#E7EADF",
        "ITEM_HOVER": "#F1EBDF",
        "ITEM_SELECTED": "#E4E8DB",
        "ITEM_SELECTED_BORDER": "#5F6E55",
        "BUTTON_BG": "#F4EFE4",
        "BUTTON_HOVER": "#EBE3D3",
        "BUTTON_TEXT": "#302D27",
        "MENU_BG": "#FCF9F2",
        "MENU_ITEM_SEL": "#E8EBDF",
        "BORDER_SOFT": "#E3DACA",
        "DANGER": "#A8492F",
        "SUCCESS": "#4E6B45",
    },
    "latte": {
        # Honey Crème: golden, sunlit honey tones — a warmer, sweeter café.
        "MAIN_BG": "#FCF7EC",
        "MAIN_BG_ALT": "#F5EBD6",
        "SIDEBAR_BG": "#F8F0DE",
        "SIDEBAR_BORDER": "#E7D8B8",
        "CARD_BG": "#FFFEF8",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#DECFA8",
        "INPUT_FOCUS": "#A87B2A",
        "TEXT": "#2F2513",
        "TEXT_MUTED": "#7E6B48",
        "ACCENT": "#B4832A",
        "ACCENT_HOVER": "#CC9938",
        "ACCENT_SOFT": "#F7E9C8",
        "ITEM_HOVER": "#F6EDD8",
        "ITEM_SELECTED": "#F0E2BC",
        "ITEM_SELECTED_BORDER": "#B4832A",
        "BUTTON_BG": "#F5ECD6",
        "BUTTON_HOVER": "#ECDFC2",
        "BUTTON_TEXT": "#2F2513",
        "MENU_BG": "#FFFEF8",
        "MENU_ITEM_SEL": "#F1E3C0",
        "BORDER_SOFT": "#EDE1C6",
        "DANGER": "#BF4E33",
        "SUCCESS": "#6A8434",
    },
    "rose-day": {
        # Sakura Café: rose-latte pinks — soft, airy, a little playful.
        "MAIN_BG": "#FCF5F4",
        "MAIN_BG_ALT": "#F5E7E6",
        "SIDEBAR_BG": "#F8EDEC",
        "SIDEBAR_BORDER": "#E7CBCA",
        "CARD_BG": "#FFFCFC",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#E5C8C6",
        "INPUT_FOCUS": "#C14E5E",
        "TEXT": "#331F24",
        "TEXT_MUTED": "#8A6570",
        "ACCENT": "#C14E5E",
        "ACCENT_HOVER": "#DB6577",
        "ACCENT_SOFT": "#F9E0E2",
        "ITEM_HOVER": "#F8ECEB",
        "ITEM_SELECTED": "#F4DCDD",
        "ITEM_SELECTED_BORDER": "#C14E5E",
        "BUTTON_BG": "#F8ECEA",
        "BUTTON_HOVER": "#F1DEDB",
        "BUTTON_TEXT": "#331F24",
        "MENU_BG": "#FFFCFC",
        "MENU_ITEM_SEL": "#F5DEDF",
        "BORDER_SOFT": "#EFD9D7",
        "DANGER": "#B93A4A",
        "SUCCESS": "#5F8A50",
    },
    "dawn": {
        # Café Dawn: peachy first-light — terracotta warmth on cream porcelain.
        "MAIN_BG": "#FDF6EF",
        "MAIN_BG_ALT": "#F9ECDF",
        "SIDEBAR_BG": "#FBF0E4",
        "SIDEBAR_BORDER": "#EFD6BE",
        "CARD_BG": "#FFFDFA",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#E8CDB2",
        "INPUT_FOCUS": "#C56A3A",
        "TEXT": "#33241A",
        "TEXT_MUTED": "#83644E",
        "ACCENT": "#C76B35",
        "ACCENT_HOVER": "#E08148",
        "ACCENT_SOFT": "#FBE7D2",
        "ITEM_HOVER": "#F9EEE0",
        "ITEM_SELECTED": "#F4DFC6",
        "ITEM_SELECTED_BORDER": "#C76B35",
        "BUTTON_BG": "#F8EFE2",
        "BUTTON_HOVER": "#F1E3CF",
        "BUTTON_TEXT": "#33241A",
        "MENU_BG": "#FFFDFA",
        "MENU_ITEM_SEL": "#F4E2CC",
        "BORDER_SOFT": "#F0E2CE",
        "DANGER": "#BC4436",
        "SUCCESS": "#5F8A4E",
    },
    "matcha-day": {
        # Matcha Latte: whisked-green freshness over rice-paper cream.
        "MAIN_BG": "#F8F9F0",
        "MAIN_BG_ALT": "#EFF2E2",
        "SIDEBAR_BG": "#F2F5E7",
        "SIDEBAR_BORDER": "#D9E0C2",
        "CARD_BG": "#FCFDF7",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#D2D9B8",
        "INPUT_FOCUS": "#5E7F3E",
        "TEXT": "#262A1B",
        "TEXT_MUTED": "#61694C",
        "ACCENT": "#6E9440",
        "ACCENT_HOVER": "#86AC52",
        "ACCENT_SOFT": "#E7EFCE",
        "ITEM_HOVER": "#EFF3E0",
        "ITEM_SELECTED": "#E3EBC8",
        "ITEM_SELECTED_BORDER": "#6E9440",
        "BUTTON_BG": "#F0F4E2",
        "BUTTON_HOVER": "#E5ECCE",
        "BUTTON_TEXT": "#262A1B",
        "MENU_BG": "#FCFDF7",
        "MENU_ITEM_SEL": "#E9F0D2",
        "BORDER_SOFT": "#E3E8D0",
        "DANGER": "#B8503E",
        "SUCCESS": "#55803C",
    },
    "sand-day": {
        # Morning Crème: cool porcelain cream with a slate-mocha accent — the
        # most neutral, office-friendly light theme.
        "MAIN_BG": "#F6F3EC",
        "MAIN_BG_ALT": "#ECE7DC",
        "SIDEBAR_BG": "#EFEAE0",
        "SIDEBAR_BORDER": "#D4CBB6",
        "CARD_BG": "#FCFAF4",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#D6CCB6",
        "INPUT_FOCUS": "#7A6248",
        "TEXT": "#2B2620",
        "TEXT_MUTED": "#726A5B",
        "ACCENT": "#8C6D46",
        "ACCENT_HOVER": "#A58052",
        "ACCENT_SOFT": "#EDE4D0",
        "ITEM_HOVER": "#EFE9DB",
        "ITEM_SELECTED": "#E7DCC4",
        "ITEM_SELECTED_BORDER": "#8C6D46",
        "BUTTON_BG": "#F1EBDD",
        "BUTTON_HOVER": "#E5DCCA",
        "BUTTON_TEXT": "#2B2620",
        "MENU_BG": "#FCFAF4",
        "MENU_ITEM_SEL": "#EDE3CC",
        "BORDER_SOFT": "#E6DECB",
        "DANGER": "#BC4A38",
        "SUCCESS": "#5F8348",
    },
    # ============================ DARK — night café ===========================
    "cafe-night": {
        # Espresso House: deep roasted espresso wood, glowing amber lamps.
        "MAIN_BG": "#14100B",
        "MAIN_BG_ALT": "#1B150D",
        "SIDEBAR_BG": "#171208",
        "SIDEBAR_BORDER": "#332614",
        "CARD_BG": "#1F1810",
        "INPUT_BG": "#241C11",
        "INPUT_BORDER": "#4A3820",
        "INPUT_FOCUS": "#E5B763",
        "TEXT": "#F7EDD9",
        "TEXT_MUTED": "#BCA988",
        "ACCENT": "#D9A94F",
        "ACCENT_HOVER": "#F0C168",
        "ACCENT_SOFT": "#43301A",
        "ITEM_HOVER": "#2B2113",
        "ITEM_SELECTED": "#46331A",
        "ITEM_SELECTED_BORDER": "#F0C168",
        "BUTTON_BG": "#2E2314",
        "BUTTON_HOVER": "#3B2C19",
        "BUTTON_TEXT": "#F7EDD9",
        "MENU_BG": "#1F1810",
        "MENU_ITEM_SEL": "#51391C",
        "BORDER_SOFT": "#2B2010",
        "DANGER": "#E57463",
        "SUCCESS": "#97AE6C",
    },
    "minimal-night": {
        # Quiet Table Night (default dark): a dim espresso lounge — deep
        # brown-charcoal walls, warm off-white ink, a low lamp of sage.
        "MAIN_BG": "#171410",
        "MAIN_BG_ALT": "#1F1A15",
        "SIDEBAR_BG": "#1B1712",
        "SIDEBAR_BORDER": "#342C22",
        "CARD_BG": "#201B16",
        "INPUT_BG": "#241F19",
        "INPUT_BORDER": "#3D3428",
        "INPUT_FOCUS": "#A9BE9B",
        "TEXT": "#F2EBDF",
        "TEXT_MUTED": "#B9AE9D",
        "ACCENT": "#93A886",
        "ACCENT_HOVER": "#C2D3B4",
        "ACCENT_SOFT": "#2A3226",
        "ITEM_HOVER": "#262019",
        "ITEM_SELECTED": "#2E3529",
        "ITEM_SELECTED_BORDER": "#93A886",
        "BUTTON_BG": "#262019",
        "BUTTON_HOVER": "#302920",
        "BUTTON_TEXT": "#F2EBDF",
        "MENU_BG": "#211C16",
        "MENU_ITEM_SEL": "#2C3527",
        "BORDER_SOFT": "#2E2820",
        "DANGER": "#E0866A",
        "SUCCESS": "#9DBE8A",
    },
    "ocean-night": {
        # Café Azul: deep blue-slate night with a luminous teal counter.
        "MAIN_BG": "#0D1219",
        "MAIN_BG_ALT": "#131B26",
        "SIDEBAR_BG": "#101721",
        "SIDEBAR_BORDER": "#24344A",
        "CARD_BG": "#17212E",
        "INPUT_BG": "#1B2634",
        "INPUT_BORDER": "#384A64",
        "INPUT_FOCUS": "#5CC9B9",
        "TEXT": "#EAF1F9",
        "TEXT_MUTED": "#9AAEC3",
        "ACCENT": "#42B8A9",
        "ACCENT_HOVER": "#63D4C4",
        "ACCENT_SOFT": "#173B39",
        "ITEM_HOVER": "#202E3F",
        "ITEM_SELECTED": "#1E4140",
        "ITEM_SELECTED_BORDER": "#63D4C4",
        "BUTTON_BG": "#223041",
        "BUTTON_HOVER": "#2D3F53",
        "BUTTON_TEXT": "#EAF1F9",
        "MENU_BG": "#151E2A",
        "MENU_ITEM_SEL": "#274A4C",
        "BORDER_SOFT": "#223041",
        "DANGER": "#E87464",
        "SUCCESS": "#74C284",
    },
    "forest-night": {
        # Matcha Night: pine-dark walls, moss trim, spring matcha glow.
        "MAIN_BG": "#0F1712",
        "MAIN_BG_ALT": "#14201A",
        "SIDEBAR_BG": "#111B15",
        "SIDEBAR_BORDER": "#29402F",
        "CARD_BG": "#18251D",
        "INPUT_BG": "#1C2B21",
        "INPUT_BORDER": "#37523F",
        "INPUT_FOCUS": "#8ADDA9",
        "TEXT": "#ECF3EC",
        "TEXT_MUTED": "#A3B8A8",
        "ACCENT": "#57BD80",
        "ACCENT_HOVER": "#7BDBA2",
        "ACCENT_SOFT": "#1D3826",
        "ITEM_HOVER": "#202F25",
        "ITEM_SELECTED": "#214230",
        "ITEM_SELECTED_BORDER": "#7BDBA2",
        "BUTTON_BG": "#223127",
        "BUTTON_HOVER": "#2C4030",
        "BUTTON_TEXT": "#ECF3EC",
        "MENU_BG": "#17231C",
        "MENU_ITEM_SEL": "#2E5039",
        "BORDER_SOFT": "#202F25",
        "DANGER": "#E87464",
        "SUCCESS": "#85C893",
    },
    "midnight-ember": {
        # Ember Night: a café lit by the fireplace — charcoal-rose walls and a
        # warm ember-orange glow. The coziest late-night theme.
        "MAIN_BG": "#151011",
        "MAIN_BG_ALT": "#1E1516",
        "SIDEBAR_BG": "#191213",
        "SIDEBAR_BORDER": "#38241F",
        "CARD_BG": "#211718",
        "INPUT_BG": "#261A1B",
        "INPUT_BORDER": "#4A2E28",
        "INPUT_FOCUS": "#F0956B",
        "TEXT": "#F8ECE4",
        "TEXT_MUTED": "#BCA196",
        "ACCENT": "#E2784A",
        "ACCENT_HOVER": "#F5926A",
        "ACCENT_SOFT": "#3B221A",
        "ITEM_HOVER": "#2C1F1E",
        "ITEM_SELECTED": "#46291F",
        "ITEM_SELECTED_BORDER": "#F5926A",
        "BUTTON_BG": "#2E211F",
        "BUTTON_HOVER": "#3C2B27",
        "BUTTON_TEXT": "#F8ECE4",
        "MENU_BG": "#201718",
        "MENU_ITEM_SEL": "#543024",
        "BORDER_SOFT": "#2C1F1E",
        "DANGER": "#E87464",
        "SUCCESS": "#8FB072",
    },
    "lavender-day": {
        # Lavender Latte: soft violet over steamed milk — calm and creative.
        "MAIN_BG": "#FAF7FC",
        "MAIN_BG_ALT": "#F2ECF7",
        "SIDEBAR_BG": "#F5EFF8",
        "SIDEBAR_BORDER": "#DFD2EA",
        "CARD_BG": "#FFFDFF",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#D5C5E4",
        "INPUT_FOCUS": "#7C5FB8",
        "TEXT": "#2A2135",
        "TEXT_MUTED": "#75688C",
        "ACCENT": "#8265C4",
        "ACCENT_HOVER": "#9C7FDC",
        "ACCENT_SOFT": "#ECE3F8",
        "ITEM_HOVER": "#F3EDF8",
        "ITEM_SELECTED": "#E7DCF4",
        "ITEM_SELECTED_BORDER": "#8265C4",
        "BUTTON_BG": "#F4EDF9",
        "BUTTON_HOVER": "#EADFF5",
        "BUTTON_TEXT": "#2A2135",
        "MENU_BG": "#FFFDFF",
        "MENU_ITEM_SEL": "#EDE2F6",
        "BORDER_SOFT": "#EBE1F2",
        "DANGER": "#B84A58",
        "SUCCESS": "#567F56",
    },
    "cocoa-day": {
        # Hot Cocoa: whipped chocolate-milk warmth with a roasted nib accent.
        "MAIN_BG": "#FAF4EE",
        "MAIN_BG_ALT": "#F1E5D8",
        "SIDEBAR_BG": "#F4EADF",
        "SIDEBAR_BORDER": "#E0CCB8",
        "CARD_BG": "#FFFCF8",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#D6BFA8",
        "INPUT_FOCUS": "#8A5A34",
        "TEXT": "#2C2016",
        "TEXT_MUTED": "#7D6450",
        "ACCENT": "#8F5E32",
        "ACCENT_HOVER": "#A97242",
        "ACCENT_SOFT": "#F2E1CE",
        "ITEM_HOVER": "#F3E9DC",
        "ITEM_SELECTED": "#ECDBC2",
        "ITEM_SELECTED_BORDER": "#8F5E32",
        "BUTTON_BG": "#F4EADD",
        "BUTTON_HOVER": "#EADCC8",
        "BUTTON_TEXT": "#2C2016",
        "MENU_BG": "#FFFCF8",
        "MENU_ITEM_SEL": "#EFDFC8",
        "BORDER_SOFT": "#EADCC9",
        "DANGER": "#B84A38",
        "SUCCESS": "#5E7F3C",
    },
    "lavender-night": {
        # Lavender Dusk: violet-dark walls, luminous lilac glow.
        "MAIN_BG": "#14101A",
        "MAIN_BG_ALT": "#1B1524",
        "SIDEBAR_BG": "#171220",
        "SIDEBAR_BORDER": "#332748",
        "CARD_BG": "#1D1626",
        "INPUT_BG": "#221A2C",
        "INPUT_BORDER": "#423256",
        "INPUT_FOCUS": "#C3A8F2",
        "TEXT": "#F2EBFA",
        "TEXT_MUTED": "#AC9CC2",
        "ACCENT": "#A98BE0",
        "ACCENT_HOVER": "#C2A6F0",
        "ACCENT_SOFT": "#2E2344",
        "ITEM_HOVER": "#251C30",
        "ITEM_SELECTED": "#362850",
        "ITEM_SELECTED_BORDER": "#C2A6F0",
        "BUTTON_BG": "#271E33",
        "BUTTON_HOVER": "#332744",
        "BUTTON_TEXT": "#F2EBFA",
        "MENU_BG": "#1C1626",
        "MENU_ITEM_SEL": "#403061",
        "BORDER_SOFT": "#251C30",
        "DANGER": "#E57A85",
        "SUCCESS": "#8FBE93",
    },
    "blueberry-night": {
        # Blueberry Night: deep blue-violet with an iris glow — moody and cool.
        "MAIN_BG": "#12101C",
        "MAIN_BG_ALT": "#191627",
        "SIDEBAR_BG": "#151223",
        "SIDEBAR_BORDER": "#2E2848",
        "CARD_BG": "#1A1729",
        "INPUT_BG": "#1F1B30",
        "INPUT_BORDER": "#3B3458",
        "INPUT_FOCUS": "#9FA8F2",
        "TEXT": "#EEEBF8",
        "TEXT_MUTED": "#A5A0C2",
        "ACCENT": "#8B90E0",
        "ACCENT_HOVER": "#A8ACEE",
        "ACCENT_SOFT": "#292747",
        "ITEM_HOVER": "#221E33",
        "ITEM_SELECTED": "#322D55",
        "ITEM_SELECTED_BORDER": "#A8ACEE",
        "BUTTON_BG": "#252040",
        "BUTTON_HOVER": "#302A52",
        "BUTTON_TEXT": "#EEEBF8",
        "MENU_BG": "#1A1729",
        "MENU_ITEM_SEL": "#3A3468",
        "BORDER_SOFT": "#221E33",
        "DANGER": "#E57A85",
        "SUCCESS": "#85B89B",
    },
    "mocha-mint": {
        # Mint Mocha: dark chocolate walls with a fresh mint counter — the
        # after-dinner drink of the theme family.
        "MAIN_BG": "#101614",
        "MAIN_BG_ALT": "#15201C",
        "SIDEBAR_BG": "#121917",
        "SIDEBAR_BORDER": "#263C34",
        "CARD_BG": "#17221E",
        "INPUT_BG": "#1B2723",
        "INPUT_BORDER": "#31493F",
        "INPUT_FOCUS": "#7FD6B8",
        "TEXT": "#EAF4EE",
        "TEXT_MUTED": "#9DB8AC",
        "ACCENT": "#4FC49A",
        "ACCENT_HOVER": "#72DDB5",
        "ACCENT_SOFT": "#17382D",
        "ITEM_HOVER": "#1E2C26",
        "ITEM_SELECTED": "#1E4237",
        "ITEM_SELECTED_BORDER": "#72DDB5",
        "BUTTON_BG": "#21312A",
        "BUTTON_HOVER": "#2B4036",
        "BUTTON_TEXT": "#EAF4EE",
        "MENU_BG": "#17221E",
        "MENU_ITEM_SEL": "#285043",
        "BORDER_SOFT": "#1E2C26",
        "DANGER": "#E57A75",
        "SUCCESS": "#85C8A8",
    },
    # ==================== 2026 pass: weather + time of day ====================
    "rain-day": {
        # Rainy Day: grey light through a wet window, cool paper, ink blue.
        "MAIN_BG": "#EEF1F4",
        "MAIN_BG_ALT": "#E4E9EE",
        "SIDEBAR_BG": "#E8ECF1",
        "SIDEBAR_BORDER": "#CFD8E0",
        "CARD_BG": "#F8FAFC",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#C3CED9",
        "INPUT_FOCUS": "#4A6E8F",
        "TEXT": "#1F2A33",
        "TEXT_MUTED": "#5E6E7C",
        "ACCENT": "#4A6E8F",
        "ACCENT_HOVER": "#5C84A8",
        "ACCENT_SOFT": "#DCE6EF",
        "ITEM_HOVER": "#E6ECF2",
        "ITEM_SELECTED": "#D8E3ED",
        "ITEM_SELECTED_BORDER": "#4A6E8F",
        "BUTTON_BG": "#E9EEF3",
        "BUTTON_HOVER": "#DDE5EC",
        "BUTTON_TEXT": "#1F2A33",
        "MENU_BG": "#F8FAFC",
        "MENU_ITEM_SEL": "#D8E3ED",
        "BORDER_SOFT": "#DDE4EA",
        "DANGER": "#B4534A",
        "SUCCESS": "#4F7B52",
    },
    "rain-night": {
        # Rainy Night: the same window after dark — slate blue, lamp-lit accent.
        "MAIN_BG": "#0D1319",
        "MAIN_BG_ALT": "#121A22",
        "SIDEBAR_BG": "#0F161D",
        "SIDEBAR_BORDER": "#22303C",
        "CARD_BG": "#141D25",
        "INPUT_BG": "#18222B",
        "INPUT_BORDER": "#2C3D4A",
        "INPUT_FOCUS": "#7FA8C9",
        "TEXT": "#E6EDF3",
        "TEXT_MUTED": "#9DB0BF",
        "ACCENT": "#6E9DC4",
        "ACCENT_HOVER": "#8FBCDD",
        "ACCENT_SOFT": "#1B2C3A",
        "ITEM_HOVER": "#1B242D",
        "ITEM_SELECTED": "#23384A",
        "ITEM_SELECTED_BORDER": "#8FBCDD",
        "BUTTON_BG": "#1D2731",
        "BUTTON_HOVER": "#26333F",
        "BUTTON_TEXT": "#E6EDF3",
        "MENU_BG": "#141D25",
        "MENU_ITEM_SEL": "#2B4256",
        "BORDER_SOFT": "#1E2A34",
        "DANGER": "#D9756B",
        "SUCCESS": "#7FA36F",
    },
    "sunrise-day": {
        # Sunrise: first light on the table, warm peach — the 5 a.m. study shift.
        "MAIN_BG": "#FBF3EA",
        "MAIN_BG_ALT": "#F6EADD",
        "SIDEBAR_BG": "#F7EDE2",
        "SIDEBAR_BORDER": "#E7D6C3",
        "CARD_BG": "#FFFBF5",
        "INPUT_BG": "#FFFFFF",
        "INPUT_BORDER": "#DCC7AE",
        "INPUT_FOCUS": "#C97B3C",
        "TEXT": "#2C2118",
        "TEXT_MUTED": "#7E674F",
        "ACCENT": "#CC7F3F",
        "ACCENT_HOVER": "#E09A5B",
        "ACCENT_SOFT": "#F8E3CE",
        "ITEM_HOVER": "#F6E9DA",
        "ITEM_SELECTED": "#F2E0C8",
        "ITEM_SELECTED_BORDER": "#CC7F3F",
        "BUTTON_BG": "#F5E9DC",
        "BUTTON_HOVER": "#EEDCCA",
        "BUTTON_TEXT": "#2C2118",
        "MENU_BG": "#FFFBF5",
        "MENU_ITEM_SEL": "#F1DEC6",
        "BORDER_SOFT": "#EFE1D0",
        "DANGER": "#C0553F",
        "SUCCESS": "#5F8340",
    },
    "autumn-day": {
        # Autumn Table: amber and spice, the study desk in October.
        "MAIN_BG": "#F8F0E4",
        "MAIN_BG_ALT": "#F1E5D2",
        "SIDEBAR_BG": "#F3E8D8",
        "SIDEBAR_BORDER": "#E0CDB2",
        "CARD_BG": "#FDF8F0",
        "INPUT_BG": "#FFFDF9",
        "INPUT_BORDER": "#D6BFA0",
        "INPUT_FOCUS": "#A96A29",
        "TEXT": "#2B2013",
        "TEXT_MUTED": "#7A6547",
        "ACCENT": "#A96A29",
        "ACCENT_HOVER": "#C4853B",
        "ACCENT_SOFT": "#F3E0C6",
        "ITEM_HOVER": "#F1E3CE",
        "ITEM_SELECTED": "#EBD9BC",
        "ITEM_SELECTED_BORDER": "#A96A29",
        "BUTTON_BG": "#F1E4D1",
        "BUTTON_HOVER": "#E8D6BC",
        "BUTTON_TEXT": "#2B2013",
        "MENU_BG": "#FDF8F0",
        "MENU_ITEM_SEL": "#E9D6B9",
        "BORDER_SOFT": "#E9DAC2",
        "DANGER": "#BC4E39",
        "SUCCESS": "#5C7F3D",
    },
}


def _art_palette(bg, alt, side, card, border, text, muted, accent, accent_hi, soft, hover, selected,
                input_bg=None, danger="#d45b55", success="#56845f"):
    """Build a complete opaque palette from a small, art-directed color set."""
    input_bg = input_bg or card
    return {
        "MAIN_BG": bg, "MAIN_BG_ALT": alt, "SIDEBAR_BG": side,
        "SIDEBAR_BORDER": border, "CARD_BG": card, "INPUT_BG": input_bg,
        "INPUT_BORDER": border, "INPUT_FOCUS": accent_hi,
        "TEXT": text, "TEXT_MUTED": muted, "ACCENT": accent,
        "ACCENT_HOVER": accent_hi, "ACCENT_SOFT": soft,
        "ITEM_HOVER": hover, "ITEM_SELECTED": selected,
        "ITEM_SELECTED_BORDER": accent, "BUTTON_BG": alt,
        "BUTTON_HOVER": hover, "BUTTON_TEXT": text,
        "MENU_BG": card, "MENU_ITEM_SEL": selected,
        "BORDER_SOFT": border, "DANGER": danger, "SUCCESS": success,
    }


# Art-directed families extend the same token contract as the café palettes.
# They stay fully opaque so the look remains readable on every Qt platform.
PALETTES.update({
    "aurora-glass": _art_palette("#101722", "#172332", "#121D2A", "#1A2837", "#304354", "#F2F6FC", "#A9BACB", "#66D6D1", "#91E8E0", "#1B4549", "#203B4A", "#284A57"),
    "sakura-twilight": _art_palette("#211923", "#30202D", "#291D2A", "#352332", "#593C50", "#FFF2F5", "#D7AEBF", "#F08CAF", "#FFA9C3", "#563047", "#442C3D", "#54334A"),
    "cyberpunk-neon": _art_palette("#11121A", "#1B1B29", "#151521", "#20202E", "#3D3B54", "#F4F2FF", "#B5B1C9", "#48E7F2", "#8BF2FA", "#173C46", "#2A2540", "#35304E"),
    "midnight-amoled": _art_palette("#050607", "#0C0E10", "#080A0C", "#101214", "#292D31", "#F4F6F8", "#A8B0B8", "#7BC8FF", "#A1D8FF", "#172B39", "#18232D", "#213442"),
    "arctic-aurora": _art_palette("#EFF6F8", "#E2EEF1", "#E8F2F4", "#FAFDFD", "#C6DADD", "#18343B", "#536E75", "#167F8C", "#0D6876", "#D7ECEE", "#DCECEE", "#CAE4E7"),
    "retro-terminal": _art_palette("#101710", "#18221A", "#131D15", "#1A261B", "#344A35", "#D6F4D0", "#9EBC98", "#75E36C", "#A1F395", "#233D25", "#263A27", "#2E482F"),
    "paper-studio": _art_palette("#F4F0E7", "#EAE4D8", "#EEE9DE", "#FBF9F3", "#D2C8B7", "#292822", "#6F6B60", "#765C3B", "#5E472D", "#E8DFD0", "#EDE6DA", "#E1D5C3"),
    "monochrome-pro": _art_palette("#F0F1F2", "#E4E6E8", "#E9EAEC", "#FAFAFB", "#C9CDD1", "#22262A", "#626970", "#3E566B", "#293F52", "#DCE2E6", "#E3E7EA", "#D1DAE0"),
    "dreamscape": _art_palette("#F2F0FA", "#E8E5F5", "#ECEAF7", "#FBFAFF", "#D3CEE9", "#29243C", "#706A89", "#6B62B8", "#554CA2", "#E5E1F6", "#E9E5F8", "#DCD7F1"),
    "solarized-focus": _art_palette("#F3F0E2", "#EAE6D6", "#EEEBDE", "#F8F5E9", "#D6D0BD", "#36464A", "#667577", "#287A78", "#1D6665", "#DDE8DF", "#E5E9DC", "#D4E1D5"),
    "high-contrast": _art_palette("#FFFFFF", "#EEEEEE", "#F4F4F4", "#FFFFFF", "#555555", "#101010", "#454545", "#003FCC", "#002E99", "#DCE6FF", "#E4E9F4", "#C8D7FF", danger="#A40000", success="#006A20"),
    "glasshouse": _art_palette("#EAF3EF", "#DDEBE5", "#E3EEE8", "#F6FBF8", "#BFD4C8", "#19362B", "#5C7568", "#397B5C", "#286746", "#D8E9DE", "#DDECE2", "#CDE2D3"),
    "forest-sanctuary": _art_palette("#111A15", "#18241C", "#141F18", "#1D2A21", "#394B3D", "#F0F4EB", "#B1BDAE", "#A9C77A", "#C4DB92", "#2A3F2C", "#2A382D", "#334A35"),
    "ocean-depths": _art_palette("#0D1722", "#142230", "#101C29", "#192837", "#344A5D", "#F0F5F8", "#AFC0CC", "#58B8CC", "#80D2E0", "#1B3A46", "#203646", "#294657"),
    "sunset-dusk": _art_palette("#21151A", "#2D1B22", "#27181F", "#35212A", "#563541", "#FFF3EB", "#D9B9B1", "#F19C72", "#FFB88D", "#4B2930", "#432530", "#55313C"),
})

# Theme shown when a profile has never picked one (and for unknown names).
DEFAULT_THEME = "minimal"

# Display names for the picker: the keys stay stable IDs, the labels tell the
# story ("Sakura Café" beats "rose-day" in a menu).
THEME_LABELS = {
    "minimal": "Quiet Table · warm paper, sage & clay",
    "minimal-night": "Quiet Table Night · dim espresso lounge",
    "latte": "Honey Crème · golden & warm",
    "rose-day": "Sakura Café · soft rose",
    "dawn": "Café Dawn · peachy first light",
    "matcha-day": "Matcha Latte · green & fresh",
    "sand-day": "Morning Crème · neutral office",
    "lavender-day": "Lavender Latte · violet calm",
    "cocoa-day": "Hot Cocoa · chocolate warmth",
    "cafe-night": "Espresso House · amber lamps",
    "ocean-night": "Café Azul · deep teal night",
    "forest-night": "Matcha Night · pine & moss",
    "rain-day": "Rainy Day · grey light, wet window",
    "rain-night": "Rainy Night · late drizzle",
    "sunrise-day": "Sunrise · first light, early study",
    "autumn-day": "Autumn Table · amber and spice",
    "midnight-ember": "Ember Night · fireplace glow",
    "lavender-night": "Lavender Dusk · lilac glow",
    "blueberry-night": "Blueberry Night · iris mood",
    "mocha-mint": "Mint Mocha · chocolate & mint",
    "aurora-glass": "Aurora Glass · luminous teal & indigo",
    "sakura-twilight": "Sakura Twilight · plum & blossom",
    "cyberpunk-neon": "Cyberpunk Neon · cyan & magenta",
    "midnight-amoled": "Midnight AMOLED · deep black",
    "arctic-aurora": "Arctic Aurora · ice & teal",
    "retro-terminal": "Retro Terminal · phosphor green",
    "paper-studio": "Paper Studio · warm ink & paper",
    "monochrome-pro": "Monochrome Pro · focused grayscale",
    "dreamscape": "Dreamscape · lavender & periwinkle",
    "solarized-focus": "Solarized Focus · low-glare reading",
    "high-contrast": "High Contrast · clear states",
    "glasshouse": "Glasshouse · botanical porcelain",
    "forest-sanctuary": "Forest Sanctuary · moss and warm earth",
    "ocean-depths": "Ocean Depths · deep marine and aqua",
    "sunset-dusk": "Sunset Dusk · ember and plum",
}


def theme_display_name(mode: str) -> str:
    return THEME_LABELS.get(mode, mode)


def accent_display_name(accent: str) -> str:
    return accent.capitalize()

DEFAULTS = {
    "TEXT_DIM": "#8a7a63",
    # Geometry scale — every corner in the chrome comes from these five values.
    # The UI had grown a dozen ad-hoc radii (4px…20px, twelve distinct values),
    # which is what made the chrome read as a pile of widgets instead of one
    # design. Tuned in the 2026 pass: controls soft, cards clearly larger than
    # chips, one pill value for anything pill-shaped.
    "RADIUS_XS": "8px",      # menu rows, tiny inner elements
    "RADIUS_SM": "10px",     # buttons, inputs, sidebar buttons
    "RADIUS": "14px",        # cards, popups
    "RADIUS_LG": "18px",     # hero panel, omnibar
    "RADIUS_PILL": "999px",  # pills and chips
    # Spacing scale (integers, for Python layouts).  One rhythm everywhere:
    # 4 / 8 / 12 / 16 / 24 / 32.  Multiples of four keep rows on a common grid
    # without every page inventing its own margins.
    "SPACE_XS": 4,
    "SPACE_SM": 8,
    "SPACE_MD": 12,
    "SPACE_LG": 16,
    "SPACE_XL": 24,
    "SPACE_XXL": 32,
    # Typography: an editorial serif for display type and numerals, a legible
    # humanist sans for the working interface, mono only for technical values.
    # Locally installed families only — no font download, no network.
    "FONT_DISPLAY": 'Georgia, "Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Times New Roman", serif',
    "FONT_UI": '"Segoe UI", "Segoe UI Variable Text", "Helvetica Neue", Arial, sans-serif',
    "FONT_MONO": '"Cascadia Mono", Consolas, "JetBrains Mono", "Courier New", monospace',
    # Kept for API compatibility; actual fallback is applied at app level via
    # QFont.setFamilies in litebrowser.main (QSS font-family cannot fall back).
    "FONT_FAMILY": '"Segoe UI", "Segoe UI Symbol", "Segoe UI Emoji", "Helvetica Neue", Arial, sans-serif',
    "TITLE_FONT": 'Georgia, "Times New Roman", serif',
}

# Accent presets: each is a (base, hover, soft, focus) tuple. The user picks one in
# Settings; it recolors buttons, active states, and focus rings across every theme.
# Soft tokens are dark-tinted; _palette() re-blends them for light themes.
# Every preset's base is dark/light enough to carry either white or near-black
# text (decided per palette by TEXT_ON_ACCENT), and its hover is legible as text
# on every surface the theme can paint.
ACCENTS = {
    "sage":      ("#5F6E55", "#47543D", "#2A3626", "#5F6E55"),  # quiet botanical green (default)
    "clay":      ("#A9603F", "#7F4326", "#40291F", "#A9603F"),  # terracotta cup
    "brass":     ("#D9A94F", "#F0C168", "#43301A", "#E5B763"),  # glowing café brass
    "caramel":   ("#C08A3E", "#DAA654", "#3D2A12", "#D4974C"),  # spun sugar caramel
    "ember":     ("#E2784A", "#F5926A", "#3B221A", "#F0956B"),  # fireplace ember
    "teal":      ("#3AB5A4", "#5FD2C2", "#12332F", "#4CC4B4"),  # mint-tea counter
    "violet":    ("#9B7FE0", "#B9A2EE", "#2B2347", "#A98FE6"),  # ube latte
    "sky":       ("#4E96DE", "#74B4EE", "#1B2E45", "#5CA2E6"),  # morning window sky
    "rose":      ("#DD6292", "#F083B0", "#3D1F30", "#E8739F"),  # strawberry glaze
    "matcha":    ("#6E9440", "#8CBB54", "#223316", "#7EA64B"),  # whisked matcha
    "slate":     ("#94A1B2", "#B0BDCE", "#272E37", "#A4B1C2"),  # quiet stone
    "terracotta": ("#bb7563", "#d49a85", "#412923", "#c98472"),
    "iris":      ("#777fc3", "#a0a5da", "#282a46", "#8d95ce"),
    "petrol":    ("#378e9b", "#63adb8", "#17343c", "#4aa0ad"),
    "plum":      ("#ac739b", "#cb9cbd", "#392434", "#bd87ac"),
}

# Accent shown for a profile that never chose one.  Changing the default does
# not rewrite stored choices: an explicit accent (preset or #hex) always wins.
DEFAULT_ACCENT = "brass"
_ACCENT_KEYS = ("ACCENT", "ACCENT_HOVER", "ACCENT_SOFT", "INPUT_FOCUS")


def accent_keys():
    """Names of the theme tokens controlled by the selected accent preset."""
    return _ACCENT_KEYS


def valid_accent(accent) -> bool:
    import re
    return isinstance(accent, str) and (accent in ACCENTS or bool(re.fullmatch(r"#[0-9a-fA-F]{6}", accent)))


def theme_variant(mode: str, dark: bool) -> str:
    pairs = (("minimal", "minimal-night"), ("latte", "cafe-night"), ("rose-day", "midnight-ember"),
             ("dawn", "cafe-night"), ("matcha-day", "forest-night"), ("sand-day", "ocean-night"),
             ("lavender-day", "lavender-night"), ("cocoa-day", "mocha-mint"), ("rain-day", "rain-night"),
             ("sunrise-day", "midnight-ember"), ("autumn-day", "cafe-night"), ("lavender-day", "blueberry-night"))
    for day, night in pairs:
        if mode in (day, night):
            return night if dark else day
    # Single-family themes keep their own art direction when automatic day/night
    # switching is enabled; they do not unexpectedly fall back to café palettes.
    return mode if mode in PALETTES else ("minimal-night" if dark else DEFAULT_THEME)


def contrast_ratio(first: str, second: str) -> float:
    def luminance(color):
        channels = [int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


def _readable_color(color, background, minimum=4.5):
    if contrast_ratio(color, background) >= minimum:
        return color
    target = "#171a1c" if _is_light_color(background) else "#ffffff"
    for step in range(21):
        candidate = _blend_hex(target, color, step / 20)
        if contrast_ratio(candidate, background) >= minimum:
            return candidate
    return target


def _accent_override(accent: str | None) -> dict:
    if valid_accent(accent) and accent.startswith("#"):
        preset = (accent, _blend_hex("#ffffff", accent, 0.2), _blend_hex(accent, "#171a1c", 0.25), accent)
    else:
        preset = ACCENTS.get(accent or "") if accent else None
    if not preset:
        return {}
    # A short preset list is tolerated: the pairs past its end are simply dropped.
    return dict(zip(_ACCENT_KEYS, preset, strict=False))


def _is_light_color(value: str) -> bool:
    """Return whether a hex color is bright enough for a light UI surface."""
    try:
        value = value.lstrip("#")
        red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
        return (red * 299 + green * 587 + blue * 114) / 1000 >= 150
    except (TypeError, ValueError):
        return False


def _blend_hex(foreground: str, background: str, amount: float) -> str:
    """Mix ``foreground`` into ``background`` without introducing a dark chip."""
    try:
        foreground = foreground.lstrip("#")
        background = background.lstrip("#")
        source = [int(foreground[index:index + 2], 16) for index in (0, 2, 4)]
        base = [int(background[index:index + 2], 16) for index in (0, 2, 4)]
        mixed = [round(base[index] + (source[index] - base[index]) * amount) for index in range(3)]
        return "#" + "".join(f"{channel:02x}" for channel in mixed)
    except (TypeError, ValueError):
        return foreground if foreground.startswith("#") else f"#{foreground}"


def _derive_semantics(palette: dict) -> dict:
    """Add the semantic surface/status layer every theme shares.

    The raw palettes keep their 24 art-directed tokens so no stored profile or
    art theme has to change.  On top of them this derives the *roles* the new
    interface actually paints with — canvas vs. paper vs. sunken well, hairline
    rules, an accent wash for quiet highlights, and a warm secondary (clay) that
    is not the primary accent.  Deriving them in one place means a theme cannot
    half-adopt the design: every palette gets the same vocabulary, already
    contrast-checked against its own surfaces.
    """
    light = _is_light_color(palette["MAIN_BG"])
    palette["SURFACE"] = palette["CARD_BG"]
    palette["SURFACE_ALT"] = palette["MAIN_BG_ALT"]
    palette["SURFACE_SUNK"] = _blend_hex(palette["TEXT"], palette["MAIN_BG_ALT"], 0.05 if light else 0.14)
    palette["EDITOR_BG"] = _blend_hex(palette["CARD_BG"], palette["MAIN_BG_ALT"], 0.35 if light else 0.25)
    palette["NAV_BG"] = palette["SIDEBAR_BG"]
    palette["RULE"] = palette["BORDER_SOFT"]
    palette["RULE_STRONG"] = _blend_hex(palette["TEXT"], palette["BORDER_SOFT"], 0.18)
    palette["ACCENT_WASH"] = _blend_hex(palette["ACCENT"], palette["MAIN_BG"], 0.13 if light else 0.20)
    palette["ACCENT_QUIET"] = _blend_hex(palette["ACCENT"], palette["CARD_BG"], 0.30 if light else 0.34)
    # A warm counterpoint to the accent.  Derived from the palette's own danger
    # hue so it never clashes, and pulled back until it reads as clay, not alarm.
    clay = _blend_hex(palette["DANGER"], "#B77756", 0.45 if light else 0.30)
    # Clay is used as text (a section mark, an overdue timestamp) as well as a
    # chip fill, so it is pulled into contrast before anything reads it.
    clay = _readable_color(clay, palette["CARD_BG"])
    palette["CLAY"] = _readable_color(clay, palette["MAIN_BG"])
    palette["CLAY_SOFT"] = _blend_hex(palette["CLAY"], palette["MAIN_BG"], 0.14 if light else 0.20)
    palette["WARNING"] = _blend_hex("#B07B18", palette["DANGER"], 0.35)
    palette["WARNING_SOFT"] = _blend_hex(palette["WARNING"], palette["MAIN_BG"], 0.13 if light else 0.20)
    palette["SUCCESS_SOFT"] = _blend_hex(palette["SUCCESS"], palette["MAIN_BG"], 0.13 if light else 0.20)
    palette["DANGER_SOFT"] = _blend_hex(palette["DANGER"], palette["MAIN_BG"], 0.13 if light else 0.20)
    palette["FOCUS_RING"] = palette["INPUT_FOCUS"]
    palette["SELECT_BG"] = palette["ACCENT_WASH"]
    palette["SELECT_FG"] = palette["TEXT"]
    palette["ON_WARM"] = "#171a1c" if contrast_ratio("#171a1c", palette["CLAY"]) >= contrast_ratio("#ffffff", palette["CLAY"]) else "#ffffff"
    return palette


def _palette(mode: str, accent: str | None = None):
    palette = dict(DEFAULTS)
    # Unknown names fall back to the documented default theme, not a random one
    # (v6.5 audit: a typo'd theme silently rendered the whole app dark).
    palette.update(PALETTES.get(mode, PALETTES[DEFAULT_THEME]))
    override = _accent_override(accent)
    palette.update(override)
    # The preset exactly as chosen.  Night palettes lift ACCENT until it can
    # carry text, so the stylesheet still records the untouched source ink.
    palette["ACCENT_BASE"] = palette["ACCENT"]
    # Accent presets include a dark soft tone for night themes.  Reusing it on
    # cafe-day creates near-black active buttons, so derive a paper-tinted
    # accent surface for every light theme instead.
    if override and _is_light_color(palette["MAIN_BG"]):
        palette["ACCENT_SOFT"] = _blend_hex(palette["ACCENT"], palette["MAIN_BG"], 0.20)
    elif override:
        # A preset tuned for paper (a deep sage, a warm clay) disappears as a
        # filled control on a night palette.  Lift it until it carries 4.5:1
        # against the night canvas, then the same TEXT_ON_ACCENT rule picks
        # near-black ink — a pale ceramic chip rather than a black hole.
        # 5.0 rather than 4.5: the fill must clear 4.5 against *both* candidate inks so TEXT_ON_ACCENT stays a real choice, not a rounding accident.
        palette["ACCENT"] = _readable_color(palette["ACCENT"], palette["MAIN_BG"], 5.0)
    palette["TEXT_ON_ACCENT"] = "#171a1c" if contrast_ratio("#171a1c", palette["ACCENT"]) >= contrast_ratio("#ffffff", palette["ACCENT"]) else "#ffffff"
    # Mid-luminance accents cannot carry either ink at 4.5:1.  Nudge the fill
    # away from the chosen ink until the filled button is genuinely readable
    # (this is the only place a preset's base colour may be adjusted).
    if contrast_ratio(palette["TEXT_ON_ACCENT"], palette["ACCENT"]) < 4.5:
        away = "#ffffff" if not _is_light_color(palette["TEXT_ON_ACCENT"]) else "#141414"
        for step in range(1, 21):
            candidate = _blend_hex(away, palette["ACCENT"], step / 20)
            if contrast_ratio(palette["TEXT_ON_ACCENT"], candidate) >= 4.5:
                palette["ACCENT"] = candidate
                break
    # Filled-button hover is distinct from accent-colored text on a surface.
    palette["ACCENT_FILL_HOVER"] = _readable_color(palette["ACCENT_HOVER"], palette["TEXT_ON_ACCENT"])
    palette["TEXT_ON_DANGER"] = "#171a1c" if contrast_ratio("#171a1c", palette["DANGER"]) >= contrast_ratio("#ffffff", palette["DANGER"]) else "#ffffff"
    for background in ("MAIN_BG", "CARD_BG", "MAIN_BG_ALT", "ACCENT_SOFT"):
        palette["ACCENT_HOVER"] = _readable_color(palette["ACCENT_HOVER"], palette[background])
    for background in ("MAIN_BG", "CARD_BG", "MAIN_BG_ALT", "INPUT_BG"):
        palette["TEXT_MUTED"] = _readable_color(palette["TEXT_MUTED"], palette[background])
    palette["TEXT_DIM"] = _blend_hex(palette["TEXT"], palette["MAIN_BG"], 0.55)
    return _derive_semantics(palette)


def palette_tokens(mode: str = "minimal", accent: str | None = None) -> dict:
    """Public accessor for the resolved color tokens (theme palette + accent merged).

    Shared by the shell QSS and the local new-tab page so the speed dial follows
    the active theme instead of staying hard-coded dark.
    """
    return _palette(mode, accent)


def is_night_theme(mode: str) -> bool:
    """Whether ``mode`` paints a dark surface.

    Read from the palette's own background (not from the theme's name), so a new
    dark theme is recognised without a second list to keep in sync. Used to make
    the web pages follow the shell: dark chrome implies dark pages unless the
    user has said otherwise (see prefs.effective_force_dark_web).
    """
    return not _is_light_color(_palette(mode or DEFAULT_THEME)["MAIN_BG"])


__all__ = [
    "ACCENTS",
    "DEFAULTS",
    "DEFAULT_THEME",
    "PALETTES",
    "THEME_LABELS",
    "_ACCENT_KEYS",
    "_accent_override",
    "_blend_hex",
    "_is_light_color",
    "_derive_semantics",
    "_palette",
    "DEFAULT_ACCENT",
    "accent_display_name",
    "accent_keys",
    "is_night_theme",
    "palette_tokens",
    "theme_display_name",
]
