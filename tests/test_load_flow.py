import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import load_flow
from models import AppSessionState


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

    def test_apply_load_result_populates_session_fields(self):
        session = AppSessionState()
        result = {
            "sales_items": [{"line_code": "AER-", "item_code": "GH781-4"}],
            "all_line_codes": ["AER-"],
            "po_items": [{"line_code": "AER-", "item_code": "GH781-4", "qty": 2}],
            "open_po_lookup": {("AER-", "GH781-4"): [{"qty": 2}]},
            "inventory_lookup": {("AER-", "GH781-4"): {"qoh": 5}},
            "pack_size_lookup": {("AER-", "GH781-4"): 6},
            "startup_warning_rows": [{"warning_type": "Example"}],
        }

        load_flow.apply_load_result(session, result, parsers_module=type("P", (), {
            "build_pack_size_fallbacks": staticmethod(lambda lookup: ({"GH781-4": 6}, {"DUP-1"})),
        }))

        self.assertEqual(session.sales_items, result["sales_items"])
        self.assertEqual(session.inventory_source_lookup, result["inventory_lookup"])
        self.assertEqual(session.pack_size_by_item, {"GH781-4": 6})
        self.assertEqual(session.pack_size_conflicts, {"DUP-1"})

    def test_parse_all_files_old_po_warning_includes_po_reference(self):
        with patch("load_flow.parsers.parse_part_sales_csv", return_value=[{
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_received": 0,
            "qty_sold": 2,
        }]), patch(
            "load_flow.parsers.parse_sales_date_range",
            return_value=(None, None),
        ), patch(
            "load_flow.parsers.parse_po_listing_csv",
            return_value=[{
                "po_number": "PO12345",
                "line_code": "AER-",
                "item_code": "GH781-4",
                "po_type": "S",
                "qty": 6,
                "date_issued": "01-Jan-2025",
            }],
        ):
            result = load_flow.parse_all_files(
                {
                    "sales": "sales.csv",
                    "po": "po.csv",
                    "susp": "",
                    "onhand": "",
                    "minmax": "",
                    "packsize": "",
                },
                old_po_warning_days=90,
                short_sales_window_days=7,
                now=datetime(2026, 3, 10),
            )

        rows = [row for row in result["startup_warning_rows"] if row["warning_type"] == "Old Open PO Warning"]
        self.assertEqual(len(rows), 1)
        self.assertIn("PO12345/S 01-Jan-2025 qty 6", rows[0]["po_reference"])


if __name__ == "__main__":
    unittest.main()
