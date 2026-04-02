import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import trend_flow
import storage


class ComputeOverridePatternTests(unittest.TestCase):
    def test_always_up_when_final_always_exceeds_suggested(self):
        entries = [
            {"final_qty": 20, "suggested_qty": 10},
            {"final_qty": 30, "suggested_qty": 15},
        ]
        self.assertEqual(trend_flow.compute_override_pattern(entries), "always_up")

    def test_always_down_when_final_always_below_suggested(self):
        entries = [
            {"final_qty": 5, "suggested_qty": 10},
            {"final_qty": 8, "suggested_qty": 20},
        ]
        self.assertEqual(trend_flow.compute_override_pattern(entries), "always_down")

    def test_mixed_when_directions_vary(self):
        entries = [
            {"final_qty": 20, "suggested_qty": 10},
            {"final_qty": 5, "suggested_qty": 10},
        ]
        self.assertEqual(trend_flow.compute_override_pattern(entries), "mixed")

    def test_none_when_final_equals_suggested(self):
        entries = [
            {"final_qty": 10, "suggested_qty": 10},
            {"final_qty": 20, "suggested_qty": 20},
        ]
        self.assertIsNone(trend_flow.compute_override_pattern(entries))

    def test_none_when_suggested_is_missing(self):
        entries = [
            {"final_qty": 10, "suggested_qty": None},
            {"final_qty": 20, "suggested_qty": None},
        ]
        self.assertIsNone(trend_flow.compute_override_pattern(entries))

    def test_none_for_empty_entries(self):
        self.assertIsNone(trend_flow.compute_override_pattern([]))


class BuildTrendReportRowsTests(unittest.TestCase):
    def _make_history(self, line_code, item_code, entries):
        return {(line_code, item_code): entries}

    def test_items_with_fewer_than_2_history_entries_excluded(self):
        items = [{"line_code": "AER-", "item_code": "X1", "description": "Bearing", "suggested_qty": 10}]
        history = self._make_history("AER-", "X1", [{"final_qty": 5, "suggested_qty": 5, "created_at": "2025-01-01"}])

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(rows, [])

    def test_items_with_2_entries_are_included(self):
        items = [{"line_code": "AER-", "item_code": "X1", "description": "Bearing", "suggested_qty": 10}]
        history = self._make_history("AER-", "X1", [
            {"final_qty": 20, "suggested_qty": 10, "created_at": "2025-02-01"},
            {"final_qty": 10, "suggested_qty": 8, "created_at": "2025-01-01"},
        ])

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["Line Code"], "AER-")
        self.assertEqual(row["Item Code"], "X1")
        self.assertEqual(row["Ordered Qty 1"], 20)
        self.assertEqual(row["Ordered Qty 2"], 10)
        self.assertEqual(row["Suggested Qty 1"], 10)
        self.assertEqual(row["Suggested Qty 2"], 8)

    def test_trend_direction_increasing(self):
        items = [{"line_code": "AER-", "item_code": "X1", "description": "", "suggested_qty": 20}]
        history = self._make_history("AER-", "X1", [
            {"final_qty": 20, "suggested_qty": 20, "created_at": "2025-02-01"},
            {"final_qty": 10, "suggested_qty": 10, "created_at": "2025-01-01"},
        ])

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(rows[0]["Trend"], "increasing")

    def test_trend_direction_decreasing(self):
        items = [{"line_code": "AER-", "item_code": "X1", "description": "", "suggested_qty": 5}]
        history = self._make_history("AER-", "X1", [
            {"final_qty": 5, "suggested_qty": 5, "created_at": "2025-02-01"},
            {"final_qty": 20, "suggested_qty": 20, "created_at": "2025-01-01"},
        ])

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(rows[0]["Trend"], "decreasing")

    def test_trend_direction_stable(self):
        items = [{"line_code": "AER-", "item_code": "X1", "description": "", "suggested_qty": 10}]
        history = self._make_history("AER-", "X1", [
            {"final_qty": 10, "suggested_qty": 10, "created_at": "2025-02-01"},
            {"final_qty": 10, "suggested_qty": 10, "created_at": "2025-01-01"},
        ])

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(rows[0]["Trend"], "stable")

    def test_override_pattern_always_up_is_surfaced(self):
        items = [{"line_code": "AER-", "item_code": "X1", "description": "", "suggested_qty": 20}]
        history = self._make_history("AER-", "X1", [
            {"final_qty": 20, "suggested_qty": 10, "created_at": "2025-02-01"},
            {"final_qty": 15, "suggested_qty": 8, "created_at": "2025-01-01"},
        ])

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(rows[0]["Override Pattern"], "always_up")

    def test_rows_sorted_by_line_code_then_item_code(self):
        items = [
            {"line_code": "ZZZ-", "item_code": "A", "description": "", "suggested_qty": 1},
            {"line_code": "AAA-", "item_code": "B", "description": "", "suggested_qty": 1},
        ]
        history = {
            ("ZZZ-", "A"): [{"final_qty": 5, "suggested_qty": 5, "created_at": "2025-02-01"}, {"final_qty": 3, "suggested_qty": 3, "created_at": "2025-01-01"}],
            ("AAA-", "B"): [{"final_qty": 5, "suggested_qty": 5, "created_at": "2025-02-01"}, {"final_qty": 3, "suggested_qty": 3, "created_at": "2025-01-01"}],
        }

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(rows[0]["Line Code"], "AAA-")
        self.assertEqual(rows[1]["Line Code"], "ZZZ-")

    def test_missing_3rd_history_entry_shows_blank(self):
        items = [{"line_code": "AER-", "item_code": "X1", "description": "", "suggested_qty": 10}]
        history = self._make_history("AER-", "X1", [
            {"final_qty": 20, "suggested_qty": 10, "created_at": "2025-02-01"},
            {"final_qty": 10, "suggested_qty": 8, "created_at": "2025-01-01"},
        ])

        rows = trend_flow.build_trend_report_rows(items, history)

        self.assertEqual(rows[0]["Ordered Qty 3"], "")
        self.assertEqual(rows[0]["Suggested Qty 3"], "")


