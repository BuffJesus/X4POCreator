from datetime import datetime, timedelta


WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
VALID_SHIPPING_POLICIES = {
    "release_immediately",
    "hold_for_free_day",
    "hold_for_threshold",
    "hybrid_free_day_threshold",
}

VENDOR_POLICY_PRESETS = {
    "release_now": {
        "label": "Release Now",
        "shipping_policy": "release_immediately",
        "preferred_free_ship_weekdays": [],
        "free_freight_threshold": 0.0,
        "urgent_release_floor": 0.0,
        "urgent_release_mode": "release_now",
        "release_lead_business_days": 1,
    },
    "free_day_friday": {
        "label": "Free Day Friday",
        "shipping_policy": "hold_for_free_day",
        "preferred_free_ship_weekdays": ["Friday"],
        "free_freight_threshold": 0.0,
        "urgent_release_floor": 0.0,
        "urgent_release_mode": "release_now",
        "release_lead_business_days": 1,
    },
    "threshold_2000": {
        "label": "Threshold 2000",
        "shipping_policy": "hold_for_threshold",
        "preferred_free_ship_weekdays": [],
        "free_freight_threshold": 2000.0,
        "urgent_release_floor": 0.0,
        "urgent_release_mode": "release_now",
        "release_lead_business_days": 1,
    },
    "hybrid_friday_2000": {
        "label": "Friday + 2000",
        "shipping_policy": "hybrid_free_day_threshold",
        "preferred_free_ship_weekdays": ["Friday"],
        "free_freight_threshold": 2000.0,
        "urgent_release_floor": 0.0,
        "urgent_release_mode": "release_now",
        "release_lead_business_days": 1,
    },
    "paid_urgent_friday_2000": {
        "label": "Friday + 2000 + Paid Urgent",
        "shipping_policy": "hybrid_free_day_threshold",
        "preferred_free_ship_weekdays": ["Friday"],
        "free_freight_threshold": 2000.0,
        "urgent_release_floor": 0.0,
        "urgent_release_mode": "paid_urgent_freight",
        "release_lead_business_days": 1,
    },
}


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


def _safe_nonnegative_int(value, default=0):
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _safe_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def normalize_vendor_policy(policy):
    policy = dict(policy or {})
    shipping_policy = str(policy.get("shipping_policy", "") or "").strip() or "release_immediately"
    if shipping_policy not in VALID_SHIPPING_POLICIES:
        shipping_policy = "release_immediately"
    urgent_release_mode = str(policy.get("urgent_release_mode", "") or "").strip() or "release_now"
    if urgent_release_mode not in ("release_now", "paid_urgent_freight"):
        urgent_release_mode = "release_now"
    weekdays = _normalize_weekdays(policy.get("preferred_free_ship_weekdays"))
    threshold = max(0.0, _safe_float(policy.get("free_freight_threshold"), 0.0))
    urgent_floor = max(0.0, _safe_float(policy.get("urgent_release_floor"), 0.0))
    release_lead_business_days = _safe_nonnegative_int(policy.get("release_lead_business_days"), 1)
    raw_lead = policy.get("estimated_lead_days")
    if raw_lead is not None:
        try:
            estimated_lead_days = max(1, int(raw_lead))
        except (TypeError, ValueError):
            estimated_lead_days = None
    else:
        estimated_lead_days = None
    if shipping_policy == "release_immediately":
        weekdays = []
        threshold = 0.0
        release_lead_business_days = 1
    elif shipping_policy == "hold_for_free_day":
        threshold = 0.0
    elif shipping_policy == "hold_for_threshold":
        weekdays = []
        release_lead_business_days = 1
    normalized = {
        "shipping_policy": shipping_policy,
        "preferred_free_ship_weekdays": weekdays,
        "free_freight_threshold": threshold,
        "urgent_release_floor": urgent_floor,
        "urgent_release_mode": urgent_release_mode,
        "release_lead_business_days": release_lead_business_days,
    }
    if estimated_lead_days is not None:
        normalized["estimated_lead_days"] = estimated_lead_days
    return normalized


def get_vendor_policy_preset(preset_name):
    preset = VENDOR_POLICY_PRESETS.get(str(preset_name or "").strip(), {})
    normalized = normalize_vendor_policy(preset)
    normalized["label"] = preset.get("label", "")
    return normalized


def vendor_policy_preset_options():
    return [(key, VENDOR_POLICY_PRESETS[key]["label"]) for key in VENDOR_POLICY_PRESETS]


def resolve_vendor_policy(vendor, vendor_policies, default_preset_name=""):
    normalized_vendor = _normalize_vendor(vendor)
    normalized_policies = vendor_policies or {}
    raw_policy = normalized_policies.get(normalized_vendor)
    if raw_policy:
        return normalize_vendor_policy(raw_policy), "saved_policy", ""
    preset_name = str(default_preset_name or "").strip()
    if preset_name:
        preset = get_vendor_policy_preset(preset_name)
        if preset.get("label"):
            return normalize_vendor_policy(preset), "default_preset", preset.get("label", "")
    return normalize_vendor_policy({}), "none", ""


def release_timing_mode(policy_or_item):
    shipping_policy = str((policy_or_item or {}).get("shipping_policy", "") or "").strip() or "release_immediately"
    lead_days = _safe_nonnegative_int((policy_or_item or {}).get("release_lead_business_days"), 1)
    if shipping_policy == "release_immediately":
        return "same_day_release"
    if shipping_policy == "hold_for_threshold":
        return "release_on_threshold"
    if shipping_policy in ("hold_for_free_day", "hybrid_free_day_threshold"):
        if lead_days <= 0:
            return "release_on_target_ship_day"
        if lead_days == 1:
            return "release_one_business_day_before_ship_day"
        return "vendor_specific_lead_days"
    return "same_day_release"


