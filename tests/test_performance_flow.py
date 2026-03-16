import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import performance_flow


class PerformanceFlowTests(unittest.TestCase):
    def test_classify_item_marks_top_performer_as_active(self):
        item = {
            "annualized_sales_loaded": 140,
            "days_since_last_sale": 12,
            "inventory_position": 5,
            "qty_on_po": 0,
        }
        inv = {"mo12_sales": 120, "qoh": 5, "min": 2}

        result = performance_flow.classify_item(item, inv)

        self.assertEqual(result["performance_profile"], "top_performer")
        self.assertEqual(result["sales_health_signal"], "active")
        self.assertFalse(result["possible_missed_reorder"])
        self.assertEqual(result["reorder_attention_signal"], "normal")

    def test_classify_item_marks_dormant_low_stock_steady_item_for_review(self):
        item = {
            "annualized_sales_loaded": 36,
            "days_since_last_sale": 500,
            "inventory_position": 1,
            "qty_on_po": 0,
        }
        inv = {"mo12_sales": 8, "qoh": 1, "min": 2}

        result = performance_flow.classify_item(item, inv)

        self.assertEqual(result["performance_profile"], "steady")
        self.assertEqual(result["sales_health_signal"], "dormant")
        self.assertTrue(result["possible_missed_reorder"])
        self.assertEqual(result["reorder_attention_signal"], "review_missed_reorder")

    def test_classify_item_marks_zero_signal_item_as_legacy(self):
        item = {
            "annualized_sales_loaded": None,
            "days_since_last_sale": None,
            "qty_on_po": 0,
        }
        inv = {"mo12_sales": 0, "qoh": 4, "min": None}

        result = performance_flow.classify_item(item, inv)

        self.assertEqual(result["performance_profile"], "legacy")
        self.assertEqual(result["sales_health_signal"], "unknown")
        self.assertFalse(result["possible_missed_reorder"])

    def test_classify_item_flags_lumpy_detailed_sales_for_review(self):
        item = {
            "annualized_sales_loaded": 48,
            "days_since_last_sale": 20,
            "inventory_position": 8,
            "qty_on_po": 0,
            "transaction_count": 4,
            "sale_day_count": 4,
            "avg_units_per_transaction": 6.0,
            "max_units_per_transaction": 18.0,
            "avg_days_between_sales": 28.0,
        }
        inv = {"mo12_sales": 0, "qoh": 8, "min": 2}

        result = performance_flow.classify_item(item, inv)

        self.assertEqual(result["detailed_sales_shape"], "lumpy_bulk")
        self.assertEqual(result["detailed_sales_shape_confidence"], "medium")
        self.assertTrue(result["detailed_sales_review_required"])
        self.assertEqual(result["reorder_attention_signal"], "review_lumpy_demand")

    def test_annotate_items_appends_detailed_sales_shape_to_why_when_present(self):
        items = [{
            "line_code": "AER-",
            "item_code": "GH781-4",
            "annualized_sales_loaded": 48,
            "days_since_last_sale": 20,
            "inventory_position": 8,
            "qty_on_po": 0,
            "transaction_count": 4,
            "sale_day_count": 4,
            "avg_units_per_transaction": 6.0,
            "max_units_per_transaction": 18.0,
            "avg_days_between_sales": 28.0,
            "why": "Base reason",
        }]

        performance_flow.annotate_items(items, inventory_lookup={("AER-", "GH781-4"): {"qoh": 8, "min": 2}})

        self.assertIn("Detailed sales shape: Lumpy / job-driven demand", items[0]["why"])


if __name__ == "__main__":
    unittest.main()
