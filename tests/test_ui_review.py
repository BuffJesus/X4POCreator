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
                {"vendor": "MOTION", "release_decision": "release_now", "recency_review_bucket": "critical_rule_protected"},
                {"vendor": "MOTION", "release_decision": "export_next_business_day_for_free_day", "recency_review_bucket": "new_or_sparse"},
                {"vendor": "MOTION", "release_decision": "hold_for_threshold", "recency_review_bucket": "stale_or_likely_dead"},
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
        self.assertIn("Low-confidence recency: 3", text)
        self.assertIn("1 stale / likely dead", text)
        self.assertIn("1 new / sparse", text)
        self.assertIn("1 critical / rule-protected", text)

    def test_is_review_exception_detects_review_relevant_items(self):
        self.assertTrue(ui_review.is_review_exception({"release_decision": "hold_for_threshold"}))
        self.assertTrue(ui_review.is_review_exception({"status": "warning"}))
        self.assertTrue(ui_review.is_review_exception({"review_required": True}))
        self.assertTrue(ui_review.is_review_exception({"recency_confidence": "low"}))
        self.assertTrue(ui_review.is_review_exception({"vendor_value_coverage": "partial"}))
        self.assertFalse(ui_review.is_review_exception({"release_decision": "release_now", "status": "ok"}))

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

    def test_recency_filter_label_maps_known_review_buckets(self):
        self.assertEqual(
            ui_review.recency_filter_label({"recency_review_bucket": "missing_data_uncertain"}),
            "Missing-Data / Uncertain",
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
                },
            ],
        )

        rows = ui_review.build_vendor_release_plan_rows(fake_app)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vendor"], "MOTION")
        self.assertEqual(rows[0]["release_now_count"], 1)
        self.assertEqual(rows[0]["planned_today_count"], 1)

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
