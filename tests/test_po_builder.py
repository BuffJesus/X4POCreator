import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import po_builder


class POBuilderTests(unittest.TestCase):
    def _make_calc_app(self):
        fake_app = SimpleNamespace(
            inventory_lookup={},
            order_rules={},
            filtered_items=[],
            qoh_adjustments={},
            vendor_codes_used=[],
            _suggest_min_max=lambda key: (None, None),
        )
        fake_app._find_filtered_item = lambda key: po_builder.POBuilderApp._find_filtered_item(fake_app, key)
        fake_app._get_effective_order_qty = lambda item: po_builder.POBuilderApp._get_effective_order_qty(fake_app, item)
        fake_app._set_effective_order_qty = (
            lambda item, qty, manual_override=False: po_builder.POBuilderApp._set_effective_order_qty(
                fake_app, item, qty, manual_override=manual_override
            )
        )
        fake_app._recalculate_item = lambda item: po_builder.POBuilderApp._recalculate_item(fake_app, item)
        fake_app._sync_review_item_to_filtered = (
            lambda item: po_builder.POBuilderApp._sync_review_item_to_filtered(fake_app, item)
        )
        fake_app._update_review_summary = lambda: None
        return fake_app

    def test_default_vendor_for_key_uses_supplier(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"supplier": "motion "}},
        )

        result = po_builder.POBuilderApp._default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "MOTION")

    def test_default_vendor_for_key_returns_blank_without_supplier(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"supplier": ""}},
        )

        result = po_builder.POBuilderApp._default_vendor_for_key(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, "")

    def test_suggest_min_max_skips_sparse_history(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 2}},
            _get_cycle_weeks=lambda: 2,
        )

        result = po_builder.POBuilderApp._suggest_min_max(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, (None, None))

    def test_suggest_min_max_uses_cycle_for_non_sparse_history(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 26}},
            _get_cycle_weeks=lambda: 2,
        )

        result = po_builder.POBuilderApp._suggest_min_max(fake_app, ("AER-", "GH781-4"))

        self.assertEqual(result, (1, 2))

    def test_quantity_helpers_keep_fields_aligned(self):
        fake_app = self._make_calc_app()
        item = {"order_qty": 7}

        self.assertEqual(po_builder.POBuilderApp._get_effective_order_qty(fake_app, item), 7)
        po_builder.POBuilderApp._set_effective_order_qty(fake_app, item, 3, manual_override=True)

        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)
        self.assertTrue(item["manual_override"])

    def test_bulk_qoh_edit_recalculates_item_fields(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 2, "max": 10}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 8,
            "pack_size": 4,
            "final_qty": 8,
            "order_qty": 8,
        }]

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "qoh", "10")

        item = fake_app.filtered_items[0]
        self.assertEqual(fake_app.qoh_adjustments[key]["new"], 10.0)
        self.assertEqual(item["raw_need"], 0)
        self.assertEqual(item["final_qty"], 0)
        self.assertEqual(item["status"], "skip")
        self.assertIn("inventory_covers_target", item["data_flags"])

    def test_bulk_final_qty_edit_preserves_override_and_recalculates_context(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 2, "max": 10}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 8,
            "pack_size": 4,
            "final_qty": 8,
            "order_qty": 8,
        }]

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "final_qty", "3")

        item = fake_app.filtered_items[0]
        self.assertTrue(item["manual_override"])
        self.assertEqual(item["raw_need"], 8)
        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)
        self.assertIn("Target stock: 10", item["why"])

    def test_review_qty_edit_syncs_and_recalculates_status(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        filtered_item = {
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 9,
            "vendor": "MOTION",
            "pack_size": 6,
            "final_qty": 12,
            "order_qty": 12,
        }
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 10}
        fake_app.filtered_items = [filtered_item]
        po_builder.POBuilderApp._recalculate_item(fake_app, filtered_item)
        fake_app.assigned_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "vendor": "MOTION",
            "pack_size": filtered_item["pack_size"],
            "order_qty": filtered_item["order_qty"],
            "status": filtered_item["status"],
            "why": filtered_item["why"],
            "order_policy": filtered_item["order_policy"],
            "data_flags": list(filtered_item["data_flags"]),
        }]

        po_builder.POBuilderApp._review_apply_editor_value(fake_app, "0", "order_qty", "0")

        assigned = fake_app.assigned_items[0]
        self.assertEqual(filtered_item["final_qty"], 0)
        self.assertEqual(assigned["final_qty"], 0)
        self.assertEqual(assigned["status"], "warning")
        self.assertIn("zero_final", assigned["data_flags"])

    def test_bulk_cur_max_edit_recalculates_raw_need(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 2, "min": 1, "max": 6}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 8,
            "pack_size": 4,
            "final_qty": 4,
            "order_qty": 4,
        }]
        po_builder.POBuilderApp._recalculate_item(fake_app, fake_app.filtered_items[0])

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "cur_max", "14")

        item = fake_app.filtered_items[0]
        self.assertEqual(fake_app.inventory_lookup[key]["max"], 14)
        self.assertEqual(item["raw_need"], 12)
        self.assertEqual(item["final_qty"], 12)
        self.assertEqual(item["target_stock"], 14)

    def test_bulk_pack_size_edit_recalculates_and_persists_rule(self):
        fake_app = self._make_calc_app()
        key = ("AER-", "GH781-4")
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 10}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "HOSE",
            "qty_sold": 9,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 9,
            "pack_size": 4,
            "final_qty": 12,
            "order_qty": 12,
        }]
        po_builder.POBuilderApp._recalculate_item(fake_app, fake_app.filtered_items[0])

        saved_rules = {}
        original_save = po_builder.storage.save_order_rules
        try:
            po_builder.storage.save_order_rules = lambda path, rules: saved_rules.update(rules)
            po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "pack_size", "6")
        finally:
            po_builder.storage.save_order_rules = original_save

        item = fake_app.filtered_items[0]
        self.assertEqual(item["pack_size"], 6)
        self.assertEqual(item["final_qty"], 12)
        self.assertEqual(fake_app.order_rules["AER-:GH781-4"]["pack_size"], 6)
        self.assertEqual(saved_rules["AER-:GH781-4"]["pack_size"], 6)

    def test_parse_all_files_sales_window_warning_uses_actionable_language(self):
        original_parse_sales = po_builder.parsers.parse_part_sales_csv
        original_parse_range = po_builder.parsers.parse_sales_date_range
        try:
            po_builder.parsers.parse_part_sales_csv = lambda path: [{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_received": 0,
                "qty_sold": 2,
            }]
            po_builder.parsers.parse_sales_date_range = lambda path: (
                datetime(2026, 3, 1),
                datetime(2026, 3, 3),
            )

            result = po_builder.POBuilderApp._parse_all_files({
                "sales": "sales.csv",
                "po": "",
                "susp": "",
                "onhand": "",
                "minmax": "",
                "packsize": "",
            })
        finally:
            po_builder.parsers.parse_part_sales_csv = original_parse_sales
            po_builder.parsers.parse_sales_date_range = original_parse_range

        title, message = result["warnings"][0]
        self.assertEqual(title, "Sales Window Warning")
        self.assertIn("You can continue", message)
        self.assertIn("wider sales date range is recommended", message)


if __name__ == "__main__":
    unittest.main()
