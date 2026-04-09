import json

import bulk_remove_flow
import session_state_flow
from debug_log import write_debug


def maybe_break(result):
    return "break" if result else None


def flush_pending_bulk_sheet_edit(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet and hasattr(bulk_sheet, "flush_pending_edit"):
        bulk_sheet.flush_pending_edit()


def refresh_bulk_view_after_edit(app, row_ids, col_name):
    try:
        return app._refresh_bulk_view_after_edit(row_ids, changed_cols=(col_name,))
    except TypeError:
        return app._refresh_bulk_view_after_edit(row_ids)


def capture_bulk_history_state(app, *, capture_spec=None):
    capture = getattr(app, "_capture_bulk_history_state", None)
    if not callable(capture):
        return None
    if capture_spec is None:
        return capture()
    try:
        return capture(capture_spec=capture_spec)
    except TypeError:
        return capture()


def bulk_edit_history_coalesce_key(kind, col_name, row_ids, *, selection_serial=None):
    return session_state_flow.bulk_history_coalesce_key(
        kind,
        col_name=col_name,
        row_ids=row_ids,
        selection_serial=selection_serial,
    )


def finalize_bulk_history_action(app, label, before_state, *, coalesce_key=None, capture_spec=None):
    finalize = getattr(app, "_finalize_bulk_history_action", None)
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


def resolve_bulk_edit_context(app, *, include_current_row=False):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    right_click_context = getattr(app, "_right_click_bulk_context", None) or {}
    if not bulk_sheet:
        return {
            "col_name": "",
            "row_ids": [],
            "clicked_row_id": right_click_context.get("row_id"),
            "row_source": "none",
        }
    col_name = (
        right_click_context.get("col_name", "")
        or bulk_sheet.selected_editable_column_name()
        or bulk_sheet.current_editable_column_name()
    )
    row_ids = list(bulk_sheet.selected_target_row_ids(col_name)) if col_name else []
    row_source = "target_rows" if row_ids else "none"
    clicked_row_id = right_click_context.get("row_id")
    if clicked_row_id:
        if not row_ids:
            row_ids = [clicked_row_id]
            row_source = "right_click_row"
        elif clicked_row_id not in row_ids:
            row_ids = [clicked_row_id]
            row_source = "right_click_override"
        else:
            row_source = "selection_including_right_click"
    if not row_ids:
        explicit_selected = getattr(bulk_sheet, "explicit_selected_row_ids", None)
        explicit_rows = list(explicit_selected()) if callable(explicit_selected) else []
        if explicit_rows:
            row_ids = explicit_rows
            row_source = "explicit_rows"
    if not row_ids:
        selected_selected = getattr(bulk_sheet, "selected_row_ids", None)
        selected_rows = list(selected_selected()) if callable(selected_selected) else []
        if selected_rows:
            row_ids = selected_rows
            row_source = "selected_rows"
    if not row_ids and include_current_row:
        current_row = getattr(bulk_sheet, "current_row_id", None)
        current_row_id = current_row() if callable(current_row) else None
        if current_row_id is not None:
            row_ids = [current_row_id]
            row_source = "current_row"
    return {
        "col_name": col_name,
        "row_ids": row_ids,
        "clicked_row_id": clicked_row_id,
        "row_source": row_source,
    }


def bulk_select_all(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.select_all_visible())


def bulk_clear_selection(app):
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
        app._right_click_bulk_context = None
        return "break"
    return None


def bulk_copy_selection(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.copy_selection_to_clipboard())


def bulk_paste_selection(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.paste_from_clipboard())


def bulk_select_current_row(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.select_current_row())


def bulk_select_current_column(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.select_current_column())


def bulk_move_next_editable_cell(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.move_current_editable_cell(1))


def bulk_move_prev_editable_cell(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.move_current_editable_cell(-1))


def bulk_extend_selection_up(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(-1, 0))


def bulk_extend_selection_down(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(1, 0))


def bulk_extend_selection_left(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(0, -1))


def bulk_extend_selection_right(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(0, 1))


def bulk_jump_home(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("home", ctrl=False))


def bulk_jump_end(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("end", ctrl=False))


def bulk_jump_ctrl_left(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("left", ctrl=True))


def bulk_jump_ctrl_right(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("right", ctrl=True))


def bulk_jump_ctrl_up(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("up", ctrl=True))


def bulk_jump_ctrl_down(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("down", ctrl=True))


def bulk_fill_selection_with_current_value(app, editable_cols, write_debug, event=None, *, alias="fill"):
    if not app.bulk_sheet:
        return None
    flush_pending_bulk_sheet_edit(app)
    edit_context = resolve_bulk_edit_context(app)
    col_name = edit_context["col_name"]
    row_ids = list(edit_context["row_ids"])
    if col_name not in editable_cols or not row_ids:
        return "break"
    value = app.bulk_sheet.current_cell_value().strip()
    capture_spec = session_state_flow.bulk_history_capture_spec_for_columns((col_name,), row_ids=row_ids)
    before_state = capture_bulk_history_state(app, capture_spec=capture_spec)
    write_debug(
        "bulk_shortcut_fill",
        alias=alias,
        col_name=col_name,
        row_count=len(row_ids),
        row_source=edit_context["row_source"],
        value=value,
    )
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, value)
    refresh_bulk_view_after_edit(app, row_ids, col_name)
    app.bulk_sheet.clear_selection()
    app._update_bulk_summary()
    app._update_bulk_cell_status()
    finalize_bulk_history_action(
        app,
        f"{alias}:{col_name}",
        before_state,
        coalesce_key=bulk_edit_history_coalesce_key(alias, col_name, row_ids),
        capture_spec=capture_spec,
    )
    return "break"


