import copy

import ui_bulk


ITEM_RUNTIME_CACHE_KEYS = frozenset({
    "_bulk_row_id",
    "_bulk_row_id_key",
})


def bulk_history_capture_spec(*, inventory_lookup=False, qoh_adjustments=False, order_rules=False, vendor_codes_used=False, last_removed_bulk_items=True, filtered_items_row_ids=()):
    return {
        "inventory_lookup": bool(inventory_lookup),
        "qoh_adjustments": bool(qoh_adjustments),
        "order_rules": bool(order_rules),
        "vendor_codes_used": bool(vendor_codes_used),
        "last_removed_bulk_items": bool(last_removed_bulk_items),
        "filtered_items_row_ids": tuple(str(row_id) for row_id in (filtered_items_row_ids or ())),
    }


def bulk_history_capture_spec_for_columns(col_names, *, row_ids=(), include_vendor_codes=False, include_last_removed=True):
    normalized = {str(col_name or "") for col_name in (col_names or ()) if str(col_name or "")}
    return bulk_history_capture_spec(
        inventory_lookup=bool(normalized.intersection({"qoh", "cur_min", "cur_max"})),
        qoh_adjustments="qoh" in normalized,
        order_rules="pack_size" in normalized,
        vendor_codes_used=bool(include_vendor_codes or "vendor" in normalized),
        last_removed_bulk_items=include_last_removed,
        filtered_items_row_ids=row_ids,
    )


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
    ui_bulk.replace_filtered_items(app, [
        item for item in app.filtered_items
        if app._ignore_key(item.get("line_code", ""), item.get("item_code", "")) not in normalized
    ])
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


def capture_bulk_history_state(app, capture_spec=None):
    spec = bulk_history_capture_spec() if capture_spec is None else dict(capture_spec)
    row_ids = tuple(str(row_id) for row_id in spec.get("filtered_items_row_ids", ()) if str(row_id))
    item_keys = _bulk_history_item_keys(app, row_ids)
    if row_ids:
        state = {
            "filtered_items_rows": _copy_bulk_history_rows(app, row_ids),
        }
    else:
        state = {
            "filtered_items": _copy_bulk_history_items(app.filtered_items),
        }
    if spec.get("inventory_lookup"):
        if item_keys:
            state["inventory_lookup_entries"] = _copy_bulk_history_mapping_entries(app.inventory_lookup, item_keys)
        else:
            state["inventory_lookup"] = copy.deepcopy(app.inventory_lookup)
    if spec.get("qoh_adjustments"):
        if item_keys:
            state["qoh_adjustments_entries"] = _copy_bulk_history_mapping_entries(app.qoh_adjustments, item_keys)
        else:
            state["qoh_adjustments"] = copy.deepcopy(app.qoh_adjustments)
    if spec.get("order_rules"):
        if item_keys:
            rule_keys = tuple(f"{line_code}:{item_code}" for line_code, item_code in item_keys)
            state["order_rules_entries"] = _copy_bulk_history_mapping_entries(app.order_rules, rule_keys)
        else:
            state["order_rules"] = copy.deepcopy(app.order_rules)
    if spec.get("vendor_codes_used"):
        state["vendor_codes_used"] = list(app.vendor_codes_used)
    if spec.get("last_removed_bulk_items", True):
        state["last_removed_bulk_items"] = list(getattr(app, "last_removed_bulk_items", ()) or ())
    return state


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


def finalize_bulk_history_action(app, label, before_state, max_bulk_history, *, coalesce_key=None, capture_spec=None):
    if before_state is None:
        return False
    capture = getattr(app, "_capture_bulk_history_state", None)
    if callable(capture):
        if capture_spec is None:
            after_state = capture()
        else:
            try:
                after_state = capture(capture_spec=capture_spec)
            except TypeError:
                after_state = capture()
    else:
        after_state = capture_bulk_history_state(app, capture_spec=capture_spec)
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
        "_capture_spec": copy.deepcopy(capture_spec),
    })
    if len(app.bulk_undo_stack) > max_bulk_history:
        app.bulk_undo_stack = app.bulk_undo_stack[-max_bulk_history:]
    app.bulk_redo_stack = []
    return True


def restore_bulk_history_state(app, state):
    if "filtered_items_rows" in state:
        filtered_items = list(getattr(app, "filtered_items", ()) or ())
        for row_id, item in state.get("filtered_items_rows", []):
            idx, _existing = ui_bulk.resolve_bulk_row_id(app, row_id)
            if idx is None or not (0 <= idx < len(filtered_items)):
                continue
            filtered_items[idx] = _sanitize_bulk_history_item(item)
        ui_bulk.replace_filtered_items(app, filtered_items)
    else:
        ui_bulk.replace_filtered_items(app, _copy_bulk_history_items(state.get("filtered_items", [])))
    if "inventory_lookup" in state:
        app.inventory_lookup = copy.deepcopy(state.get("inventory_lookup", {}))
    elif "inventory_lookup_entries" in state:
        app.inventory_lookup = _restore_bulk_history_mapping_entries(app.inventory_lookup, state.get("inventory_lookup_entries", []))
    if "qoh_adjustments" in state:
        app.qoh_adjustments = copy.deepcopy(state.get("qoh_adjustments", {}))
    elif "qoh_adjustments_entries" in state:
        app.qoh_adjustments = _restore_bulk_history_mapping_entries(app.qoh_adjustments, state.get("qoh_adjustments_entries", []))
    if "order_rules" in state:
        app.order_rules = copy.deepcopy(state.get("order_rules", {}))
    elif "order_rules_entries" in state:
        app.order_rules = _restore_bulk_history_mapping_entries(app.order_rules, state.get("order_rules_entries", []))
    if "vendor_codes_used" in state:
        app.vendor_codes_used = list(state.get("vendor_codes_used", []))
    if "last_removed_bulk_items" in state:
        app.last_removed_bulk_items = list(state.get("last_removed_bulk_items", []))
    app._refresh_vendor_inputs()
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    app._apply_bulk_filter()
    app._update_bulk_summary()
    app._update_bulk_cell_status()


def _sanitize_bulk_history_item(item):
    copied = copy.deepcopy(item)
    if isinstance(copied, dict):
        for key in ITEM_RUNTIME_CACHE_KEYS:
            copied.pop(key, None)
    return copied


def _copy_bulk_history_items(items):
    return [_sanitize_bulk_history_item(item) for item in list(items or [])]


def _copy_bulk_history_rows(app, row_ids):
    rows = []
    for row_id in row_ids:
        _idx, item = ui_bulk.resolve_bulk_row_id(app, row_id)
        if item is None:
            continue
        rows.append((str(row_id), _sanitize_bulk_history_item(item)))
    return rows


def _bulk_history_item_keys(app, row_ids):
    keys = []
    for row_id in row_ids:
        _idx, item = ui_bulk.resolve_bulk_row_id(app, row_id)
        if item is None:
            continue
        keys.append((item.get("line_code"), item.get("item_code")))
    return tuple(keys)


def _copy_bulk_history_mapping_entries(mapping, keys):
    entries = []
    for key in keys:
        if key in mapping:
            entries.append((copy.deepcopy(key), True, copy.deepcopy(mapping[key])))
        else:
            entries.append((copy.deepcopy(key), False, None))
    return entries


def _restore_bulk_history_mapping_entries(current_mapping, entries):
    restored = copy.deepcopy(current_mapping)
    for key, present, value in entries:
        if present:
            restored[key] = copy.deepcopy(value)
        else:
            restored.pop(key, None)
    return restored
