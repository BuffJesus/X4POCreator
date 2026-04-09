"""Pure functions for the supplier → vendor auto-mapping feature.

The map persists `{supplier_code: vendor_code}` to
`supplier_vendor_map.json` alongside the other config files.  Operators
can edit it manually in the dialog or auto-learn from prior session
snapshots.

All helpers in this module are pure (no tk, no app state) so they can
be unit-tested without a UI.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from typing import Dict, Iterable, List, Mapping, Tuple


def _normalize_code(value) -> str:
    return str(value or "").strip().upper()


def load_supplier_map(path: str) -> Dict[str, str]:
    """Load `{supplier_code: vendor_code}` from *path*.

    Returns an empty dict when the file is missing or malformed —
    callers can treat that as a clean starting state.
    """
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    mapping: Dict[str, str] = {}
    for supplier, vendor in raw.items():
        s = _normalize_code(supplier)
        v = _normalize_code(vendor)
        if s and v:
            mapping[s] = v
    return mapping


def save_supplier_map(path: str, mapping: Mapping[str, str]) -> None:
    """Atomically persist *mapping* to *path*.

    Empty / blank entries are stripped.  Writes go through a tempfile +
    rename so a crashed write can never leave a half-formed JSON file
    in place.
    """
    if not path:
        raise ValueError("path is required")
    cleaned: Dict[str, str] = {}
    for supplier, vendor in (mapping or {}).items():
        s = _normalize_code(supplier)
        v = _normalize_code(vendor)
        if s and v:
            cleaned[s] = v
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".supplier_map.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cleaned, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _supplier_for_item(item: Mapping) -> str:
    """Pull the supplier code off an item, looking in the usual places."""
    if not isinstance(item, Mapping):
        return ""
    inv = item.get("inventory") or {}
    candidate = inv.get("supplier") if isinstance(inv, Mapping) else ""
    if not candidate:
        candidate = item.get("supplier", "")
    return _normalize_code(candidate)


def apply_supplier_map(
    items: Iterable[Mapping],
    mapping: Mapping[str, str],
) -> List[Tuple[Mapping, str]]:
    """Return `(item, vendor_code)` pairs for unassigned items the map covers.

    Items that already have a `vendor` field are skipped — manual
    assignments always win.  Items with no supplier (or a supplier the
    map doesn't cover) are skipped silently.  The caller decides
    whether to mutate the items or just preview the proposed changes.
    """
    if not mapping:
        return []
    normalized_map = {
        _normalize_code(s): _normalize_code(v)
        for s, v in mapping.items()
        if _normalize_code(s) and _normalize_code(v)
    }
    if not normalized_map:
        return []
    pairs: List[Tuple[Mapping, str]] = []
    for item in items or ():
        if not isinstance(item, Mapping):
            continue
        existing_vendor = _normalize_code(item.get("vendor", ""))
        if existing_vendor:
            continue
        supplier = _supplier_for_item(item)
        if not supplier:
            continue
        vendor = normalized_map.get(supplier)
        if vendor:
            pairs.append((item, vendor))
    return pairs


def build_supplier_map_from_history(snapshots: Iterable[Mapping]) -> Dict[str, str]:
    """Infer `supplier → most-frequently-used vendor` from session snapshots.

    Walks `exported_items` (preferred) and falls back to `assigned_items`
    on each snapshot, counts `(supplier, vendor)` co-occurrences, and
    returns `{supplier: most_common_vendor}`.  Ties are broken by
    insertion order — `Counter.most_common(1)` is stable enough for the
    rare ambiguous case.

    Snapshots without supplier or vendor evidence on an item contribute
    nothing.  An empty / missing input returns an empty dict.
    """
    counts: Dict[str, Counter] = {}
    for snapshot in snapshots or ():
        if not isinstance(snapshot, Mapping):
            continue
        items = snapshot.get("exported_items") or snapshot.get("assigned_items") or ()
        for item in items:
            if not isinstance(item, Mapping):
                continue
            vendor = _normalize_code(item.get("vendor", ""))
            if not vendor:
                continue
            supplier = _supplier_for_item(item)
            if not supplier:
                continue
            counts.setdefault(supplier, Counter())[vendor] += 1
    inferred: Dict[str, str] = {}
    for supplier, vendor_counts in counts.items():
        most_common = vendor_counts.most_common(1)
        if most_common:
            inferred[supplier] = most_common[0][0]
    return inferred


def merge_supplier_maps(
    base: Mapping[str, str],
    overlay: Mapping[str, str],
    *,
    overlay_wins: bool = False,
) -> Dict[str, str]:
    """Combine two maps.

    By default *base* wins (manual entries take precedence over inferred
    suggestions); set ``overlay_wins=True`` to flip that.
    """
    merged: Dict[str, str] = {}
    # The last source iterated wins on conflict, so put the higher-
    # precedence source second.
    sources = (base, overlay) if overlay_wins else (overlay, base)
    for source in sources:
        for supplier, vendor in (source or {}).items():
            s = _normalize_code(supplier)
            v = _normalize_code(vendor)
            if s and v:
                merged[s] = v
    return merged
