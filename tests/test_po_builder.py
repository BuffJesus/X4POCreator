import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import po_builder
import ui_bulk_dialogs


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
        fake_app._normalize_vendor_code = lambda value: po_builder.POBuilderApp._normalize_vendor_code(value)
        fake_app._get_effective_order_qty = lambda item: po_builder.POBuilderApp._get_effective_order_qty(fake_app, item)
        fake_app._set_effective_order_qty = (
            lambda item, qty, manual_override=False: po_builder.POBuilderApp._set_effective_order_qty(
                fake_app, item, qty, manual_override=manual_override
            )
        )
        fake_app._remember_vendor_code = lambda vendor: po_builder.POBuilderApp._remember_vendor_code(fake_app, vendor)
        fake_app._rename_vendor_code = (
            lambda old_vendor, new_vendor: po_builder.POBuilderApp._rename_vendor_code(fake_app, old_vendor, new_vendor)
        )
        fake_app._clear_manual_override = lambda item: po_builder.POBuilderApp._clear_manual_override(item)
        fake_app._effective_order_rule = lambda item, rule: po_builder.POBuilderApp._effective_order_rule(fake_app, item, rule)
        fake_app._recalculate_item = lambda item: po_builder.POBuilderApp._recalculate_item(fake_app, item)
        fake_app._sync_review_item_to_filtered = (
            lambda item: po_builder.POBuilderApp._sync_review_item_to_filtered(fake_app, item)
        )
        fake_app._update_review_summary = lambda: None
        fake_app._update_bulk_summary = lambda: None
        fake_app._refresh_vendor_inputs = lambda: None
        fake_app._save_vendor_codes = lambda: None
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

    def test_quantity_helper_clamps_negative_qty_to_zero(self):
        fake_app = self._make_calc_app()
        item = {"order_qty": 7}

        po_builder.POBuilderApp._set_effective_order_qty(fake_app, item, -12, manual_override=True)

        self.assertEqual(item["final_qty"], 0)
        self.assertEqual(item["order_qty"], 0)
        self.assertTrue(item["manual_override"])

    def test_remember_vendor_code_normalizes_and_sorts(self):
        fake_app = self._make_calc_app()
        fake_app.vendor_codes_used = ["MOTION"]

        result = po_builder.POBuilderApp._remember_vendor_code(fake_app, "gregdist")

        self.assertEqual(result, "GREGDIST")
        self.assertEqual(fake_app.vendor_codes_used, ["GREGDIST", "MOTION"])

    def test_rename_vendor_code_updates_current_session_items(self):
        fake_app = self._make_calc_app()
        fake_app.vendor_codes_used = ["GREGDIST", "MOTION"]
        fake_app.filtered_items = [{"vendor": "GREGDIST"}]
        fake_app.individual_items = [{"vendor": "GREGDIST"}]
        fake_app.assigned_items = [{"vendor": "GREGDIST"}]

        result = po_builder.POBuilderApp._rename_vendor_code(fake_app, "gregdist", "source")

        self.assertEqual(result, "SOURCE")
        self.assertEqual(fake_app.vendor_codes_used, ["MOTION", "SOURCE"])
        self.assertEqual(fake_app.filtered_items[0]["vendor"], "SOURCE")
        self.assertEqual(fake_app.individual_items[0]["vendor"], "SOURCE")
        self.assertEqual(fake_app.assigned_items[0]["vendor"], "SOURCE")

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

    def test_review_negative_qty_edit_is_clamped_to_zero(self):
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

        po_builder.POBuilderApp._review_apply_editor_value(fake_app, "0", "order_qty", "-12")

        assigned = fake_app.assigned_items[0]
        self.assertEqual(filtered_item["final_qty"], 0)
        self.assertEqual(assigned["final_qty"], 0)
        self.assertEqual(assigned["order_qty"], 0)

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

    def test_bulk_pack_size_edit_recalculates_qty_and_persists_rule(self):
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
            "pack_size": 5,
            "final_qty": 10,
            "order_qty": 10,
            "manual_override": True,
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
        self.assertFalse(item["manual_override"])
        self.assertEqual(item["suggested_qty"], 12)
        self.assertEqual(item["final_qty"], 12)
        self.assertEqual(item["order_qty"], 12)
        self.assertEqual(fake_app.order_rules["AER-:GH781-4"]["pack_size"], 6)
        self.assertEqual(saved_rules["AER-:GH781-4"]["pack_size"], 6)

    def test_bulk_pack_size_edit_moves_exact_qty_item_to_pack_rounded_qty(self):
        fake_app = self._make_calc_app()
        key = ("GDY-", "5VX560")
        fake_app.inventory_lookup[key] = {"qoh": 1, "max": 3}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "BELT",
            "qty_sold": 2,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 2,
            "pack_size": None,
            "final_qty": 2,
            "order_qty": 2,
        }]
        po_builder.POBuilderApp._recalculate_item(fake_app, fake_app.filtered_items[0])

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "pack_size", "3")

        item = fake_app.filtered_items[0]
        self.assertEqual(item["order_policy"], "standard")
        self.assertEqual(item["raw_need"], 2)
        self.assertEqual(item["suggested_qty"], 3)
        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)

    def test_bulk_pack_size_edit_clears_stale_exact_policy_rule(self):
        fake_app = self._make_calc_app()
        key = ("GDY-", "5VX560")
        fake_app.inventory_lookup[key] = {"qoh": 1, "max": 3}
        fake_app.order_rules = {"GDY-:5VX560": {"order_policy": "exact_qty"}}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "BELT",
            "qty_sold": 2,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 2,
            "pack_size": None,
            "final_qty": 2,
            "order_qty": 2,
        }]

        po_builder.POBuilderApp._bulk_apply_editor_value(fake_app, "0", "pack_size", "3")

        item = fake_app.filtered_items[0]
        self.assertEqual(item["order_policy"], "standard")
        self.assertEqual(item["suggested_qty"], 3)
        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(fake_app.order_rules["GDY-:5VX560"]["pack_size"], 3)
        self.assertNotIn("order_policy", fake_app.order_rules["GDY-:5VX560"])

    def test_buy_rule_save_allow_below_pack_uses_soft_pack_without_locked_standard(self):
        fake_app = self._make_calc_app()
        fake_app.root = SimpleNamespace()
        fake_app._autosize_dialog = lambda *args, **kwargs: None
        fake_app._bulk_row_values = lambda item: ("",)
        fake_app.bulk_sheet = SimpleNamespace(refresh_row=lambda row_id, values: None)
        fake_app._apply_bulk_filter = lambda: None
        fake_app._update_bulk_summary = lambda: None
        key = ("GDY-", "5VX560")
        fake_app.inventory_lookup[key] = {"qoh": 0, "max": 3}
        fake_app.filtered_items = [{
            "line_code": key[0],
            "item_code": key[1],
            "description": "BELT",
            "qty_sold": 3,
            "qty_suspended": 0,
            "qty_on_po": 0,
            "demand_signal": 3,
            "pack_size": 12,
            "final_qty": 12,
            "order_qty": 12,
            "order_policy": "standard",
            "suggested_qty": 12,
            "raw_need": 3,
        }]
        fake_app.order_rules = {}

        created_buttons = {}

        class FakeWidget:
            def __init__(self, *args, **kwargs):
                pass
            def pack(self, *args, **kwargs):
                return self
            def grid(self, *args, **kwargs):
                return self
            def configure(self, *args, **kwargs):
                return self
            config = configure
            def bind(self, *args, **kwargs):
                return self
            def insert(self, *args, **kwargs):
                return self
            def destroy(self):
                return None
            def wait_window(self):
                return None
            def transient(self, *args, **kwargs):
                return self
            def grab_set(self, *args, **kwargs):
                return self
            def title(self, *args, **kwargs):
                return self

        class FakeTopLevel(FakeWidget):
            def configure(self, *args, **kwargs):
                return self

        class FakeStringVar:
            queue = []
            def __init__(self, value=""):
                self.value = FakeStringVar.queue.pop(0) if FakeStringVar.queue else value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        class FakeBooleanVar:
            queue = []
            def __init__(self, value=False):
                self.value = FakeBooleanVar.queue.pop(0) if FakeBooleanVar.queue else value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        class FakeEntry(FakeWidget):
            values = []
            def __init__(self, *args, **kwargs):
                self.value = FakeEntry.values.pop(0) if FakeEntry.values else ""
            def insert(self, index, text):
                if not self.value:
                    self.value = text
            def get(self):
                return self.value

        class FakeButton(FakeWidget):
            def __init__(self, *args, **kwargs):
                self.command = kwargs.get("command")
                text = kwargs.get("text", "")
                created_buttons[text] = self

        FakeStringVar.queue = ["standard", "2", "12"]
        FakeBooleanVar.queue = [True]
        FakeEntry.values = [""]

        with patch("ui_bulk_dialogs.tk.Toplevel", FakeTopLevel), \
             patch("ui_bulk_dialogs.ttk.Label", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.LabelFrame", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Combobox", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Checkbutton", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Entry", FakeEntry), \
             patch("ui_bulk_dialogs.ttk.Frame", lambda *args, **kwargs: FakeWidget()), \
             patch("ui_bulk_dialogs.ttk.Button", FakeButton), \
             patch("ui_bulk_dialogs.tk.StringVar", FakeStringVar), \
             patch("ui_bulk_dialogs.tk.BooleanVar", FakeBooleanVar), \
             patch("ui_bulk_dialogs.storage.save_order_rules", lambda *args, **kwargs: None):
            ui_bulk_dialogs.open_buy_rule_editor(fake_app, 0, po_builder.ORDER_RULES_FILE)
            created_buttons["Save Rule"].command()

        item = fake_app.filtered_items[0]
        self.assertEqual(item["order_policy"], "soft_pack")
        self.assertEqual(item["suggested_qty"], 4)
        self.assertEqual(item["final_qty"], 4)
        self.assertTrue(fake_app.order_rules["GDY-:5VX560"]["allow_below_pack"])
        self.assertEqual(fake_app.order_rules["GDY-:5VX560"]["min_order_qty"], 2)
        self.assertNotIn("order_policy", fake_app.order_rules["GDY-:5VX560"])

    def test_review_pack_size_edit_recalculates_order_qty(self):
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
            "pack_size": 5,
            "final_qty": 10,
            "order_qty": 10,
            "manual_override": True,
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
            "final_qty": filtered_item["final_qty"],
            "status": filtered_item["status"],
            "why": filtered_item["why"],
            "order_policy": filtered_item["order_policy"],
            "data_flags": list(filtered_item["data_flags"]),
            "manual_override": True,
        }]

        po_builder.POBuilderApp._review_apply_editor_value(fake_app, "0", "pack_size", "6")

        assigned = fake_app.assigned_items[0]
        self.assertFalse(filtered_item["manual_override"])
        self.assertEqual(filtered_item["pack_size"], 6)
        self.assertEqual(filtered_item["final_qty"], 12)
        self.assertEqual(assigned["final_qty"], 12)
        self.assertEqual(assigned["order_qty"], 12)

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

    def test_parse_all_files_warns_when_inventory_has_negative_qoh(self):
        original_parse_sales = po_builder.parsers.parse_part_sales_csv
        original_parse_range = po_builder.parsers.parse_sales_date_range
        original_parse_onhand = po_builder.parsers.parse_on_hand_report
        try:
            po_builder.parsers.parse_part_sales_csv = lambda path: [{
                "line_code": "AMS-",
                "item_code": "XLF-1G",
                "description": "5W-30 XL OIL",
                "qty_received": 0,
                "qty_sold": 2,
            }]
            po_builder.parsers.parse_sales_date_range = lambda path: (None, None)
            po_builder.parsers.parse_on_hand_report = lambda path: {
                ("AMS-", "XLF-1G"): {"qoh": -12.0, "repl_cost": 45.75}
            }

            result = po_builder.POBuilderApp._parse_all_files({
                "sales": "sales.csv",
                "po": "",
                "susp": "",
                "onhand": "onhand.csv",
                "minmax": "",
                "packsize": "",
            })
        finally:
            po_builder.parsers.parse_part_sales_csv = original_parse_sales
            po_builder.parsers.parse_sales_date_range = original_parse_range
            po_builder.parsers.parse_on_hand_report = original_parse_onhand

        warning_titles = [title for title, _message in result["warnings"]]
        self.assertIn("Negative QOH Warning", warning_titles)
        self.assertEqual(result["startup_warning_rows"][0]["warning_type"], "Negative QOH Warning")
        self.assertEqual(result["startup_warning_rows"][0]["qty"], "-12")


if __name__ == "__main__":
    unittest.main()
