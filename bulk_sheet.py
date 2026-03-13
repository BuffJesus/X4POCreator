import tkinter as tk
from types import SimpleNamespace

try:
    from tksheet import Sheet
    HAS_TKSHEET = True
    TKSHEET_IMPORT_ERROR = None
except ImportError as exc:
    Sheet = None
    HAS_TKSHEET = False
    TKSHEET_IMPORT_ERROR = exc

from debug_log import write_debug


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
        self._selection_anchor = None
        self._resize_after_id = None
        self._edit_refresh_after_id = None
        self._pending_edit = None
        self._selection_serial = 0
        self.context_menu = tk.Menu(parent, tearoff=0)

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
        self.sheet.disable_bindings("rc_popup_menu")
        self._build_context_menu()
        self._bind_text_editor_shortcuts()

    @staticmethod
    def _split_clipboard_matrix(text):
        if text is None:
            return []
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        if normalized == "":
            return []
        return [row.split("\t") for row in normalized.split("\n")]

    def _handle_select(self, event_data):
        if getattr(self.app, "_right_click_bulk_context", None):
            self.app._right_click_bulk_context = None
            write_debug("bulk_sheet.select.clear_right_click_context")
        self._remember_selection()
        self.app._update_bulk_sheet_status()

    def handle_right_click(self, event):
        row = None
        col = None
        try:
            row = self.sheet.identify_row(event, exclude_index=True, allow_end=False)
            col = self.sheet.identify_column(event, exclude_header=True, allow_end=False)
        except Exception:
            row = None
            col = None
        if row is None or col is None:
            return None
        if row < 0 or row >= len(self.row_ids) or col < 0 or col >= len(self.columns):
            return None

        # Snapshot the selection BEFORE set_currently_selected() can clear it.
        # If the right-clicked row is already part of the selection, keep the
        # whole selection intact.  Only move focus if clicking outside it.
        current_selected_rows = set(self.sheet.get_selected_rows())
        if row not in current_selected_rows:
            try:
                self.sheet.set_currently_selected(row=row, column=col)
            except Exception:
                pass

        self.app._right_click_bulk_context = {
            "row_id": str(self.row_ids[row]),
            "col_name": self.columns[col],
        }
        write_debug(
            "bulk_sheet.right_click",
            row=row,
            col=col,
            row_id=str(self.row_ids[row]),
            col_name=self.columns[col],
        )
        self._remember_selection()
        self.app._update_bulk_sheet_status()
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.context_menu.grab_release()
            except Exception:
                pass
        return "break"

    def _build_context_menu(self):
        self.context_menu.delete(0, "end")
        self.context_menu.add_command(label="Bulk Edit Selection", command=self.app._bulk_begin_edit_from_menu)
        self.context_menu.add_command(label="Remove Selected Rows", command=self.app._bulk_remove_selected_rows)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Edit Buy Rule", command=self.app._edit_buy_rule_from_bulk)
        self.context_menu.add_command(label="View Item Details", command=self.app._view_item_details)
        self.context_menu.add_command(label="Ignore Item", command=self.app._ignore_from_bulk)
        self.context_menu.add_command(label="Mark Review Resolved", command=self.app._resolve_review_from_bulk)
        self.context_menu.add_command(label="Dismiss duplicate warning", command=self.app._dismiss_duplicate_from_bulk)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select Current Row", command=self.app._bulk_select_current_row)
        self.context_menu.add_command(label="Select Current Column", command=self.app._bulk_select_current_column)

    def _bind_text_editor_shortcuts(self):
        bindings = {
            "<Left>": lambda event=None: self.commit_editor_and_move("left"),
            "<Right>": lambda event=None: self.commit_editor_and_move("right"),
            "<Up>": lambda event=None: self.commit_editor_and_move("up"),
            "<Down>": lambda event=None: self.commit_editor_and_move("down"),
            "<Tab>": lambda event=None: self.commit_editor_and_move("next"),
            "<ISO_Left_Tab>": lambda event=None: self.commit_editor_and_move("prev"),
            "<Shift-Tab>": lambda event=None: self.commit_editor_and_move("prev"),
        }
        for key, func in bindings.items():
            try:
                self.sheet.bind_key_text_editor(key, func)
            except Exception:
                pass

    def _handle_edit(self, event_data):
        self._drain_pending_edit()
        row = event_data.get("row")
        col = event_data.get("column")
        write_debug("bulk_sheet.handle_edit.begin", row=row, col=col, event_value=str(event_data.get("value", "")))
        if row is None or col is None or row >= len(self.row_ids) or col >= len(self.columns):
            write_debug("bulk_sheet.handle_edit.skip", reason="row_or_col_out_of_range", row=row, col=col)
            return
        row_id = str(self.row_ids[row])
        col_name = self.columns[col]
        write_debug("bulk_sheet.handle_edit.target", row=row, row_id=row_id, col=col, col_name=col_name)
        if col_name not in self.editable_cols:
            self._pending_edit = {
                "row": row,
                "col": col,
                "row_id": row_id,
                "col_name": col_name,
                "editable": False,
                "target_row_ids": (),
                "committed_value": event_data.get("value", ""),
                "selection_serial": getattr(self, "_selection_serial", 0),
            }
            write_debug("bulk_sheet.handle_edit.readonly", row_id=row_id, col_name=col_name)
            self._queue_post_edit_refresh()
            return
        target_row_ids = list(self._snapshot_target_row_ids(col_name))
        if row_id not in target_row_ids:
            target_row_ids = [row_id]
        write_debug("bulk_sheet.handle_edit.queued", col_name=col_name, row_id=row_id, target_row_ids=",".join(target_row_ids))
        self._pending_edit = {
            "row": row,
            "col": col,
            "row_id": row_id,
            "col_name": col_name,
            "editable": True,
            "target_row_ids": tuple(target_row_ids),
            "committed_value": event_data.get("value", ""),
            "selection_serial": getattr(self, "_selection_serial", 0),
        }
        self._queue_post_edit_refresh()

    def _run_post_edit_refresh(self):
        self._edit_refresh_after_id = None
        pending = self._pending_edit
        self._pending_edit = None
        before_state = None
        if pending and pending.get("editable") and hasattr(self.app, "_capture_bulk_history_state"):
            before_state = self.app._capture_bulk_history_state()
        if pending:
            row = pending.get("row")
            col = pending.get("col")
            row_id = pending.get("row_id")
            col_name = pending.get("col_name")
            value = pending.get("committed_value", "")
            try:
                sheet_value = self.sheet.get_cell_data(row, col)
            except Exception:
                sheet_value = ""
            if value is None:
                value = ""
            if sheet_value is None:
                sheet_value = ""
            value = str(value)
            sheet_value = str(sheet_value)
            write_debug(
                "bulk_sheet.post_edit.commit",
                row=pending.get("row"),
                col=pending.get("col"),
                row_id=row_id,
                col_name=col_name,
                editable=pending.get("editable"),
                committed_value=value,
                sheet_value=sheet_value,
            )
            if pending.get("editable"):
                for target_row_id in pending.get("target_row_ids", ()):
                    write_debug(
                        "bulk_sheet.post_edit.apply",
                        row_id=target_row_id,
                        col_name=col_name,
                        value=value,
                    )
                    self.app._bulk_apply_editor_value(target_row_id, col_name, value)
            elif row_id is not None:
                self.refresh_row(row_id, self.app._bulk_row_values(self.app.filtered_items[int(row_id)]))
        if pending and pending.get("editable"):
            refreshed = self.app._refresh_bulk_view_after_edit(pending.get("target_row_ids", ()))
        else:
            refreshed = True
        write_debug("bulk_sheet.post_edit.filtered", incremental=bool(refreshed))
        if pending and pending.get("row_id") is not None:
            try:
                rendered = self.app._bulk_row_values(self.app.filtered_items[int(pending["row_id"])])
                write_debug(
                    "bulk_sheet.post_edit.rendered_row",
                    row_id=pending["row_id"],
                    col_name=pending.get("col_name", ""),
                    rendered=" || ".join("" if value is None else str(value) for value in rendered),
                )
            except Exception as exc:
                write_debug("bulk_sheet.post_edit.rendered_row_error", row_id=pending["row_id"], error=str(exc))
        if self._should_clear_selection_after_edit(pending):
            self.clear_selection()
        else:
            write_debug(
                "bulk_sheet.post_edit.keep_selection",
                pending_serial=pending.get("selection_serial"),
                current_serial=getattr(self, "_selection_serial", 0),
            )
        self.app._update_bulk_summary()
        self.app._update_bulk_sheet_status()
        if pending and pending.get("editable") and hasattr(self.app, "_finalize_bulk_history_action"):
            self.app._finalize_bulk_history_action(f"sheet_edit:{pending.get('col_name', '')}", before_state)

    def _drain_pending_edit(self):
        pending = getattr(self, "_pending_edit", None)
        if not pending:
            return False
        after_id = getattr(self, "_edit_refresh_after_id", None)
        if after_id is not None:
            try:
                self.sheet.after_cancel(after_id)
            except Exception:
                pass
            self._edit_refresh_after_id = None
        write_debug(
            "bulk_sheet.post_edit.drain",
            row_id=pending.get("row_id"),
            col_name=pending.get("col_name"),
        )
        self._run_post_edit_refresh()
        return True

    def flush_pending_edit(self):
        return self._drain_pending_edit()

    def _queue_post_edit_refresh(self):
        if self._edit_refresh_after_id is not None:
            try:
                self.sheet.after_cancel(self._edit_refresh_after_id)
            except Exception:
                pass
            self._edit_refresh_after_id = None
        try:
            write_debug("bulk_sheet.post_edit.schedule", delay_ms=1)
            self._edit_refresh_after_id = self.sheet.after(1, self._run_post_edit_refresh)
        except Exception:
            write_debug("bulk_sheet.post_edit.schedule_fallback")
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
        self._selection_serial = getattr(self, "_selection_serial", 0) + 1
        self._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        self._selection_anchor = None
        self.app._update_bulk_sheet_status()

    def select_all_visible(self):
        if not self.row_ids:
            return False
        try:
            self.sheet.deselect("all", redraw=False)
        except Exception:
            pass
        for row in range(len(self.row_ids)):
            self.sheet.select_row(row, redraw=False)
        current_row, current_col = self.current_cell()
        if current_row is None:
            current_row = 0
        if current_col is None:
            current_col = 0
        try:
            self.sheet.set_currently_selected(row=current_row, column=current_col)
        except Exception:
            pass
        self._remember_selection()
        self.sheet.refresh()
        self.sheet.redraw()
        self.app._update_bulk_sheet_status()
        return True

    def _remember_selection(self):
        self._selection_serial = getattr(self, "_selection_serial", 0) + 1
        self._selection_snapshot = {
            "cells": tuple(sorted(self.sheet.get_selected_cells())),
            "rows": tuple(sorted(self.sheet.get_selected_rows())),
            "columns": tuple(sorted(self.sheet.get_selected_columns())),
            "current": self.current_cell(),
        }
        current = self._selection_snapshot.get("current")
        if current and current != (None, None):
            self._selection_anchor = current

    def _should_clear_selection_after_edit(self, pending):
        if not pending:
            return True
        return pending.get("selection_serial") == getattr(self, "_selection_serial", 0)

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

    def snapshot_row_ids(self):
        """Return row ids from the selection snapshot taken at right-click time.
        Use this instead of explicit_selected_row_ids() inside context menu
        commands, because tksheet clears the live selection before the command fires."""
        rows = self._selection_snapshot.get("rows", ())
        return tuple(str(self.row_ids[r]) for r in rows if 0 <= r < len(self.row_ids))

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
        get_selected_columns = getattr(self.sheet, "get_selected_columns", None)
        explicit_cols = tuple(
            self.columns[c]
            for c in sorted(get_selected_columns() if get_selected_columns else ())
            if 0 <= c < len(self.columns) and self.columns[c] in self.editable_cols
        )
        if len(explicit_cols) == 1:
            return explicit_cols[0]
        if len(explicit_cols) > 1:
            return ""
        selected_cells = self.selected_cells()
        if not selected_cells:
            return self.current_editable_column_name()
        columns = {c for _, c in selected_cells}
        if len(columns) != 1:
            return ""
        col_idx = next(iter(columns))
        if 0 <= col_idx < len(self.columns) and self.columns[col_idx] in self.editable_cols:
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

    def move_current_editable_cell(self, step):
        editable_positions = [idx for idx, name in enumerate(self.columns) if name in self.editable_cols]
        if not editable_positions or not self.row_ids:
            return False
        row, col = self.current_cell()
        if row is None:
            row = 0
        if col not in editable_positions:
            target_col = editable_positions[0 if step >= 0 else -1]
        else:
            current_pos = editable_positions.index(col)
            next_pos = current_pos + step
            if next_pos >= len(editable_positions):
                row = min(len(self.row_ids) - 1, row + 1)
                target_col = editable_positions[0]
            elif next_pos < 0:
                row = max(0, row - 1)
                target_col = editable_positions[-1]
            else:
                target_col = editable_positions[next_pos]
        try:
            self.sheet.deselect("all", redraw=False)
        except Exception:
            pass
        try:
            self.sheet.set_currently_selected(row=row, column=target_col)
        except Exception:
            return False
        self._remember_selection()
        self.sheet.refresh()
        self.sheet.redraw()
        self.app._update_bulk_sheet_status()
        return True

    def _close_open_text_editor(self, *, keysym="Commit"):
        try:
            if not self.sheet.MT.text_editor.open:
                return False
        except Exception:
            return False
        try:
            self.sheet.MT.close_text_editor(SimpleNamespace(keysym=keysym))
        except Exception:
            return False
        return True

    def commit_editor_and_move(self, direction):
        if not self._close_open_text_editor(keysym="Commit"):
            return None
        if direction == "next":
            moved = self.move_current_editable_cell(1)
        elif direction == "prev":
            moved = self.move_current_editable_cell(-1)
        elif direction in ("left", "right", "up", "down"):
            moved = self.jump_current_cell(direction, ctrl=False)
        else:
            moved = False
        return "break" if moved else "break"

    def _set_current_cell(self, row, col):
        if not self.row_ids or row < 0 or row >= len(self.row_ids) or col < 0 or col >= len(self.columns):
            return False
        try:
            self.sheet.deselect("all", redraw=False)
        except Exception:
            pass
        try:
            self.sheet.set_currently_selected(row=row, column=col)
        except Exception:
            return False
        self._remember_selection()
        self.sheet.refresh()
        self.sheet.redraw()
        self.app._update_bulk_sheet_status()
        return True

    def extend_selection(self, row_delta, col_delta):
        if not self.row_ids or not self.columns:
            return False
        row, col = self.current_cell()
        if row is None or col is None:
            row, col = 0, 0
        anchor_row, anchor_col = self._selection_anchor or (row, col)
        target_row = max(0, min(len(self.row_ids) - 1, row + row_delta))
        target_col = max(0, min(len(self.columns) - 1, col + col_delta))
        try:
            self.sheet.deselect("all", redraw=False)
            self.sheet.select_cell(anchor_row, anchor_col, redraw=False)
            for sel_row in range(min(anchor_row, target_row), max(anchor_row, target_row) + 1):
                for sel_col in range(min(anchor_col, target_col), max(anchor_col, target_col) + 1):
                    if sel_row == anchor_row and sel_col == anchor_col:
                        continue
                    self.sheet.add_cell_selection(sel_row, sel_col, redraw=False, set_as_current=False)
            self.sheet.set_currently_selected(row=target_row, column=target_col)
        except Exception:
            return False
        self._selection_snapshot = {
            "cells": tuple(
                (sel_row, sel_col)
                for sel_row in range(min(anchor_row, target_row), max(anchor_row, target_row) + 1)
                for sel_col in range(min(anchor_col, target_col), max(anchor_col, target_col) + 1)
            ),
            "rows": (),
            "columns": (),
            "current": (target_row, target_col),
        }
        self.sheet.refresh()
        self.sheet.redraw()
        self.app._update_bulk_sheet_status()
        return True

    def jump_current_cell(self, direction, ctrl=False):
        editable_positions = [idx for idx, name in enumerate(self.columns) if name in self.editable_cols]
        if not editable_positions or not self.row_ids:
            return False
        row, col = self.current_cell()
        if row is None:
            row = 0
        if col is None:
            col = editable_positions[0]
        if direction == "home":
            target_row = 0 if ctrl else row
            target_col = editable_positions[0]
        elif direction == "end":
            target_row = len(self.row_ids) - 1 if ctrl else row
            target_col = editable_positions[-1]
        elif direction == "left":
            target_row = row
            target_col = editable_positions[0] if ctrl else editable_positions[max(0, editable_positions.index(col) - 1)] if col in editable_positions else editable_positions[0]
        elif direction == "right":
            target_row = row
            target_col = editable_positions[-1] if ctrl else editable_positions[min(len(editable_positions) - 1, editable_positions.index(col) + 1)] if col in editable_positions else editable_positions[-1]
        elif direction == "up":
            target_row = 0 if ctrl else max(0, row - 1)
            target_col = col
        elif direction == "down":
            target_row = len(self.row_ids) - 1 if ctrl else min(len(self.row_ids) - 1, row + 1)
            target_col = col
        else:
            return False
        return self._set_current_cell(target_row, target_col)

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
        self.flush_pending_edit()
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
        before_state = self.app._capture_bulk_history_state() if hasattr(self.app, "_capture_bulk_history_state") else None

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
            refreshed = False
            if hasattr(self.app, "_refresh_bulk_view_after_edit"):
                refreshed = bool(self.app._refresh_bulk_view_after_edit(row_ids))
            if not refreshed:
                self.app._apply_bulk_filter()
            self.clear_selection()
            self.app._update_bulk_summary()
            self.app._update_bulk_sheet_status()
            if hasattr(self.app, "_finalize_bulk_history_action"):
                self.app._finalize_bulk_history_action(f"paste:{target_col}", before_state)
            return True

        if current_row is None or current_col is None:
            return False
        touched_row_ids = []
        for row_offset, row_values in enumerate(matrix):
            row_pos = current_row + row_offset
            if row_pos >= len(self.row_ids):
                break
            row_id = str(self.row_ids[row_pos])
            touched_row_ids.append(row_id)
            for col_offset, value in enumerate(row_values):
                col_pos = current_col + col_offset
                if col_pos >= len(self.columns):
                    break
                col_name = self.columns[col_pos]
                if col_name not in self.editable_cols:
                    continue
                self.app._bulk_apply_editor_value(row_id, col_name, value)
        refreshed = False
        if hasattr(self.app, "_refresh_bulk_view_after_edit"):
            refreshed = bool(self.app._refresh_bulk_view_after_edit(touched_row_ids))
        if not refreshed:
            self.app._apply_bulk_filter()
        self.clear_selection()
        self.app._update_bulk_summary()
        self.app._update_bulk_sheet_status()
        if hasattr(self.app, "_finalize_bulk_history_action"):
            self.app._finalize_bulk_history_action("paste:block", before_state)
        return True
