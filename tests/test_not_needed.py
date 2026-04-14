import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rules.not_needed import not_needed_reason


class NotNeededTests(unittest.TestCase):
    def test_suspect_inventory_count_is_protected_from_auto_remove(self):
        app = SimpleNamespace(
            inventory_lookup={("ORG-", "7012"): {"qoh": 12, "min": None, "max": None}},
            on_po_qty={},
            _suggest_min_max=lambda key: (None, 2),
        )
        item = {
            "line_code": "ORG-",
            "item_code": "7012",
            "final_qty": 0,
            "suggested_qty": 0,
            "gross_need": 2,
            "demand_signal": 2,
            "inventory_position": 12,
            "target_stock": 2,
            "suspect_inventory_count": True,
        }

        reason, auto_remove = not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertFalse(auto_remove)
        self.assertIn("stock may be overstated", reason)


if __name__ == "__main__":
    unittest.main()
