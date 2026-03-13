from tkinter import messagebox

import ui_bulk


def flush_pending_bulk_sheet_edit(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet and hasattr(bulk_sheet, "flush_pending_edit"):
        bulk_sheet.flush_pending_edit()


def bulk_vendor_autocomplete(app, event):
    if event.keysym in ("Return", "Escape", "Tab", "Up", "Down"):
        return
    typed = app.var_bulk_vendor.get().strip().upper()
    if not typed:
        app.combo_bulk_vendor["values"] = app.vendor_codes_used
        return
    filtered = [vendor for vendor in app.vendor_codes_used if vendor.upper().startswith(typed)]
    if not filtered:
        filtered = [vendor for vendor in app.vendor_codes_used if typed in vendor.upper()]
    app.combo_bulk_vendor["values"] = filtered


def bulk_apply_selected(app):
    flush_pending_bulk_sheet_edit(app)
    vendor = app.var_bulk_vendor.get().strip().upper()
    if not vendor:
        messagebox.showinfo("Vendor Required", "Enter a vendor code first.")
        return
    selected = app.bulk_sheet.selected_row_ids() if getattr(app, "bulk_sheet", None) else app.bulk_tree.selection()
    if not selected:
        messagebox.showinfo("No Selection", "Select rows in the table first.")
        return
    before_state = app._capture_bulk_history_state() if hasattr(app, "_capture_bulk_history_state") else None
    for item_id in selected:
        idx = int(item_id)
        before_summary_item = {
            "vendor": app.filtered_items[idx].get("vendor", ""),
            "status": app.filtered_items[idx].get("status", ""),
        }
        app.filtered_items[idx]["vendor"] = vendor
        ui_bulk.adjust_bulk_summary_for_item_change(
            app,
            before_summary_item,
            {"vendor": app.filtered_items[idx].get("vendor", ""), "status": app.filtered_items[idx].get("status", "")},
        )
        if not getattr(app, "bulk_sheet", None):
            app.bulk_tree.set(item_id, "vendor", vendor)
    if hasattr(app, "_remember_vendor_code"):
        app._remember_vendor_code(vendor)
    elif vendor not in app.vendor_codes_used:
        app.vendor_codes_used.append(vendor)
    if getattr(app, "bulk_sheet", None) and hasattr(app, "_refresh_bulk_view_after_edit"):
        app._refresh_bulk_view_after_edit(selected, changed_cols=("vendor",))
    app._update_bulk_summary()
    if hasattr(app, "_finalize_bulk_history_action"):
        app._finalize_bulk_history_action("vendor:selected", before_state)


def bulk_apply_visible(app):
    flush_pending_bulk_sheet_edit(app)
    vendor = app.var_bulk_vendor.get().strip().upper()
    if not vendor:
        messagebox.showinfo("Vendor Required", "Enter a vendor code first.")
        return
    visible = app.bulk_sheet.visible_row_ids() if getattr(app, "bulk_sheet", None) else app.bulk_tree.get_children()
    if not visible:
        messagebox.showinfo("No Items", "There are no visible rows to update.")
        return
    before_state = app._capture_bulk_history_state() if hasattr(app, "_capture_bulk_history_state") else None
    for item_id in visible:
        idx = int(item_id)
        before_summary_item = {
            "vendor": app.filtered_items[idx].get("vendor", ""),
            "status": app.filtered_items[idx].get("status", ""),
        }
        app.filtered_items[idx]["vendor"] = vendor
        ui_bulk.adjust_bulk_summary_for_item_change(
            app,
            before_summary_item,
            {"vendor": app.filtered_items[idx].get("vendor", ""), "status": app.filtered_items[idx].get("status", "")},
        )
        if not getattr(app, "bulk_sheet", None):
            app.bulk_tree.set(item_id, "vendor", vendor)
    if hasattr(app, "_remember_vendor_code"):
        app._remember_vendor_code(vendor)
    elif vendor not in app.vendor_codes_used:
        app.vendor_codes_used.append(vendor)
    if getattr(app, "bulk_sheet", None) and hasattr(app, "_refresh_bulk_view_after_edit"):
        app._refresh_bulk_view_after_edit(visible, changed_cols=("vendor",))
    app._update_bulk_summary()
    if hasattr(app, "_finalize_bulk_history_action"):
        app._finalize_bulk_history_action("vendor:visible", before_state)


def undo_last_bulk_removal(app):
    flush_pending_bulk_sheet_edit(app)
    if not app.last_removed_bulk_items:
        messagebox.showinfo("Nothing to Undo", "No recent bulk removal to undo.")
        return

    restored = 0
    for idx, item in sorted(app.last_removed_bulk_items, key=lambda row: row[0]):
        insert_at = max(0, min(idx, len(app.filtered_items)))
        app.filtered_items.insert(insert_at, item)
        restored += 1

    app.last_removed_bulk_items = []
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
