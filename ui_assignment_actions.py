from tkinter import messagebox

import session_state_flow
import storage
import ui_bulk
import vendor_summary_flow


def _vendor_lead_time_lookup(app):
    """Return the cached vendor → lead-day map for the current session.

    Computed lazily on first access — `infer_vendor_lead_times` walks
    the snapshot history and we don't want to pay that cost on every
    keystroke.  Cleared when `session.vendor_codes_used` is rebuilt.
    """
    cached = getattr(app, "_vendor_lead_time_cache", None)
    if cached is not None:
        return cached
    sessions_dir = ""
    data_path = getattr(app, "_data_path", None)
    if callable(data_path):
        try:
            sessions_dir = data_path("sessions") or ""
        except Exception:
            sessions_dir = ""
    snapshots = []
    if sessions_dir:
        try:
            snapshots = storage.load_session_snapshots(sessions_dir, max_count=25) or []
        except Exception:
            snapshots = []
    try:
        lookup = storage.infer_vendor_lead_times(snapshots) or {}
    except Exception:
        lookup = {}
    app._vendor_lead_time_cache = lookup
    return lookup


def _hinted_vendor_values(app, codes):
    lookup = _vendor_lead_time_lookup(app)
    return [
        vendor_summary_flow.format_vendor_combo_value(code, lookup.get(str(code or "").strip().upper()))
        for code in codes
    ]


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


def bulk_vendor_history_coalesce_key(kind, row_ids, vendor):
    return session_state_flow.bulk_history_coalesce_key(
        kind,
        col_name="vendor",
        row_ids=row_ids,
        scope={"vendor": str(vendor or "")},
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


def bulk_vendor_autocomplete(app, event):
    if event.keysym in ("Return", "Escape", "Tab", "Up", "Down"):
        return
    raw = vendor_summary_flow.strip_vendor_hint(app.var_bulk_vendor.get())
    typed = raw.strip().upper()
    if not typed:
        app.combo_bulk_vendor["values"] = _hinted_vendor_values(app, app.vendor_codes_used)
        return
    filtered = [vendor for vendor in app.vendor_codes_used if vendor.upper().startswith(typed)]
    if not filtered:
        filtered = [vendor for vendor in app.vendor_codes_used if typed in vendor.upper()]
    app.combo_bulk_vendor["values"] = _hinted_vendor_values(app, filtered)


def bulk_apply_selected(app):
    flush_pending_bulk_sheet_edit(app)
    vendor = vendor_summary_flow.strip_vendor_hint(app.var_bulk_vendor.get()).strip().upper()
    if not vendor:
        messagebox.showinfo("Vendor Required", "Enter a vendor code first.")
        return
    selected = app.bulk_sheet.selected_row_ids() if getattr(app, "bulk_sheet", None) else app.bulk_tree.selection()
    if not selected:
        messagebox.showinfo("No Selection", "Select rows in the table first.")
        return
    capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("vendor",), row_ids=selected, include_vendor_codes=True)
    before_state = capture_bulk_history_state(app, capture_spec=capture_spec)
    for item_id in selected:
        resolver = getattr(app, "_resolve_bulk_row_id", None)
        if callable(resolver):
            idx, item = resolver(item_id)
        else:
            idx, item = ui_bulk.resolve_bulk_row_id(app, item_id)
        if idx is None or item is None:
            continue
        before_summary_item = ui_bulk.bulk_filter_bucket_snapshot(item)
        item["vendor"] = vendor
        ui_bulk.adjust_bulk_summary_for_item_change(
            app,
            before_summary_item,
            ui_bulk.bulk_filter_bucket_snapshot(item),
            item=item,
        )
        if not getattr(app, "bulk_sheet", None):
            app.bulk_tree.set(item_id, "vendor", vendor)
    if hasattr(app, "_remember_vendor_code"):
        app._remember_vendor_code(vendor)
    elif vendor not in app.vendor_codes_used:
        app.vendor_codes_used.append(vendor)
    if getattr(app, "bulk_sheet", None) and hasattr(app, "_refresh_bulk_view_after_edit"):
        refresh_bulk_view_after_edit(app, selected, "vendor")
    app._update_bulk_summary()
    finalize_bulk_history_action(
        app,
        "vendor:selected",
        before_state,
        coalesce_key=bulk_vendor_history_coalesce_key("vendor_selected", selected, vendor),
        capture_spec=capture_spec,
    )