def bulk_begin_edit(app, editable_cols, askstring, write_debug, event=None):
    if not app.bulk_sheet:
        return None
    flush_pending_bulk_sheet_edit(app)
    edit_context = resolve_bulk_edit_context(app)
    col_name = edit_context["col_name"]
    row_ids = list(edit_context["row_ids"])
    clicked_row_id = edit_context["clicked_row_id"]
    write_debug(
        "bulk_begin_edit",
        col_name=col_name,
        row_ids=",".join(row_ids),
        row_count=len(row_ids),
        right_click_row_id=clicked_row_id or "",
        row_source=edit_context["row_source"],
    )
    if col_name == "buy_rule" and clicked_row_id:
        resolve_row = getattr(app, "_resolve_bulk_row_id", None)
        if callable(resolve_row):
            idx, _item = resolve_row(clicked_row_id)
        else:
            try:
                idx = int(clicked_row_id)
            except (TypeError, ValueError):
                idx = None
        if idx is not None:
            app._open_buy_rule_editor(idx)
        write_debug("bulk_begin_edit.buy_rule_editor", row_id=clicked_row_id)
        app._right_click_bulk_context = None
        return "break"
    if col_name not in editable_cols:
        if app.bulk_sheet and hasattr(app.bulk_sheet, "sheet"):
            app.bulk_sheet.sheet.open_cell()
        write_debug("bulk_begin_edit.open_cell", col_name=col_name, row_count=len(row_ids))
        app._right_click_bulk_context = None
        return "break"

    initial_value = app.bulk_sheet.current_cell_value()
    if len(row_ids) == 1:
        prompt = f"Enter a value for {col_name}:"
    else:
        prompt = f"Enter a value for {col_name} across {len(row_ids)} selected row(s):"
    value = askstring("Bulk Edit Selection", prompt, initialvalue=initial_value, parent=app.root)
    write_debug("bulk_begin_edit.prompt_result", col_name=col_name, value="" if value is None else value, cancelled=value is None)
    if value is None:
        app._right_click_bulk_context = None
        return "break"
    value = value.strip()
    if not row_ids:
        if app.bulk_sheet and hasattr(app.bulk_sheet, "sheet"):
            app.bulk_sheet.sheet.open_cell()
        write_debug("bulk_begin_edit.open_cell", col_name=col_name, row_count=len(row_ids))
        app._right_click_bulk_context = None
        return "break"
    capture_spec = session_state_flow.bulk_history_capture_spec_for_columns((col_name,), row_ids=row_ids)
    before_state = capture_bulk_history_state(app, capture_spec=capture_spec)
    write_debug(
        "bulk_begin_edit.apply",
        col_name=col_name,
        row_count=len(row_ids),
        row_source=edit_context["row_source"],
        value=value,
        right_click_context=repr(getattr(app, "_right_click_bulk_context", None)),
    )
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, value)
    refresh_bulk_view_after_edit(app, row_ids, col_name)
    for row_id in row_ids[:12]:
        try:
            resolve_row = getattr(app, "_resolve_bulk_row_id", None)
            if callable(resolve_row):
                _idx, item = resolve_row(row_id)
            else:
                _idx = int(row_id)
                item = app.filtered_items[_idx] if 0 <= _idx < len(app.filtered_items) else None
            if item is None:
                continue
            rendered = app._bulk_row_values(item)
            write_debug(
                "bulk_begin_edit.rendered_row",
                row_id=row_id,
                col_name=col_name,
                rendered=" || ".join("" if cell is None else str(cell) for cell in rendered),
            )
        except Exception as exc:
            write_debug("bulk_begin_edit.rendered_row_error", row_id=row_id, col_name=col_name, error=str(exc))
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._right_click_bulk_context = None
    app._update_bulk_summary()
    app._update_bulk_cell_status()
    finalize_bulk_history_action(
        app,
        f"edit:{col_name}",
        before_state,
        coalesce_key=bulk_edit_history_coalesce_key("edit", col_name, row_ids),
        capture_spec=capture_spec,
    )
    return "break"


