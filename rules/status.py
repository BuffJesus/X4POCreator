"""Item status evaluation — determines ok / review / warning / skip
and populates data_flags for the UI and export paths."""


def evaluate_item_status(item):
    """
    Evaluate the status of an item and set data_flags.
    Returns (status, data_flags) where status is 'ok', 'review', 'warning', 'skip'
    """
    flags = []
    status = "ok"

    if not item.get("pack_size") and not item.get("exact_qty_override"):
        flags.append("missing_pack")

    if item.get("order_policy") == "reel_review":
        flags.append("reel_review")
        status = "review"

    if item.get("order_policy") == "reel_auto":
        flags.append("reel_auto")

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
        if item.get("deferred_pack_overshoot"):
            flags.append("deferred_pack_overshoot")

    if final <= 0 and raw <= 0:
        status = "skip"

    if final > 0:
        projected_overstock = item.get("projected_overstock_qty", 0) or 0
        within_tolerance = item.get("overstock_within_tolerance", True)
        if projected_overstock > 0 and not within_tolerance:
            flags.append("would_overshoot_max")
        target = item.get("effective_target_stock", item.get("target_stock", 0)) or 0
        floor = item.get("effective_order_floor", target) or 0
        acceptable_overstock = item.get("acceptable_overstock_qty_effective", 0) or 0
        if floor > target + acceptable_overstock:
            flags.append("order_floor_above_max")

    if (
        item.get("review_required")
        and not item.get("review_resolved")
        and (raw > 0 or final > 0)
    ):
        status = "review"

    return status, flags