def vendor_release_plan_status(row):
    shipping_policy = str((row or {}).get("shipping_policy", "") or "").strip()
    timing_mode = str((row or {}).get("release_timing_mode", "") or "").strip()
    release_now_count = int(_safe_float((row or {}).get("release_now_count"), 0.0))
    planned_today_count = int(_safe_float((row or {}).get("planned_today_count"), 0.0))
    held_count = int(_safe_float((row or {}).get("held_count"), 0.0))
    threshold_shortfall = _safe_float((row or {}).get("vendor_threshold_shortfall"), 0.0)
    paid_urgent_count = int(_safe_float((row or {}).get("paid_urgent_count"), 0.0))
    vendor_urgent_consolidation_count = int(_safe_float((row or {}).get("vendor_urgent_consolidation_count"), 0.0))
    urgent_release_count = int(_safe_float((row or {}).get("urgent_release_count"), 0.0))

    if release_now_count > 0:
        if paid_urgent_count > 0:
            return "release_now_paid_urgent"
        if vendor_urgent_consolidation_count > 0 or urgent_release_count > 0:
            return "release_now_urgent"
        return "release_now"
    if planned_today_count > 0:
        if timing_mode == "release_on_target_ship_day":
            return "release_on_next_free_ship_day"
        return "release_on_order_ahead_date"
    if held_count > 0:
        if shipping_policy == "hold_for_threshold":
            return "hold_accumulating_to_threshold" if threshold_shortfall > 0 else "release_now"
        if shipping_policy == "hybrid_free_day_threshold" and threshold_shortfall > 0:
            return "hold_accumulating_to_threshold"
        if shipping_policy in ("hold_for_free_day", "hybrid_free_day_threshold"):
            if timing_mode == "release_on_target_ship_day":
                return "release_on_next_free_ship_day"
            return "release_on_order_ahead_date"
    return "release_now"


def vendor_release_plan_status_label(status):
    return {
        "release_now": "Release Now",
        "release_now_paid_urgent": "Release Now: Paid Urgent",
        "release_now_urgent": "Release Now: Urgent",
        "hold_accumulating_to_threshold": "Hold Toward Threshold",
        "release_on_next_free_ship_day": "Release On Free-Ship Day",
        "release_on_order_ahead_date": "Release On Order-Ahead Date",
    }.get(status, status or "")


def release_decision_detail_label(detail):
    return {
        "release_now_policy_default": "Release now by policy",
        "release_now_threshold_reached": "Release now: threshold reached",
        "release_now_free_day_today": "Release now: free-ship day",
        "release_now_urgent_floor": "Release now: urgent floor",
        "release_now_paid_urgent_freight": "Release now: paid urgent freight",
        "hold_until_free_day": "Hold until free-ship day",
        "hold_for_threshold": "Hold for threshold",
        "export_next_business_day_for_free_day": "Export next business day for free day",
        "release_now_vendor_urgent_consolidation": "Release now: vendor urgent consolidation",
        "release_now_paid_urgent_vendor_consolidation": "Release now: paid urgent vendor consolidation",
    }.get(detail or "", detail or "")


def vendor_release_detail_label(row):
    paid_urgent_count = int(_safe_float((row or {}).get("paid_urgent_count"), 0.0))
    vendor_urgent_consolidation_count = int(_safe_float((row or {}).get("vendor_urgent_consolidation_count"), 0.0))
    urgent_release_count = int(_safe_float((row or {}).get("urgent_release_count"), 0.0))
    if paid_urgent_count > 0 and vendor_urgent_consolidation_count > 0:
        return "Paid urgent freight + vendor consolidation"
    if paid_urgent_count > 0:
        return "Paid urgent freight"
    if urgent_release_count > 0 and vendor_urgent_consolidation_count > 0:
        return "Urgent floor + vendor consolidation"
    if vendor_urgent_consolidation_count > 0:
        return "Vendor urgent consolidation"
    if urgent_release_count > 0:
        return "Urgent floor release"
    return str((row or {}).get("release_decision_detail_label", "") or "").strip()


def estimated_value_source_label(source):
    return {
        "inventory_repl_cost": "Inventory repl_cost",
        "missing_repl_cost": "Missing inventory repl_cost",
        "zero_repl_cost": "Zero inventory repl_cost",
        "invalid_repl_cost": "Invalid inventory repl_cost",
        "suspicious_repl_cost": "Suspicious inventory repl_cost (possible stale or data-entry error)",
    }.get(source or "", source or "")


def value_confidence_label(confidence):
    return {
        "none": "None",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }.get(confidence or "", confidence or "")