def bulk_remove_selected_rows(app, deepcopy, askyesno, event=None):
    flush_pending_bulk_sheet_edit(app)
    selected = []
    if app.bulk_sheet:
        selected = list(app.bulk_sheet.explicit_selected_row_ids())
        if not selected:
            # tksheet clears the live selection before firing context menu commands;
            # use the snapshot captured at right-click time.
            snap_fn = getattr(app.bulk_sheet, "snapshot_row_ids", None)
            if callable(snap_fn):
                selected = list(snap_fn())
        if not selected:
            ctx = getattr(app, "_right_click_bulk_context", None) or {}
            row_id = ctx.get("row_id") or app.bulk_sheet.current_row_id()
            if row_id is not None:
                selected = [row_id]
    else:
        selected = list(app.bulk_tree.selection())
    if not selected:
        return "break" if event is not None else None
    if not askyesno("Confirm Remove", f"Remove {len(selected)} item(s) from this session?"):
        return "break" if event is not None else None
    removed_payload = []
    resolved = []
    expected_keys = {}
    resolve_row = getattr(app, "_resolve_bulk_row_id", None)
    for row_id in selected:
        if callable(resolve_row):
            idx, _item = resolve_row(row_id)
        else:
            try:
                idx = int(row_id)
            except (TypeError, ValueError):
                idx = None
        if idx is not None:
            try:
                parts = json.loads(str(row_id))
                if isinstance(parts, list) and len(parts) == 2:
                    expected_keys[idx] = (str(parts[0]), str(parts[1]))
            except (ValueError, TypeError):
                pass
            resolved.append(idx)
    for idx in sorted(set(resolved), reverse=True):
        if 0 <= idx < len(app.filtered_items):
            removed_payload.append(idx)
    requested_count = len(removed_payload)
    removed_payload = bulk_remove_flow.remove_filtered_rows(
        app,
        removed_payload,
        deepcopy,
        history_label="remove:selected_rows",
        expected_keys=expected_keys or None,
    )
    skipped = list(getattr(app, "last_skipped_bulk_removals", []) or [])
    if skipped and len(removed_payload) < requested_count:
        notify = getattr(app, "_notify_bulk_status", None) or getattr(app, "_show_bulk_status", None)
        message = (
            f"Skipped {len(skipped)} of {requested_count} row(s) — the view "
            f"shifted before confirm (filter or sort changed). Reselect and retry."
        )
        if callable(notify):
            try:
                notify(message)
            except TypeError:
                notify(message, level="warning")
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._apply_bulk_filter()
    app._update_bulk_summary()
    return "break" if event is not None else None


def bulk_fill_selected_cells(app, editable_cols, askstring, showinfo):
    flush_pending_bulk_sheet_edit(app)
    if app.bulk_sheet:
        edit_context = resolve_bulk_edit_context(app)
        col_name = edit_context["col_name"]
        row_ids = list(edit_context["row_ids"])
    else:
        col_name = ""
        row_ids = list(app.bulk_tree.selection())
    if col_name not in editable_cols or not row_ids:
        showinfo("No Cell Selection", "Select one or more rows or cells in a single editable column first.")
        return
    value = askstring("Fill Selected Cells", f"Enter a value for {col_name}:", parent=app.root)
    if value is None:
        return
    capture_spec = session_state_flow.bulk_history_capture_spec_for_columns((col_name,), row_ids=row_ids)
    before_state = capture_bulk_history_state(app, capture_spec=capture_spec)
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, value.strip())
    refresh_bulk_view_after_edit(app, row_ids, col_name)
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._update_bulk_summary()
    app._update_bulk_cell_status()
    finalize_bulk_history_action(
        app,
        f"fill:{col_name}",
        before_state,
        coalesce_key=bulk_edit_history_coalesce_key("fill", col_name, row_ids),
        capture_spec=capture_spec,
    )


