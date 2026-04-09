"""Pure helpers for the QOH Adjustment Review feature.

`qoh_adjustments` on the session is `{(line_code, item_code): {"old": float, "new": float}}`,
populated by `bulk_edit_flow` whenever the operator edits the QOH cell on
the bulk grid.  This module formats those adjustments for review and
provides a pure revert helper that doesn't touch tk.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Tuple


def _coerce_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_qoh_adjustments(
    qoh_adjustments: Mapping[Tuple[str, str], Mapping[str, Any]],
    inventory_lookup: Mapping[Tuple[str, str], Mapping[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Build a sorted, review-friendly list of QOH adjustments.

    Returns one dict per non-zero-delta adjustment, sorted by
    (line_code, item_code).  Zero-delta entries are dropped — they
    represent edits the operator typed but didn't actually change.

    Each row contains:
        - line_code, item_code
        - description (looked up from *inventory_lookup* when present)
        - old_qoh, new_qoh, delta (delta = new - old)
    """
    inventory_lookup = inventory_lookup or {}
    rows: List[Dict[str, Any]] = []
    for key, payload in (qoh_adjustments or {}).items():
        if not isinstance(payload, Mapping):
            continue
        line_code, item_code = (key + ("", ""))[:2] if isinstance(key, tuple) else ("", "")
        old_qoh = _coerce_float(payload.get("old", 0))
        new_qoh = _coerce_float(payload.get("new", 0))
        delta = new_qoh - old_qoh
        if delta == 0:
            continue
        inv = inventory_lookup.get(key) or {}
        description = ""
        if isinstance(inv, Mapping):
            description = str(inv.get("description", "") or "").strip()
        rows.append({
            "line_code": str(line_code or ""),
            "item_code": str(item_code or ""),
            "description": description,
            "old_qoh": old_qoh,
            "new_qoh": new_qoh,
            "delta": delta,
        })
    rows.sort(key=lambda r: (r["line_code"], r["item_code"]))
    return rows


def revert_qoh_adjustments(
    qoh_adjustments: Dict[Tuple[str, str], Dict[str, Any]],
    inventory_lookup: Dict[Tuple[str, str], Dict[str, Any]],
    keys: Iterable[Tuple[str, str]],
) -> int:
    """Revert *keys* to their pre-edit QOH values.

    Mutates both `qoh_adjustments` (removes the entry) and
    `inventory_lookup` (restores the old qoh on the inventory record).
    Returns the number of keys actually reverted; missing keys are a
    no-op.

    The caller is responsible for re-running per-item recalculation and
    refreshing the bulk grid afterwards — keeping that out of this
    helper lets it stay pure-Python and unit-testable.
    """
    if not keys:
        return 0
    reverted = 0
    for key in list(keys):
        payload = qoh_adjustments.get(key)
        if not isinstance(payload, Mapping):
            continue
        old_qoh = _coerce_float(payload.get("old", 0))
        inv = inventory_lookup.get(key)
        if isinstance(inv, dict):
            inv["qoh"] = old_qoh
        qoh_adjustments.pop(key, None)
        reverted += 1
    return reverted
