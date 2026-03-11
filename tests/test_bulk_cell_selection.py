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
            _bulk_apply_editor_value=lambda row_id, col_name, value: calls.append((row_id, col_name, value)),
            _apply_bulk_filter=lambda: calls.append(("filter",)),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_cell_status=lambda: calls.append(("status",)),
        )

        with patch("po_builder.simpledialog.askstring", return_value="750"):
            result = po_builder.POBuilderApp._bulk_begin_edit(fake_app)

        self.assertEqual(result, "break")
        self.assertEqual(calls[:6], [("0", "pack_size", "750"), ("1", "pack_size", "750"), ("filter",), ("cleared",), ("summary",), ("status",)])


class BulkSheetViewTests(unittest.TestCase):
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
        view.selected_target_row_ids = lambda col_name: ("4",)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value: calls.append((row_id, col_name, value)),
            _apply_bulk_filter=lambda: calls.append(("filter",)),
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
                ("filter",),
                ("cleared",),
                ("summary",),
                ("status",),
            ],
        )

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
        view.sheet = SimpleNamespace(get_selected_cells=lambda: [(0, 1), (2, 1)])
        view.current_column_name = lambda: ""

        self.assertEqual(view.selected_editable_column_name(), "pack_size")

    def test_selected_editable_column_name_returns_blank_for_mixed_columns(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.sheet = SimpleNamespace(get_selected_cells=lambda: [(0, 1), (2, 2)])
        view.current_column_name = lambda: ""

        self.assertEqual(view.selected_editable_column_name(), "")

    def test_selected_target_row_ids_prefers_cells_in_active_column(self):
        view = BulkSheetView.__new__(BulkSheetView)
        view.columns = ("vendor", "pack_size", "why")
        view.col_index = {"vendor": 0, "pack_size": 1, "why": 2}
        view.row_ids = [4, 8, 12]
        view.explicit_selected_row_ids = lambda: ()
        view.selected_cells = lambda: [(0, 1), (1, 1), (2, 2)]
        view.selected_row_ids = lambda: ("4", "8", "12")

        self.assertEqual(view.selected_target_row_ids("pack_size"), ("4", "8"))

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
        view.sheet = SimpleNamespace(clipboard_get=lambda: "500")
        view.selected_editable_column_name = lambda: "pack_size"
        view.current_editable_column_name = lambda: "pack_size"
        view.selected_target_row_ids = lambda col_name: ("4", "8")
        view.current_cell = lambda: (0, 1)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value: calls.append((row_id, col_name, value)),
            _apply_bulk_filter=lambda: calls.append(("filter",)),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )

        result = view.paste_from_clipboard()

        self.assertTrue(result)
        self.assertEqual(calls[:2], [("4", "pack_size", "500"), ("8", "pack_size", "500")])

    def test_paste_rectangular_block_starts_at_current_cell(self):
        calls = []
        view = BulkSheetView.__new__(BulkSheetView)
        view.editable_cols = {"vendor", "pack_size"}
        view.row_ids = [4, 8, 12]
        view.columns = ("vendor", "pack_size", "why")
        view.sheet = SimpleNamespace(clipboard_get=lambda: "ABC\t500\nDEF\t600")
        view.selected_editable_column_name = lambda: ""
        view.current_editable_column_name = lambda: "vendor"
        view.selected_target_row_ids = lambda col_name: ()
        view.current_cell = lambda: (1, 0)
        view.app = SimpleNamespace(
            _bulk_apply_editor_value=lambda row_id, col_name, value: calls.append((row_id, col_name, value)),
            _apply_bulk_filter=lambda: calls.append(("filter",)),
            _update_bulk_summary=lambda: calls.append(("summary",)),
            _update_bulk_sheet_status=lambda: calls.append(("status",)),
        )

        result = view.paste_from_clipboard()

        self.assertTrue(result)
        self.assertEqual(
            calls[:4],
            [
                ("8", "vendor", "ABC"),
                ("8", "pack_size", "500"),
                ("12", "vendor", "DEF"),
                ("12", "pack_size", "600"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
