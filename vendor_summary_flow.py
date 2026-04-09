"""Pure helpers for the Vendor Review feature.

Builds a per-vendor summary from session snapshots: how often the
operator has ordered from the vendor recently, what the inferred lead
time is, when the last receipt landed, and the top items by quantity.

All helpers are pure (no tk, no app state) so they can be unit-tested
without a UI.  The only thing they touch is the snapshot dicts that
`storage.load_session_snapshots` returns.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence


def _norm_vendor(value) -> str:
    return str(value or "").strip().upper()


def _items_from(snapshot: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    if not isinstance(snapshot, Mapping):
        return []
    items = snapshot.get("exported_items") or snapshot.get("assigned_items") or ()
    return [item for item in items if isinstance(item, Mapping)]


def _coerce_qty(value) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def summarize_vendor(
    vendor_code: str,
    snapshots: Sequence[Mapping[str, Any]],
    *,
    lead_times: Optional[Mapping[str, int]] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """Build a summary dict for a single vendor across *snapshots*.

    *snapshots* should be most-recent-first (as returned by
    `storage.load_session_snapshots`).  *lead_times* is the dict
    returned by `storage.infer_vendor_lead_times`; pass it in once
    and reuse across vendors instead of recomputing.

    Returns:
        {
            "vendor_code": "GRELIN",
            "session_count": 4,        # snapshots that included this vendor
            "order_count": 12,         # items ordered from this vendor
            "total_qty_ordered": 144,
            "total_qty_received": 80,
            "last_session_date": "2026-04-01T08:00:00",
            "inferred_lead_days": 7,    # None if unknown
            "top_items": [
                {"line_code": ..., "item_code": ..., "description": ..., "qty": ...},
                ...
            ],
        }
    """
    code = _norm_vendor(vendor_code)
    summary: Dict[str, Any] = {
        "vendor_code": code,
        "session_count": 0,
        "order_count": 0,
        "total_qty_ordered": 0,
        "total_qty_received": 0,
        "last_session_date": "",
        "inferred_lead_days": None,
        "top_items": [],
    }
    if not code:
        return summary
    if lead_times:
        summary["inferred_lead_days"] = lead_times.get(code)

    item_qty: Counter = Counter()
    item_descriptions: Dict[tuple, str] = {}

    for snapshot in snapshots or ():
        items = _items_from(snapshot)
        seen_in_snapshot = False
        snap_date = str((snapshot or {}).get("created_at", "") or "").strip()
        for item in items:
            if _norm_vendor(item.get("vendor")) != code:
                continue
            seen_in_snapshot = True
            summary["order_count"] += 1
            qty = _coerce_qty(item.get("final_qty") if item.get("final_qty") not in (None, "") else item.get("order_qty"))
            received = _coerce_qty(item.get("qty_received"))
            summary["total_qty_ordered"] += max(0, qty)
            summary["total_qty_received"] += max(0, received)
            key = (str(item.get("line_code") or ""), str(item.get("item_code") or ""))
            if key[1]:
                item_qty[key] += max(0, qty)
                desc = str(item.get("description") or "")
                if desc and key not in item_descriptions:
                    item_descriptions[key] = desc
        if seen_in_snapshot:
            summary["session_count"] += 1
            if not summary["last_session_date"] or snap_date > summary["last_session_date"]:
                summary["last_session_date"] = snap_date

    summary["top_items"] = [
        {
            "line_code": key[0],
            "item_code": key[1],
            "description": item_descriptions.get(key, ""),
            "qty": qty,
        }
        for key, qty in item_qty.most_common(max(0, int(top_n)))
    ]
    return summary


def summarize_all_vendors(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    vendor_codes: Optional[Sequence[str]] = None,
    lead_times: Optional[Mapping[str, int]] = None,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Summarize every vendor that appears in *snapshots*.

    If *vendor_codes* is supplied, restrict the output to that set
    (useful when the caller only wants the vendors used in the current
    session).  Otherwise every vendor that shows up across the
    snapshots is summarized.

    Result is sorted by `(-order_count, vendor_code)` — most-active
    first, alphabetical tie-break.
    """
    discovered: Counter = Counter()
    for snapshot in snapshots or ():
        for item in _items_from(snapshot):
            v = _norm_vendor(item.get("vendor"))
            if v:
                discovered[v] += 1
    if vendor_codes is not None:
        target = {_norm_vendor(code) for code in vendor_codes if _norm_vendor(code)}
    else:
        target = set(discovered)
    summaries = [
        summarize_vendor(code, snapshots, lead_times=lead_times, top_n=top_n)
        for code in sorted(target)
    ]
    summaries.sort(key=lambda s: (-int(s.get("order_count") or 0), s["vendor_code"]))
    return summaries


def strip_vendor_hint(value) -> str:
    """Pull the bare vendor code out of a hinted combobox label.

    The vendor combobox in the bulk grid renders entries as
    `GRELIN (lead ~7d)` so the operator can see lead time at the
    point of assignment.  When the field is read back the parens
    must be stripped or the apply path will try to use
    "GRELIN (LEAD ~7D)" as a vendor code.

    Returns the input verbatim when no parenthetical suffix is
    present.  Tolerates `None`.
    """
    text = str(value or "")
    cut = text.find(" (")
    if cut == -1:
        return text.strip()
    return text[:cut].strip()


def format_vendor_combo_value(vendor_code: str, lead_days: Optional[int]) -> str:
    """Render a vendor code with its inferred lead time for combobox display.

    Returns the bare code when *lead_days* is None / unknown so the
    combobox stays clean for vendors with no history.
    """
    code = _norm_vendor(vendor_code)
    label = format_lead_time_label(lead_days)
    if not code:
        return ""
    if not label:
        return code
    return f"{code} (lead {label})"


def format_lead_time_label(lead_days: Optional[int]) -> str:
    """Render an inferred lead time as a short label.

    Returns "" when *lead_days* is None so callers can use it as a
    truthiness check before appending to combobox values.
    """
    if lead_days is None:
        return ""
    try:
        days = int(lead_days)
    except (TypeError, ValueError):
        return ""
    if days <= 0:
        return ""
    return f"~{days}d"
