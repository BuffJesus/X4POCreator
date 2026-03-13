import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_bulk


class UIBulkTests(unittest.TestCase):
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
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(refresh_row=lambda row_id, values: events.append((row_id, values))),
            filtered_items=[
                {"line_code": "AER-", "item_code": "GH781-4", "vendor": "MOTION", "description": ""},
                {"line_code": "AER-", "item_code": "GH781-5", "vendor": "", "description": ""},
            ],
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

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, ("0", "1"))

        self.assertTrue(result)
        self.assertEqual(events, [("0", ("GH781-4", "MOTION")), ("1", ("GH781-5", ""))])

    def test_refresh_bulk_view_after_edit_falls_back_to_filter_when_filtered(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(refresh_row=lambda row_id, values: events.append((row_id, values))),
            filtered_items=[{"line_code": "AER-", "item_code": "GH781-4", "description": ""}],
            _bulk_row_values=lambda item: (item["item_code"],),
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

        result = ui_bulk.refresh_bulk_view_after_edit(fake_app, ("0",))

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
        self.assertEqual(captured[1][1], ["0"])
        self.assertEqual(captured[1][0][0][2], "A")
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 2, "assigned": 2, "review": 0, "warning": 0})

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


if __name__ == "__main__":
    unittest.main()
