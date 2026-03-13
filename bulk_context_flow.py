import ui_bulk_dialogs


def open_buy_rule_editor(app, idx, write_debug):
    item = app.filtered_items[idx] if 0 <= idx < len(app.filtered_items) else {}
    write_debug(
        "bulk_open_buy_rule_editor",
        idx=idx,
        line_code=item.get("line_code", ""),
        item_code=item.get("item_code", ""),
        right_click_context=repr(getattr(app, "_right_click_bulk_context", None)),
    )
    ui_bulk_dialogs.open_buy_rule_editor(app, idx, app._data_path("order_rules"))


def dismiss_duplicate(app, item_code):
    app.dup_whitelist.add(item_code)
    app._save_duplicate_whitelist()
    app.duplicate_ic_lookup.pop(item_code, None)
    app._apply_bulk_filter()


def ignore_from_bulk(app, askyesno, showinfo):
    right_click_context = getattr(app, "_right_click_bulk_context", None) or {}
    row_id = right_click_context.get("row_id")
    if row_id is not None and app.bulk_sheet and hasattr(app.bulk_sheet, "snapshot_row_ids"):
        snapshot_row_ids = list(app.bulk_sheet.snapshot_row_ids())
        if snapshot_row_ids and row_id in snapshot_row_ids:
            row_ids = snapshot_row_ids
        else:
            row_ids = [row_id]
    elif row_id is not None:
        row_ids = [row_id]
    elif app.bulk_sheet and app.bulk_sheet.explicit_selected_row_ids():
        row_ids = list(app.bulk_sheet.explicit_selected_row_ids())
    elif app.bulk_sheet and app.bulk_sheet.selected_row_ids():
        row_ids = list(app.bulk_sheet.selected_row_ids())
    elif app.bulk_sheet and app.bulk_sheet.current_row_id() is not None:
        row_ids = [app.bulk_sheet.current_row_id()]
    else:
        row_ids = []
    if not row_ids:
        showinfo("No Selection", "Select a row to ignore first.")
        return
    ignore_keys = set()
    for row_id in row_ids:
        idx = int(row_id)
        if 0 <= idx < len(app.filtered_items):
            item = app.filtered_items[idx]
            ignore_keys.add(app._ignore_key(item["line_code"], item["item_code"]))
    if not ignore_keys:
        return
    if not askyesno(
        "Ignore Item",
        f"Ignore {len(ignore_keys)} item(s) for future ordering and remove them from this session?",
    ):
        return
    removed = app._ignore_items_by_keys(ignore_keys)
    showinfo("Ignored", f"Ignored {removed} item(s).")
