"""Pure calculation functions for ordering logic.

These functions compute inventory position, target stock, raw need,
suggested quantities, and overstock assessment.  They mutate the item
dict in place (persisting computed fields) but produce no explanation
strings — that responsibility stays in the orchestrator.
"""

import math

from rules._constants import MAX_CREDIBILITY_PACK_RATIO


def _max_is_credible(current_max, pack_qty):
    """Return True if current_max looks like an intentional operator setting
    rather than X4 auto-calculated noise.

    Heuristic: if a single pack is more than 3x the max, no operator
    would have set that max knowing the pack size.  X4's auto-calc
    formula doesn't consider pack sizes, so it routinely produces
    max=10 for bolts that come in packs of 100.
    """
    if not pack_qty or pack_qty <= 0:
        return True  # can't assess without pack info
    if not isinstance(current_max, (int, float)) or current_max <= 0:
        return True  # no max to question
    return pack_qty <= current_max * MAX_CREDIBILITY_PACK_RATIO


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

    # Operator-set current_max is authoritative when credible.
    # But X4 auto-calculates max without considering pack sizes,
    # producing nonsense like max=10 for bolts in packs of 100.
    # When pack >> max (ratio > 3x), treat max as auto-noise and
    # adjust target up to at least one full pack.
    pack_qty = item.get("pack_size") or 0
    if isinstance(current_max, (int, float)) and current_max > 0:
        if _max_is_credible(current_max, pack_qty):
            target_stock = current_max
            item["target_basis"] = "current_max"
        else:
            target_stock = max(current_max, pack_qty)
            item["target_basis"] = "pack_adjusted_max"
    elif isinstance(suggested_max, (int, float)) and suggested_max > 0:
        target_stock = suggested_max
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
            # Decay: if the computed target is lower than the held target,
            # move 25% of the way toward it each session.  This prevents
            # hysteresis from holding a stale high target indefinitely
            # when demand is gradually declining.
            if target_stock < previous_target_stock:
                decayed = previous_target_stock - (previous_target_stock - target_stock) * 0.25
                target_stock = max(target_stock, int(round(decayed)))
                hysteresis_applied = True
                item["target_stock_hysteresis_decayed"] = True
            else:
                target_stock = previous_target_stock
                hysteresis_applied = True

    item["target_stock"] = target_stock if target_stock else 0
    item["target_stock_hysteresis_applied"] = hysteresis_applied
    return item["target_stock"]


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

    # Sanity cap: flag (but don't override) when the trigger threshold
    # is extremely high relative to the stock target.  The operator set
    # these rules deliberately, so we warn rather than silently cap.
    inv = item.get("inventory", {}) or {}
    cap_ref = max((v for v in (inv.get("max"), inv.get("min"), item.get("target_stock")) if isinstance(v, (int, float)) and v > 0), default=0)
    if cap_ref > 0 and threshold > cap_ref * 5:
        item["reorder_trigger_high_vs_max"] = True
    item["reorder_trigger_threshold"] = threshold
    item["reorder_trigger_basis"] = basis
    return threshold


# Minimum annualized demand to justify auto-ordering.  Items below this
# threshold with no explicit trigger rules are routed to skip/review
# instead of generating orders.  Prevents 8-year-old single-sale items
# from producing purchase orders.
MIN_ANNUALIZED_DEMAND_FOR_AUTO_ORDER = 1.0


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
            item["zero_demand_min_protection"] = True
            return True
        return False

    # Stale demand check: if the annualized demand is below 1 unit/year
    # AND there's no explicit trigger rule, don't auto-order.  This
    # prevents items sold once in 8 years from generating POs.
    #
    # demand_signal is already normalized to per-cycle (e.g. per-week).
    # Annualize it: demand_signal * (365 / cycle_days).
    cycle_days = max(1, (item.get("reorder_cycle_weeks", 1) or 1) * 7)
    sales_span_days = item.get("sales_span_days") or 365
    if isinstance(sales_span_days, (int, float)) and sales_span_days > 90:
        annualized = demand_signal * (365.0 / cycle_days)
        if annualized < MIN_ANNUALIZED_DEMAND_FOR_AUTO_ORDER:
            has_explicit_trigger = (trigger_threshold is not None
                                    and isinstance(trigger_threshold, (int, float))
                                    and trigger_threshold > 0)
            if not has_explicit_trigger:
                item["stale_demand_below_threshold"] = True
                item["annualized_demand"] = round(annualized, 2)
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
    item["effective_target_stock"] = target_stock
    effective_order_floor = target_stock
    if isinstance(trigger_threshold, (int, float)) and trigger_threshold > effective_order_floor:
        effective_order_floor = trigger_threshold
    item["effective_order_floor"] = effective_order_floor
    return max(0, int(math.ceil(effective_order_floor - inventory_position)))


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


