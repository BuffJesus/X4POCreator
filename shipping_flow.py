from datetime import datetime


WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _normalize_vendor(value):
    return str(value or "").strip().upper()


def _normalize_weekdays(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, str):
        parts = [part.strip() for part in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        parts = [str(part).strip() for part in raw_value]
    else:
        parts = [str(raw_value).strip()]
    normalized = []
    for part in parts:
        if not part:
            continue
        lowered = part.lower()
        for weekday in WEEKDAY_NAMES:
            if lowered in (weekday.lower(), weekday[:3].lower()):
                normalized.append(weekday)
                break
    return normalized


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_vendor_policy(policy):
    policy = dict(policy or {})
    shipping_policy = str(policy.get("shipping_policy", "") or "").strip() or "release_immediately"
    normalized = {
        "shipping_policy": shipping_policy,
        "preferred_free_ship_weekdays": _normalize_weekdays(policy.get("preferred_free_ship_weekdays")),
        "free_freight_threshold": _safe_float(policy.get("free_freight_threshold"), 0.0),
        "urgent_release_floor": _safe_float(policy.get("urgent_release_floor"), 0.0),
    }
    return normalized


def estimate_item_order_value(item, inventory_lookup):
    key = (item.get("line_code", ""), item.get("item_code", ""))
    inv = inventory_lookup.get(key, {}) if inventory_lookup else {}
    repl_cost = _safe_float(inv.get("repl_cost"), 0.0)
    qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
    return repl_cost * qty


def build_vendor_order_totals(items, inventory_lookup):
    totals = {}
    for item in items or []:
        vendor = _normalize_vendor(item.get("vendor", ""))
        if not vendor:
            continue
        qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
        if qty <= 0:
            continue
        totals[vendor] = totals.get(vendor, 0.0) + estimate_item_order_value(item, inventory_lookup)
    return totals


def _choose_release_decision(item, policy, vendor_total, now):
    shipping_policy = policy.get("shipping_policy", "release_immediately")
    weekdays = policy.get("preferred_free_ship_weekdays", [])
    threshold = max(0.0, _safe_float(policy.get("free_freight_threshold"), 0.0))
    urgent_floor = max(0.0, _safe_float(policy.get("urgent_release_floor"), 0.0))
    today_name = (now or datetime.now()).strftime("%A")
    inventory_position = _safe_float(item.get("inventory_position"), 0.0)
    urgent = urgent_floor > 0 and inventory_position <= urgent_floor

    if urgent:
        return "release_now", f"Released now because inventory position {inventory_position:g} is at or below urgent floor {urgent_floor:g}"

    if shipping_policy == "hold_for_free_day":
        if weekdays and today_name in weekdays:
            return "release_now", f"Released now because today is preferred free-shipping day ({today_name})"
        if weekdays:
            return "hold_for_free_day", f"Held for vendor free-shipping day ({', '.join(weekdays)})"
        return "release_now", "Released now because no preferred free-shipping day is configured"

    if shipping_policy == "hold_for_threshold":
        if threshold > 0 and vendor_total >= threshold:
            return "release_now", f"Released now because vendor threshold {threshold:g} was reached"
        if threshold > 0:
            return "hold_for_threshold", f"Held for freight threshold {threshold:g} (current vendor total {vendor_total:g})"
        return "release_now", "Released now because no freight threshold is configured"

    if shipping_policy == "hybrid_free_day_threshold":
        if threshold > 0 and vendor_total >= threshold:
            return "release_now", f"Released now because vendor threshold {threshold:g} was reached"
        if weekdays and today_name in weekdays:
            return "release_now", f"Released now because today is preferred free-shipping day ({today_name})"
        if weekdays:
            return "hold_for_free_day", f"Held for vendor free-shipping day ({', '.join(weekdays)})"
        if threshold > 0:
            return "hold_for_threshold", f"Held for freight threshold {threshold:g} (current vendor total {vendor_total:g})"
        return "release_now", "Released now because no vendor hold condition is configured"

    return "release_now", "Released now by vendor policy"


def annotate_release_decisions(session, now=None):
    inventory_lookup = getattr(session, "inventory_lookup", {}) or {}
    vendor_policies = getattr(session, "vendor_policies", {}) or {}
    source_items = list(getattr(session, "assigned_items", []) or [])
    if not source_items:
        source_items = list(getattr(session, "filtered_items", []) or [])
    vendor_totals = build_vendor_order_totals(source_items, inventory_lookup)

    for collection_name in ("filtered_items", "assigned_items"):
        for item in getattr(session, collection_name, []) or []:
            vendor = _normalize_vendor(item.get("vendor", ""))
            qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
            item["estimated_order_value"] = estimate_item_order_value(item, inventory_lookup)
            item["vendor_order_value_total"] = vendor_totals.get(vendor, 0.0) if vendor else 0.0
            item["release_decision"] = ""
            item["release_reason"] = ""
            item["shipping_policy"] = ""
            item["shipping_policy_weekdays"] = []
            item["shipping_policy_threshold"] = 0.0
            base_why = item.get("core_why") or item.get("why", "")
            item["why"] = base_why

            raw_policy = vendor_policies.get(vendor)
            if not vendor or qty <= 0 or not raw_policy:
                continue

            policy = normalize_vendor_policy(raw_policy)
            decision, reason = _choose_release_decision(item, policy, item["vendor_order_value_total"], now)
            item["release_decision"] = decision
            item["release_reason"] = reason
            item["shipping_policy"] = policy["shipping_policy"]
            item["shipping_policy_weekdays"] = list(policy["preferred_free_ship_weekdays"])
            item["shipping_policy_threshold"] = policy["free_freight_threshold"]
            item["why"] = " | ".join(part for part in (base_why, f"Release: {reason}") if part)
