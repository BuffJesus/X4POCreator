from datetime import datetime, timedelta


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


def _safe_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


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


def item_has_known_cost(item, inventory_lookup):
    key = (item.get("line_code", ""), item.get("item_code", ""))
    inv = inventory_lookup.get(key, {}) if inventory_lookup else {}
    return _safe_float(inv.get("repl_cost"), 0.0) > 0


def build_vendor_value_coverage(items, inventory_lookup):
    coverage = {}
    for item in items or []:
        vendor = _normalize_vendor(item.get("vendor", ""))
        if not vendor:
            continue
        entry = coverage.setdefault(vendor, {"known": 0, "unknown": 0})
        qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
        if qty <= 0:
            continue
        if item_has_known_cost(item, inventory_lookup):
            entry["known"] += 1
        else:
            entry["unknown"] += 1
    for vendor, entry in coverage.items():
        known = entry["known"]
        unknown = entry["unknown"]
        total = known + unknown
        if total <= 0:
            label = "none"
        elif unknown <= 0:
            label = "complete"
        elif known <= 0:
            label = "missing"
        else:
            label = "partial"
        entry["label"] = label
    return coverage


def _next_preferred_weekday(now, weekdays):
    weekdays = weekdays or []
    if not weekdays:
        return None
    weekday_indexes = []
    for weekday in weekdays:
        try:
            weekday_indexes.append(WEEKDAY_NAMES.index(weekday))
        except ValueError:
            continue
    if not weekday_indexes:
        return None
    today = _safe_date(now or datetime.now())
    for offset in range(0, 14):
        candidate = today + timedelta(days=offset)
        if candidate.weekday() in weekday_indexes:
            return candidate
    return None


def _previous_business_day(target_date):
    if target_date is None:
        return None
    candidate = target_date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _format_date(value):
    if not value:
        return ""
    return value.isoformat()


def release_bucket(item):
    decision = str(item.get("release_decision", "") or "").strip()
    if decision in ("hold_for_free_day", "hold_for_threshold"):
        return "held"
    if decision == "export_next_business_day_for_free_day":
        return "planned_today"
    return "release_now"


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


def build_vendor_release_plan(items):
    plan = {}
    for item in items or []:
        vendor = _normalize_vendor(item.get("vendor", ""))
        if not vendor:
            continue
        qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
        if qty <= 0:
            continue
        bucket = release_bucket(item)
        row = plan.setdefault(
            vendor,
            {
                "vendor": vendor,
                "release_now_count": 0,
                "planned_today_count": 0,
                "held_count": 0,
                "release_now_value": 0.0,
                "planned_today_value": 0.0,
                "held_value": 0.0,
                "vendor_order_value_total": _safe_float(item.get("vendor_order_value_total"), 0.0),
                "vendor_threshold_shortfall": _safe_float(item.get("vendor_threshold_shortfall"), 0.0),
                "vendor_threshold_progress_pct": _safe_float(item.get("vendor_threshold_progress_pct"), 0.0),
                "vendor_value_coverage": item.get("vendor_value_coverage") or "none",
                "next_free_ship_date": item.get("next_free_ship_date") or "",
                "planned_export_date": item.get("planned_export_date") or "",
                "shipping_policy": item.get("shipping_policy") or "",
            },
        )
        value = _safe_float(item.get("estimated_order_value"), 0.0)
        row[f"{bucket}_count"] += 1
        row[f"{bucket}_value"] += value
        row["vendor_order_value_total"] = max(row["vendor_order_value_total"], _safe_float(item.get("vendor_order_value_total"), 0.0))
        row["vendor_threshold_shortfall"] = max(row["vendor_threshold_shortfall"], _safe_float(item.get("vendor_threshold_shortfall"), 0.0))
        row["vendor_threshold_progress_pct"] = max(row["vendor_threshold_progress_pct"], _safe_float(item.get("vendor_threshold_progress_pct"), 0.0))
        if row["vendor_value_coverage"] in ("none", "") and item.get("vendor_value_coverage"):
            row["vendor_value_coverage"] = item.get("vendor_value_coverage")
        elif row["vendor_value_coverage"] != item.get("vendor_value_coverage") and item.get("vendor_value_coverage"):
            coverage_priority = {"missing": 3, "partial": 2, "complete": 1, "none": 0}
            if coverage_priority.get(item.get("vendor_value_coverage"), 0) > coverage_priority.get(row["vendor_value_coverage"], 0):
                row["vendor_value_coverage"] = item.get("vendor_value_coverage")
        if not row["next_free_ship_date"] and item.get("next_free_ship_date"):
            row["next_free_ship_date"] = item.get("next_free_ship_date")
        if not row["planned_export_date"] and item.get("planned_export_date"):
            row["planned_export_date"] = item.get("planned_export_date")
        if not row["shipping_policy"] and item.get("shipping_policy"):
            row["shipping_policy"] = item.get("shipping_policy")
    return [plan[vendor] for vendor in sorted(plan)]


