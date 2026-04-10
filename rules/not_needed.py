"""Not-needed classification logic for bulk removal flow.

Extracted from ui_bulk_dialogs.py to avoid duplicating rules.py logic
in a UI module.
"""

import math

from rules.calc import determine_acceptable_overstock_qty


def not_needed_reason(app, item, max_exceed_abs_buffer):
    reasons = []
    auto_remove = False
    key = (item["line_code"], item["item_code"])
    inv = app.inventory_lookup.get(key, {})
    qoh = inv.get("qoh", 0)
    if qoh is None:
        qoh = 0
    mx = inv.get("max")
    ps = item.get("pack_size")
    po_qty = item.get("qty_on_po", app.on_po_qty.get(key, 0))
    final_qty = item.get("final_qty", item.get("order_qty", 0))
    suggested_qty = item.get("suggested_qty", final_qty)
    gross_need = item.get("gross_need", item.get("raw_need", final_qty))
    inventory_position = item.get("inventory_position", qoh + po_qty)
    target_stock = item.get("target_stock")
    effective_target_stock = item.get("effective_target_stock")
    demand_signal = item.get("demand_signal", gross_need)
    effective_susp = item.get("effective_qty_suspended", item.get("qty_suspended", 0))
    effective_sales = item.get("effective_qty_sold", item.get("qty_sold", 0))
    performance_profile = item.get("performance_profile", "")
    sales_health_signal = item.get("sales_health_signal", "")
    possible_missed_reorder = bool(item.get("possible_missed_reorder"))
    reorder_trigger_threshold = item.get("reorder_trigger_threshold")
    reorder_trigger_basis = item.get("reorder_trigger_basis", "")
    reorder_needed = bool(item.get("reorder_needed"))
    acceptable_overstock = item.get("acceptable_overstock_qty_effective")
    if acceptable_overstock in (None, ""):
        acceptable_overstock = determine_acceptable_overstock_qty(item)

    if item.get("status") == "skip" or final_qty <= 0:
        reasons.append("No net need (skip/zero final qty)")
        auto_remove = True

    if target_stock is None:
        _, sug_max = app._suggest_min_max(key)
        target_candidates = [
            value for value in (mx, sug_max) if isinstance(value, (int, float)) and value > 0
        ]
        target_stock = max(target_candidates) if target_candidates else 0
    else:
        _, sug_max = app._suggest_min_max(key)

    effective_order_floor = item.get("effective_order_floor", effective_target_stock)
    if (
        isinstance(effective_order_floor, (int, float))
        and effective_order_floor > 0
        and (
            not isinstance(target_stock, (int, float))
            or effective_order_floor > target_stock
        )
    ):
        target_stock = effective_order_floor

    if target_stock and inventory_position >= target_stock and final_qty > 0:
        reasons.append(
            f"Inventory position already meets target (pos {inventory_position:g} >= target {target_stock:g})"
        )
        auto_remove = True

    if demand_signal <= 0 and inventory_position > 0 and final_qty > 0:
        reasons.append(f"No uncovered demand signal (sales {effective_sales:g}, susp {effective_susp:g})")
        auto_remove = True

    if (
        ps
        and qoh >= gross_need
        and gross_need > 0
        and not (
            reorder_needed
            and isinstance(reorder_trigger_threshold, (int, float))
            and reorder_trigger_threshold > 0
        )
    ):
        reasons.append(f"QOH covers demand signal (QOH {qoh:g} >= need {gross_need:g})")
        auto_remove = True

    resulting_stock = inventory_position + final_qty

    hard_max = mx if isinstance(mx, (int, float)) and mx > 0 else None
    soft_candidates = [
        value for value in (target_stock, hard_max, sug_max) if isinstance(value, (int, float)) and value > 0
    ]
    soft_max = max(soft_candidates) if soft_candidates else None

    pack_margin = math.ceil(ps * 0.5) if isinstance(ps, (int, float)) and ps > 0 else 0

    def _margin(max_ref):
        return max(max_exceed_abs_buffer, math.ceil(max_ref * 0.25), pack_margin)

    hard_excess = False
    soft_excess = False
    if hard_max is not None:
        hard_threshold = hard_max + _margin(hard_max) + acceptable_overstock
        hard_excess = resulting_stock > hard_threshold
    else:
        hard_threshold = None

    if soft_max is not None:
        soft_threshold = soft_max + _margin(soft_max) + acceptable_overstock
        soft_excess = resulting_stock > soft_threshold
    else:
        soft_threshold = None

    if soft_excess:
        reasons.append(
            f"Strong target exceed (stock {resulting_stock:g} > soft limit {soft_threshold:g}; "
            f"target {target_stock if target_stock is not None else '-'}, "
            f"cur max {hard_max if hard_max is not None else '-'}, sug max {sug_max if sug_max is not None else '-'})"
        )
        auto_remove = True
    elif acceptable_overstock > 0 and resulting_stock > (soft_max or 0):
        reasons.append(
            f"Review: intentional overstock is within tolerance (stock {resulting_stock:g}; allowed over target {acceptable_overstock:g})"
        )
    elif hard_excess:
        reasons.append(
            f"Review: exceeds current max (stock {resulting_stock:g} > hard limit {hard_threshold:g}; "
            f"cur max {hard_max:g}, sug max {sug_max if sug_max is not None else '-'})"
        )

    if isinstance(suggested_qty, (int, float)) and suggested_qty >= 0 and final_qty > 0:
        if isinstance(ps, (int, float)) and ps > 0:
            qty_tolerance = ps
        else:
            qty_tolerance = max(1, math.ceil(suggested_qty * 0.5))
        if final_qty > (suggested_qty + qty_tolerance):
            if hard_excess or soft_excess:
                reasons.append(
                    f"Final qty far above suggestion ({final_qty:g} vs suggested {suggested_qty:g}, tol {qty_tolerance:g})"
                )
                auto_remove = auto_remove or soft_excess
            else:
                reasons.append(
                    f"Review: final qty above suggestion ({final_qty:g} vs suggested {suggested_qty:g}, tol {qty_tolerance:g})"
                )

    if target_stock and final_qty > 0 and resulting_stock > target_stock and suggested_qty <= 0:
        reasons.append(
            f"Review: order pushes stock above target despite zero suggestion (stock {resulting_stock:g} vs target {target_stock:g})"
        )

    protect_from_auto_remove = False
    if possible_missed_reorder:
        reasons.append("Review: likely missed reorder candidate based on historical sales and stale recency")
        protect_from_auto_remove = True
    elif (
        reorder_needed
        and isinstance(reorder_trigger_threshold, (int, float))
        and reorder_trigger_threshold > 0
    ):
        basis_label = {
            "minimum_packs_on_hand": "minimum packs on hand",
            "trigger_qty": "trigger quantity",
            "trigger_pct": "trigger percent",
            "current_min": "current min",
            "configured_trigger": "configured trigger",
        }.get(reorder_trigger_basis, "trigger threshold")
        reasons.append(
            f"Review: trigger-based replenishment is active (pos {inventory_position:g} <= trigger {reorder_trigger_threshold:g}; basis {basis_label})"
        )
        protect_from_auto_remove = True
    elif performance_profile in ("top_performer", "steady") and sales_health_signal == "dormant":
        reasons.append("Review: historically meaningful item is dormant, so removal should be confirmed manually")
        protect_from_auto_remove = True

    if protect_from_auto_remove:
        auto_remove = False

    return "; ".join(reasons), auto_remove


