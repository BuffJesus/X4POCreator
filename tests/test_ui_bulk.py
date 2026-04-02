import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk


class UIBulkTests(unittest.TestCase):
    def test_set_combobox_values_if_changed_skips_redundant_assignment(self):
        writes = []

        class Combo:
            def __init__(self):
                self.values = ("ALL", "AER-")

            def __getitem__(self, key):
                if key != "values":
                    raise KeyError(key)
                return self.values

            def __setitem__(self, key, value):
                if key != "values":
                    raise KeyError(key)
                writes.append(tuple(value))
                self.values = tuple(value)

        combo = Combo()

        changed = ui_bulk.set_combobox_values_if_changed(combo, ["ALL", "AER-"])

        self.assertFalse(changed)
        self.assertEqual(writes, [])

    def test_bulk_row_id_caches_serialized_value_on_item(self):
        item = {"line_code": "AER-", "item_code": "GH781-4"}

        first = ui_bulk.bulk_row_id(item)
        second = ui_bulk.bulk_row_id(item)

        self.assertEqual(first, "[\"AER-\",\"GH781-4\"]")
        self.assertEqual(second, first)
        self.assertEqual(item["_bulk_row_id_key"], ("AER-", "GH781-4"))
        self.assertEqual(item["_bulk_row_id"], first)

    def test_bulk_row_id_rebuilds_cache_when_key_fields_change(self):
        item = {"line_code": "AER-", "item_code": "GH781-4"}

        first = ui_bulk.bulk_row_id(item)
        item["item_code"] = "GH900-1"
        second = ui_bulk.bulk_row_id(item)

        self.assertEqual(first, "[\"AER-\",\"GH781-4\"]")
        self.assertEqual(second, "[\"AER-\",\"GH900-1\"]")
        self.assertEqual(item["_bulk_row_id_key"], ("AER-", "GH900-1"))
        self.assertEqual(item["_bulk_row_id"], second)

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

    def test_resolve_bulk_row_id_uses_direct_row_id_index_without_json_parse(self):
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AER-", "item_code": "B"}
        row_id_b = ui_bulk.bulk_row_id(item_b)
        fake_app = SimpleNamespace(filtered_items=[item_a, item_b])

        ui_bulk.bulk_row_index(fake_app)

        with patch("ui_bulk.json.loads", side_effect=AssertionError("json.loads should not be called")):
            result = ui_bulk.resolve_bulk_row_id(fake_app, row_id_b)

        self.assertEqual(result, (1, item_b))

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

    def test_resolve_bulk_row_id_after_sort_uses_direct_row_id_index_without_json_parse(self):
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AER-", "item_code": "B"}
        row_id_a = ui_bulk.bulk_row_id(item_a)
        fake_app = SimpleNamespace(filtered_items=[item_b, item_a])

        ui_bulk.bulk_row_index(fake_app)
        fake_app.filtered_items.sort(key=lambda item: item["item_code"])
        ui_bulk.invalidate_bulk_row_index(fake_app)
        ui_bulk.bulk_row_index(fake_app)

        with patch("ui_bulk.json.loads", side_effect=AssertionError("json.loads should not be called")):
            result = ui_bulk.resolve_bulk_row_id(fake_app, row_id_a)

        self.assertEqual(result, (0, item_a))

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
            _bulk_filter_result_generation=0,
            _bulk_filter_result_cache={"generation": 0, "filter_state": (), "visible_items": ()},
            _bulk_visible_rows_generation=0,
            _bulk_visible_rows_cache={"generation": 0, "key": (), "row_ids": (), "rows": ()},
            _bulk_row_render_cache={
                ui_bulk.bulk_row_id(keep_item): (("sig",), ("row",)),
                ui_bulk.bulk_row_id(drop_item): (("sig",), ("row",)),
            },
        )

        removed = ui_bulk.sync_bulk_cache_state(fake_app, filtered_items_changed=True)

        self.assertEqual(removed, 1)
        self.assertIsNone(fake_app._bulk_row_index_cache)
        self.assertEqual(fake_app._bulk_row_index_generation, 1)
        self.assertIsNone(fake_app._bulk_filter_result_cache)
        self.assertEqual(fake_app._bulk_filter_result_generation, 1)
        self.assertIsNone(fake_app._bulk_visible_rows_cache)
        self.assertEqual(fake_app._bulk_visible_rows_generation, 1)
        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [ui_bulk.bulk_row_id(keep_item)])

    def test_replace_filtered_items_updates_plain_object_and_syncs_caches(self):
        keep_item = {
            "line_code": "AER-",
            "item_code": "KEEP",
            "vendor": "MOTION",
            "status": "review",
            "performance_profile": "steady",
            "sales_health_signal": "active",
            "reorder_attention_signal": "normal",
        }
        drop_item = {"line_code": "AER-", "item_code": "DROP"}
        fake_app = SimpleNamespace(
            filtered_items=[drop_item],
            _bulk_row_index_generation=0,
            _bulk_row_index_cache={"generation": 0, "by_row_id": {}, "by_key": {}},
            _bulk_row_render_cache={
                ui_bulk.bulk_row_id(keep_item): (("sig",), ("row",)),
                ui_bulk.bulk_row_id(drop_item): (("sig",), ("row",)),
            },
        )

        result = ui_bulk.replace_filtered_items(fake_app, [keep_item])

        self.assertEqual(result, [keep_item])
        self.assertEqual(fake_app.filtered_items, [keep_item])
        self.assertIsNone(fake_app._bulk_row_index_cache)
        self.assertEqual(fake_app._bulk_row_index_generation, 1)
        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [ui_bulk.bulk_row_id(keep_item)])
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 1, "assigned": 1, "review": 1, "warning": 0, "skip": 0})
        self.assertEqual(fake_app._bulk_line_code_values, ["AER-"])
        self.assertEqual(fake_app._bulk_items_by_assignment_status, {"Assigned": (keep_item,)})
        self.assertEqual(fake_app._bulk_items_by_item_status, {"Review": (keep_item,)})
        self.assertEqual(fake_app._bulk_items_by_performance, {"Steady": (keep_item,)})
        self.assertEqual(fake_app._bulk_items_by_sales_health, {"Active": (keep_item,)})
        self.assertEqual(fake_app._bulk_items_by_attention, {"Normal": (keep_item,)})

    def test_sort_filtered_items_replaces_list_and_invalidates_index(self):
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AER-", "item_code": "B"}
        fake_app = SimpleNamespace(
            filtered_items=[item_b, item_a],
            _bulk_row_index_generation=0,
            _bulk_row_index_cache={"generation": 0, "by_row_id": {}, "by_key": {}},
            _bulk_row_render_cache={},
        )

        result = ui_bulk.sort_filtered_items(fake_app, key=lambda item: item["item_code"])

        self.assertEqual(result, [item_a, item_b])
        self.assertEqual(fake_app.filtered_items, [item_a, item_b])
        self.assertIsNone(fake_app._bulk_row_index_cache)
        self.assertEqual(fake_app._bulk_row_index_generation, 1)

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
        item = {
            "vendor": "OLD",
            "status": "review",
            "data_flags": [],
            "performance_profile": "steady",
            "sales_health_signal": "active",
            "reorder_attention_signal": "normal",
        }
        fake_app = SimpleNamespace(
            filtered_items=[item],
            _bulk_summary_counts={"total": 1, "assigned": 1, "review": 1, "warning": 0},
            _bulk_items_by_assignment_status={"Assigned": (item,)},
            _bulk_items_by_item_status={"Review": (item,)},
            _bulk_items_by_performance={"Steady": (item,)},
            _bulk_items_by_sales_health={"Active": (item,)},
            _bulk_items_by_attention={"Normal": (item,)},
        )

        result = ui_bulk.adjust_bulk_summary_for_item_change(
            fake_app,
            {
                "vendor": "OLD",
                "status": "review",
                "data_flags": (),
                "performance_profile": "steady",
                "sales_health_signal": "active",
                "reorder_attention_signal": "normal",
            },
            {
                "vendor": "",
                "status": "warning",
                "data_flags": ("missing_pack",),
                "performance_profile": "legacy",
                "sales_health_signal": "dormant",
                "reorder_attention_signal": "review_missed_reorder",
            },
            item=item,
        )

        self.assertTrue(result)
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 1, "assigned": 0, "review": 0, "warning": 1})
        self.assertEqual(fake_app._bulk_items_by_assignment_status, {"Unassigned": (item,)})
        self.assertEqual(fake_app._bulk_items_by_item_status, {"No Pack": (item,)})
        self.assertEqual(fake_app._bulk_items_by_performance, {"Legacy": (item,)})
        self.assertEqual(fake_app._bulk_items_by_sales_health, {"Dormant": (item,)})
        self.assertEqual(fake_app._bulk_items_by_attention, {"Missed Reorder": (item,)})

    def test_adjust_bulk_summary_for_item_change_invalidates_filter_result_cache(self):
        item = {"vendor": "", "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item],
            _bulk_summary_counts={"total": 1, "assigned": 0, "review": 0, "warning": 0},
            _bulk_filter_result_generation=0,
            _bulk_filter_result_cache={"generation": 0, "filter_state": (("status", "ALL"),), "visible_items": (item,)},
            _bulk_visible_rows_generation=0,
            _bulk_visible_rows_cache={"generation": 0, "key": (), "row_ids": ("0",), "rows": (("row",),)},
        )

        ui_bulk.adjust_bulk_summary_for_item_change(
            fake_app,
            {"vendor": "", "status": "ok"},
            {"vendor": "MOTION", "status": "ok"},
            item=item,
        )

        self.assertIsNone(fake_app._bulk_filter_result_cache)
        self.assertEqual(fake_app._bulk_filter_result_generation, 1)
        self.assertIsNone(fake_app._bulk_visible_rows_cache)
        self.assertEqual(fake_app._bulk_visible_rows_generation, 1)

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
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 2, "assigned": 2, "review": 0, "warning": 0, "skip": 0})

    def test_apply_bulk_filter_default_path_skips_matcher_scan(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))

        class Combo:
            def __init__(self):
                self.values = ()

            def __getitem__(self, key):
                if key != "values":
                    raise KeyError(key)
                return self.values

            def __setitem__(self, key, value):
                if key != "values":
                    raise KeyError(key)
                self.values = tuple(value)

        fake_app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"},
                {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"},
            ],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-", "MOT-"],
            _bulk_items_by_line_code={"AER-": (), "MOT-": ()},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=Combo(),
            combo_bulk_vendor=Combo(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item) for item in fake_app.filtered_items])

    def test_apply_bulk_filter_line_code_path_scans_only_line_code_bucket(self):
        seen = []
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))

        class Combo:
            def __init__(self):
                self.values = ()

            def __getitem__(self, key):
                if key != "values":
                    raise KeyError(key)
                return self.values

            def __setitem__(self, key, value):
                if key != "values":
                    raise KeyError(key)
                self.values = tuple(value)

        item_a = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        item_b = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_a, item_b],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-", "MOT-"],
            _bulk_items_by_line_code={"AER-": (item_a,), "MOT-": (item_b,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "AER-"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=Combo(),
            combo_bulk_vendor=Combo(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_a)])

    def test_apply_bulk_filter_source_path_scans_only_source_bucket(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_sales = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        item_susp = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 0, "qty_suspended": 1, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_sales, item_susp],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-", "MOT-"],
            _bulk_items_by_line_code={"AER-": (item_sales,), "MOT-": (item_susp,)},
            _bulk_items_by_source={"Sales": (item_sales,), "Susp": (item_susp,)},
            _bulk_items_by_line_code_source={("AER-", "Sales"): (item_sales,), ("MOT-", "Susp"): (item_susp,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "Sales"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_sales)])

    def test_apply_bulk_filter_assignment_status_path_uses_assignment_bucket(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_assigned = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "MOTION", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        item_unassigned = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_assigned, item_unassigned],
            _bulk_summary_counts={"total": 2, "assigned": 1, "review": 0, "warning": 0},
            _bulk_items_by_assignment_status={"Assigned": (item_assigned,), "Unassigned": (item_unassigned,)},
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
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_assigned)])

    def test_apply_bulk_filter_item_status_path_uses_item_status_bucket(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_ok = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        item_warning = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "warning"}
        fake_app = SimpleNamespace(
            filtered_items=[item_ok, item_warning],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 1},
            _bulk_items_by_item_status={"OK": (item_ok,), "Warning": (item_warning,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "Warning"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_warning)])

    def test_apply_bulk_filter_line_code_and_source_path_uses_intersection_bucket(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_match = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        item_same_lc = {"line_code": "AER-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 0, "qty_suspended": 1, "status": "ok"}
        item_same_source = {"line_code": "MOT-", "item_code": "C", "description": "Item C", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_match, item_same_lc, item_same_source],
            _bulk_summary_counts={"total": 3, "assigned": 0, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-", "MOT-"],
            _bulk_items_by_line_code={"AER-": (item_match, item_same_lc), "MOT-": (item_same_source,)},
            _bulk_items_by_source={"Sales": (item_match, item_same_source), "Susp": (item_same_lc,)},
            _bulk_items_by_line_code_source={("AER-", "Sales"): (item_match,), ("AER-", "Susp"): (item_same_lc,), ("MOT-", "Sales"): (item_same_source,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "AER-"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "Sales"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_match)])

    def test_apply_bulk_filter_bucket_intersection_skips_matcher_for_status_and_source(self):
        seen = []
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_sales = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "MOTION", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        item_susp = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 0, "qty_suspended": 1, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_sales, item_susp],
            _bulk_summary_counts={"total": 2, "assigned": 1, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-", "MOT-"],
            _bulk_items_by_line_code={"AER-": (item_sales,), "MOT-": (item_susp,)},
            _bulk_items_by_source={"Sales": (item_sales,), "Susp": (item_susp,)},
            _bulk_items_by_assignment_status={"Assigned": (item_sales,), "Unassigned": (item_susp,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "Assigned"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "Sales"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_sales)])

    def test_apply_bulk_filter_performance_path_uses_performance_bucket(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_top = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "MOTION", "qty_sold": 1, "qty_suspended": 0, "status": "ok", "performance_profile": "top_performer"}
        item_steady = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 0, "qty_suspended": 1, "status": "ok", "performance_profile": "steady"}
        fake_app = SimpleNamespace(
            filtered_items=[item_top, item_steady],
            _bulk_summary_counts={"total": 2, "assigned": 1, "review": 0, "warning": 0},
            _bulk_items_by_assignment_status={"Assigned": (item_top,), "Unassigned": (item_steady,)},
            _bulk_items_by_performance={"Top": (item_top,), "Steady": (item_steady,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "Assigned"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "Top"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_top)])

    def test_apply_bulk_filter_attention_and_source_path_uses_bucket_intersection(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_match = {
            "line_code": "AER-",
            "item_code": "A",
            "description": "Item A",
            "vendor": "",
            "qty_sold": 1,
            "qty_suspended": 0,
            "status": "ok",
            "reorder_attention_signal": "review_missed_reorder",
        }
        item_source_only = {
            "line_code": "MOT-",
            "item_code": "B",
            "description": "Item B",
            "vendor": "",
            "qty_sold": 1,
            "qty_suspended": 0,
            "status": "ok",
            "reorder_attention_signal": "normal",
        }
        item_attention_only = {
            "line_code": "MOT-",
            "item_code": "C",
            "description": "Item C",
            "vendor": "",
            "qty_sold": 0,
            "qty_suspended": 1,
            "status": "ok",
            "reorder_attention_signal": "review_missed_reorder",
        }
        fake_app = SimpleNamespace(
            filtered_items=[item_match, item_source_only, item_attention_only],
            _bulk_summary_counts={"total": 3, "assigned": 0, "review": 0, "warning": 0},
            _bulk_items_by_source={"Sales": (item_match, item_source_only), "Susp": (item_attention_only,)},
            _bulk_items_by_attention={"Missed Reorder": (item_match, item_attention_only), "Normal": (item_source_only,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "Sales"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "Missed Reorder"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=AssertionError("matcher should not run")):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_match)])

    def test_apply_bulk_filter_uses_matcher_when_bucket_cache_is_missing(self):
        seen = []
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_top = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok", "performance_profile": "top_performer"}
        item_steady = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok", "performance_profile": "steady"}
        fake_app = SimpleNamespace(
            filtered_items=[item_top, item_steady],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "Top"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        original = ui_bulk.item_matches_bulk_filter

        def tracking_matcher(item, filter_state):
            seen.append(item["item_code"])
            return original(item, filter_state)

        with patch("ui_bulk.item_matches_bulk_filter", side_effect=tracking_matcher):
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(seen, ["A", "B"])
        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_top)])

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

    def test_apply_bulk_filter_reuses_cached_visible_result_when_filter_state_is_unchanged(self):
        calls = []
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_sales = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        item_susp = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 0, "qty_suspended": 1, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_sales, item_susp],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            _bulk_items_by_source={"Sales": (item_sales,), "Susp": (item_susp,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "Sales"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        original = ui_bulk.filtered_candidate_items

        def tracking_candidates(app, filter_state):
            calls.append(dict(filter_state))
            return original(app, filter_state)

        with patch("ui_bulk.filtered_candidate_items", side_effect=tracking_candidates):
            ui_bulk.apply_bulk_filter(fake_app)
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(len(calls), 1)
        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_sales)])
        self.assertEqual(captured[3][1], [ui_bulk.bulk_row_id(item_sales)])

    def test_apply_bulk_filter_reuses_cached_visible_row_payload_when_state_is_unchanged(self):
        build_calls = []
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_sales = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_sales],
            _bulk_summary_counts={"total": 1, "assigned": 0, "review": 0, "warning": 0},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            var_reorder_cycle=SimpleNamespace(get=lambda: "Biweekly"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        original = ui_bulk.build_bulk_sheet_rows

        def tracking_build(app, items, **kwargs):
            build_calls.append(tuple(items))
            return original(app, items, **kwargs)

        with patch("ui_bulk.build_bulk_sheet_rows", side_effect=tracking_build):
            ui_bulk.apply_bulk_filter(fake_app)
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(len(build_calls), 1)
        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_sales)])
        self.assertEqual(captured[3][1], [ui_bulk.bulk_row_id(item_sales)])

    def test_apply_bulk_filter_recomputes_visible_result_after_item_change_invalidation(self):
        calls = []
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_top = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok", "performance_profile": "top_performer"}
        item_steady = {"line_code": "MOT-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok", "performance_profile": "steady"}
        fake_app = SimpleNamespace(
            filtered_items=[item_top, item_steady],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            _bulk_items_by_performance={"Top": (item_top,), "Steady": (item_steady,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "Top"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        original = ui_bulk.filtered_candidate_items

        def tracking_candidates(app, filter_state):
            calls.append(dict(filter_state))
            return original(app, filter_state)

        with patch("ui_bulk.filtered_candidate_items", side_effect=tracking_candidates):
            ui_bulk.apply_bulk_filter(fake_app)
            ui_bulk.adjust_bulk_summary_for_item_change(
                fake_app,
                ui_bulk.bulk_filter_bucket_snapshot(item_top),
                {
                    "vendor": "",
                    "status": "ok",
                    "data_flags": (),
                    "performance_profile": "steady",
                    "sales_health_signal": "",
                    "reorder_attention_signal": "",
                },
                item=item_top,
            )
            item_top["performance_profile"] = "steady"
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(len(calls), 2)
        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_top)])
        self.assertEqual(captured[3][1], [])

    def test_apply_bulk_filter_rebuilds_visible_row_payload_after_item_change_invalidation(self):
        build_calls = []
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))
        item_top = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 1, "qty_suspended": 0, "status": "ok", "performance_profile": "top_performer"}
        fake_app = SimpleNamespace(
            filtered_items=[item_top],
            _bulk_summary_counts={"total": 1, "assigned": 0, "review": 0, "warning": 0},
            _bulk_items_by_performance={"Top": (item_top,)},
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: captured.append(("flush",)),
                set_rows=lambda rows, row_ids: captured.append((rows, row_ids)),
            ),
            var_bulk_lc_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_status_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_source_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_item_status=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_performance_filter=SimpleNamespace(get=lambda: "Top"),
            var_bulk_sales_health_filter=SimpleNamespace(get=lambda: "ALL"),
            var_bulk_attention_filter=SimpleNamespace(get=lambda: "ALL"),
            var_reorder_cycle=SimpleNamespace(get=lambda: "Biweekly"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            combo_bulk_lc=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            combo_bulk_vendor=type("Combo", (), {"__getitem__": lambda self, key: (), "__setitem__": lambda self, key, value: None})(),
            vendor_codes_used=[],
            lbl_bulk_summary=label,
        )

        original = ui_bulk.build_bulk_sheet_rows

        def tracking_build(app, items, **kwargs):
            build_calls.append(tuple(items))
            return original(app, items, **kwargs)

        with patch("ui_bulk.build_bulk_sheet_rows", side_effect=tracking_build):
            ui_bulk.apply_bulk_filter(fake_app)
            ui_bulk.adjust_bulk_summary_for_item_change(
                fake_app,
                ui_bulk.bulk_filter_bucket_snapshot(item_top),
                {
                    "vendor": "",
                    "status": "ok",
                    "data_flags": (),
                    "performance_profile": "steady",
                    "sales_health_signal": "",
                    "reorder_attention_signal": "",
                },
                item=item_top,
            )
            item_top["performance_profile"] = "steady"
            fake_app._bulk_items_by_performance = {"Steady": (item_top,)}
            ui_bulk.apply_bulk_filter(fake_app)

        self.assertEqual(len(build_calls), 2)
        self.assertEqual(captured[1][1], [ui_bulk.bulk_row_id(item_top)])
        self.assertEqual(captured[3][1], [])

    def test_populate_bulk_tree_skips_combobox_updates_when_values_are_unchanged(self):
        captured = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))

        class Combo:
            def __init__(self, values):
                self.values = tuple(values)
                self.write_count = 0

            def __getitem__(self, key):
                if key != "values":
                    raise KeyError(key)
                return self.values

            def __setitem__(self, key, value):
                if key != "values":
                    raise KeyError(key)
                self.write_count += 1
                self.values = tuple(value)

        fake_app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "MOTION", "qty_sold": 1, "qty_suspended": 0, "status": "ok"},
            ],
            _bulk_summary_counts={"total": 1, "assigned": 1, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-"],
            combo_bulk_lc=Combo(("ALL", "AER-")),
            combo_bulk_vendor=Combo(("MOTION",)),
            vendor_codes_used=["MOTION"],
            bulk_sheet=SimpleNamespace(set_rows=lambda rows, row_ids: captured.append((rows, row_ids))),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            lbl_bulk_summary=label,
        )

        ui_bulk.populate_bulk_tree(fake_app)

        self.assertEqual(fake_app.combo_bulk_lc.write_count, 0)
        self.assertEqual(fake_app.combo_bulk_vendor.write_count, 0)
        self.assertEqual(captured[0][1], ["0"])

    def test_populate_bulk_tree_reuses_cached_visible_row_payload_when_state_is_unchanged(self):
        captured = []
        build_calls = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))

        class Combo:
            def __init__(self):
                self.values = ()

            def __getitem__(self, key):
                if key != "values":
                    raise KeyError(key)
                return self.values

            def __setitem__(self, key, value):
                if key != "values":
                    raise KeyError(key)
                self.values = tuple(value)

        fake_app = SimpleNamespace(
            filtered_items=[
                {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "MOTION", "qty_sold": 1, "qty_suspended": 0, "status": "ok"},
            ],
            _bulk_summary_counts={"total": 1, "assigned": 1, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-"],
            combo_bulk_lc=Combo(),
            combo_bulk_vendor=Combo(),
            vendor_codes_used=["MOTION"],
            bulk_sheet=SimpleNamespace(set_rows=lambda rows, row_ids: captured.append((rows, row_ids))),
            var_reorder_cycle=SimpleNamespace(get=lambda: "Biweekly"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            lbl_bulk_summary=label,
        )

        original = ui_bulk.build_bulk_sheet_rows

        def tracking_build(app, items, **kwargs):
            build_calls.append(tuple(items))
            return original(app, items, **kwargs)

        with patch("ui_bulk.build_bulk_sheet_rows", side_effect=tracking_build):
            ui_bulk.populate_bulk_tree(fake_app)
            ui_bulk.populate_bulk_tree(fake_app)

        self.assertEqual(len(build_calls), 1)
        self.assertEqual(captured[0][1], ["0"])
        self.assertEqual(captured[1][1], ["0"])

    def test_populate_bulk_tree_rebuilds_visible_row_payload_after_sort_invalidation(self):
        captured = []
        build_calls = []
        label = SimpleNamespace(config=lambda **kwargs: setattr(label, "text", kwargs.get("text", "")))

        class Combo:
            def __init__(self):
                self.values = ()

            def __getitem__(self, key):
                if key != "values":
                    raise KeyError(key)
                return self.values

            def __setitem__(self, key, value):
                if key != "values":
                    raise KeyError(key)
                self.values = tuple(value)

        item_b = {"line_code": "AER-", "item_code": "B", "description": "Item B", "vendor": "", "qty_sold": 0, "qty_suspended": 0, "status": "ok"}
        item_a = {"line_code": "AER-", "item_code": "A", "description": "Item A", "vendor": "", "qty_sold": 0, "qty_suspended": 0, "status": "ok"}
        fake_app = SimpleNamespace(
            filtered_items=[item_b, item_a],
            _bulk_summary_counts={"total": 2, "assigned": 0, "review": 0, "warning": 0},
            _bulk_line_code_values=["AER-"],
            combo_bulk_lc=Combo(),
            combo_bulk_vendor=Combo(),
            vendor_codes_used=[],
            bulk_sheet=SimpleNamespace(set_rows=lambda rows, row_ids: captured.append((rows, row_ids))),
            var_reorder_cycle=SimpleNamespace(get=lambda: "Biweekly"),
            _suggest_min_max=lambda key: (None, None),
            inventory_lookup={},
            order_rules={},
            lbl_bulk_summary=label,
        )

        original = ui_bulk.build_bulk_sheet_rows

        def tracking_build(app, items, **kwargs):
            build_calls.append(tuple(item["item_code"] for item in items))
            return original(app, items, **kwargs)

        with patch("ui_bulk.build_bulk_sheet_rows", side_effect=tracking_build):
            ui_bulk.populate_bulk_tree(fake_app)
            ui_bulk.sort_filtered_items(fake_app, key=lambda item: item["item_code"])
            ui_bulk.populate_bulk_tree(fake_app)

        self.assertEqual(len(build_calls), 2)
        self.assertEqual(build_calls[0], ("B", "A"))
        self.assertEqual(build_calls[1], ("A", "B"))
        self.assertEqual(captured[0][1], ["0", "1"])
        self.assertEqual(captured[1][1], ["0", "1"])

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

    # --- Phase 6: filter and sort persistence ---

    class _FakeVar:
        def __init__(self, value="ALL"):
            self._value = value
        def get(self):
            return self._value
        def set(self, v):
            self._value = v

    def _make_filter_app(self, settings=None):
        saved_calls = []
        app = SimpleNamespace(
            app_settings=settings or {},
            _bulk_sort_col=None,
            _bulk_sort_reverse=False,
            var_bulk_lc_filter=self._FakeVar("ALL"),
            var_bulk_status_filter=self._FakeVar("ALL"),
            var_bulk_source_filter=self._FakeVar("ALL"),
            var_bulk_item_status=self._FakeVar("ALL"),
            var_bulk_performance_filter=self._FakeVar("ALL"),
            var_bulk_sales_health_filter=self._FakeVar("ALL"),
            var_bulk_attention_filter=self._FakeVar("ALL"),
        )
        app._save_app_settings = lambda: saved_calls.append("saved")
        app._saved_calls = saved_calls
        return app

    def test_save_bulk_filter_sort_state_persists_to_app_settings(self):
        app = self._make_filter_app()
        app.var_bulk_lc_filter.set("AER-")
        app._bulk_sort_col = "vendor"
        app._bulk_sort_reverse = True
        ui_bulk.save_bulk_filter_sort_state(app)
        self.assertEqual(app.app_settings["bulk_filter_state"]["lc"], "AER-")
        self.assertEqual(app.app_settings["bulk_sort_col"], "vendor")
        self.assertTrue(app.app_settings["bulk_sort_reverse"])
        self.assertIn("saved", app._saved_calls)

    def test_restore_bulk_filter_sort_state_applies_saved_values(self):
        settings = {
            "bulk_filter_state": {"lc": "AER-", "status": "Assigned", "source": "ALL",
                                   "item_status": "ALL", "performance": "ALL",
                                   "sales_health": "ALL", "attention": "ALL"},
            "bulk_sort_col": "vendor",
            "bulk_sort_reverse": True,
        }
        app = self._make_filter_app(settings)
        ui_bulk.restore_bulk_filter_sort_state(app)
        self.assertEqual(app.var_bulk_lc_filter.get(), "AER-")
        self.assertEqual(app.var_bulk_status_filter.get(), "Assigned")
        self.assertEqual(app._bulk_sort_col, "vendor")
        self.assertTrue(app._bulk_sort_reverse)

    def test_restore_bulk_filter_sort_state_handles_missing_settings(self):
        app = self._make_filter_app({})
        ui_bulk.restore_bulk_filter_sort_state(app)
        self.assertEqual(app.var_bulk_lc_filter.get(), "ALL")
        self.assertIsNone(app._bulk_sort_col)

    def test_save_bulk_filter_sort_state_noop_when_no_app_settings(self):
        app = SimpleNamespace()
        del app  # no app_settings attr
        app = SimpleNamespace()
        # Should not raise
        ui_bulk.save_bulk_filter_sort_state(app)


class BulkFilterPresetTests(unittest.TestCase):
    def _make_app(self):
        from types import SimpleNamespace
        saved = []

        def save_fn():
            saved.append(1)

        app = SimpleNamespace(
            app_settings={},
            _save_app_settings=save_fn,
            combo_bulk_preset=None,
            var_bulk_lc_filter=None,
            var_bulk_status_filter=None,
            var_bulk_source_filter=None,
            var_bulk_item_status=None,
            var_bulk_performance_filter=None,
            var_bulk_sales_health_filter=None,
            var_bulk_attention_filter=None,
        )
        app._saved = saved
        return app

    def test_save_bulk_filter_preset_persists(self):
        app = self._make_app()
        # Manually set a filter state via var stubs
        class _Var:
            def __init__(self, v):
                self._v = v
            def get(self):
                return self._v
            def set(self, v):
                self._v = v

        app.var_bulk_lc_filter = _Var("AER-")
        app.var_bulk_status_filter = _Var("Unassigned")
        app.var_bulk_source_filter = _Var("ALL")
        app.var_bulk_item_status = _Var("ALL")
        app.var_bulk_performance_filter = _Var("Top")
        app.var_bulk_sales_health_filter = _Var("ALL")
        app.var_bulk_attention_filter = _Var("ALL")

        ui_bulk.save_bulk_filter_preset(app, "MyPreset")

        presets = ui_bulk.get_bulk_filter_presets(app)
        self.assertIn("MyPreset", presets)
        self.assertEqual(presets["MyPreset"]["lc"], "AER-")
        self.assertEqual(presets["MyPreset"]["status"], "Unassigned")
        self.assertEqual(presets["MyPreset"]["performance"], "Top")
        self.assertTrue(len(app._saved) >= 1)

    def test_apply_bulk_filter_preset_sets_vars(self):
        app = self._make_app()

        class _Var:
            def __init__(self, v):
                self._v = v
            def get(self):
                return self._v
            def set(self, v):
                self._v = v

        app.var_bulk_lc_filter = _Var("ALL")
        app.var_bulk_status_filter = _Var("ALL")
        app.var_bulk_source_filter = _Var("ALL")
        app.var_bulk_item_status = _Var("ALL")
        app.var_bulk_performance_filter = _Var("ALL")
        app.var_bulk_sales_health_filter = _Var("ALL")
        app.var_bulk_attention_filter = _Var("ALL")

        app.app_settings["bulk_filter_presets"] = {
            "TestPreset": {
                "lc": "AMS-",
                "status": "Assigned",
                "source": "Sales",
                "item_status": "Review",
                "performance": "Steady",
                "sales_health": "Active",
                "attention": "Normal",
            }
        }

        apply_calls = []

        with patch("ui_bulk.apply_bulk_filter", side_effect=lambda a: apply_calls.append(a)):
            ui_bulk.apply_bulk_filter_preset(app, "TestPreset")

        self.assertEqual(app.var_bulk_lc_filter.get(), "AMS-")
        self.assertEqual(app.var_bulk_status_filter.get(), "Assigned")
        self.assertEqual(app.var_bulk_source_filter.get(), "Sales")
        self.assertEqual(app.var_bulk_item_status.get(), "Review")
        self.assertEqual(app.var_bulk_performance_filter.get(), "Steady")
        self.assertEqual(app.var_bulk_sales_health_filter.get(), "Active")
        self.assertEqual(app.var_bulk_attention_filter.get(), "Normal")
        self.assertEqual(len(apply_calls), 1)

    def test_delete_bulk_filter_preset_removes_entry(self):
        app = self._make_app()
        app.app_settings["bulk_filter_presets"] = {
            "Keep": {"lc": "ALL", "status": "ALL", "source": "ALL",
                     "item_status": "ALL", "performance": "ALL",
                     "sales_health": "ALL", "attention": "ALL"},
            "Delete": {"lc": "AER-", "status": "ALL", "source": "ALL",
                       "item_status": "ALL", "performance": "ALL",
                       "sales_health": "ALL", "attention": "ALL"},
        }

        ui_bulk.delete_bulk_filter_preset(app, "Delete")

        presets = ui_bulk.get_bulk_filter_presets(app)
        self.assertIn("Keep", presets)
        self.assertNotIn("Delete", presets)
        self.assertTrue(len(app._saved) >= 1)

    def test_apply_nonexistent_preset_is_noop(self):
        app = self._make_app()
        app.app_settings["bulk_filter_presets"] = {}

        class _Var:
            def __init__(self, v):
                self._v = v
            def get(self):
                return self._v
            def set(self, v):
                self._v = v

        app.var_bulk_lc_filter = _Var("AER-")

        # Should not raise, should not change any var
        ui_bulk.apply_bulk_filter_preset(app, "DoesNotExist")
        self.assertEqual(app.var_bulk_lc_filter.get(), "AER-")


if __name__ == "__main__":
    unittest.main()