PACK_OVERSHOOT_DEFER_THRESHOLD = 0.50  # defer if QOH >= 50% of max


PACK_OVERSHOOT_TOLERANCE = 0.25  # allow overshoot up to 25% of pack


def _should_defer_pack_overshoot(raw_need, pack_qty, inv):
    """Return True if ordering a full pack would significantly overshoot
    max while current stock is already comfortable.

    Only defers when ALL of:
    - raw_need < pack_qty (order is purely pack-rounding waste)
    - pack_qty <= max (if pack > max, overshoot is inherent)
    - QOH >= 50% of max (stock is comfortable)
    - QOH + pack would exceed max by more than 25% of a pack
      (small overshoots near a pack multiple are acceptable)
    """
    if not inv or not pack_qty or pack_qty <= 0:
        return False
    if raw_need >= pack_qty:
        return False
    mx = inv.get("max")
    if not isinstance(mx, (int, float)) or mx <= 0:
        return False
    if pack_qty > mx:
        return False
    qoh = max(0, inv.get("qoh", 0) or 0)
    if qoh < mx * PACK_OVERSHOOT_DEFER_THRESHOLD:
        return False
    projected = qoh + pack_qty
    overshoot = projected - mx
    return overshoot > pack_qty * PACK_OVERSHOOT_TOLERANCE


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
            if _should_defer_pack_overshoot(raw_need, pack_qty, inv):
                qoh = max(0, (inv or {}).get("qoh", 0) or 0)
                mx = (inv or {}).get("max", 0)
                pct = int(round(qoh / mx * 100)) if mx else 0
                return 0, f"Defer: stock at {pct}% of max ({qoh}/{mx}), pack {pack_qty} would overshoot"
            rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
            return rounded, f"Reel auto: graduated to auto-order, rounded to replenishment unit {pack_qty}"
        return raw_need, "Reel auto: graduated to auto-order"

    if policy == "pack_trigger":
        if pack_qty and pack_qty > 0:
            if _should_defer_pack_overshoot(raw_need, pack_qty, inv):
                qoh = max(0, (inv or {}).get("qoh", 0) or 0)
                mx = (inv or {}).get("max", 0)
                pct = int(round(qoh / mx * 100)) if mx else 0
                return 0, f"Defer: stock at {pct}% of max ({qoh}/{mx}), pack {pack_qty} would overshoot"
            rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
            return rounded, f"Pack trigger: rounded to replenishment unit {pack_qty}"
        return raw_need, "Pack trigger (no pack data)"

    if pack_qty and pack_qty > 0:
        if _should_defer_pack_overshoot(raw_need, pack_qty, inv):
            qoh = max(0, (inv or {}).get("qoh", 0) or 0)
            mx = (inv or {}).get("max", 0)
            pct = int(round(qoh / mx * 100)) if mx else 0
            return 0, f"Defer: stock at {pct}% of max ({qoh}/{mx}), pack {pack_qty} would overshoot"
        rounded = max(pack_qty, math.ceil(raw_need / pack_qty) * pack_qty)
        # Near-boundary tolerance: if raw_need is within 5% BELOW a pack
        # multiple (e.g. 99 need vs 100 pack), use exact qty instead of
        # rounding up.  Only triggers when the waste from rounding is tiny.
        waste = rounded - raw_need
        if waste > 0 and rounded > pack_qty and (waste / pack_qty) < 0.05:
            return raw_need, f"Near-pack boundary: {raw_need} is within 5% of pack {pack_qty}, using exact qty"
        return rounded, f"Rounded up to pack of {pack_qty}"

    return raw_need, "Standard (no pack)"


DEFAULT_LEAD_TIME_DAYS = 14


def compute_stockout_risk_score(item, lead_time_days=None):
    """Return a 0.0-1.0 stockout risk score for an enriched item.

    0.0 — no meaningful risk (no demand, or inventory covers >= 2x lead time)
    1.0 — critical (zero cover with active demand)
    """
    if lead_time_days is None:
        lead_time_days = DEFAULT_LEAD_TIME_DAYS
    demand_signal = item.get("demand_signal", 0) or 0
    if demand_signal <= 0:
        return 0.0
    inventory_position = item.get("inventory_position", 0) or 0
    daily_demand = demand_signal / 365.0
    days_of_cover = inventory_position / daily_demand if daily_demand > 0 else 999.0
    buffer_days = 2.0 * lead_time_days
    coverage_risk = max(0.0, min(1.0, 1.0 - days_of_cover / buffer_days))
    recency_confidence = (item.get("recency_confidence", "low") or "low").lower()
    recency_weight = {"high": 0.0, "medium": 0.10, "low": 0.20}.get(recency_confidence, 0.15)
    score = min(1.0, coverage_risk + recency_weight * (1.0 - coverage_risk))
    return round(score, 3)
