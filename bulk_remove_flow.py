import perf_trace
import ui_bulk
import session_state_flow


def remove_filtered_rows(app, remove_indices, deepcopy, *, history_label="remove:bulk", expected_keys=None):
    with perf_trace.span(
        "bulk_remove_flow.remove_filtered_rows",
        history_label=history_label,
        requested=len(remove_indices) if remove_indices else 0,
    ):
        return _remove_filtered_rows_inner(app, remove_indices, deepcopy, history_label=history_label, expected_keys=expected_keys)


def _remove_filtered_rows_inner(app, remove_indices, deepcopy, *, history_label="remove:bulk", expected_keys=None):
    unique_indices = sorted({int(idx) for idx in remove_indices if idx is not None}, reverse=True)
    if not unique_indices:
        return []
    capture_spec = session_state_flow.bulk_history_capture_spec(last_removed_bulk_items=True)
    before_state = None
    capture = getattr(app, "_capture_bulk_history_state", None)
    if callable(capture):
        try:
            before_state = capture(capture_spec=capture_spec)
        except TypeError:
            before_state = capture()
    filtered_items = list(getattr(app, "filtered_items", ()) or ())
    removed_payload = []
    protected_payload = []
    skipped_payload = []
    protect_item = getattr(app, "_is_bulk_removal_protected", None)
    for idx in unique_indices:
        if not (0 <= idx < len(filtered_items)):
            skipped_payload.append((idx, "out_of_range"))
            continue
        item = filtered_items[idx]
        if expected_keys is not None:
            expected = expected_keys.get(idx)
            if expected is not None:
                actual = (item.get("line_code", ""), item.get("item_code", ""))
                if actual != expected:
                    # Row at this index is no longer the row the caller
                    # asked to remove (filter changed underneath us, items
                    # were re-sorted, etc.).  Record it instead of silently
                    # dropping so callers can surface the discrepancy.
                    skipped_payload.append((idx, "key_mismatch"))
                    continue
        protected = False
        protected_reason = ""
        if callable(protect_item):
            try:
                protected, protected_reason = protect_item(item, history_label=history_label)
            except TypeError:
                protected = bool(protect_item(item))
        if protected:
            preserved = deepcopy(item)
            if protected_reason:
                preserved["_removal_protection_reason"] = protected_reason
            protected_payload.append((idx, preserved))
            continue
        removed_payload.append((idx, deepcopy(item)))
        filtered_items.pop(idx)
    app.last_protected_bulk_items = protected_payload
    app.last_skipped_bulk_removals = skipped_payload
    if not removed_payload:
        # Reset the prior removal payload too — otherwise undo / status
        # banners would still surface a stale "X items removed" record from
        # an earlier call when the current call removed nothing.
        app.last_removed_bulk_items = []
        return []
    ui_bulk.replace_filtered_items(app, filtered_items)
    app.last_removed_bulk_items = removed_payload
    if hasattr(app, "_finalize_bulk_history_action"):
        try:
            app._finalize_bulk_history_action(history_label, before_state, capture_spec=capture_spec)
        except TypeError:
            app._finalize_bulk_history_action(history_label, before_state)
    return removed_payload
