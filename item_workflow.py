import reorder_flow
from rules import enrich_item, infer_default_order_policy


def find_filtered_item(filtered_items, key):
    """Return the live filtered item matching the given (line_code, item_code)."""
    for item in filtered_items:
        if (item["line_code"], item["item_code"]) == key:
            return item
    return None


def get_effective_order_qty(item):
    """Return the current working quantity regardless of storage field."""
    return item.get("final_qty", item.get("order_qty", 0))


def set_effective_order_qty(item, qty, *, manual_override=False):
    """Keep quantity fields aligned while optionally marking a user override."""
    qty = max(0, int(qty))
    item["final_qty"] = qty
    item["order_qty"] = qty
    if manual_override:
        item["manual_override"] = True


def clear_manual_override(item):
    """Allow recalculation-driven edits to restore the suggested quantity."""
    item["manual_override"] = False


def apply_recent_order_context(item, recent_orders):
    """Stamp recent local PO evidence onto an item for recency-confidence handling."""
    recent_orders = list(recent_orders or [])
    total_qty = 0
    latest_date = ""
    for row in recent_orders:
        try:
            total_qty += max(0, int(float(row.get("qty", 0) or 0)))
        except Exception:
            continue
        raw_date = str(row.get("date", "") or "").strip()
        if raw_date and raw_date > latest_date:
            latest_date = raw_date
    item["recent_local_order_count"] = len(recent_orders)
    item["recent_local_order_qty"] = total_qty
    item["recent_local_order_date"] = latest_date
    item["has_recent_local_order"] = bool(recent_orders and total_qty > 0)


def apply_pack_size_edit(item, raw, order_rules, get_rule_key):
    """Update an item's pack size and its persisted per-item rule."""
    item["pack_size"] = None if raw == "" else int(float(raw))
    rule_key = get_rule_key(item["line_code"], item["item_code"])
    rule = dict(order_rules.get(rule_key) or {})
    if item["pack_size"] is None:
        rule.pop("pack_size", None)
    else:
        rule["pack_size"] = item["pack_size"]
    if not rule.get("policy_locked") and rule.get("order_policy") in ("exact_qty", "standard"):
        rule.pop("order_policy", None)
    order_rules[rule_key] = rule
    return rule_key, rule


def effective_order_rule(item, rule, inventory_lookup):
    """Ignore stale default policies so the current pack data can drive the default behavior."""
    if not rule:
        return rule
    effective = dict(rule)
    if not effective.get("policy_locked"):
        inferred_policy = infer_default_order_policy(
            item,
            inventory_lookup.get((item["line_code"], item["item_code"]), {}),
            item.get("pack_size"),
            allow_below_pack=effective.get("allow_below_pack", False),
        )
        saved_policy = effective.get("order_policy")
        if saved_policy == inferred_policy or saved_policy in ("exact_qty", "standard"):
            effective.pop("order_policy", None)
    return effective


def recalculate_item(item, inventory_lookup, order_rules, suggest_min_max, get_rule_key, *, suggestion_context_app=None):
    """Refresh derived ordering fields for a single item after edits."""
    key = (item["line_code"], item["item_code"])
    rule_key = get_rule_key(item["line_code"], item["item_code"])
    rule = effective_order_rule(item, order_rules.get(rule_key), inventory_lookup)
    sug_min, sug_max = suggest_min_max(key)
    if suggestion_context_app is not None:
        reorder_flow.apply_suggestion_context(suggestion_context_app, item, key, (sug_min, sug_max))
    else:
        item["suggested_min"] = sug_min
        item["suggested_max"] = sug_max
    enrich_item(item, inventory_lookup.get(key, {}), item.get("pack_size"), rule)
    if suggestion_context_app is not None:
        reorder_flow.append_suggestion_comparison_reason(item)
    return item


def recalculate_item_from_session(item, session, suggest_min_max, get_rule_key):
    apply_recent_order_context(
        item,
        (getattr(session, "recent_orders", {}) or {}).get((item["line_code"], item["item_code"]), []),
    )
    return recalculate_item(
        item,
        session.inventory_lookup,
        session.order_rules,
        suggest_min_max,
        get_rule_key,
        suggestion_context_app=session,
    )


def sync_review_item_to_filtered(
    review_item,
    filtered_items,
    inventory_lookup,
    order_rules,
    suggest_min_max,
    get_rule_key,
    *,
    suggestion_context_app=None,
):
    """Mirror review edits back to the filtered item so both views stay consistent."""
    key = (review_item["line_code"], review_item["item_code"])
    filtered = find_filtered_item(filtered_items, key)
    if filtered is None:
        return None

    filtered["vendor"] = review_item.get("vendor", filtered.get("vendor", ""))
    filtered["pack_size"] = review_item.get("pack_size")
    if not review_item.get("manual_override", False):
        clear_manual_override(filtered)
    set_effective_order_qty(
        filtered,
        review_item.get("order_qty", get_effective_order_qty(filtered)),
        manual_override=review_item.get("manual_override", False),
    )
    recalculate_item(
        filtered,
        inventory_lookup,
        order_rules,
        suggest_min_max,
        get_rule_key,
        suggestion_context_app=suggestion_context_app,
    )

    review_item["status"] = filtered.get("status", review_item.get("status", "ok"))
    review_item["why"] = filtered.get("why", review_item.get("why", ""))
    review_item["data_flags"] = list(filtered.get("data_flags", review_item.get("data_flags", [])))
    review_item["order_policy"] = filtered.get("order_policy", review_item.get("order_policy", ""))
    review_item["suggested_min"] = filtered.get("suggested_min")
    review_item["suggested_max"] = filtered.get("suggested_max")
    review_item["detailed_suggested_min"] = filtered.get("detailed_suggested_min")
    review_item["detailed_suggested_max"] = filtered.get("detailed_suggested_max")
    review_item["detailed_suggestion_compare"] = filtered.get("detailed_suggestion_compare", "")
    review_item["detailed_suggestion_compare_label"] = filtered.get("detailed_suggestion_compare_label", "")
    review_item["suggested_qty"] = filtered.get("suggested_qty")
    review_item["raw_need"] = filtered.get("raw_need")
    review_item["final_qty"] = get_effective_order_qty(filtered)
    review_item["order_qty"] = get_effective_order_qty(filtered)
    review_item["manual_override"] = filtered.get("manual_override", review_item.get("manual_override", False))
    return filtered


def sync_review_item_to_filtered_from_session(review_item, session, suggest_min_max, get_rule_key):
    return sync_review_item_to_filtered(
        review_item,
        session.filtered_items,
        session.inventory_lookup,
        session.order_rules,
        suggest_min_max,
        get_rule_key,
        suggestion_context_app=session,
    )