def item_cost_data(item, inventory_lookup):
    key = (item.get("line_code", ""), item.get("item_code", ""))
    inv = inventory_lookup.get(key, {}) if inventory_lookup else {}
    qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
    raw_cost = inv.get("repl_cost")
    unit_cost = None
    source = "missing_repl_cost"
    if raw_cost not in (None, ""):
        try:
            unit_cost = float(raw_cost)
        except (TypeError, ValueError):
            source = "invalid_repl_cost"
            unit_cost = None
        else:
            if unit_cost > 0:
                # Flag costs that are implausibly extreme: above $500,000/unit or
                # below $0.0001/unit (but nonzero) are almost certainly data errors.
                if unit_cost > 500_000 or unit_cost < 0.0001:
                    source = "suspicious_repl_cost"
                else:
                    source = "inventory_repl_cost"
            elif unit_cost == 0:
                source = "zero_repl_cost"
                unit_cost = 0.0
            else:
                source = "invalid_repl_cost"
                unit_cost = None
    estimated_order_value = (unit_cost * qty) if source == "inventory_repl_cost" and unit_cost is not None else 0.0
    confidence = "high" if source == "inventory_repl_cost" else "low"
    return {
        "unit_cost": unit_cost,
        "estimated_order_value": estimated_order_value,
        "source": source,
        "source_label": estimated_value_source_label(source),
        "confidence": confidence,
        "confidence_label": value_confidence_label(confidence),
    }


def estimate_item_order_value(item, inventory_lookup):
    return item_cost_data(item, inventory_lookup)["estimated_order_value"]


def item_has_known_cost(item, inventory_lookup):
    return item_cost_data(item, inventory_lookup)["source"] == "inventory_repl_cost"


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
        cost_data = item_cost_data(item, inventory_lookup)
        entry["item_count"] = entry.get("item_count", 0) + 1
        entry["known_value_total"] = entry.get("known_value_total", 0.0) + _safe_float(cost_data.get("estimated_order_value"), 0.0)
        entry.setdefault("missing_cost", 0)
        entry.setdefault("zero_cost", 0)
        entry.setdefault("invalid_cost", 0)
        entry.setdefault("suspicious_cost", 0)
        if cost_data["source"] == "inventory_repl_cost":
            entry["known"] += 1
        else:
            entry["unknown"] += 1
            if cost_data["source"] == "missing_repl_cost":
                entry["missing_cost"] += 1
            elif cost_data["source"] == "zero_repl_cost":
                entry["zero_cost"] += 1
            elif cost_data["source"] == "suspicious_repl_cost":
                entry["suspicious_cost"] += 1
            else:
                entry["invalid_cost"] += 1
    for vendor, entry in coverage.items():
        known = entry["known"]
        unknown = entry["unknown"]
        total = known + unknown
        if total <= 0:
            label = "none"
            confidence = "none"
        elif unknown <= 0:
            label = "complete"
            confidence = "high"
        elif known <= 0:
            label = "missing"
            confidence = "low"
        else:
            label = "partial"
            confidence = "medium"
        entry["label"] = label
        entry["confidence"] = confidence
        entry["known_pct"] = (known / total * 100.0) if total > 0 else 0.0
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


def _previous_business_days(target_date, business_days=1):
    if target_date is None:
        return None
    remaining = max(0, _safe_nonnegative_int(business_days, 1))
    candidate = target_date
    while remaining > 0:
        candidate -= timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        remaining -= 1
    return candidate


def _format_date(value):
    if not value:
        return ""
    return value.isoformat()


def _set_release_targets(item, *, release_date=None, order_date=None):
    item["target_release_date"] = _format_date(release_date)
    item["target_order_date"] = _format_date(order_date)


def shipping_planning_dates(policy_or_item, now=None):
    current_dt = now or datetime.now()
    weekdays = (policy_or_item or {}).get("preferred_free_ship_weekdays", [])
    release_lead_business_days = _safe_nonnegative_int((policy_or_item or {}).get("release_lead_business_days"), 1)
    next_free_ship_date = _next_preferred_weekday(current_dt, weekdays)
    planned_export_date = _previous_business_days(next_free_ship_date, release_lead_business_days)
    return {
        "next_free_ship_date": next_free_ship_date,
        "planned_export_date": planned_export_date,
        "release_lead_business_days": release_lead_business_days,
        "release_timing_mode": release_timing_mode(policy_or_item),
    }


def release_bucket(item):
    decision = str(item.get("release_decision", "") or "").strip()
    if decision in ("hold_for_free_day", "hold_for_threshold"):
        return "held"
    if decision == "export_next_business_day_for_free_day":
        return "planned_today"
    return "release_now"


def is_critical_shipping_hold(item):
    if release_bucket(item) != "held":
        return False
    if str(item.get("status", "") or "").strip().lower() in ("review", "warning", "error"):
        return True
    if bool(item.get("review_required")):
        return True
    if str(item.get("reorder_attention_signal", "") or "").strip().lower() == "review_missed_reorder":
        return True
    if str(item.get("recency_review_bucket", "") or "").strip() in (
        "critical_min_rule_protected",
        "critical_rule_protected",
    ):
        return True
    if str(item.get("sales_health_signal", "") or "").strip().lower() in ("critical", "at_risk"):
        return True
    return False


def item_recommended_action(item):
    bucket = release_bucket(item)
    if bucket == "held":
        if is_critical_shipping_hold(item):
            return "Review Critical Hold"
        target_order_date = str(item.get("target_order_date", "") or "").strip()
        if target_order_date:
            return f"Hold Until {target_order_date}"
        return "Hold"
    if bucket == "planned_today":
        return "Export Planned Today"
    if str(item.get("status", "") or "").strip().lower() in ("review", "warning", "error"):
        return "Review Before Export"
    if bool(item.get("review_required")):
        return "Review Before Export"
    if str(item.get("recency_confidence", "") or "").strip().lower() == "low":
        return "Review Before Export"
    if str(item.get("vendor_value_coverage", "") or "").strip().lower() in ("partial", "missing"):
        return "Review Before Export"
    if str(item.get("reorder_attention_signal", "") or "").strip().lower() == "review_missed_reorder":
        return "Review Before Export"
    return "Export Now"


