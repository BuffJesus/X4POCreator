"""
trend_flow.py — Build the per-item trend report from session snapshot history.

The trend report is a CSV export that surfaces:
  - the last 3 final (ordered) qtys for each item with at least 2 sessions of history
  - the last 3 suggested qtys for comparison
  - an inferred trend direction (increasing / decreasing / stable)
  - the operator override pattern (always_up / always_down / mixed / "")

This is a pure function module with no UI dependencies.
"""

_TREND_COLUMNS = [
    "Line Code",
    "Item Code",
    "Description",
    "Current Suggestion",
    "Ordered Qty 1",
    "Ordered Qty 2",
    "Ordered Qty 3",
    "Suggested Qty 1",
    "Suggested Qty 2",
    "Suggested Qty 3",
    "Trend",
    "Override Pattern",
]


def compute_override_pattern(entries):
    """Return 'always_up', 'always_down', 'mixed', or None.

    entries — list of dicts with 'final_qty' and 'suggested_qty' keys (most-recent first).
    Returns None when there are no overrides or insufficient data.
    """
    directions = []
    for e in entries:
        final = e.get("final_qty")
        suggested = e.get("suggested_qty")
        if final is None or suggested is None:
            continue
        if final > suggested:
            directions.append("up")
        elif final < suggested:
            directions.append("down")
    if not directions:
        return None
    if all(d == "up" for d in directions):
        return "always_up"
    if all(d == "down" for d in directions):
        return "always_down"
    return "mixed"


def _trend_direction(final_qtys):
    """Compare most-recent to oldest final qty to determine trend direction."""
    if len(final_qtys) < 2:
        return ""
    newest = final_qtys[0]
    oldest = final_qtys[-1]
    if newest > oldest:
        return "increasing"
    if newest < oldest:
        return "decreasing"
    return "stable"


def build_trend_report_rows(current_items, full_order_history):
    """
    Build trend report rows for items that appear in at least 2 session snapshots.

    current_items      — list of enriched item dicts from the current session
    full_order_history — dict from storage.extract_full_order_history():
                         (line_code, item_code) → [{final_qty, suggested_qty, created_at}, ...]
                         (most-recent first)

    Returns a list of dicts with keys matching _TREND_COLUMNS, ready to write as CSV.
    Only items with at least 2 historical entries are included.
    """
    rows = []
    for item in current_items:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        entries = full_order_history.get(key, [])
        if len(entries) < 2:
            continue
        final_qtys = [e["final_qty"] for e in entries]
        suggested_qtys = [e.get("suggested_qty") for e in entries]
        trend = _trend_direction(final_qtys)
        override_pattern = compute_override_pattern(entries) or ""
        row = {
            "Line Code": key[0],
            "Item Code": key[1],
            "Description": item.get("description", ""),
            "Current Suggestion": item.get("suggested_qty", ""),
            "Ordered Qty 1": final_qtys[0] if len(final_qtys) > 0 else "",
            "Ordered Qty 2": final_qtys[1] if len(final_qtys) > 1 else "",
            "Ordered Qty 3": final_qtys[2] if len(final_qtys) > 2 else "",
            "Suggested Qty 1": suggested_qtys[0] if suggested_qtys[0] is not None else "",
            "Suggested Qty 2": (suggested_qtys[1] if len(suggested_qtys) > 1 and suggested_qtys[1] is not None else ""),
            "Suggested Qty 3": (suggested_qtys[2] if len(suggested_qtys) > 2 and suggested_qtys[2] is not None else ""),
            "Trend": trend,
            "Override Pattern": override_pattern,
        }
        rows.append(row)
    rows.sort(key=lambda r: (r["Line Code"], r["Item Code"]))
    return rows


def trend_report_column_order():
    """Return the canonical column order for the trend report CSV."""
    return list(_TREND_COLUMNS)