def bulk_clear_selected_cells(app, editable_cols, showinfo):
    flush_pending_bulk_sheet_edit(app)
    if app.bulk_sheet:
        edit_context = resolve_bulk_edit_context(app)
        col_name = edit_context["col_name"]
        row_ids = list(edit_context["row_ids"])
    else:
        col_name = ""
        row_ids = list(app.bulk_tree.selection())
    if col_name not in editable_cols or not row_ids:
        showinfo("No Cell Selection", "Select one or more rows or cells in a single editable column first.")
        return
    capture_spec = session_state_flow.bulk_history_capture_spec_for_columns((col_name,), row_ids=row_ids)
    before_state = capture_bulk_history_state(app, capture_spec=capture_spec)
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, "")
    refresh_bulk_view_after_edit(app, row_ids, col_name)
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._update_bulk_summary()
    app._update_bulk_cell_status()
    finalize_bulk_history_action(
        app,
        f"clear:{col_name}",
        before_state,
        coalesce_key=bulk_edit_history_coalesce_key("clear", col_name, row_ids),
        capture_spec=capture_spec,
    )


def bulk_delete_selected(app, event=None):
    """Delete key handler — ALWAYS removes rows.

    The operator's mental model (confirmed across multiple bug
    reports since v0.8.0) is that Delete on the bulk grid should
    remove the row under the selection, period.  The previous
    Excel-style "cells selected → clear cells" branch silently
    cleared the vendor cell instead, which looked like "delete key
    doesn't work" even though the interceptor was firing correctly
    (v0.8.6 debug logging proved it).

    Dispatch order:
        1. Explicit row-header selection (click row numbers, ctrl-click
           for multiple) → remove those rows
        2. Cell selection(s) → derive the rows they live on and
           remove those rows
        3. Current row fallback → remove the single focused row
        4. Nothing → no-op
    """
    sheet = getattr(app, "bulk_sheet", None)
    if sheet is None:
        return None

    # 1. Explicit row-header selection
    row_ids = tuple(sheet.explicit_selected_row_ids())
    if row_ids:
        write_debug("bulk_delete_selected.source", mode="row_header", n=len(row_ids))
        return app._bulk_remove_selected_rows(event)

    # 2. Cell selection → promote to row selection
    cells = list(sheet.selected_cells() or [])
    if cells:
        row_ids_set = set()
        for r, _c in cells:
            if 0 <= r < len(sheet.row_ids):
                row_ids_set.add(str(sheet.row_ids[r]))
        if row_ids_set:
            write_debug(
                "bulk_delete_selected.source",
                mode="cell_promoted_to_row",
                n=len(row_ids_set),
            )
            # Feed the promoted set back to the sheet's selection so
            # `_bulk_remove_selected_rows` picks it up via the normal
            # `explicit_selected_row_ids()` path.  Also seed the
            # snapshot so the confirm dialog sees the same rows.
            try:
                sheet._selection_snapshot = {
                    "rows": tuple(sorted({
                        r for r, _c in cells if 0 <= r < len(sheet.row_ids)
                    })),
                    "cells": tuple(cells),
                }
            except Exception:
                pass
            return app._bulk_remove_selected_rows(event)

    # 3. Current row fallback
    current_row = sheet.current_row_id() if hasattr(sheet, "current_row_id") else None
    if current_row is not None:
        write_debug("bulk_delete_selected.source", mode="current_row", row_id=str(current_row))
        try:
            sheet._selection_snapshot = {
                "rows": (sheet.row_lookup.get(str(current_row), -1),)
                if hasattr(sheet, "row_lookup") else (),
                "cells": (),
            }
        except Exception:
            pass
        return app._bulk_remove_selected_rows(event)

    # 4. Nothing to do
    write_debug("bulk_delete_selected.source", mode="empty")
    return None
