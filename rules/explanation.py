"""Build the human-readable explanation (``why``, ``reason_codes``,
``core_why``) from an enriched item's calculated fields.

Called by the ``enrich_item`` orchestrator after all calculation,
policy, and classification steps have stamped their results on the
item dict.  The functions here only *read* the item — they don't
mutate it (the caller stamps the returned values).
"""

import math

from rules._constants import CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE


def _label(mapping, key, default=None):
    return mapping.get(key, default if default is not None else (key or ""))


def build_reason_codes(item, *, raw_need, pack_qty, policy, suggested, acceptable_overstock,
                       overstock_exceeded_for_auto_order):
    """Return a list of reason code strings from the enriched item state."""
    reason_codes = []
    if raw_need <= 0:
        reason_codes.append("inventory_covers_target")
    else:
        reason_codes.append("below_target_stock")
    target_basis = item.get("target_basis", "")
    if target_basis:
        reason_codes.append(f"target_{target_basis}")
    if item.get("target_stock_hysteresis_applied"):
        reason_codes.append("target_hysteresis_applied")
    trigger_basis = item.get("reorder_trigger_basis", "")
    trigger_threshold = item.get("reorder_trigger_threshold")
    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > 0:
        reason_codes.append(f"trigger_{trigger_basis or 'configured'}")
    if item.get("reorder_trigger_high_vs_max"):
        reason_codes.append("trigger_high_vs_max")
    if item.get("zero_demand_min_protection"):
        reason_codes.append("zero_demand_min_protection")
    if item.get("stale_demand_below_threshold"):
        reason_codes.append("stale_demand_below_threshold")
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
    if policy == "reel_auto":
        reason_codes.append("reel_auto")
    if policy == "large_pack_review":
        reason_codes.append("large_pack_review")
    if item.get("policy_graduated_from"):
        reason_codes.append(f"graduated_from_{item['policy_graduated_from']}")
    if policy == "manual_only":
        reason_codes.append("manual_only")
    if item.get("package_profile"):
        reason_codes.append(f"package_{item['package_profile']}")
    replenishment_unit_mode = item.get("replenishment_unit_mode")
    if replenishment_unit_mode:
        reason_codes.append(f"unitmode_{replenishment_unit_mode}")
    if item.get("deferred_pack_overshoot"):
        reason_codes.append("deferred_pack_overshoot")
    if item.get("confirmed_stocking"):
        if item.get("confirmed_stocking_expired"):
            reason_codes.append("confirmed_stocking_expired")
        else:
            reason_codes.append("confirmed_stocking")
    if item.get("recency_confidence") == "low":
        reason_codes.append("low_recency_confidence")
    recency_review_bucket = item.get("recency_review_bucket")
    if recency_review_bucket:
        reason_codes.append(f"recency_{recency_review_bucket}")
    data_completeness = item.get("data_completeness", "")
    if data_completeness:
        reason_codes.append(f"data_{data_completeness}")
    if acceptable_overstock > 0:
        reason_codes.append("acceptable_overstock_configured")
        if overstock_exceeded_for_auto_order:
            reason_codes.append("acceptable_overstock_exceeded")
    receipt_vendor_confidence = item.get("receipt_vendor_confidence", "")
    if receipt_vendor_confidence and receipt_vendor_confidence != "none":
        reason_codes.append(f"receipt_vendor_{receipt_vendor_confidence}")
    if item.get("receipt_vendor_ambiguous"):
        reason_codes.append("receipt_vendor_ambiguous")
    receipt_sales_balance = str(item.get("receipt_sales_balance", "") or "").strip().lower()
    if receipt_sales_balance:
        reason_codes.append(f"receipt_sales_{receipt_sales_balance}")
    receipt_pack_confidence = str(item.get("potential_pack_confidence", "") or "").strip().lower()
    receipt_pack_candidate = item.get("potential_pack_size")
    active_pack_source = str(item.get("pack_size_source", "") or "").strip().lower()
    receipt_pack_mismatch = (
        receipt_pack_confidence == "high"
        and isinstance(receipt_pack_candidate, (int, float))
        and receipt_pack_candidate > 0
        and isinstance(pack_qty, (int, float))
        and pack_qty > 0
        and active_pack_source != "receipt_history"
        and not math.isclose(float(pack_qty), float(receipt_pack_candidate))
    )
    if receipt_pack_mismatch:
        reason_codes.append("receipt_pack_mismatch")
    return reason_codes, receipt_pack_mismatch