def vendor_has_value_risk(row):
    coverage = str((row or {}).get("vendor_value_coverage", "") or "").strip().lower()
    confidence = str((row or {}).get("vendor_value_confidence", "") or "").strip().lower()
    if coverage in ("partial", "missing"):
        return True
    if confidence == "low":
        return True
    return any(
        int(_safe_float((row or {}).get(field), 0.0)) > 0
        for field in (
            "vendor_value_unknown_items",
            "vendor_value_missing_cost_items",
            "vendor_value_zero_cost_items",
            "vendor_value_invalid_cost_items",
        )
    )


def vendor_recommended_action(row):
    release_now_count = int(_safe_float((row or {}).get("release_now_count"), 0.0))
    planned_today_count = int(_safe_float((row or {}).get("planned_today_count"), 0.0))
    held_count = int(_safe_float((row or {}).get("held_count"), 0.0))
    critical_held_count = int(_safe_float((row or {}).get("critical_held_count"), 0.0))
    status = str((row or {}).get("release_plan_status", "") or "").strip()
    planned_export_date = str((row or {}).get("planned_export_date", "") or "").strip()
    next_free_ship_date = str((row or {}).get("next_free_ship_date", "") or "").strip()
    paid_urgent_count = int(_safe_float((row or {}).get("paid_urgent_count"), 0.0))
    vendor_urgent_consolidation_count = int(_safe_float((row or {}).get("vendor_urgent_consolidation_count"), 0.0))
    urgent_release_count = int(_safe_float((row or {}).get("urgent_release_count"), 0.0))

    if critical_held_count > 0:
        return "Review Critical Holds"
    if paid_urgent_count > 0:
        return "Review Paid Urgent Freight"
    if vendor_urgent_consolidation_count > 0:
        return "Export Urgent Consolidated Now"
    if urgent_release_count > 0:
        return "Export Urgent Now"
    if vendor_has_value_risk(row):
        return "Review Value Coverage"
    if release_now_count > 0 and planned_today_count > 0:
        return "Export All Due"
    if release_now_count > 0:
        return "Export Now"
    if planned_today_count > 0:
        return "Export Planned Today"
    if held_count > 0:
        if status == "hold_accumulating_to_threshold":
            return "Wait for Threshold"
        if planned_export_date:
            return f"Wait for {planned_export_date}"
        if next_free_ship_date:
            return f"Wait for {next_free_ship_date}"
        return "Hold"
    return "No Action"


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
                "critical_held_count": 0,
                "release_now_value": 0.0,
                "planned_today_value": 0.0,
                "held_value": 0.0,
                "urgent_release_count": 0,
                "vendor_urgent_consolidation_count": 0,
                "paid_urgent_count": 0,
                "vendor_order_value_total": _safe_float(item.get("vendor_order_value_total"), 0.0),
                "vendor_threshold_current_total": _safe_float(item.get("vendor_threshold_current_total"), 0.0),
                "vendor_threshold_shortfall": _safe_float(item.get("vendor_threshold_shortfall"), 0.0),
                "vendor_threshold_progress_pct": _safe_float(item.get("vendor_threshold_progress_pct"), 0.0),
                "vendor_value_coverage": item.get("vendor_value_coverage") or "none",
                "vendor_value_confidence": item.get("vendor_value_confidence") or "none",
                "vendor_value_known_pct": _safe_float(item.get("vendor_value_known_pct"), 0.0),
                "vendor_value_known_items": int(_safe_float(item.get("vendor_value_known_items"), 0.0)),
                "vendor_value_unknown_items": int(_safe_float(item.get("vendor_value_unknown_items"), 0.0)),
                "vendor_value_missing_cost_items": int(_safe_float(item.get("vendor_value_missing_cost_items"), 0.0)),
                "vendor_value_zero_cost_items": int(_safe_float(item.get("vendor_value_zero_cost_items"), 0.0)),
                "vendor_value_invalid_cost_items": int(_safe_float(item.get("vendor_value_invalid_cost_items"), 0.0)),
                "release_decision_detail_label": item.get("release_decision_detail_label") or item.get("release_decision_detail") or "",
                "next_free_ship_date": item.get("next_free_ship_date") or "",
                "planned_export_date": item.get("planned_export_date") or "",
                "shipping_policy": item.get("shipping_policy") or "",
                "release_lead_business_days": _safe_nonnegative_int(item.get("release_lead_business_days"), 1),
                "release_timing_mode": item.get("release_timing_mode") or "",
                "release_plan_status": "",
                "recommended_action": "",
            },
        )
        value = _safe_float(item.get("estimated_order_value"), 0.0)
        row[f"{bucket}_count"] += 1
        row[f"{bucket}_value"] += value
        trigger = str(item.get("release_trigger", "") or "").strip()
        detail = str(item.get("release_decision_detail", "") or "").strip()
        decision = str(item.get("release_decision", "") or "").strip()
        if trigger == "urgent_floor":
            row["urgent_release_count"] += 1
        if trigger == "vendor_urgent_consolidation":
            row["vendor_urgent_consolidation_count"] += 1
        if decision == "release_now_paid_urgent_freight" or detail == "release_now_paid_urgent_vendor_consolidation":
            row["paid_urgent_count"] += 1
        if is_critical_shipping_hold(item):
            row["critical_held_count"] += 1
        row["vendor_order_value_total"] = max(row["vendor_order_value_total"], _safe_float(item.get("vendor_order_value_total"), 0.0))
        row["vendor_threshold_current_total"] = max(row["vendor_threshold_current_total"], _safe_float(item.get("vendor_threshold_current_total"), 0.0))
        row["vendor_threshold_shortfall"] = max(row["vendor_threshold_shortfall"], _safe_float(item.get("vendor_threshold_shortfall"), 0.0))
        row["vendor_threshold_progress_pct"] = max(row["vendor_threshold_progress_pct"], _safe_float(item.get("vendor_threshold_progress_pct"), 0.0))
        if row["vendor_value_coverage"] in ("none", "") and item.get("vendor_value_coverage"):
            row["vendor_value_coverage"] = item.get("vendor_value_coverage")
        elif row["vendor_value_coverage"] != item.get("vendor_value_coverage") and item.get("vendor_value_coverage"):
            coverage_priority = {"missing": 3, "partial": 2, "complete": 1, "none": 0}
            if coverage_priority.get(item.get("vendor_value_coverage"), 0) > coverage_priority.get(row["vendor_value_coverage"], 0):
                row["vendor_value_coverage"] = item.get("vendor_value_coverage")
        confidence_priority = {"low": 3, "medium": 2, "high": 1, "none": 0}
        current_confidence = str(item.get("vendor_value_confidence", "") or "")
        if confidence_priority.get(current_confidence, 0) > confidence_priority.get(row.get("vendor_value_confidence", "none"), 0):
            row["vendor_value_confidence"] = current_confidence
        row["vendor_value_known_pct"] = max(row["vendor_value_known_pct"], _safe_float(item.get("vendor_value_known_pct"), 0.0))
        row["vendor_value_known_items"] = max(row["vendor_value_known_items"], int(_safe_float(item.get("vendor_value_known_items"), 0.0)))
        row["vendor_value_unknown_items"] = max(row["vendor_value_unknown_items"], int(_safe_float(item.get("vendor_value_unknown_items"), 0.0)))
        row["vendor_value_missing_cost_items"] = max(row["vendor_value_missing_cost_items"], int(_safe_float(item.get("vendor_value_missing_cost_items"), 0.0)))
        row["vendor_value_zero_cost_items"] = max(row["vendor_value_zero_cost_items"], int(_safe_float(item.get("vendor_value_zero_cost_items"), 0.0)))
        row["vendor_value_invalid_cost_items"] = max(row["vendor_value_invalid_cost_items"], int(_safe_float(item.get("vendor_value_invalid_cost_items"), 0.0)))
        if not row["release_decision_detail_label"] and (item.get("release_decision_detail_label") or item.get("release_decision_detail")):
            row["release_decision_detail_label"] = item.get("release_decision_detail_label") or item.get("release_decision_detail")
        if not row["next_free_ship_date"] and item.get("next_free_ship_date"):
            row["next_free_ship_date"] = item.get("next_free_ship_date")
        if not row["planned_export_date"] and item.get("planned_export_date"):
            row["planned_export_date"] = item.get("planned_export_date")
        if not row["shipping_policy"] and item.get("shipping_policy"):
            row["shipping_policy"] = item.get("shipping_policy")
        row["release_lead_business_days"] = max(
            row.get("release_lead_business_days", 1),
            _safe_nonnegative_int(item.get("release_lead_business_days"), 1),
        )
        if not row.get("release_timing_mode") and item.get("release_timing_mode"):
            row["release_timing_mode"] = item.get("release_timing_mode")
    rows = [plan[vendor] for vendor in sorted(plan)]
    for row in rows:
        row["release_decision_detail_label"] = vendor_release_detail_label(row)
        row["release_plan_status"] = vendor_release_plan_status(row)
        row["release_plan_label"] = vendor_release_plan_status_label(row["release_plan_status"])
        row["recommended_action"] = vendor_recommended_action(row)
    return rows


