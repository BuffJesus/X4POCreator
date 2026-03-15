import copy


def is_bulk_removal_history_label(label):
    normalized = str(label or "").strip().lower()
    return normalized.startswith("remove:")


def ignore_key(line_code, item_code):
    return f"{str(line_code).strip()}:{str(item_code).strip()}"


def bulk_history_coalesce_key(kind, *, col_name="", row_ids=(), selection_serial=None, scope=None):
    key = {"kind": str(kind or "")}
    if col_name:
        key["col_name"] = str(col_name)
    if row_ids:
        key["row_ids"] = tuple(str(row_id) for row_id in row_ids)
    if selection_serial is not None:
        key["selection_serial"] = selection_serial
    if scope:
        key["scope"] = scope
    return key


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


def _normalize_bulk_history_coalesce_key(key):
    if key is None:
        return None
    if isinstance(key, dict):
        return tuple(sorted((str(name), _normalize_bulk_history_coalesce_key(value)) for name, value in key.items()))
    if isinstance(key, (list, tuple, set)):
        return tuple(_normalize_bulk_history_coalesce_key(value) for value in key)
    return key


def _merge_bulk_history_entry(app, label, before_state, after_state, coalesce_key):
    if coalesce_key is None:
        return False
    undo_stack = getattr(app, "bulk_undo_stack", None)
    if not undo_stack:
        return False
    previous = undo_stack[-1]
    if previous.get("_coalesce_key") != coalesce_key:
        return False
    if previous.get("after") != before_state:
        return False
    previous["label"] = label
    previous["after"] = after_state
    return True


def finalize_bulk_history_action(app, label, before_state, max_bulk_history, *, coalesce_key=None):
    if before_state is None:
        return False
    after_state = app._capture_bulk_history_state()
    if after_state == before_state:
        return False
    normalized_coalesce_key = _normalize_bulk_history_coalesce_key(coalesce_key)
    if _merge_bulk_history_entry(app, label, before_state, after_state, normalized_coalesce_key):
        app.bulk_redo_stack = []
        return True
    app.bulk_undo_stack.append({
        "label": label,
        "before": before_state,
        "after": after_state,
        "_coalesce_key": normalized_coalesce_key,
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
