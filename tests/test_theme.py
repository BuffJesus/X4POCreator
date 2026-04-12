"""Tests for the framework-independent ``theme.py`` token module.

Pure data — no Tk, no Qt, no widgets.  These tests lock the palette
against accidental drift: if someone adds a new hex value to theme.py
without a corresponding test update, the reviewer notices.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import theme


HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class PaletteShapeTests(unittest.TestCase):
    """The palette must stay disciplined: 5 bg levels, 5 text levels, 5 accents."""

    def test_five_background_levels(self):
        bg = [theme.BG_DEEP, theme.BG_BASE, theme.BG_PANEL, theme.BG_ELEVATED, theme.BG_INSET]
        self.assertEqual(len(set(bg)), 5, "backgrounds must be distinct")
        for value in bg:
            self.assertRegex(value, HEX_RE)

    def test_five_text_levels(self):
        text = [theme.TEXT_PRIMARY, theme.TEXT_SECONDARY, theme.TEXT_MUTED,
                theme.TEXT_DIM, theme.TEXT_INVERSE]
        self.assertEqual(len(set(text)), 5)
        for value in text:
            self.assertRegex(value, HEX_RE)

    def test_five_semantic_accents(self):
        accents = [theme.ACCENT_PRIMARY, theme.ACCENT_OK, theme.ACCENT_WARNING,
                   theme.ACCENT_DANGER, theme.ACCENT_SPECIAL]
        self.assertEqual(len(set(accents)), 5)
        for value in accents:
            self.assertRegex(value, HEX_RE)


class TypeScaleTests(unittest.TestCase):
    def test_strictly_ascending(self):
        scale = [theme.FONT_MICRO, theme.FONT_SMALL, theme.FONT_BODY,
                 theme.FONT_MEDIUM, theme.FONT_LABEL, theme.FONT_HEADING, theme.FONT_HERO]
        for prev, cur in zip(scale, scale[1:]):
            self.assertLess(prev, cur, f"type scale must be ascending at {prev} -> {cur}")

    def test_spacing_ascending_powers_of_two_ish(self):
        spacing = [theme.SPACE_XS, theme.SPACE_SM, theme.SPACE_MD,
                   theme.SPACE_LG, theme.SPACE_XL]
        for prev, cur in zip(spacing, spacing[1:]):
            self.assertLess(prev, cur)

    def test_radii_small_to_large(self):
        self.assertLess(theme.RADIUS_SM, theme.RADIUS_MD)
        self.assertLess(theme.RADIUS_MD, theme.RADIUS_LG)


class ZoneAccentTests(unittest.TestCase):
    def test_known_zones_map_to_accents(self):
        self.assertEqual(theme.zone_accent("ok"), theme.ACCENT_OK)
        self.assertEqual(theme.zone_accent("warning"), theme.ACCENT_WARNING)
        self.assertEqual(theme.zone_accent("danger"), theme.ACCENT_DANGER)
        self.assertEqual(theme.zone_accent("primary"), theme.ACCENT_PRIMARY)

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(theme.zone_accent("  DANGER "), theme.ACCENT_DANGER)
        self.assertEqual(theme.zone_accent("Ok"), theme.ACCENT_OK)

    def test_unknown_zone_falls_back_to_primary(self):
        self.assertEqual(theme.zone_accent("nonsense"), theme.ACCENT_PRIMARY)
        self.assertEqual(theme.zone_accent(""), theme.ACCENT_PRIMARY)
        self.assertEqual(theme.zone_accent(None), theme.ACCENT_PRIMARY)

    def test_zone_fill_maps_for_row_tints(self):
        self.assertEqual(theme.zone_fill("ok"), theme.FILL_OK_SOFT)
        self.assertEqual(theme.zone_fill("warning"), theme.FILL_WARNING_SOFT)
        self.assertEqual(theme.zone_fill("danger"), theme.FILL_DANGER_SOFT)
        self.assertEqual(theme.zone_fill("skip"), theme.FILL_SKIP_SOFT)

    def test_unknown_zone_fill_falls_back_to_panel(self):
        self.assertEqual(theme.zone_fill("???"), theme.BG_PANEL)


class PalettePinTests(unittest.TestCase):
    """Lock the Tuner palette values explicitly.

    If someone changes a hex, the test fails and the reviewer has to
    either update the test (deliberate) or fix their change (accident).
    Both accents and backgrounds are named below.
    """

    def test_accent_primary_matches_tuner(self):
        self.assertEqual(theme.ACCENT_PRIMARY, "#5a9ad6")

    def test_bg_levels_match_tuner(self):
        self.assertEqual(theme.BG_DEEP,     "#0f1116")
        self.assertEqual(theme.BG_BASE,     "#14171e")
        self.assertEqual(theme.BG_PANEL,    "#1a1d24")
        self.assertEqual(theme.BG_ELEVATED, "#20242c")
        self.assertEqual(theme.BG_INSET,    "#262a33")

    def test_text_levels_match_tuner(self):
        self.assertEqual(theme.TEXT_PRIMARY,   "#e8edf5")
        self.assertEqual(theme.TEXT_SECONDARY, "#c9d1e0")
        self.assertEqual(theme.TEXT_MUTED,     "#8a93a6")
        self.assertEqual(theme.TEXT_DIM,       "#6a7080")


if __name__ == "__main__":
    unittest.main()
