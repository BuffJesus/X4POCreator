import math

import storage


def get_cycle_weeks(app):
    cycle = app.var_reorder_cycle.get()
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


def default_vendor_for_key(app, key):
    inv = app.inventory_lookup.get(key, {})
    supplier = (inv.get("supplier", "") or "").strip().upper()
    return supplier or ""


def refresh_suggestions(app):
    for item in app.filtered_items:
        app._recalculate_item(item)
    for item in app.assigned_items:
        app._sync_review_item_to_filtered(item)
    app._apply_bulk_filter()


def refresh_recent_orders(app):
    try:
        days = app.var_lookback_days.get()
    except Exception:
        days = 14
    app.recent_orders = storage.get_recent_orders(app._data_path("order_history"), days)
    app._apply_bulk_filter()
