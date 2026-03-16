import copy

import ui_bulk


ITEM_RUNTIME_CACHE_KEYS = frozenset({
    "_bulk_row_id",
    "_bulk_row_id_key",
})


def bulk_history_capture_spec(
    *,
    inventory_lookup=False,
    qoh_adjustments=False,
    order_rules=False,
    vendor_codes_used=False,
    last_removed_bulk_items=True,
    filtered_items_row_ids=(),
    changed_columns=(),
):
    return {
        "inventory_lookup": bool(inventory_lookup),
        "qoh_adjustments": bool(qoh_adjustments),
        "order_rules": bool(order_rules),
        "vendor_codes_used": bool(vendor_codes_used),
        "last_removed_bulk_items": bool(last_removed_bulk_items),
        "filtered_items_row_ids": tuple(str(row_id) for row_id in (filtered_items_row_ids or ())),
        "changed_columns": tuple(str(col_name) for col_name in (changed_columns or ()) if str(col_name)),
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
        changed_columns=tuple(sorted(normalized)),
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
    vendor_codes = _bulk_history_row_vendor_codes(app, row_ids)
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
        if vendor_codes:
            state["vendor_codes_used_entries"] = _copy_bulk_history_vendor_code_entries(app.vendor_codes_used, vendor_codes)
        else:
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
    if not bulk_history_states_equivalent(previous.get("after", {}), before_state):
        return False
    merged_before, merged_after = compact_bulk_history_state_pair(previous.get("before", {}), after_state)
    if merged_after == merged_before:
        undo_stack.pop()
        return True
    previous["label"] = label
    previous["before"] = merged_before
    previous["after"] = merged_after
    return True


def _prune_unchanged_bulk_history_state(before_state, after_state):
    normalized_before = dict(before_state)
    normalized_after = dict(after_state)
    normalized_before, normalized_after = _normalize_bulk_history_state_pair_shapes(
        normalized_before,
        normalized_after,
    )
    normalized_before, normalized_after = _prune_unchanged_bulk_history_entries(
        normalized_before,
        normalized_after,
        "filtered_items_rows",
    )
    normalized_before, normalized_after = _prune_unchanged_bulk_history_entries(
        normalized_before,
        normalized_after,
        "inventory_lookup_entries",
    )
    normalized_before, normalized_after = _prune_unchanged_bulk_history_entries(
        normalized_before,
        normalized_after,
        "qoh_adjustments_entries",
    )
    normalized_before, normalized_after = _prune_unchanged_bulk_history_entries(
        normalized_before,
        normalized_after,
        "order_rules_entries",
    )
    normalized_before, normalized_after = _prune_unchanged_bulk_history_entries(
        normalized_before,
        normalized_after,
        "vendor_codes_used_entries",
    )
    normalized_before, normalized_after = _compact_bulk_history_row_patches(
        normalized_before,
        normalized_after,
    )
    normalized_before, normalized_after = _compact_bulk_history_mapping_entry_patches(
        normalized_before,
        normalized_after,
        "inventory_lookup_entries",
        "inventory_lookup_entry_patches",
    )
    normalized_before, normalized_after = _compact_bulk_history_mapping_entry_patches(
        normalized_before,
        normalized_after,
        "qoh_adjustments_entries",
        "qoh_adjustments_entry_patches",
    )
    normalized_before, normalized_after = _compact_bulk_history_mapping_entry_patches(
        normalized_before,
        normalized_after,
        "order_rules_entries",
        "order_rules_entry_patches",
    )
    optional_keys = (
        "inventory_lookup",
        "inventory_lookup_entries",
        "inventory_lookup_entry_patches",
        "qoh_adjustments",
        "qoh_adjustments_entries",
        "qoh_adjustments_entry_patches",
        "order_rules",
        "order_rules_entries",
        "order_rules_entry_patches",
        "vendor_codes_used",
        "vendor_codes_used_entries",
        "filtered_items_row_patches",
        "last_removed_bulk_items",
    )
    for key in optional_keys:
        if key in normalized_before and key in normalized_after and normalized_before[key] == normalized_after[key]:
            normalized_before.pop(key, None)
            normalized_after.pop(key, None)
    normalized_before = _prune_empty_bulk_history_state_sections(normalized_before)
    normalized_after = _prune_empty_bulk_history_state_sections(normalized_after)
    return normalized_before, normalized_after


def compact_bulk_history_state_pair(before_state, after_state):
    return _prune_unchanged_bulk_history_state(before_state, after_state)


def bulk_history_states_equivalent(left_state, right_state):
    normalized_left, normalized_right = compact_bulk_history_state_pair(left_state, right_state)
    return normalized_left == normalized_right


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
    before_state, after_state = _prune_unchanged_bulk_history_state(before_state, after_state)
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


def restore_bulk_history_state(app, state, *, capture_spec=None):
    state = _prune_empty_bulk_history_state_sections(dict(state))
    row_scoped_restore = "filtered_items_rows" in state or "filtered_items_row_patches" in state
    touched_row_ids = []
    vendor_codes_changed = False
    if "filtered_items_rows" in state:
        for row_id, restored_item in state.get("filtered_items_rows", []):
            _idx, current_item = ui_bulk.resolve_bulk_row_id(app, row_id)
            if current_item is None:
                continue
            before_summary_item = ui_bulk.bulk_filter_bucket_snapshot(current_item)
            sanitized_item = _sanitize_bulk_history_item(restored_item)
            current_item.clear()
            current_item.update(sanitized_item)
            ui_bulk.adjust_bulk_summary_for_item_change(
                app,
                before_summary_item,
                ui_bulk.bulk_filter_bucket_snapshot(current_item),
                item=current_item,
            )
            touched_row_ids.append(str(row_id))
        ui_bulk.invalidate_bulk_row_render_entries(app, touched_row_ids)
    elif "filtered_items_row_patches" in state:
        touched_row_ids = _restore_bulk_history_row_patches_in_place(
            app,
            state.get("filtered_items_row_patches", []),
        )
        ui_bulk.invalidate_bulk_row_render_entries(app, touched_row_ids)
    elif "filtered_items" in state:
        ui_bulk.replace_filtered_items(app, _copy_bulk_history_items(state.get("filtered_items", [])))
    if "inventory_lookup" in state:
        app.inventory_lookup = copy.deepcopy(state.get("inventory_lookup", {}))
    else:
        if "inventory_lookup_entries" in state:
            _restore_bulk_history_mapping_entries_in_place(app.inventory_lookup, state.get("inventory_lookup_entries", []))
        if "inventory_lookup_entry_patches" in state:
            _restore_bulk_history_mapping_patches_in_place(app.inventory_lookup, state.get("inventory_lookup_entry_patches", []))
    if "qoh_adjustments" in state:
        app.qoh_adjustments = copy.deepcopy(state.get("qoh_adjustments", {}))
    else:
        if "qoh_adjustments_entries" in state:
            _restore_bulk_history_mapping_entries_in_place(app.qoh_adjustments, state.get("qoh_adjustments_entries", []))
        if "qoh_adjustments_entry_patches" in state:
            _restore_bulk_history_mapping_patches_in_place(app.qoh_adjustments, state.get("qoh_adjustments_entry_patches", []))
    if "order_rules" in state:
        app.order_rules = copy.deepcopy(state.get("order_rules", {}))
    else:
        if "order_rules_entries" in state:
            _restore_bulk_history_mapping_entries_in_place(app.order_rules, state.get("order_rules_entries", []))
        if "order_rules_entry_patches" in state:
            _restore_bulk_history_mapping_patches_in_place(app.order_rules, state.get("order_rules_entry_patches", []))
    if "vendor_codes_used" in state:
        restored_vendor_codes = list(state.get("vendor_codes_used", []))
        vendor_codes_changed = list(getattr(app, "vendor_codes_used", [])) != restored_vendor_codes
        app.vendor_codes_used = restored_vendor_codes
    elif "vendor_codes_used_entries" in state:
        vendor_codes_changed = _restore_bulk_history_vendor_code_entries_in_place(
            app.vendor_codes_used,
            state.get("vendor_codes_used_entries", []),
        )
    if "last_removed_bulk_items" in state:
        app.last_removed_bulk_items = list(state.get("last_removed_bulk_items", []))
    if vendor_codes_changed:
        app._refresh_vendor_inputs()
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
    refreshed = False
    changed_columns = tuple((capture_spec or {}).get("changed_columns", ()))
    if row_scoped_restore and touched_row_ids and hasattr(app, "_refresh_bulk_view_after_edit"):
        try:
            refreshed = bool(app._refresh_bulk_view_after_edit(touched_row_ids, changed_cols=changed_columns))
        except TypeError:
            refreshed = bool(app._refresh_bulk_view_after_edit(touched_row_ids))
    if not refreshed and getattr(app, "bulk_sheet", None):
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


def _bulk_history_row_vendor_codes(app, row_ids):
    vendor_codes = []
    seen = set()
    for row_id in row_ids:
        _idx, item = ui_bulk.resolve_bulk_row_id(app, row_id)
        if item is None:
            continue
        vendor = str(item.get("vendor", "") or "").strip()
        if not vendor or vendor in seen:
            continue
        seen.add(vendor)
        vendor_codes.append(vendor)
    return tuple(vendor_codes)


def _copy_bulk_history_mapping_entries(mapping, keys):
    entries = []
    for key in keys:
        if key in mapping:
            entries.append((copy.deepcopy(key), True, copy.deepcopy(mapping[key])))
        else:
            entries.append((copy.deepcopy(key), False, None))
    return entries


def _copy_bulk_history_vendor_code_entries(vendor_codes_used, vendor_codes):
    normalized = [str(code or "").strip() for code in list(vendor_codes_used or [])]
    entries = []
    for vendor in vendor_codes:
        if vendor in normalized:
            entries.append((vendor, True, normalized.index(vendor)))
        else:
            entries.append((vendor, False, None))
    return entries


def _prune_unchanged_bulk_history_entries(before_state, after_state, key):
    if key not in before_state or key not in after_state:
        return before_state, after_state
    before_entries = list(before_state.get(key, ()))
    after_entries = list(after_state.get(key, ()))
    if not before_entries or not after_entries:
        return before_state, after_state
    before_by_id = {entry[0]: entry for entry in before_entries}
    after_by_id = {entry[0]: entry for entry in after_entries}
    unchanged_ids = {
        entry_id
        for entry_id in before_by_id.keys() & after_by_id.keys()
        if before_by_id[entry_id] == after_by_id[entry_id]
    }
    if not unchanged_ids:
        return before_state, after_state
    before_pruned = [entry for entry in before_entries if entry[0] not in unchanged_ids]
    after_pruned = [entry for entry in after_entries if entry[0] not in unchanged_ids]
    if before_pruned:
        before_state[key] = before_pruned
    else:
        before_state.pop(key, None)
    if after_pruned:
        after_state[key] = after_pruned
    else:
        after_state.pop(key, None)
    return before_state, after_state


def _normalize_bulk_history_state_pair_shapes(before_state, after_state):
    before_state, after_state = _normalize_bulk_history_item_pair_shapes(
        before_state,
        after_state,
        "filtered_items_rows",
        "filtered_items_row_patches",
    )
    before_state, after_state = _normalize_bulk_history_mapping_pair_shapes(
        before_state,
        after_state,
        "inventory_lookup_entries",
        "inventory_lookup_entry_patches",
    )
    before_state, after_state = _normalize_bulk_history_mapping_pair_shapes(
        before_state,
        after_state,
        "qoh_adjustments_entries",
        "qoh_adjustments_entry_patches",
    )
    before_state, after_state = _normalize_bulk_history_mapping_pair_shapes(
        before_state,
        after_state,
        "order_rules_entries",
        "order_rules_entry_patches",
    )
    return before_state, after_state


def _prune_empty_bulk_history_state_sections(state):
    for key in (
        "filtered_items_rows",
        "inventory_lookup_entries",
        "qoh_adjustments_entries",
        "order_rules_entries",
        "vendor_codes_used_entries",
    ):
        if key in state and not list(state.get(key, ())):
            state.pop(key, None)
    for key in (
        "filtered_items_row_patches",
        "inventory_lookup_entry_patches",
        "qoh_adjustments_entry_patches",
        "order_rules_entry_patches",
    ):
        if key not in state:
            continue
        pruned_entries = [
            (entry_id, patch_entries)
            for entry_id, patch_entries in list(state.get(key, ()))
            if list(patch_entries or ())
        ]
        if pruned_entries:
            state[key] = pruned_entries
        else:
            state.pop(key, None)
    return state


def _normalize_bulk_history_item_pair_shapes(before_state, after_state, rows_key, patches_key):
    before_rows = before_state.get(rows_key)
    after_rows = after_state.get(rows_key)
    before_patches = before_state.get(patches_key)
    after_patches = after_state.get(patches_key)
    if before_rows is not None and after_rows is None and after_patches is not None:
        inflated = _inflate_bulk_history_item_rows(before_rows, after_patches)
        if inflated is not None:
            after_state[rows_key] = inflated
            after_state.pop(patches_key, None)
    elif after_rows is not None and before_rows is None and before_patches is not None:
        inflated = _inflate_bulk_history_item_rows(after_rows, before_patches)
        if inflated is not None:
            before_state[rows_key] = inflated
            before_state.pop(patches_key, None)
    return before_state, after_state


def _normalize_bulk_history_mapping_pair_shapes(before_state, after_state, entries_key, patches_key):
    before_entries = before_state.get(entries_key)
    after_entries = after_state.get(entries_key)
    before_patches = before_state.get(patches_key)
    after_patches = after_state.get(patches_key)
    if before_entries is not None and after_entries is None and after_patches is not None:
        inflated = _inflate_bulk_history_mapping_entries(before_entries, after_patches)
        if inflated is not None:
            after_state[entries_key] = inflated
            after_state.pop(patches_key, None)
    elif after_entries is not None and before_entries is None and before_patches is not None:
        inflated = _inflate_bulk_history_mapping_entries(after_entries, before_patches)
        if inflated is not None:
            before_state[entries_key] = inflated
            before_state.pop(patches_key, None)
    return before_state, after_state


def _inflate_bulk_history_item_rows(base_rows, patch_rows):
    base_by_id = {row_id: item for row_id, item in list(base_rows or [])}
    patch_by_id = {row_id: patch_entries for row_id, patch_entries in list(patch_rows or [])}
    if tuple(base_by_id.keys()) != tuple(patch_by_id.keys()):
        return None
    inflated = []
    for row_id, item in list(base_rows or []):
        inflated.append((row_id, _apply_bulk_history_item_patch(item, patch_by_id.get(row_id, ()))))
    return inflated


def _inflate_bulk_history_mapping_entries(base_entries, patch_entries):
    base_by_id = {entry_id: (present, value) for entry_id, present, value in list(base_entries or [])}
    patch_by_id = {entry_id: patch for entry_id, patch in list(patch_entries or [])}
    if tuple(base_by_id.keys()) != tuple(patch_by_id.keys()):
        return None
    inflated = []
    for entry_id, present, value in list(base_entries or []):
        patch = patch_by_id.get(entry_id, ())
        if not present or not isinstance(value, dict):
            return None
        inflated.append((entry_id, True, _apply_bulk_history_item_patch(value, patch)))
    return inflated


def _compact_bulk_history_mapping_entry_patches(before_state, after_state, entry_key, patch_key):
    if entry_key not in before_state or entry_key not in after_state:
        return before_state, after_state
    before_entries = list(before_state.get(entry_key, ()))
    after_entries = list(after_state.get(entry_key, ()))
    if not before_entries or not after_entries:
        return before_state, after_state
    before_by_id = {entry[0]: entry for entry in before_entries}
    after_by_id = {entry[0]: entry for entry in after_entries}
    if tuple(before_by_id.keys()) != tuple(after_by_id.keys()):
        return before_state, after_state
    remaining_before_entries = []
    remaining_after_entries = []
    before_patch_entries = []
    after_patch_entries = []
    for entry_id, before_present, before_value in before_entries:
        _after_id, after_present, after_value = after_by_id[entry_id]
        if before_present and after_present and isinstance(before_value, dict) and isinstance(after_value, dict):
            before_patch, after_patch = _build_bulk_history_item_patch_pair(before_value, after_value)
            before_patch_entries.append((entry_id, before_patch))
            after_patch_entries.append((entry_id, after_patch))
        else:
            remaining_before_entries.append((entry_id, before_present, before_value))
            remaining_after_entries.append(after_by_id[entry_id])
    if before_patch_entries:
        before_state[patch_key] = before_patch_entries
        after_state[patch_key] = after_patch_entries
    if remaining_before_entries:
        before_state[entry_key] = remaining_before_entries
    else:
        before_state.pop(entry_key, None)
    if remaining_after_entries:
        after_state[entry_key] = remaining_after_entries
    else:
        after_state.pop(entry_key, None)
    return before_state, after_state


def _compact_bulk_history_row_patches(before_state, after_state):
    if "filtered_items_rows" not in before_state or "filtered_items_rows" not in after_state:
        return before_state, after_state
    before_rows = list(before_state.get("filtered_items_rows", ()))
    after_rows = list(after_state.get("filtered_items_rows", ()))
    if not before_rows or not after_rows:
        return before_state, after_state
    before_by_id = {row_id: item for row_id, item in before_rows}
    after_by_id = {row_id: item for row_id, item in after_rows}
    if tuple(before_by_id.keys()) != tuple(after_by_id.keys()):
        return before_state, after_state
    before_patches = []
    after_patches = []
    for row_id, before_item in before_rows:
        after_item = after_by_id.get(row_id)
        if after_item is None:
            return before_state, after_state
        before_patch, after_patch = _build_bulk_history_item_patch_pair(before_item, after_item)
        before_patches.append((row_id, before_patch))
        after_patches.append((row_id, after_patch))
    before_state.pop("filtered_items_rows", None)
    after_state.pop("filtered_items_rows", None)
    if before_patches:
        before_state["filtered_items_row_patches"] = before_patches
    if after_patches:
        after_state["filtered_items_row_patches"] = after_patches
    return before_state, after_state


def _build_bulk_history_item_patch_pair(before_item, after_item):
    before_patch = []
    after_patch = []
    ordered_keys = []
    seen = set()
    for key in list(before_item.keys()) + list(after_item.keys()):
        if key in seen:
            continue
        seen.add(key)
        ordered_keys.append(key)
    for key in ordered_keys:
        before_present = key in before_item
        after_present = key in after_item
        before_value = before_item.get(key)
        after_value = after_item.get(key)
        if before_present == after_present and before_value == after_value:
            continue
        before_patch.append((key, before_present, copy.deepcopy(before_value) if before_present else None))
        after_patch.append((key, after_present, copy.deepcopy(after_value) if after_present else None))
    return before_patch, after_patch


def _apply_bulk_history_item_patch(item, patch_entries):
    updated = copy.deepcopy(item)
    for field_name, present, value in list(patch_entries or []):
        if present:
            updated[field_name] = copy.deepcopy(value)
        else:
            updated.pop(field_name, None)
    return updated


def _restore_bulk_history_mapping_entries(current_mapping, entries):
    restored = copy.deepcopy(current_mapping)
    for key, present, value in entries:
        if present:
            restored[key] = copy.deepcopy(value)
        else:
            restored.pop(key, None)
    return restored


def _restore_bulk_history_mapping_entries_in_place(current_mapping, entries):
    for key, present, value in entries:
        if present:
            current_mapping[key] = copy.deepcopy(value)
        else:
            current_mapping.pop(key, None)
    return current_mapping


def _restore_bulk_history_mapping_patches_in_place(current_mapping, entry_patches):
    for key, patch_entries in entry_patches:
        normalized_patch_entries = list(patch_entries or ())
        if not normalized_patch_entries:
            continue
        current_value = current_mapping.get(key)
        if not isinstance(current_value, dict):
            current_value = {}
            current_mapping[key] = current_value
        for field_name, present, value in normalized_patch_entries:
            if present:
                current_value[field_name] = copy.deepcopy(value)
            else:
                current_value.pop(field_name, None)
        if not current_value:
            current_mapping.pop(key, None)
    return current_mapping


def _restore_bulk_history_vendor_code_entries_in_place(current_vendor_codes, entries):
    changed = False
    for vendor, present, index in entries:
        normalized_vendor = str(vendor or "").strip()
        if not normalized_vendor:
            continue
        try:
            current_index = current_vendor_codes.index(normalized_vendor)
        except ValueError:
            current_index = None
        if present:
            target_index = max(0, min(int(index or 0), len(current_vendor_codes)))
            if current_index is None:
                current_vendor_codes.insert(target_index, normalized_vendor)
                changed = True
                continue
            if current_index != target_index:
                current_vendor_codes.pop(current_index)
                target_index = max(0, min(target_index, len(current_vendor_codes)))
                current_vendor_codes.insert(target_index, normalized_vendor)
                changed = True
        elif current_index is not None:
            current_vendor_codes.pop(current_index)
            changed = True
    return changed


def _restore_bulk_history_row_patches_in_place(app, row_patches):
    touched_row_ids = []
    for row_id, patch_entries in row_patches:
        if not list(patch_entries or ()):
            continue
        _idx, current_item = ui_bulk.resolve_bulk_row_id(app, row_id)
        if current_item is None:
            continue
        before_summary_item = ui_bulk.bulk_filter_bucket_snapshot(current_item)
        for field_name, present, value in patch_entries:
            if present:
                current_item[field_name] = copy.deepcopy(value)
            else:
                current_item.pop(field_name, None)
        ui_bulk.adjust_bulk_summary_for_item_change(
            app,
            before_summary_item,
            ui_bulk.bulk_filter_bucket_snapshot(current_item),
            item=current_item,
        )
        touched_row_ids.append(str(row_id))
    return touched_row_ids
