import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_edit_flow
import po_builder
import ui_bulk


class BulkEditFlowTests(unittest.TestCase):
    def test_apply_editor_value_vendor_remembers_code_without_forcing_summary(self):
        events = []
        fake_app = SimpleNamespace(
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4", "vendor": ""}],
            inventory_lookup={},
            order_rules={},
            _remember_vendor_code=lambda value: events.append(("remember", value)),
            _bulk_summary_counts={"total": 1, "assigned": 0, "review": 0, "warning": 0},
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
        self.assertNotIn(("summary", None), events)
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 1, "assigned": 1, "review": 0, "warning": 0})

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

    def test_apply_editor_value_resolves_stable_row_id_to_matching_item(self):
        events = []
        item_a = {"line_code": "AER-", "item_code": "GH781-4", "vendor": ""}
        item_b = {"line_code": "MOT-", "item_code": "ABC123", "vendor": ""}
        fake_app = SimpleNamespace(
            filtered_items=[item_b, item_a],
            inventory_lookup={},
            order_rules={},
            _remember_vendor_code=lambda value: events.append(("remember", value)),
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            _find_filtered_item=lambda key: po_builder.POBuilderApp._find_filtered_item(SimpleNamespace(filtered_items=[item_b, item_a]), key),
        )

        bulk_edit_flow.apply_editor_value(
            fake_app,
            ui_bulk.bulk_row_id(item_a),
            "vendor",
            "source",
            ("vendor",),
            po_builder.get_rule_key,
            lambda event, **kwargs: events.append((event, kwargs)),
        )

        self.assertEqual(item_a["vendor"], "SOURCE")
        self.assertEqual(item_b["vendor"], "")
        self.assertIn(("remember", "SOURCE"), events)


if __name__ == "__main__":
    unittest.main()