def _build_release_why(base_why, item):
    planning_parts = []
    if item.get("shipping_policy_source"):
        source_label = {
            "saved_policy": "saved vendor policy",
            "default_preset": "default vendor preset",
        }.get(item.get("shipping_policy_source"), item.get("shipping_policy_source"))
        if item.get("shipping_policy_source") == "default_preset" and item.get("shipping_policy_preset_label"):
            source_label = f"{source_label} ({item['shipping_policy_preset_label']})"
        planning_parts.append(f"Shipping policy source: {source_label}")
    threshold = _safe_float(item.get("shipping_policy_threshold"), 0.0)
    current_total = _safe_float(item.get("vendor_threshold_current_total", item.get("vendor_order_value_total")), 0.0)
    threshold_progress_pct = _safe_float(item.get("vendor_threshold_progress_pct"), 100.0)
    threshold_shortfall = _safe_float(item.get("vendor_threshold_shortfall"), 0.0)
    coverage_label = item.get("vendor_value_coverage", "")
    coverage_confidence = item.get("vendor_value_confidence", "")
    known = int(_safe_float(item.get("vendor_value_known_items"), 0.0))
    unknown = int(_safe_float(item.get("vendor_value_unknown_items"), 0.0))
    missing_cost = int(_safe_float(item.get("vendor_value_missing_cost_items"), 0.0))
    zero_cost = int(_safe_float(item.get("vendor_value_zero_cost_items"), 0.0))
    invalid_cost = int(_safe_float(item.get("vendor_value_invalid_cost_items"), 0.0))
    estimated_value_source = str(item.get("estimated_order_value_source_label", "") or "").strip()
    next_free_ship_date = item.get("next_free_ship_date", "")
    planned_export_date = item.get("planned_export_date", "")
    if threshold > 0:
        planning_parts.append(
            f"Vendor threshold progress: {current_total:g}/{threshold:g} ({threshold_progress_pct:.0f}%, short {threshold_shortfall:g})"
        )
    if coverage_label not in ("", "complete"):
        detail = f"Vendor value coverage: {coverage_label}"
        if coverage_confidence:
            detail += f" ({coverage_confidence} confidence"
        else:
            detail += " ("
        detail += f"; {known} known, {unknown} unknown"
        if missing_cost:
            detail += f", missing cost {missing_cost}"
        if zero_cost:
            detail += f", zero cost {zero_cost}"
        if invalid_cost:
            detail += f", invalid cost {invalid_cost}"
        detail += ")"
        planning_parts.append(detail)
    if estimated_value_source and item.get("estimated_order_value_source") != "inventory_repl_cost":
        planning_parts.append(f"Estimated value source: {estimated_value_source}")
    if next_free_ship_date:
        planning_parts.append(f"Next free-ship date: {next_free_ship_date}")
    if planned_export_date:
        planning_parts.append(f"Planned export date: {planned_export_date}")
    if item.get("target_order_date"):
        planning_parts.append(f"Target order date: {item['target_order_date']}")
    if item.get("target_release_date"):
        planning_parts.append(f"Target release date: {item['target_release_date']}")
    if item.get("urgent_release_mode") and item.get("urgent_release_mode") != "release_now":
        planning_parts.append(f"Urgent override: {item['urgent_release_mode']}")
    if item.get("shipping_policy") in ("hold_for_free_day", "hybrid_free_day_threshold") and item.get("release_lead_business_days") is not None:
        planning_parts.append(f"Release lead days: {int(_safe_float(item['release_lead_business_days'], 0.0))}")
    if item.get("release_timing_mode"):
        planning_parts.append(f"Timing mode: {item['release_timing_mode']}")
    reason = item.get("release_reason", "")
    detail_label = release_decision_detail_label(item.get("release_decision_detail", ""))
    if detail_label:
        planning_parts.append(f"Decision detail: {detail_label}")
    return " | ".join(part for part in (base_why, *planning_parts, f"Release: {reason}" if reason else "") if part)


