import math

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
from rules._heuristics import (  # noqa: E402
    compute_heuristic_confidence,
    infer_minimum_packs_on_hand,
    infer_minimum_cover_cycles,
)


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
    item["deferred_pack_overshoot"] = suggested == 0 and raw_need > 0 and why.startswith("Defer:")
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