class ExtractFullOrderHistoryTests(unittest.TestCase):
    def test_extracts_final_and_suggested_qty(self):
        snapshots = [{
            "created_at": "2025-02-01",
            "assigned_items": [
                {"line_code": "AER-", "item_code": "X1", "final_qty": 20, "suggested_qty": 10},
            ],
        }]

        history = storage.extract_full_order_history(snapshots)

        self.assertIn(("AER-", "X1"), history)
        entry = history[("AER-", "X1")][0]
        self.assertEqual(entry["final_qty"], 20)
        self.assertEqual(entry["suggested_qty"], 10)
        self.assertEqual(entry["created_at"], "2025-02-01")

    def test_excludes_zero_or_negative_final_qty(self):
        snapshots = [{
            "created_at": "2025-01-01",
            "assigned_items": [
                {"line_code": "AER-", "item_code": "X1", "final_qty": 0, "suggested_qty": 10},
                {"line_code": "AER-", "item_code": "X2", "final_qty": -5, "suggested_qty": 10},
            ],
        }]

        history = storage.extract_full_order_history(snapshots)

        self.assertNotIn(("AER-", "X1"), history)
        self.assertNotIn(("AER-", "X2"), history)

    def test_none_suggested_qty_stored_as_none(self):
        snapshots = [{
            "created_at": "2025-01-01",
            "assigned_items": [
                {"line_code": "AER-", "item_code": "X1", "final_qty": 10},
            ],
        }]

        history = storage.extract_full_order_history(snapshots)

        self.assertIsNone(history[("AER-", "X1")][0]["suggested_qty"])

    def test_multiple_snapshots_produce_multiple_entries(self):
        snapshots = [
            {"created_at": "2025-02-01", "assigned_items": [{"line_code": "A-", "item_code": "X", "final_qty": 20, "suggested_qty": 15}]},
            {"created_at": "2025-01-01", "assigned_items": [{"line_code": "A-", "item_code": "X", "final_qty": 10, "suggested_qty": 10}]},
        ]

        history = storage.extract_full_order_history(snapshots)

        self.assertEqual(len(history[("A-", "X")]), 2)
        self.assertEqual(history[("A-", "X")][0]["final_qty"], 20)
        self.assertEqual(history[("A-", "X")][1]["final_qty"], 10)

    def test_returns_empty_for_empty_snapshots(self):
        self.assertEqual(storage.extract_full_order_history([]), {})


if __name__ == "__main__":
    unittest.main()
