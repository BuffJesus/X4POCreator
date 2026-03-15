import ui_bulk


def remove_filtered_rows(app, remove_indices, deepcopy, *, history_label="remove:bulk"):
    unique_indices = sorted({int(idx) for idx in remove_indices if idx is not None}, reverse=True)
    if not unique_indices:
        return []
    before_state = app._capture_bulk_history_state() if hasattr(app, "_capture_bulk_history_state") else None
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
        app._finalize_bulk_history_action(history_label, before_state)
    return removed_payload
