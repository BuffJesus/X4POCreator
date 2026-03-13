def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _max_signal(item, inv):
    return max(
        _safe_float(item.get("annualized_sales_loaded")),
        _safe_float(inv.get("mo12_sales")),
    )


def classify_item(item, inv):
    annualized_loaded = _safe_float(item.get("annualized_sales_loaded"))
    mo12_sales = _safe_float(inv.get("mo12_sales"))
    historical_rank_score = max(annualized_loaded, mo12_sales)
    days_since_last_sale = item.get("days_since_last_sale")

    if historical_rank_score >= 104:
        performance_profile = "top_performer"
    elif historical_rank_score >= 24:
        performance_profile = "steady"
    elif historical_rank_score > 0:
        performance_profile = "intermittent"
    else:
        performance_profile = "legacy"

    if days_since_last_sale is None:
        sales_health_signal = "unknown"
    elif days_since_last_sale <= 90:
        sales_health_signal = "active"
    elif days_since_last_sale <= 365:
        sales_health_signal = "cooling"
    elif historical_rank_score >= 24:
        sales_health_signal = "dormant"
    else:
        sales_health_signal = "stale"

    inventory_position = item.get("inventory_position")
    if inventory_position is None:
        inventory_position = _safe_float(inv.get("qoh")) + _safe_float(item.get("qty_on_po"))
    current_min = inv.get("min")
    min_threshold = _safe_float(current_min) if current_min is not None else 0.0

    possible_missed_reorder = bool(
        historical_rank_score >= 24
        and days_since_last_sale is not None
        and days_since_last_sale > 365
        and inventory_position <= min_threshold
    )
    reorder_attention_signal = "review_missed_reorder" if possible_missed_reorder else "normal"

    return {
        "performance_profile": performance_profile,
        "sales_health_signal": sales_health_signal,
        "historical_rank_score": historical_rank_score,
        "possible_missed_reorder": possible_missed_reorder,
        "reorder_attention_signal": reorder_attention_signal,
    }


def annotate_items(items, *, inventory_lookup):
    for item in items:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        inv = inventory_lookup.get(key, {}) or {}
        item.update(classify_item(item, inv))
    return items
