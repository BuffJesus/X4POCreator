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
            po_builder.POBuilderApp._persist_suspense_carry(fake_app)

        self.assertEqual(fake_app.suspense_carry[("AER-", "GH781-4")]["qty"], 6)
        mocked_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
