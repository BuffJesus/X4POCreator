import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_review


class UIReviewTests(unittest.TestCase):
    def test_tree_selected_values_or_first_uses_first_row_when_nothing_selected(self):
        class Tree:
            def __init__(self):
                self.selected = []
            def selection(self):
                return tuple(self.selected)
            def get_children(self):
                return ("0", "1")
            def selection_set(self, item_id):
                self.selected = [item_id]
            def item(self, item_id, field):
                if field != "values":
                    raise AssertionError(field)
                return {"0": ("MOTION",), "1": ("SOURCE",)}[item_id]

        tree = Tree()

        values = ui_review.tree_selected_values_or_first(tree)

        self.assertEqual(values, ("MOTION",))
        self.assertEqual(tree.selected, ["0"])

    def test_tree_selected_index_or_first_uses_first_row_when_nothing_selected(self):
        class Tree:
            def __init__(self):
                self.selected = []
            def selection(self):
                return tuple(self.selected)
            def get_children(self):
                return ("0", "1")
            def selection_set(self, item_id):
                self.selected = [item_id]

        tree = Tree()

        idx = ui_review.tree_selected_index_or_first(tree)

        self.assertEqual(idx, 0)
        self.assertEqual(tree.selected, ["0"])

    def test_flush_pending_bulk_sheet_edit_calls_sheet_hook(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append("flush")),
        )

        ui_review.flush_pending_bulk_sheet_edit(fake_app)

        self.assertEqual(events, ["flush"])

    def test_apply_review_filter_honors_vendor_performance_attention_and_release_bucket(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Item A",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "performance_profile": "steady",
                    "reorder_attention_signal": "review_missed_reorder",
                    "recency_review_bucket": "stale_or_likely_dead",
                    "release_decision": "export_next_business_day_for_free_day",
                },
                {
                    "vendor": "SOURCE",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Item B",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "performance_profile": "steady",
                    "reorder_attention_signal": "normal",
                    "recency_review_bucket": "missing_data_uncertain",
                    "release_decision": "hold_for_threshold",
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "MOTION"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "Steady"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "Missed Reorder"),
            var_review_recency_filter=SimpleNamespace(get=lambda: "Stale / Likely Dead"),
            var_review_suggestion_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_release_filter=SimpleNamespace(get=lambda: "Planned Today"),
            var_review_focus_filter=SimpleNamespace(get=lambda: "Exceptions Only"),
        )

        ui_review.apply_review_filter(fake_app)

        self.assertEqual(events[0], ("flush",))
        self.assertEqual(events[1], ("delete", "old"))
        self.assertEqual(events[2][0], "insert")
        self.assertEqual(events[2][1], "0")
        self.assertEqual(events[2][2][2], "A")
        self.assertEqual(len(events), 3)

    def test_populate_review_tab_flushes_pending_bulk_sheet_edit(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        class Var:
            def __init__(self):
                self.value = None
            def set(self, value):
                self.value = value
                events.append(("set", value))
            def get(self):
                return self.value

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Item A",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                },
            ],
            combo_vendor_filter={},
            var_vendor_filter=Var(),
            var_review_performance_filter=Var(),
            var_review_attention_filter=Var(),
            var_review_recency_filter=Var(),
            var_review_suggestion_filter=Var(),
            var_review_release_filter=Var(),
            var_review_focus_filter=Var(),
            _get_review_export_focus=lambda: "all_items",
            lbl_review_summary=SimpleNamespace(config=lambda **kwargs: events.append(("summary", kwargs.get("text", "")))),
        )

        ui_review.populate_review_tab(fake_app)

        self.assertEqual(events[0], ("flush",))
        self.assertEqual(events[1], ("delete", "old"))
        self.assertTrue(any(event[0] == "insert" for event in events))

    def test_update_review_summary_includes_immediate_planned_and_held_counts(self):
        captured = {}
        fake_app = SimpleNamespace(
            assigned_items=[
                {"vendor": "MOTION", "release_decision": "release_now", "recency_review_bucket": "critical_min_rule_protected"},
                {
                    "vendor": "MOTION",
                    "release_decision": "export_next_business_day_for_free_day",
                    "recency_review_bucket": "new_or_sparse",
                    "receipt_vendor_ambiguous": True,
                    "reorder_attention_signal": "review_lumpy_demand",
                    "detailed_suggestion_compare": "detailed_only",
                },
                {
                    "vendor": "MOTION",
                    "release_decision": "hold_for_threshold",
                    "recency_review_bucket": "receipt_heavy_unverified",
                    "reorder_attention_signal": "review_receipt_heavy",
                    "status": "review",
                },
                {"vendor": "SOURCE", "release_decision": ""},
            ],
            lbl_review_summary=SimpleNamespace(config=lambda **kwargs: captured.update(kwargs)),
        )

        ui_review.update_review_summary(fake_app)

        text = captured["text"]
        self.assertIn("Exportable now: 3", text)
        self.assertIn("Immediate: 2", text)
        self.assertIn("Exceptions: 2", text)
        self.assertIn("Planned today: 1", text)
        self.assertIn("Held by shipping policy: 1", text)
        self.assertIn("Critical held: 1", text)
        self.assertIn("Receipt vendor ambiguity: 1", text)
        self.assertIn("Lumpy demand: 1", text)
        self.assertIn("Receipt-heavy vs sales: 1", text)
        self.assertIn("Suggestion gaps: 1 (1 detailed only)", text)
        self.assertIn("Low-confidence recency: 3", text)
        self.assertIn("1 new / sparse", text)
        self.assertIn("1 receipt-heavy / sales-unverified", text)
        self.assertIn("1 critical / explicit min rule", text)

    def test_update_review_summary_includes_receipt_pack_mismatch_count(self):
        captured = {}
        fake_app = SimpleNamespace(
            assigned_items=[
                {"vendor": "MOTION", "release_decision": "release_now", "receipt_pack_mismatch": True},
                {"vendor": "SOURCE", "release_decision": "release_now"},
            ],
            lbl_review_summary=SimpleNamespace(config=lambda **kwargs: captured.update(kwargs)),
        )

        ui_review.update_review_summary(fake_app)

        self.assertIn("Receipt pack mismatch: 1", captured["text"])

    def test_is_review_exception_detects_review_relevant_items(self):
        self.assertTrue(ui_review.is_review_exception({"release_decision": "hold_for_threshold"}))
        self.assertTrue(ui_review.is_review_exception({"status": "warning"}))
        self.assertTrue(ui_review.is_review_exception({"review_required": True}))
        self.assertTrue(ui_review.is_review_exception({"recency_confidence": "low"}))
        self.assertTrue(ui_review.is_review_exception({"vendor_value_coverage": "partial"}))
        self.assertTrue(ui_review.is_review_exception({"reorder_attention_signal": "review_lumpy_demand"}))
        self.assertTrue(ui_review.is_review_exception({"reorder_attention_signal": "review_receipt_heavy"}))
        self.assertTrue(ui_review.is_review_exception({"receipt_pack_mismatch": True}))
        self.assertTrue(ui_review.is_review_exception({"receipt_vendor_ambiguous": True}))
        self.assertTrue(ui_review.is_review_exception({"detailed_suggestion_compare": "detailed_only"}))
        self.assertFalse(ui_review.is_review_exception({"release_decision": "release_now", "status": "ok"}))

    def test_apply_review_filter_can_isolate_detailed_suggestion_gap_type(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Detailed only",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                    "detailed_suggestion_compare": "detailed_only",
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Detailed higher",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                    "detailed_suggestion_compare": "detailed_higher",
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_recency_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_suggestion_filter=SimpleNamespace(get=lambda: "Detailed Higher"),
            var_review_release_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_focus_filter=SimpleNamespace(get=lambda: "All Items"),
        )

        ui_review.apply_review_filter(fake_app)

        inserts = [event for event in events if event[0] == "insert"]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][2][2], "B")

    def test_apply_review_filter_can_isolate_receipt_heavy_attention(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Receipt heavy",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                    "reorder_attention_signal": "review_receipt_heavy",
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Lumpy",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                    "reorder_attention_signal": "review_lumpy_demand",
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "Receipt Heavy"),
            var_review_recency_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_suggestion_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_release_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_focus_filter=SimpleNamespace(get=lambda: "All Items"),
        )

        ui_review.apply_review_filter(fake_app)

        inserts = [event for event in events if event[0] == "insert"]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][2][2], "A")

    def test_apply_review_filter_can_isolate_receipt_pack_mismatch_attention(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Mismatch",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                    "receipt_pack_mismatch": True,
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Normal",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "Pack Mismatch"),
            var_review_recency_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_suggestion_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_release_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_focus_filter=SimpleNamespace(get=lambda: "All Items"),
        )

        ui_review.apply_review_filter(fake_app)

        inserts = [event for event in events if event[0] == "insert"]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][2][2], "A")

    def test_is_critical_shipping_hold_detects_review_sensitive_held_items(self):
        self.assertTrue(ui_review.is_critical_shipping_hold({"release_decision": "hold_for_threshold", "status": "review"}))
        self.assertTrue(ui_review.is_critical_shipping_hold({"release_decision": "hold_for_free_day", "review_required": True}))
        self.assertTrue(ui_review.is_critical_shipping_hold({"release_decision": "hold_for_threshold", "reorder_attention_signal": "review_missed_reorder"}))
        self.assertFalse(ui_review.is_critical_shipping_hold({"release_decision": "hold_for_threshold", "status": "ok"}))

    def test_apply_review_filter_can_hide_non_exception_items(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Routine",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Held",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "hold_for_threshold",
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_recency_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_suggestion_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_release_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_focus_filter=SimpleNamespace(get=lambda: "Exceptions Only"),
        )

        ui_review.apply_review_filter(fake_app)

        inserts = [event for event in events if event[0] == "insert"]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][2][2], "B")

    def test_apply_review_filter_treats_receipt_vendor_ambiguity_as_exception(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Routine",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Mixed receipt vendor",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "release_now",
                    "receipt_vendor_ambiguous": True,
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_recency_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_release_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_focus_filter=SimpleNamespace(get=lambda: "Exceptions Only"),
        )

        ui_review.apply_review_filter(fake_app)

        inserts = [event for event in events if event[0] == "insert"]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][2][2], "B")

    def test_release_filter_bucket_maps_planned_and_held_states(self):
        self.assertEqual(
            ui_review.release_filter_bucket({"release_decision": "export_next_business_day_for_free_day"}),
            "Planned Today",
        )
        self.assertEqual(
            ui_review.release_filter_bucket({"release_decision": "hold_for_free_day"}),
            "Held",
        )
        self.assertEqual(
            ui_review.release_filter_bucket({"release_decision": "release_now"}),
            "Release Now",
        )

    def test_apply_review_filter_can_isolate_critical_held_items(self):
        events = []

        class Tree:
            def get_children(self):
                return ("old",)
            def delete(self, item_id):
                events.append(("delete", item_id))
            def insert(self, parent, where, iid, values):
                events.append(("insert", iid, values))

        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=Tree(),
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Routine held",
                    "order_qty": 1,
                    "status": "ok",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "hold_for_threshold",
                },
                {
                    "vendor": "MOTION",
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Critical held",
                    "order_qty": 1,
                    "status": "review",
                    "why": "",
                    "pack_size": 6,
                    "release_decision": "hold_for_free_day",
                },
            ],
            var_vendor_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_recency_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_suggestion_filter=SimpleNamespace(get=lambda: "ALL"),
            var_review_release_filter=SimpleNamespace(get=lambda: "Critical Held"),
            var_review_focus_filter=SimpleNamespace(get=lambda: "All Items"),
        )

        ui_review.apply_review_filter(fake_app)

        inserts = [event for event in events if event[0] == "insert"]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][2][2], "B")

    def test_recency_filter_label_maps_known_review_buckets(self):
        self.assertEqual(
            ui_review.recency_filter_label({"recency_review_bucket": "missing_data_uncertain"}),
            "Missing-Data / Uncertain",
        )
        self.assertEqual(
            ui_review.recency_filter_label({"recency_review_bucket": "critical_min_rule_protected"}),
            "Critical / Explicit Min Rule",
        )
        self.assertEqual(
            ui_review.recency_filter_label({"recency_review_bucket": "recent_local_po_protected"}),
            "Recent Local PO-Protected",
        )
        self.assertEqual(ui_review.recency_filter_label({}), "None")

    def test_build_vendor_release_plan_rows_returns_vendor_aggregate_rows(self):
        fake_app = SimpleNamespace(
            assigned_items=[
                {
                    "vendor": "MOTION",
                    "final_qty": 2,
                    "estimated_order_value": 20.0,
                    "release_decision": "release_now",
                    "vendor_order_value_total": 45.0,
                    "vendor_threshold_shortfall": 55.0,
                    "vendor_threshold_progress_pct": 45.0,
                    "vendor_value_coverage": "partial",
                    "next_free_ship_date": "2026-03-13",
                    "planned_export_date": "2026-03-12",
                    "shipping_policy": "hybrid_free_day_threshold",
                    "release_timing_mode": "same_day_release",
                    "release_plan_label": "Release Now",
                },
                {
                    "vendor": "MOTION",
                    "final_qty": 1,
                    "estimated_order_value": 15.0,
                    "release_decision": "export_next_business_day_for_free_day",
                    "vendor_order_value_total": 45.0,
                    "vendor_threshold_shortfall": 55.0,
                    "vendor_threshold_progress_pct": 45.0,
                    "vendor_value_coverage": "partial",
                    "next_free_ship_date": "2026-03-13",
                    "planned_export_date": "2026-03-12",
                    "shipping_policy": "hybrid_free_day_threshold",
                    "release_timing_mode": "release_one_business_day_before_ship_day",
                    "release_plan_label": "Release On Order-Ahead Date",
                },
            ],
        )

        rows = ui_review.build_vendor_release_plan_rows(fake_app)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vendor"], "MOTION")
        self.assertEqual(rows[0]["release_now_count"], 1)
        self.assertEqual(rows[0]["planned_today_count"], 1)
        self.assertEqual(rows[0]["release_timing_mode"], "same_day_release")
        self.assertEqual(rows[0]["release_plan_label"], "Release Now")
        self.assertEqual(rows[0]["recommended_action"], "Export All Due")

    def test_compact_review_bucket_distinguishes_ready_planned_and_blocked(self):
        self.assertEqual(
            ui_review.compact_review_bucket({"release_now_count": 1, "planned_today_count": 0, "held_count": 0}),
            "Ready Now",
        )
        self.assertEqual(
            ui_review.compact_review_bucket({"release_now_count": 0, "planned_today_count": 1, "held_count": 0}),
            "Planned Today",
        )
        self.assertEqual(
            ui_review.compact_review_bucket({"release_now_count": 0, "planned_today_count": 0, "held_count": 1}),
            "Blocked",
        )
        self.assertEqual(
            ui_review.compact_review_bucket({"release_now_count": 0, "planned_today_count": 0, "held_count": 1, "critical_held_count": 1}),
            "Blocked",
        )

    def test_compact_review_reason_explains_vendor_state(self):
        self.assertIn(
            "short 55.00",
            ui_review.compact_review_reason({
                "release_now_count": 0,
                "planned_today_count": 0,
                "held_count": 2,
                "critical_held_count": 0,
                "release_plan_status": "hold_accumulating_to_threshold",
                "vendor_threshold_shortfall": 55.0,
            }),
        )
        self.assertIn(
            "planned export date 2026-03-12",
            ui_review.compact_review_reason({
                "release_now_count": 0,
                "planned_today_count": 0,
                "held_count": 1,
                "critical_held_count": 0,
                "planned_export_date": "2026-03-12",
            }),
        )
        self.assertIn(
            "ready now",
            ui_review.compact_review_reason({
                "release_now_count": 1,
                "planned_today_count": 0,
                "held_count": 0,
                "critical_held_count": 0,
            }).lower(),
        )

    def test_build_compact_review_rows_sorts_ready_planned_then_blocked(self):
        fake_app = SimpleNamespace(
            assigned_items=[
                {
                    "vendor": "BLOCKED",
                    "final_qty": 1,
                    "estimated_order_value": 10.0,
                    "release_decision": "hold_for_threshold",
                    "vendor_order_value_total": 10.0,
                    "vendor_threshold_shortfall": 90.0,
                    "vendor_threshold_progress_pct": 10.0,
                    "vendor_value_coverage": "complete",
                    "release_plan_status": "hold_accumulating_to_threshold",
                    "shipping_policy": "hold_for_threshold",
                },
                {
                    "vendor": "PLANNED",
                    "final_qty": 1,
                    "estimated_order_value": 10.0,
                    "release_decision": "export_next_business_day_for_free_day",
                    "vendor_order_value_total": 10.0,
                    "vendor_threshold_shortfall": 0.0,
                    "vendor_threshold_progress_pct": 100.0,
                    "vendor_value_coverage": "complete",
                    "planned_export_date": "2026-03-12",
                    "shipping_policy": "hold_for_free_day",
                },
                {
                    "vendor": "READY",
                    "final_qty": 1,
                    "estimated_order_value": 10.0,
                    "release_decision": "release_now",
                    "vendor_order_value_total": 10.0,
                    "vendor_threshold_shortfall": 0.0,
                    "vendor_threshold_progress_pct": 100.0,
                    "vendor_value_coverage": "complete",
                    "shipping_policy": "release_immediately",
                },
            ],
        )

        rows = ui_review.build_compact_review_rows(fake_app)

        self.assertEqual([row["vendor"] for row in rows], ["READY", "PLANNED", "BLOCKED"])
        self.assertEqual([row["compact_bucket"] for row in rows], ["Ready Now", "Planned Today", "Blocked"])

    def test_apply_release_plan_view_sets_review_filters_and_selects_review_tab(self):
        events = []

        class Var:
            def __init__(self):
                self.value = None
            def set(self, value):
                self.value = value
                events.append(("set", value))

        fake_app = SimpleNamespace(
            var_vendor_filter=Var(),
            var_review_performance_filter=Var(),
            var_review_attention_filter=Var(),
            var_review_recency_filter=Var(),
            var_review_release_filter=Var(),
            var_review_focus_filter=Var(),
            _apply_review_filter=lambda: events.append(("apply", None)),
            notebook=SimpleNamespace(select=lambda idx: events.append(("select", idx))),
        )

        ui_review.apply_release_plan_view(fake_app, "MOTION", focus="Exceptions Only", release="Held")

        self.assertEqual(fake_app.var_vendor_filter.value, "MOTION")
        self.assertEqual(fake_app.var_review_release_filter.value, "Held")
        self.assertEqual(fake_app.var_review_focus_filter.value, "Exceptions Only")
        self.assertEqual(fake_app.var_review_recency_filter.value, "ALL")
        self.assertIn(("apply", None), events)
        self.assertIn(("select", 5), events)

    def test_export_release_plan_scope_exports_only_selected_vendor_bucket(self):
        captured = {}
        fake_app = SimpleNamespace(
            assigned_items=[
                {"vendor": "MOTION", "item_code": "A", "release_decision": "release_now"},
                {"vendor": "MOTION", "item_code": "B", "release_decision": "export_next_business_day_for_free_day"},
                {"vendor": "SOURCE", "item_code": "C", "release_decision": "release_now"},
            ],
            _export_vendor_po=object(),
            _data_path=lambda key: f"/tmp/{key}",
        )

        with patch("ui_review.export_flow.do_export", side_effect=lambda *args, **kwargs: captured.update({"args": args, "kwargs": kwargs})):
            ui_review.export_release_plan_scope(fake_app, "MOTION", release="Release Now")

        scoped_items = captured["kwargs"]["assigned_items"]
        self.assertEqual([item["item_code"] for item in scoped_items], ["A"])
        self.assertEqual(captured["kwargs"]["export_scope_label"], "MOTION release now items")
        self.assertEqual(captured["kwargs"]["selection_mode"], "all_exportable")

    def test_export_review_scope_can_export_planned_items_only(self):
        captured = {}
        fake_app = SimpleNamespace(
            assigned_items=[
                {"vendor": "MOTION", "item_code": "A", "release_decision": "release_now"},
                {"vendor": "MOTION", "item_code": "B", "release_decision": "export_next_business_day_for_free_day"},
                {"vendor": "SOURCE", "item_code": "C", "release_decision": "hold_for_threshold"},
            ],
            _export_vendor_po=object(),
            _data_path=lambda key: f"/tmp/{key}",
        )

        with patch("ui_review.export_flow.do_export", side_effect=lambda *args, **kwargs: captured.update({"args": args, "kwargs": kwargs})):
            ui_review.export_review_scope(fake_app, "planned_only")

        scoped_items = captured["kwargs"]["assigned_items"]
        self.assertEqual([item["item_code"] for item in scoped_items], ["B"])
        self.assertEqual(captured["kwargs"]["export_scope_label"], "planned today items")
        self.assertEqual(captured["kwargs"]["selection_mode"], "all_exportable")

    def test_export_review_scope_reports_when_no_matching_items_exist(self):
        fake_app = SimpleNamespace(
            assigned_items=[
                {"vendor": "MOTION", "item_code": "A", "release_decision": "hold_for_threshold"},
            ],
            _export_vendor_po=object(),
            _data_path=lambda key: f"/tmp/{key}",
        )

        with patch("ui_review.messagebox.showinfo") as mocked_info, \
             patch("ui_review.export_flow.do_export") as mocked_export:
            ui_review.export_review_scope(fake_app, "planned_only")

        mocked_export.assert_not_called()
        mocked_info.assert_called_once()
        self.assertIn("No planned today items", mocked_info.call_args.args[1])

    def test_sort_tree_flushes_pending_bulk_sheet_edit(self):
        events = []

        class Tree:
            def __init__(self):
                self.moves = []
            def get_children(self, _parent=""):
                return ("1", "0")
            def set(self, item_id, col):
                return {"1": {"order_qty": "10"}, "0": {"order_qty": "2"}}[item_id][col]
            def move(self, item_id, parent, index):
                self.moves.append((item_id, parent, index))

        tree = Tree()
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append(("flush",))),
            tree=tree,
        )

        ui_review.sort_tree(fake_app, "order_qty")

        self.assertEqual(events, [("flush",)])
        self.assertEqual(tree.moves, [("0", "", 0), ("1", "", 1)])


if __name__ == "__main__":
    unittest.main()
