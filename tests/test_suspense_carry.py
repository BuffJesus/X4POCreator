import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import po_builder


class SuspenseCarryTests(unittest.TestCase):
    def test_persist_suspense_carry_consumes_prior_by_sales_and_adds_new_covered_suspense(self):
        fake_app = SimpleNamespace(
            filtered_items=[
                {
                    "line_code": "AER-",
                    "item_code": "GH781-4",
                    "qty_sold": 2,
                    "qty_suspended": 8,
                    "effective_qty_suspended": 3,
                    "vendor": "GREGDIST",
                    "final_qty": 3,
                    "order_qty": 3,
                }
            ],
            suspense_carry={("AER-", "GH781-4"): {"qty": 5, "updated_at": "2026-03-10T00:00:00"}},
            _loaded_suspense_carry={("AER-", "GH781-4"): {"qty": 5, "updated_at": "2026-03-10T00:00:00"}},
        )
        fake_app._get_suspense_carry_qty = lambda key: po_builder.POBuilderApp._get_suspense_carry_qty(fake_app, key)
        fake_app._data_path = lambda key: f"C:\\Temp\\{key}"

        with patch("po_builder.storage.save_suspense_carry") as mocked_save:
            mocked_save.return_value = {"payload": {("AER-", "GH781-4"): {"qty": 6, "updated_at": "2026-03-10T12:00:00"}}, "meta": None, "conflict": False}
            result = po_builder.POBuilderApp._persist_suspense_carry(fake_app)

        self.assertEqual(fake_app.suspense_carry[("AER-", "GH781-4")]["qty"], 6)
        self.assertFalse(result["conflict"])
        mocked_save.assert_called_once()

    def test_persist_suspense_carry_logs_when_shared_merge_conflict_occurs(self):
        fake_app = SimpleNamespace(
            filtered_items=[
                {
                    "line_code": "AER-",
                    "item_code": "GH781-4",
                    "qty_sold": 0,
                    "qty_suspended": 2,
                    "effective_qty_suspended": 2,
                    "vendor": "GREGDIST",
                    "final_qty": 2,
                    "order_qty": 2,
                }
            ],
            suspense_carry={},
            _loaded_suspense_carry={},
        )
        fake_app._get_suspense_carry_qty = lambda key: po_builder.POBuilderApp._get_suspense_carry_qty(fake_app, key)
        fake_app._data_path = lambda key: f"C:\\Temp\\{key}"

        with patch("po_builder.storage.save_suspense_carry") as mocked_save, \
             patch("po_builder.write_debug") as mocked_debug:
            mocked_save.return_value = {
                "payload": {("AER-", "GH781-4"): {"qty": 2, "updated_at": "2026-03-10T12:00:00"}},
                "meta": None,
                "conflict": True,
            }
            result = po_builder.POBuilderApp._persist_suspense_carry(fake_app)

        self.assertTrue(result["conflict"])
        mocked_debug.assert_called_once()
        self.assertEqual(mocked_debug.call_args.args[0], "suspense_carry.merge_conflict")


if __name__ == "__main__":
    unittest.main()
