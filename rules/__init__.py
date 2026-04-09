import math

REEL_REVIEW_MIN_PACK_QTY = 250
LARGE_PACK_REVIEW_MIN_PACK_QTY = 25
# Number of consecutive sessions without any new sale or receipt evidence before a
# confirmed_stocking flag expires and the item reverts to manual review.
CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE = 3
# A current suggestion that deviates from historical_order_qty by more than this
# fraction triggers suggestion_vs_history_gap review routing.
SUGGESTION_VS_HISTORY_GAP_THRESHOLD = 0.5

# --- Heuristic inference constants ---
PACK_MAX_RATIO_FOR_LARGE_PACK       = 3      # pack_qty > mx * 3 → large-pack territory
HEURISTIC_WEEKLY_PACK_RATIO         = 0.75   # weekly demand >= pack * 0.75 threshold
HEURISTIC_WEEKLY_MAX_RATIO          = 1.5    # weekly demand >= mx * 1.5 threshold
HEURISTIC_ANNUAL_PACK_RATIO         = 18.0   # annualized demand >= pack * 18
HEURISTIC_ANNUAL_MAX_RATIO          = 24.0   # annualized demand >= mx * 24
HEURISTIC_MIN_SALES_SPAN_DAYS       = 180    # minimum span for high-confidence heuristic
HEURISTIC_SHORT_SPAN_DAYS           = 14     # below this span → conservative single-pack buffer
HEURISTIC_COVER_WEEKLY_PACK_RATIO   = 0.85
HEURISTIC_COVER_WEEKLY_MAX_RATIO    = 1.75
HEURISTIC_COVER_ANNUAL_PACK_RATIO   = 26.0
HEURISTIC_COVER_ANNUAL_MAX_RATIO    = 40.0
HEURISTIC_MAX_DAYS_SINCE_SALE       = 120    # days_since_last_sale > this → skip buffer
HEURISTIC_HIGH_CONFIDENCE_THRESHOLD = 0.75   # heuristic_confidence >= this → elevated buffer allowed
# Default assumed vendor lead time (days) used in stockout risk scoring when no
# vendor-specific lead time has been inferred from session history.
DEFAULT_LEAD_TIME_DAYS = 14
# Items with no sale or receipt in this many days and no pending demand are
# classified as dead stock candidates.
DEAD_STOCK_MIN_DAYS_SINCE_SALE = 365
REEL_BLOCKLIST = (
    "BELT",
    "BOLT",
    "BOLTS",
    "NUT",
    "NUTS",
    "WASHER",
    "WASHERS",
    "SCREW",
    "SCREWS",
    "CLAMP",
    "CLAMPS",
    "FITTING",
    "FITTINGS",
    "FERRULE",
    "FERRULES",
    "NIPPLE",
    "NIPPLES",
    "SLEEVE",
    "SLEEVES",
    "SPROCKET",
    "SPROCKETS",
    "BEARING",
    "BEARINGS",
    "ASSY",
    "ASSEMBLY",
    "BRUSH",
    "CUTTER",
    "TIE",
    "TIES",
)
REEL_STRONG_PHRASES = (
    "AIRCRAFT CABLE",
    "AIRBRAKE TUBE",
)
REEL_BASE_TERMS = (
    "HOSE",
    "CABLE",
    "TUBE",
    "TUBING",
    "CORD",
    "ROPE",
)
REEL_LENGTH_TERMS = (
    " FT",
    "FT ",
    "100FT",
    "X100F",
    "X 100F",
    "ROLL",
    "COIL",
    "SPOOL",
)
HARDWARE_PACK_TERMS = (
    "BOLT",
    "BOLTS",
    "NUT",
    "NUTS",
    "WASHER",
    "WASHERS",
    "SCREW",
    "SCREWS",
    "CLAMP",
    "CLAMPS",
    "FITTING",
    "FITTINGS",
    "FASTENER",
    "FASTENERS",
)


def looks_like_reel_item(item, inv):
    """Return True when the item description suggests bulk-by-length material."""
    desc = (item.get("description") or inv.get("description") or "").upper()
    if not desc:
        return False

    if any(term in desc for term in REEL_BLOCKLIST):
        return False

    if any(phrase in desc for phrase in REEL_STRONG_PHRASES):
        return True

    if any(term in desc for term in REEL_BASE_TERMS):
        return True

    if "WIRE" in desc and any(term in desc for term in REEL_LENGTH_TERMS):
        return True

    if "CHAIN" in desc and any(term in desc for term in ("COIL", "ROLL")):
        return True

    return False


def looks_like_hardware_pack_item(item, inv):
    """Return True when the description suggests boxed/bagged hardware rather than reel stock."""
    desc = (item.get("description") or inv.get("description") or "").upper()
    if not desc:
        return False
    if looks_like_reel_item(item, inv or {}):
        return False
    return any(term in desc for term in HARDWARE_PACK_TERMS)


def classify_package_profile(item, inv, pack_qty):
    """Classify the item's replenishment/package shape for policy and UI explanations."""
    if not pack_qty:
        return "no_pack_data"
    if looks_like_reel_item(item, inv or {}):
        return "reel_stock"
    if looks_like_hardware_pack_item(item, inv or {}):
        if should_large_pack_review(item, inv or {}, pack_qty):
            return "hardware_large_pack"
        return "hardware_pack"
    if should_large_pack_review(item, inv or {}, pack_qty):
        return "large_nonreel_pack"
    if pack_qty >= LARGE_PACK_REVIEW_MIN_PACK_QTY:
        return "general_pack"
    return "unit_pack"


def package_profile_label(profile):
    return {
        "no_pack_data": "No pack data",
        "reel_stock": "Reel / bulk-by-length",
        "hardware_pack": "Hardware pack",
        "hardware_large_pack": "Large hardware pack",
        "large_nonreel_pack": "Large non-reel pack",
        "general_pack": "General pack item",
        "unit_pack": "Small unit pack",
    }.get(profile, profile or "")


def classify_replenishment_unit_mode(policy, item, pack_qty, rule):
    """Classify the replenishment-unit behavior separately from review gating."""
    if policy == "exact_qty" or not pack_qty:
        return "exact_qty"
    if policy == "soft_pack":
        return "soft_pack_min_order"
    if policy == "pack_trigger":
        return "pack_trigger_replenishment"
    if policy == "reel_review":
        return "reel_bulk_review"
    if policy == "reel_auto":
        return "pack_trigger_replenishment"
    if policy == "large_pack_review":
        return "large_pack_review"
    if pack_qty and pack_qty > 0:
        return "full_pack_round_up"
    return "exact_qty"


def replenishment_unit_mode_label(mode):
    return {
        "exact_qty": "Exact qty",
        "soft_pack_min_order": "Soft pack / min order",
        "pack_trigger_replenishment": "Pack-trigger replenishment",
        "reel_bulk_review": "Reel / bulk review",
        "large_pack_review": "Large-pack review",
        "full_pack_round_up": "Full-pack round-up",
    }.get(mode, mode or "")


