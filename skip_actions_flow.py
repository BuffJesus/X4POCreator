"""Pure helpers for the Skip Cleanup Tools feature.

Operates on the items that v0.5.4 → v0.6.5 made visible in the Skip
filter — items where the system has nothing to order (`final_qty <= 0`
and `raw_need <= 0`).  Helpers stay pure (no tk, no app state) so the
business logic is unit-testable independently of the dialog wiring.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping


def is_skip_item(item: Mapping[str, Any]) -> bool:
    """Return True if *item* is currently in the Skip status bucket.

    Mirrors the canonical definition from `rules.evaluate_item_status`:
    `final_qty <= 0` AND `raw_need <= 0`.  Doesn't read `item["status"]`
    directly because the field is sometimes stale on items copied
    around between flows; the underlying numbers are the source of
    truth.
    """
    if not isinstance(item, Mapping):
        return False
    try:
        final_qty = float(item.get("final_qty", 0) or 0)
    except (TypeError, ValueError):
        final_qty = 0.0
    try:
        raw_need = float(item.get("raw_need", 0) or 0)
    except (TypeError, ValueError):
        raw_need = 0.0
    return final_qty <= 0 and raw_need <= 0


def filter_skip_items(items: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Return only the items that match `is_skip_item`."""
    return [item for item in items or () if is_skip_item(item)]


def count_skip_clusters_by_line_code(items: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Group skip items by line code and return per-cluster counts.

    Operators almost always want to act on a whole line code at a time
    rather than per-individual-item, so this is the helper that drives
    the per-line-code grouped view.

    Returns a list of dicts:
        [{"line_code": "025-", "count": 142}, ...]
    sorted by `(-count, line_code)` — biggest clusters first,
    alphabetical tie-break.
    """
    counts: Counter = Counter()
    for item in items or ():
        if not isinstance(item, Mapping) or not is_skip_item(item):
            continue
        line_code = str(item.get("line_code", "") or "")
        counts[line_code] += 1
    rows = [{"line_code": lc, "count": c} for lc, c in counts.items()]
    rows.sort(key=lambda r: (-r["count"], r["line_code"]))
    return rows


def collect_keys_for_action(items: Iterable[Mapping[str, Any]]) -> List[tuple]:
    """Return `(line_code, item_code)` tuples for items the action should touch.

    Skips items that are missing one of the two parts of the key —
    those can't be applied cleanly through the existing ignore /
    discontinue flows.
    """
    keys = []
    for item in items or ():
        if not isinstance(item, Mapping):
            continue
        lc = str(item.get("line_code", "") or "").strip()
        ic = str(item.get("item_code", "") or "").strip()
        if not ic:
            continue
        keys.append((lc, ic))
    return keys


def collect_ignore_keys(items: Iterable[Mapping[str, Any]]) -> List[str]:
    """Return `LC:IC` strings ready for `ignore_items_by_keys`."""
    return [f"{lc}:{ic}" for lc, ic in collect_keys_for_action(items)]


def build_skip_export_rows(
    items: Iterable[Mapping[str, Any]],
    inventory_lookup: Mapping[tuple, Mapping[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Build the row dicts for the Skip CSV export.

    One row per skip item, with the columns operators want when doing
    an offline review pass before triggering bulk ignore / discontinue:
    line code, item code, description, qoh, last sale date, last
    receipt date, and the per-item suggested min/max anchors when
    available.

    *inventory_lookup* is `session.inventory_lookup` (keyed by
    `(line_code, item_code)`).  When None, the helper falls back to
    whatever the item itself carries.
    """
    inventory_lookup = inventory_lookup or {}
    rows: List[Dict[str, Any]] = []
    for item in items or ():
        if not isinstance(item, Mapping) or not is_skip_item(item):
            continue
        lc = str(item.get("line_code", "") or "")
        ic = str(item.get("item_code", "") or "")
        inv = inventory_lookup.get((lc, ic)) or item.get("inventory") or {}
        if not isinstance(inv, Mapping):
            inv = {}
        rows.append({
            "line_code": lc,
            "item_code": ic,
            "description": str(item.get("description", "") or ""),
            "qoh": inv.get("qoh", ""),
            "current_min": inv.get("min", "") if inv.get("min") is not None else "",
            "current_max": inv.get("max", "") if inv.get("max") is not None else "",
            "supplier": inv.get("supplier", ""),
            "last_sale_date": item.get("last_sale_date", "") or inv.get("last_sale", ""),
            "last_receipt_date": item.get("last_receipt_date", "") or inv.get("last_receipt", ""),
            "suggested_min": item.get("suggested_min", "") if item.get("suggested_min") is not None else "",
            "suggested_max": item.get("suggested_max", "") if item.get("suggested_max") is not None else "",
        })
    rows.sort(key=lambda r: (r["line_code"], r["item_code"]))
    return rows


SKIP_EXPORT_COLUMNS = (
    "line_code",
    "item_code",
    "description",
    "qoh",
    "current_min",
    "current_max",
    "supplier",
    "last_sale_date",
    "last_receipt_date",
    "suggested_min",
    "suggested_max",
)


def render_skip_csv(rows: List[Dict[str, Any]]) -> str:
    """Render *rows* as CSV text using `SKIP_EXPORT_COLUMNS` column order."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=SKIP_EXPORT_COLUMNS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows or ():
        writer.writerow(row)
    return buffer.getvalue()
