import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import po_builder
from bulk_sheet import BulkSheetView


class FakeLabel:
    def __init__(self):
        self.text = ""

    def config(self, text=""):
        self.text = text


class BulkSheetStatusTests(unittest.TestCase):
    def test_bulk_status_uses_sheet_current_column_when_no_cell_selection(self):
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_cells=lambda: [],
                selected_editable_column_name=lambda: "",
                current_column_name=lambda: "pack_size",
                selected_row_ids=lambda: ("1", "2"),
            ),
            lbl_bulk_cell_status=FakeLabel(),
        )

        po_builder.POBuilderApp._update_bulk_cell_status(fake_app)

        self.assertIn("Active edit column: Pack", fake_app.lbl_bulk_cell_status.text)
        self.assertIn("Selected rows: 2", fake_app.lbl_bulk_cell_status.text)

    def test_bulk_status_prefers_sheet_selected_cells_count(self):
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_cells=lambda: [(0, 15), (1, 15)],
                selected_editable_column_name=lambda: "pack_size",
                current_column_name=lambda: "pack_size",
                selected_row_ids=lambda: ("1", "2"),
            ),
            lbl_bulk_cell_status=FakeLabel(),
        )

        po_builder.POBuilderApp._update_bulk_cell_status(fake_app)

        self.assertIn("Selected cells: 2", fake_app.lbl_bulk_cell_status.text)

    def test_bulk_delete_selected_prefers_explicit_row_selection(self):
        removed = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                explicit_selected_row_ids=lambda: ("1",),
                selected_cells=lambda: [(0, 15)],
                selected_row_ids=lambda: ("0", "1"),
                clear_selection=lambda: removed.append("cleared"),
            ),
            filtered_items=[{"item_code": "A"}, {"item_code": "B"}],
            last_removed_bulk_items=[],
            _apply_bulk_filter=lambda: removed.append("filtered"),
            _update_bulk_summary=lambda: removed.append("summary"),
        )
        fake_app._bulk_remove_selected_rows = lambda event=None: po_builder.POBuilderApp._bulk_remove_selected_rows(fake_app, event)

        with patch("po_builder.messagebox.askyesno", return_value=True):
            result = po_builder.POBuilderApp._bulk_delete_selected(fake_app)

        self.assertIsNone(result)
        self.assertEqual(len(fake_app.filtered_items), 1)
        self.assertEqual(fake_app.filtered_items[0]["item_code"], "A")

    def test_bulk_delete_selected_removes_multiple_noncontiguous_rows(self):
        # Regression for the v0.8.1 Delete-key wiring: ctrl-clicking
        # row headers 0, 2, and 4 then pressing Delete should remove
        # exactly those three rows, not collapse them to a contiguous
        # range.
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                # explicit_selected_row_ids returns the ctrl-click set,
                # which already contains non-contiguous ids.
                explicit_selected_row_ids=lambda: ("0", "2", "4"),
                selected_cells=lambda: [],
                selected_row_ids=lambda: ("0", "2", "4"),
                clear_selection=lambda: None,
            ),
            filtered_items=[
                {"line_code": "A", "item_code": "1"},
                {"line_code": "A", "item_code": "2"},
                {"line_code": "A", "item_code": "3"},
                {"line_code": "A", "item_code": "4"},
                {"line_code": "A", "item_code": "5"},
            ],
            last_removed_bulk_items=[],
            _apply_bulk_filter=lambda: None,
            _update_bulk_summary=lambda: None,
        )
        fake_app._bulk_remove_selected_rows = lambda event=None: (
            po_builder.POBuilderApp._bulk_remove_selected_rows(fake_app, event)
        )

        with patch("po_builder.messagebox.askyesno", return_value=True):
            result = po_builder.POBuilderApp._bulk_delete_selected(fake_app)

        self.assertIsNone(result)
        remaining = [item["item_code"] for item in fake_app.filtered_items]
        self.assertEqual(remaining, ["2", "4"])

    def test_bulk_delete_selected_falls_back_to_current_row(self):
        removed = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                explicit_selected_row_ids=lambda: (),
                current_row_id=lambda: "0",
                clear_selection=lambda: removed.append("cleared"),
            ),
            filtered_items=[{"item_code": "A"}, {"item_code": "B"}],
            last_removed_bulk_items=[],
            _apply_bulk_filter=lambda: removed.append("filtered"),
            _update_bulk_summary=lambda: removed.append("summary"),
        )

        with patch("po_builder.messagebox.askyesno", return_value=True):
            result = po_builder.POBuilderApp._bulk_remove_selected_rows(fake_app)

        self.assertEqual(result, None)
        self.assertEqual(len(fake_app.filtered_items), 1)
        self.assertEqual(fake_app.filtered_items[0]["item_code"], "B")

    def test_bulk_begin_edit_bulk_applies_multi_selection(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("0", "1"),
                current_cell_value=lambda: "500",
                clear_selection=lambda: calls.append(("cleared",)),
            ),
            root=None,
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="750"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:6], [("0", "pack_size", "750"), ("1", "pack_size", "750"), ("refresh", ("0", "1")), ("cleared",), ("summary",), ("status",)])

    def test_bulk_begin_edit_uses_selected_rows_when_column_is_active(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: (),
                selected_row_ids=lambda: ("0", "1"),
                current_cell_value=lambda: "500",
                clear_selection=lambda: calls.append(("cleared",)),
            ),
            root=None,
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="750"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:6], [("0", "pack_size", "750"), ("1", "pack_size", "750"), ("refresh", ("0", "1")), ("cleared",), ("summary",), ("status",)])

    def test_bulk_begin_edit_single_row_uses_prompt_path(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("8",),
                selected_row_ids=lambda: ("8",),
                current_cell_value=lambda: "2",
                clear_selection=lambda: calls.append(("cleared",)),
                sheet=SimpleNamespace(open_cell=lambda: calls.append(("open_cell",))),
            ),
            root=None,
            _right_click_bulk_context=None,
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="3"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:5], [("8", "pack_size", "3"), ("refresh", ("8",)), ("cleared",), ("summary",), ("status",)])
        self.assertNotIn(("open_cell",), calls)

    def test_bulk_begin_edit_prefers_right_click_context(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "",
                current_editable_column_name=lambda: "",
                selected_target_row_ids=lambda col_name: (),
                selected_row_ids=lambda: (),
                current_cell_value=lambda: "2",
                clear_selection=lambda: calls.append(("cleared",)),
                sheet=SimpleNamespace(open_cell=lambda: calls.append(("open_cell",))),
            ),
            root=None,
            _right_click_bulk_context={"row_id": "8", "col_name": "pack_size"},
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="3"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:5], [("8", "pack_size", "3"), ("refresh", ("8",)), ("cleared",), ("summary",), ("status",)])

    def test_bulk_begin_edit_right_click_context_overrides_existing_selection(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("0", "1", "2"),
                selected_row_ids=lambda: ("0", "1", "2"),
                current_cell_value=lambda: "2",
                clear_selection=lambda: calls.append(("cleared",)),
                sheet=SimpleNamespace(open_cell=lambda: calls.append(("open_cell",))),
            ),
            root=None,
            _right_click_bulk_context={"row_id": "5", "col_name": "pack_size"},
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="5"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:5], [("5", "pack_size", "5"), ("refresh", ("5",)), ("cleared",), ("summary",), ("status",)])

    def test_bulk_begin_edit_right_click_within_selection_keeps_selected_rows(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("2", "3", "4"),
                selected_row_ids=lambda: ("2", "3", "4"),
                current_cell_value=lambda: "2",
                clear_selection=lambda: calls.append(("cleared",)),
                sheet=SimpleNamespace(open_cell=lambda: calls.append(("open_cell",))),
            ),
            root=None,
            _right_click_bulk_context={"row_id": "3", "col_name": "pack_size"},
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="5"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(
            calls[:7],
            [("2", "pack_size", "5"), ("3", "pack_size", "5"), ("4", "pack_size", "5"), ("refresh", ("2", "3", "4")), ("cleared",), ("summary",), ("status",)],
        )

    def test_bulk_begin_edit_uses_new_selection_after_right_click_context_is_cleared(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("2",),
                selected_row_ids=lambda: ("2",),
                current_cell_value=lambda: "2",
                clear_selection=lambda: calls.append(("cleared",)),
            ),
            root=None,
            _right_click_bulk_context=None,
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="5"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:5], [("2", "pack_size", "5"), ("refresh", ("2",)), ("cleared",), ("summary",), ("status",)])

    def test_bulk_begin_edit_right_click_buy_rule_opens_editor(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "",
                current_editable_column_name=lambda: "",
                selected_target_row_ids=lambda col_name: (),
                selected_row_ids=lambda: (),
                current_cell_value=lambda: "",
                sheet=SimpleNamespace(open_cell=lambda: calls.append(("open_cell",))),
            ),
            root=None,
            _right_click_bulk_context={"row_id": "7", "col_name": "buy_rule"},
            _open_buy_rule_editor=lambda idx: calls.append(("buy_rule_editor", idx)),
        )

        result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls, [("buy_rule_editor", 7)])

    def test_bulk_select_all_uses_sheet_helper(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(select_all_visible=lambda: calls.append("select_all") or True),
        )

        result = po_builder.POBuilderApp._bulk_select_all(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls, ["select_all"])

    def test_bulk_clear_selection_clears_sheet_and_context(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(clear_selection=lambda: calls.append("cleared")),
            _right_click_bulk_context={"row_id": "8", "col_name": "pack_size"},
        )

        result = po_builder.POBuilderApp._bulk_clear_selection(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(fake_app._right_click_bulk_context, None)
        self.assertEqual(calls, ["cleared"])

    def test_bulk_fill_down_uses_current_cell_value_for_selected_rows(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(
                selected_editable_column_name=lambda: "pack_size",
                current_editable_column_name=lambda: "pack_size",
                selected_target_row_ids=lambda col_name: ("0", "1"),
                current_cell_value=lambda: "500",
                clear_selection=lambda: calls.append(("cleared",)),
            ),
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )
        fake_app._bulk_fill_selection_with_current_value = (
            lambda event=None, alias="fill": po_builder.POBuilderApp._bulk_fill_selection_with_current_value(
                fake_app, event, alias=alias
            )
        )

        result = po_builder.POBuilderApp._bulk_fill_down_selection(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(
            calls,
            [("0", "pack_size", "500"), ("1", "pack_size", "500"), ("refresh", ("0", "1")), ("cleared",), ("summary",), ("status",)],
        )

    def test_bulk_apply_current_value_to_selection_reuses_fill_helper(self):
        calls = []
        fake_app = SimpleNamespace(
            _bulk_fill_selection_with_current_value=lambda event=None, alias="fill": calls.append(alias) or "break",
        )

        result = po_builder.POBuilderApp._bulk_apply_current_value_to_selection(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls, ["ctrl_enter"])

    def test_bulk_move_next_editable_cell_uses_sheet_helper(self):
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(move_current_editable_cell=lambda step: step == 1),
        )

        result = po_builder.POBuilderApp._bulk_move_next_editable_cell(fake_app)

        self.assertEqual(result, "break")

    def test_bulk_move_prev_editable_cell_uses_sheet_helper(self):
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(move_current_editable_cell=lambda step: step == -1),
        )

        result = po_builder.POBuilderApp._bulk_move_prev_editable_cell(fake_app)

        self.assertEqual(result, "break")

    def test_bulk_extend_selection_right_uses_sheet_helper(self):
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(extend_selection=lambda row_delta, col_delta: (row_delta, col_delta) == (0, 1)),
        )

        result = po_builder.POBuilderApp._bulk_extend_selection_right(fake_app)

        self.assertEqual(result, "break")

    def test_bulk_jump_ctrl_down_uses_sheet_helper(self):
        fake_app = SimpleNamespace(
            bulk_sheet=SimpleNamespace(jump_current_cell=lambda direction, ctrl=False: direction == "down" and ctrl),
        )

        result = po_builder.POBuilderApp._bulk_jump_ctrl_down(fake_app)

        self.assertEqual(result, "break")

    def test_bulk_undo_restores_previous_snapshot_and_queues_redo(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_undo_stack=[{"label": "edit:pack_size", "before": {"filtered_items": [{"item_code": "A"}]}, "after": {"filtered_items": [{"item_code": "B"}]}}],
            bulk_redo_stack=[],
            bulk_sheet=None,
            _capture_bulk_history_state=lambda: {"filtered_items": [{"item_code": "LIVE"}]},
            _restore_bulk_history_state=lambda state: calls.append(("restore", state)),
        )

        result = po_builder.POBuilderApp._bulk_undo(fake_app)

        self.assertIsNone(result)
        self.assertEqual(calls, [("restore", {"filtered_items": [{"item_code": "A"}]})])
        self.assertEqual(fake_app.bulk_undo_stack, [])
        self.assertEqual(fake_app.bulk_redo_stack[0]["after"], {"filtered_items": [{"item_code": "LIVE"}]})

    def test_bulk_redo_restores_after_snapshot_and_queues_undo(self):
        calls = []
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[{"label": "edit:pack_size", "before": {"filtered_items": [{"item_code": "A"}]}, "after": {"filtered_items": [{"item_code": "B"}]}}],
            bulk_sheet=None,
            _capture_bulk_history_state=lambda: {"filtered_items": [{"item_code": "LIVE"}]},
            _restore_bulk_history_state=lambda state: calls.append(("restore", state)),
        )

        result = po_builder.POBuilderApp._bulk_redo(fake_app)

        self.assertIsNone(result)
        self.assertEqual(calls, [("restore", {"filtered_items": [{"item_code": "B"}]})])
        self.assertEqual(fake_app.bulk_redo_stack, [])
        self.assertEqual(fake_app.bulk_undo_stack[0]["before"], {"filtered_items": [{"item_code": "LIVE"}]})

    def test_bulk_undo_flushes_pending_edit_before_restoring(self):
        """Undo must drain any queued async edit first so the after(1,...) callback
        cannot replay over the restored state."""
        calls = []
        fake_sheet = SimpleNamespace(flush_pending_edit=lambda: calls.append(("flush",)))
        fake_app = SimpleNamespace(
            bulk_undo_stack=[{"label": "edit:vendor", "before": {"filtered_items": []}, "after": {"filtered_items": []}}],
            bulk_redo_stack=[],
            bulk_sheet=fake_sheet,
            _capture_bulk_history_state=lambda: {"filtered_items": []},
            _restore_bulk_history_state=lambda state: calls.append(("restore",)),
        )

        po_builder.POBuilderApp._bulk_undo(fake_app)

        self.assertIn(("flush",), calls)
        self.assertTrue(calls.index(("flush",)) < calls.index(("restore",)))

    def test_bulk_redo_flushes_pending_edit_before_restoring(self):
        calls = []
        fake_sheet = SimpleNamespace(flush_pending_edit=lambda: calls.append(("flush",)))
        fake_app = SimpleNamespace(
            bulk_undo_stack=[],
            bulk_redo_stack=[{"label": "edit:vendor", "before": {"filtered_items": []}, "after": {"filtered_items": []}}],
            bulk_sheet=fake_sheet,
            _capture_bulk_history_state=lambda: {"filtered_items": []},
            _restore_bulk_history_state=lambda state: calls.append(("restore",)),
        )

        po_builder.POBuilderApp._bulk_redo(fake_app)

        self.assertIn(("flush",), calls)
        self.assertTrue(calls.index(("flush",)) < calls.index(("restore",)))


