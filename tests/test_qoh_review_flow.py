import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import qoh_review_flow


class FormatQohAdjustmentsTests(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(qoh_review_flow.format_qoh_adjustments({}), [])
        self.assertEqual(qoh_review_flow.format_qoh_adjustments(None), [])

    def test_single_adjustment_carries_description_and_delta(self):
        adjustments = {("AER-", "GH781"): {"old": 5, "new": 12}}
        inv = {("AER-", "GH781"): {"description": "HOSE FITTING"}}
        rows = qoh_review_flow.format_qoh_adjustments(adjustments, inv)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["line_code"], "AER-")
        self.assertEqual(row["item_code"], "GH781")
        self.assertEqual(row["description"], "HOSE FITTING")
        self.assertEqual(row["old_qoh"], 5.0)
        self.assertEqual(row["new_qoh"], 12.0)
        self.assertEqual(row["delta"], 7.0)

    def test_zero_delta_entries_are_dropped(self):
        adjustments = {
            ("AER-", "GH781"): {"old": 5, "new": 5},
            ("AER-", "OTHER"): {"old": 1, "new": 4},
        }
        rows = qoh_review_flow.format_qoh_adjustments(adjustments)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_code"], "OTHER")

    def test_rows_are_sorted_by_line_code_then_item_code(self):
        adjustments = {
            ("BAR-", "001"): {"old": 0, "new": 1},
            ("AER-", "Z99"): {"old": 0, "new": 1},
            ("AER-", "A01"): {"old": 0, "new": 1},
        }
        rows = qoh_review_flow.format_qoh_adjustments(adjustments)
        self.assertEqual(
            [(r["line_code"], r["item_code"]) for r in rows],
            [("AER-", "A01"), ("AER-", "Z99"), ("BAR-", "001")],
        )

    def test_missing_inventory_lookup_yields_blank_description(self):
        adjustments = {("AER-", "GH781"): {"old": 0, "new": 3}}
        rows = qoh_review_flow.format_qoh_adjustments(adjustments)
        self.assertEqual(rows[0]["description"], "")

    def test_negative_delta_is_preserved(self):
        adjustments = {("AER-", "GH781"): {"old": 10, "new": 4}}
        rows = qoh_review_flow.format_qoh_adjustments(adjustments)
        self.assertEqual(rows[0]["delta"], -6.0)

    def test_non_numeric_qoh_coerces_to_zero(self):
        adjustments = {("AER-", "GH781"): {"old": "x", "new": "y"}}
        rows = qoh_review_flow.format_qoh_adjustments(adjustments)
        # 0 → 0 → delta 0 → dropped
        self.assertEqual(rows, [])

    def test_skips_non_mapping_payload(self):
        adjustments = {("AER-", "GH781"): "not-a-dict"}
        self.assertEqual(qoh_review_flow.format_qoh_adjustments(adjustments), [])


class RevertQohAdjustmentsTests(unittest.TestCase):
    def test_revert_restores_inv_and_drops_adjustment(self):
        adjustments = {("AER-", "GH781"): {"old": 5, "new": 12}}
        inv = {("AER-", "GH781"): {"qoh": 12.0, "description": "HOSE"}}
        reverted = qoh_review_flow.revert_qoh_adjustments(
            adjustments, inv, [("AER-", "GH781")],
        )
        self.assertEqual(reverted, 1)
        self.assertEqual(inv[("AER-", "GH781")]["qoh"], 5.0)
        self.assertNotIn(("AER-", "GH781"), adjustments)

    def test_revert_missing_key_is_noop(self):
        adjustments = {("AER-", "GH781"): {"old": 5, "new": 12}}
        inv = {("AER-", "GH781"): {"qoh": 12.0}}
        reverted = qoh_review_flow.revert_qoh_adjustments(
            adjustments, inv, [("AER-", "MISSING")],
        )
        self.assertEqual(reverted, 0)
        self.assertIn(("AER-", "GH781"), adjustments)

    def test_revert_multiple_keys(self):
        adjustments = {
            ("AER-", "A"): {"old": 1, "new": 5},
            ("AER-", "B"): {"old": 2, "new": 8},
        }
        inv = {
            ("AER-", "A"): {"qoh": 5.0},
            ("AER-", "B"): {"qoh": 8.0},
        }
        reverted = qoh_review_flow.revert_qoh_adjustments(
            adjustments, inv, [("AER-", "A"), ("AER-", "B")],
        )
        self.assertEqual(reverted, 2)
        self.assertEqual(adjustments, {})
        self.assertEqual(inv[("AER-", "A")]["qoh"], 1.0)
        self.assertEqual(inv[("AER-", "B")]["qoh"], 2.0)

    def test_revert_handles_empty_keys(self):
        self.assertEqual(qoh_review_flow.revert_qoh_adjustments({}, {}, []), 0)


if __name__ == "__main__":
    unittest.main()
