from tkinter import ttk

import item_workflow


def review_editor_widget(app, col_name):
    if col_name == "vendor":
        return ttk.Combobox(app.tree, values=app.vendor_codes_used, font=("Segoe UI", 10))
    return ttk.Entry(app.tree, font=("Segoe UI", 10))


def review_editor_value(app, row_id, col_name):
    return app.tree.set(row_id, col_name)


def review_refresh_editor_row(app, row_id):
    idx = int(row_id)
    app.tree.item(row_id, values=app._review_row_values(app.assigned_items[idx]))


def review_apply_editor_value(app, row_id, col_name, raw, get_rule_key):
    idx = int(row_id)
    item = app.assigned_items[idx]
    if col_name == "order_qty":
        try:
            app._set_effective_order_qty(item, int(float(raw)), manual_override=True)
            app._sync_review_item_to_filtered(item)
        except ValueError:
            pass
    elif col_name == "vendor":
        new_val = raw.upper()
        if new_val:
            item["vendor"] = new_val
            app._remember_vendor_code(new_val)
            app._sync_review_item_to_filtered(item)
            app._update_review_summary()
    elif col_name == "pack_size":
        try:
            item_workflow.apply_pack_size_edit(item, raw, app.order_rules, get_rule_key)
            app._save_order_rules()
            app._clear_manual_override(item)
            app._sync_review_item_to_filtered(item)
        except ValueError:
            pass
