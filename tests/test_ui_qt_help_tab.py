"""Headless Qt tests for ``ui_qt.help_tab.HelpTab`` and its HTML renderer."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    _PYSIDE6_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYSIDE6_AVAILABLE = False


class RenderSectionHtmlTests(unittest.TestCase):
    """Renderer tests do not require a QApplication — pure string transform."""

    def setUp(self):
        from ui_qt.help_tab import render_section_html
        self.render = render_section_html

    def test_title_promoted_when_body_has_no_heading(self):
        html = self.render("My Section", "first paragraph")
        self.assertIn("My Section", html)
        self.assertIn("<h1", html)

    def test_title_not_duplicated_when_body_opens_with_heading(self):
        html = self.render("Overview", "# Overview\nBody")
        # Only one h1 tag (from the body, not an extra prepended one).
        self.assertEqual(html.count("<h1"), 1)

    def test_heading2_renders_as_h2(self):
        html = self.render("X", "## Sub Heading\nbody")
        self.assertIn("<h2", html)
        self.assertIn("Sub Heading", html)

    def test_bullets_wrapped_in_ul(self):
        html = self.render("X", "- one\n- two")
        self.assertIn("<ul", html)
        self.assertEqual(html.count("<li"), 2)

    def test_asterisk_bullets_also_wrapped(self):
        html = self.render("X", "* one\n* two")
        self.assertEqual(html.count("<li"), 2)

    def test_inline_code_rendered_with_token_background(self):
        import theme
        html = self.render("X", "See `reqFuel` for details")
        self.assertIn("<code", html)
        self.assertIn("reqFuel", html)
        self.assertIn(theme.BG_INSET, html)

    def test_html_is_escaped(self):
        html = self.render("X", "a <b> c & d")
        self.assertNotIn("<b>", html)  # raw would-be-tag not emitted
        self.assertIn("&lt;b&gt;", html)
        self.assertIn("&amp;", html)

    def test_blank_line_ends_bullet_list(self):
        html = self.render("X", "- one\n\nafter list")
        # Both the <ul>...</ul> and the paragraph after
        self.assertIn("</ul>", html)
        self.assertIn("after list", html)


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 not installed")
class HelpTabWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tab_instantiates_with_section_list(self):
        from ui_qt.help_tab import HelpTab
        from ui_help_data import HELP_SECTIONS
        tab = HelpTab()
        self.assertEqual(tab._sections.count(), len(HELP_SECTIONS))

    def test_initial_section_selected(self):
        from ui_qt.help_tab import HelpTab
        tab = HelpTab()
        self.assertEqual(tab._sections.currentRow(), 0)

    def test_changing_section_updates_body(self):
        from ui_qt.help_tab import HelpTab
        tab = HelpTab()
        first_html = tab._body.toHtml()
        # Switch to a different section if one exists.
        if tab._sections.count() > 1:
            tab._sections.setCurrentRow(1)
            second_html = tab._body.toHtml()
            self.assertNotEqual(first_html, second_html)


if __name__ == "__main__":
    unittest.main()
