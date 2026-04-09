import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_help


def _headless_tk_root():
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except tk.TclError:
        return None


class UIHelpTests(unittest.TestCase):
    def test_overview_help_documents_exception_first_export_recommended_workflow(self):
        overview = next(section for section in ui_help.HELP_SECTIONS if section[0] == "Overview")
        body = overview[2]

        self.assertIn("Review exceptions first", body)
        self.assertIn("Export Recommended", body)
        self.assertIn("exception-first screen", body)

    def test_review_and_export_help_documents_default_review_fallback_and_recommended_export(self):
        section = next(section for section in ui_help.HELP_SECTIONS if section[0] == "Review And Export")
        body = section[2]

        self.assertIn("Exceptions Only", body)
        self.assertIn("falls back to All Items", body)
        self.assertIn("Export Recommended is the normal path", body)

    def test_shipping_help_documents_urgent_overrides_as_review_first(self):
        section = next(section for section in ui_help.HELP_SECTIONS if section[0] == "Shipping And Release")
        body = section[2]

        self.assertIn("urgent overrides", body.lower())
        self.assertIn("review-first exceptions", body)


class ContextualHelpMapTests(unittest.TestCase):
    def test_every_mapped_key_resolves_to_a_real_section(self):
        titles = {t for t, _i, _b in ui_help.HELP_SECTIONS}
        for key, target in ui_help.CONTEXTUAL_HELP_MAP.items():
            with self.subTest(key=key):
                self.assertIn(target, titles)


class FocusHelpSectionTests(unittest.TestCase):
    def test_returns_false_when_help_not_built(self):
        app = SimpleNamespace()
        self.assertFalse(ui_help.focus_help_section(app, "Overview"))

    def test_returns_true_and_selects_matching_section(self):
        selected = []
        class FakeNotebook:
            def select(self, idx):
                selected.append(idx)
        pages = [
            SimpleNamespace(_help_title="Overview"),
            SimpleNamespace(_help_title="Bulk Assign"),
        ]
        app = SimpleNamespace(
            _help_notebook=FakeNotebook(),
            _help_pages=pages,
            notebook=None,
        )
        self.assertTrue(ui_help.focus_help_section(app, "Bulk Assign"))
        self.assertEqual(selected, [1])

    def test_returns_false_for_unknown_section(self):
        pages = [SimpleNamespace(_help_title="Overview")]
        app = SimpleNamespace(
            _help_notebook=SimpleNamespace(select=lambda idx: None),
            _help_pages=pages,
            notebook=None,
        )
        self.assertFalse(ui_help.focus_help_section(app, "Not A Section"))


class OpenHelpForTests(unittest.TestCase):
    def test_contextual_key_routes_to_mapped_section(self):
        picked = []
        pages = [SimpleNamespace(_help_title=t) for t, *_ in ui_help.HELP_SECTIONS]
        app = SimpleNamespace(
            _help_notebook=SimpleNamespace(select=lambda idx: picked.append(idx)),
            _help_pages=pages,
            notebook=None,
        )
        ui_help.open_help_for(app, "skip_filter")  # → "Bulk Assign"
        target_idx = [i for i, p in enumerate(pages) if p._help_title == "Bulk Assign"][0]
        self.assertEqual(picked, [target_idx])

    def test_unknown_key_falls_back_to_first_section(self):
        picked = []
        pages = [SimpleNamespace(_help_title=t) for t, *_ in ui_help.HELP_SECTIONS]
        app = SimpleNamespace(
            _help_notebook=SimpleNamespace(select=lambda idx: picked.append(idx)),
            _help_pages=pages,
            notebook=None,
        )
        ui_help.open_help_for(app, "does-not-exist")
        self.assertEqual(picked, [0])


class RenderHelpBodyTests(unittest.TestCase):
    def setUp(self):
        self.root = _headless_tk_root()
        if self.root is None:
            self.skipTest("no tk display available")

    def tearDown(self):
        if self.root is not None:
            self.root.destroy()

    def test_h1_line_gets_heading1_tag(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        ui_help._render_help_body(body, "T", "# Big\nplain text\n")
        ranges = body.tag_ranges("heading1")
        self.assertTrue(ranges)
        self.assertIn("Big", body.get(ranges[0], ranges[1]))

    def test_h2_line_gets_heading2_tag(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        ui_help._render_help_body(body, "T", "# top\n## sub\nplain\n")
        ranges = body.tag_ranges("heading2")
        self.assertTrue(ranges)
        self.assertIn("sub", body.get(ranges[0], ranges[1]))

    def test_synthesizes_title_heading_when_body_has_no_leading_hash(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        ui_help._render_help_body(body, "SectionTitle", "plain text\n")
        # Title was synthesized as the first line with heading1 tag.
        first_line = body.get("1.0", "1.end")
        self.assertEqual(first_line, "SectionTitle")
        self.assertIn("heading1", body.tag_names("1.0"))

    def test_inline_code_span_gets_code_tag(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        ui_help._render_help_body(body, "T", "# H\nUse `final_qty` to decide.\n")
        code_ranges = body.tag_ranges("code")
        self.assertTrue(code_ranges)
        self.assertEqual(body.get(code_ranges[0], code_ranges[1]), "final_qty")

    def test_bullet_lines_get_bullet_tag(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        ui_help._render_help_body(body, "T", "# H\n- first\n- second\n")
        bullet_ranges = body.tag_ranges("bullet")
        # two bullet lines → tag_ranges returns (start, end, start, end)
        self.assertEqual(len(bullet_ranges), 4)


class HighlightMatchesTests(unittest.TestCase):
    def setUp(self):
        self.root = _headless_tk_root()
        if self.root is None:
            self.skipTest("no tk display available")

    def tearDown(self):
        if self.root is not None:
            self.root.destroy()

    def test_highlight_returns_zero_for_blank_needle(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        body.insert("1.0", "anything")
        self.assertEqual(ui_help._highlight_matches(body, ""), 0)

    def test_highlight_tags_all_occurrences_case_insensitive(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        body.insert("1.0", "Foo bar FOO baz Foo\nfoo\n")
        first_line = ui_help._highlight_matches(body, "foo")
        self.assertEqual(first_line, 1)
        match_ranges = body.tag_ranges("match")
        # 4 matches => 8 tag range indices
        self.assertEqual(len(match_ranges), 8)

    def test_highlight_returns_zero_when_no_match(self):
        body = tk.Text(self.root)
        ui_help._configure_help_text_tags(body)
        body.insert("1.0", "hello\n")
        self.assertEqual(ui_help._highlight_matches(body, "zzz"), 0)


if __name__ == "__main__":
    unittest.main()
