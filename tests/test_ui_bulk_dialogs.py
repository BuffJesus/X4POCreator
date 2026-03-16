import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk_dialogs


class BulkDialogTests(unittest.TestCase):
    def test_buy_rule_field_visibility_hides_specialized_fields_by_default(self):
        visibility = ui_bulk_dialogs.buy_rule_field_visibility(advanced=False)

        self.assertFalse(visibility["trigger_qty"])
        self.assertFalse(visibility["min_packs"])
        self.assertFalse(visibility["cover_cycles"])
        self.assertFalse(visibility["overstock_qty"])
        self.assertFalse(visibility["notes"])

    def test_buy_rule_field_visibility_shows_specialized_fields_in_advanced_mode(self):
        visibility = ui_bulk_dialogs.buy_rule_field_visibility(advanced=True)

        self.assertTrue(visibility["trigger_qty"])
        self.assertTrue(visibility["trigger_pct"])
        self.assertTrue(visibility["min_packs"])
        self.assertTrue(visibility["cover_days"])
        self.assertTrue(visibility["cover_cycles"])
        self.assertTrue(visibility["overstock_qty"])
        self.assertTrue(visibility["overstock_pct"])
        self.assertTrue(visibility["notes"])

    def test_should_expand_buy_rule_advanced_only_when_specialized_values_exist(self):
        self.assertFalse(ui_bulk_dialogs.should_expand_buy_rule_advanced({
            "min_order_qty": 1,
            "pack_size": 10,
        }))
        self.assertTrue(ui_bulk_dialogs.should_expand_buy_rule_advanced({
            "minimum_cover_cycles": 2,
        }))
        self.assertTrue(ui_bulk_dialogs.should_expand_buy_rule_advanced({
            "notes": "special handling",
        }))

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

    def test_not_needed_reason_respects_acceptable_overstock_tolerance(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 0, "max": 20}},
            on_po_qty={("AER-", "GH781-4"): 0},
            _suggest_min_max=lambda key: (10, 20),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 100,
            "final_qty": 100,
            "order_qty": 100,
            "suggested_qty": 100,
            "gross_need": 20,
            "raw_need": 20,
            "inventory_position": 0,
            "target_stock": 20,
            "acceptable_overstock_qty": 80,
            "status": "ok",
        }

        reason, auto_remove = ui_bulk_dialogs.not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertIn("intentional overstock is within tolerance", reason)
        self.assertNotIn("Strong target exceed", reason)
        self.assertFalse(auto_remove)

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

    def test_not_needed_reason_does_not_auto_remove_trigger_based_replenishment(self):
        app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 150, "max": 20, "min": 5}},
            on_po_qty={("AER-", "GH781-4"): 0},
            _suggest_min_max=lambda key: (10, 20),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "pack_size": 100,
            "final_qty": 100,
            "order_qty": 100,
            "suggested_qty": 100,
            "gross_need": 50,
            "raw_need": 50,
            "inventory_position": 150,
            "target_stock": 20,
            "effective_target_stock": 200,
            "demand_signal": 30,
            "effective_qty_sold": 30,
            "effective_qty_suspended": 0,
            "order_policy": "pack_trigger",
            "reorder_needed": True,
            "reorder_trigger_threshold": 200,
            "reorder_trigger_basis": "minimum_packs_on_hand",
            "status": "ok",
        }

        reason, auto_remove = ui_bulk_dialogs.not_needed_reason(app, item, max_exceed_abs_buffer=5)

        self.assertIn("trigger-based replenishment is active", reason)
        self.assertNotIn("QOH covers demand signal", reason)
        self.assertFalse(auto_remove)

    def test_bulk_remove_not_needed_uses_saved_scope_without_prompt(self):
        class FakeSheet:
            def flush_pending_edit(self):
                pass
            def visible_row_ids(self):
                return ["0", "1"]

        app = SimpleNamespace(
            bulk_sheet=FakeSheet(),
            filtered_items=[
                {
                    "line_code": "AER-",
                    "item_code": "A",
                    "vendor": "",
                    "status": "skip",
                    "final_qty": 0,
                    "order_qty": 0,
                    "suggested_qty": 0,
                    "gross_need": 0,
                    "raw_need": 0,
                    "pack_size": 1,
                },
                {
                    "line_code": "AER-",
                    "item_code": "B",
                    "vendor": "MOTION",
                    "status": "skip",
                    "final_qty": 0,
                    "order_qty": 0,
                    "suggested_qty": 0,
                    "gross_need": 0,
                    "raw_need": 0,
                    "pack_size": 1,
                },
            ],
            inventory_lookup={
                ("AER-", "A"): {"qoh": 0, "max": 0},
                ("AER-", "B"): {"qoh": 0, "max": 0},
            },
            on_po_qty={("AER-", "A"): 0, ("AER-", "B"): 0},
            _suggest_min_max=lambda key: (0, 0),
            _get_remove_not_needed_scope=lambda: "unassigned_only",
            root=None,
            bulk_tree=SimpleNamespace(get_children=lambda: (), bbox=lambda iid: True),
            last_removed_bulk_items=[],
        )

        with patch("ui_bulk_dialogs.messagebox.askyesno") as mocked_prompt, \
             patch("ui_bulk_dialogs.tk.Toplevel", side_effect=RuntimeError("stop after candidate selection")):
            with self.assertRaisesRegex(RuntimeError, "stop after candidate selection"):
                ui_bulk_dialogs.bulk_remove_not_needed(app, "screen", 5)

        mocked_prompt.assert_not_called()

    def test_bulk_remove_not_needed_can_include_assigned_when_explicitly_requested(self):
        class FakeSheet:
            def flush_pending_edit(self):
                pass
            def visible_row_ids(self):
                return ["0", "1"]

        seen = {}

        def fake_not_needed_reason(_app, item, _buffer):
            seen.setdefault("items", []).append(item["item_code"])
            return "candidate", True

        app = SimpleNamespace(
            bulk_sheet=FakeSheet(),
            filtered_items=[
                {
                    "line_code": "AER-",
                    "item_code": "A",
                    "vendor": "",
                    "status": "skip",
                    "final_qty": 0,
                    "order_qty": 0,
                    "suggested_qty": 0,
                    "gross_need": 0,
                    "raw_need": 0,
                    "pack_size": 1,
                },
                {
                    "line_code": "AER-",
                    "item_code": "B",
                    "vendor": "MOTION",
                    "status": "skip",
                    "final_qty": 0,
                    "order_qty": 0,
                    "suggested_qty": 0,
                    "gross_need": 0,
                    "raw_need": 0,
                    "pack_size": 1,
                },
            ],
            inventory_lookup={
                ("AER-", "A"): {"qoh": 0, "max": 0},
                ("AER-", "B"): {"qoh": 0, "max": 0},
            },
            on_po_qty={("AER-", "A"): 0, ("AER-", "B"): 0},
            _suggest_min_max=lambda key: (0, 0),
            root=None,
            bulk_tree=SimpleNamespace(get_children=lambda: (), bbox=lambda iid: True),
            last_removed_bulk_items=[],
        )

        with patch("ui_bulk_dialogs.not_needed_reason", side_effect=fake_not_needed_reason), \
             patch("ui_bulk_dialogs.tk.Toplevel", side_effect=RuntimeError("stop after candidate selection")):
            with self.assertRaisesRegex(RuntimeError, "stop after candidate selection"):
                ui_bulk_dialogs.bulk_remove_not_needed(app, "screen", 5, include_assigned=True)

        self.assertEqual(seen["items"], ["A", "B"])

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
        self.assertEqual(row_lookup["Dtl Sug Min / Max"], "- / -")
        self.assertEqual(row_lookup["Sug Compare"], "-")
        self.assertEqual(row_lookup["Demand Shape"], "-")
        self.assertEqual(row_lookup["Shape Confidence"], "-")
        self.assertEqual(row_lookup["Days Since Last Sale"], "7")
        self.assertEqual(row_lookup["Recency Confidence"], "-")
        self.assertEqual(row_lookup["Data Completeness"], "-")
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
            "minimum_packs_on_hand_source": "rule",
            "minimum_cover_days": 14.0,
            "minimum_cover_cycles": 2.0,
            "recency_confidence": "medium",
            "data_completeness": "partial_recency",
            "recency_review_bucket": None,
            "acceptable_overstock_qty": 12,
            "acceptable_overstock_pct": 10.0,
            "acceptable_overstock_qty_effective": 30,
            "projected_overstock_qty": 18,
            "recommended_action": "Review Before Export",
            "shipping_policy": "hold_for_threshold",
            "shipping_policy_source": "default_preset",
            "shipping_policy_preset_label": "Threshold 2000",
            "urgent_release_mode": "paid_urgent_freight",
            "release_lead_business_days": 1,
            "release_timing_mode": "release_on_threshold",
            "release_decision": "hold_for_threshold",
            "release_reason": "Held for freight threshold 2000 (current vendor total 1200)",
            "vendor_order_value_total": 1200.0,
            "vendor_value_coverage": "partial",
            "vendor_threshold_shortfall": 800.0,
            "vendor_threshold_progress_pct": 60.0,
            "next_free_ship_date": "2026-03-13",
            "planned_export_date": "2026-03-12",
            "target_order_date": "2026-03-12",
            "target_release_date": "2026-03-13",
        }
        inv = {"qoh": 6, "min": 2, "max": 18}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Trigger Qty"], "60")
        self.assertEqual(row_lookup["Trigger %"], "20.00")
        self.assertEqual(row_lookup["Min Packs"], "2 (Saved Rule)")
        self.assertEqual(row_lookup["Cover Days"], "14.00")
        self.assertEqual(row_lookup["Cover Cycles"], "2.00")
        self.assertEqual(row_lookup["Recency Confidence"], "medium")
        self.assertEqual(row_lookup["Data Completeness"], "partial_recency")
        self.assertEqual(row_lookup["Recency Review Type"], "-")
        self.assertEqual(row_lookup["Overstock Qty"], "12")
        self.assertEqual(row_lookup["Overstock %"], "10.00")
        self.assertEqual(row_lookup["Allowed Overstock"], "30")
        self.assertEqual(row_lookup["Projected Overstock"], "18")
        self.assertEqual(row_lookup["Recommended Action"], "Review Before Export")
        self.assertEqual(row_lookup["Shipping Policy"], "hold_for_threshold")
        self.assertEqual(row_lookup["Policy Source"], "Default Preset (Threshold 2000)")
        self.assertEqual(row_lookup["Urgent Override"], "paid_urgent_freight")
        self.assertEqual(row_lookup["Release Lead Days"], "1")
        self.assertEqual(row_lookup["Timing Mode"], "release_on_threshold")
        self.assertEqual(row_lookup["Release Decision"], "hold_for_threshold")
        self.assertIn("freight threshold 2000", row_lookup["Release Reason"])
        self.assertEqual(row_lookup["Vendor Order Value"], "1200.00")
        self.assertEqual(row_lookup["Vendor Value Coverage"], "partial")
        self.assertEqual(row_lookup["Threshold Shortfall"], "800.00")
        self.assertEqual(row_lookup["Threshold Progress %"], "60.00")
        self.assertEqual(row_lookup["Next Free-Ship Date"], "2026-03-13")
        self.assertEqual(row_lookup["Planned Export Date"], "2026-03-12")
        self.assertEqual(row_lookup["Target Order Date"], "2026-03-12")
        self.assertEqual(row_lookup["Target Release Date"], "2026-03-13")

    def test_item_details_rows_label_inferred_min_packs(self):
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
            "order_policy": "pack_trigger",
            "status": "ok",
            "data_flags": [],
            "minimum_packs_on_hand": 2,
            "minimum_packs_on_hand_source": "heuristic",
        }
        inv = {"qoh": 6, "min": 2, "max": 18}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Min Packs"], "2 (Inferred)")

    def test_item_details_rows_label_inferred_cover_cycles(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 0},
            recent_orders={},
            duplicate_ic_lookup={},
            _suggest_min_max=lambda key: (10, 18),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 8,
            "qty_suspended": 0,
            "qty_received": 0,
            "qty_on_po": 0,
            "raw_need": 7,
            "suggested_qty": 10,
            "final_qty": 10,
            "order_policy": "pack_trigger",
            "status": "ok",
            "data_flags": [],
            "minimum_cover_cycles": 2,
            "minimum_cover_cycles_source": "heuristic",
        }
        inv = {"qoh": 9, "min": 2, "max": 8}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Cover Cycles"], "2.00 (Inferred)")

    def test_item_details_rows_show_recency_review_type(self):
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
            "qty_suspended": 0,
            "qty_received": 0,
            "qty_on_po": 0,
            "raw_need": 1,
            "suggested_qty": 0,
            "final_qty": 0,
            "order_policy": "manual_only",
            "status": "review",
            "data_flags": ["manual_only", "zero_final"],
            "recency_confidence": "low",
            "data_completeness": "missing_recency",
            "recency_review_bucket": "stale_or_likely_dead",
        }
        inv = {"qoh": 0, "min": 1, "max": 0}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Recency Review Type"], "Stale / likely dead")

    def test_item_details_rows_show_explicit_min_rule_recency_type(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 0},
            recent_orders={},
            duplicate_ic_lookup={},
            _suggest_min_max=lambda key: (None, None),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 1,
            "qty_suspended": 0,
            "qty_received": 0,
            "qty_on_po": 0,
            "raw_need": 1,
            "suggested_qty": 2,
            "final_qty": 2,
            "order_policy": "soft_pack",
            "package_profile": "hardware_pack",
            "replenishment_unit_mode": "soft_pack_min_order",
            "status": "ok",
            "data_flags": [],
            "recency_confidence": "low",
            "data_completeness": "missing_recency_critical_min_protected",
            "recency_review_bucket": "critical_min_rule_protected",
        }
        inv = {"qoh": 0, "min": 0, "max": 1}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Recency Review Type"], "Critical / explicit min rule")
        self.assertEqual(row_lookup["Package Profile"], "Hardware pack")
        self.assertEqual(row_lookup["Replenishment Mode"], "Soft pack / min order")

    def test_item_details_rows_show_receipt_vendor_evidence(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 0},
            recent_orders={},
            duplicate_ic_lookup={},
            _suggest_min_max=lambda key: (None, None),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 1,
            "qty_suspended": 0,
            "qty_received": 5,
            "qty_on_po": 0,
            "raw_need": 1,
            "suggested_qty": 2,
            "final_qty": 2,
            "order_policy": "soft_pack",
            "status": "ok",
            "data_flags": [],
            "receipt_primary_vendor": "MOTION",
            "receipt_vendor_confidence": "high",
            "receipt_vendor_candidates": ["MOTION", "SOURCE"],
        }
        inv = {"qoh": 0, "min": 0, "max": 1}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Receipt Vendor"], "MOTION")
        self.assertEqual(row_lookup["Receipt Confidence"], "high")
        self.assertEqual(row_lookup["Receipt Vendor Candidates"], "MOTION, SOURCE")

    def test_item_details_rows_show_detailed_sales_transaction_shape(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 0},
            recent_orders={},
            duplicate_ic_lookup={},
            _suggest_min_max=lambda key: (None, None),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 1,
            "qty_suspended": 0,
            "qty_received": 5,
            "qty_on_po": 0,
            "raw_need": 1,
            "suggested_qty": 2,
            "final_qty": 2,
            "order_policy": "soft_pack",
            "status": "ok",
            "data_flags": [],
            "transaction_count": 7,
            "sale_day_count": 5,
            "avg_units_per_transaction": 2.5,
            "median_units_per_transaction": 2,
            "max_units_per_transaction": 6,
            "avg_days_between_sales": 4.5,
        }
        inv = {"qoh": 0, "min": 0, "max": 1}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Demand Shape"], "-")
        self.assertEqual(row_lookup["Shape Confidence"], "-")
        self.assertEqual(row_lookup["Dtl Sug Min / Max"], "- / -")
        self.assertEqual(row_lookup["Sug Compare"], "-")
        self.assertEqual(row_lookup["Txn Count"], "7")
        self.assertEqual(row_lookup["Sale Days"], "5")
        self.assertEqual(row_lookup["Avg Units / Txn"], "2.50")
        self.assertEqual(row_lookup["Median Units / Txn"], "2.00")
        self.assertEqual(row_lookup["Max Units / Txn"], "6.00")
        self.assertEqual(row_lookup["Avg Days Between Sales"], "4.50")

    def test_item_details_rows_show_detailed_sales_shape(self):
        app = SimpleNamespace(
            on_po_qty={("AER-", "GH781-4"): 0},
            recent_orders={},
            duplicate_ic_lookup={},
            _suggest_min_max=lambda key: (None, None),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "qty_sold": 1,
            "qty_suspended": 0,
            "qty_received": 5,
            "qty_on_po": 0,
            "raw_need": 1,
            "suggested_qty": 2,
            "final_qty": 2,
            "order_policy": "soft_pack",
            "status": "ok",
            "data_flags": [],
            "detailed_sales_shape": "lumpy_bulk",
            "detailed_sales_shape_confidence": "medium",
            "detailed_suggested_min": 3,
            "detailed_suggested_max": 6,
            "detailed_suggestion_compare_label": "Detailed higher",
        }
        inv = {"qoh": 0, "min": 0, "max": 1}

        rows = ui_bulk_dialogs.item_details_rows(app, item, inv, ("AER-", "GH781-4"))
        row_lookup = dict(row for row in rows if row[0])

        self.assertEqual(row_lookup["Demand Shape"], "lumpy_bulk")
        self.assertEqual(row_lookup["Shape Confidence"], "medium")
        self.assertEqual(row_lookup["Dtl Sug Min / Max"], "3 / 6")
        self.assertEqual(row_lookup["Sug Compare"], "Detailed higher")

    def test_finish_bulk_final_carries_recency_fields_into_review_items(self):
        events = []
        app = SimpleNamespace(
            bulk_sheet=None,
            filtered_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "LOCAL PO HISTORY ITEM",
                "qty_sold": 0,
                "qty_suspended": 0,
                "qty_received": 0,
                "qty_on_po": 0,
                "vendor": "MOTION",
                "pack_size": 1,
                "final_qty": 2,
                "order_qty": 2,
                "status": "review",
                "why": "why",
                "core_why": "core why",
                "order_policy": "manual_only",
                "data_flags": ["manual_only"],
                "review_required": True,
                "review_resolved": False,
                "suggested_qty": 0,
                "raw_need": 2,
                "recency_confidence": "low",
                "data_completeness": "missing_recency_local_po_protected",
                "recency_review_bucket": "recent_local_po_protected",
                "performance_profile": "legacy",
                "sales_health_signal": "unknown",
                "reorder_attention_signal": "normal",
                "recent_local_order_count": 1,
                "recent_local_order_qty": 2,
                "recent_local_order_date": "2026-03-10",
                "receipt_primary_vendor": "MOTION",
                "receipt_vendor_confidence": "high",
                "receipt_vendor_candidates": ["MOTION"],
                "detailed_suggested_min": 3,
                "detailed_suggested_max": 6,
                "detailed_suggestion_compare": "detailed_only",
                "detailed_suggestion_compare_label": "Detailed only",
                "inventory_position": 0,
            }],
            _annotate_release_decisions=lambda: events.append("annotate"),
            _populate_review_tab=lambda: events.append("review"),
            notebook=SimpleNamespace(tab=lambda *args, **kwargs: None, select=lambda idx: events.append(("select", idx))),
        )

        with patch("ui_bulk_dialogs.messagebox.showinfo"), \
             patch("ui_bulk_dialogs.messagebox.askyesno", return_value=True):
            ui_bulk_dialogs.finish_bulk_final(app)

        assigned = app.assigned_items[0]
        self.assertEqual(assigned["recency_review_bucket"], "recent_local_po_protected")
        self.assertEqual(assigned["recent_local_order_qty"], 2)
        self.assertEqual(assigned["receipt_primary_vendor"], "MOTION")
        self.assertEqual(assigned["receipt_vendor_confidence"], "high")
        self.assertEqual(assigned["detailed_suggested_min"], 3)
        self.assertEqual(assigned["detailed_suggestion_compare_label"], "Detailed only")
        self.assertEqual(assigned["final_qty"], 2)
        self.assertIn("annotate", events)
        self.assertIn("review", events)


if __name__ == "__main__":
    unittest.main()
