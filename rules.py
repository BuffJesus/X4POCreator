import math

REEL_REVIEW_MIN_PACK_QTY = 250
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


def calculate_raw_need(item):
    """Calculate the unconstrained order need from inventory position."""
    inv = item.get("inventory", {}) or {}
    qoh = inv.get("qoh", 0) or 0
    on_po = item.get("qty_on_po", 0) or 0
    inventory_position = qoh + on_po
    item["inventory_position"] = inventory_position

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

    if demand_signal <= 0:
        if isinstance(current_min, (int, float)) and inventory_position < current_min:
            target_stock = max(value for value in (target_stock, current_min) if isinstance(value, (int, float)))
        else:
            item["target_stock"] = target_stock if target_stock else 0
            return 0

    item["target_stock"] = target_stock
    return max(0, int(math.ceil(target_stock - inventory_position)))


def determine_order_policy(item, inv, pack_qty, rule):
    """
    Determine the ordering policy for an item.
    Returns: 'standard', 'soft_pack', 'exact_qty', 'reel_review', or 'manual_only'
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

    if policy == "soft_pack":
        min_qty = 1
        if rule and rule.get("min_order_qty"):
            min_qty = rule["min_order_qty"]
        suggested = max(raw_need, min_qty)
        if min_qty > 1:
            suggested = math.ceil(suggested / min_qty) * min_qty
        return suggested, f"Soft pack: min order {min_qty}"

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
    raw_need = calculate_raw_need(item)
    item["raw_need"] = raw_need

    policy = determine_order_policy(item, inv, pack_qty, rule)
    item["order_policy"] = policy

    suggested, why = calculate_suggested_qty(raw_need, pack_qty, policy, rule, inv)
    reason_codes = []
    inventory_position = item.get("inventory_position", 0)
    target_stock = item.get("target_stock", 0)
    if raw_need <= 0:
        reason_codes.append("inventory_covers_target")
    else:
        reason_codes.append("below_target_stock")
    target_basis = item.get("target_basis", "")
    if target_basis:
        reason_codes.append(f"target_{target_basis}")
    if item.get("effective_qty_suspended", 0):
        reason_codes.append("suspense_included")
    if item.get("suspense_carry_qty", 0):
        reason_codes.append("suspense_carry_applied")
    if pack_qty and policy == "standard" and suggested > raw_need:
        reason_codes.append("pack_round_up")
    if policy == "soft_pack":
        reason_codes.append("soft_pack_rule")
    if policy == "reel_review":
        reason_codes.append("reel_review")
    if policy == "manual_only":
        reason_codes.append("manual_only")

    detail_parts = [f"Stock after open POs: {inventory_position:g}", f"Target stock: {target_stock:g}"]
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
    detail_parts.append(why)
    item["suggested_qty"] = suggested
    item["why"] = " | ".join(detail_parts)
    item["reason_codes"] = reason_codes

    if not item.get("manual_override"):
        item["final_qty"] = suggested
    if "final_qty" not in item:
        item["final_qty"] = suggested

    item["review_required"] = policy in ("reel_review", "manual_only")
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


def get_buy_rule_summary(item, rule):
    """Build a compact summary string for the buy rule column."""
    parts = []
    policy = item.get("order_policy", "")
    pack = item.get("pack_size")

    if policy == "standard" and pack:
        parts.append(f"Pk:{pack}")
    elif policy == "soft_pack":
        min_q = rule.get("min_order_qty", 1) if rule else 1
        parts.append(f"Soft:{min_q}")
    elif policy == "exact_qty":
        parts.append("Exact")
    elif policy == "reel_review":
        parts.append(f"Reel:{pack}")
    elif policy == "manual_only":
        parts.append("Manual")
    else:
        if pack:
            parts.append(f"Pk:{pack}")

    if rule and rule.get("allow_below_pack"):
        parts.append("↓OK")

    return " ".join(parts) if parts else "—"
