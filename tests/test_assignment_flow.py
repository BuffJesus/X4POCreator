import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import assignment_flow
from models import AppSessionState


class AssignmentFlowTests(unittest.TestCase):
    def test_prepare_assignment_session_builds_filtered_items_and_duplicates(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 9,
            }],
            po_items=[{"line_code": "AER-", "item_code": "GH781-4", "qty": 2}],
            inventory_lookup={
                ("AER-", "GH781-4"): {"qoh": 0, "max": 10},
                ("ALT-", "GH781-4"): {"qoh": 1, "max": 2},
            },
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={("AER-", "GH781-4"): [{"qty": 1}]}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["MOTION"]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=["MOTION"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "MOTION",
                resolve_pack_size=lambda key: 6,
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertTrue(result)
        self.assertEqual(len(session.filtered_items), 1)
        self.assertEqual(session.filtered_items[0]["vendor"], "MOTION")
        self.assertEqual(session.filtered_items[0]["qty_on_po"], 2)
        self.assertEqual(session.filtered_items[0]["reorder_cycle_weeks"], 2)
        self.assertEqual(session.filtered_items[0]["performance_profile"], "legacy")
        self.assertEqual(session.filtered_items[0]["sales_health_signal"], "unknown")
        self.assertEqual(session.filtered_items[0]["detailed_sales_shape"], "")
        self.assertEqual(session.filtered_items[0]["recent_local_order_count"], 1)
        self.assertEqual(session.filtered_items[0]["recent_local_order_qty"], 1)
        self.assertTrue(session.filtered_items[0]["has_recent_local_order"])
        self.assertEqual(session.filtered_items[0]["receipt_primary_vendor"], "")
        self.assertEqual(session.filtered_items[0]["receipt_vendor_confidence"], "none")
        self.assertIn("GH781-4", session.duplicate_ic_lookup)
        self.assertEqual(session.recent_orders[("AER-", "GH781-4")][0]["qty"], 1)

    def test_prepare_assignment_session_attaches_receipt_vendor_context(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 5,
                "qty_sold": 9,
            }],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10}},
            receipt_history_lookup={("AER-", "GH781-4"): {
                "primary_vendor": "MOTION",
                "most_recent_vendor": "MOTION",
                "vendor_confidence": "high",
                "vendor_confidence_reason": "single_vendor_history",
                "vendor_candidates": ["MOTION"],
                "primary_vendor_qty_share": 1.0,
                "primary_vendor_receipt_share": 1.0,
            }},
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["MOTION"]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=["MOTION"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "MOTION",
                resolve_pack_size=lambda key: 6,
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertTrue(result)
        self.assertEqual(session.filtered_items[0]["receipt_primary_vendor"], "MOTION")
        self.assertEqual(session.filtered_items[0]["receipt_vendor_confidence"], "high")
        self.assertEqual(session.filtered_items[0]["receipt_vendor_candidates"], ["MOTION"])

    def test_prepare_assignment_session_keeps_pack_source_from_resolution(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 5,
                "qty_sold": 9,
            }],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10}},
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["MOTION"]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=["MOTION"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "MOTION",
                resolve_pack_size=lambda key: None,
                resolve_pack_size_with_source=lambda key: (25, "receipt_history"),
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertTrue(result)
        self.assertEqual(session.filtered_items[0]["pack_size"], 25)
        self.assertEqual(session.filtered_items[0]["pack_size_source"], "receipt_history")

    def test_prepare_assignment_session_carries_detailed_sales_shape_signals(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 5,
                "qty_sold": 24,
                "transaction_count": 4,
                "sale_day_count": 4,
                "avg_units_per_transaction": 6.0,
                "max_units_per_transaction": 18.0,
                "avg_days_between_sales": 28.0,
                "annualized_sales_loaded": 48.0,
            }],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10}},
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["MOTION"]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=["MOTION"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "MOTION",
                resolve_pack_size=lambda key: 6,
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertTrue(result)
        self.assertEqual(session.filtered_items[0]["detailed_sales_shape"], "lumpy_bulk")
        self.assertEqual(session.filtered_items[0]["reorder_attention_signal"], "review_lumpy_demand")
        self.assertIn("Detailed sales shape: Lumpy / job-driven demand", session.filtered_items[0]["why"])

    def test_prepare_assignment_session_marks_detailed_only_gap_for_review(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 5,
                "qty_sold": 24,
                "transaction_count": 6,
                "sale_day_count": 5,
                "avg_units_per_transaction": 3.0,
                "median_units_per_transaction": 3.0,
                "max_units_per_transaction": 4.0,
                "avg_days_between_sales": 7.0,
                "annualized_sales_loaded": 26.0,
            }],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10, "mo12_sales": 0}},
            detailed_sales_stats_lookup={("AER-", "GH781-4"): {
                "annualized_qty_sold": 26,
                "transaction_count": 6,
                "sale_day_count": 5,
                "avg_units_per_transaction": 3.0,
                "median_units_per_transaction": 3.0,
                "max_units_per_transaction": 4.0,
                "avg_days_between_sales": 7.0,
            }},
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["MOTION"]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=["MOTION"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "MOTION",
                resolve_pack_size=lambda key: 6,
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertTrue(result)
        item = session.filtered_items[0]
        self.assertEqual(item["suggested_source"], "detailed_sales_fallback")
        self.assertEqual(item["suggested_source_label"], "Detailed sales fallback")
        self.assertEqual(item["suggested_min"], 3)
        self.assertEqual(item["suggested_max"], 6)
        self.assertEqual(item["detailed_suggestion_compare"], "aligned")
        self.assertNotIn("suggestion_gap_detailed_only", item["data_flags"])

    def test_prepare_assignment_session_suppresses_receipt_heavy_detailed_fallback_to_review_gap(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 12,
                "qty_sold": 2,
            }],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10, "mo12_sales": 0}},
            receipt_history_lookup={("AER-", "GH781-4"): {
                "receipt_count": 3,
                "avg_units_per_receipt": 4.0,
            }},
            detailed_sales_stats_lookup={("AER-", "GH781-4"): {
                "annualized_qty_sold": 26,
                "transaction_count": 6,
                "sale_day_count": 5,
                "avg_units_per_transaction": 3.0,
                "median_units_per_transaction": 3.0,
                "max_units_per_transaction": 4.0,
                "avg_days_between_sales": 7.0,
            }},
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=["MOTION"]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=["MOTION"],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "MOTION",
                resolve_pack_size=lambda key: 6,
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertTrue(result)
        item = session.filtered_items[0]
        self.assertEqual(item["suggested_source"], "none")
        self.assertEqual(item["suggested_source_label"], "No suggestion")
        self.assertIsNone(item["suggested_min"])
        self.assertIsNone(item["suggested_max"])
        self.assertEqual(item["detailed_suggested_min"], 3)
        self.assertEqual(item["detailed_suggested_max"], 6)
        self.assertEqual(item["detailed_suggestion_compare"], "detailed_only")
        self.assertIn("suggestion_gap_detailed_only", item["data_flags"])
        self.assertEqual(item["receipt_sales_balance"], "receipt_heavy")
        self.assertEqual(item["reorder_attention_signal"], "review_receipt_heavy")

    def test_prepare_assignment_session_returns_false_when_no_items_remain(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 0,
            }],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 5, "min": 0, "max": 10}},
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=[]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes={"AER-"},
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys=set(),
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=[],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "",
                resolve_pack_size=lambda key: None,
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertFalse(result)
        self.assertEqual(session.filtered_items, [])

    def test_prepare_assignment_session_skips_persistently_ignored_items(self):
        session = AppSessionState(
            sales_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 9,
            }],
            inventory_lookup={
                ("AER-", "GH781-4"): {"qoh": 0, "max": 10},
            },
            order_rules={},
        )

        with patch("assignment_flow.storage.get_recent_orders", return_value={}), \
             patch("assignment_flow.storage.load_vendor_codes", return_value=[]):
            result = assignment_flow.prepare_assignment_session(
                session,
                excluded_line_codes=set(),
                excluded_customers=set(),
                dup_whitelist=set(),
                ignored_keys={"AER-:GH781-4"},
                lookback_days=14,
                order_history_path=str(ROOT / "test_order_history.json"),
                vendor_codes_path=str(ROOT / "test_vendor_codes.txt"),
                known_vendors=[],
                get_suspense_carry_qty=lambda key: 0,
                default_vendor_for_key=lambda key: "",
                resolve_pack_size=lambda key: None,
                suggest_min_max=lambda key: (None, None),
                get_cycle_weeks=lambda: 2,
                get_rule_key=lambda lc, ic: f"{lc}:{ic}",
            )

        self.assertFalse(result)
        self.assertEqual(session.filtered_items, [])


if __name__ == "__main__":
    unittest.main()
