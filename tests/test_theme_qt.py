"""Tests for ``theme_qt.py`` composed stylesheet helpers.

theme_qt returns strings, so these tests don't need a QApplication — we
assert that each helper embeds the expected token values and follows the
shape the Tuner's theme.hpp helpers do.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import theme
import theme_qt as tq


class CardStyleTests(unittest.TestCase):
    def test_default_has_no_left_accent(self):
        s = tq.card_style()
        self.assertIn(theme.BG_PANEL, s)
        self.assertIn(theme.BORDER, s)
        self.assertIn("border-radius", s)
        self.assertNotIn("border-left:", s)

    def test_accent_variant_gets_left_bar(self):
        s = tq.card_style(theme.ACCENT_PRIMARY)
        self.assertIn(theme.ACCENT_PRIMARY, s)
        self.assertIn("border-left: 3px solid", s)

    def test_danger_accent_passes_through(self):
        s = tq.card_style(theme.ACCENT_DANGER)
        self.assertIn(theme.ACCENT_DANGER, s)


class HeaderStripTests(unittest.TestCase):
    def test_uses_elevated_bg(self):
        s = tq.header_strip_style()
        self.assertIn(theme.BG_ELEVATED, s)
        self.assertIn(theme.BORDER, s)

    def test_tab_header_uses_panel_bg(self):
        s = tq.tab_header_style()
        self.assertIn(theme.BG_PANEL, s)


class ChipStyleTests(unittest.TestCase):
    def test_chip_uses_inset_bg(self):
        s = tq.chip_style()
        self.assertIn(theme.BG_INSET, s)
        self.assertIn(theme.BORDER, s)

    def test_chip_accent_overrides_border(self):
        s = tq.chip_style(theme.ACCENT_WARNING)
        self.assertIn(theme.ACCENT_WARNING, s)


class TabHeaderHtmlTests(unittest.TestCase):
    def test_title_uses_primary_text(self):
        html = tq.tab_header_html("Bulk Grid", "assign vendors")
        self.assertIn("Bulk Grid", html)
        self.assertIn("assign vendors", html)
        self.assertIn(theme.TEXT_PRIMARY, html)
        self.assertIn(theme.TEXT_DIM, html)

    def test_escapes_not_needed_for_static_strings(self):
        # Sanity: bullet separator present
        html = tq.tab_header_html("A", "B")
        self.assertIn("\u00b7", html)


class NumberCardTests(unittest.TestCase):
    def test_top_border_uses_accent(self):
        s = tq.number_card_style(theme.ACCENT_OK, top_border_px=4)
        self.assertIn("border-top: 4px solid", s)
        self.assertIn(theme.ACCENT_OK, s)

    def test_html_renders_value_units_title(self):
        html = tq.number_card_html("38", "items", "Draft Qty Total", theme.ACCENT_OK)
        self.assertIn("38", html)
        self.assertIn("items", html)
        self.assertIn("Draft Qty Total", html)
        self.assertIn(theme.ACCENT_OK, html)


class SidebarStyleTests(unittest.TestCase):
    def test_sidebar_has_selected_left_bar(self):
        s = tq.sidebar_style()
        self.assertIn("QListWidget::item:selected", s)
        self.assertIn("border-left: 3px solid", s)
        self.assertIn(theme.ACCENT_PRIMARY, s)

    def test_sidebar_uses_deep_bg_for_chrome(self):
        s = tq.sidebar_style()
        self.assertIn(theme.BG_DEEP, s)


class ScalarEditorStateTests(unittest.TestCase):
    def test_default_state_uses_border_color(self):
        s = tq.scalar_editor_style("default")
        self.assertIn(theme.BORDER, s)
        self.assertIn(theme.TEXT_PRIMARY, s)
        self.assertIn("font-weight: normal", s)

    def test_ok_state_uses_primary_accent(self):
        s = tq.scalar_editor_style("ok")
        self.assertIn(theme.ACCENT_PRIMARY, s)
        self.assertIn("font-weight: bold", s)

    def test_warning_state_uses_warning_accent(self):
        s = tq.scalar_editor_style("warning")
        self.assertIn(theme.ACCENT_WARNING, s)
        self.assertIn("font-weight: bold", s)


class AppStylesheetTests(unittest.TestCase):
    def test_contains_every_primary_widget_selector(self):
        ss = tq.app_stylesheet()
        for selector in ("QMainWindow", "QPushButton", "QLineEdit",
                          "QTableView", "QHeaderView", "QMenu",
                          "QScrollBar", "QLabel", "QStatusBar"):
            self.assertIn(selector, ss, f"missing selector {selector}")

    def test_uses_base_bg_and_primary_text(self):
        ss = tq.app_stylesheet()
        self.assertIn(theme.BG_BASE, ss)
        self.assertIn(theme.TEXT_PRIMARY, ss)


if __name__ == "__main__":
    unittest.main()
