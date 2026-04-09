"""Policy determination, classification, and escalation logic.

Functions here decide which ordering policy applies to an item
(standard, pack_trigger, soft_pack, reel_review, manual_only, etc.),
classify package profiles, recency confidence, dead stock, and
determine when items need manual review escalation.
"""

from rules._constants import (
    REEL_REVIEW_MIN_PACK_QTY,
    LARGE_PACK_REVIEW_MIN_PACK_QTY,
    PACK_MAX_RATIO_FOR_LARGE_PACK,
    CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE,
    DEAD_STOCK_MIN_DAYS_SINCE_SALE,
    REEL_STRONG_PHRASES,
    REEL_BASE_TERMS,
    REEL_LENGTH_TERMS,
    REEL_BLOCKLIST,
    HARDWARE_PACK_TERMS,
)
from rules._helpers import get_rule_int, get_rule_float, has_exact_qty_override, has_pack_trigger_fields


# ── Description pattern matchers ─────────────────────────────────────

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


# ── Label helpers ────────────────────────────────────────────────────

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


def replenishment_unit_mode_label(mode):
    return {
        "exact_qty": "Exact qty",
        "soft_pack_min_order": "Soft pack / min order",
        "pack_trigger_replenishment": "Pack-trigger replenishment",
        "reel_bulk_review": "Reel / bulk review",
        "large_pack_review": "Large-pack review",
        "full_pack_round_up": "Full-pack round-up",
    }.get(mode, mode or "")


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


# ── Package and replenishment classification ─────────────────────────

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


# ── Recency confidence ──────────���────────────────────────────────────

def classify_recency_confidence(item, inv, rule):
    """Classify how trustworthy the item's sale/receipt recency evidence is."""
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
    elif qty_received > 0 and sales_health in ("", "unknown") and historical_rank < 24:
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


def classify_dead_stock(item):
    """Return True when an item shows no sale or receipt movement and has no pending demand.

    Criteria (all must be met):
    - days_since_last_sale is known and >= DEAD_STOCK_MIN_DAYS_SINCE_SALE
    - no effective suspended demand (effective_qty_suspended or qty_suspended)
    - no open PO qty (qty_on_po)
    """
    days_since = item.get("days_since_last_sale")
    if not isinstance(days_since, (int, float)) or days_since < DEAD_STOCK_MIN_DAYS_SINCE_SALE:
        return False
    has_pending_suspense = bool(item.get("effective_qty_suspended") or item.get("qty_suspended", 0))
    has_open_po = bool(item.get("qty_on_po", 0))
    if has_pending_suspense or has_open_po:
        return False
    return True


# ── Policy escalation ────────────────────────────────────────────────

def _confirmed_stocking_is_valid(rule):
    """Return True when the rule carries a non-expired confirmed_stocking flag."""
    if not (rule and rule.get("confirmed_stocking")):
        return False
    sessions_without = rule.get("confirmed_stocking_sessions_without_evidence", 0) or 0
    return sessions_without < CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE


def should_force_recency_review(item, inv, rule):
    """Return True when a reorder candidate lacks enough recency evidence for auto-order."""
    recency_confidence = item.get("recency_confidence") or classify_recency_confidence(item, inv, rule)
    if recency_confidence != "low":
        return False
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


def _qualifies_for_review_policy_graduation(item, inv, pack_qty, rule):
    """Return True if a reel_review or large_pack_review item has enough evidence to auto-order."""
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
    """Determine the ordering policy for an item."""
    if has_exact_qty_override(rule):
        return "exact_qty"
    if rule and rule.get("order_policy"):
        return rule["order_policy"]
    if not pack_qty:
        return "exact_qty"
    mx = inv.get("max") if inv else None
    package_profile = classify_package_profile(item, inv, pack_qty)

    if (
        mx and mx > 0
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
        and mx and mx > 0
        and pack_qty and pack_qty >= LARGE_PACK_REVIEW_MIN_PACK_QTY
        and pack_qty > mx * PACK_MAX_RATIO_FOR_LARGE_PACK
    ):
        return "pack_trigger"

    if has_pack_trigger_fields(rule) or has_pack_trigger_fields(item):
        return "pack_trigger"

    if rule and rule.get("allow_below_pack"):
        return "soft_pack"

    return "standard"