class BulkSheetViewTests(unittest.TestCase):
    def test_set_rows_clears_stale_right_click_context(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.labels = {"vendor": "Vendor", "pack_size": "Pack"}
        view.columns = ("vendor", "pack_size")
        view.app = SimpleNamespace(
            _right_click_bulk_context={"row_id": "7", "col_name": "vendor"},
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.sheet = SimpleNamespace(
            set_sheet_data=lambda rows, reset_col_positions=False, reset_row_positions=True: calls.append(("set_rows", rows)),
            headers=lambda headers, redraw=False: calls.append(("headers", tuple(headers))),
            display_rows=lambda value, redraw=True: calls.append(("display", value, redraw)),
        )

        view.set_rows([["A", "5"]], ["0"])

        self.assertIsNone(view.app._right_click_bulk_context)
        self.assertEqual(view.row_ids, ["0"])
        self.assertEqual(calls[-1], ("status",))

    def test_set_rows_skips_sheet_reset_when_rendered_rows_are_unchanged(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.labels = {"vendor": "Vendor", "pack_size": "Pack"}
        view.columns = ("vendor", "pack_size")
        view._rendered_row_ids = ("0",)
        view._rendered_rows = (("A", "5"),)
        view.app = SimpleNamespace(
            _right_click_bulk_context=None,
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.sheet = SimpleNamespace(
            set_sheet_data=lambda *args, **kwargs: calls.append(("set_rows",)),
            headers=lambda *args, **kwargs: calls.append(("headers",)),
            display_rows=lambda *args, **kwargs: calls.append(("display",)),
        )

        result = view.set_rows([["A", "5"]], ["0"])

        self.assertFalse(result)
        self.assertEqual(view.row_ids, ["0"])
        self.assertEqual(view.row_lookup, {"0": 0})
        self.assertEqual(calls, [("status",)])

    def test_set_rows_bumps_selection_serial_on_data_change(self):
        """A data-changing set_rows call must increment _selection_serial so
        history entries queued before the refresh cannot coalesce with entries
        queued after it."""
        view = BulkSheetView.__new__(BulkSheetView)
        view.labels = {"vendor": "Vendor", "pack_size": "Pack"}
        view.columns = ("vendor", "pack_size")
        view._rendered_row_ids = ()
        view._rendered_rows = ()
        view._selection_serial = 3
        view.app = SimpleNamespace(
            _right_click_bulk_context=None,
            _update_bulk_sheet_status=lambda: None,
        )
        view.sheet = SimpleNamespace(
            set_sheet_data=lambda *args, **kwargs: None,
            headers=lambda *args, **kwargs: None,
            display_rows=lambda *args, **kwargs: None,
        )

        result = view.set_rows([["VENDOR", "5"]], ["0"])

        self.assertTrue(result)
        self.assertGreater(view._selection_serial, 3)

    def test_set_rows_does_not_bump_selection_serial_when_rows_unchanged(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.labels = {"vendor": "Vendor", "pack_size": "Pack"}
        view.columns = ("vendor", "pack_size")
        view._rendered_row_ids = ("0",)
        view._rendered_rows = (("VENDOR", "5"),)
        view._selection_serial = 3
        view.app = SimpleNamespace(
            _right_click_bulk_context=None,
            _update_bulk_sheet_status=lambda: None,
        )
        view.sheet = SimpleNamespace()

        result = view.set_rows([["VENDOR", "5"]], ["0"])

        self.assertFalse(result)
        self.assertEqual(view._selection_serial, 3)

    def test_clear_selection_flushes_pending_edit_before_deselecting(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view._pending_edit = {"row_id": "4", "col_name": "vendor"}
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(deselect=lambda *args, **kwargs: calls.append(("deselect",)))

        view.clear_selection()

        self.assertEqual(calls[:2], [("flush",), ("deselect",)])

    def test_select_all_visible_flushes_pending_edit_before_selecting_rows(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8]
        view._pending_edit = {"row_id": "4", "col_name": "vendor"}
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        view.current_cell = lambda: (None, None)
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            select_row=lambda row, redraw=False: calls.append(("row", row, redraw)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.select_all_visible()

        self.assertTrue(result)
        self.assertEqual(calls[:2], [("flush",), ("deselect",)])

    def test_handle_select_clears_stale_right_click_context(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.app = SimpleNamespace(
            _right_click_bulk_context={"row_id": "7", "col_name": "vendor"},
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view._remember_selection = lambda: calls.append(("remember",))

        view._handle_select({})

        self.assertIsNone(view.app._right_click_bulk_context)
        self.assertEqual(calls, [("remember",), ("status",)])

    def test_handle_select_flushes_pending_edit_before_remembering_new_selection(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.app = SimpleNamespace(
            _right_click_bulk_context=None,
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view._pending_edit = {"row_id": "4", "col_name": "vendor"}
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view._remember_selection = lambda: calls.append(("remember",))

        view._handle_select({})

        self.assertEqual(calls, [("flush",), ("remember",), ("status",)])

    def test_handle_right_click_flushes_pending_edit_before_moving_context(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = ["4", "8"]
        view.columns = ("vendor", "pack_size")
        view._pending_edit = {"row_id": "4", "col_name": "vendor"}
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(
            _right_click_bulk_context=None,
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.context_menu = SimpleNamespace(
            tk_popup=lambda x, y: calls.append(("popup", x, y)),
            grab_release=lambda: calls.append(("release",)),
        )
        view.sheet = SimpleNamespace(
            identify_row=lambda event, exclude_index=True, allow_end=False: 1,
            identify_column=lambda event, exclude_header=True, allow_end=False: 0,
            get_selected_rows=lambda: set(),
            get_selected_cells=lambda: [],
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
        )

        event = SimpleNamespace(x_root=10, y_root=20)
        result = view.handle_right_click(event)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:3], [("flush",), ("current", 1, 0), ("remember",)])

    def test_handle_edit_applies_value_to_selected_target_rows(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8]
        view.columns = ("vendor", "pack_size", "why")
        view.editable_cols = {"vendor", "pack_size"}
        view._selection_snapshot = {"cells": ((0, 1), (1, 1)), "rows": (), "columns": (), "current": (0, 1)}
        view.col_index = {"vendor": 0, "pack_size": 1, "why": 2}
        view._edit_refresh_after_id = None
        view._pending_edit = None
        view._selection_serial = 0
        view.selected_target_row_ids = lambda col_name: ("4",)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))) or True,
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))
        view.sheet = SimpleNamespace(
            get_cell_data=lambda row, col: "500",
            after=lambda delay, callback: (calls.append(("after", delay)), callback(), "after-id")[2],
            after_cancel=lambda after_id: calls.append(("cancel", after_id)),
        )

        view._handle_edit({"row": 0, "column": 1, "value": "500"})

        self.assertEqual(
            calls[:7],
            [
                ("after", 1),
                ("4", "pack_size", "500"),
                ("8", "pack_size", "500"),
                ("refresh", ("4", "8")),
                ("cleared",),
                ("summary",),
                ("status",),
            ],
        )

    def test_handle_edit_drains_older_pending_edit_before_queueing_new_one(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8]
        view.columns = ("vendor", "pack_size", "why")
        view.editable_cols = {"vendor", "pack_size"}
        view._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (1, 1)}
        view.col_index = {"vendor": 0, "pack_size": 1, "why": 2}
        view._selection_serial = 1
        view._edit_refresh_after_id = "old-after"
        view._pending_edit = {
            "row": 0,
            "col": 0,
            "row_id": "4",
            "col_name": "vendor",
            "editable": True,
            "target_row_ids": ("4",),
            "committed_value": "OLDV",
            "selection_serial": 0,
        }
        view.selected_target_row_ids = lambda col_name: ("8",)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))) or True,
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))
        view.sheet = SimpleNamespace(
            get_cell_data=lambda row, col: "VALUE",
            after=lambda delay, callback: (calls.append(("after", delay)), "new-after")[1],
            after_cancel=lambda after_id: calls.append(("cancel", after_id)),
        )

        view._handle_edit({"row": 1, "column": 1, "value": "12"})

        self.assertEqual(
            calls[:6],
            [
                ("cancel", "old-after"),
                ("4", "vendor", "OLDV"),
                ("refresh", ("4",)),
                ("summary",),
                ("status",),
                ("after", 1),
            ],
        )
        self.assertEqual(view._pending_edit["row_id"], "8")
        self.assertEqual(view._pending_edit["col_name"], "pack_size")
        self.assertEqual(view._pending_edit["committed_value"], "12")

    def test_run_post_edit_refresh_keeps_newer_selection_intact(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8]
        view.columns = ("vendor", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view._selection_serial = 2
        view._edit_refresh_after_id = None
        view._pending_edit = {
            "row": 0,
            "col": 0,
            "row_id": "4",
            "col_name": "vendor",
            "editable": True,
            "target_row_ids": ("4",),
            "committed_value": "ABC",
            "selection_serial": 1,
        }
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))) or True,
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
            _bulk_row_values=lambda item: ["row"],
            filtered_items=[{"item_code": "A"}, {"item_code": "B"}],
        )
        view.clear_selection = lambda: calls.append(("cleared",))
        view.sheet = SimpleNamespace(get_cell_data=lambda row, col: "ABC")

        view._run_post_edit_refresh()

        self.assertEqual(
            calls[:4],
            [("4", "vendor", "ABC"), ("refresh", ("4",)), ("summary",), ("status",)],
        )
        self.assertNotIn(("cleared",), calls)

    def test_run_post_edit_refresh_ignores_stale_scheduled_generation(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8]
        view.columns = ("vendor", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view._selection_serial = 1
        view._edit_refresh_after_id = "new-after"
        view._scheduled_edit_generation = 2
        view._pending_edit = {
            "row": 1,
            "col": 1,
            "row_id": "8",
            "col_name": "pack_size",
            "editable": True,
            "target_row_ids": ("8",),
            "committed_value": "12",
            "selection_serial": 1,
            "generation": 2,
        }
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))) or True,
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))
        view.sheet = SimpleNamespace(get_cell_data=lambda row, col: "12")

        result = view._run_post_edit_refresh(1)

        self.assertFalse(result)
        self.assertEqual(calls, [])
        self.assertEqual(view._pending_edit["row_id"], "8")
        self.assertEqual(view._scheduled_edit_generation, 2)

    def test_queued_stale_callback_does_not_commit_newer_pending_edit(self):
        calls = []
        scheduled = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8]
        view.columns = ("vendor", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (0, 0)}
        view.col_index = {"vendor": 0, "pack_size": 1}
        view._selection_serial = 1
        view._edit_refresh_after_id = None
        view._pending_edit = None
        view._pending_edit_generation = 0
        view._scheduled_edit_generation = None
        view.selected_target_row_ids = lambda col_name: ("4", "8")
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids, changed_cols=None: calls.append(("refresh", tuple(row_ids))) or True,
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))

        def after(delay, callback):
            after_id = f"after-{len(scheduled) + 1}"
            scheduled.append((after_id, callback))
            calls.append(("after", delay, after_id))
            return after_id

        view.sheet = SimpleNamespace(
            get_cell_data=lambda row, col: "value",
            after=after,
            after_cancel=lambda after_id: calls.append(("cancel", after_id)),
        )

        view._handle_edit({"row": 0, "column": 0, "value": "OLDV"})
        view._pending_edit = {
            "row": 1,
            "col": 1,
            "row_id": "8",
            "col_name": "pack_size",
            "editable": True,
            "target_row_ids": ("4", "8"),
            "committed_value": "12",
            "selection_serial": 1,
            "generation": 2,
        }
        view._scheduled_edit_generation = 2
        view._edit_refresh_after_id = "after-2"

        scheduled[0][1]()

        self.assertEqual(calls, [("after", 1, "after-1")])
        self.assertEqual(view._pending_edit["row_id"], "8")
        self.assertEqual(view._pending_edit["col_name"], "pack_size")

        view._run_post_edit_refresh(2)

        self.assertEqual(
            calls,
            [
                ("after", 1, "after-1"),
                ("4", "pack_size", "12"),
                ("8", "pack_size", "12"),
                ("refresh", ("4", "8")),
                ("cleared",),
                ("summary",),
                ("status",),
            ],
        )
        self.assertIsNone(view._pending_edit)

    def test_run_post_edit_refresh_coalesces_matching_sheet_edit_history(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8]
        view.columns = ("vendor", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view._selection_serial = 4
        view._edit_refresh_after_id = None
        view._scheduled_edit_generation = 2
        view._pending_edit = {
            "row": 0,
            "col": 1,
            "row_id": "4",
            "col_name": "pack_size",
            "editable": True,
            "target_row_ids": ("4", "8"),
            "committed_value": "12",
            "selection_serial": 4,
            "generation": 2,
        }
        view.app = SimpleNamespace(
            _capture_bulk_history_state=lambda: {"before": True},
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids, changed_cols=None: calls.append(("refresh", tuple(row_ids), changed_cols)) or True,
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))
        view.sheet = SimpleNamespace(get_cell_data=lambda row, col: "12")

        view._run_post_edit_refresh(2)

        self.assertEqual(
            calls,
            [
                ("4", "pack_size", "12"),
                ("8", "pack_size", "12"),
                ("refresh", ("4", "8"), ("pack_size",)),
                ("cleared",),
                ("summary",),
                ("status",),
                (
                    "sheet_edit:pack_size",
                    {"before": True},
                    {
                        "kind": "sheet_edit",
                        "col_name": "pack_size",
                        "row_ids": ("4", "8"),
                        "selection_serial": 4,
                    },
                ),
            ],
        )

    def test_select_all_visible_selects_all_rows_and_updates_status(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8, 12]
        view._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        view.current_cell = lambda: (None, None)
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            select_row=lambda row, redraw=False: calls.append(("row", row, redraw)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.select_all_visible()

        self.assertTrue(result)
        self.assertEqual(
            calls,
            [("deselect",), ("row", 0, False), ("row", 1, False), ("row", 2, False), ("current", 0, 0), ("remember",), ("refresh",), ("redraw",), ("status",)],
        )

    def test_move_current_editable_cell_advances_with_wrap(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "line_code", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view.row_ids = [4, 8]
        view.current_cell = lambda: (0, 2)
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.move_current_editable_cell(1)

        self.assertTrue(result)
        self.assertEqual(calls, [("deselect",), ("current", 1, 0), ("remember",), ("refresh",), ("redraw",), ("status",)])

    def test_move_current_editable_cell_goes_back_to_previous_row(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "line_code", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view.row_ids = [4, 8]
        view.current_cell = lambda: (1, 0)
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.move_current_editable_cell(-1)

        self.assertTrue(result)
        self.assertEqual(calls, [("deselect",), ("current", 0, 2), ("remember",), ("refresh",), ("redraw",), ("status",)])

    def test_extend_selection_builds_rectangular_range_from_anchor(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.row_ids = [4, 8, 12]
        view._selection_anchor = (0, 0)
        view.current_cell = lambda: (0, 0)
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            select_cell=lambda row, col, redraw=False: calls.append(("select", row, col, redraw)),
            add_cell_selection=lambda row, col, redraw=False, set_as_current=False: calls.append(("add", row, col, redraw, set_as_current)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.extend_selection(1, 1)

        self.assertTrue(result)
        self.assertEqual(
            calls,
            [
                ("deselect",),
                ("select", 0, 0, False),
                ("add", 0, 1, False, False),
                ("add", 1, 0, False, False),
                ("add", 1, 1, False, False),
                ("current", 1, 1),
                ("refresh",),
                ("redraw",),
                ("status",),
            ],
        )
        self.assertEqual(view._selection_snapshot["current"], (1, 1))

    def test_jump_current_cell_end_moves_to_last_editable_column(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "line_code", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view.row_ids = [4, 8, 12]
        view.current_cell = lambda: (1, 0)
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.jump_current_cell("end", ctrl=False)

        self.assertTrue(result)
        self.assertEqual(calls, [("deselect",), ("current", 1, 2), ("remember",), ("refresh",), ("redraw",), ("status",)])

    def test_jump_current_cell_ctrl_up_moves_to_first_row(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view.row_ids = [4, 8, 12]
        view.current_cell = lambda: (2, 1)
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.jump_current_cell("up", ctrl=True)

        self.assertTrue(result)
        self.assertEqual(calls, [("deselect",), ("current", 0, 1), ("remember",), ("refresh",), ("redraw",), ("status",)])

    def test_close_open_text_editor_commits_editor(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.sheet = SimpleNamespace(
            MT=SimpleNamespace(
                text_editor=SimpleNamespace(open=True),
                close_text_editor=lambda event: calls.append(event.keysym),
            )
        )

        result = view._close_open_text_editor(keysym="Commit")

        self.assertTrue(result)
        self.assertEqual(calls, ["Commit"])

    def test_commit_editor_and_move_uses_jump_for_arrow_keys(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view._close_open_text_editor = lambda keysym="Commit": calls.append(("close", keysym)) or True
        view._flush_pending_before_navigation = lambda: calls.append(("flush_pending",))
        view.jump_current_cell = lambda direction, ctrl=False: calls.append(("jump", direction, ctrl)) or True

        result = view.commit_editor_and_move("down")

        self.assertEqual(result, "break")
        self.assertEqual(calls, [("close", "Commit"), ("flush_pending",), ("jump", "down", False)])

    def test_commit_editor_and_move_uses_editable_navigation_for_tab(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view._close_open_text_editor = lambda keysym="Commit": calls.append(("close", keysym)) or True
        view._flush_pending_before_navigation = lambda: calls.append(("flush_pending",))
        view.move_current_editable_cell = lambda step: calls.append(("move", step)) or True

        result = view.commit_editor_and_move("next")

        self.assertEqual(result, "break")
        self.assertEqual(calls, [("close", "Commit"), ("flush_pending",), ("move", 1)])

    def test_move_current_editable_cell_flushes_pending_edit_before_navigation(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "line_code", "pack_size")
        view.editable_cols = {"vendor", "pack_size"}
        view.row_ids = [4, 8]
        view.current_cell = lambda: (0, 2)
        view._pending_edit = {"row_id": "4", "col_name": "pack_size"}
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view._remember_selection = lambda: calls.append(("remember",))
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.move_current_editable_cell(1)

        self.assertTrue(result)
        self.assertEqual(calls[0], ("flush",))
        self.assertEqual(calls[1:], [("deselect",), ("current", 1, 0), ("remember",), ("refresh",), ("redraw",), ("status",)])

    def test_extend_selection_flushes_pending_edit_before_selection_change(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.row_ids = [4, 8, 12]
        view._pending_edit = {"row_id": "4", "col_name": "vendor"}
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view._selection_anchor = (0, 0)
        view.current_cell = lambda: (0, 0)
        view.app = SimpleNamespace(_update_bulk_sheet_status=lambda: calls.append(("status",)))
        view.sheet = SimpleNamespace(
            deselect=lambda *args, **kwargs: calls.append(("deselect",)),
            select_cell=lambda row, col, redraw=False: calls.append(("select", row, col, redraw)),
            add_cell_selection=lambda row, col, redraw=False, set_as_current=False: calls.append(("add", row, col, redraw, set_as_current)),
            set_currently_selected=lambda row, column: calls.append(("current", row, column)),
            refresh=lambda: calls.append(("refresh",)),
            redraw=lambda: calls.append(("redraw",)),
        )

        result = view.extend_selection(1, 1)

        self.assertTrue(result)
        self.assertEqual(calls[0], ("flush",))

    def test_snapshot_target_row_ids_prefers_pre_edit_selection(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [4, 8, 12]
        view.col_index = {"vendor": 0, "pack_size": 1, "why": 2}
        view._selection_snapshot = {"cells": ((0, 1), (2, 1)), "rows": (), "columns": (), "current": (0, 1)}
        view.selected_target_row_ids = lambda col_name: ("4",)

        self.assertEqual(view._snapshot_target_row_ids("pack_size"), ("4", "12"))

    def test_current_editable_column_name_ignores_readonly_columns(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.editable_cols = {"vendor", "pack_size"}
        view.current_column_name = lambda: "why"

        self.assertEqual(view.current_editable_column_name(), "")

    def test_selected_editable_column_name_returns_single_selected_column(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.editable_cols = {"vendor", "pack_size"}
        view.sheet = SimpleNamespace(get_selected_cells=lambda: [(0, 1), (2, 1)])
        view.current_column_name = lambda: ""
        view.current_editable_column_name = lambda: ""

        self.assertEqual(view.selected_editable_column_name(), "pack_size")

    def test_selected_editable_column_name_returns_blank_for_mixed_columns(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.sheet = SimpleNamespace(get_selected_cells=lambda: [(0, 1), (2, 2)])
        view.current_column_name = lambda: ""
        view.current_editable_column_name = lambda: ""
        view.editable_cols = {"vendor", "pack_size"}

        self.assertEqual(view.selected_editable_column_name(), "")

    def test_selected_editable_column_name_uses_explicit_selected_column(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.editable_cols = {"vendor", "pack_size"}
        view.sheet = SimpleNamespace(get_selected_cells=lambda: [], get_selected_columns=lambda: {1})
        view.current_editable_column_name = lambda: ""

        self.assertEqual(view.selected_editable_column_name(), "pack_size")

    def test_selected_target_row_ids_prefers_cells_in_active_column(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.col_index = {"vendor": 0, "pack_size": 1, "why": 2}
        view.row_ids = [4, 8, 12]
        view.explicit_selected_row_ids = lambda: ()
        view.selected_cells = lambda: [(0, 1), (1, 1), (2, 2)]
        view.selected_row_ids = lambda: ("4", "8", "12")

        self.assertEqual(view.selected_target_row_ids("pack_size"), ("4", "8"))

    def test_snapshot_row_ids_derives_rows_from_cells_when_rows_empty(self):
        """snapshot_row_ids must fall back to cell-selection rows.
        Normal shift-click / drag populates snapshot['cells'], not snapshot['rows'].
        Before this fix, snapshot_row_ids() returned () and remove/ignore fell back
        to the single right-clicked row."""
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [10, 20, 30]
        view._selection_snapshot = {
            "cells": ((0, 1), (1, 0), (2, 1)),
            "rows": (),
            "columns": (),
            "current": (0, 1),
        }

        self.assertEqual(view.snapshot_row_ids(), ("10", "20", "30"))

    def test_snapshot_row_ids_prefers_rows_over_cells(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [10, 20, 30]
        view._selection_snapshot = {
            "cells": ((0, 1), (2, 1)),
            "rows": (1,),
            "columns": (),
            "current": (1, 1),
        }

        self.assertEqual(view.snapshot_row_ids(), ("20",))

    def test_snapshot_row_ids_returns_empty_when_snapshot_missing(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = [10, 20]

        self.assertEqual(view.snapshot_row_ids(), ())

    def test_handle_right_click_keeps_cell_selection_when_row_is_already_selected(self):
        """handle_right_click must NOT call set_currently_selected when the
        right-clicked row is already part of a cell-based (non-row-header) selection.
        Before this fix, get_selected_rows() returned {} for cell selections, so the
        condition was always True and the selection was clobbered."""
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = ["r0", "r1", "r2"]
        view.columns = ("vendor", "pack_size")
        view._pending_edit = None
        view._flush_pending_before_navigation = lambda: None
        view._remember_selection = lambda: calls.append("remember")
        view.app = SimpleNamespace(
            _right_click_bulk_context=None,
            _update_bulk_sheet_status=lambda: calls.append("status"),
        )
        view.context_menu = SimpleNamespace(
            tk_popup=lambda x, y: calls.append(("popup",)),
            grab_release=lambda: None,
        )
        # Row 1 selected via cells (not row-header) — get_selected_rows returns {}
        view.sheet = SimpleNamespace(
            identify_row=lambda event, exclude_index=True, allow_end=False: 1,
            identify_column=lambda event, exclude_header=True, allow_end=False: 0,
            get_selected_rows=lambda: set(),
            get_selected_cells=lambda: [(0, 0), (1, 0), (2, 0)],
            set_currently_selected=lambda row, column: calls.append(("set_selected", row, column)),
        )

        view.handle_right_click(SimpleNamespace(x_root=5, y_root=5))

        # set_currently_selected must NOT have been called because row 1 was already selected
        self.assertNotIn(("set_selected", 1, 0), calls)

    def test_handle_right_click_moves_focus_when_row_not_in_cell_selection(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.row_ids = ["r0", "r1", "r2"]
        view.columns = ("vendor", "pack_size")
        view._pending_edit = None
        view._flush_pending_before_navigation = lambda: None
        view._remember_selection = lambda: calls.append("remember")
        view.app = SimpleNamespace(
            _right_click_bulk_context=None,
            _update_bulk_sheet_status=lambda: None,
        )
        view.context_menu = SimpleNamespace(
            tk_popup=lambda x, y: None,
            grab_release=lambda: None,
        )
        # Row 2 clicked, but only rows 0 and 1 are in cells
        view.sheet = SimpleNamespace(
            identify_row=lambda event, exclude_index=True, allow_end=False: 2,
            identify_column=lambda event, exclude_header=True, allow_end=False: 0,
            get_selected_rows=lambda: set(),
            get_selected_cells=lambda: [(0, 0), (1, 0)],
            set_currently_selected=lambda row, column: calls.append(("set_selected", row, column)),
        )

        view.handle_right_click(SimpleNamespace(x_root=5, y_root=5))

        self.assertIn(("set_selected", 2, 0), calls)

    def test_selected_target_row_ids_falls_back_to_selected_rows(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.col_index = {"vendor": 0, "pack_size": 1, "why": 2}
        view.row_ids = [4, 8, 12]
        view.explicit_selected_row_ids = lambda: ()
        view.selected_cells = lambda: [(2, 2)]
        view.selected_row_ids = lambda: ("4", "8")

        self.assertEqual(view.selected_target_row_ids("pack_size"), ("4", "8"))

    def test_selected_target_row_ids_prefers_explicit_row_selection(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.col_index = {"vendor": 0, "pack_size": 1, "why": 2}
        view.row_ids = [4, 8, 12]
        view.explicit_selected_row_ids = lambda: ("8", "12")
        view.selected_cells = lambda: [(0, 1)]
        view.selected_row_ids = lambda: ("4", "8", "12")

        self.assertEqual(view.selected_target_row_ids("pack_size"), ("8", "12"))

    def test_selected_column_names_includes_explicit_columns(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.sheet = SimpleNamespace(get_selected_columns=lambda: {1})
        view.selected_cells = lambda: []

        self.assertEqual(view.selected_column_names(), ("pack_size",))

    def test_fit_columns_to_window_scales_widths(self):
        recorded = {}
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "description", "why")
        view.col_index = {"vendor": 0, "description": 1, "why": 2}
        view.base_widths = {"vendor": 80, "description": 150, "why": 180}
        view.sheet = SimpleNamespace(
            get_column_text_width=lambda idx, visible_only=True: [60, 220, 140][idx],
            set_column_widths=lambda widths: recorded.setdefault("widths", list(widths)),
            refresh=lambda: recorded.setdefault("refresh", True),
            redraw=lambda: recorded.setdefault("redraw", True),
        )

        result = view.fit_columns_to_window(available_width=500)

        self.assertTrue(result)
        self.assertIn("widths", recorded)
        self.assertLessEqual(sum(recorded["widths"]), 500)
        self.assertGreaterEqual(recorded["widths"][1], recorded["widths"][0])

    def test_fit_columns_to_window_does_not_expand_columns_just_to_fill_space(self):
        recorded = {}
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "description", "why")
        view.col_index = {"vendor": 0, "description": 1, "why": 2}
        view.base_widths = {"vendor": 80, "description": 150, "why": 180}
        view.sheet = SimpleNamespace(
            get_column_text_width=lambda idx, visible_only=True: [40, 90, 70][idx],
            set_column_widths=lambda widths: recorded.setdefault("widths", list(widths)),
            refresh=lambda: recorded.setdefault("refresh", True),
            redraw=lambda: recorded.setdefault("redraw", True),
        )

        result = view.fit_columns_to_window(available_width=700)

        self.assertTrue(result)
        self.assertEqual(recorded["widths"], [52, 98, 260])

    def test_fit_columns_to_window_uses_compact_numeric_widths_and_wider_why(self):
        recorded = {}
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("raw_need", "suggested_qty", "final_qty", "why")
        view.col_index = {"raw_need": 0, "suggested_qty": 1, "final_qty": 2, "why": 3}
        view.base_widths = {"raw_need": 44, "suggested_qty": 54, "final_qty": 64, "why": 180}
        view.sheet = SimpleNamespace(
            get_column_text_width=lambda idx, visible_only=True: [90, 96, 88, 120][idx],
            set_column_widths=lambda widths: recorded.setdefault("widths", list(widths)),
            refresh=lambda: recorded.setdefault("refresh", True),
            redraw=lambda: recorded.setdefault("redraw", True),
        )

        result = view.fit_columns_to_window(available_width=900)

        self.assertTrue(result)
        self.assertEqual(recorded["widths"], [98, 104, 96, 260])

    def test_split_clipboard_matrix_handles_windows_newlines(self):
        self.assertEqual(
            BulkSheetView._split_clipboard_matrix("A\tB\r\n1\t2\r\n"),
            [["A", "B"], ["1", "2"]],
        )

    def test_paste_single_value_fills_selected_target_rows(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.editable_cols = {"pack_size"}
        view.row_ids = [4, 8]
        view.columns = ("vendor", "pack_size", "why")
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view.sheet = SimpleNamespace(clipboard_get=lambda: "500")
        view.selected_editable_column_name = lambda: "pack_size"
        view.current_editable_column_name = lambda: "pack_size"
        view.selected_target_row_ids = lambda col_name: ("4", "8")
        view.current_cell = lambda: (0, 1)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))) or True,
            _apply_bulk_filter=lambda: calls.append(("filter",)),
            _capture_bulk_history_state=lambda: {"before": True},
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))

        result = view.paste_from_clipboard()

        self.assertTrue(result)
        self.assertEqual(
            calls,
            [
                ("flush",),
                ("4", "pack_size", "500"),
                ("8", "pack_size", "500"),
                ("refresh", ("4", "8")),
                ("cleared",),
                ("summary",),
                ("status",),
                ("paste:pack_size", {"before": True}, {"kind": "paste", "col_name": "pack_size", "row_ids": ("4", "8")}),
            ],
        )

    def test_paste_rectangular_block_starts_at_current_cell(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.editable_cols = {"vendor", "pack_size"}
        view.row_ids = [4, 8, 12]
        view.columns = ("vendor", "pack_size", "why")
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view.sheet = SimpleNamespace(clipboard_get=lambda: "ABC\t500\nDEF\t600")
        view.selected_editable_column_name = lambda: ""
        view.current_editable_column_name = lambda: "vendor"
        view.selected_target_row_ids = lambda col_name: ()
        view.current_cell = lambda: (1, 0)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))) or True,
            _apply_bulk_filter=lambda: calls.append(("filter",)),
            _capture_bulk_history_state=lambda: {"before": True},
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
            _finalize_bulk_history_action=lambda label, before, coalesce_key=None: calls.append((label, before, coalesce_key)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))

        result = view.paste_from_clipboard()

        self.assertTrue(result)
        self.assertEqual(
            calls,
            [
                ("flush",),
                ("8", "vendor", "ABC"),
                ("8", "pack_size", "500"),
                ("12", "vendor", "DEF"),
                ("12", "pack_size", "600"),
                ("refresh", ("8", "12")),
                ("cleared",),
                ("summary",),
                ("status",),
                ("paste:block", {"before": True}, {"kind": "paste_block", "col_name": "vendor", "row_ids": ("8", "12"), "scope": ("vendor", "pack_size")}),
            ],
        )

    def test_paste_falls_back_to_filter_when_incremental_refresh_is_unavailable(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.editable_cols = {"pack_size"}
        view.row_ids = [4]
        view.columns = ("vendor", "pack_size")
        view.flush_pending_edit = lambda: calls.append(("flush",))
        view.sheet = SimpleNamespace(clipboard_get=lambda: "9")
        view.selected_editable_column_name = lambda: "pack_size"
        view.current_editable_column_name = lambda: "pack_size"
        view.selected_target_row_ids = lambda col_name: ("4",)
        view.current_cell = lambda: (0, 1)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value, **kw: calls.append((row_id, col_name, value)),
            _refresh_bulk_view_after_edit=lambda row_ids: calls.append(("refresh", tuple(row_ids))) or False,
            _apply_bulk_filter=lambda: calls.append(("filter",)),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )
        view.clear_selection = lambda: calls.append(("cleared",))

        result = view.paste_from_clipboard()

        self.assertTrue(result)
        self.assertEqual(
            calls[:5],
            [("flush",), ("4", "pack_size", "9"), ("refresh", ("4",)), ("filter",), ("cleared",)],
        )


if __name__ == "__main__":
    unittest.main()
