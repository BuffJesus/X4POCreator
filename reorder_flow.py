import math

import item_workflow
import storage


def _recalculate_item(app, item, *, annotate_release):
    try:
        app._recalculate_item(item, annotate_release=annotate_release)
    except TypeError:
        app._recalculate_item(item)


def get_cycle_weeks(app):
    cycle_var = getattr(app, "var_reorder_cycle", None)
    cycle = cycle_var.get() if cycle_var and hasattr(cycle_var, "get") else "Biweekly"
    return {"Weekly": 1, "Biweekly": 2, "Monthly": 4}.get(cycle, 2)


def suggest_min_max(app, key, min_annual_sales_for_suggestions):
    inv = app.inventory_lookup.get(key, {})
    mo12 = inv.get("mo12_sales", 0)
    if not mo12 or mo12 <= 0:
        return None, None
    if mo12 < min_annual_sales_for_suggestions:
        return None, None
    weekly = mo12 / 52
    weeks = app._get_cycle_weeks()
    sug_min = max(1, math.ceil(weekly * weeks))
    sug_max = max(sug_min + 1, math.ceil(weekly * weeks * 2))
    return sug_min, sug_max


def receipt_history_for_key(app, key):
    return dict((getattr(app, "receipt_history_lookup", {}) or {}).get(key, {}) or {})


def receipt_vendor_evidence(app, key):
    history = receipt_history_for_key(app, key)
    candidates = receipt_vendor_candidates(app, key)
    return {
        "primary_vendor": str(history.get("primary_vendor", "") or "").strip().upper(),
        "most_recent_vendor": str(history.get("most_recent_vendor", "") or "").strip().upper(),
        "vendor_confidence": str(history.get("vendor_confidence", "none") or "none").strip().lower(),
        "vendor_confidence_reason": str(history.get("vendor_confidence_reason", "") or "").strip(),
        "vendor_ambiguous": bool(history.get("vendor_ambiguous")),
        "primary_vendor_qty_share": float(history.get("primary_vendor_qty_share", 0.0) or 0.0),
        "primary_vendor_receipt_share": float(history.get("primary_vendor_receipt_share", 0.0) or 0.0),
        "vendor_candidates": candidates,
    }


def apply_receipt_vendor_context(app, item, key):
    evidence = receipt_vendor_evidence(app, key)
    item["receipt_primary_vendor"] = evidence["primary_vendor"]
    item["receipt_most_recent_vendor"] = evidence["most_recent_vendor"]
    item["receipt_vendor_confidence"] = evidence["vendor_confidence"]
    item["receipt_vendor_confidence_reason"] = evidence["vendor_confidence_reason"]
    item["receipt_vendor_ambiguous"] = evidence["vendor_ambiguous"]
    item["receipt_vendor_qty_share"] = evidence["primary_vendor_qty_share"]
    item["receipt_vendor_receipt_share"] = evidence["primary_vendor_receipt_share"]
    item["receipt_vendor_candidates"] = list(evidence["vendor_candidates"])
    return evidence


def receipt_vendor_candidates(app, key):
    history = receipt_history_for_key(app, key)
    candidates = []
    for vendor in list(history.get("vendor_candidates", []) or []):
        normalized = str(vendor or "").strip().upper()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    primary_vendor = str(history.get("primary_vendor", "") or "").strip().upper()
    if primary_vendor and primary_vendor not in candidates:
        candidates.insert(0, primary_vendor)
    return candidates


def default_vendor_for_key(app, key):
    evidence = receipt_vendor_evidence(app, key)
    if evidence["primary_vendor"] and evidence["vendor_confidence"] == "high":
        return evidence["primary_vendor"]
    if evidence["vendor_candidates"]:
        return ""
    inv = app.inventory_lookup.get(key, {})
    supplier = (inv.get("supplier", "") or "").strip().upper()
    return supplier or ""