def bulk_apply_visible(app):
    flush_pending_bulk_sheet_edit(app)
    vendor = vendor_summary_flow.strip_vendor_hint(app.var_bulk_vendor.get()).strip().upper()
    if not vendor:
        messagebox.showinfo("Vendor Required", "Enter a vendor code first.")
        return
    visible = app.bulk_sheet.visible_row_ids() if getattr(app, "bulk_sheet", None) else app.bulk_tree.get_children()
    if not visible:
        messagebox.showinfo("No Items", "There are no visible rows to update.")
        return
    capture_spec = session_state_flow.bulk_history_capture_spec_for_columns(("vendor",), row_ids=visible, include_vendor_codes=True)
    before_state = capture_bulk_history_state(app, capture_spec=capture_spec)
    for item_id in visible:
        resolver = getattr(app, "_resolve_bulk_row_id", None)
        if callable(resolver):
            idx, item = resolver(item_id)
        else:
            idx, item = ui_bulk.resolve_bulk_row_id(app, item_id)
        if idx is None or item is None:
            continue
        before_summary_item = ui_bulk.bulk_filter_bucket_snapshot(item)
        item["vendor"] = vendor
        ui_bulk.adjust_bulk_summary_for_item_change(
            app,
            before_summary_item,
            ui_bulk.bulk_filter_bucket_snapshot(item),
            item=item,
        )
        if not getattr(app, "bulk_sheet", None):
            app.bulk_tree.set(item_id, "vendor", vendor)
    if hasattr(app, "_remember_vendor_code"):
        app._remember_vendor_code(vendor)
    elif vendor not in app.vendor_codes_used:
        app.vendor_codes_used.append(vendor)
    if getattr(app, "bulk_sheet", None) and hasattr(app, "_refresh_bulk_view_after_edit"):
        refresh_bulk_view_after_edit(app, visible, "vendor")
    app._update_bulk_summary()
    finalize_bulk_history_action(
        app,
        "vendor:visible",
        before_state,
        coalesce_key=bulk_vendor_history_coalesce_key("vendor_visible", visible, vendor),
        capture_spec=capture_spec,
    )


def undo_last_bulk_removal(app):
    flush_pending_bulk_sheet_edit(app)
    undo_stack = list(getattr(app, "bulk_undo_stack", []) or [])
    if undo_stack:
        latest = undo_stack[-1]
        if session_state_flow.is_bulk_removal_history_label(latest.get("label", "")):
            if hasattr(app, "_bulk_undo"):
                app._bulk_undo()
                messagebox.showinfo("Undo Complete", "Reverted the most recent bulk removal.")
                return
        else:
            messagebox.showinfo(
                "Nothing to Undo",
                "The most recent bulk action was not a removal. Use Undo for the latest action first.",
            )
            return
    if not app.last_removed_bulk_items:
        messagebox.showinfo("Nothing to Undo", "No recent bulk removal to undo.")
        return

    restored = 0
    new_items = list(app.filtered_items)
    for idx, item in sorted(app.last_removed_bulk_items, key=lambda row: row[0]):
        insert_at = max(0, min(idx, len(new_items)))
        new_items.insert(insert_at, item)
        restored += 1

    app.last_removed_bulk_items = []
    ui_bulk.replace_filtered_items(app, new_items)
    app._apply_bulk_filter()
    app._update_bulk_summary()
    messagebox.showinfo("Undo Complete", f"Restored {restored} item(s).")


def go_to_individual(app):
    flush_pending_bulk_sheet_edit(app)
    if not app._check_stock_warnings():
        return
    unassigned = [item for item in app.filtered_items if not item.get("vendor")]
    if not unassigned:
        messagebox.showinfo("All Assigned", "All items already have a vendor. Proceeding to review.")
        app._finish_bulk_final()
        return
    app.individual_items = unassigned
    app.assign_index = 0
    app._populate_assign_item()
    app.notebook.tab(4, state="normal")
    app.notebook.select(4)


def vendor_autocomplete(app, event):
    ignored = (
        "Return", "Escape", "Tab", "Up", "Down", "BackSpace", "Delete",
        "Left", "Right", "Home", "End", "Shift_L", "Shift_R",
        "Control_L", "Control_R", "Alt_L", "Alt_R",
    )
    if event.keysym in ignored:
        if event.keysym in ("BackSpace", "Delete"):
            typed = app.var_vendor_input.get().strip().upper()
            if typed:
                filtered = [vendor for vendor in app.vendor_codes_used if typed in vendor.upper()]
            else:
                filtered = app.vendor_codes_used
            app.combo_vendor["values"] = filtered
        return

    typed = app.var_vendor_input.get().strip().upper()
    if not typed:
        app.combo_vendor["values"] = app.vendor_codes_used
        return

    filtered = [vendor for vendor in app.vendor_codes_used if vendor.upper().startswith(typed)]
    if not filtered:
        filtered = [vendor for vendor in app.vendor_codes_used if typed in vendor.upper()]
    app.combo_vendor["values"] = filtered

    if filtered and not app.combo_vendor.winfo_ismapped():
        app.combo_vendor.event_generate("<Down>")


def dismiss_dup_from_individual(app):
    item = app.individual_items[app.assign_index]
    app._dismiss_duplicate(item["item_code"])
    app.lbl_dup_warning.config(text="")
    app.btn_dismiss_dup.pack_forget()


def assign_current(app):
    vendor = app.var_vendor_input.get().strip().upper()
    if not vendor:
        messagebox.showinfo("Vendor Required", "Please enter a vendor code before assigning.")
        return

    item = app.individual_items[app.assign_index]
    item["vendor"] = vendor

    if hasattr(app, "_remember_vendor_code"):
        app._remember_vendor_code(vendor)
    elif vendor not in app.vendor_codes_used:
        app.vendor_codes_used.append(vendor)

    app.assign_index += 1
    if app.assign_index < len(app.individual_items):
        app._populate_assign_item()
    else:
        app._finish_assign()


def assign_skip(app):
    app.assign_index += 1
    if app.assign_index < len(app.individual_items):
        app._populate_assign_item()
    else:
        app._finish_assign()


def assign_back(app):
    if app.assign_index > 0:
        app.assign_index -= 1
        app._populate_assign_item()


def finish_assign(app):
    app._finish_bulk()