def should_large_pack_review(item, inv, pack_qty):
    """Return True when a non-reel item's pack looks risky enough for manual review."""
    mx = inv.get("max") if inv else None
    if not (mx and mx > 0 and pack_qty and pack_qty > 0):
        return False
    if pack_qty < LARGE_PACK_REVIEW_MIN_PACK_QTY:
        return False
    if pack_qty <= mx * PACK_MAX_RATIO_FOR_LARGE_PACK:
        return False
    if looks_like_reel_item(item, inv or {}):
        return False

    sales_health = item.get("sales_health_signal", "")
    performance = item.get("performance_profile", "")
    days_since_last_sale = item.get("days_since_last_sale")

    if sales_health in ("dormant", "declining"):
        return True
    if performance in ("legacy", "dormant"):
        return True
    if isinstance(days_since_last_sale, (int, float)) and days_since_last_sale >= 365:
        return True
    return False


def get_rule_pack_size(rule):
    """Return a persisted pack-size override from a saved rule, if present."""
    if not rule:
        return None
    value = rule.get("pack_size")
    if value in (None, ""):
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def has_exact_qty_override(rule):
    """Return True when a rule explicitly forces exact-quantity behavior."""
    if not rule:
        return False
    if rule.get("exact_qty_override"):
        return True
    value = rule.get("pack_size")
    if value in (None, ""):
        return False
    try:
        return int(float(value)) <= 0
    except (TypeError, ValueError):
        return False


