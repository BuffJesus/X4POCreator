import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk_dialogs


class BulkDialogTests(unittest.TestCase):
    def test_not_needed_reason_treats_none_qoh_as_zero(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": None, "max": 20}},
            on_po_qty={("AER-", "GH781-4"): 4},
            _suggest_min_max=lambda key: (10, 18),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 6,
            "final_qty": 6,
            "order_qty": 6,
            "suggested_qty": 0,
            "gross_need": 0,
            "raw_need": 0,
            "target_stock": 20,
            "demand_signal": 0,
            "effective_qty_sold": 0,
            "effective_qty_suspended": 0,
            "status": "ok",
        }

        reason, auto_remove = ui_bulk_dialogs.not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertIn("No uncovered demand signal", reason)
        self.assertTrue(auto_remove)

    def test_not_needed_reason_flags_soft_max_exceed_and_auto_remove(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 40, "max": 50}},
            on_po_qty={("AER-", "GH781-4"): 10},
            _suggest_min_max=lambda key: (20, 60),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 25,
            "final_qty": 80,
            "order_qty": 80,
            "suggested_qty": 25,
            "gross_need": 20,
            "raw_need": 20,
            "status": "ok",
        }

        reason, auto_remove = ui_bulk_dialogs.not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertIn("Strong target exceed", reason)
        self.assertIn("Final qty far above suggestion", reason)
        self.assertTrue(auto_remove)

    def test_not_needed_reason_flags_inventory_position_already_at_target(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 18, "max": 20}},
            on_po_qty={("AER-", "GH781-4"): 4},
            _suggest_min_max=lambda key: (10, 18),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 6,
            "final_qty": 6,
            "order_qty": 6,
            "suggested_qty": 0,
            "gross_need": 0,
            "raw_need": 0,
            "inventory_position": 22,
            "target_stock": 20,
            "demand_signal": 0,
            "effective_qty_sold": 0,
            "effective_qty_suspended": 0,
            "status": "ok",
        }

        reason, auto_remove = ui_bulk_dialogs.not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertIn("Inventory position already meets target", reason)
        self.assertIn("No uncovered demand signal", reason)
        self.assertTrue(auto_remove)


if __name__ == "__main__":
    unittest.main()
