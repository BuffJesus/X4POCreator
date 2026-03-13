from datetime import datetime


AVERAGE_DAYS_PER_MONTH = 365.25 / 12.0


def _coerce_span_days(sales_span_days):
    try:
        value = int(sales_span_days)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _annualize(quantity, span_days):
    if span_days is None:
        return None
    return (float(quantity or 0) * 365.25) / float(span_days)


def _monthly_rate(quantity, span_days):
    if span_days is None:
        return None
    return (float(quantity or 0) * AVERAGE_DAYS_PER_MONTH) / float(span_days)


def _weekly_rate(quantity, span_days):
    if span_days is None:
        return None
    return (float(quantity or 0) * 7.0) / float(span_days)


def sales_last_sale_metrics(last_sale_value, *, now=None, parse_date):
    last_sale_dt = parse_date(last_sale_value) if last_sale_value else None
    if last_sale_dt is None:
        return {"last_sale_date": "", "days_since_last_sale": None}
    today = now or datetime.now()
    return {
        "last_sale_date": last_sale_dt.date().isoformat(),
        "days_since_last_sale": max(0, (today.date() - last_sale_dt.date()).days),
    }


def annotate_sales_items(sales_items, *, inventory_lookup, sales_span_days, parse_date, now=None):
    span_days = _coerce_span_days(sales_span_days)
    for item in sales_items:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        inv = inventory_lookup.get(key, {}) or {}
        qty_sold = item.get("qty_sold", 0) or 0
        qty_received = item.get("qty_received", 0) or 0
        item["sales_span_days"] = span_days
        item["avg_weekly_sales_loaded"] = _weekly_rate(qty_sold, span_days)
        item["avg_monthly_sales_loaded"] = _monthly_rate(qty_sold, span_days)
        item["annualized_sales_loaded"] = _annualize(qty_sold, span_days)
        item["avg_weekly_receipts_loaded"] = _weekly_rate(qty_received, span_days)
        item["annualized_receipts_loaded"] = _annualize(qty_received, span_days)
        item.update(
            sales_last_sale_metrics(
                inv.get("last_sale", ""),
                now=now,
                parse_date=parse_date,
            )
        )
    return sales_items
