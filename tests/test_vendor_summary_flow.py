import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import vendor_summary_flow


def _item(lc, ic, *, vendor="", qty=0, received=0, description=""):
    return {
        "line_code": lc,
        "item_code": ic,
        "vendor": vendor,
        "final_qty": qty,
        "qty_received": received,
        "description": description,
    }


def _snap(items, *, created_at="2026-04-01T08:00:00", key="exported_items"):
    return {"created_at": created_at, key: items}


class SummarizeVendorTests(unittest.TestCase):
    def test_blank_vendor_returns_empty_summary(self):
        summary = vendor_summary_flow.summarize_vendor("", [])
        self.assertEqual(summary["vendor_code"], "")
        self.assertEqual(summary["session_count"], 0)
        self.assertEqual(summary["order_count"], 0)
        self.assertEqual(summary["top_items"], [])

    def test_no_snapshots_returns_zero_counts(self):
        summary = vendor_summary_flow.summarize_vendor("GRELIN", [])
        self.assertEqual(summary["vendor_code"], "GRELIN")
        self.assertEqual(summary["session_count"], 0)
        self.assertIsNone(summary["inferred_lead_days"])

    def test_normalizes_vendor_code_to_upper(self):
        snapshots = [_snap([_item("AER-", "A", vendor="grelin", qty=5)])]
        summary = vendor_summary_flow.summarize_vendor(" grelin ", snapshots)
        self.assertEqual(summary["vendor_code"], "GRELIN")
        self.assertEqual(summary["order_count"], 1)
        self.assertEqual(summary["total_qty_ordered"], 5)

    def test_session_count_only_counts_snapshots_with_vendor(self):
        snapshots = [
            _snap([_item("AER-", "A", vendor="GRELIN", qty=3)], created_at="2026-04-01"),
            _snap([_item("AER-", "B", vendor="OTHER", qty=2)], created_at="2026-03-25"),
            _snap([_item("AER-", "C", vendor="GRELIN", qty=4)], created_at="2026-03-18"),
        ]
        summary = vendor_summary_flow.summarize_vendor("GRELIN", snapshots)
        self.assertEqual(summary["session_count"], 2)
        self.assertEqual(summary["order_count"], 2)
        self.assertEqual(summary["total_qty_ordered"], 7)

    def test_last_session_date_picks_most_recent(self):
        snapshots = [
            _snap([_item("AER-", "A", vendor="GRELIN", qty=1)], created_at="2026-03-15"),
            _snap([_item("AER-", "B", vendor="GRELIN", qty=2)], created_at="2026-04-01"),
            _snap([_item("AER-", "C", vendor="GRELIN", qty=3)], created_at="2026-03-22"),
        ]
        summary = vendor_summary_flow.summarize_vendor("GRELIN", snapshots)
        self.assertEqual(summary["last_session_date"], "2026-04-01")

    def test_total_qty_received_sums_across_snapshots(self):
        snapshots = [
            _snap([_item("AER-", "A", vendor="GRELIN", qty=10, received=4)]),
            _snap([_item("AER-", "A", vendor="GRELIN", qty=10, received=8)]),
        ]
        summary = vendor_summary_flow.summarize_vendor("GRELIN", snapshots)
        self.assertEqual(summary["total_qty_received"], 12)

    def test_top_items_sorted_by_qty_descending(self):
        snapshots = [
            _snap([
                _item("AER-", "SMALL", vendor="GRELIN", qty=2, description="small"),
                _item("AER-", "BIG",   vendor="GRELIN", qty=20, description="big"),
                _item("AER-", "MED",   vendor="GRELIN", qty=10, description="med"),
            ]),
        ]
        summary = vendor_summary_flow.summarize_vendor("GRELIN", snapshots, top_n=2)
        codes = [t["item_code"] for t in summary["top_items"]]
        self.assertEqual(codes, ["BIG", "MED"])
        self.assertEqual(summary["top_items"][0]["description"], "big")

    def test_top_items_aggregates_across_snapshots(self):
        snapshots = [
            _snap([_item("AER-", "A", vendor="GRELIN", qty=5)]),
            _snap([_item("AER-", "A", vendor="GRELIN", qty=8)]),
            _snap([_item("AER-", "A", vendor="GRELIN", qty=3)]),
        ]
        summary = vendor_summary_flow.summarize_vendor("GRELIN", snapshots, top_n=5)
        self.assertEqual(len(summary["top_items"]), 1)
        self.assertEqual(summary["top_items"][0]["qty"], 16)

    def test_lead_times_lookup_used_when_supplied(self):
        snapshots = [_snap([_item("AER-", "A", vendor="GRELIN", qty=1)])]
        summary = vendor_summary_flow.summarize_vendor(
            "GRELIN", snapshots, lead_times={"GRELIN": 7},
        )
        self.assertEqual(summary["inferred_lead_days"], 7)

    def test_lead_times_missing_for_vendor_returns_none(self):
        snapshots = [_snap([_item("AER-", "A", vendor="GRELIN", qty=1)])]
        summary = vendor_summary_flow.summarize_vendor(
            "GRELIN", snapshots, lead_times={"OTHER": 4},
        )
        self.assertIsNone(summary["inferred_lead_days"])

    def test_assigned_items_used_when_exported_items_missing(self):
        snapshots = [_snap([_item("AER-", "A", vendor="GRELIN", qty=5)], key="assigned_items")]
        summary = vendor_summary_flow.summarize_vendor("GRELIN", snapshots)
        self.assertEqual(summary["order_count"], 1)
        self.assertEqual(summary["total_qty_ordered"], 5)