def _choose_release_decision(item, policy, vendor_total, now):
    shipping_policy = policy.get("shipping_policy", "release_immediately")
    weekdays = policy.get("preferred_free_ship_weekdays", [])
    threshold = max(0.0, _safe_float(policy.get("free_freight_threshold"), 0.0))
    urgent_floor = max(0.0, _safe_float(policy.get("urgent_release_floor"), 0.0))
    urgent_release_mode = str(policy.get("urgent_release_mode", "release_now") or "release_now").strip() or "release_now"
    current_dt = now or datetime.now()
    current_date = _safe_date(current_dt)
    today_name = current_dt.strftime("%A")
    inventory_position = _safe_float(item.get("inventory_position"), 0.0)
    urgent = urgent_floor > 0 and inventory_position <= urgent_floor
    planning = shipping_planning_dates(policy, current_dt)
    next_free_ship_date = planning["next_free_ship_date"]
    previous_business_export_date = planning["planned_export_date"]

    if urgent:
        if urgent_release_mode == "paid_urgent_freight":
            return {
                "decision": "release_now_paid_urgent_freight",
                "detail": "release_now_paid_urgent_freight",
                "reason": (
                    f"Released now on paid urgent freight because inventory position {inventory_position:g} "
                    f"is at or below urgent floor {urgent_floor:g}"
                ),
                "trigger": "urgent_floor",
            }
        return {
            "decision": "release_now",
            "detail": "release_now_urgent_floor",
            "reason": f"Released now because inventory position {inventory_position:g} is at or below urgent floor {urgent_floor:g}",
            "trigger": "urgent_floor",
        }

    if shipping_policy == "hold_for_free_day":
        if weekdays and today_name in weekdays:
            return {
                "decision": "release_now",
                "detail": "release_now_free_day_today",
                "reason": f"Released now because today is preferred free-shipping day ({today_name})",
                "trigger": "free_day_today",
            }
        if previous_business_export_date and current_date == previous_business_export_date:
            free_day_name = next_free_ship_date.strftime("%A") if next_free_ship_date else "scheduled free-shipping day"
            return {
                "decision": "export_next_business_day_for_free_day",
                "detail": "export_next_business_day_for_free_day",
                "reason": f"Export today so the PO is ready for vendor free-shipping day ({free_day_name} {_format_date(next_free_ship_date)})",
                "trigger": "planned_free_day",
            }
        if weekdays:
            extra = ""
            if next_free_ship_date:
                extra = (
                    f"; next free-shipping day {_format_date(next_free_ship_date)}"
                    f"; planned export {_format_date(previous_business_export_date)}"
                )
            return {
                "decision": "hold_for_free_day",
                "detail": "hold_until_free_day",
                "reason": f"Held for vendor free-shipping day ({', '.join(weekdays)}{extra})",
                "trigger": "hold_for_free_day",
            }
        return {
            "decision": "release_now",
            "detail": "release_now_policy_default",
            "reason": "Released now because no preferred free-shipping day is configured",
            "trigger": "policy_default",
        }

    if shipping_policy == "hold_for_threshold":
        if threshold > 0 and vendor_total >= threshold:
            return {
                "decision": "release_now",
                "detail": "release_now_threshold_reached",
                "reason": f"Released now because vendor threshold {threshold:g} was reached",
                "trigger": "threshold_reached",
            }
        if threshold > 0:
            return {
                "decision": "hold_for_threshold",
                "detail": "hold_for_threshold",
                "reason": f"Held for freight threshold {threshold:g} (current vendor total {vendor_total:g})",
                "trigger": "hold_for_threshold",
            }
        return {
            "decision": "release_now",
            "detail": "release_now_policy_default",
            "reason": "Released now because no freight threshold is configured",
            "trigger": "policy_default",
        }

    if shipping_policy == "hybrid_free_day_threshold":
        if threshold > 0 and vendor_total >= threshold:
            return {
                "decision": "release_now",
                "detail": "release_now_threshold_reached",
                "reason": f"Released now because vendor threshold {threshold:g} was reached",
                "trigger": "threshold_reached",
            }
        if weekdays and today_name in weekdays:
            return {
                "decision": "release_now",
                "detail": "release_now_free_day_today",
                "reason": f"Released now because today is preferred free-shipping day ({today_name})",
                "trigger": "free_day_today",
            }
        if previous_business_export_date and current_date == previous_business_export_date:
            free_day_name = next_free_ship_date.strftime("%A") if next_free_ship_date else "scheduled free-shipping day"
            return {
                "decision": "export_next_business_day_for_free_day",
                "detail": "export_next_business_day_for_free_day",
                "reason": f"Export today so the PO is ready for vendor free-shipping day ({free_day_name} {_format_date(next_free_ship_date)})",
                "trigger": "planned_free_day",
            }
        if weekdays:
            extra = ""
            if next_free_ship_date:
                extra = (
                    f"; next free-shipping day {_format_date(next_free_ship_date)}"
                    f"; planned export {_format_date(previous_business_export_date)}"
                )
            return {
                "decision": "hold_for_free_day",
                "detail": "hold_until_free_day",
                "reason": f"Held for vendor free-shipping day ({', '.join(weekdays)}{extra})",
                "trigger": "hold_for_free_day",
            }
        if threshold > 0:
            return {
                "decision": "hold_for_threshold",
                "detail": "hold_for_threshold",
                "reason": f"Held for freight threshold {threshold:g} (current vendor total {vendor_total:g})",
                "trigger": "hold_for_threshold",
            }
        return {
            "decision": "release_now",
            "detail": "release_now_policy_default",
            "reason": "Released now because no vendor hold condition is configured",
            "trigger": "policy_default",
        }

    return {
        "decision": "release_now",
        "detail": "release_now_policy_default",
        "reason": "Released now by vendor policy",
        "trigger": "policy_default",
    }