def build_detail_parts(item, *, why, pack_qty, policy, acceptable_overstock,
                       projected_overstock, overstock_within_tolerance,
                       overstock_exceeded_for_auto_order,
                       auto_order_projected_overstock, auto_order_overstock_within_tolerance,
                       receipt_pack_mismatch):
    """Return a list of detail strings that get joined into ``core_why``."""
    from rules.policy import (
        package_profile_label,
        replenishment_unit_mode_label,
        recency_review_bucket_label,
    )

    inventory_position = item.get("inventory_position", 0)
    target_stock = item.get("target_stock", 0)
    effective_order_floor = item.get("effective_order_floor", item.get("effective_target_stock", target_stock))
    trigger_threshold = item.get("reorder_trigger_threshold")
    target_basis = item.get("target_basis", "")
    data_completeness = item.get("data_completeness", "")
    recency_review_bucket = item.get("recency_review_bucket")
    receipt_sales_balance = str(item.get("receipt_sales_balance", "") or "").strip().lower()
    receipt_vendor_confidence = item.get("receipt_vendor_confidence", "")
    receipt_pack_candidate = item.get("potential_pack_size")

    detail_parts = [f"Stock after open POs: {inventory_position:g}", f"Target stock: {target_stock:g}"]

    if item.get("policy_graduated_from"):
        graduated_from = item["policy_graduated_from"]
        label = "Reel review" if graduated_from == "reel_review" else "Large-pack review"
        detail_parts.append(f"Policy graduated from {label}: strong recency and demand evidence supports auto-order")
    if item.get("package_profile"):
        detail_parts.append(f"Package profile: {package_profile_label(item['package_profile'])}")
    replenishment_unit_mode = item.get("replenishment_unit_mode")
    if replenishment_unit_mode:
        detail_parts.append(f"Replenishment mode: {replenishment_unit_mode_label(replenishment_unit_mode)}")
    if effective_order_floor != target_stock:
        detail_parts.append(f"Effective reorder floor: {effective_order_floor:g}")
    if target_basis:
        basis_labels = {
            "current_max": "Based on current max",
            "pack_adjusted_max": "Max adjusted up to pack size (system max too low for pack)",
            "suggested_max": "Based on suggested max",
            "current_min": "Based on current min",
            "suggested_min": "Based on suggested min",
            "demand_fallback": "Based on demand signal",
            "none": "No target basis available",
        }
        detail_parts.append(basis_labels.get(target_basis, f"Based on {target_basis}"))
    if item.get("target_stock_hysteresis_applied"):
        detail_parts.append("Target hysteresis: retained prior target to avoid small recommendation churn")
    if item.get("effective_qty_suspended", 0):
        detail_parts.append(f"Suspended demand included: {item.get('effective_qty_suspended', 0):g}")
    if item.get("qty_on_po", 0):
        detail_parts.append(f"Already on PO: {item.get('qty_on_po', 0):g}")
    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > 0:
        detail_parts.append(f"Reorder trigger: {trigger_threshold:g}")
    if item.get("reorder_trigger_high_vs_max"):
        detail_parts.append(f"Review: trigger threshold ({trigger_threshold:g}) is 5× or more above the stock target — verify rule settings are intentional")
    if item.get("zero_demand_min_protection"):
        detail_parts.append("Review: ordering to current min despite zero loaded demand — verify min is still appropriate")
    if item.get("confirmed_stocking"):
        sessions_without = item.get("confirmed_stocking_sessions_without_evidence", 0) or 0
        if item.get("confirmed_stocking_expired"):
            detail_parts.append(
                f"Confirmed stocking: expired after {CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE} sessions without evidence — reverted to review"
            )
        else:
            remaining = CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE - sessions_without
            if sessions_without > 0:
                detail_parts.append(
                    f"Confirmed stocking: operator-confirmed (auto-order bypassed recency review; {sessions_without} session(s) without new evidence, {remaining} remaining before expiry)"
                )
            else:
                detail_parts.append("Confirmed stocking: operator-confirmed (auto-order bypassed recency review; evidence current)")
    recency_confidence = item.get("recency_confidence")
    if recency_confidence:
        detail_parts.append(f"Recency confidence: {recency_confidence}")
    if data_completeness:
        completeness_labels = {
            "complete": "Sale and receipt history present",
            "partial_recency": "Only one recency signal present",
            "missing_recency": "No sale or receipt history available",
            "missing_recency_critical_min_protected": "No sale or receipt history, but protected by an explicit critical min rule",
            "missing_recency_local_po_protected": "No sale or receipt history, but recent local PO history exists",
            "missing_recency_rule_protected": "No sale or receipt history, but protected by an explicit stocking rule",
            "missing_recency_activity_protected": "No sale or receipt history, but protected by other evidence",
            "missing_recency_receipt_heavy": "No trustworthy recency history; receipts appear materially heavier than sales",
        }
        detail_parts.append(completeness_labels.get(data_completeness, data_completeness))
    if recency_review_bucket:
        detail_parts.append(f"Recency review type: {recency_review_bucket_label(recency_review_bucket)}")
    recent_local_order_count = item.get("recent_local_order_count", 0) or 0
    recent_local_order_qty = item.get("recent_local_order_qty", 0) or 0
    recent_local_order_date = item.get("recent_local_order_date", "")
    if recent_local_order_count > 0 and recent_local_order_qty > 0:
        recent_local_detail = (
            f"Recent local PO history: {recent_local_order_count:g} order(s), "
            f"{recent_local_order_qty:g} total"
        )
        if recent_local_order_date:
            recent_local_detail += f", latest {recent_local_order_date}"
        detail_parts.append(recent_local_detail)
    loaded_receipts = item.get("qty_received", 0) or 0
    if loaded_receipts > 0:
        detail_parts.append(f"Loaded receipts in selected window: {loaded_receipts:g}")
    receipt_sales_reason = str(item.get("receipt_sales_balance_reason", "") or "").strip()
    receipt_sales_balance_label = {
        "balanced": "balanced with sales",
        "receipt_led": "running ahead of sales",
        "receipt_only": "receipt-only evidence",
        "receipt_heavy": "receipt-heavy vs sales",
    }.get(receipt_sales_balance, receipt_sales_balance.replace("_", " "))
    if receipt_sales_balance:
        receipt_sales_detail = f"Receipt vs sales: {receipt_sales_balance_label}"
        if receipt_sales_reason:
            receipt_sales_detail += f" ({receipt_sales_reason})"
        detail_parts.append(receipt_sales_detail)
    receipt_primary_vendor = item.get("receipt_primary_vendor", "")
    if receipt_primary_vendor:
        receipt_vendor_detail = f"Receipt vendor evidence: {receipt_primary_vendor}"
        if receipt_vendor_confidence and receipt_vendor_confidence != "none":
            receipt_vendor_detail += f" ({receipt_vendor_confidence} confidence)"
        detail_parts.append(receipt_vendor_detail)
    if item.get("receipt_vendor_ambiguous"):
        receipt_candidates = list(item.get("receipt_vendor_candidates", []) or [])
        if receipt_candidates:
            detail_parts.append(f"Receipt vendor history is mixed: {', '.join(receipt_candidates[:3])}")
    if receipt_pack_mismatch:
        detail_parts.append(
            f"Receipt pack evidence suggests {receipt_pack_candidate:g}, "
            f"but active pack is {pack_qty:g}"
        )
    if acceptable_overstock > 0:
        overstock_basis = item.get("acceptable_overstock_basis")
        basis_label = {"qty": "saved qty", "pct": "percent of pack"}.get(overstock_basis, "configured")
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
        source_label = {"heuristic": "inferred", "rule": "saved rule"}.get(minimum_packs_source, "configured")
        detail_parts.append(f"Minimum packs on hand: {minimum_packs:g} ({source_label})")
    minimum_cover_cycles = item.get("minimum_cover_cycles")
    if isinstance(minimum_cover_cycles, (int, float)) and minimum_cover_cycles > 0:
        source_label = {"heuristic": "inferred", "rule": "saved rule"}.get(item.get("minimum_cover_cycles_source"), "configured")
        detail_parts.append(f"Minimum cover cycles: {minimum_cover_cycles:g} ({source_label})")
    minimum_cover_days = item.get("minimum_cover_days")
    if isinstance(minimum_cover_days, (int, float)) and minimum_cover_days > 0:
        source_label = {"heuristic": "inferred", "rule": "saved rule"}.get(item.get("minimum_cover_days_source"), "configured")
        detail_parts.append(f"Minimum cover days: {minimum_cover_days:g} ({source_label})")
    detail_parts.append(why)
    return detail_parts
