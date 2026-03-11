try:
    from tksheet import Sheet
    HAS_TKSHEET = True
    TKSHEET_IMPORT_ERROR = None
except ImportError as exc:
    Sheet = None
    HAS_TKSHEET = False
    TKSHEET_IMPORT_ERROR = exc


class BulkSheetView:
    def __init__(self, app, parent, columns, labels, widths, editable_cols):
        if not HAS_TKSHEET:
            raise RuntimeError("tksheet is not installed") from TKSHEET_IMPORT_ERROR
        self.app = app
        self.columns = tuple(columns)
        self.labels = dict(labels)
        self.editable_cols = set(editable_cols)
        self.col_index = {name: idx for idx, name in enumerate(self.columns)}
        self.base_widths = {name: int(widths.get(name, 100)) for name in self.columns}
        self.row_ids = []
        self.row_lookup = {}
        self._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        self._resize_after_id = None
        self._edit_refresh_after_id = None
        self._pending_edit = None

        headers = [self.labels[col] for col in self.columns]
        self.sheet = Sheet(
            parent,
            headers=headers,
            show_row_index=False,
            show_top_left=False,
            theme="dark blue",
            default_column_width=100,
            auto_resize_columns=None,
            edit_cell_tab="right",
            edit_cell_return="down",
        )
        self.sheet.enable_bindings("all")
        self.sheet.pack(fill="both", expand=True)

        for col_name, width in widths.items():
            if col_name in self.col_index:
                self.sheet.column_width(self.col_index[col_name], width)

        readonly_cols = [self.col_index[name] for name in self.columns if name not in self.editable_cols]
        if readonly_cols:
            self.sheet.readonly_columns(readonly_cols, readonly=True)

        for binding in (
            "cell_select",
            "row_select",
            "column_select",
            "ctrl_cell_select",
            "ctrl_row_select",
            "shift_cell_select",
            "shift_row_select",
        ):
            self.sheet.extra_bindings(binding, self._handle_select)
        self.sheet.extra_bindings("end_edit_table", self._handle_edit)

    @staticmethod
    def _split_clipboard_matrix(text):
        if text is None:
            return []
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        if normalized == "":
            return []
        return [row.split("\t") for row in normalized.split("\n")]

    def _handle_select(self, event_data):
        self._remember_selection()
        self.app._update_bulk_sheet_status()

    def _handle_edit(self, event_data):
        row = event_data.get("row")
        col = event_data.get("column")
        if row is None or col is None or row >= len(self.row_ids) or col >= len(self.columns):
            return
        row_id = str(self.row_ids[row])
        col_name = self.columns[col]
        if col_name not in self.editable_cols:
            self._pending_edit = {
                "row": row,
                "col": col,
                "row_id": row_id,
                "col_name": col_name,
                "editable": False,
                "target_row_ids": (),
                "fallback_value": event_data.get("value", ""),
            }
            self._queue_post_edit_refresh()
            return
        target_row_ids = list(self._snapshot_target_row_ids(col_name))
        if row_id not in target_row_ids:
            target_row_ids = [row_id]
        self._pending_edit = {
            "row": row,
            "col": col,
            "row_id": row_id,
            "col_name": col_name,
            "editable": True,
            "target_row_ids": tuple(target_row_ids),
            "fallback_value": event_data.get("value", ""),
        }
        self._queue_post_edit_refresh()

    def _run_post_edit_refresh(self):
        self._edit_refresh_after_id = None
        pending = self._pending_edit
        self._pending_edit = None
        if pending:
            row = pending.get("row")
            col = pending.get("col")
            row_id = pending.get("row_id")
            col_name = pending.get("col_name")
            try:
                value = self.sheet.get_cell_data(row, col)
            except Exception:
                value = pending.get("fallback_value", "")
            if value is None:
                value = pending.get("fallback_value", "")
            value = str(value)
            if pending.get("editable"):
                for target_row_id in pending.get("target_row_ids", ()):
                    self.app._bulk_apply_editor_value(target_row_id, col_name, value)
            elif row_id is not None:
                self.refresh_row(row_id, self.app._bulk_row_values(self.app.filtered_items[int(row_id)]))
        self.app._apply_bulk_filter()
        self.clear_selection()
        self.app._update_bulk_summary()
        self.app._update_bulk_sheet_status()

    def _queue_post_edit_refresh(self):
        if self._edit_refresh_after_id is not None:
            try:
                self.sheet.after_cancel(self._edit_refresh_after_id)
            except Exception:
                pass
            self._edit_refresh_after_id = None
        try:
            self._edit_refresh_after_id = self.sheet.after(1, self._run_post_edit_refresh)
        except Exception:
            self._run_post_edit_refresh()

    def set_rows(self, rows, row_ids):
        self.row_ids = [int(row_id) for row_id in row_ids]
        self.row_lookup = {str(row_id): idx for idx, row_id in enumerate(self.row_ids)}
        self._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        self.sheet.set_sheet_data(rows, reset_col_positions=False, reset_row_positions=True)
        self.sheet.headers([self.labels[col] for col in self.columns], redraw=False)
        self.sheet.display_rows("all", redraw=True)
        self.app._update_bulk_sheet_status()

    def clear_selection(self):
        try:
            self.sheet.deselect("all", redraw=True)
        except Exception:
            pass
        self._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        self.app._update_bulk_sheet_status()

    def _remember_selection(self):
        self._selection_snapshot = {
            "cells": tuple(sorted(self.sheet.get_selected_cells())),
            "rows": tuple(sorted(self.sheet.get_selected_rows())),
            "columns": tuple(sorted(self.sheet.get_selected_columns())),
            "current": self.current_cell(),
        }

    def _snapshot_target_row_ids(self, col_name):
        col_idx = self.col_index.get(col_name)
        if col_idx is None:
            return tuple()
        snap_rows = tuple(
            str(self.row_ids[r]) for r in self._selection_snapshot.get("rows", ()) if 0 <= r < len(self.row_ids)
        )
        if snap_rows:
            return snap_rows
        snap_cells = self._selection_snapshot.get("cells", ())
        if snap_cells:
            matching_rows = {r for r, c in snap_cells if c == col_idx}
            if matching_rows:
                return tuple(str(self.row_ids[r]) for r in sorted(matching_rows) if 0 <= r < len(self.row_ids))
        return self.selected_target_row_ids(col_name)

    def explicit_selected_row_ids(self):
        rows = set(self.sheet.get_selected_rows())
        return tuple(str(self.row_ids[r]) for r in sorted(rows) if 0 <= r < len(self.row_ids))

    def selected_row_ids(self):
        rows = set(self.sheet.get_selected_rows())
        if not rows:
            rows = {r for r, _ in self.sheet.get_selected_cells()}
        return tuple(str(self.row_ids[r]) for r in sorted(rows) if 0 <= r < len(self.row_ids))

    def selected_cells(self):
        return sorted(self.sheet.get_selected_cells())

    def selected_column_names(self):
        cols = set(self.sheet.get_selected_columns())
        if not cols:
            cols = {c for _r, c in self.selected_cells()}
        return tuple(self.columns[c] for c in sorted(cols) if 0 <= c < len(self.columns))

    def visible_row_ids(self):
        return tuple(str(row_id) for row_id in self.row_ids)

    def current_cell(self):
        selected = self.sheet.get_currently_selected()
        if not selected:
            return None, None
        row = getattr(selected, "row", None)
        col = getattr(selected, "column", None)
        if row is None or col is None:
            return None, None
        if row < 0 or row >= len(self.row_ids) or col < 0 or col >= len(self.columns):
            return None, None
        return row, col

    def current_row_id(self):
        row, _col = self.current_cell()
        if row is None:
            return None
        return str(self.row_ids[row])

    def current_column_name(self):
        _row, col = self.current_cell()
        if col is None:
            return ""
        return self.columns[col]

    def current_editable_column_name(self):
        col_name = self.current_column_name()
        return col_name if col_name in self.editable_cols else ""

    def current_column_index(self):
        _row, col = self.current_cell()
        return col

    def current_cell_value(self):
        row, col = self.current_cell()
        if row is None or col is None:
            return ""
        try:
            value = self.sheet.get_cell_data(row, col)
        except Exception:
            return ""
        return "" if value is None else str(value)

    def selected_target_row_ids(self, col_name):
        col_idx = self.col_index.get(col_name)
        if col_idx is None:
            return tuple()
        explicit_rows = self.explicit_selected_row_ids()
        if explicit_rows:
            return explicit_rows
        selected_cells = self.selected_cells()
        if selected_cells:
            matching_rows = {r for r, c in selected_cells if c == col_idx}
            if matching_rows:
                return tuple(str(self.row_ids[r]) for r in sorted(matching_rows) if 0 <= r < len(self.row_ids))
        return self.selected_row_ids()

    def selected_editable_column_name(self):
        selected_cells = self.selected_cells()
        if not selected_cells:
            return self.current_column_name()
        columns = {c for _, c in selected_cells}
        if len(columns) != 1:
            return ""
        col_idx = next(iter(columns))
        if 0 <= col_idx < len(self.columns):
            return self.columns[col_idx]
        return ""

    def refresh_row(self, row_id, values):
        row_pos = self.row_lookup.get(str(row_id))
        if row_pos is None:
            return
        self.sheet.set_row_data(row_pos, values=values, redraw=True)

    def set_cell(self, row_id, col_name, value):
        row_pos = self.row_lookup.get(str(row_id))
        col_pos = self.col_index.get(col_name)
        if row_pos is None or col_pos is None:
            return
        self.sheet.set_cell_data(row_pos, col_pos, value, redraw=True)

    def get_children(self, _parent=""):
        return self.visible_row_ids()

    def selection(self):
        return self.selected_row_ids()

    def focus_set(self):
        self.sheet.focus_set()

    def resize_to_container(self, width=None, height=None):
        if self._resize_after_id is not None:
            try:
                self.sheet.after_cancel(self._resize_after_id)
            except Exception:
                pass
            self._resize_after_id = None
        self._resize_after_id = self.sheet.after(30, lambda: self._apply_resize(width, height))
        return self

    def _apply_resize(self, width=None, height=None):
        self._resize_after_id = None
        try:
            self.sheet.master.update_idletasks()
        except Exception:
            pass
        if width is None:
            width = self.sheet.master.winfo_width()
        if height is None:
            height = self.sheet.master.winfo_height()
        if width > 1 and height > 1:
            self.sheet.height_and_width(height=height, width=width)
            self.sheet.refresh()
            self.sheet.redraw()
        return self

    def fit_columns_to_window(self, available_width=None):
        if available_width is None:
            available_width = self.sheet.master.winfo_width()
        if available_width is None or available_width <= 1:
            return False

        padding = 24
        usable_width = max(200, int(available_width) - padding)
        fitted = []
        minimums = []
        maximums = []
        for col in self.columns:
            if col == "why":
                minimums.append(260)
                maximums.append(560)
            elif col == "description":
                minimums.append(80)
                maximums.append(560)
            elif col in ("vendor", "item_code", "supplier", "buy_rule"):
                minimums.append(52)
                maximums.append(220)
            else:
                minimums.append(40)
                maximums.append(160)

        for idx, col in enumerate(self.columns):
            try:
                text_width = int(self.sheet.get_column_text_width(idx, visible_only=True))
            except Exception:
                text_width = self.base_widths.get(col, 100)
            if text_width <= 0:
                text_width = self.base_widths.get(col, 100)
            extra_padding = 24 if col == "why" else 8
            target_width = max(minimums[idx], min(maximums[idx], text_width + extra_padding))
            fitted.append(target_width)

        total_width = sum(fitted)
        if total_width > usable_width:
            reducible = [max(0, fitted[i] - minimums[i]) for i in range(len(fitted))]
            overflow = total_width - usable_width
            while overflow > 0 and any(amount > 0 for amount in reducible):
                progress = False
                for i, amount in enumerate(reducible):
                    if overflow <= 0:
                        break
                    if amount > 0:
                        fitted[i] -= 1
                        reducible[i] -= 1
                        overflow -= 1
                        progress = True
                if not progress:
                    break

        self.sheet.set_column_widths(fitted)
        self.sheet.refresh()
        self.sheet.redraw()
        return True

    def select_current_row(self):
        row, col = self.current_cell()
        if row is None:
            return False
        self.sheet.deselect("all", redraw=False)
        self.sheet.select_row(row, redraw=True)
        if col is not None:
            self.sheet.set_currently_selected(row=row, column=col)
        self.app._update_bulk_sheet_status()
        return True

    def select_current_column(self):
        row, col = self.current_cell()
        if col is None:
            return False
        self.sheet.deselect("all", redraw=False)
        self.sheet.select_column(col, redraw=True)
        if row is not None:
            self.sheet.set_currently_selected(row=row, column=col)
        self.app._update_bulk_sheet_status()
        return True

    def copy_selection_to_clipboard(self):
        selected_cells = self.selected_cells()
        explicit_rows = self.explicit_selected_row_ids()
        selected_rows = explicit_rows or self.selected_row_ids()
        if explicit_rows:
            lines = []
            for row_id in selected_rows:
                row_pos = self.row_lookup.get(str(row_id))
                if row_pos is None:
                    continue
                row_values = [
                    str(self.sheet.get_cell_data(row_pos, col_idx))
                    for col_idx in range(len(self.columns))
                ]
                lines.append("\t".join(row_values))
            payload = "\n".join(lines)
        elif selected_cells:
            rows = sorted({r for r, _c in selected_cells})
            cols = sorted({c for _r, c in selected_cells})
            selected_lookup = set(selected_cells)
            lines = []
            for row in rows:
                values = []
                for col in cols:
                    if (row, col) in selected_lookup:
                        values.append(str(self.sheet.get_cell_data(row, col)))
                    else:
                        values.append("")
                lines.append("\t".join(values))
            payload = "\n".join(lines)
        elif selected_rows:
            lines = []
            for row_id in selected_rows:
                row_pos = self.row_lookup.get(str(row_id))
                if row_pos is None:
                    continue
                row_values = [
                    str(self.sheet.get_cell_data(row_pos, col_idx))
                    for col_idx in range(len(self.columns))
                ]
                lines.append("\t".join(row_values))
            payload = "\n".join(lines)
        else:
            row, col = self.current_cell()
            if row is None or col is None:
                return False
            payload = str(self.sheet.get_cell_data(row, col))
        self.sheet.clipboard_clear()
        self.sheet.clipboard_append(payload)
        return True

    def paste_from_clipboard(self):
        try:
            text = self.sheet.clipboard_get()
        except Exception:
            return False
        matrix = self._split_clipboard_matrix(text)
        if not matrix:
            return False

        current_row, current_col = self.current_cell()
        selected_col = self.selected_editable_column_name()
        target_col = selected_col or self.current_editable_column_name()

        if len(matrix[0]) == 1 and target_col in self.editable_cols:
            row_ids = list(self.selected_target_row_ids(target_col))
            if not row_ids and current_row is not None:
                row_ids = [str(self.row_ids[current_row])]
            if not row_ids:
                return False
            values = [row[0] for row in matrix]
            if len(values) == 1:
                values = values * len(row_ids)
            elif len(values) < len(row_ids):
                values.extend([values[-1]] * (len(row_ids) - len(values)))
            else:
                values = values[:len(row_ids)]
            for row_id, value in zip(row_ids, values):
                self.app._bulk_apply_editor_value(row_id, target_col, value)
            self.app._apply_bulk_filter()
            self.clear_selection()
            self.app._update_bulk_summary()
            self.app._update_bulk_sheet_status()
            return True

        if current_row is None or current_col is None:
            return False
        for row_offset, row_values in enumerate(matrix):
            row_pos = current_row + row_offset
            if row_pos >= len(self.row_ids):
                break
            row_id = str(self.row_ids[row_pos])
            for col_offset, value in enumerate(row_values):
                col_pos = current_col + col_offset
                if col_pos >= len(self.columns):
                    break
                col_name = self.columns[col_pos]
                if col_name not in self.editable_cols:
                    continue
                self.app._bulk_apply_editor_value(row_id, col_name, value)
        self.app._apply_bulk_filter()
        self.clear_selection()
        self.app._update_bulk_summary()
        self.app._update_bulk_sheet_status()
        return True
