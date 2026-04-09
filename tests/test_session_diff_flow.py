import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import session_diff_flow


def _item(lc, ic, *, qty=0, vendor="", description=""):
    return {
        "line_code": lc,
        "item_code": ic,
        "final_qty": qty,
        "vendor": vendor,
        "description": description,
    }


def _snap(items, *, created_at="2026-04-01T08:00:00", key="exported_items"):
    return {"created_at": created_at, key: items}


class LoadPreviousSnapshotTests(unittest.TestCase):
    def test_returns_first_snapshot_from_loader(self):
        sentinel = {"created_at": "2026-03-31"}

        def loader(directory, max_count):
            self.assertEqual(directory, "/fake")
            self.assertEqual(max_count, 1)
            return [sentinel]

        result = session_diff_flow.load_previous_snapshot("/fake", loader=loader)
        self.assertIs(result, sentinel)

    def test_returns_none_when_loader_empty(self):
        self.assertIsNone(
            session_diff_flow.load_previous_snapshot("/fake", loader=lambda d, max_count: [])
        )


class DiffSessionsTests(unittest.TestCase):
    def test_empty_inputs_return_empty_buckets(self):
        diff = session_diff_flow.diff_sessions(None, None)
        for bucket in ("new_items", "removed_items", "qty_increased", "qty_decreased", "vendor_changed"):
            self.assertEqual(diff[bucket], [])

    def test_new_items_appear_in_new_bucket(self):
        prev = _snap([_item("AER-", "A", qty=5)])
        curr = _snap([_item("AER-", "A", qty=5), _item("AER-", "B", qty=3)])
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(len(diff["new_items"]), 1)
        self.assertEqual(diff["new_items"][0]["item_code"], "B")
        self.assertEqual(diff["new_items"][0]["qty"], 3)

    def test_removed_items_appear_in_removed_bucket(self):
        prev = _snap([_item("AER-", "A", qty=5), _item("AER-", "B", qty=3)])
        curr = _snap([_item("AER-", "A", qty=5)])
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(len(diff["removed_items"]), 1)
        self.assertEqual(diff["removed_items"][0]["item_code"], "B")

    def test_qty_increased_records_delta(self):
        prev = _snap([_item("AER-", "A", qty=5)])
        curr = _snap([_item("AER-", "A", qty=12)])
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(len(diff["qty_increased"]), 1)
        row = diff["qty_increased"][0]
        self.assertEqual(row["old_qty"], 5)
        self.assertEqual(row["new_qty"], 12)
        self.assertEqual(row["delta"], 7)
        self.assertEqual(diff["qty_decreased"], [])

    def test_qty_decreased_records_negative_delta(self):
        prev = _snap([_item("AER-", "A", qty=12)])
        curr = _snap([_item("AER-", "A", qty=5)])
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(len(diff["qty_decreased"]), 1)
        self.assertEqual(diff["qty_decreased"][0]["delta"], -7)

    def test_vendor_change_records_old_and_new(self):
        prev = _snap([_item("AER-", "A", qty=5, vendor="VENDOR1")])
        curr = _snap([_item("AER-", "A", qty=5, vendor="vendor2")])  # case-insensitive
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(len(diff["vendor_changed"]), 1)
        row = diff["vendor_changed"][0]
        self.assertEqual(row["old_vendor"], "VENDOR1")
        self.assertEqual(row["new_vendor"], "VENDOR2")
        self.assertEqual(diff["qty_increased"], [])

    def test_qty_unchanged_and_vendor_unchanged_produces_nothing(self):
        prev = _snap([_item("AER-", "A", qty=5, vendor="V1")])
        curr = _snap([_item("AER-", "A", qty=5, vendor="V1")])
        diff = session_diff_flow.diff_sessions(prev, curr)
        for bucket in diff.values():
            self.assertEqual(bucket, [])

    def test_item_can_appear_in_qty_and_vendor_buckets_simultaneously(self):
        prev = _snap([_item("AER-", "A", qty=5, vendor="V1")])
        curr = _snap([_item("AER-", "A", qty=10, vendor="V2")])
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(len(diff["qty_increased"]), 1)
        self.assertEqual(len(diff["vendor_changed"]), 1)

    def test_assigned_items_used_when_exported_items_missing(self):
        prev = _snap([_item("AER-", "A", qty=5)], key="assigned_items")
        curr = _snap([_item("AER-", "A", qty=8)], key="assigned_items")
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(len(diff["qty_increased"]), 1)

    def test_exported_items_preferred_over_assigned_items(self):
        prev = {
            "exported_items": [_item("AER-", "A", qty=5)],
            "assigned_items": [_item("AER-", "A", qty=999)],  # ignored
        }
        curr = {
            "exported_items": [_item("AER-", "A", qty=10)],
            "assigned_items": [],
        }
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(diff["qty_increased"][0]["delta"], 5)

    def test_results_are_sorted_by_line_code_then_item_code(self):
        prev = _snap([])
        curr = _snap([
            _item("BAR-", "001"),
            _item("AER-", "Z99"),
            _item("AER-", "A01"),
        ])
        diff = session_diff_flow.diff_sessions(prev, curr)
        keys = [(r["line_code"], r["item_code"]) for r in diff["new_items"]]
        self.assertEqual(keys, [("AER-", "A01"), ("AER-", "Z99"), ("BAR-", "001")])

    def test_items_without_item_code_are_skipped(self):
        prev = _snap([])
        curr = _snap([
            {"line_code": "AER-", "item_code": "", "final_qty": 5},
            {"line_code": "AER-", "item_code": "OK", "final_qty": 5},
        ])
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual([r["item_code"] for r in diff["new_items"]], ["OK"])

    def test_order_qty_used_when_final_qty_missing(self):
        prev = _snap([{"line_code": "AER-", "item_code": "A", "order_qty": 3}])
        curr = _snap([{"line_code": "AER-", "item_code": "A", "order_qty": 8}])
        diff = session_diff_flow.diff_sessions(prev, curr)
        self.assertEqual(diff["qty_increased"][0]["delta"], 5)


