import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_sheet_actions_flow
import ui_bulk


class BulkSheetActionsFlowTests(unittest.TestCase):
    def test_flush_pending_bulk_sheet_edit_calls_sheet_hook(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(flush_pending_edit=lambda: events.append("flushed")),
        )

        bulk_sheet_actions_flow.flush_pending_bulk_sheet_edit(fake_app)

        self.assertEqual(events, ["flushed"])

    def test_bulk_copy_selection_returns_break_only_when_sheet_copies(self):
        app_true = SimpleNamespace(bulk_sheet=SimpleNamespace(copy_selection_to_clipboard=lambda: True))
        app_false = SimpleNamespace(bulk_sheet=SimpleNamespace(copy_selection_to_clipboard=lambda: False))

        self.assertEqual(bulk_sheet_actions_flow.bulk_copy_selection(app_true), "break")
        self.assertIsNone(bulk_sheet_actions_flow.bulk_copy_selection(app_false))

    def test_bulk_clear_selection_resets_context(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(clear_selection=lambda: events.append("clear")),
            _right_click_bulk_context={"row_id": "1"},
        )

        result = bulk_sheet_actions_flow.bulk_clear_selection(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(events, ["clear"])
        self.assertIsNone(fake_app._right_click_bulk_context)

    def test_bulk_fill_selection_with_current_value_applies_and_records_history(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("0", "1"),
                current_cell_value=lambda: " 6 ",
                clear_selection=lambda: events.append("clear"),
            ),
            _capture_bulk_history_state=lambda: {"before": True},
            _bulk_apply_editor_value=lambda row_id, col_name, value: events.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: events.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
            _finalize_bulk_history_action=lambda label, before: events.append((label, before)),
        )

        result = bulk_sheet_actions_flow.bulk_fill_selection_with_current_value(
            fake_app,
            ("pack_size",),
            lambda event, **kwargs: events.append((event, kwargs["alias"], kwargs["row_count"], kwargs["value"])),
            alias="fill_down",
        )

        self.assertEqual(result, "break")
        self.assertEqual(
            events,
            [
                ("bulk_shortcut_fill", "fill_down", 2, "6"),
                ("0", "pack_size", "6"),
                ("1", "pack_size", "6"),
                ("refresh", ("0", "1")),
                "clear",
                "summary",
                "status",
                ("fill_down:pack_size", {"before": True}),
            ],
        )

    def test_bulk_begin_edit_opens_buy_rule_editor_from_right_click(self):
        events = []
        row_id = ui_bulk.bulk_row_id({"line_code": "AER-", "item_code": "GH781-4"})
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "",
                current_editable_column_name=lambda: "",
                selected_target_row_ids=lambda col_name: (),
                selected_row_ids=lambda: (),
            ),
            _right_click_bulk_context={"row_id": row_id, "col_name": "buy_rule"},
            _resolve_bulk_row_id=lambda current_row_id: (7, {"line_code": "AER-", "item_code": "GH781-4"}) if current_row_id == row_id else (None, None),
            _open_buy_rule_editor=lambda idx: events.append(("buy_rule", idx)),
        )

        result = bulk_sheet_actions_flow.bulk_begin_edit(
            fake_app,
            ("pack_size",),
            lambda *args, **kwargs: None,
            lambda event, **kwargs: events.append((event, kwargs)),
        )

        self.assertEqual(result, "break")
        self.assertIn(("buy_rule", 7), events)
        self.assertIn("bulk_begin_edit", [entry[0] for entry in events if isinstance(entry, tuple) and isinstance(entry[0], str)])
        self.assertIn("bulk_begin_edit.buy_rule_editor", [entry[0] for entry in events if isinstance(entry, tuple) and isinstance(entry[0], str)])
        self.assertIsNone(fake_app._right_click_bulk_context)

    def test_bulk_begin_edit_opens_sheet_cell_for_non_editable_column(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "",
                current_editable_column_name=lambda: "",
                selected_target_row_ids=lambda col_name: (),
                selected_row_ids=lambda: (),
                sheet=SimpleNamespace(open_cell=lambda: events.append("open_cell")),
            ),
            _right_click_bulk_context={"row_id": "3", "col_name": "description"},
        )

        result = bulk_sheet_actions_flow.bulk_begin_edit(
            fake_app,
            ("pack_size",),
            lambda *args, **kwargs: None,
            lambda event, **kwargs: events.append((event, kwargs)),
        )

        self.assertEqual(result, "break")
        self.assertIn("open_cell", events)
        self.assertIn("bulk_begin_edit.open_cell", [entry[0] for entry in events if isinstance(entry, tuple)])
        self.assertIsNone(fake_app._right_click_bulk_context)

    def test_bulk_remove_selected_rows_prefers_right_click_context_row(self):
        events = []
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "AER-", "item_code": "B"}
        row_id_a = ui_bulk.bulk_row_id(item_a)
        row_id_b = ui_bulk.bulk_row_id(item_b)
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                explicit_selected_row_ids=lambda: (),
                current_row_id=lambda: row_id_a,
                clear_selection=lambda: events.append("clear"),
            ),
            _right_click_bulk_context={"row_id": row_id_b},
            filtered_items=[item_a, item_b],
            last_removed_bulk_items=[],
            _apply_bulk_filter=lambda: events.append("filter"),
            _update_bulk_summary=lambda: events.append("summary"),
            _resolve_bulk_row_id=lambda current_row_id: (0, item_a) if current_row_id == row_id_a else ((1, item_b) if current_row_id == row_id_b else (None, None)),
        )

        result = bulk_sheet_actions_flow.bulk_remove_selected_rows(
            fake_app,
            lambda value: dict(value),
            lambda title, message: True,
        )

        self.assertIsNone(result)
        self.assertEqual(fake_app.filtered_items, [item_a])
        self.assertEqual(fake_app.last_removed_bulk_items, [(1, dict(item_b))])
        self.assertEqual(events, ["clear", "filter", "summary"])

    def test_bulk_remove_selected_rows_returns_break_when_nothing_selected_from_event(self):
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                explicit_selected_row_ids=lambda: (),
                current_row_id=lambda: None,
            ),
            _right_click_bulk_context=None,
        )

        result = bulk_sheet_actions_flow.bulk_remove_selected_rows(
            fake_app,
            lambda value: value,
            lambda title, message: True,
            event=object(),
        )

        self.assertEqual(result, "break")

    def test_bulk_fill_selected_cells_applies_value_and_finalizes_history(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: events.append("flush"),
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("0", "1"),
                clear_selection=lambda: events.append("clear"),
            ),
            root=None,
            _capture_bulk_history_state=lambda: {"before": True},
            _bulk_apply_editor_value=lambda row_id, col_name, value: events.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: events.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
            _finalize_bulk_history_action=lambda label, before: events.append((label, before)),
        )

        bulk_sheet_actions_flow.bulk_fill_selected_cells(
            fake_app,
            ("pack_size",),
            lambda title, prompt, parent=None: " 6 ",
            lambda title, message: events.append((title, message)),
        )

        self.assertEqual(
            events,
            [
                "flush",
                ("0", "pack_size", "6"),
                ("1", "pack_size", "6"),
                ("refresh", ("0", "1")),
                "clear",
                "summary",
                "status",
                ("fill:pack_size", {"before": True}),
            ],
        )

    def test_bulk_clear_selected_cells_clears_values_and_finalizes_history(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: events.append("flush"),
                selected_editable_column_name=lambda: "vendor",
                current_editable_column_name=lambda: "vendor",
                selected_target_row_ids=lambda col_name: ("0",),
                clear_selection=lambda: events.append("clear"),
            ),
            _capture_bulk_history_state=lambda: {"before": True},
            _bulk_apply_editor_value=lambda row_id, col_name, value: events.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: events.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: events.append("summary"),
            _update_bulk_cell_status=lambda: events.append("status"),
            _finalize_bulk_history_action=lambda label, before: events.append((label, before)),
        )

        bulk_sheet_actions_flow.bulk_clear_selected_cells(
            fake_app,
            ("vendor",),
            lambda title, message: events.append((title, message)),
        )

        self.assertEqual(
            events,
            [
                "flush",
                ("0", "vendor", ""),
                ("refresh", ("0",)),
                "clear",
                "summary",
                "status",
                ("clear:vendor", {"before": True}),
            ],
        )

    def test_bulk_remove_selected_rows_flushes_pending_sheet_edit_first(self):
        events = []
        item_a = {"line_code": "AER-", "item_code": "A"}
        item_b = {"line_code": "MOT-", "item_code": "B"}
        row_id_a = ui_bulk.bulk_row_id(item_a)
        row_id_b = ui_bulk.bulk_row_id(item_b)
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                flush_pending_edit=lambda: events.append("flush"),
                explicit_selected_row_ids=lambda: (row_id_b,),
                current_row_id=lambda: row_id_a,
                clear_selection=lambda: events.append("clear"),
            ),
            _right_click_bulk_context=None,
            filtered_items=[item_a, item_b],
            last_removed_bulk_items=[],
            _apply_bulk_filter=lambda: events.append("filter"),
            _update_bulk_summary=lambda: events.append("summary"),
            _resolve_bulk_row_id=lambda current_row_id: (0, item_a) if current_row_id == row_id_a else ((1, item_b) if current_row_id == row_id_b else (None, None)),
        )

        result = bulk_sheet_actions_flow.bulk_remove_selected_rows(
            fake_app,
            lambda value: dict(value),
            lambda title, message: True,
        )

        self.assertIsNone(result)
        self.assertEqual(events[:4], ["flush", "clear", "filter", "summary"])

    def test_bulk_delete_selected_clears_cells_when_cells_are_selected(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                explicit_selected_row_ids=lambda: (),
                selected_cells=lambda: [(0, 1)],
            ),
            _bulk_clear_selected_cells=lambda: events.append("clear_cells"),
            _bulk_remove_selected_rows=lambda event=None: events.append(("remove_rows", event)),
        )

        result = bulk_sheet_actions_flow.bulk_delete_selected(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(events, ["clear_cells"])

    def test_bulk_delete_selected_falls_back_to_remove_rows(self):
        events = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                explicit_selected_row_ids=lambda: (),
                selected_cells=lambda: [],
            ),
            _bulk_clear_selected_cells=lambda: events.append("clear_cells"),
            _bulk_remove_selected_rows=lambda event=None: events.append(("remove_rows", event)) or "break",
        )

        result = bulk_sheet_actions_flow.bulk_delete_selected(fake_app, event="evt")

        self.assertEqual(result, "break")
        self.assertEqual(events, [("remove_rows", "evt")])


if __name__ == "__main__":
    unittest.main()
