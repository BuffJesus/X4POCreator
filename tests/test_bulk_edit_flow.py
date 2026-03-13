import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_edit_flow
import po_builder


class BulkEditFlowTests(unittest.TestCase):
    def test_apply_editor_value_vendor_remembers_code_and_updates_summary(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4", "vendor": ""}],
            inventory_lookup={},
            order_rules={},
            _remember_vendor_code=lambda value: events.append(("remember", value)),
            _update_bulk_summary=lambda: events.append(("summary", None)),
        )

        bulk_edit_flow.apply_editor_value(
            fake_app,
            "0",
            "vendor",
            "source",
            ("vendor",),
            po_builder.get_rule_key,
            lambda event, **kwargs: events.append((event, kwargs)),
        )

        self.assertEqual(fake_app.filtered_items[0]["vendor"], "SOURCE")
        self.assertIn(("remember", "SOURCE"), events)
        self.assertIn(("summary", None), events)

    def test_apply_editor_value_cur_max_creates_inventory_stub_and_recalculates(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4"}],
            inventory_lookup={},
            order_rules={},
            _recalculate_item=lambda item: events.append(("recalc", item["item_code"])),
        )

        bulk_edit_flow.apply_editor_value(
            fake_app,
            "0",
            "cur_max",
            "14",
            ("cur_max",),
            po_builder.get_rule_key,
            lambda event, **kwargs: events.append((event, kwargs)),
        )

        self.assertEqual(fake_app.inventory_lookup[("AER-", "GH781-4")]["max"], 14)
        self.assertIn(("recalc", "GH781-4"), events)


if __name__ == "__main__":
    unittest.main()
