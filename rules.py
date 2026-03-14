import math

REEL_REVIEW_MIN_PACK_QTY = 250
LARGE_PACK_REVIEW_MIN_PACK_QTY = 25
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


def should_large_pack_review(item, inv, pack_qty):
    """Return True when a non-reel item's pack looks risky enough for manual review."""
    mx = inv.get("max") if inv else None
    if not (mx and mx > 0 and pack_qty and pack_qty > 0):
        return False
    if pack_qty < LARGE_PACK_REVIEW_MIN_PACK_QTY:
        return False
    if pack_qty <= mx * 3:
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
        return int(float(value))
    except (TypeError, ValueError):
        return None


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
        )
    )


def infer_minimum_packs_on_hand(item, inv, pack_qty):
    """Infer a conservative two-pack floor for active hardware with extreme pack/max mismatch."""
    mx = inv.get("max") if inv else None
    if not (mx and mx > 0 and pack_qty and pack_qty >= LARGE_PACK_REVIEW_MIN_PACK_QTY):
        return None
    if not looks_like_hardware_pack_item(item, inv or {}):
        return None
    if should_large_pack_review(item, inv or {}, pack_qty):
        return None
    if pack_qty <= mx * 3:
        return None

    sales_health = item.get("sales_health_signal", "")
    performance = item.get("performance_profile", "")
    days_since_last_sale = item.get("days_since_last_sale")

    if sales_health not in ("active", "stable", ""):
        return None
    if performance not in ("steady", "top_performer", "intermittent", ""):
        return None
    if isinstance(days_since_last_sale, (int, float)) and days_since_last_sale > 120:
        return None
    return 2


def classify_recency_confidence(item, inv, rule):
    """Classify how trustworthy the item's sale/receipt recency evidence is."""
    has_last_sale = bool((inv or {}).get("last_sale"))
    has_last_receipt = bool((inv or {}).get("last_receipt"))
    has_recent_suspense = bool(item.get("effective_qty_suspended", item.get("qty_suspended", 0)))
    has_open_po = bool(item.get("qty_on_po", 0))
    has_protective_rule = bool(
        has_pack_trigger_fields(rule)
        or (rule and rule.get("order_policy"))
        or isinstance((inv or {}).get("min"), (int, float)) and (inv or {}).get("min") > 0
    )

    if has_last_sale and has_last_receipt:
        item["recency_confidence"] = "high"
        item["data_completeness"] = "complete"
    elif has_last_sale or has_last_receipt:
        item["recency_confidence"] = "medium"
        item["data_completeness"] = "partial_recency"
    elif has_recent_suspense or has_open_po:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency_activity_protected"
    elif has_protective_rule:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency_rule_protected"
    else:
        item["recency_confidence"] = "low"
        item["data_completeness"] = "missing_recency"
    return item["recency_confidence"]


def should_force_recency_review(item, inv, rule):
    """Return True when a reorder candidate lacks enough recency evidence for auto-order."""
    recency_confidence = item.get("recency_confidence") or classify_recency_confidence(item, inv, rule)
    if recency_confidence != "low":
        return False

    data_completeness = item.get("data_completeness", "")
    raw_need = item.get("raw_need", 0)
    demand_signal = item.get("demand_signal", 0)
    pack_size = item.get("pack_size", 0)

    if raw_need <= 0:
        return False
    if data_completeness == "missing_recency_rule_protected":
        return False
    if data_completeness == "missing_recency_activity_protected":
        return True
    if demand_signal > 0:
        return True
    if isinstance(pack_size, (int, float)) and pack_size > 1:
        return True
    return False


