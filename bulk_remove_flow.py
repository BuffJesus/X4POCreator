import ui_bulk
import session_state_flow


def remove_filtered_rows(app, remove_indices, deepcopy, *, history_label="remove:bulk"):
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
    protect_item = getattr(app, "_is_bulk_removal_protected", None)
    for idx in unique_indices:
        if 0 <= idx < len(filtered_items):
            item = filtered_items[idx]
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
    if not removed_payload:
        return []
    ui_bulk.replace_filtered_items(app, filtered_items)
    app.last_removed_bulk_items = removed_payload
    if hasattr(app, "_finalize_bulk_history_action"):
        try:
            app._finalize_bulk_history_action(history_label, before_state, capture_spec=capture_spec)
        except TypeError:
            app._finalize_bulk_history_action(history_label, before_state)
    return removed_payload
