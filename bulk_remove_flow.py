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
    for idx in unique_indices:
        if 0 <= idx < len(filtered_items):
            removed_payload.append((idx, deepcopy(filtered_items[idx])))
            filtered_items.pop(idx)
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
