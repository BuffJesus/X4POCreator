def maybe_break(result):
    return "break" if result else None


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
    col_name = (
        app.bulk_sheet.selected_editable_column_name()
        or app.bulk_sheet.current_editable_column_name()
    )
    row_ids = list(app.bulk_sheet.selected_target_row_ids(col_name)) if col_name else []
    if col_name not in editable_cols or not row_ids:
        return "break"
    value = app.bulk_sheet.current_cell_value().strip()
    before_state = app._capture_bulk_history_state() if hasattr(app, "_capture_bulk_history_state") else None
    write_debug(
        "bulk_shortcut_fill",
        alias=alias,
        col_name=col_name,
        row_count=len(row_ids),
        value=value,
    )
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, value)
    app._apply_bulk_filter()
    app.bulk_sheet.clear_selection()
    app._update_bulk_summary()
    app._update_bulk_cell_status()
    if hasattr(app, "_finalize_bulk_history_action"):
        app._finalize_bulk_history_action(f"{alias}:{col_name}", before_state)
    return "break"


def bulk_begin_edit(app, editable_cols, askstring, write_debug, event=None):
    if not app.bulk_sheet:
        return None
    right_click_context = getattr(app, "_right_click_bulk_context", None) or {}
    col_name = (
        right_click_context.get("col_name", "")
        or app.bulk_sheet.selected_editable_column_name()
        or app.bulk_sheet.current_editable_column_name()
    )
    row_ids = []
    if col_name:
        row_ids = list(app.bulk_sheet.selected_target_row_ids(col_name))
    clicked_row_id = right_click_context.get("row_id")
    if clicked_row_id:
        if not row_ids or clicked_row_id not in row_ids:
            row_ids = [clicked_row_id]
    if not row_ids and app.bulk_sheet:
        row_ids = list(app.bulk_sheet.selected_row_ids())
    write_debug(
        "bulk_begin_edit",
        col_name=col_name,
        row_ids=",".join(row_ids),
        row_count=len(row_ids),
        right_click_row_id=clicked_row_id or "",
    )
    if col_name == "buy_rule" and clicked_row_id:
        app._open_buy_rule_editor(int(clicked_row_id))
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
    before_state = app._capture_bulk_history_state() if hasattr(app, "_capture_bulk_history_state") else None
    write_debug(
        "bulk_begin_edit.apply",
        col_name=col_name,
        row_count=len(row_ids),
        value=value,
        right_click_context=repr(right_click_context),
    )
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, value)
    app._apply_bulk_filter()
    for row_id in row_ids[:12]:
        try:
            rendered = app._bulk_row_values(app.filtered_items[int(row_id)])
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
    if hasattr(app, "_finalize_bulk_history_action"):
        app._finalize_bulk_history_action(f"edit:{col_name}", before_state)
    return "break"


def bulk_remove_selected_rows(app, deepcopy, askyesno, event=None):
    selected = []
    if app.bulk_sheet:
        selected = list(app.bulk_sheet.explicit_selected_row_ids())
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
    for idx in sorted((int(row_id) for row_id in selected), reverse=True):
        if 0 <= idx < len(app.filtered_items):
            removed_payload.append((idx, deepcopy(app.filtered_items[idx])))
            app.filtered_items.pop(idx)
    app.last_removed_bulk_items = removed_payload
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._apply_bulk_filter()
    app._update_bulk_summary()
    return "break" if event is not None else None


def bulk_fill_selected_cells(app, editable_cols, askstring, showinfo):
    col_name = (
        (app.bulk_sheet.selected_editable_column_name() if app.bulk_sheet else "")
        or (app.bulk_sheet.current_editable_column_name() if app.bulk_sheet else "")
    )
    if app.bulk_sheet:
        row_ids = list(app.bulk_sheet.selected_target_row_ids(col_name))
    else:
        row_ids = list(app.bulk_tree.selection())
    if col_name not in editable_cols or not row_ids:
        showinfo("No Cell Selection", "Select one or more rows or cells in a single editable column first.")
        return
    value = askstring("Fill Selected Cells", f"Enter a value for {col_name}:", parent=app.root)
    if value is None:
        return
    before_state = app._capture_bulk_history_state() if hasattr(app, "_capture_bulk_history_state") else None
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, value.strip())
    app._apply_bulk_filter()
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._update_bulk_summary()
    app._update_bulk_cell_status()
    if hasattr(app, "_finalize_bulk_history_action"):
        app._finalize_bulk_history_action(f"fill:{col_name}", before_state)


def bulk_clear_selected_cells(app, editable_cols, showinfo):
    col_name = (
        (app.bulk_sheet.selected_editable_column_name() if app.bulk_sheet else "")
        or (app.bulk_sheet.current_editable_column_name() if app.bulk_sheet else "")
    )
    if app.bulk_sheet:
        row_ids = list(app.bulk_sheet.selected_target_row_ids(col_name))
    else:
        row_ids = list(app.bulk_tree.selection())
    if col_name not in editable_cols or not row_ids:
        showinfo("No Cell Selection", "Select one or more rows or cells in a single editable column first.")
        return
    before_state = app._capture_bulk_history_state() if hasattr(app, "_capture_bulk_history_state") else None
    for row_id in row_ids:
        app._bulk_apply_editor_value(row_id, col_name, "")
    app._apply_bulk_filter()
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._update_bulk_summary()
    app._update_bulk_cell_status()
    if hasattr(app, "_finalize_bulk_history_action"):
        app._finalize_bulk_history_action(f"clear:{col_name}", before_state)


def bulk_delete_selected(app, event=None):
    if app.bulk_sheet and app.bulk_sheet.explicit_selected_row_ids():
        return app._bulk_remove_selected_rows(event)
    if app.bulk_sheet and app.bulk_sheet.selected_cells():
        app._bulk_clear_selected_cells()
        return "break"
    return app._bulk_remove_selected_rows(event)