class FormatDiffSummaryTests(unittest.TestCase):
    def test_blank_diff_returns_empty_string(self):
        self.assertEqual(session_diff_flow.format_diff_summary({}), "")
        self.assertEqual(
            session_diff_flow.format_diff_summary({
                "new_items": [], "removed_items": [],
                "qty_increased": [], "qty_decreased": [], "vendor_changed": [],
            }),
            "",
        )

    def test_summarizes_each_non_empty_bucket(self):
        diff = {
            "new_items": [1, 2, 3],
            "removed_items": [],
            "qty_increased": [1],
            "qty_decreased": [1, 2],
            "vendor_changed": [1],
        }
        summary = session_diff_flow.format_diff_summary(diff)
        self.assertEqual(summary, "3 new, 1 qty up, 2 qty down, 1 vendor changed")


class DiffTotalCountTests(unittest.TestCase):
    def test_sums_all_buckets(self):
        diff = {
            "new_items": [1, 2],
            "removed_items": [3],
            "qty_increased": [4, 5, 6],
            "qty_decreased": [],
            "vendor_changed": [7],
        }
        self.assertEqual(session_diff_flow.diff_total_count(diff), 7)

    def test_empty_diff_is_zero(self):
        self.assertEqual(session_diff_flow.diff_total_count({}), 0)
        self.assertEqual(session_diff_flow.diff_total_count(None), 0)


class SnapshotLabelTests(unittest.TestCase):
    def test_returns_created_at(self):
        self.assertEqual(
            session_diff_flow.snapshot_label({"created_at": "2026-04-01T08:00:00"}),
            "2026-04-01T08:00:00",
        )

    def test_blank_for_missing_or_none(self):
        self.assertEqual(session_diff_flow.snapshot_label(None), "")
        self.assertEqual(session_diff_flow.snapshot_label({}), "")


if __name__ == "__main__":
    unittest.main()
