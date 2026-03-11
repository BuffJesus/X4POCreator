import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import load_flow


class LoadFlowTests(unittest.TestCase):
    def test_parse_all_files_sales_window_warning_uses_actionable_language(self):
        with patch("load_flow.parsers.parse_part_sales_csv", return_value=[{
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_received": 0,
            "qty_sold": 2,
        }]), patch(
            "load_flow.parsers.parse_sales_date_range",
            return_value=(datetime(2026, 3, 1), datetime(2026, 3, 3)),
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "sales.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        title, message = result["warnings"][0]
        self.assertEqual(title, "Sales Window Warning")
        self.assertIn("You can continue", message)
        self.assertIn("wider sales date range is recommended", message)

    def test_parse_all_files_warns_when_inventory_has_negative_qoh(self):
        with patch("load_flow.parsers.parse_part_sales_csv", return_value=[{
            "line_code": "AMS-",
            "item_code": "XLF-1G",
            "description": "5W-30 XL OIL",
            "qty_received": 0,
            "qty_sold": 2,
        }]), patch(
            "load_flow.parsers.parse_sales_date_range",
            return_value=(None, None),
        ), patch(
            "load_flow.parsers.parse_on_hand_report",
            return_value={("AMS-", "XLF-1G"): {"qoh": -12.0, "repl_cost": 45.75}},
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "sales.csv",
                    "po": "",
                    "susp": "",
                    "onhand": "onhand.csv",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
            )

        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Negative QOH Warning", warning_titles)
        self.assertEqual(result["startup_warning_rows"][0]["warning_type"], "Negative QOH Warning")
        self.assertEqual(result["startup_warning_rows"][0]["qty"], "-12")


if __name__ == "__main__":
    unittest.main()
