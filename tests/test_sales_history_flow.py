import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sales_history_flow
import parsers


class SalesHistoryFlowTests(unittest.TestCase):
    def test_annotate_sales_items_adds_span_rates_and_last_sale_recency(self):
        items = [{
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 104,
            "qty_received": 52,
        }]
        inventory_lookup = {
            ("AER-", "GH781-4"): {"last_sale": "05-Mar-2026"},
        }

        sales_history_flow.annotate_sales_items(
            items,
            inventory_lookup=inventory_lookup,
            sales_span_days=364,
            parse_date=parsers.parse_x4_date,
            now=datetime(2026, 3, 12),
        )

        item = items[0]
        self.assertEqual(item["sales_span_days"], 364)
        self.assertAlmostEqual(item["avg_weekly_sales_loaded"], 2.0, places=4)
        self.assertAlmostEqual(item["avg_monthly_sales_loaded"], 8.6964, places=3)
        self.assertAlmostEqual(item["annualized_sales_loaded"], 104.3571, places=3)
        self.assertAlmostEqual(item["avg_weekly_receipts_loaded"], 1.0, places=4)
        self.assertEqual(item["last_sale_date"], "2026-03-05")
        self.assertEqual(item["days_since_last_sale"], 7)

    def test_annotate_sales_items_leaves_recency_blank_without_last_sale(self):
        items = [{
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 8,
            "qty_received": 0,
        }]

        sales_history_flow.annotate_sales_items(
            items,
            inventory_lookup={},
            sales_span_days=None,
            parse_date=parsers.parse_x4_date,
            now=datetime(2026, 3, 12),
        )

        item = items[0]
        self.assertIsNone(item["avg_weekly_sales_loaded"])
        self.assertIsNone(item["annualized_sales_loaded"])
        self.assertEqual(item["last_sale_date"], "")
        self.assertIsNone(item["days_since_last_sale"])


if __name__ == "__main__":
    unittest.main()