def annotate_release_decisions(session, now=None):
    inventory_lookup = getattr(session, "inventory_lookup", {}) or {}
    vendor_policies = getattr(session, "vendor_policies", {}) or {}
    default_policy_preset = str(getattr(session, "default_vendor_policy_preset", "") or "").strip()
    source_items = list(getattr(session, "assigned_items", []) or [])
    if not source_items:
        source_items = list(getattr(session, "filtered_items", []) or [])
    vendor_totals = build_vendor_order_totals(source_items, inventory_lookup)
    vendor_value_coverage = build_vendor_value_coverage(source_items, inventory_lookup)
    current_dt = now or datetime.now()
    annotated_items = []

    for collection_name in ("filtered_items", "assigned_items"):
        for item in getattr(session, collection_name, []) or []:
            vendor = _normalize_vendor(item.get("vendor", ""))
            qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
            policy, policy_source, preset_label = resolve_vendor_policy(vendor, vendor_policies, default_policy_preset)
            threshold = max(0.0, _safe_float(policy.get("free_freight_threshold"), 0.0))
            current_total = vendor_totals.get(vendor, 0.0) if vendor else 0.0
            coverage_entry = vendor_value_coverage.get(vendor, {
                "label": "none",
                "confidence": "none",
                "known": 0,
                "unknown": 0,
                "known_pct": 0.0,
                "missing_cost": 0,
                "zero_cost": 0,
                "invalid_cost": 0,
            })
            threshold_shortfall = max(0.0, threshold - current_total) if threshold > 0 else 0.0
            threshold_progress_pct = min(100.0, (current_total / threshold) * 100.0) if threshold > 0 else 100.0
            planning = shipping_planning_dates(policy, current_dt)
            next_free_ship_date = planning["next_free_ship_date"]
            planned_export_date = planning["planned_export_date"]
            cost_data = item_cost_data(item, inventory_lookup)
            item["estimated_order_unit_cost"] = cost_data["unit_cost"]
            item["estimated_order_value"] = cost_data["estimated_order_value"]
            item["estimated_order_value_source"] = cost_data["source"]
            item["estimated_order_value_source_label"] = cost_data["source_label"]
            item["estimated_order_value_confidence"] = cost_data["confidence"]
            item["estimated_order_value_confidence_label"] = cost_data["confidence_label"]
            item["vendor_order_value_total"] = current_total
            item["vendor_threshold_current_total"] = current_total
            item["vendor_value_coverage"] = coverage_entry["label"]
            item["vendor_value_confidence"] = coverage_entry.get("confidence", "none")
            item["vendor_value_known_pct"] = coverage_entry.get("known_pct", 0.0)
            item["vendor_value_known_items"] = coverage_entry["known"]
            item["vendor_value_unknown_items"] = coverage_entry["unknown"]
            item["vendor_value_missing_cost_items"] = coverage_entry.get("missing_cost", 0)
            item["vendor_value_zero_cost_items"] = coverage_entry.get("zero_cost", 0)
            item["vendor_value_invalid_cost_items"] = coverage_entry.get("invalid_cost", 0)
            item["vendor_threshold_shortfall"] = threshold_shortfall
            item["vendor_threshold_progress_pct"] = threshold_progress_pct
            item["next_free_ship_date"] = _format_date(next_free_ship_date)
            item["planned_export_date"] = _format_date(planned_export_date)
            _set_release_targets(item)
            item["release_decision"] = ""
            item["release_reason"] = ""
            item["release_trigger"] = ""
            item["release_decision_detail"] = ""
            item["release_decision_detail_label"] = ""
            item["shipping_policy"] = ""
            item["shipping_policy_source"] = ""
            item["shipping_policy_preset_label"] = ""
            item["shipping_policy_weekdays"] = []
            item["shipping_policy_threshold"] = 0.0
            item["urgent_release_mode"] = "release_now"
            item["release_lead_business_days"] = 1
            item["release_timing_mode"] = release_timing_mode({"shipping_policy": "", "release_lead_business_days": 1})
            base_why = item.get("core_why") or item.get("why", "")
            item["why"] = base_why
            item["_shipping_base_why"] = base_why
            annotated_items.append(item)

            if not vendor or qty <= 0 or policy_source == "none":
                continue

            decision_data = _choose_release_decision(item, policy, current_total, current_dt)
            decision = decision_data["decision"]
            reason = decision_data["reason"]
            item["release_decision"] = decision
            item["release_reason"] = reason
            item["release_trigger"] = decision_data.get("trigger", "")
            item["release_decision_detail"] = decision_data.get("detail", "")
            item["release_decision_detail_label"] = release_decision_detail_label(item["release_decision_detail"])
            item["shipping_policy"] = policy["shipping_policy"]
            item["shipping_policy_source"] = policy_source
            item["shipping_policy_preset_label"] = preset_label
            item["shipping_policy_weekdays"] = list(policy["preferred_free_ship_weekdays"])
            item["shipping_policy_threshold"] = policy["free_freight_threshold"]
            item["urgent_release_mode"] = policy.get("urgent_release_mode", "release_now")
            item["release_lead_business_days"] = planning["release_lead_business_days"]
            item["release_timing_mode"] = planning["release_timing_mode"]
            if decision in ("hold_for_free_day", "export_next_business_day_for_free_day"):
                _set_release_targets(
                    item,
                    release_date=next_free_ship_date,
                    order_date=planned_export_date,
                )
            elif decision == "release_now":
                _set_release_targets(
                    item,
                    release_date=_safe_date(current_dt),
                    order_date=_safe_date(current_dt),
                )
            item["why"] = _build_release_why(base_why, item)
            item["recommended_action"] = item_recommended_action(item)

    urgent_vendors = {
        _normalize_vendor(item.get("vendor", ""))
        for item in annotated_items
        if item.get("release_trigger") == "urgent_floor"
    }
    current_date = _safe_date(current_dt)
    for item in annotated_items:
        vendor = _normalize_vendor(item.get("vendor", ""))
        qty = max(0, _safe_float(item.get("final_qty", item.get("order_qty", 0)), 0.0))
        if not vendor or qty <= 0 or vendor not in urgent_vendors:
            continue
        if item.get("release_trigger") == "urgent_floor":
            item["recommended_action"] = item_recommended_action(item)
            item["why"] = _build_release_why(item.get("_shipping_base_why", item.get("core_why", "")), item)
            continue
        if item.get("release_decision") == "release_now":
            item["recommended_action"] = item_recommended_action(item)
            item["why"] = _build_release_why(item.get("_shipping_base_why", item.get("core_why", "")), item)
            continue
        urgent_items = [
            candidate for candidate in annotated_items
            if _normalize_vendor(candidate.get("vendor", "")) == vendor and candidate.get("release_trigger") == "urgent_floor"
        ]
        urgent_decision = "release_now"
        if any(candidate.get("release_decision") == "release_now_paid_urgent_freight" for candidate in urgent_items):
            urgent_decision = "release_now_paid_urgent_freight"
        urgent_codes = ", ".join(
            f"{candidate.get('line_code', '')}{candidate.get('item_code', '')}"
            for candidate in urgent_items[:3]
        )
        if len(urgent_items) > 3:
            urgent_codes += ", ..."
        item["release_decision"] = urgent_decision
        item["release_reason"] = (
            ("Released now on paid urgent freight with urgent vendor item" if urgent_decision == "release_now_paid_urgent_freight" else "Released now with urgent vendor item")
            + (f" ({urgent_codes})" if urgent_codes else "")
            + " so the vendor PO stays consolidated"
        )
        item["release_trigger"] = "vendor_urgent_consolidation"
        item["release_decision_detail"] = (
            "release_now_paid_urgent_vendor_consolidation"
            if urgent_decision == "release_now_paid_urgent_freight"
            else "release_now_vendor_urgent_consolidation"
        )
        item["release_decision_detail_label"] = release_decision_detail_label(item["release_decision_detail"])
        _set_release_targets(item, release_date=current_date, order_date=current_date)
        item["recommended_action"] = item_recommended_action(item)
        item["why"] = _build_release_why(item.get("_shipping_base_why", item.get("core_why", "")), item)

    for item in annotated_items:
        if not item.get("recommended_action"):
            item["recommended_action"] = item_recommended_action(item)
        item.pop("_shipping_base_why", None)
