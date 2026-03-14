import copy


def is_bulk_removal_history_label(label):
    normalized = str(label or "").strip().lower()
    return normalized.startswith("remove:")


def ignore_key(line_code, item_code):
    return f"{str(line_code).strip()}:{str(item_code).strip()}"


def ignore_items_by_keys(app, ignore_keys):
    normalized = {str(key).strip() for key in ignore_keys if str(key).strip()}
    if not normalized:
        return 0
    app.ignored_item_keys.update(normalized)
    app._save_ignored_item_keys()
    app.filtered_items = [
        item for item in app.filtered_items
        if app._ignore_key(item.get("line_code", ""), item.get("item_code", "")) not in normalized
    ]
    app.assigned_items = [
        item for item in app.assigned_items
        if app._ignore_key(item.get("line_code", ""), item.get("item_code", "")) not in normalized
    ]
    app.individual_items = [
        item for item in app.individual_items
        if app._ignore_key(item.get("line_code", ""), item.get("item_code", "")) not in normalized
    ]
    app._apply_bulk_filter()
    app._update_bulk_summary()
    if hasattr(app, "tree"):
        app._populate_review_tab()
    return len(normalized)


def capture_bulk_history_state(app):
    return {
        "filtered_items": copy.deepcopy(app.filtered_items),
        "inventory_lookup": copy.deepcopy(app.inventory_lookup),
        "qoh_adjustments": copy.deepcopy(app.qoh_adjustments),
        "order_rules": copy.deepcopy(app.order_rules),
        "vendor_codes_used": list(app.vendor_codes_used),
        "_loaded_order_rules": copy.deepcopy(app._loaded_order_rules),
        "_loaded_vendor_codes": list(app._loaded_vendor_codes),
        "last_removed_bulk_items": copy.deepcopy(app.last_removed_bulk_items),
    }


def finalize_bulk_history_action(app, label, before_state, max_bulk_history):
    if before_state is None:
        return False
    after_state = app._capture_bulk_history_state()
    if after_state == before_state:
        return False
    app.bulk_undo_stack.append({
        "label": label,
        "before": before_state,
        "after": after_state,
    })
    if len(app.bulk_undo_stack) > max_bulk_history:
        app.bulk_undo_stack = app.bulk_undo_stack[-max_bulk_history:]
    app.bulk_redo_stack = []
    return True


def restore_bulk_history_state(app, state):
    app.filtered_items = copy.deepcopy(state.get("filtered_items", []))
    app.inventory_lookup = copy.deepcopy(state.get("inventory_lookup", {}))
    app.qoh_adjustments = copy.deepcopy(state.get("qoh_adjustments", {}))
    app.order_rules = copy.deepcopy(state.get("order_rules", {}))
    app.vendor_codes_used = list(state.get("vendor_codes_used", []))
    app._loaded_order_rules = copy.deepcopy(state.get("_loaded_order_rules", {}))
    app._loaded_vendor_codes = list(state.get("_loaded_vendor_codes", []))
    app.last_removed_bulk_items = copy.deepcopy(state.get("last_removed_bulk_items", []))
    app._refresh_vendor_inputs()
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._apply_bulk_filter()
    app._update_bulk_summary()
    app._update_bulk_cell_status()