def get_rule_int(rule, field_name):
    """Return an integer-like persisted rule field, if present."""
    if not rule:
        return None
    value = rule.get(field_name)
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def get_rule_float(rule, field_name):
    """Return a float-like persisted rule field, if present."""
    if not rule:
        return None
    value = rule.get(field_name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_rule_fields(item, rule):
    """Copy persisted rule fields onto the working item for visibility and later logic."""
    item["reorder_trigger_qty"] = get_rule_int(rule, "reorder_trigger_qty")
    item["reorder_trigger_pct"] = get_rule_float(rule, "reorder_trigger_pct")
    item["minimum_packs_on_hand"] = get_rule_int(rule, "minimum_packs_on_hand")
    item["minimum_packs_on_hand_source"] = "rule" if item["minimum_packs_on_hand"] is not None else None
    item["minimum_cover_days"] = get_rule_float(rule, "minimum_cover_days")
    item["minimum_cover_days_source"] = "rule" if item["minimum_cover_days"] is not None else None
    item["minimum_cover_cycles"] = get_rule_float(rule, "minimum_cover_cycles")
    item["minimum_cover_cycles_source"] = "rule" if item["minimum_cover_cycles"] is not None else None
    item["acceptable_overstock_qty"] = get_rule_int(rule, "acceptable_overstock_qty")
    item["acceptable_overstock_pct"] = get_rule_float(rule, "acceptable_overstock_pct")


def has_pack_trigger_fields(rule):
    """Return True when a saved rule defines trigger-style replenishment fields."""
    return any(
        value is not None and value > 0
        for value in (
            get_rule_int(rule, "reorder_trigger_qty"),
            get_rule_float(rule, "reorder_trigger_pct"),
            get_rule_int(rule, "minimum_packs_on_hand"),
            get_rule_float(rule, "minimum_cover_days"),
            get_rule_float(rule, "minimum_cover_cycles"),
        )
    )


def _demand_is_volatile(item):
    """Return True when demand shape or signals indicate volatile/unreliable demand."""
    shape = (item.get("detailed_sales_shape") or "").lower()
    if shape in ("erratic", "lumpy"):
        return True
    health = (item.get("sales_health_signal") or "").lower()
    if health in ("declining", "dormant"):
        return True
    profile = (item.get("performance_profile") or "").lower()
    span = item.get("sales_span_days") or 0
    if profile == "intermittent" and span < HEURISTIC_MIN_SALES_SPAN_DAYS:
        return True
    return False


def _recent_history_supports_higher_buffer(item, pack_qty):
    """Return True if order history suggests the item regularly needs >= 2 packs."""
    if not pack_qty or pack_qty <= 0:
        return False
    hist = item.get("historical_order_qty")
    if isinstance(hist, (int, float)) and hist >= pack_qty * 2:
        return True
    local_qty = item.get("recent_local_order_qty") or 0
    local_count = item.get("recent_local_order_count") or 0
    if local_count > 0 and (local_qty / local_count) >= pack_qty * 2:
        return True
    return False


def compute_heuristic_confidence(item):
    """
    Return a float in [0, 1] reflecting how much loaded evidence supports
    the inferred hardware buffer policy for this item.
    Independently of recency_confidence (which governs review gating).
    """
    score = 0.0
    span = item.get("sales_span_days") or 0
    if span >= HEURISTIC_MIN_SALES_SPAN_DAYS:
        score += 0.25
    if item.get("recency_confidence") == "high":
        score += 0.25
    if item.get("performance_profile") in ("top_performer", "steady"):
        score += 0.20
    if item.get("sales_health_signal") == "active":
        score += 0.15
    if item.get("detailed_sales_shape") in ("steady_repeat", "routine_mixed"):
        score += 0.10
    days_since = item.get("days_since_last_sale")
    if isinstance(days_since, (int, float)) and days_since < 30:
        score += 0.05
    score = min(score, 1.0)
    # Hard-cap at 0.3 when sales window is too short to be meaningful
    if span < HEURISTIC_SHORT_SPAN_DAYS:
        score = min(score, 0.3)
    return score


def compute_stockout_risk_score(item, lead_time_days=None):
    """Return a 0.0–1.0 stockout risk score for an enriched item.

    0.0 — no meaningful risk (no demand, or inventory covers >= 2× lead time)
    1.0 — critical (zero cover with active demand)

    The score is based on:
    - days of inventory cover vs the assumed vendor lead time
    - a recency-confidence penalty (low-confidence data → slightly higher risk)

    Requires item["demand_signal"] and item["inventory_position"] to be stamped
    (i.e. called after enrich_item has run through calculate_inventory_position
    and determine_target_stock).
    """
    if lead_time_days is None:
        lead_time_days = DEFAULT_LEAD_TIME_DAYS
    demand_signal = item.get("demand_signal", 0) or 0
    if demand_signal <= 0:
        return 0.0
    inventory_position = item.get("inventory_position", 0) or 0
    daily_demand = demand_signal / 365.0
    days_of_cover = inventory_position / daily_demand if daily_demand > 0 else 999.0
    # Risk is 1.0 at zero cover, 0.0 at ≥ 2× lead time
    buffer_days = 2.0 * lead_time_days
    coverage_risk = max(0.0, min(1.0, 1.0 - days_of_cover / buffer_days))
    # Recency penalty: low-confidence data is less trustworthy, bumping risk slightly
    recency_confidence = (item.get("recency_confidence", "low") or "low").lower()
    recency_weight = {"high": 0.0, "medium": 0.10, "low": 0.20}.get(recency_confidence, 0.15)
    score = min(1.0, coverage_risk + recency_weight * (1.0 - coverage_risk))
    return round(score, 3)


def classify_dead_stock(item):
    """Return True when an item shows no sale or receipt movement and has no pending demand.

    Criteria (all must be met):
    - days_since_last_sale is known and >= DEAD_STOCK_MIN_DAYS_SINCE_SALE
    - no effective suspended demand (effective_qty_suspended or qty_suspended)
    - no open PO qty (qty_on_po)

    Items where `days_since_last_sale` is None are left unclassified (False) because
    missing recency data is already handled by the recency-confidence path.
    """
    days_since = item.get("days_since_last_sale")
    if not isinstance(days_since, (int, float)) or days_since < DEAD_STOCK_MIN_DAYS_SINCE_SALE:
        return False
    has_pending_suspense = bool(item.get("effective_qty_suspended") or item.get("qty_suspended", 0))
    has_open_po = bool(item.get("qty_on_po", 0))
    if has_pending_suspense or has_open_po:
        return False
    return True


def infer_minimum_packs_on_hand(item, inv, pack_qty):
    """Infer a conservative hardware pack floor for active hardware with extreme pack/max mismatch."""
    mx = inv.get("max") if inv else None
    if not (mx and mx > 0 and pack_qty and pack_qty >= LARGE_PACK_REVIEW_MIN_PACK_QTY):
        return None
    if not looks_like_hardware_pack_item(item, inv or {}):
        return None
    if should_large_pack_review(item, inv or {}, pack_qty):
        return None
    if pack_qty <= mx * PACK_MAX_RATIO_FOR_LARGE_PACK:
        return None

    sales_health = item.get("sales_health_signal", "")
    performance = item.get("performance_profile", "")
    days_since_last_sale = item.get("days_since_last_sale")

    if sales_health not in ("active", "stable", ""):
        return None
    if performance not in ("steady", "top_performer", "intermittent", ""):
        return None
    if isinstance(days_since_last_sale, (int, float)) and days_since_last_sale > HEURISTIC_MAX_DAYS_SINCE_SALE:
        return None

    if _demand_is_volatile(item):
        return 1

    sales_span_days = item.get("sales_span_days")
    weekly_demand = item.get("avg_weekly_sales_loaded")
    annualized_demand = item.get("annualized_sales_loaded")
    detailed_shape = str(item.get("detailed_sales_shape", "") or "").strip().lower()
    if not isinstance(weekly_demand, (int, float)) or weekly_demand <= 0:
        weekly_demand = item.get("demand_signal")

    if (
        isinstance(sales_span_days, (int, float))
        and sales_span_days >= HEURISTIC_MIN_SALES_SPAN_DAYS
        and isinstance(weekly_demand, (int, float))
        and weekly_demand >= max(float(pack_qty) * HEURISTIC_WEEKLY_PACK_RATIO, float(mx) * HEURISTIC_WEEKLY_MAX_RATIO)
        and isinstance(annualized_demand, (int, float))
        and annualized_demand >= max(float(pack_qty) * HEURISTIC_ANNUAL_PACK_RATIO, float(mx) * HEURISTIC_ANNUAL_MAX_RATIO)
        and performance in ("steady", "top_performer")
        and detailed_shape in ("", "steady_repeat", "routine_mixed")
    ):
        return 3
    # Elevated buffer path: high heuristic confidence + history support
    if (
        item.get("heuristic_confidence", 0) >= HEURISTIC_HIGH_CONFIDENCE_THRESHOLD
        and _recent_history_supports_higher_buffer(item, pack_qty)
    ):
        item.setdefault("reason_codes", [])
        if "heuristic_confidence_elevated_buffer" not in item.get("reason_codes", []):
            item["reason_codes"] = item.get("reason_codes", []) + ["heuristic_confidence_elevated_buffer"]
        return 3
    # A very short loaded window does not provide enough history to confidently
    # assert a two-pack floor.  Use a single-pack conservative buffer.
    if isinstance(sales_span_days, (int, float)) and sales_span_days < HEURISTIC_SHORT_SPAN_DAYS:
        return 1
    return 2


def infer_minimum_cover_cycles(item, inv, pack_qty):
    """Infer a conservative hardware cover floor for active weekly-order hardware items."""
    reorder_cycle_weeks = item.get("reorder_cycle_weeks")
    mx = inv.get("max") if inv else None
    if not (
        isinstance(reorder_cycle_weeks, (int, float))
        and reorder_cycle_weeks > 0
        and reorder_cycle_weeks <= 1
        and isinstance(pack_qty, (int, float))
        and pack_qty > 0
        and isinstance(mx, (int, float))
        and mx > 0
    ):
        return None
    if pack_qty > mx * PACK_MAX_RATIO_FOR_LARGE_PACK:
        return None
    if not looks_like_hardware_pack_item(item, inv or {}):
        return None
    if should_large_pack_review(item, inv or {}, pack_qty):
        return None

    sales_health = item.get("sales_health_signal", "")
    performance = item.get("performance_profile", "")
    days_since_last_sale = item.get("days_since_last_sale")
    if sales_health not in ("active", "stable", ""):
        return None
    if performance not in ("steady", "top_performer", "intermittent", ""):
        return None
    if isinstance(days_since_last_sale, (int, float)) and days_since_last_sale > HEURISTIC_MAX_DAYS_SINCE_SALE:
        return None

    sales_span_days = item.get("sales_span_days")
    if isinstance(sales_span_days, (int, float)) and sales_span_days < HEURISTIC_SHORT_SPAN_DAYS:
        return 1
    if _demand_is_volatile(item):
        return 1

    weekly_demand = item.get("avg_weekly_sales_loaded")
    if not isinstance(weekly_demand, (int, float)) or weekly_demand <= 0:
        weekly_demand = item.get("demand_signal")
    if not isinstance(weekly_demand, (int, float)) or weekly_demand <= 0:
        return None
    if weekly_demand < max(1.0, mx * 0.75):
        return None
    if weekly_demand < max(1.0, pack_qty * 0.5):
        return None

    annualized_demand = item.get("annualized_sales_loaded")
    detailed_shape = str(item.get("detailed_sales_shape", "") or "").strip().lower()
    if (
        isinstance(sales_span_days, (int, float))
        and sales_span_days >= HEURISTIC_MIN_SALES_SPAN_DAYS
        and weekly_demand >= max(float(pack_qty) * HEURISTIC_COVER_WEEKLY_PACK_RATIO, float(mx) * HEURISTIC_COVER_WEEKLY_MAX_RATIO)
        and isinstance(annualized_demand, (int, float))
        and annualized_demand >= max(float(pack_qty) * HEURISTIC_COVER_ANNUAL_PACK_RATIO, float(mx) * HEURISTIC_COVER_ANNUAL_MAX_RATIO)
        and performance in ("steady", "top_performer")
        and detailed_shape in ("", "steady_repeat", "routine_mixed")
    ):
        return 3
    return 2


def classify_recency_confidence(item, inv, rule):
    """Classify how trustworthy the item's sale/receipt recency evidence is."""
    # The Min/Max report's last_sale/last_receipt columns are the primary
    # signal, but items missing from that report (e.g. QOH=0 fittings the
    # X4 export skips) still have recency from the loaded Detailed Part
    # Sales / Received Parts files.  Fall back to those per-item dates so
    # they don't get force-routed to manual review with order_qty=0.
    has_last_sale = bool((inv or {}).get("last_sale")) or bool(item.get("last_sale_date"))
    has_last_receipt = (
        bool((inv or {}).get("last_receipt"))
        or bool(item.get("last_receipt_date"))
    )
    has_recent_suspense = bool(item.get("effective_qty_suspended", item.get("qty_suspended", 0)))
    has_open_po = bool(item.get("qty_on_po", 0))
    has_loaded_receipt_activity = bool(item.get("qty_received", 0))
    receipt_sales_balance = str(item.get("receipt_sales_balance", "") or "").strip().lower()
    receipt_heavy = has_loaded_receipt_activity and receipt_sales_balance == "receipt_heavy"
    protective_receipt_activity = has_loaded_receipt_activity and not receipt_heavy
    has_recent_local_order = bool(item.get("has_recent_local_order"))
    has_explicit_critical_min_rule = bool(get_rule_int(rule, "min_order_qty"))
    has_other_protective_rule = bool(
        has_pack_trigger_fields(rule)
        or (rule and rule.get("order_policy"))
    )

    if has_last_sale and has_last_receipt:
        item["recency_confidence"] = "high"
        item["data_completeness"] = "complete"
    elif has_last_sale or has_last_receipt:
        item["recency_confidence"] = "medium"
        item["data_completeness"] = "partial_recency"
    elif has_recent_suspense or has_open_po or protective_receipt_activity:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency_activity_protected"
    elif receipt_heavy:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency_receipt_heavy"
    elif has_recent_local_order:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency_local_po_protected"
    elif has_explicit_critical_min_rule:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency_critical_min_protected"
    elif has_other_protective_rule:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency_rule_protected"
    else:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency"
    return item["recency_confidence"]


def classify_low_confidence_recency(item, inv, rule):
    """Add a more actionable subtype for low-confidence recency cases."""
    if (item.get("recency_confidence") or classify_recency_confidence(item, inv, rule)) != "low":
        item["recency_review_bucket"] = None
        return None

    data_completeness = item.get("data_completeness", "")
    performance = (item.get("performance_profile", "") or "").strip().lower()
    sales_health = (item.get("sales_health_signal", "") or "").strip().lower()
    qty_received = item.get("qty_received", 0) or 0
    historical_rank = item.get("historical_rank_score", 0) or 0
    qoh = (inv or {}).get("qoh", 0) or 0

    if data_completeness == "missing_recency_critical_min_protected":
        bucket = "critical_min_rule_protected"
    elif data_completeness == "missing_recency_rule_protected":
        bucket = "critical_rule_protected"
    elif data_completeness == "missing_recency_local_po_protected":
        bucket = "recent_local_po_protected"
    elif data_completeness == "missing_recency_receipt_heavy":
        bucket = "receipt_heavy_unverified"
    elif (
        qty_received > 0
        and sales_health in ("", "unknown")
        and historical_rank < 24
    ):
        bucket = "new_or_sparse"
    elif data_completeness == "missing_recency_activity_protected":
        bucket = "activity_protected"
    elif sales_health in ("dormant", "stale") or (
        performance == "legacy" and qty_received <= 0 and qoh <= 0
    ):
        bucket = "stale_or_likely_dead"
    else:
        bucket = "missing_data_uncertain"

    item["recency_review_bucket"] = bucket
    return bucket


def recency_review_bucket_label(bucket):
    return {
        "critical_min_rule_protected": "Critical / explicit min rule",
        "critical_rule_protected": "Critical / rule-protected",
        "recent_local_po_protected": "Protected by recent local PO history",
        "receipt_heavy_unverified": "Receipt-heavy / sales-unverified",
        "activity_protected": "Protected by other activity",
        "new_or_sparse": "New or too sparse",
        "stale_or_likely_dead": "Stale / likely dead",
        "missing_data_uncertain": "Missing-data / uncertain",
    }.get(bucket, bucket or "")


def _confirmed_stocking_is_valid(rule):
    """
    Return True when the rule carries a non-expired confirmed_stocking flag.
    The flag expires after CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE consecutive
    sessions pass without any new sale or receipt evidence.
    """
    if not (rule and rule.get("confirmed_stocking")):
        return False
    sessions_without = rule.get("confirmed_stocking_sessions_without_evidence", 0) or 0
    return sessions_without < CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE


def should_force_recency_review(item, inv, rule):
    """Return True when a reorder candidate lacks enough recency evidence for auto-order."""
    recency_confidence = item.get("recency_confidence") or classify_recency_confidence(item, inv, rule)
    if recency_confidence != "low":
        return False

    # Operator has confirmed this item for stocking — bypass recency review if still valid.
    if _confirmed_stocking_is_valid(rule):
        return False

    data_completeness = item.get("data_completeness", "")
    raw_need = item.get("raw_need", 0)

    if raw_need <= 0:
        return False
    if data_completeness in ("missing_recency_critical_min_protected", "missing_recency_rule_protected"):
        return False
    if data_completeness in (
        "missing_recency_local_po_protected",
        "missing_recency_activity_protected",
        "missing_recency_receipt_heavy",
        "missing_recency",
    ):
        return True
    return False


def should_suppress_manual_only_qty(item):
    """Return True when a manual-review item should not carry a default order quantity."""
    if item.get("order_policy") != "manual_only":
        return False
    # Confirmed-stocking items keep their computed qty even in manual review.
    if item.get("confirmed_stocking") and not item.get("confirmed_stocking_expired"):
        return False
    if (item.get("recency_confidence") or "") != "low":
        return False
    return (item.get("data_completeness") or "") in (
        "missing_recency",
        "missing_recency_local_po_protected",
        "missing_recency_activity_protected",
        "missing_recency_receipt_heavy",
    )


def determine_reorder_trigger_threshold(item):
    """Compute an explicit reorder trigger threshold when rule fields define one."""
    inv = item.get("inventory", {}) or {}
    current_min = inv.get("min")
    pack_size = item.get("pack_size")
    trigger_qty = item.get("reorder_trigger_qty")
    trigger_pct = item.get("reorder_trigger_pct")
    minimum_packs_on_hand = item.get("minimum_packs_on_hand")
    minimum_cover_days = item.get("minimum_cover_days")
    minimum_cover_cycles = item.get("minimum_cover_cycles")
    demand_signal = item.get("demand_signal")
    reorder_cycle_weeks = item.get("reorder_cycle_weeks")
    avg_weekly_sales = item.get("avg_weekly_sales_loaded")

    has_explicit_trigger = (
        isinstance(trigger_qty, (int, float)) and trigger_qty > 0
    ) or (
        isinstance(trigger_pct, (int, float)) and trigger_pct > 0
    ) or (
        isinstance(minimum_packs_on_hand, (int, float)) and minimum_packs_on_hand > 0
    ) or (
        isinstance(minimum_cover_days, (int, float)) and minimum_cover_days > 0
    ) or (
        isinstance(minimum_cover_cycles, (int, float)) and minimum_cover_cycles > 0
    )
    if not has_explicit_trigger:
        item["reorder_trigger_threshold"] = None
        item["reorder_trigger_basis"] = "default_target"
        return None

    candidates = [value for value in (current_min, trigger_qty) if isinstance(value, (int, float)) and value > 0]
    if (
        isinstance(pack_size, (int, float))
        and pack_size > 0
        and isinstance(trigger_pct, (int, float))
        and trigger_pct > 0
    ):
        candidates.append(pack_size * (trigger_pct / 100.0))
    if (
        isinstance(pack_size, (int, float))
        and pack_size > 0
        and isinstance(minimum_packs_on_hand, (int, float))
        and minimum_packs_on_hand > 0
    ):
        candidates.append(pack_size * minimum_packs_on_hand)
    if (
        isinstance(demand_signal, (int, float))
        and demand_signal > 0
        and isinstance(minimum_cover_cycles, (int, float))
        and minimum_cover_cycles > 0
    ):
        candidates.append(demand_signal * minimum_cover_cycles)
    daily_demand = None
    if isinstance(avg_weekly_sales, (int, float)) and avg_weekly_sales > 0:
        daily_demand = avg_weekly_sales / 7.0
    elif (
        isinstance(demand_signal, (int, float))
        and demand_signal > 0
        and isinstance(reorder_cycle_weeks, (int, float))
        and reorder_cycle_weeks > 0
    ):
        daily_demand = demand_signal / (reorder_cycle_weeks * 7.0)
    if (
        isinstance(daily_demand, (int, float))
        and daily_demand > 0
        and isinstance(minimum_cover_days, (int, float))
        and minimum_cover_days > 0
    ):
        candidates.append(daily_demand * minimum_cover_days)

    if not candidates:
        item["reorder_trigger_threshold"] = None
        item["reorder_trigger_basis"] = "default_target"
        return None

    threshold = max(candidates)
    if isinstance(trigger_qty, (int, float)) and threshold == trigger_qty:
        basis = "trigger_qty"
    elif (
        isinstance(pack_size, (int, float))
        and pack_size > 0
        and isinstance(minimum_packs_on_hand, (int, float))
        and minimum_packs_on_hand > 0
        and math.isclose(threshold, pack_size * minimum_packs_on_hand)
    ):
        basis = "minimum_packs_on_hand"
    elif (
        isinstance(demand_signal, (int, float))
        and demand_signal > 0
        and isinstance(minimum_cover_cycles, (int, float))
        and minimum_cover_cycles > 0
        and math.isclose(threshold, demand_signal * minimum_cover_cycles)
    ):
        basis = "minimum_cover_cycles"
    elif (
        isinstance(daily_demand, (int, float))
        and daily_demand > 0
        and isinstance(minimum_cover_days, (int, float))
        and minimum_cover_days > 0
        and math.isclose(threshold, daily_demand * minimum_cover_days)
    ):
        basis = "minimum_cover_days"
    elif (
        isinstance(pack_size, (int, float))
        and pack_size > 0
        and isinstance(trigger_pct, (int, float))
        and trigger_pct > 0
        and math.isclose(threshold, pack_size * (trigger_pct / 100.0))
    ):
        basis = "trigger_pct"
    elif isinstance(current_min, (int, float)) and threshold == current_min:
        basis = "current_min"
    else:
        basis = "configured_trigger"

    item["reorder_trigger_threshold"] = threshold
    item["reorder_trigger_basis"] = basis
    return threshold


def determine_acceptable_overstock_qty(item):
    """Compute tolerated post-receipt overstock from explicit qty or pack percent settings."""
    pack_size = item.get("pack_size")
    overstock_qty = item.get("acceptable_overstock_qty")
    overstock_pct = item.get("acceptable_overstock_pct")

    candidates = []
    if isinstance(overstock_qty, (int, float)) and overstock_qty > 0:
        candidates.append(("qty", float(overstock_qty)))
    if (
        isinstance(pack_size, (int, float))
        and pack_size > 0
        and isinstance(overstock_pct, (int, float))
        and overstock_pct > 0
    ):
        candidates.append(("pct", float(pack_size) * (overstock_pct / 100.0)))

    if not candidates:
        item["acceptable_overstock_qty_effective"] = 0
        item["acceptable_overstock_basis"] = None
        return 0

    basis, tolerance = max(candidates, key=lambda entry: entry[1])
    effective_tolerance = int(math.ceil(tolerance))
    item["acceptable_overstock_qty_effective"] = effective_tolerance
    item["acceptable_overstock_basis"] = basis
    return effective_tolerance


def assess_post_receipt_overstock(item, suggested_qty):
    """Compare projected post-receipt stock against the effective target plus tolerated overstock."""
    inventory_position = item.get("inventory_position", 0) or 0
    # Use effective_order_floor when present so trigger-driven orders to a high floor are not
    # incorrectly flagged as overstock relative to the lower operational display target.
    effective_target_stock = item.get("effective_order_floor", item.get("effective_target_stock", item.get("target_stock", 0))) or 0
    acceptable_overstock = item.get("acceptable_overstock_qty_effective", 0) or 0
    resulting_stock = inventory_position + max(0, suggested_qty or 0)
    overstock_qty = max(0, resulting_stock - effective_target_stock)
    within_tolerance = overstock_qty <= acceptable_overstock

    item["projected_post_receipt_stock"] = resulting_stock
    item["projected_overstock_qty"] = overstock_qty
    item["overstock_within_tolerance"] = within_tolerance
    item["max_allowed_post_receipt_stock"] = effective_target_stock + acceptable_overstock
    return overstock_qty, within_tolerance


def calculate_inventory_position(item):
    """Calculate and persist the item's inventory position."""
    inv = item.get("inventory", {}) or {}
    qoh = max(0, inv.get("qoh", 0) or 0)
    on_po = item.get("qty_on_po", 0) or 0
    inventory_position = qoh + on_po
    item["inventory_position"] = inventory_position
    return inventory_position


def determine_target_stock(item):
    """Choose and persist the target stock basis for the item."""
    inv = item.get("inventory", {}) or {}
    previous_target_stock = item.get("target_stock")
    previous_target_basis = str(item.get("target_basis", "") or "").strip()
    current_min = inv.get("min")
    current_max = inv.get("max")
    suggested_min = item.get("suggested_min")
    suggested_max = item.get("suggested_max")
    demand_signal = item.get("demand_signal")
    if demand_signal is None:
        demand_signal = item.get("qty_sold", 0) + item.get("qty_suspended", 0)
    item["demand_signal"] = demand_signal

    target_candidates = [value for value in (current_max, suggested_max) if isinstance(value, (int, float)) and value > 0]
    if target_candidates:
        target_stock = max(target_candidates)
        if isinstance(current_max, (int, float)) and current_max == target_stock:
            item["target_basis"] = "current_max"
        else:
            item["target_basis"] = "suggested_max"
    else:
        fallback_candidates = [value for value in (current_min, suggested_min, demand_signal) if isinstance(value, (int, float)) and value > 0]
        target_stock = max(fallback_candidates) if fallback_candidates else 0
        if isinstance(current_min, (int, float)) and current_min == target_stock:
            item["target_basis"] = "current_min"
        elif isinstance(suggested_min, (int, float)) and suggested_min == target_stock:
            item["target_basis"] = "suggested_min"
        elif target_stock > 0:
            item["target_basis"] = "demand_fallback"
        else:
            item["target_basis"] = "none"

    hysteresis_applied = False
    current_basis = str(item.get("target_basis", "") or "").strip()
    if (
        current_basis in ("suggested_max", "suggested_min", "demand_fallback")
        and previous_target_basis == current_basis
        and isinstance(previous_target_stock, (int, float))
        and previous_target_stock > 0
        and isinstance(target_stock, (int, float))
        and target_stock > 0
    ):
        gap = abs(float(target_stock) - float(previous_target_stock))
        max_target = max(float(target_stock), float(previous_target_stock))
        if gap <= 1.0 or (max_target > 0 and (gap / max_target) <= 0.15):
            target_stock = previous_target_stock
            hysteresis_applied = True

    item["target_stock"] = target_stock if target_stock else 0
    item["target_stock_hysteresis_applied"] = hysteresis_applied
    return item["target_stock"]


def evaluate_reorder_trigger(item):
    """Return whether the current inventory position warrants a reorder suggestion."""
    inv = item.get("inventory", {}) or {}
    inventory_position = item.get("inventory_position")
    if inventory_position is None:
        inventory_position = calculate_inventory_position(item)

    target_stock = item.get("target_stock")
    if target_stock is None:
        target_stock = determine_target_stock(item)

    current_min = inv.get("min")
    demand_signal = item.get("demand_signal")
    if demand_signal is None:
        demand_signal = item.get("qty_sold", 0) + item.get("qty_suspended", 0)
        item["demand_signal"] = demand_signal

    trigger_threshold = determine_reorder_trigger_threshold(item)

    if demand_signal <= 0:
        if isinstance(current_min, (int, float)) and inventory_position < current_min:
            target_stock = max(value for value in (target_stock, current_min) if isinstance(value, (int, float)))
            item["target_stock"] = target_stock
            return True
        return False

    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > 0:
        return inventory_position < trigger_threshold

    return True


def calculate_raw_need(item):
    """Calculate the unconstrained order need from inventory position."""
    inventory_position = calculate_inventory_position(item)
    determine_target_stock(item)
    if not evaluate_reorder_trigger(item):
        item["effective_target_stock"] = item.get("target_stock", 0)
        item["effective_order_floor"] = item.get("target_stock", 0)
        return 0
    target_stock = item.get("target_stock", 0)
    trigger_threshold = item.get("reorder_trigger_threshold")
    # effective_target_stock is the preferred operational target and is never inflated by the
    # trigger threshold so that downstream display and reporting remain accurate.
    item["effective_target_stock"] = target_stock
    # effective_order_floor is the quantity basis for this order cycle: when a trigger threshold
    # sits above the operational target (e.g. minimum_packs_on_hand > max), we order enough to
    # clear the floor rather than leaving inventory below the trigger level.
    effective_order_floor = target_stock
    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > effective_order_floor:
        effective_order_floor = trigger_threshold
    item["effective_order_floor"] = effective_order_floor
    return max(0, int(math.ceil(effective_order_floor - inventory_position)))


def _qualifies_for_review_policy_graduation(item, inv, pack_qty, rule):
    """
    Return True if a reel_review or large_pack_review item has enough protective
    evidence to auto-order this cycle without human review.

    Graduation is blocked when the operator has explicitly set policy_locked on the rule.
    At least one evidence tier must be satisfied:

      Tier 1 — high recency + active sales health (clearest demand signal)
      Tier 2 — high recency + operator has placed a recent local order (implicit confirmation)

    When evidence weakens in a future session (recency drops, sales stall) the item
    naturally falls back to reel_review / large_pack_review on re-evaluation.
    """
    if rule and rule.get("policy_locked"):
        return False

    recency_confidence = item.get("recency_confidence", "")
    if recency_confidence != "high":
        return False

    sales_health = item.get("sales_health_signal", "")
    if sales_health == "active":
        return True

    if item.get("has_recent_local_order"):
        return True

    return False


def determine_order_policy(item, inv, pack_qty, rule):
    """
    Determine the ordering policy for an item.
    Returns: 'standard', 'pack_trigger', 'soft_pack', 'exact_qty',
             'reel_review', 'reel_auto', 'large_pack_review', or 'manual_only'
    """
    if has_exact_qty_override(rule):
        return "exact_qty"

    if rule and rule.get("order_policy"):
        return rule["order_policy"]

    if not pack_qty:
        return "exact_qty"

    mx = inv.get("max") if inv else None
    package_profile = classify_package_profile(item, inv, pack_qty)

    if (
        mx
        and mx > 0
        and pack_qty >= REEL_REVIEW_MIN_PACK_QTY
        and pack_qty > mx * PACK_MAX_RATIO_FOR_LARGE_PACK
        and package_profile == "reel_stock"
    ):
        if _qualifies_for_review_policy_graduation(item, inv, pack_qty, rule):
            item["policy_graduated_from"] = "reel_review"
            return "reel_auto"
        return "reel_review"

    if package_profile in ("hardware_large_pack", "large_nonreel_pack"):
        if _qualifies_for_review_policy_graduation(item, inv, pack_qty, rule):
            item["policy_graduated_from"] = "large_pack_review"
            return "pack_trigger"
        return "large_pack_review"

    if (
        package_profile == "hardware_pack"
        and mx
        and mx > 0
        and pack_qty
        and pack_qty >= LARGE_PACK_REVIEW_MIN_PACK_QTY
        and pack_qty > mx * PACK_MAX_RATIO_FOR_LARGE_PACK
    ):
        return "pack_trigger"

    if has_pack_trigger_fields(rule) or has_pack_trigger_fields(item):
        return "pack_trigger"

    if rule and rule.get("allow_below_pack"):
        return "soft_pack"

    return "standard"


def calculate_suggested_qty(raw_need, pack_qty, policy, rule, inv):
    """
    Calculate a suggested order quantity based on policy and pack.
    Returns (suggested_qty, why_explanation)
    """
    if raw_need <= 0:
        return 0, "Inventory position already covers target"

    if policy == "exact_qty":
        return raw_need, "Exact qty (no pack data)"

    if policy == "manual_only":
        return raw_need, "Manual review required"

    if policy == "reel_review":
        mx = inv.get("max") if inv else None
        if mx and raw_need <= mx:
            return raw_need, f"Reel review: pack={pack_qty}, suggesting raw need (max={mx})"
        return raw_need, f"Reel review: pack={pack_qty}, needs manual decision"

    if policy == "large_pack_review":
        mx = inv.get("max") if inv else None
        if mx and raw_need <= mx:
            return raw_need, f"Large-pack review: pack={pack_qty}, suggesting raw need (max={mx})"
        return raw_need, f"Large-pack review: pack={pack_qty}, needs manual decision"

    if policy == "soft_pack":
        min_qty = 1
        if rule and rule.get("min_order_qty"):
            min_qty = rule["min_order_qty"]
        suggested = max(raw_need, min_qty)
        if min_qty > 1:
            suggested = math.ceil(suggested / min_qty) * min_qty
        return suggested, f"Soft pack: min order {min_qty}"

    if policy == "reel_auto":
        if pack_qty and pack_qty > 0:
            rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
            return rounded, f"Reel auto: graduated to auto-order, rounded to replenishment unit {pack_qty}"
        return raw_need, "Reel auto: graduated to auto-order"

    if policy == "pack_trigger":
        if pack_qty and pack_qty > 0:
            rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
            return rounded, f"Pack trigger: rounded to replenishment unit {pack_qty}"
        return raw_need, "Pack trigger (no pack data)"

    if pack_qty and pack_qty > 0:
        rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
        return rounded, f"Rounded up to pack of {pack_qty}"

    return raw_need, "Standard (no pack)"


# --- Extracted sub-modules override local definitions ---
from rules._constants import *  # noqa: E402, F811, F403
from rules._helpers import (  # noqa: E402, F811
    has_exact_qty_override,
    get_rule_int,
    get_rule_float,
    apply_rule_fields,
    has_pack_trigger_fields,
    get_rule_pack_size,
)
from rules.status import evaluate_item_status  # noqa: E402, F811
from rules.calc import (  # noqa: E402, F811
    calculate_inventory_position,
    determine_target_stock,
    determine_reorder_trigger_threshold,
    evaluate_reorder_trigger,
    calculate_raw_need,
    determine_acceptable_overstock_qty,
    assess_post_receipt_overstock,
    calculate_suggested_qty,
    compute_stockout_risk_score,
)
from rules.policy import (  # noqa: E402, F811
    looks_like_reel_item,
    looks_like_hardware_pack_item,
    should_large_pack_review,
    classify_package_profile,
    classify_replenishment_unit_mode,
    classify_recency_confidence,
    classify_low_confidence_recency,
    classify_dead_stock,
    should_force_recency_review,
    should_suppress_manual_only_qty,
    determine_order_policy,
    _qualifies_for_review_policy_graduation,
    _confirmed_stocking_is_valid,
    package_profile_label,
    replenishment_unit_mode_label,
    recency_review_bucket_label,
)
from rules.explanation import build_reason_codes, build_detail_parts  # noqa: E402


def _apply_confirmed_stocking(item, inv, rule):
    """
    Stamp confirmed_stocking fields onto the item from the rule and advance the
    sessions-without-evidence counter if applicable.

    If the operator has set confirmed_stocking = True in the rule:
    - item["confirmed_stocking"] = True
    - item["confirmed_stocking_sessions_without_evidence"] = current counter value
    - item["confirmed_stocking_expired"] = True if the counter has hit the threshold

    When new evidence is present (last_sale and last_receipt both exist), the
    counter is reset to 0 on the item so that persistent_state_flow can write it
    back to order_rules.json.  When evidence is absent, the counter is incremented.
    The rule dict is also mutated in place so callers can detect the change.
    """
    if not (rule and rule.get("confirmed_stocking")):
        item["confirmed_stocking"] = False
        return

    sessions_without = rule.get("confirmed_stocking_sessions_without_evidence", 0) or 0
    expired = sessions_without >= CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE
    item["confirmed_stocking"] = True
    item["confirmed_stocking_expired"] = expired

    # Same Min/Max-only blind spot as classify_recency_confidence: items
    # missing from On Hand Min Max Sales never have inv["last_sale"] /
    # inv["last_receipt"], so the confirmed-stocking evidence counter
    # would tick up every session and eventually expire them even when
    # the loaded files show real activity.  Fall back to per-item dates.
    has_new_evidence = (
        (bool(inv.get("last_sale")) or bool(item.get("last_sale_date")))
        and (bool(inv.get("last_receipt")) or bool(item.get("last_receipt_date")))
    )
    if has_new_evidence:
        new_count = 0
    else:
        new_count = sessions_without + 1 if not expired else sessions_without

    item["confirmed_stocking_sessions_without_evidence"] = new_count
    # Propagate back to rule so callers know the counter changed.
    rule["confirmed_stocking_sessions_without_evidence"] = new_count


def _manual_only_suppression_reason(item):
    """Return the why-explanation when a manual_only item's qty is suppressed to 0."""
    recency_bucket = item.get("recency_review_bucket")
    completeness = item.get("data_completeness", "")
    return {
        "stale_or_likely_dead": "Manual review required before ordering (missing sale/receipt history; likely stale or dead item)",
        "new_or_sparse": "Manual review required before ordering (missing sale/receipt history; may be new or too sparse)",
        "receipt_heavy_unverified": "Manual review required before ordering (receipts outpace sales; receiving history may reflect overstock rather than demand)",
        "missing_data_uncertain": "Manual review required before ordering (missing sale/receipt history; incomplete data makes demand uncertain)",
        "critical_min_rule_protected": "Manual review required before ordering (missing sale/receipt history; protected by explicit critical min rule)",
        "recent_local_po_protected": "Manual review required before ordering (missing sale/receipt history; protected by recent local PO history)",
        "activity_protected": "Manual review required before ordering (missing sale/receipt history; protected by other evidence)",
    }.get(recency_bucket, {
        "missing_recency": "Manual review required before ordering (missing sale/receipt history)",
        "missing_recency_critical_min_protected": "Manual review required before ordering (missing sale/receipt history; protected by explicit critical min rule)",
        "missing_recency_local_po_protected": "Manual review required before ordering (missing sale/receipt history; protected by recent local PO history)",
        "missing_recency_activity_protected": "Manual review required before ordering (missing sale/receipt history; protected by other evidence)",
        "missing_recency_receipt_heavy": "Manual review required before ordering (receipts outpace sales; receiving history may reflect overstock rather than demand)",
    }.get(completeness, "Manual review required before ordering"))


def _apply_history_gap_detection(item, suggested, policy, reason_codes):
    """Flag when the current suggestion deviates materially from historical order quantities."""
    if policy in ("reel_review", "large_pack_review", "manual_only"):
        item["suggestion_vs_history_gap"] = False
        return

    historical_order_qty = item.get("historical_order_qty")
    if (
        isinstance(historical_order_qty, (int, float))
        and historical_order_qty > 0
        and isinstance(suggested, (int, float))
        and suggested > 0
    ):
        ratio = abs(suggested - historical_order_qty) / float(historical_order_qty)
        if ratio > SUGGESTION_VS_HISTORY_GAP_THRESHOLD:
            item["suggestion_vs_history_gap"] = True
            item["review_required"] = True
            if "suggestion_vs_history_gap" not in reason_codes:
                reason_codes.append("suggestion_vs_history_gap")
            item["reason_codes"] = reason_codes
            detail = f"History gap: current suggestion {suggested:g} deviates from historical median {historical_order_qty:g}"
            item["why"] = item["why"] + f" | {detail}" if item.get("why") else detail
        return

    # Secondary fallback: recent local PO history
    local_qty = item.get("recent_local_order_qty") or 0
    local_count = item.get("recent_local_order_count") or 0
    if local_count > 0 and local_qty > 0:
        per_order_avg = local_qty / local_count
        suggestion = item.get("suggested_qty") or suggested or 0
        if per_order_avg > 0 and suggestion > 0:
            ratio = abs(suggestion - per_order_avg) / per_order_avg
            if ratio > SUGGESTION_VS_HISTORY_GAP_THRESHOLD:
                item["suggestion_vs_history_gap"] = True
                item["review_required"] = True
                if "suggestion_vs_history_gap" not in reason_codes:
                    reason_codes.append("suggestion_vs_history_gap")
                item["reason_codes"] = reason_codes
                gap_pct = int(ratio * 100)
                direction = "above" if suggestion > per_order_avg else "below"
                local_note = (
                    f"Local PO history gap: suggestion {gap_pct}% {direction} "
                    f"recent local avg ({int(per_order_avg)})"
                )
                item["why"] = item["why"] + f" | {local_note}" if item.get("why") else local_note
                if item.get("item_status") not in ("review", "warning"):
                    item["item_status"] = "review"
                return
    item["suggestion_vs_history_gap"] = False


def enrich_item(item, inv, pack_qty, rule, lead_time_days=None):
    """
    Orchestrate the full enrichment pipeline for a single item.
    Mutates the item dict in place with calculated fields.
    """
    item["inventory"] = inv or {}
    item["exact_qty_override"] = has_exact_qty_override(rule)
    item["package_profile"] = classify_package_profile(item, inv or {}, pack_qty)
    apply_rule_fields(item, rule)
    # Classify recency confidence first so compute_heuristic_confidence can use it.
    classify_recency_confidence(item, inv or {}, rule)
    classify_low_confidence_recency(item, inv or {}, rule)
    item["heuristic_confidence"] = compute_heuristic_confidence(item)
    if item.get("minimum_packs_on_hand") is None:
        inferred_min_packs = infer_minimum_packs_on_hand(item, inv or {}, pack_qty)
        if inferred_min_packs is not None:
            item["minimum_packs_on_hand"] = inferred_min_packs
            item["minimum_packs_on_hand_source"] = "heuristic"
    if item.get("minimum_cover_cycles") is None:
        inferred_cover_cycles = infer_minimum_cover_cycles(item, inv or {}, pack_qty)
        if inferred_cover_cycles is not None:
            item["minimum_cover_cycles"] = inferred_cover_cycles
            item["minimum_cover_cycles_source"] = "heuristic"
    _apply_confirmed_stocking(item, inv or {}, rule)
    calculate_inventory_position(item)
    determine_target_stock(item)
    item["stockout_risk_score"] = compute_stockout_risk_score(item, lead_time_days=lead_time_days)
    item["dead_stock"] = classify_dead_stock(item)
    item["reorder_needed"] = evaluate_reorder_trigger(item)
    raw_need = calculate_raw_need(item)
    item["raw_need"] = raw_need
    acceptable_overstock = determine_acceptable_overstock_qty(item)

    policy = determine_order_policy(item, inv, pack_qty, rule)
    if policy not in ("manual_only", "reel_review", "large_pack_review") and should_force_recency_review(item, inv, rule):
        policy = "manual_only"
    suggested, why = calculate_suggested_qty(raw_need, pack_qty, policy, rule, inv)
    projected_overstock, overstock_within_tolerance = assess_post_receipt_overstock(item, suggested)
    auto_order_projected_overstock = projected_overstock
    auto_order_overstock_within_tolerance = overstock_within_tolerance
    overstock_exceeded_for_auto_order = (
        acceptable_overstock > 0 and projected_overstock > acceptable_overstock
    )
    if (
        policy not in ("manual_only", "reel_review", "large_pack_review")
        and overstock_exceeded_for_auto_order
    ):
        policy = "manual_only"
        suggested, why = calculate_suggested_qty(raw_need, pack_qty, policy, rule, inv)
        projected_overstock, overstock_within_tolerance = assess_post_receipt_overstock(item, suggested)
    item["order_policy"] = policy
    if should_suppress_manual_only_qty(item):
        suggested = 0
        why = _manual_only_suppression_reason(item)
        projected_overstock, overstock_within_tolerance = assess_post_receipt_overstock(item, suggested)
    replenishment_unit_mode = classify_replenishment_unit_mode(policy, item, pack_qty, rule)
    item["replenishment_unit_mode"] = replenishment_unit_mode
    reason_codes, receipt_pack_mismatch = build_reason_codes(
        item,
        raw_need=raw_need,
        pack_qty=pack_qty,
        policy=policy,
        suggested=suggested,
        acceptable_overstock=acceptable_overstock,
        overstock_exceeded_for_auto_order=overstock_exceeded_for_auto_order,
    )
    item["receipt_pack_mismatch"] = receipt_pack_mismatch
    if receipt_pack_mismatch:
        if str(item.get("reorder_attention_signal", "") or "").strip().lower() in ("", "normal"):
            item["reorder_attention_signal"] = "review_receipt_pack_mismatch"
    detail_parts = build_detail_parts(
        item,
        why=why,
        pack_qty=pack_qty,
        policy=policy,
        acceptable_overstock=acceptable_overstock,
        projected_overstock=projected_overstock,
        overstock_within_tolerance=overstock_within_tolerance,
        overstock_exceeded_for_auto_order=overstock_exceeded_for_auto_order,
        auto_order_projected_overstock=auto_order_projected_overstock,
        auto_order_overstock_within_tolerance=auto_order_overstock_within_tolerance,
        receipt_pack_mismatch=receipt_pack_mismatch,
    )
    item["suggested_qty"] = suggested
    item["core_why"] = " | ".join(detail_parts)
    item["why"] = item["core_why"]
    item["reason_codes"] = reason_codes

    if not item.get("manual_override"):
        item["final_qty"] = suggested
    if "final_qty" not in item:
        item["final_qty"] = suggested

    item["review_required"] = policy in ("reel_review", "large_pack_review", "manual_only")
    if "review_resolved" not in item:
        item["review_resolved"] = False
    if "manual_override" not in item:
        item["manual_override"] = False

    _apply_history_gap_detection(item, suggested, policy, reason_codes)

    status, flags = evaluate_item_status(item)
    for code in reason_codes:
        if code not in flags:
            flags.append(code)
    item["status"] = status
    item["data_flags"] = flags
    item["order_qty"] = item["final_qty"]


def infer_default_order_policy(item, inv, pack_qty, *, allow_below_pack=False):
    """Return the policy implied by the current data when no explicit policy override exists."""
    inferred_rule = {"allow_below_pack": True} if allow_below_pack else None
    return determine_order_policy(item, inv, pack_qty, inferred_rule)


def get_buy_rule_summary(item, rule):
    """Build a compact summary string for the buy rule column."""
    parts = []
    policy = item.get("order_policy", "")
    pack = item.get("pack_size")

    if policy == "standard" and pack:
        parts.append(f"Pk:{pack}")
    elif policy == "pack_trigger":
        parts.append(f"TrigPk:{pack}" if pack else "TrigPk")
    elif policy == "soft_pack":
        min_q = rule.get("min_order_qty", 1) if rule else 1
        parts.append(f"Soft:{min_q}")
    elif policy == "exact_qty":
        parts.append("Exact")
    elif policy == "reel_review":
        parts.append(f"Reel:{pack}")
    elif policy == "large_pack_review":
        parts.append(f"LgPk:{pack}" if pack else "LgPk")
    elif policy == "manual_only":
        parts.append("Manual")
    elif pack:
        parts.append(f"Pk:{pack}")

    if rule and rule.get("allow_below_pack"):
        parts.append("vOK")

    trigger_qty = get_rule_int(rule, "reorder_trigger_qty")
    if trigger_qty is not None:
        parts.append(f"Trg:{trigger_qty:g}")

    trigger_pct = get_rule_float(rule, "reorder_trigger_pct")
    if trigger_pct is not None:
        parts.append(f"Trg:{trigger_pct:g}%")

    minimum_packs = get_rule_int(rule, "minimum_packs_on_hand")
    if minimum_packs is not None:
        parts.append(f"MinPk:{minimum_packs:g}")

    minimum_cover_days = get_rule_float(rule, "minimum_cover_days")
    if minimum_cover_days is not None:
        parts.append(f"CvrD:{minimum_cover_days:g}")

    minimum_cover_cycles = get_rule_float(rule, "minimum_cover_cycles")
    if minimum_cover_cycles is not None:
        parts.append(f"CvrC:{minimum_cover_cycles:g}")

    return " ".join(parts) if parts else "-"
