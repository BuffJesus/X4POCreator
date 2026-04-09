"""Per-item notes persistence and helpers.

Notes are keyed by ``LC:IC`` (line_code:item_code) and stored as a
flat JSON dict in ``item_notes.json`` next to the executable or
script directory.
"""

import json
import os


def load_notes(path):
    """Load notes dict from *path*.  Returns {} on missing/corrupt file."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items() if v}
        return {}
    except Exception:
        return {}


def save_notes(path, notes):
    """Persist *notes* dict to *path* atomically."""
    clean = {k: str(v) for k, v in notes.items() if v and str(v).strip()}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return clean


def apply_notes_to_items(items, notes):
    """Merge notes into items in-place.  Fast O(n) pass."""
    if not notes:
        return
    for item in items:
        key = f"{item.get('line_code', '')}:{item.get('item_code', '')}"
        note = notes.get(key, "")
        if note:
            item["notes"] = note


def clear_notes_for_keys(notes, keys):
    """Remove notes for the given (line_code, item_code) tuples."""
    removed = 0
    for lc, ic in keys:
        k = f"{lc}:{ic}"
        if k in notes:
            del notes[k]
            removed += 1
    return removed