def _choose_release_decision(item, policy, vendor_total, now):
    shipping_policy = policy.get("shipping_policy", "release_immediately")
    weekdays = policy.get("preferred_free_ship_weekdays", [])
    threshold = max(0.0, _safe_float(policy.get("free_freight_threshold"), 0.0))
    urgent_floor = max(0.0, _safe_float(policy.get("urgent_release_floor"), 0.0))
    current_dt = now or datetime.now()
    current_date = _safe_date(current_dt)
    today_name = current_dt.strftime("%A")
    inventory_position = _safe_float(item.get("inventory_position"), 0.0)
    urgent = urgent_floor > 0 and inventory_position <= urgent_floor
    next_free_ship_date = _next_preferred_weekday(current_dt, weekdays)
    previous_business_export_date = _previous_business_day(next_free_ship_date)

    if urgent:
        return "release_now", f"Released now because inventory position {inventory_position:g} is at or below urgent floor {urgent_floor:g}"

    if shipping_policy == "hold_for_free_day":
        if weekdays and today_name in weekdays:
            return "release_now", f"Released now because today is preferred free-shipping day ({today_name})"
        if previous_business_export_date and current_date == previous_business_export_date:
            free_day_name = next_free_ship_date.strftime("%A") if next_free_ship_date else "scheduled free-shipping day"
            return (
                "export_next_business_day_for_free_day",
                f"Export today so the PO is ready for vendor free-shipping day ({free_day_name} {_format_date(next_free_ship_date)})",
            )
        if weekdays:
            extra = ""
            if next_free_ship_date:
                extra = (
                    f"; next free-shipping day {_format_date(next_free_ship_date)}"
                    f"; planned export {_format_date(previous_business_export_date)}"
                )
            return "hold_for_free_day", f"Held for vendor free-shipping day ({', '.join(weekdays)}{extra})"
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
        if previous_business_export_date and current_date == previous_business_export_date:
            free_day_name = next_free_ship_date.strftime("%A") if next_free_ship_date else "scheduled free-shipping day"
            return (
                "export_next_business_day_for_free_day",
                f"Export today so the PO is ready for vendor free-shipping day ({free_day_name} {_format_date(next_free_ship_date)})",
            )
        if weekdays:
            extra = ""
            if next_free_ship_date:
                extra = (
                    f"; next free-shipping day {_format_date(next_free_ship_date)}"
                    f"; planned export {_format_date(previous_business_export_date)}"
                )
            return "hold_for_free_day", f"Held for vendor free-shipping day ({', '.join(weekdays)}{extra})"
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
    vendor_value_coverage = build_vendor_value_coverage(source_items, inventory_lookup)
    current_dt = now or datetime.now()

    for collection_name in ("filtered_items", "assigned_items"):
        for item in getattr(session, collection_name, []) or []:
            vendor = _normalize_vendor(item.get("vendor", ""))
            qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
            policy = normalize_vendor_policy(vendor_policies.get(vendor))
            threshold = max(0.0, _safe_float(policy.get("free_freight_threshold"), 0.0))
            current_total = vendor_totals.get(vendor, 0.0) if vendor else 0.0
            coverage_entry = vendor_value_coverage.get(vendor, {"label": "none", "known": 0, "unknown": 0})
            threshold_shortfall = max(0.0, threshold - current_total) if threshold > 0 else 0.0
            threshold_progress_pct = min(100.0, (current_total / threshold) * 100.0) if threshold > 0 else 100.0
            next_free_ship_date = _next_preferred_weekday(current_dt, policy.get("preferred_free_ship_weekdays", []))
            planned_export_date = _previous_business_day(next_free_ship_date)
            item["estimated_order_value"] = estimate_item_order_value(item, inventory_lookup)
            item["vendor_order_value_total"] = current_total
            item["vendor_value_coverage"] = coverage_entry["label"]
            item["vendor_value_known_items"] = coverage_entry["known"]
            item["vendor_value_unknown_items"] = coverage_entry["unknown"]
            item["vendor_threshold_shortfall"] = threshold_shortfall
            item["vendor_threshold_progress_pct"] = threshold_progress_pct
            item["next_free_ship_date"] = _format_date(next_free_ship_date)
            item["planned_export_date"] = _format_date(planned_export_date)
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

            decision, reason = _choose_release_decision(item, policy, current_total, current_dt)
            item["release_decision"] = decision
            item["release_reason"] = reason
            item["shipping_policy"] = policy["shipping_policy"]
            item["shipping_policy_weekdays"] = list(policy["preferred_free_ship_weekdays"])
            item["shipping_policy_threshold"] = policy["free_freight_threshold"]
            planning_parts = []
            if threshold > 0:
                planning_parts.append(
                    f"Vendor threshold progress: {current_total:g}/{threshold:g} ({threshold_progress_pct:.0f}%, short {threshold_shortfall:g})"
                )
            if coverage_entry["label"] != "complete":
                planning_parts.append(
                    f"Vendor value coverage: {coverage_entry['label']} ({coverage_entry['known']} known, {coverage_entry['unknown']} unknown)"
                )
            if next_free_ship_date:
                planning_parts.append(f"Next free-ship date: {_format_date(next_free_ship_date)}")
            if planned_export_date:
                planning_parts.append(f"Planned export date: {_format_date(planned_export_date)}")
            item["why"] = " | ".join(part for part in (base_why, *planning_parts, f"Release: {reason}") if part)
