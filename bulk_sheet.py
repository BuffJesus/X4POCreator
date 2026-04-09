import tkinter as tk
from types import SimpleNamespace

import session_state_flow

try:
    from tksheet import Sheet
    HAS_TKSHEET = True
    TKSHEET_IMPORT_ERROR = None
except ImportError as exc:
    Sheet = None
    HAS_TKSHEET = False
    TKSHEET_IMPORT_ERROR = exc

from debug_log import write_debug

# Dark-theme palette for the right-click context menu.  Kept local
# because tk.Menu doesn't pick up ttk style settings — it's a classic
# tk widget, not a themed one.  Colors match the clam theme block in
# po_builder.py so the menu visually belongs to the rest of the app.
_CONTEXT_MENU_BG = "#2a2a40"
_CONTEXT_MENU_FG = "#d6d6e5"
_CONTEXT_MENU_ACTIVE_BG = "#5b4670"
_CONTEXT_MENU_ACTIVE_FG = "#ffffff"
_CONTEXT_MENU_BORDER = "#3a3a52"


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
        self._rendered_rows = ()
        self._rendered_row_ids = ()
        self._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        self._selection_anchor = None
        self._resize_after_id = None
        self._edit_refresh_after_id = None
        self._pending_edit = None
        self._pending_edit_generation = 0
        self._scheduled_edit_generation = None
        self._selection_serial = 0
        self.context_menu = tk.Menu(
            parent,
            tearoff=0,
            bg=_CONTEXT_MENU_BG,
            fg=_CONTEXT_MENU_FG,
            activebackground=_CONTEXT_MENU_ACTIVE_BG,
            activeforeground=_CONTEXT_MENU_ACTIVE_FG,
            activeborderwidth=0,
            bd=1,
            relief="flat",
            font=("Segoe UI", 10),
        )
        # The border color is set via a configure() call because several
        # platforms ignore it when passed to the constructor.
        try:
            self.context_menu.configure(borderwidth=1, background=_CONTEXT_MENU_BG)
        except tk.TclError:
            pass

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
        self.sheet.extra_bindings("end_edit_cell", self._handle_edit)
        self.sheet.extra_bindings("begin_edit_cell", self._handle_begin_edit)
        # Verify binding was actually registered
        write_debug(
            "bulk_sheet.init.bindings_check",
            end_edit_func_set=self.sheet.MT.extra_end_edit_cell_func is not None,
            begin_edit_func_set=self.sheet.MT.extra_begin_edit_cell_func is not None,
        )
        self.sheet.disable_bindings("rc_popup_menu")
        # tksheet's "all" bindings capture Delete internally to clear
        # cell contents.  Disable it so our Delete handler gets the
        # event and can route to row removal when row headers are
        # selected (matching the user's Excel muscle memory).
        try:
            self.sheet.disable_bindings("delete")
        except Exception:
            pass
        self._build_context_menu()
        self._bind_text_editor_shortcuts()
        self._bind_row_delete_keys()

    @staticmethod
    def _split_clipboard_matrix(text):
        if text is None:
            return []
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        if normalized == "":
            return []
        return [row.split("\t") for row in normalized.split("\n")]

    def _handle_select(self, event_data):
        self._flush_pending_before_navigation()
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
        self._flush_pending_before_navigation()

        # Snapshot the selection BEFORE set_currently_selected() can clear it.
        # If the right-clicked row is already part of the selection, keep the
        # whole selection intact.  Only move focus if clicking outside it.
        # get_selected_rows() returns row-header selections only; normal
        # shift-click / drag selection populates get_selected_cells() instead.
        current_selected_rows = set(self.sheet.get_selected_rows())
        current_selected_rows |= {r for r, _c in self.sheet.get_selected_cells()}
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
        self.context_menu.add_command(label="Edit Rule for Selection", command=self.app._edit_rule_for_selection)
        self.context_menu.add_command(label="View Item Details", command=self.app._view_item_details)
        self.context_menu.add_command(label="Ignore Item", command=self.app._ignore_from_bulk)
        self.context_menu.add_command(label="Mark Review Resolved", command=self.app._resolve_review_from_bulk)
        self.context_menu.add_command(label="Dismiss duplicate warning", command=self.app._dismiss_duplicate_from_bulk)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Flag for Discontinue Review", command=self.app._flag_discontinue_from_bulk)
        self.context_menu.add_command(label="Show Vendor Summary...", command=self.app._show_vendor_summary_from_bulk)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All Rows", command=self.app._bulk_select_all_rows)
        self.context_menu.add_command(label="Select Current Row", command=self.app._bulk_select_current_row)
        self.context_menu.add_command(label="Select Current Column", command=self.app._bulk_select_current_column)

    def _bind_row_delete_keys(self):
        """Route Delete / Backspace on the sheet to `_bulk_delete_selected`.

        The app's `bulk_delete_selected` handler already does the right
        thing based on what's selected:
            - explicit row-header selection (including non-contiguous
              ctrl-click selection) → remove those rows
            - cell selection → clear the cell contents
            - no selection → no-op

        tksheet's internal "delete" binding was disabled above so the
        event reaches us first.  We bind on every surface the event
        could land on: the Sheet composite, its internal MainTable
        canvas, and the row-index canvas.  Not every tksheet version
        exposes the same children, so we tolerate missing attributes.
        """
        delete_handler = getattr(self.app, "_bulk_delete_selected", None)
        if not callable(delete_handler):
            return

        def _on_delete(event=None):
            write_debug(
                "bulk_sheet.delete_interceptor.fired",
                widget=type(getattr(event, "widget", None)).__name__ if event is not None else "",
            )
            try:
                result = delete_handler(event)
                write_debug("bulk_sheet.delete_interceptor.handled", result=repr(result))
            except Exception as exc:
                write_debug("bulk_sheet.delete_key.error", error=str(exc))
                return None
            # Returning "break" stops Tk from dispatching the event to
            # any remaining bindtags (tksheet's class-level Delete handler
            # that was eating the event before our previous attempts).
            return "break"

        # Collect every widget the Delete key could land on.  tksheet's
        # Sheet is a composite: the MainTable (MT) is the cell area,
        # RowIndex (RI) is the row header column, ColumnHeader (CH) is
        # the header row, and TopLeftRectangle (TL) is the corner.
        targets = [self.sheet]
        for attr in ("MT", "RI", "CH", "TL"):
            child = getattr(self.sheet, attr, None)
            if child is not None:
                targets.append(child)

        # --------- The real fix: bindtag interception ---------------
        # Previous attempts bound on these widgets with add="+" but
        # tksheet registers its own Delete handler at the CLASS level
        # (via bind_class on Canvas) which runs in a later bindtag and
        # returns "break", stopping event propagation.  Widget-level
        # `add="+"` bindings run in the order they were registered on
        # the same bindtag — which on the widget tag means tksheet's
        # widget-level handler runs first.
        #
        # The bulletproof fix is to INSERT a custom bindtag at position
        # 0 on each target widget.  Tk dispatches events through
        # bindtags in order, so a custom tag at position 0 runs before
        # the widget's own tag, before the class tag, before toplevel,
        # before "all".  tksheet's bindings can't preempt us because
        # they live in later bindtags.
        custom_tag = "POBuilderSheetDelete"
        try:
            # Register the handler on the custom bindtag (once per
            # BulkSheetView instance — same handler closure, idempotent
            # rebinding is fine).
            self.sheet.bind_class(custom_tag, "<Delete>", _on_delete)
            self.sheet.bind_class(custom_tag, "<KP_Delete>", _on_delete)
        except Exception as exc:
            write_debug("bulk_sheet.delete_interceptor.bind_class_error", error=str(exc))

        for target in targets:
            try:
                current = list(target.bindtags())
                if custom_tag in current:
                    continue
                target.bindtags((custom_tag,) + tuple(current))
                write_debug(
                    "bulk_sheet.delete_interceptor.tag_installed",
                    widget=type(target).__name__,
                    bindtags=repr(target.bindtags()),
                )
            except Exception as exc:
                write_debug(
                    "bulk_sheet.delete_interceptor.tag_error",
                    widget=type(target).__name__,
                    error=str(exc),
                )

        # Also keep the legacy widget-level bindings as a fallback —
        # harmless when the bindtag interception works, a safety net
        # on tksheet versions where bindtags don't behave as expected.
        for target in targets:
            for sequence in ("<Delete>", "<KP_Delete>"):
                try:
                    target.bind(sequence, _on_delete, add="+")
                except Exception:
                    continue

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

    def _handle_begin_edit(self, event_data):
        """Suppress tksheet's inline text editor.

        Edits on this sheet are handled by the dialog-prompt path
        (``bulk_begin_edit`` via Double-click / F2 / Return bindings).
        If the inline editor is allowed to open, it races with the
        dialog: focus-out on the editor fires ``close_text_editor``
        which writes the OLD value back via ``set_cell_data_undo``,
        overwriting the dialog's new value.

        Returning None tells tksheet to cancel the editor open.
        """
        return None

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
            generation = self._next_pending_edit_generation()
            self._pending_edit = {
                "row": row,
                "col": col,
                "row_id": row_id,
                "col_name": col_name,
                "editable": False,
                "target_row_ids": (),
                "committed_value": event_data.get("value", ""),
                "selection_serial": getattr(self, "_selection_serial", 0),
                "generation": generation,
            }
            write_debug("bulk_sheet.handle_edit.readonly", row_id=row_id, col_name=col_name)
            self._queue_post_edit_refresh(generation)
            return
        target_row_ids = list(self._snapshot_target_row_ids(col_name))
        if row_id not in target_row_ids:
            target_row_ids = [row_id]
        write_debug("bulk_sheet.handle_edit.queued", col_name=col_name, row_id=row_id, target_row_ids=",".join(target_row_ids))
        generation = self._next_pending_edit_generation()
        self._pending_edit = {
            "row": row,
            "col": col,
            "row_id": row_id,
            "col_name": col_name,
            "editable": True,
            "target_row_ids": tuple(target_row_ids),
            "committed_value": event_data.get("value", ""),
            "selection_serial": getattr(self, "_selection_serial", 0),
            "generation": generation,
        }
        self._queue_post_edit_refresh(generation)

    def _next_pending_edit_generation(self):
        generation = getattr(self, "_pending_edit_generation", 0) + 1
        self._pending_edit_generation = generation
        return generation

    def _run_post_edit_refresh(self, expected_generation=None):
        pending = self._pending_edit
        pending_generation = pending.get("generation") if pending else None
        active_generation = getattr(self, "_scheduled_edit_generation", None)
        if expected_generation is not None and (
            pending is None
            or pending_generation != expected_generation
            or active_generation != expected_generation
        ):
            write_debug(
                "bulk_sheet.post_edit.skip_stale",
                expected_generation=expected_generation,
                pending_generation=pending_generation,
                active_generation=active_generation,
            )
            return False
        self._edit_refresh_after_id = None
        self._scheduled_edit_generation = None
        self._pending_edit = None
        before_state = None
        capture_spec = None
        if pending and pending.get("editable") and hasattr(self.app, "_capture_bulk_history_state"):
            capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(
                (pending.get("col_name"),),
                row_ids=pending.get("target_row_ids", ()),
            )
            try:
                before_state = self.app._capture_bulk_history_state(capture_spec=capture_spec)
            except TypeError:
                before_state = self.app._capture_bulk_history_state()
        if pending:
            row = pending.get("row")
            col = pending.get("col")
            row_id = pending.get("row_id")
            col_name = pending.get("col_name")
            value = pending.get("committed_value", "")
            # Re-lookup row position by stable row_id in case the sheet was re-rendered
            # between edit-fire and the async post-edit callback, so the debug read targets
            # the right cell rather than whatever is now at the original positional index.
            live_row = getattr(self, "row_lookup", {}).get(str(row_id)) if row_id is not None else None
            try:
                sheet_value = self.sheet.get_cell_data(live_row if live_row is not None else row, col)
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
                resolve_row = getattr(self.app, "_resolve_bulk_row_id", None)
                idx, item = resolve_row(row_id) if callable(resolve_row) else (None, None)
                if item is not None:
                    self.refresh_row(row_id, self.app._bulk_row_values(item))
        if pending and pending.get("editable"):
            try:
                refreshed = self.app._refresh_bulk_view_after_edit(
                    pending.get("target_row_ids", ()),
                    changed_cols=(pending.get("col_name"),),
                )
            except TypeError:
                refreshed = self.app._refresh_bulk_view_after_edit(pending.get("target_row_ids", ()))
        else:
            refreshed = True
        write_debug("bulk_sheet.post_edit.filtered", incremental=bool(refreshed))
        if pending and pending.get("row_id") is not None:
            try:
                resolve_row = getattr(self.app, "_resolve_bulk_row_id", None)
                idx, item = resolve_row(pending["row_id"]) if callable(resolve_row) else (None, None)
                if item is None:
                    raise LookupError("row not found")
                rendered = self.app._bulk_row_values(item)
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
        if pending and pending.get("editable"):
            self._finalize_bulk_history_action(
                f"sheet_edit:{pending.get('col_name', '')}",
                before_state,
                coalesce_key=self._history_coalesce_key_for_pending_edit(pending),
                capture_spec=capture_spec,
            )
        return bool(pending)

    def _history_coalesce_key_for_pending_edit(self, pending):
        if not pending or not pending.get("editable"):
            return None
        return session_state_flow.bulk_history_coalesce_key(
            "sheet_edit",
            col_name=pending.get("col_name", ""),
            row_ids=pending.get("target_row_ids", ()),
            selection_serial=pending.get("selection_serial"),
        )

    def _finalize_bulk_history_action(self, label, before_state, *, coalesce_key=None, capture_spec=None):
        finalize = getattr(self.app, "_finalize_bulk_history_action", None)
        if not callable(finalize):
            return None
        try:
            if capture_spec is not None and coalesce_key is not None:
                return finalize(label, before_state, coalesce_key=coalesce_key, capture_spec=capture_spec)
            if capture_spec is not None:
                return finalize(label, before_state, capture_spec=capture_spec)
            if coalesce_key is not None:
                return finalize(label, before_state, coalesce_key=coalesce_key)
            return finalize(label, before_state)
        except TypeError:
            if coalesce_key is not None:
                try:
                    return finalize(label, before_state, coalesce_key=coalesce_key)
                except TypeError:
                    return finalize(label, before_state)
            return finalize(label, before_state)

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
        generation = pending.get("generation")
        self._scheduled_edit_generation = generation
        write_debug(
            "bulk_sheet.post_edit.drain",
            row_id=pending.get("row_id"),
            col_name=pending.get("col_name"),
            generation=generation,
        )
        self._run_post_edit_refresh(generation)
        return True

    def flush_pending_edit(self):
        return self._drain_pending_edit()

    def _queue_post_edit_refresh(self, generation):
        if self._edit_refresh_after_id is not None:
            try:
                self.sheet.after_cancel(self._edit_refresh_after_id)
            except Exception:
                pass
            self._edit_refresh_after_id = None
        self._scheduled_edit_generation = generation
        try:
            write_debug("bulk_sheet.post_edit.schedule", delay_ms=1, generation=generation)
            self._edit_refresh_after_id = self.sheet.after(1, lambda: self._run_post_edit_refresh(generation))
        except Exception:
            write_debug("bulk_sheet.post_edit.schedule_fallback", generation=generation)
            self._run_post_edit_refresh(generation)

    def set_rows(self, rows, row_ids):
        normalized_row_ids = tuple(str(row_id) for row_id in row_ids)
        normalized_rows = tuple(tuple(row) for row in rows)
        ids_match = normalized_row_ids == getattr(self, "_rendered_row_ids", ())
        rows_match = normalized_rows == getattr(self, "_rendered_rows", ())
        write_debug(
            "bulk_sheet.set_rows.dedup_check",
            ids_match=ids_match,
            rows_match=rows_match,
            new_count=len(normalized_rows),
            old_count=len(getattr(self, "_rendered_rows", ())),
        )
        if ids_match and rows_match:
            self.row_ids = list(normalized_row_ids)
            self.row_lookup = {str(row_id): idx for idx, row_id in enumerate(self.row_ids)}
            self.app._update_bulk_sheet_status()
            return False
        self.row_ids = list(normalized_row_ids)
        self.row_lookup = {str(row_id): idx for idx, row_id in enumerate(self.row_ids)}
        self._rendered_row_ids = normalized_row_ids
        self._rendered_rows = normalized_rows
        if getattr(self.app, "_right_click_bulk_context", None):
            self.app._right_click_bulk_context = None
            write_debug("bulk_sheet.set_rows.clear_right_click_context")
        # Bump selection serial on every data change so history entries that were
        # queued before this render do not coalesce with entries queued after it.
        self._selection_serial = getattr(self, "_selection_serial", 0) + 1
        self._selection_snapshot = {"cells": (), "rows": (), "columns": (), "current": (None, None)}
        self.sheet.set_sheet_data(rows, reset_col_positions=False, reset_row_positions=True)
        self.sheet.headers([self.labels[col] for col in self.columns], redraw=False)
        self._apply_row_colors(rows)
        self.sheet.display_rows("all", redraw=True)
        self.app._update_bulk_sheet_status()
        return True

    # Row color palette — subtle tints over the dark grid background.
    # Keep contrast low so text stays readable against the base theme.
    _ROW_COLORS = {
        "assigned":  {"bg": "#243030"},   # very faint green tint
        "review":    {"bg": "#302c1e"},   # very faint amber tint
        "warning":   {"bg": "#302020"},   # very faint red tint
        "skip":      {"bg": "#1e1e1e"},   # slightly darker than base
    }

    def _apply_row_colors(self, rows):
        """Color-code rows by status and vendor assignment."""
        col_index = getattr(self, "col_index", None)
        if not col_index:
            return
        status_col = col_index.get("status")
        vendor_col = col_index.get("vendor")
        if status_col is None:
            return
        try:
            self.sheet.dehighlight_rows(redraw=False)
        except Exception:
            pass
        for row_idx, row_data in enumerate(rows):
            if not row_data:
                continue
            ncols = len(row_data)
            status = str(row_data[status_col]).strip().upper() if status_col < ncols else ""
            vendor = str(row_data[vendor_col]).strip() if vendor_col is not None and vendor_col < ncols else ""
            if vendor and status not in ("REVIEW", "WARN", "WARNING"):
                colors = self._ROW_COLORS.get("assigned")
            elif status in ("REVIEW",):
                colors = self._ROW_COLORS.get("review")
            elif status in ("WARN", "WARNING"):
                colors = self._ROW_COLORS.get("warning")
            elif status == "SKIP":
                colors = self._ROW_COLORS.get("skip")
            else:
                continue
            if colors:
                try:
                    self.sheet.highlight_rows(row_idx, bg=colors["bg"], redraw=False)
                except Exception:
                    pass

    def clear_selection(self):
        self._flush_pending_before_navigation()
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
        self._flush_pending_before_navigation()
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
        commands, because tksheet clears the live selection before the command fires.
        Falls back to deriving unique rows from cell selections when no row-header
        selection exists (normal shift-click / drag populates cells, not rows)."""
        snap = getattr(self, "_selection_snapshot", {})
        rows = snap.get("rows", ())
        if not rows:
            rows = sorted({r for r, _c in snap.get("cells", ())})
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

    def viewport_row_ids(self):
        """Row ids currently rendered inside the visible viewport.

        ``visible_row_ids`` returns every row that survived the active filter
        (the full filtered set), which is what callers want for "filtered"
        scope.  For "on screen" scope we need just the rows the user can
        actually see right now.  tksheet exposes ``visible_rows`` for that —
        fall back to the full set if it isn't available or fails.
        """
        if not self.row_ids:
            return tuple()
        get_visible = getattr(self.sheet, "visible_rows", None)
        if not callable(get_visible):
            return self.visible_row_ids()
        try:
            rows = get_visible()
        except Exception:
            return self.visible_row_ids()
        try:
            indices = sorted({int(r) for r in rows})
        except (TypeError, ValueError):
            return self.visible_row_ids()
        return tuple(
            str(self.row_ids[r])
            for r in indices
            if 0 <= r < len(self.row_ids)
        )

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
            write_debug("selected_target_row_ids.source", source="explicit", count=len(explicit_rows))
            return explicit_rows
        # Check live cell selection first — this survives drag selections
        # that the snapshot may have missed (the snapshot is overwritten on
        # every cell_select event, but tksheet's internal selection state
        # preserves the full drag range).
        selected_cells = self.selected_cells()
        if selected_cells:
            matching_rows = {r for r, c in selected_cells if c == col_idx}
            if matching_rows:
                write_debug("selected_target_row_ids.source", source="live_cells", count=len(matching_rows), col_idx=col_idx)
                return tuple(str(self.row_ids[r]) for r in sorted(matching_rows) if 0 <= r < len(self.row_ids))
        # Live selection empty (e.g. right-click cleared it) — fall back
        # to the snapshot captured at the last select event.
        snap_rows = self.snapshot_row_ids()
        if snap_rows:
            write_debug("selected_target_row_ids.source", source="snapshot", count=len(snap_rows))
            return snap_rows
        fallback = self.selected_row_ids()
        write_debug("selected_target_row_ids.source", source="fallback", count=len(fallback))
        return fallback

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
        write_debug(
            "bulk_sheet.refresh_row",
            row_id=row_id,
            row_pos=row_pos,
            values_len=len(values) if values else 0,
            sample=str(values[0] if values else "")[:40] if values else "",
        )
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
        self._flush_pending_before_navigation()
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
        self._flush_pending_before_navigation()
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
        return self._set_current_cell(row, target_col)

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
        self._flush_pending_before_navigation()
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
        self._flush_pending_before_navigation()
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
        self._flush_pending_before_navigation()
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

    def _flush_pending_before_navigation(self):
        if getattr(self, "_pending_edit", None):
            self.flush_pending_edit()

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

        if len(matrix[0]) == 1 and target_col in self.editable_cols:
            row_ids = list(self.selected_target_row_ids(target_col))
            if not row_ids and current_row is not None:
                row_ids = [str(self.row_ids[current_row])]
            if not row_ids:
                return False
            capture_spec = session_state_flow.bulk_history_capture_spec_for_columns((target_col,), row_ids=row_ids)
            before_state = None
            if hasattr(self.app, "_capture_bulk_history_state"):
                try:
                    before_state = self.app._capture_bulk_history_state(capture_spec=capture_spec)
                except TypeError:
                    before_state = self.app._capture_bulk_history_state()
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
                try:
                    refreshed = bool(self.app._refresh_bulk_view_after_edit(row_ids, changed_cols=(target_col,)))
                except TypeError:
                    refreshed = bool(self.app._refresh_bulk_view_after_edit(row_ids))
            if not refreshed:
                self.app._apply_bulk_filter()
            self.clear_selection()
            self.app._update_bulk_summary()
            self.app._update_bulk_sheet_status()
            self._finalize_bulk_history_action(
                f"paste:{target_col}",
                before_state,
                coalesce_key=session_state_flow.bulk_history_coalesce_key(
                    "paste",
                    col_name=target_col,
                    row_ids=row_ids,
                ),
                capture_spec=capture_spec,
            )
            return True

        if current_row is None or current_col is None:
            return False
        changed_cols = tuple(
            col_name
            for col_name in self.columns[current_col:current_col + max((len(row) for row in matrix), default=0)]
            if col_name in self.editable_cols
        )
        touched_row_ids = []
        for row_offset, _row_values in enumerate(matrix):
            row_pos = current_row + row_offset
            if row_pos >= len(self.row_ids):
                break
            touched_row_ids.append(str(self.row_ids[row_pos]))
        capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(changed_cols, row_ids=touched_row_ids)
        before_state = None
        if hasattr(self.app, "_capture_bulk_history_state"):
            try:
                before_state = self.app._capture_bulk_history_state(capture_spec=capture_spec)
            except TypeError:
                before_state = self.app._capture_bulk_history_state()
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
        refreshed = False
        if hasattr(self.app, "_refresh_bulk_view_after_edit"):
            try:
                refreshed = bool(self.app._refresh_bulk_view_after_edit(touched_row_ids, changed_cols=changed_cols))
            except TypeError:
                refreshed = bool(self.app._refresh_bulk_view_after_edit(touched_row_ids))
        if not refreshed:
            self.app._apply_bulk_filter()
        self.clear_selection()
        self.app._update_bulk_summary()
        self.app._update_bulk_sheet_status()
        self._finalize_bulk_history_action(
            "paste:block",
            before_state,
            coalesce_key=session_state_flow.bulk_history_coalesce_key(
                "paste_block",
                col_name=self.columns[current_col] if 0 <= current_col < len(self.columns) else "",
                row_ids=touched_row_ids,
                scope=changed_cols,
            ),
            capture_spec=capture_spec,
        )
        return True
