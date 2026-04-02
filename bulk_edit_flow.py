import json

import item_workflow
import ui_bulk


def apply_editor_value(app, row_id, col_name, raw, editable_cols, get_rule_key, write_debug):
    write_debug("bulk_apply_editor_value.begin", row_id=row_id, col_name=col_name, raw=str(raw))
    resolve_row = getattr(app, "_resolve_bulk_row_id", None)
    if callable(resolve_row):
        idx, item = resolve_row(row_id)
    else:
        idx, item = ui_bulk.resolve_bulk_row_id(app, row_id)
    if idx is None or item is None:
        write_debug("bulk_apply_editor_value.skip", row_id=row_id, col_name=col_name, reason="row_not_found")
        return
    if col_name == "buy_rule":
        app._open_buy_rule_editor(idx)
        write_debug("bulk_apply_editor_value.buy_rule_editor", row_id=row_id)
        return
    if col_name not in editable_cols:
        write_debug("bulk_apply_editor_value.skip", row_id=row_id, col_name=col_name, reason="not_editable")
        return
    before_summary_item = ui_bulk.bulk_filter_bucket_snapshot(item)
    key = (item["line_code"], item["item_code"])
    inv = app.inventory_lookup.get(key, {})
    if col_name == "vendor":
        new_val = raw.strip().upper()
        if new_val:
            item["vendor"] = new_val
            app._remember_vendor_code(new_val)
            write_debug("bulk_apply_editor_value.vendor", row_id=row_id, vendor=new_val)
    elif col_name == "final_qty":
        try:
            qty = int(float(raw))
            app._set_effective_order_qty(item, qty, manual_override=True)
            app._recalculate_item(item)
            write_debug(
                "bulk_apply_editor_value.final_qty",
                row_id=row_id,
                qty=qty,
                suggested=item.get("suggested_qty"),
                final=item.get("final_qty"),
                why=item.get("why", ""),
            )
        except ValueError:
            write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
    elif col_name == "qoh":
        try:
            new_qoh = float(raw)
            old_qoh = inv.get("qoh", 0)
            if new_qoh != old_qoh:
                app.qoh_adjustments[key] = {"old": old_qoh, "new": new_qoh}
                if key in app.inventory_lookup:
                    app.inventory_lookup[key]["qoh"] = new_qoh
                app._recalculate_item(item)
            write_debug(
                "bulk_apply_editor_value.qoh",
                row_id=row_id,
                old_qoh=old_qoh,
                new_qoh=new_qoh,
                raw_need=item.get("raw_need"),
                suggested=item.get("suggested_qty"),
                final=item.get("final_qty"),
            )
        except ValueError:
            write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
    elif col_name in ("cur_min", "cur_max"):
        if key not in app.inventory_lookup:
            qoh_adj = getattr(app, "qoh_adjustments", {}).get(key, {})
            qoh = qoh_adj.get("new", 0)
            app.inventory_lookup[key] = {
                "qoh": qoh, "repl_cost": 0, "min": None, "max": None,
                "ytd_sales": 0, "mo12_sales": 0, "supplier": "",
                "last_receipt": "", "last_sale": "",
            }
        try:
            parsed = None if raw == "" else int(float(raw))
            if col_name == "cur_min":
                app.inventory_lookup[key]["min"] = parsed
            else:
                app.inventory_lookup[key]["max"] = parsed
            app._recalculate_item(item)
            write_debug(
                "bulk_apply_editor_value.minmax",
                row_id=row_id,
                col_name=col_name,
                parsed=parsed,
                raw_need=item.get("raw_need"),
                suggested=item.get("suggested_qty"),
                final=item.get("final_qty"),
            )
        except ValueError:
            write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
    elif col_name == "pack_size":
        try:
            old_pack = item.get("pack_size")
            old_policy = item.get("order_policy", "")
            old_suggested = item.get("suggested_qty")
            old_final = item.get("final_qty")
            rule_key, _rule = item_workflow.apply_pack_size_edit(item, raw, app.order_rules, get_rule_key)
            app._save_order_rules()
            app._clear_manual_override(item)
            app._recalculate_item(item)
            write_debug(
                "bulk_apply_editor_value.pack_size",
                row_id=row_id,
                line_code=item.get("line_code", ""),
                item_code=item.get("item_code", ""),
                old_pack=old_pack,
                new_pack=item.get("pack_size"),
                old_policy=old_policy,
                new_policy=item.get("order_policy", ""),
                old_suggested=old_suggested,
                new_suggested=item.get("suggested_qty"),
                old_final=old_final,
                new_final=item.get("final_qty"),
                rule=json.dumps(app.order_rules.get(rule_key, {}), sort_keys=True),
                why=item.get("why", ""),
            )
        except ValueError:
            write_debug("bulk_apply_editor_value.error", row_id=row_id, col_name=col_name, raw=str(raw), reason="value_error")
    ui_bulk.adjust_bulk_summary_for_item_change(
        app,
        before_summary_item,
        ui_bulk.bulk_filter_bucket_snapshot(item),
        item=item,
    )