def _normalize_demand_signal(raw_demand, cycle_weeks, sales_span_days):
    """Normalize a raw period-total demand signal down to one reorder cycle's worth.

    E.g. 40 sold over 365 days on a weekly (7-day) cycle -> 40 * 7 / 365 ~= 0.77 -> 1.
    Returns the raw value unchanged when span_days is unknown/zero.

    Intentionally does NOT floor at 1 — items that normalize below 0.5 round to
    zero demand and are dropped from suggestions unless X4 shows they are below
    their set minimum.  This prevents one-off sales from a long export window from
    producing spurious reorder suggestions.
    """
    if not sales_span_days or sales_span_days <= 0:
        return raw_demand
    cycle_days = cycle_weeks * 7
    normalized = raw_demand * cycle_days / sales_span_days
    return round(normalized) if raw_demand > 0 else 0


def refresh_suggestions(app):
    """Recalculate suggestions when the reorder cycle changes.

    Explicitly stamps suggested_min/suggested_max AND a cycle-normalized
    demand_signal onto each item before calling _recalculate_item, so that
    enrich_item -> calculate_raw_need uses values appropriate to the new cycle.
    """
    span_days = getattr(app, "sales_span_days", None)
    get_cycle = getattr(app, "_get_cycle_weeks", None)
    cycle_weeks = get_cycle() if callable(get_cycle) else 2
    suggest = getattr(app, "_suggest_min_max", None)
    for item in app.filtered_items:
        if callable(suggest):
            key = (item["line_code"], item["item_code"])
            sug_min, sug_max = suggest(key)
            item["suggested_min"] = sug_min
            item["suggested_max"] = sug_max
        item["reorder_cycle_weeks"] = cycle_weeks
        raw_eff_sales = item.get("effective_qty_sold", item.get("qty_sold", 0))
        raw_eff_susp = item.get("effective_qty_suspended", item.get("qty_suspended", 0))
        raw_demand = raw_eff_sales + raw_eff_susp
        item["demand_signal"] = _normalize_demand_signal(raw_demand, cycle_weeks, span_days)
        item["gross_need"] = item["demand_signal"]
        _recalculate_item(app, item, annotate_release=False)
    for item in app.assigned_items:
        app._sync_review_item_to_filtered(item)
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()
    app._apply_bulk_filter()


def normalize_items_to_cycle(app):
    """Normalize demand_signal on all filtered_items to match the current reorder cycle.

    Called once after assignment_flow.prepare_assignment_session() builds the
    raw item list.  assignment_flow sets demand_signal as a total over the full
    sales export window (e.g. 40 bearings sold in a year).  Without this step,
    items without a current_max in inventory fall back to that raw total as their
    target stock, producing wildly over-sized suggestions on long export windows.

    Items whose normalized demand rounds to zero are left at zero — calculate_raw_need
    will still include them if their inventory is below a set X4 minimum, but pure
    one-off sales from a long window will no longer generate spurious suggestions.

    Formula: demand_signal = round(raw_demand * cycle_days / span_days)
    Example: 40 sold / 365 days * 7 days (weekly) = 0.77 -> 1
    Example: 1 sold / 365 days * 7 days (weekly) = 0.019 -> 0  (one-off, suppressed)
    """
    span_days = getattr(app, "sales_span_days", None)
    cycle_weeks = app._get_cycle_weeks()

    for item in app.filtered_items:
        item["reorder_cycle_weeks"] = cycle_weeks
        raw_eff_sales = item.get("effective_qty_sold", item.get("qty_sold", 0))
        raw_eff_susp = item.get("effective_qty_suspended", item.get("qty_suspended", 0))
        raw_demand = raw_eff_sales + raw_eff_susp
        item["demand_signal"] = _normalize_demand_signal(raw_demand, cycle_weeks, span_days)
        item["gross_need"] = item["demand_signal"]
        key = (item["line_code"], item["item_code"])
        sug_min, sug_max = app._suggest_min_max(key)
        item["suggested_min"] = sug_min
        item["suggested_max"] = sug_max
        _recalculate_item(app, item, annotate_release=False)
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()


def refresh_recent_orders(app):
    try:
        days = app.var_lookback_days.get()
    except Exception:
        days = 14
    app.recent_orders = storage.get_recent_orders(app._data_path("order_history"), days)
    for item in getattr(app, "filtered_items", []) or []:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        item_workflow.apply_recent_order_context(item, app.recent_orders.get(key, []))
        _recalculate_item(app, item, annotate_release=False)
    for item in getattr(app, "assigned_items", []) or []:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        item_workflow.apply_recent_order_context(item, app.recent_orders.get(key, []))
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()
    app._apply_bulk_filter()
