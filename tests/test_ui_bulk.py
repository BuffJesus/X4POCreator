import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk


class BulkUiTests(unittest.TestCase):
    def test_bulk_row_values_treats_none_qoh_as_blank(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": None, "min": 2, "max": 6, "supplier": "MOTION"}},
            order_rules={},
            _suggest_min_max=lambda key: (None, None),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "HOSE",
            "qty_sold": 2,
            "qty_suspended": 0,
            "raw_need": 3,
            "suggested_qty": 6,
            "final_qty": 6,
            "pack_size": 6,
            "vendor": "MOTION",
            "why": "Example",
            "status": "ok",
        }

        row = ui_bulk.bulk_row_values(app, item)

        self.assertEqual(row[10], "")

    def test_autosize_bulk_tree_is_noop_without_legacy_tree_editor(self):
        app = SimpleNamespace(bulk_sheet=SimpleNamespace())

        result = ui_bulk.autosize_bulk_tree(app)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
