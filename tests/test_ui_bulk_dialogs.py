import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk_dialogs


class BulkDialogTests(unittest.TestCase):
    def test_flush_pending_bulk_sheet_edit_calls_sheet_hook(self):
        calls = []
        app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: calls.append("flush")),
        )

        ui_bulk_dialogs.flush_pending_bulk_sheet_edit(app)

        self.assertEqual(calls, ["flush"])

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

    def test_not_needed_reason_does_not_auto_remove_dormant_steady_item(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 18, "max": 20, "min": 2}},
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
            "performance_profile": "steady",
            "sales_health_signal": "dormant",
            "possible_missed_reorder": False,
            "status": "ok",
        }

        reason, auto_remove = ui_bulk_dialogs.not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertIn("Inventory position already meets target", reason)
        self.assertIn("historically meaningful item is dormant", reason)
        self.assertFalse(auto_remove)

    def test_not_needed_reason_does_not_auto_remove_possible_missed_reorder(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 20, "min": 2}},
            on_po_qty={("AER-", "GH781-4"): 0},
            _suggest_min_max=lambda key: (10, 18),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 6,
            "final_qty": 0,
            "order_qty": 0,
            "suggested_qty": 0,
            "gross_need": 0,
            "raw_need": 0,
            "inventory_position": 0,
            "target_stock": 20,
            "demand_signal": 0,
            "effective_qty_sold": 0,
            "effective_qty_suspended": 0,
            "performance_profile": "steady",
            "sales_health_signal": "dormant",
            "possible_missed_reorder": True,
            "status": "skip",
        }

        reason, auto_remove = ui_bulk_dialogs.not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertIn("No net need", reason)
        self.assertIn("likely missed reorder candidate", reason)
        self.assertFalse(auto_remove)

    def test_item_details_rows_include_sales_history_and_attention_signals(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 4},
            recent_orders={("AER-", "GH781-4"): [{"qty": 2, "vendor": "MOTION", "date": "2026-03-10"}]},
            duplicate_ic_lookup={"GH781-4": {"AER-", "ALT-"}},
            _suggest_min_max=lambda key: (10, 18),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 52,
            "qty_suspended": 0,
            "qty_received": 12,
            "qty_on_po": 4,
            "raw_need": 6,
            "suggested_qty": 6,
            "final_qty": 6,
            "order_policy": "standard",
            "status": "ok",
            "data_flags": ["target_suggested_max"],
            "sales_span_days": 365,
            "sales_window_start": "2025-03-01",
            "sales_window_end": "2026-02-28",
            "avg_weekly_sales_loaded": 1.0,
            "avg_monthly_sales_loaded": 4.33,
            "annualized_sales_loaded": 52.03,
            "days_since_last_sale": 7,
            "performance_profile": "steady",
            "sales_health_signal": "active",
            "reorder_attention_signal": "normal",
        }
        inv = {
            "qoh": 9,
            "min": 2,
            "max": 6,
            "supplier": "MOTION",
            "last_receipt": "01-Mar-2026",
            "last_sale": "05-Mar-2026",
            "ytd_sales": 11,
            "mo12_sales": 22,
        }

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Sales Window"], "2025-03-01 to 2026-02-28 (365 days)")
        self.assertEqual(row_lookup["Avg Weekly Sales"], "1.00")
        self.assertEqual(row_lookup["Annualized Sales"], "52.03")
        self.assertEqual(row_lookup["Days Since Last Sale"], "7")
        self.assertEqual(row_lookup["Performance"], "steady")
        self.assertEqual(row_lookup["Sales Health"], "active")
        self.assertEqual(row_lookup["Attention"], "normal")
        self.assertEqual(row_lookup["Trigger Qty"], "-")
        self.assertEqual(row_lookup["Trigger %"], "-")
        self.assertIn("2 total: 2x via MOTION (2026-03-10)", row_lookup["Recent Orders"])
        self.assertEqual(row_lookup["Also Under"], "ALT-")

    def test_item_details_rows_handle_missing_sales_window_metrics(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 0},
            recent_orders={},
            duplicate_ic_lookup={},
            _suggest_min_max=lambda key: (None, None),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 0,
            "qty_suspended": 2,
            "qty_received": 0,
            "qty_on_po": 0,
            "raw_need": 2,
            "suggested_qty": 2,
            "final_qty": 2,
            "order_policy": "exact_qty",
            "status": "review",
            "data_flags": [],
        }
        inv = {"qoh": 0, "min": None, "max": None}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Sales Window"], "-")
        self.assertEqual(row_lookup["Avg Weekly Sales"], "-")
        self.assertEqual(row_lookup["Days Since Last Sale"], "-")
        self.assertEqual(row_lookup["Performance"], "-")
        self.assertEqual(row_lookup["Attention"], "-")

    def test_item_details_rows_include_trigger_and_overstock_fields(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 0},
            recent_orders={},
            duplicate_ic_lookup={},
            _suggest_min_max=lambda key: (10, 18),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 12,
            "qty_suspended": 0,
            "qty_received": 0,
            "qty_on_po": 0,
            "raw_need": 6,
            "suggested_qty": 6,
            "final_qty": 6,
            "order_policy": "standard",
            "status": "ok",
            "data_flags": [],
            "reorder_trigger_qty": 60,
            "reorder_trigger_pct": 20.0,
            "minimum_packs_on_hand": 2,
            "acceptable_overstock_qty": 12,
            "acceptable_overstock_pct": 10.0,
        }
        inv = {"qoh": 6, "min": 2, "max": 18}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Trigger Qty"], "60")
        self.assertEqual(row_lookup["Trigger %"], "20.00")
        self.assertEqual(row_lookup["Min Packs"], "2")
        self.assertEqual(row_lookup["Overstock Qty"], "12")
        self.assertEqual(row_lookup["Overstock %"], "10.00")


if __name__ == "__main__":
    unittest.main()
