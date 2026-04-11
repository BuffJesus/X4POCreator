import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_command_palette


class BuildActionIndexTests(unittest.TestCase):
    def test_only_callable_actions_are_indexed(self):
        app = MagicMock()
        # Strip out a handful of methods to simulate a partially-built app
        app._proceed_to_review_with_enrich = None
        app._bulk_remove_not_needed_filtered = None
        app.notebook = MagicMock()

        index = ui_command_palette.build_action_index(app)
        labels = {entry["label"] for entry in index}
        # Callable methods make it in
        self.assertIn("Go to Load tab", labels)
        # Missing methods are filtered out
        self.assertNotIn("Export POs", labels)
        self.assertNotIn("Remove Not Needed", labels)

    def test_actions_have_haystack(self):
        app = MagicMock()
        app.notebook = MagicMock()
        index = ui_command_palette.build_action_index(app)
        for entry in index:
            self.assertEqual(entry["kind"], "action")
            self.assertTrue(entry["haystack"])
            self.assertTrue(callable(entry["run"]))


class BuildItemIndexTests(unittest.TestCase):
    def test_skips_empty_items(self):
        calls = []
        index = ui_command_palette.build_item_index(
            [
                {"line_code": "GR1-", "item_code": "3504-04-04", "description": "FEM SAE"},
                {"line_code": "", "item_code": "", "description": ""},
                {"line_code": "GR2-", "item_code": "114-06", "description": "BELT"},
            ],
            lambda lc, ic: calls.append((lc, ic)),
        )
        labels = [e["label"] for e in index]
        self.assertEqual(labels, ["GR1-3504-04-04", "GR2-114-06"])

    def test_run_callback_captures_item(self):
        calls = []
        index = ui_command_palette.build_item_index(
            [{"line_code": "GR1-", "item_code": "A"}, {"line_code": "GR1-", "item_code": "B"}],
            lambda lc, ic: calls.append((lc, ic)),
        )
        index[0]["run"]()
        index[1]["run"]()
        self.assertEqual(calls, [("GR1-", "A"), ("GR1-", "B")])

    def test_vendor_in_sublabel(self):
        index = ui_command_palette.build_item_index(
            [{"line_code": "GR1-", "item_code": "A", "description": "HOSE", "vendor": "MOTION"}],
            lambda lc, ic: None,
        )
        self.assertIn("MOTION", index[0]["sublabel"])
        self.assertIn("HOSE", index[0]["sublabel"])


class RankResultsTests(unittest.TestCase):
    def _entry(self, kind, label, haystack=None, sort_key=None):
        return {
            "kind": kind,
            "label": label,
            "sublabel": "",
            "haystack": (haystack or label).lower(),
            "run": lambda: None,
            "sort_key": sort_key or (label,),
        }

    def test_prefix_match_beats_substring(self):
        entries = [
            self._entry("item", "GR1-3504-04-04"),
            self._entry("item", "ABC-3504-GR1"),  # substring only
        ]
        results = ui_command_palette.rank_results("gr1", entries)
        self.assertEqual([r["label"] for r in results], ["GR1-3504-04-04", "ABC-3504-GR1"])

    def test_actions_rank_above_items_on_ties(self):
        entries_a = [self._entry("action", "Export POs", haystack="export")]
        entries_b = [self._entry("item", "GR1-export-thing", haystack="export")]
        results = ui_command_palette.rank_results("export", entries_a, entries_b)
        self.assertEqual(results[0]["label"], "Export POs")

    def test_empty_query_returns_everything_up_to_limit(self):
        entries = [self._entry("item", f"ITEM-{i}") for i in range(5)]
        results = ui_command_palette.rank_results("", entries)
        self.assertEqual(len(results), 5)

    def test_substring_in_haystack_match(self):
        entries = [self._entry("item", "GR1-A", haystack="gr1-a hose reducer")]
        results = ui_command_palette.rank_results("reducer", entries)
        self.assertEqual(len(results), 1)

    def test_no_match_returns_empty(self):
        entries = [self._entry("item", "GR1-A", haystack="gr1-a hose")]
        results = ui_command_palette.rank_results("xyzzy", entries)
        self.assertEqual(results, [])

    def test_limit_caps_result_count(self):
        entries = [self._entry("item", f"ITEM-{i}") for i in range(20)]
        results = ui_command_palette.rank_results("item", entries, limit=5)
        self.assertEqual(len(results), 5)


class BuildVendorIndexTests(unittest.TestCase):
    def test_dedupes_and_skips_blank(self):
        calls = []
        index = ui_command_palette.build_vendor_index(
            ["GRELIN", "GRELIN", "", "MOTION", None],
            lambda v: calls.append(v),
        )
        labels = [e["label"] for e in index]
        self.assertEqual(labels, ["Filter: GRELIN", "Filter: MOTION"])

    def test_run_callback_receives_vendor(self):
        calls = []
        index = ui_command_palette.build_vendor_index(
            ["GRELIN", "MOTION"],
            lambda v: calls.append(v),
        )
        index[0]["run"]()
        index[1]["run"]()
        self.assertEqual(calls, ["GRELIN", "MOTION"])


if __name__ == "__main__":
    unittest.main()
