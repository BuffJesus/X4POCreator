def refresh_vendor_inputs(app):
    if hasattr(app, "combo_bulk_vendor"):
        app.combo_bulk_vendor["values"] = app.vendor_codes_used
    if hasattr(app, "combo_vendor"):
        app.combo_vendor["values"] = app.vendor_codes_used
    if hasattr(app, "combo_vendor_filter"):
        vendors = sorted(set(item["vendor"] for item in app.assigned_items if item.get("vendor")))
        app.combo_vendor_filter["values"] = ["ALL"] + vendors


def remove_vendor_code(app, vendor):
    normalized = app._normalize_vendor_code(vendor)
    if not normalized:
        return
    app.vendor_codes_used = [code for code in app.vendor_codes_used if code != normalized]
    if hasattr(app, "vendor_policies"):
        app.vendor_policies.pop(normalized, None)
    app._save_vendor_codes()
    if hasattr(app, "_save_vendor_policies"):
        app._save_vendor_policies()
    app._refresh_vendor_inputs()


def update_bulk_cell_status(app):
    if not hasattr(app, "lbl_bulk_cell_status"):
        return
    bulk_sheet = getattr(app, "bulk_sheet", None)
    sheet_selected_cells = bulk_sheet.selected_cells() if bulk_sheet else []
    active_col = (
        bulk_sheet.selected_editable_column_name() if bulk_sheet else ""
    ) or (bulk_sheet.current_column_name() if bulk_sheet else "")
    if active_col:
        label_map = {
            "vendor": "Vendor",
            "final_qty": "Order Qty",
            "qoh": "QOH",
            "cur_min": "Min",
            "cur_max": "Max",
            "pack_size": "Pack",
        }
        col_label = label_map.get(active_col, active_col)
        count = len(sheet_selected_cells)
        if count:
            app.lbl_bulk_cell_status.config(text=f"Active edit column: {col_label} | Selected cells: {count}")
            return
        selected_rows = len(app.bulk_sheet.selected_row_ids()) if getattr(app, "bulk_sheet", None) else (
            len(app.bulk_tree.selection()) if hasattr(app, "bulk_tree") else 0
        )
        app.lbl_bulk_cell_status.config(text=f"Active edit column: {col_label} | Selected rows: {selected_rows}")
    else:
        selected_rows = len(app.bulk_sheet.selected_row_ids()) if getattr(app, "bulk_sheet", None) else (
            len(app.bulk_tree.selection()) if hasattr(app, "bulk_tree") else 0
        )
        app.lbl_bulk_cell_status.config(text=f"Active edit column: none | Selected rows: {selected_rows}")
