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


def detailed_sales_shape_label(shape):
    return {
        "steady_repeat": "Steady repeat demand",
        "routine_mixed": "Routine mixed demand",
        "lumpy_bulk": "Lumpy / job-driven demand",
        "sporadic": "Sporadic demand",
        "sparse_transactions": "Very sparse transactions",
    }.get(shape, shape or "")


def classify_receipt_sales_balance(item):
    qty_sold = _safe_float(item.get("qty_sold"))
    qty_received = _safe_float(item.get("qty_received"))
    receipt_count = int(_safe_float(item.get("receipt_count")))
    avg_units_per_receipt = _safe_float(item.get("avg_units_per_receipt"))
    avg_units_per_transaction = _safe_float(item.get("avg_units_per_transaction"))

    result = {
        "receipt_sales_balance": "",
        "receipt_sales_balance_reason": "",
        "receipt_sales_review_required": False,
    }
    if qty_received <= 0 or receipt_count <= 0:
        return result
    if qty_sold <= 0:
        if receipt_count >= 2:
            result.update({
                "receipt_sales_balance": "receipt_heavy",
                "receipt_sales_balance_reason": "repeat receipts exist in the loaded window without matching sales activity",
                "receipt_sales_review_required": True,
            })
        else:
            result.update({
                "receipt_sales_balance": "receipt_only",
                "receipt_sales_balance_reason": "receipt activity exists, but matching sales evidence is too thin",
            })
        return result

    receipt_to_sales_ratio = qty_received / qty_sold if qty_sold > 0 else 0.0
    if receipt_count >= 2 and receipt_to_sales_ratio >= 3.0:
        result.update({
            "receipt_sales_balance": "receipt_heavy",
            "receipt_sales_balance_reason": "receipts materially outpace loaded sales in the selected window",
            "receipt_sales_review_required": True,
        })
        return result
    if (
        receipt_count >= 2
        and avg_units_per_transaction > 0
        and avg_units_per_receipt >= (avg_units_per_transaction * 3.0)
    ):
        result.update({
            "receipt_sales_balance": "receipt_heavy",
            "receipt_sales_balance_reason": "typical receipt lots are much larger than actual sales transactions",
            "receipt_sales_review_required": True,
        })
        return result
    if receipt_to_sales_ratio >= 1.5:
        result.update({
            "receipt_sales_balance": "receipt_led",
            "receipt_sales_balance_reason": "receipts are running ahead of sales, but not enough to treat as overstock-driven",
        })
        return result
    result.update({
        "receipt_sales_balance": "balanced",
        "receipt_sales_balance_reason": "loaded receipts and sales are in a similar range",
    })
    return result


def classify_detailed_sales_shape(item):
    transaction_count = int(_safe_float(item.get("transaction_count")))
    sale_day_count = int(_safe_float(item.get("sale_day_count")))
    avg_units = _safe_float(item.get("avg_units_per_transaction"))
    max_units = _safe_float(item.get("max_units_per_transaction"))
    avg_days_between_sales = _safe_float(item.get("avg_days_between_sales"))

    result = {
        "detailed_sales_shape": "",
        "detailed_sales_shape_confidence": "none",
        "detailed_sales_shape_reason": "",
        "detailed_sales_review_required": False,
    }
    if transaction_count <= 0:
        return result

    if transaction_count <= 2 or sale_day_count <= 2:
        result.update({
            "detailed_sales_shape": "sparse_transactions",
            "detailed_sales_shape_confidence": "low",
            "detailed_sales_shape_reason": "very few detailed sales transactions in the loaded window",
        })
        return result

    if avg_units >= 4 and max_units >= max(8.0, avg_units * 2.0) and avg_days_between_sales >= 21:
        result.update({
            "detailed_sales_shape": "lumpy_bulk",
            "detailed_sales_shape_confidence": "medium" if transaction_count >= 3 else "low",
            "detailed_sales_shape_reason": "larger transactions are spaced far apart",
            "detailed_sales_review_required": True,
        })
        return result

    if avg_days_between_sales > 0 and avg_days_between_sales <= 14 and sale_day_count >= 4 and avg_units <= 3:
        result.update({
            "detailed_sales_shape": "steady_repeat",
            "detailed_sales_shape_confidence": "high",
            "detailed_sales_shape_reason": "smaller repeat transactions show up regularly",
        })
        return result

    if avg_days_between_sales > 0 and avg_days_between_sales <= 30 and transaction_count >= 3:
        result.update({
            "detailed_sales_shape": "routine_mixed",
            "detailed_sales_shape_confidence": "medium",
            "detailed_sales_shape_reason": "sales recur often enough to look operationally routine",
        })
        return result

    result.update({
        "detailed_sales_shape": "sporadic",
        "detailed_sales_shape_confidence": "low",
        "detailed_sales_shape_reason": "detailed sales exist, but the cadence is irregular",
    })
    return result


def _append_detailed_sales_shape_reason(item):
    shape = item.get("detailed_sales_shape", "")
    if not shape:
        return
    base_why = str(item.get("core_why", item.get("why", "")) or "").strip()
    if not base_why:
        return
    detail = f"Detailed sales shape: {detailed_sales_shape_label(shape) or shape}"
    confidence = str(item.get("detailed_sales_shape_confidence", "") or "").strip().lower()
    if confidence and confidence != "none":
        detail += f" ({confidence} confidence)"
    reason = str(item.get("detailed_sales_shape_reason", "") or "").strip()
    if reason:
        detail += f"; {reason}"
    if detail in base_why:
        return
    merged = f"{base_why} | {detail}"
    if item.get("core_why"):
        item["core_why"] = merged
    item["why"] = merged


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
    demand_shape = classify_detailed_sales_shape(item)
    receipt_balance = classify_receipt_sales_balance(item)
    if possible_missed_reorder:
        reorder_attention_signal = "review_missed_reorder"
    elif demand_shape.get("detailed_sales_review_required"):
        reorder_attention_signal = "review_lumpy_demand"
    elif receipt_balance.get("receipt_sales_review_required"):
        reorder_attention_signal = "review_receipt_heavy"
    else:
        reorder_attention_signal = "normal"

    return {
        "performance_profile": performance_profile,
        "sales_health_signal": sales_health_signal,
        "historical_rank_score": historical_rank_score,
        "possible_missed_reorder": possible_missed_reorder,
        "reorder_attention_signal": reorder_attention_signal,
        **receipt_balance,
        **demand_shape,
    }


def annotate_items(items, *, inventory_lookup):
    for item in items:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        inv = inventory_lookup.get(key, {}) or {}
        item.update(classify_item(item, inv))
        _append_detailed_sales_shape_reason(item)
    return items