class SummarizeAllVendorsTests(unittest.TestCase):
    def test_empty_snapshots_returns_empty_list(self):
        self.assertEqual(vendor_summary_flow.summarize_all_vendors([]), [])

    def test_discovers_every_vendor_when_no_filter_supplied(self):
        snapshots = [_snap([
            _item("AER-", "A", vendor="GRELIN", qty=1),
            _item("AER-", "B", vendor="OTHER",  qty=2),
        ])]
        result = vendor_summary_flow.summarize_all_vendors(snapshots)
        codes = sorted(s["vendor_code"] for s in result)
        self.assertEqual(codes, ["GRELIN", "OTHER"])

    def test_restricts_to_supplied_vendor_codes(self):
        snapshots = [_snap([
            _item("AER-", "A", vendor="GRELIN", qty=1),
            _item("AER-", "B", vendor="OTHER",  qty=2),
        ])]
        result = vendor_summary_flow.summarize_all_vendors(snapshots, vendor_codes=["GRELIN"])
        self.assertEqual([s["vendor_code"] for s in result], ["GRELIN"])

    def test_sorted_by_order_count_descending(self):
        snapshots = [_snap([
            _item("AER-", "A", vendor="ALPHA", qty=1),
            _item("AER-", "B", vendor="ALPHA", qty=1),
            _item("AER-", "C", vendor="ALPHA", qty=1),
            _item("AER-", "D", vendor="BETA",  qty=1),
            _item("AER-", "E", vendor="BETA",  qty=1),
            _item("AER-", "F", vendor="GAMMA", qty=1),
        ])]
        result = vendor_summary_flow.summarize_all_vendors(snapshots)
        codes = [s["vendor_code"] for s in result]
        self.assertEqual(codes, ["ALPHA", "BETA", "GAMMA"])

    def test_lead_times_propagated_to_each_summary(self):
        snapshots = [_snap([_item("AER-", "A", vendor="GRELIN", qty=1)])]
        result = vendor_summary_flow.summarize_all_vendors(
            snapshots, lead_times={"GRELIN": 5},
        )
        self.assertEqual(result[0]["inferred_lead_days"], 5)


class StripVendorHintTests(unittest.TestCase):
    def test_strips_parenthetical_suffix(self):
        self.assertEqual(
            vendor_summary_flow.strip_vendor_hint("GRELIN (lead ~7d)"),
            "GRELIN",
        )

    def test_returns_bare_code_unchanged(self):
        self.assertEqual(vendor_summary_flow.strip_vendor_hint("GRELIN"), "GRELIN")

    def test_handles_none_and_empty(self):
        self.assertEqual(vendor_summary_flow.strip_vendor_hint(None), "")
        self.assertEqual(vendor_summary_flow.strip_vendor_hint(""), "")

    def test_strips_leading_trailing_whitespace(self):
        self.assertEqual(
            vendor_summary_flow.strip_vendor_hint("  GRELIN (lead ~7d)  "),
            "GRELIN",
        )


class FormatVendorComboValueTests(unittest.TestCase):
    def test_known_lead_time_appends_hint(self):
        self.assertEqual(
            vendor_summary_flow.format_vendor_combo_value("grelin", 7),
            "GRELIN (lead ~7d)",
        )

    def test_unknown_lead_time_returns_bare_code(self):
        self.assertEqual(
            vendor_summary_flow.format_vendor_combo_value("GRELIN", None),
            "GRELIN",
        )

    def test_zero_lead_time_returns_bare_code(self):
        self.assertEqual(
            vendor_summary_flow.format_vendor_combo_value("GRELIN", 0),
            "GRELIN",
        )

    def test_blank_vendor_returns_blank(self):
        self.assertEqual(vendor_summary_flow.format_vendor_combo_value("", 5), "")


class FormatLeadTimeLabelTests(unittest.TestCase):
    def test_none_returns_blank(self):
        self.assertEqual(vendor_summary_flow.format_lead_time_label(None), "")

    def test_positive_integer(self):
        self.assertEqual(vendor_summary_flow.format_lead_time_label(7), "~7d")

    def test_zero_or_negative_returns_blank(self):
        self.assertEqual(vendor_summary_flow.format_lead_time_label(0), "")
        self.assertEqual(vendor_summary_flow.format_lead_time_label(-3), "")

    def test_non_numeric_returns_blank(self):
        self.assertEqual(vendor_summary_flow.format_lead_time_label("foo"), "")


if __name__ == "__main__":
    unittest.main()
