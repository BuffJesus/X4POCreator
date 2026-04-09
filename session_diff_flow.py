"""Pure helpers for the Session Diff feature.

Compares the current in-progress session against the most recent
snapshot in `sessions/` and reports what changed.  All helpers are
pure (no tk, no app state) so they can be unit-tested without a UI.

Snapshot dicts come from `storage.load_session_snapshots`; each one
exposes `exported_items` (preferred) and `assigned_items` (fallback).
Each item in those lists has at least `line_code`, `item_code`,
`final_qty` (or `order_qty`), and `vendor`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple


ItemKey = Tuple[str, str]


def _norm_key(item: Mapping[str, Any]) -> Optional[ItemKey]:
    line_code = str(item.get("line_code", "") or "").strip()
    item_code = str(item.get("item_code", "") or "").strip()
    if not item_code:
        return None
    return (line_code, item_code)


def _norm_qty(item: Mapping[str, Any]) -> int:
    for field in ("final_qty", "order_qty"):
        value = item.get(field)
        if value in (None, ""):
            continue
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            continue
    return 0


def _norm_vendor(item: Mapping[str, Any]) -> str:
    return str(item.get("vendor", "") or "").strip().upper()


def _items_from_snapshot(snapshot: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Pull the per-item list from a snapshot, preferring exported_items."""
    if not isinstance(snapshot, Mapping):
        return []
    items = snapshot.get("exported_items")
    if not items:
        items = snapshot.get("assigned_items")
    if not items:
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _index_by_key(items: List[Mapping[str, Any]]) -> Dict[ItemKey, Mapping[str, Any]]:
    """Build `{(line_code, item_code): item}` keeping the first occurrence."""
    index: Dict[ItemKey, Mapping[str, Any]] = {}
    for item in items:
        key = _norm_key(item)
        if key is None or key in index:
            continue
        index[key] = item
    return index


def load_previous_snapshot(sessions_dir: str, *, loader=None) -> Optional[Mapping[str, Any]]:
    """Return the most recent snapshot in *sessions_dir*, or None.

    *loader* is an optional injection point for tests so they don't
    have to fake the filesystem.  Defaults to
    `storage.load_session_snapshots` when not supplied.
    """
    if loader is None:
        from storage import load_session_snapshots as loader  # local import keeps tests fast
    snapshots = loader(sessions_dir, max_count=1) or []
    return snapshots[0] if snapshots else None


def diff_sessions(
    previous: Optional[Mapping[str, Any]],
    current: Optional[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Compare two snapshots and return a categorized diff.

    Returns a dict with five keys, each a list of dicts:
        - new_items        — keys in current but not previous
        - removed_items    — keys in previous but not current
        - qty_increased    — same key, current qty > previous qty
        - qty_decreased    — same key, current qty < previous qty
        - vendor_changed   — same key, vendor differs (case-insensitive)

    Each row carries `line_code`, `item_code`, `description`, plus the
    relevant before/after fields (`old_qty`/`new_qty`/`delta` for the
    qty buckets, `old_vendor`/`new_vendor` for vendor change).

    Either side can be `None` (or empty) — that's a clean
    "everything is new" or "everything was removed" diff.
    """
    prev_items = _items_from_snapshot(previous or {})
    curr_items = _items_from_snapshot(current or {})
    prev_index = _index_by_key(prev_items)
    curr_index = _index_by_key(curr_items)

    new_items: List[Dict[str, Any]] = []
    removed_items: List[Dict[str, Any]] = []
    qty_increased: List[Dict[str, Any]] = []
    qty_decreased: List[Dict[str, Any]] = []
    vendor_changed: List[Dict[str, Any]] = []

    def _row(key: ItemKey, item: Mapping[str, Any], **extras) -> Dict[str, Any]:
        return {
            "line_code": key[0],
            "item_code": key[1],
            "description": str(item.get("description", "") or ""),
            **extras,
        }

    for key, item in curr_index.items():
        if key not in prev_index:
            new_items.append(_row(key, item, qty=_norm_qty(item), vendor=_norm_vendor(item)))
            continue
        prev_item = prev_index[key]
        old_qty = _norm_qty(prev_item)
        new_qty = _norm_qty(item)
        old_vendor = _norm_vendor(prev_item)
        new_vendor = _norm_vendor(item)
        if new_qty > old_qty:
            qty_increased.append(_row(
                key, item,
                old_qty=old_qty, new_qty=new_qty, delta=new_qty - old_qty,
            ))
        elif new_qty < old_qty:
            qty_decreased.append(_row(
                key, item,
                old_qty=old_qty, new_qty=new_qty, delta=new_qty - old_qty,
            ))
        if old_vendor != new_vendor:
            vendor_changed.append(_row(
                key, item,
                old_vendor=old_vendor, new_vendor=new_vendor,
            ))

    for key, item in prev_index.items():
        if key not in curr_index:
            removed_items.append(_row(
                key, item,
                qty=_norm_qty(item), vendor=_norm_vendor(item),
            ))

    sort_key = lambda r: (r["line_code"], r["item_code"])
    return {
        "new_items": sorted(new_items, key=sort_key),
        "removed_items": sorted(removed_items, key=sort_key),
        "qty_increased": sorted(qty_increased, key=sort_key),
        "qty_decreased": sorted(qty_decreased, key=sort_key),
        "vendor_changed": sorted(vendor_changed, key=sort_key),
    }


def format_diff_summary(diff: Mapping[str, List[Any]]) -> str:
    """Build a one-line human-readable summary of *diff*.

    Returns "" when nothing changed so callers can use it as a
    truthiness check before showing a banner.
    """
    if not diff:
        return ""
    parts = []
    counts = (
        ("new_items", "new"),
        ("removed_items", "removed"),
        ("qty_increased", "qty up"),
        ("qty_decreased", "qty down"),
        ("vendor_changed", "vendor changed"),
    )
    for key, label in counts:
        n = len(diff.get(key) or ())
        if n:
            parts.append(f"{n} {label}")
    return ", ".join(parts)


def diff_total_count(diff: Mapping[str, List[Any]]) -> int:
    """Total number of changes across all categories.

    Note that an item can be counted in more than one bucket
    (qty_increased AND vendor_changed, for example), so this is the
    sum of bucket sizes, not a unique-item count.
    """
    if not diff:
        return 0
    return sum(len(diff.get(k) or ()) for k in (
        "new_items", "removed_items", "qty_increased", "qty_decreased", "vendor_changed",
    ))


def snapshot_label(snapshot: Optional[Mapping[str, Any]]) -> str:
    """Short label for the snapshot — its `created_at` if present."""
    if not isinstance(snapshot, Mapping):
        return ""
    return str(snapshot.get("created_at", "") or "").strip()