def determine_reorder_trigger_threshold(item):
    """Compute an explicit reorder trigger threshold when rule fields define one."""
    inv = item.get("inventory", {}) or {}
    current_min = inv.get("min")
    pack_size = item.get("pack_size")
    trigger_qty = item.get("reorder_trigger_qty")
    trigger_pct = item.get("reorder_trigger_pct")
    minimum_packs_on_hand = item.get("minimum_packs_on_hand")

    has_explicit_trigger = (
        isinstance(trigger_qty, (int, float)) and trigger_qty > 0
    ) or (
        isinstance(trigger_pct, (int, float)) and trigger_pct > 0
    ) or (
        isinstance(minimum_packs_on_hand, (int, float)) and minimum_packs_on_hand > 0
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
    effective_target_stock = item.get("effective_target_stock", item.get("target_stock", 0)) or 0
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

    item["target_stock"] = target_stock if target_stock else 0
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
        return 0
    target_stock = item.get("target_stock", 0)
    trigger_threshold = item.get("reorder_trigger_threshold")
    effective_target_stock = target_stock
    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > effective_target_stock:
        effective_target_stock = trigger_threshold
    item["effective_target_stock"] = effective_target_stock
    return max(0, int(math.ceil(effective_target_stock - inventory_position)))


def determine_order_policy(item, inv, pack_qty, rule):
    """
    Determine the ordering policy for an item.
    Returns: 'standard', 'pack_trigger', 'soft_pack', 'exact_qty', 'reel_review', 'large_pack_review', or 'manual_only'
    """
    if rule and rule.get("order_policy"):
        return rule["order_policy"]

    if not pack_qty:
        return "exact_qty"

    mx = inv.get("max") if inv else None

    if (
        mx
        and mx > 0
        and pack_qty >= REEL_REVIEW_MIN_PACK_QTY
        and pack_qty > mx * 3
        and looks_like_reel_item(item, inv or {})
    ):
        return "reel_review"

    if should_large_pack_review(item, inv or {}, pack_qty):
        return "large_pack_review"

    if (
        looks_like_hardware_pack_item(item, inv or {})
        and mx
        and mx > 0
        and pack_qty
        and pack_qty >= LARGE_PACK_REVIEW_MIN_PACK_QTY
        and pack_qty > mx * 3
    ):
        return "pack_trigger"

    if has_pack_trigger_fields(rule):
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

    if policy == "pack_trigger":
        if pack_qty and pack_qty > 0:
            rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
            return rounded, f"Pack trigger: rounded to replenishment unit {pack_qty}"
        return raw_need, "Pack trigger (no pack data)"

    if pack_qty and pack_qty > 0:
        rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
        return rounded, f"Rounded up to pack of {pack_qty}"

    return raw_need, "Standard (no pack)"


def evaluate_item_status(item):
    """
    Evaluate the status of an item and set data_flags.
    Returns (status, data_flags) where status is 'ok', 'review', 'warning', 'error'
    """
    flags = []
    status = "ok"

    if not item.get("pack_size"):
        flags.append("missing_pack")

    if item.get("order_policy") == "reel_review":
        flags.append("reel_review")
        status = "review"

    if item.get("order_policy") == "large_pack_review":
        flags.append("large_pack_review")
        status = "review"

    if item.get("order_policy") == "manual_only":
        flags.append("manual_only")
        status = "review"

    final = item.get("final_qty", 0)
    raw = item.get("raw_need", 0)

    if final <= 0 and raw > 0:
        status = "warning"
        flags.append("zero_final")

    if final <= 0 and raw <= 0:
        status = "skip"

    if item.get("review_required") and not item.get("review_resolved"):
        status = "review"

    return status, flags


def enrich_item(item, inv, pack_qty, rule):
    """
    Orchestrate the full enrichment pipeline for a single item.
    Mutates the item dict in place with calculated fields.
    """
    item["inventory"] = inv or {}
    apply_rule_fields(item, rule)
    if item.get("minimum_packs_on_hand") is None:
        inferred_min_packs = infer_minimum_packs_on_hand(item, inv or {}, pack_qty)
        if inferred_min_packs is not None:
            item["minimum_packs_on_hand"] = inferred_min_packs
            item["minimum_packs_on_hand_source"] = "heuristic"
    classify_recency_confidence(item, inv or {}, rule)
    calculate_inventory_position(item)
    determine_target_stock(item)
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
    reason_codes = []
    inventory_position = item.get("inventory_position", 0)
    target_stock = item.get("target_stock", 0)
    effective_target_stock = item.get("effective_target_stock", target_stock)
    if raw_need <= 0:
        reason_codes.append("inventory_covers_target")
    else:
        reason_codes.append("below_target_stock")
    target_basis = item.get("target_basis", "")
    if target_basis:
        reason_codes.append(f"target_{target_basis}")
    trigger_basis = item.get("reorder_trigger_basis", "")
    trigger_threshold = item.get("reorder_trigger_threshold")
    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > 0:
        reason_codes.append(f"trigger_{trigger_basis or 'configured'}")
    if item.get("effective_qty_suspended", 0):
        reason_codes.append("suspense_included")
    if item.get("suspense_carry_qty", 0):
        reason_codes.append("suspense_carry_applied")
    if pack_qty and policy == "standard" and suggested > raw_need:
        reason_codes.append("pack_round_up")
    if policy == "soft_pack":
        reason_codes.append("soft_pack_rule")
    if policy == "pack_trigger":
        reason_codes.append("pack_trigger")
    if policy == "reel_review":
        reason_codes.append("reel_review")
    if policy == "large_pack_review":
        reason_codes.append("large_pack_review")
    if policy == "manual_only":
        reason_codes.append("manual_only")
    if item.get("recency_confidence") == "low":
        reason_codes.append("low_recency_confidence")
    data_completeness = item.get("data_completeness", "")
    if data_completeness:
        reason_codes.append(f"data_{data_completeness}")
    if acceptable_overstock > 0:
        reason_codes.append("acceptable_overstock_configured")
        if overstock_exceeded_for_auto_order:
            reason_codes.append("acceptable_overstock_exceeded")

    detail_parts = [f"Stock after open POs: {inventory_position:g}", f"Target stock: {target_stock:g}"]
    if effective_target_stock != target_stock:
        detail_parts.append(f"Effective reorder floor: {effective_target_stock:g}")
    if target_basis:
        basis_labels = {
            "current_max": "Based on current max",
            "suggested_max": "Based on suggested max",
            "current_min": "Based on current min",
            "suggested_min": "Based on suggested min",
            "demand_fallback": "Based on demand signal",
            "none": "No target basis available",
        }
        detail_parts.append(basis_labels.get(target_basis, f"Based on {target_basis}"))
    if item.get("effective_qty_suspended", 0):
        detail_parts.append(f"Suspended demand included: {item.get('effective_qty_suspended', 0):g}")
    if item.get("qty_on_po", 0):
        detail_parts.append(f"Already on PO: {item.get('qty_on_po', 0):g}")
    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > 0:
        detail_parts.append(f"Reorder trigger: {trigger_threshold:g}")
    recency_confidence = item.get("recency_confidence")
    if recency_confidence:
        detail_parts.append(f"Recency confidence: {recency_confidence}")
    if data_completeness:
        completeness_labels = {
            "complete": "Sale and receipt history present",
            "partial_recency": "Only one recency signal present",
            "missing_recency": "No sale or receipt history available",
            "missing_recency_rule_protected": "No sale or receipt history, but protected by an explicit stocking rule",
            "missing_recency_activity_protected": "No sale or receipt history, but protected by other evidence",
        }
        detail_parts.append(completeness_labels.get(data_completeness, data_completeness))
    if acceptable_overstock > 0:
        overstock_basis = item.get("acceptable_overstock_basis")
        basis_label = {
            "qty": "saved qty",
            "pct": "percent of pack",
        }.get(overstock_basis, "configured")
        detail_parts.append(f"Acceptable overstock: {acceptable_overstock:g} ({basis_label})")
        detail_parts.append(
            f"Projected overstock after receipt: {projected_overstock:g} "
            f"({'within tolerance' if overstock_within_tolerance else 'exceeds tolerance'})"
        )
        if overstock_exceeded_for_auto_order:
            detail_parts.append(
                f"Auto-order projection: {auto_order_projected_overstock:g} "
                f"({'within tolerance' if auto_order_overstock_within_tolerance else 'exceeds tolerance'})"
            )
            detail_parts.append("Auto-order blocked because projected overstock exceeds configured tolerance")
    minimum_packs = item.get("minimum_packs_on_hand")
    minimum_packs_source = item.get("minimum_packs_on_hand_source")
    if isinstance(minimum_packs, (int, float)) and minimum_packs > 0:
        source_label = {
            "heuristic": "inferred",
            "rule": "saved rule",
        }.get(minimum_packs_source, "configured")
        detail_parts.append(f"Minimum packs on hand: {minimum_packs:g} ({source_label})")
    detail_parts.append(why)
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
    else:
        if pack:
            parts.append(f"Pk:{pack}")

    if rule and rule.get("allow_below_pack"):
        parts.append("↓OK")

    trigger_qty = get_rule_int(rule, "reorder_trigger_qty")
    if trigger_qty is not None:
        parts.append(f"Trg:{trigger_qty:g}")

    trigger_pct = get_rule_float(rule, "reorder_trigger_pct")
    if trigger_pct is not None:
        parts.append(f"Trg:{trigger_pct:g}%")

    minimum_packs = get_rule_int(rule, "minimum_packs_on_hand")
    if minimum_packs is not None:
        parts.append(f"MinPk:{minimum_packs:g}")

    return " ".join(parts) if parts else "—"
