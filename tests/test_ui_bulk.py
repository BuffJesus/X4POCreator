import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk


class UIBulkTests(unittest.TestCase):
    def test_resolve_bulk_row_id_uses_cached_index_for_stable_row_id(self):
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AER-", "item_code": "B"}
        row_id_b = ui_bulk.bulk_row_id(item_b)
        fake_app = SimpleNamespace(
            filtered_items=[item_a, item_b],
        )

        first = ui_bulk.resolve_bulk_row_id(fake_app, row_id_b)
        second = ui_bulk.resolve_bulk_row_id(fake_app, row_id_b)

        self.assertEqual(first, (1, item_b))
        self.assertEqual(second, (1, item_b))
        self.assertEqual(fake_app._bulk_row_index_cache["by_key"][("AER-", "B")], (1, item_b))

    def test_invalidate_bulk_row_index_rebuilds_resolved_positions_after_sort(self):
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AER-", "item_code": "B"}
        row_id_a = ui_bulk.bulk_row_id(item_a)
        fake_app = SimpleNamespace(
            filtered_items=[item_b, item_a],
        )

        self.assertEqual(ui_bulk.resolve_bulk_row_id(fake_app, row_id_a), (1, item_a))
        fake_app.filtered_items.sort(key=lambda item: item["item_code"])
        ui_bulk.invalidate_bulk_row_index(fake_app)

        self.assertEqual(ui_bulk.resolve_bulk_row_id(fake_app, row_id_a), (0, item_a))

    def test_find_filtered_item_uses_cached_row_index(self):
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AMS-", "item_code": "B"}
        fake_app = SimpleNamespace(filtered_items=[item_a, item_b])

        first = ui_bulk.find_filtered_item(fake_app, ("AMS-", "B"))
        second = ui_bulk.find_filtered_item(fake_app, ("AMS-", "B"))

        self.assertIs(first, item_b)
        self.assertIs(second, item_b)
        self.assertEqual(fake_app._bulk_row_index_cache["by_key"][("AMS-", "B")], (1, item_b))

    def test_sync_bulk_cache_state_invalidates_index_and_prunes_render_cache(self):
        keep_item = {"line_code": "AER-", "item_code": "KEEP"}
        drop_item = {"line_code": "AER-", "item_code": "DROP"}
        fake_app = SimpleNamespace(
            filtered_items=[keep_item],
            _bulk_row_index_generation=0,
            _bulk_row_index_cache={"generation": 0, "by_row_id": {}, "by_key": {}},
            _bulk_row_render_cache={
                ui_bulk.bulk_row_id(keep_item): (("sig",), ("row",)),
                ui_bulk.bulk_row_id(drop_item): (("sig",), ("row",)),
            },
        )

        removed = ui_bulk.sync_bulk_cache_state(fake_app, filtered_items_changed=True)

        self.assertEqual(removed, 1)
        self.assertIsNone(fake_app._bulk_row_index_cache)
        self.assertEqual(fake_app._bulk_row_index_generation, 1)
        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [ui_bulk.bulk_row_id(keep_item)])

    def test_update_bulk_summary_uses_cached_counts_when_available(self):
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        fake_app = SimpleNamespace(
            filtered_items=[{"vendor": ""}, {"vendor": "MOTION"}],
            _bulk_summary_counts={"total": 2, "assigned": 1, "review": 0, "warning": 1},
            lbl_bulk_summary=label,
        )

        ui_bulk.update_bulk_summary(fake_app)

        self.assertIn("2 total", label.text)
        self.assertIn("1 assigned", label.text)
        self.assertIn("1 warning", label.text)

    def test_adjust_bulk_summary_for_item_change_updates_cached_counts(self):
        fake_app = SimpleNamespace(
            filtered_items=[{"vendor": "OLD", "status": "review"}],
            _bulk_summary_counts={"total": 1, "assigned": 1, "review": 1, "warning": 0},
        )

        result = ui_bulk.adjust_bulk_summary_for_item_change(
            fake_app,
            {"vendor": "OLD", "status": "review"},
            {"vendor": "", "status": "warning"},
        )

        self.assertTrue(result)
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 1, "assigned": 0, "review": 0, "warning": 1})

    def test_flush_pending_bulk_sheet_edit_calls_sheet_hook(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append("flush")),
        )

        ui_bulk.flush_pending_bulk_sheet_edit(fake_app)

        self.assertEqual(events, ["flush"])

    def test_refresh_bulk_view_after_edit_refreshes_rows_when_unfiltered_unsorted(self):
        events = []
        item_a = {"line_code": "AER-", "item_code": "GH781-4", "vendor": "MOTION", "description": ""}
        item_b = {"line_code": "AER-", "item_code": "GH781-5", "vendor": "", "description": ""}
        row_id_a = ui_bulk.bulk_row_id(item_a)
        row_id_b = ui_bulk.bulk_row_id(item_b)
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda row_id, values: events.append((row_id, values)),
                row_lookup={row_id_a: 0, row_id_b: 1},
            ),
            filtered_items=[item_a, item_b],
            _bulk_row_values=lambda item: (item["item_code"], item.get("vendor", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id_a, row_id_b), changed_cols=("vendor",))

        self.assertTrue(result)
        self.assertEqual(events, [(row_id_a, ("GH781-4", "MOTION")), (row_id_b, ("GH781-5", ""))])

    def test_refresh_bulk_view_after_edit_falls_back_to_filter_when_changed_column_affects_active_filter(self):
        events = []
        row_id = ui_bulk.bulk_row_id({"line_code": "AER-", "item_code": "GH781-4"})
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(refresh_row=lambda row_id, values: events.append((row_id, values)), row_lookup={row_id: 0}),
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4", "description": ""}],
            _bulk_row_values=lambda item: (item["item_code"],),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "Assigned"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("vendor",))

        self.assertFalse(result)
        self.assertEqual(events, ["filter"])

    def test_refresh_bulk_view_after_edit_keeps_assigned_filter_incremental_when_row_stays_visible(self):
        events = []
        item = {"line_code": "AER-", "item_code": "GH781-4", "vendor": "SOURCE", "description": ""}
        row_id = ui_bulk.bulk_row_id(item)
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda current_row_id, values: events.append((current_row_id, values)),
                row_lookup={row_id: 0},
            ),
            filtered_items=[item],
            _bulk_row_values=lambda current_item: (current_item["item_code"], current_item.get("vendor", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "Assigned"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("vendor",))

        self.assertTrue(result)
        self.assertEqual(events, [(row_id, ("GH781-4", "SOURCE"))])

    def test_refresh_bulk_view_after_edit_skips_rebuild_when_filtered_out_row_stays_out(self):
        events = []
        item = {"line_code": "AER-", "item_code": "GH781-4", "vendor": "", "description": ""}
        row_id = ui_bulk.bulk_row_id(item)
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda current_row_id, values: events.append((current_row_id, values)),
                row_lookup={},
            ),
            filtered_items=[item],
            _bulk_row_values=lambda current_item: (current_item["item_code"], current_item.get("vendor", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "Assigned"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("vendor",))

        self.assertTrue(result)
        self.assertEqual(events, [])

    def test_refresh_bulk_view_after_edit_keeps_filtered_refresh_incremental_when_column_cannot_affect_filter(self):
        events = []
        row_id = ui_bulk.bulk_row_id({"line_code": "AER-", "item_code": "GH781-4"})
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda row_id, values: events.append((row_id, values)),
                row_lookup={row_id: 0},
            ),
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4", "pack_size": 6, "description": ""}],
            _bulk_row_values=lambda item: (item["item_code"], item.get("pack_size", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "AER-"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("pack_size",))

        self.assertTrue(result)
        self.assertEqual(events, [(row_id, ("GH781-4", 6))])

    def test_refresh_bulk_view_after_edit_rebuilds_attention_filter_when_row_leaves_visible_set(self):
        events = []
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "",
            "qoh": 0,
            "reorder_attention_signal": "normal",
        }
        row_id = ui_bulk.bulk_row_id(item)
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda current_row_id, values: events.append((current_row_id, values)),
                row_lookup={row_id: 0},
            ),
            filtered_items=[item],
            _bulk_row_values=lambda current_item: (current_item["item_code"], current_item.get("reorder_attention_signal", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "Missed Reorder"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("qoh",))

        self.assertFalse(result)
        self.assertEqual(events, ["filter"])

    def test_refresh_bulk_view_after_edit_keeps_sorted_refresh_incremental_when_column_cannot_affect_sort(self):
        events = []
        row_id = ui_bulk.bulk_row_id({"line_code": "AER-", "item_code": "GH781-4"})
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda row_id, values: events.append((row_id, values)),
                row_lookup={row_id: 0},
            ),
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4", "pack_size": 6, "description": ""}],
            _bulk_row_values=lambda item: (item["item_code"], item.get("pack_size", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col="item_code",
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("pack_size",))

        self.assertTrue(result)
        self.assertEqual(events, [(row_id, ("GH781-4", 6))])

    def test_refresh_bulk_view_after_edit_rebuilds_sorted_view_when_column_can_affect_sort(self):
        events = []
        row_id = ui_bulk.bulk_row_id({"line_code": "AER-", "item_code": "GH781-4"})
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda row_id, values: events.append((row_id, values)),
                row_lookup={row_id: 0},
            ),
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4", "pack_size": 6, "description": ""}],
            _bulk_row_values=lambda item: (item["item_code"], item.get("pack_size", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col="vendor",
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("vendor",))

        self.assertFalse(result)
        self.assertEqual(events, ["filter"])

    def test_can_incremental_refresh_requires_new_signal_filters_to_be_all(self):
        fake_app = SimpleNamespace(
            bulk_sheet=object(),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "Steady"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        self.assertFalse(ui_bulk.can_incremental_refresh(fake_app))

    def test_apply_bulk_filter_honors_performance_health_and_attention_filters(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        fake_app = SimpleNamespace(
            filtered_items=[
                {
                    "line_code": "AER-",
                    "item_code": "A",
                    "description": "Item A",
                    "vendor": "MOTION",
                    "qty_sold": 1,
                    "qty_suspended": 0,
                    "status": "ok",
                    "performance_profile": "steady",
                    "sales_health_signal": "dormant",
                    "reorder_attention_signal": "review_missed_reorder",
                },
                {
                    "line_code": "AER-",
                    "item_code": "B",
                    "description": "Item B",
                    "vendor": "MOTION",
                    "qty_sold": 1,
                    "qty_suspended": 0,
                    "status": "ok",
                    "performance_profile": "steady",
                    "sales_health_signal": "active",
                    "reorder_attention_signal": "normal",
                },
            ],
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "Steady"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "Dormant"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "Missed Reorder"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            bulk_tree_columns=(),
            bulk_tree_labels={},
            lbl_bulk_summary=label,
        )

        ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[0], ("flush",))
        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(fake_app.filtered_items[0])])
        self.assertEqual(captured[1][0][0][2], "A")
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 2, "assigned": 2, "review": 0, "warning": 0})

    def test_apply_bulk_filter_reuses_cached_summary_counts(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        fake_app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "MOTION", "qty_sold": 1, "qty_suspended": 0, "status": "ok"},
                {"line_code": "AER-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "warning"},
            ],
            _bulk_summary_counts={"total": 2, "assigned": 1, "review": 0, "warning": 1},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "Assigned"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            bulk_tree_columns=(),
            bulk_tree_labels={},
            lbl_bulk_summary=label,
        )

        ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(fake_app._bulk_summary_counts, {"total": 2, "assigned": 1, "review": 0, "warning": 1})
        self.assertIn("1 assigned", label.text)
        self.assertEqual(len(captured[1][1]), 1)

    def test_refresh_bulk_view_after_edit_resolves_stable_row_id_after_item_reordering(self):
        events = []
        original = {"line_code": "AER-", "item_code": "GH781-4", "vendor": "MOTION", "description": ""}
        other = {"line_code": "AER-", "item_code": "GH781-5", "vendor": "", "description": ""}
        row_id = ui_bulk.bulk_row_id(original)
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                refresh_row=lambda current_row_id, values: events.append((current_row_id, values)),
                row_lookup={row_id: 0},
            ),
            filtered_items=[other, original],
            _bulk_row_values=lambda item: (item["item_code"], item.get("vendor", "")),
            _apply_bulk_filter=lambda: events.append("filter"),
            _bulk_sort_col=None,
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
        )

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, (row_id,), changed_cols=("vendor",))

        self.assertTrue(result)
        self.assertEqual(events, [(row_id, ("GH781-4", "MOTION"))])

    def test_sort_bulk_tree_flushes_pending_edit_before_sorting(self):
        events = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: events.append("flush"),
                set_rows=lambda rows, row_ids: events.append(("rows", row_ids)),
            ),
            filtered_items=[
                {"line_code": "AER-", "item_code": "B", "description": "", "vendor": "", "qty_sold": 0, "qty_suspended": 0},
                {"line_code": "AER-", "item_code": "A", "description": "", "vendor": "", "qty_sold": 0, "qty_suspended": 0},
            ],
            bulk_tree_columns=(
                "vendor", "line_code", "item_code", "description", "source",
                "status", "raw_need", "suggested_qty", "final_qty", "buy_rule",
                "qoh", "cur_min", "cur_max", "sug_min", "sug_max",
                "pack_size", "supplier", "why",
            ),
            _bulk_sort_col=None,
            _bulk_sort_reverse=False,
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            lbl_bulk_summary=label,
        )

        ui_bulk.sort_bulk_tree(fake_app, "item_code")

        self.assertEqual(events[0], "flush")
        self.assertEqual([item["item_code"] for item in fake_app.filtered_items], ["A", "B"])

    def test_sort_bulk_tree_by_item_code_does_not_call_suggest_min_max(self):
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        fake_app = SimpleNamespace(
            bulk_sheet=None,
            filtered_items=[
                {"line_code": "AER-", "item_code": "B", "description": "", "vendor": "", "qty_sold": 0, "qty_suspended": 0},
                {"line_code": "AER-", "item_code": "A", "description": "", "vendor": "", "qty_sold": 0, "qty_suspended": 0},
            ],
            bulk_tree_columns=(
                "vendor", "line_code", "item_code", "description", "source",
                "status", "raw_need", "suggested_qty", "final_qty", "buy_rule",
                "qoh", "cur_min", "cur_max", "sug_min", "sug_max",
                "pack_size", "supplier", "why",
            ),
            _bulk_sort_col=None,
            _bulk_sort_reverse=False,
            _suggest_min_max=lambda key: (_ for _ in ()).throw(AssertionError("unexpected suggest_min_max call")),
            inventory_lookup={},
            order_rules={},
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            lbl_bulk_summary=label,
        )

        ui_bulk.sort_bulk_tree(fake_app, "item_code")

        self.assertEqual([item["item_code"] for item in fake_app.filtered_items], ["A", "B"])

    def test_apply_bulk_filter_without_sheet_does_not_render_rows(self):
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        fake_app = SimpleNamespace(
            bulk_sheet=None,
            filtered_items=[
                {"line_code": "AER-", "item_code": "A", "description": "", "vendor": "", "qty_sold": 0, "qty_suspended": 0, "status": "ok"},
            ],
            _bulk_summary_counts={"total": 1, "assigned": 0, "review": 0, "warning": 0},
            _suggest_min_max=lambda key: (_ for _ in ()).throw(AssertionError("unexpected suggest_min_max call")),
            inventory_lookup={},
            order_rules={},
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            lbl_bulk_summary=label,
        )

        ui_bulk.apply_bulk_filter(fake_app)

        self.assertIn("1 total", label.text)

    def test_bulk_sort_value_calls_suggest_min_max_for_sug_min(self):
        calls = []
        fake_app = SimpleNamespace(
            inventory_lookup={},
            order_rules={},
            _suggest_min_max=lambda key: calls.append(key) or (3, 7),
        )
        item = {"line_code": "AER-", "item_code": "GH781-4"}

        value = ui_bulk.bulk_sort_value(fake_app, item, "sug_min")

        self.assertEqual(value, 3)
        self.assertEqual(calls, [("AER-", "GH781-4")])

    def test_cached_bulk_row_values_reuses_render_for_unchanged_item(self):
        calls = []
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 52}},
            order_rules={},
            var_reorder_cycle=SimpleNamespace(get=lambda: "Biweekly"),
            _suggest_min_max=lambda key: calls.append(key) or (2, 5),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "Bearing",
            "vendor": "MOTION",
            "qty_sold": 1,
            "qty_suspended": 0,
            "status": "ok",
            "raw_need": 2,
            "suggested_qty": 2,
            "final_qty": 2,
            "why": "",
        }

        first = ui_bulk.cached_bulk_row_values(fake_app, item)
        second = ui_bulk.cached_bulk_row_values(fake_app, item)

        self.assertEqual(first, second)
        self.assertEqual(calls, [("AER-", "GH781-4")])

    def test_cached_bulk_row_values_invalidates_when_cycle_changes(self):
        calls = []
        cycle_state = {"value": "Biweekly"}
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "GH781-4"): {"mo12_sales": 52}},
            order_rules={},
            var_reorder_cycle=SimpleNamespace(get=lambda: cycle_state["value"]),
            _suggest_min_max=lambda key: calls.append((key, cycle_state["value"])) or (2, 5),
        )
        item = {
            "line_code": "AER-",
            "item_code": "GH781-4",
            "description": "Bearing",
            "vendor": "MOTION",
            "qty_sold": 1,
            "qty_suspended": 0,
            "status": "ok",
            "raw_need": 2,
            "suggested_qty": 2,
            "final_qty": 2,
            "why": "",
        }

        ui_bulk.cached_bulk_row_values(fake_app, item)
        cycle_state["value"] = "Weekly"
        ui_bulk.cached_bulk_row_values(fake_app, item)

        self.assertEqual(
            calls,
            [(("AER-", "GH781-4"), "Biweekly"), (("AER-", "GH781-4"), "Weekly")],
        )

    def test_prune_bulk_row_render_cache_removes_entries_not_in_filtered_items(self):
        keep_item = {"line_code": "AER-", "item_code": "KEEP"}
        drop_item = {"line_code": "AER-", "item_code": "DROP"}
        fake_app = SimpleNamespace(
            filtered_items=[keep_item],
            _bulk_row_render_cache={
                ui_bulk.bulk_row_id(keep_item): (("sig",), ("row",)),
                ui_bulk.bulk_row_id(drop_item): (("sig",), ("row",)),
            },
        )

        removed = ui_bulk.prune_bulk_row_render_cache(fake_app)

        self.assertEqual(removed, 1)
        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [ui_bulk.bulk_row_id(keep_item)])

    def test_apply_bulk_filter_prunes_stale_render_cache_entries(self):
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        keep_item = {"line_code": "AER-", "item_code": "KEEP", "description": "", "vendor": "", "qty_sold": 0, "qty_suspended": 0, "status": "ok"}
        drop_item = {"line_code": "AER-", "item_code": "DROP"}
        fake_app = SimpleNamespace(
            bulk_sheet=None,
            filtered_items=[keep_item],
            _bulk_summary_counts={"total": 1, "assigned": 0, "review": 0, "warning": 0},
            _bulk_row_render_cache={
                ui_bulk.bulk_row_id(keep_item): (("sig",), ("row",)),
                ui_bulk.bulk_row_id(drop_item): (("sig",), ("row",)),
            },
            inventory_lookup={},
            order_rules={},
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            lbl_bulk_summary=label,
        )

        ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [ui_bulk.bulk_row_id(keep_item)])

    def test_bulk_row_values_use_zero_qty_for_missing_recency_manual_review_item(self):
        fake_app = SimpleNamespace(
            inventory_lookup={("AER-", "STALE"): {}},
            order_rules={},
            _suggest_min_max=lambda key: (None, None),
        )
        item = {
            "line_code": "AER-",
            "item_code": "STALE",
            "description": "STALE ITEM",
            "qty_sold": 0,
            "qty_suspended": 0,
            "status": "review",
            "raw_need": 1,
            "suggested_qty": 0,
            "final_qty": 0,
            "order_qty": 1,
            "order_policy": "manual_only",
            "why": "Manual review required before ordering (missing sale/receipt history)",
        }

        values = ui_bulk.bulk_row_values(fake_app, item)

        self.assertEqual(values[6], 1)
        self.assertEqual(values[7], 0)
        self.assertEqual(values[8], 0)


if __name__ == "__main__":
    unittest.main()
