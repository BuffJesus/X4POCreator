import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import item_workflow
from models import AppSessionState


class ItemWorkflowTests(unittest.TestCase):
    def test_set_effective_order_qty_keeps_fields_aligned(self):
        item = {"order_qty": 7}

        item_workflow.set_effective_order_qty(item, 3, manual_override=True)

        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)
        self.assertTrue(item["manual_override"])

    def test_set_effective_order_qty_clamps_negative_qty_to_zero(self):
        item = {"order_qty": 7}

        item_workflow.set_effective_order_qty(item, -12, manual_override=True)

        self.assertEqual(item["final_qty"], 0)
        self.assertEqual(item["order_qty"], 0)
        self.assertTrue(item["manual_override"])

    def test_find_filtered_item_returns_matching_item(self):
        items = [
            {"line_code": "AER-", "item_code": "GH781-4"},
            {"line_code": "AMS-", "item_code": "XLF-1G"},
        ]

        result = item_workflow.find_filtered_item(items, ("AMS-", "XLF-1G"))

        self.assertIs(result, items[1])

    def test_apply_pack_size_edit_updates_item_and_rule(self):
        item = {"line_code": "AER-", "item_code": "GH781-4", "pack_size": 5}
        order_rules = {"AER-:GH781-4": {"order_policy": "standard"}}

        rule_key, rule = item_workflow.apply_pack_size_edit(
            item,
            "12",
            order_rules,
            lambda line_code, item_code: f"{line_code}:{item_code}",
        )

        self.assertEqual(rule_key, "AER-:GH781-4")
        self.assertEqual(item["pack_size"], 12)
        self.assertEqual(rule["pack_size"], 12)
        self.assertNotIn("order_policy", rule)

    def test_recalculate_item_from_session_uses_session_state(self):
        session = AppSessionState(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}},
            order_rules={},
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 6,
        }

        item_workflow.recalculate_item_from_session(item, session, lambda key: (None, None), lambda lc, ic: f"{lc}:{ic}")

        self.assertEqual(item["final_qty"], 12)
        self.assertEqual(item["order_qty"], 12)

    def test_recalculate_item_from_session_stamps_detailed_suggestion_context(self):
        session = AppSessionState(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026", "mo12_sales": 0}},
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
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 6,
        }

        item_workflow.recalculate_item_from_session(item, session, lambda key: (None, None), lambda lc, ic: f"{lc}:{ic}")

        self.assertEqual(item["detailed_suggested_min"], 3)
        self.assertEqual(item["detailed_suggested_max"], 6)
        self.assertEqual(item["detailed_suggestion_compare"], "detailed_only")
        self.assertIn("Detailed sales-only suggestion: 3 / 6", item["why"])

    def test_sync_review_item_to_filtered_from_session_uses_session_state(self):
        filtered = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 6,
            "vendor": "MOTION",
        }
        review = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 6,
            "vendor": "SOURCE",
            "order_qty": 3,
            "manual_override": True,
        }
        session = AppSessionState(
            filtered_items=[filtered],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026"}},
            order_rules={},
        )

        item_workflow.sync_review_item_to_filtered_from_session(
            review,
            session,
            lambda key: (None, None),
            lambda lc, ic: f"{lc}:{ic}",
        )

        self.assertEqual(filtered["vendor"], "SOURCE")
        self.assertEqual(filtered["final_qty"], 3)
        self.assertEqual(review["final_qty"], 3)

    def test_sync_review_item_to_filtered_from_session_carries_detailed_suggestion_fields(self):
        filtered = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "pack_size": 6,
            "vendor": "MOTION",
        }
        review = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 6,
            "vendor": "SOURCE",
            "order_qty": 3,
            "manual_override": True,
        }
        session = AppSessionState(
            filtered_items=[filtered],
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 10, "last_sale": "05-Mar-2026", "last_receipt": "01-Mar-2026", "mo12_sales": 0}},
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

        item_workflow.sync_review_item_to_filtered_from_session(
            review,
            session,
            lambda key: (None, None),
            lambda lc, ic: f"{lc}:{ic}",
        )

        self.assertEqual(review["detailed_suggested_min"], 3)
        self.assertEqual(review["detailed_suggested_max"], 6)
        self.assertEqual(review["detailed_suggestion_compare"], "detailed_only")


if __name__ == "__main__":
    unittest.main()
