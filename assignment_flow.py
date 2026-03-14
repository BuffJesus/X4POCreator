from collections import defaultdict

import performance_flow
import shipping_flow
import storage
from item_workflow import apply_recent_order_context
from rules import enrich_item, get_rule_pack_size


def prepare_assignment_session(
    session,
    *,
    excluded_line_codes,
    excluded_customers,
    dup_whitelist,
    ignored_keys,
    lookback_days,
    order_history_path,
    vendor_codes_path,
    known_vendors,
    get_suspense_carry_qty,
    default_vendor_for_key,
    resolve_pack_size,
    suggest_min_max,
    get_cycle_weeks,
    get_rule_key,
    default_vendor_policy_preset="",
):
    """Apply filters, merge source data, and prepare the session for assignment."""
    session.suspended_lookup = defaultdict(list)
    session.suspended_set = set()
    for suspended_item in session.suspended_items:
        if suspended_item["line_code"] in excluded_line_codes:
            continue
        cust_code = suspended_item.get("customer_code", "")
        if cust_code in excluded_customers:
            continue
        key = (suspended_item["line_code"], suspended_item["item_code"])
        session.suspended_lookup[key].append(suspended_item)
        session.suspended_set.add(key)

    suspended_qty = defaultdict(int)
    for suspended_item in session.suspended_items:
        if suspended_item["line_code"] in excluded_line_codes:
            continue
        cust_code = suspended_item.get("customer_code", "")
        if cust_code in excluded_customers:
            continue
        key = (suspended_item["line_code"], suspended_item["item_code"])
        suspended_qty[key] += suspended_item.get("qty_ordered", 0)

    session.on_po_qty = defaultdict(float)
    for po_item in session.po_items:
        key = (po_item["line_code"], po_item["item_code"])
        session.on_po_qty[key] += po_item["qty"]

    session.filtered_items = []
    seen_keys = set()
    for item in session.sales_items:
        if item["line_code"] in excluded_line_codes:
            continue
        key = (item["line_code"], item["item_code"])
        if f"{key[0]}:{key[1]}" in ignored_keys:
            continue
        sq = suspended_qty.get(key, 0)
        carry_qty = get_suspense_carry_qty(key)
        effective_sales = max(0, int(item.get("qty_sold", 0)) - carry_qty)
        effective_susp = max(0, sq - carry_qty)
        demand_signal = effective_sales + effective_susp
        inv = session.inventory_lookup.get(key, {})
        inventory_position = (inv.get("qoh", 0) or 0) + session.on_po_qty.get(key, 0)
        current_min = inv.get("min")
        if demand_signal <= 0 and not (
            isinstance(current_min, (int, float)) and inventory_position < current_min
        ):
            continue
        po_qty = session.on_po_qty.get(key, 0)
        session.filtered_items.append({
            **item,
            "qty_suspended": sq,
            "effective_qty_sold": effective_sales,
            "effective_qty_suspended": effective_susp,
            "suspense_carry_qty": carry_qty,
            "demand_signal": demand_signal,
            "qty_on_po": po_qty,
            "gross_need": demand_signal,
            "order_qty": 0,
            "vendor": default_vendor_for_key(key),
            "pack_size": resolve_pack_size(key),
            "reorder_cycle_weeks": get_cycle_weeks(),
        })
        seen_keys.add(key)

    for key, susp_list in session.suspended_lookup.items():
        if key in seen_keys or key[0] in excluded_line_codes:
            continue
        if f"{key[0]}:{key[1]}" in ignored_keys:
            continue
        sq = suspended_qty.get(key, 0)
        if sq <= 0:
            continue
        carry_qty = get_suspense_carry_qty(key)
        effective_susp = max(0, sq - carry_qty)
        if effective_susp <= 0:
            continue
        po_qty = session.on_po_qty.get(key, 0)
        first = susp_list[0]
        session.filtered_items.append({
            "line_code": key[0],
            "item_code": key[1],
            "description": first.get("description", ""),
            "qty_sold": 0,
            "effective_qty_sold": 0,
            "qty_received": 0,
            "qty_suspended": sq,
            "effective_qty_suspended": effective_susp,
            "suspense_carry_qty": carry_qty,
            "demand_signal": effective_susp,
            "qty_on_po": po_qty,
            "gross_need": effective_susp,
            "order_qty": 0,
            "vendor": default_vendor_for_key(key),
            "pack_size": resolve_pack_size(key),
            "reorder_cycle_weeks": get_cycle_weeks(),
        })

    if not session.filtered_items:
        return False

    session.filtered_items.sort(key=lambda x: (x["line_code"], x["item_code"]))

    session.recent_orders = storage.get_recent_orders(order_history_path, lookback_days)

    for item in session.filtered_items:
        key = (item["line_code"], item["item_code"])
        inv = session.inventory_lookup.get(key, {})
        sug_min, sug_max = suggest_min_max(key)
        item["suggested_min"] = sug_min
        item["suggested_max"] = sug_max
        apply_recent_order_context(item, session.recent_orders.get(key, []))
        rule_key = get_rule_key(item["line_code"], item["item_code"])
        rule = session.order_rules.get(rule_key)
        rule_pack = get_rule_pack_size(rule)
        if rule_pack is not None:
            item["pack_size"] = rule_pack
        enrich_item(item, inv, item.get("pack_size"), rule)
    performance_flow.annotate_items(
        session.filtered_items,
        inventory_lookup=session.inventory_lookup,
    )

    duplicate_ic_lookup = defaultdict(set)
    for line_code, item_code in session.inventory_lookup:
        duplicate_ic_lookup[item_code].add(line_code)
    session.duplicate_ic_lookup = {
        item_code: line_codes
        for item_code, line_codes in duplicate_ic_lookup.items()
        if len(line_codes) > 1 and item_code not in dup_whitelist
    }

    session.assigned_items = []
    session.qoh_adjustments = {}
    session.default_vendor_policy_preset = str(default_vendor_policy_preset or "").strip()
    session.vendor_codes_used = storage.load_vendor_codes(vendor_codes_path, known_vendors)
    for item in session.filtered_items:
        vendor = item.get("vendor", "").strip().upper()
        if vendor and vendor not in session.vendor_codes_used:
            session.vendor_codes_used.append(vendor)
    session.vendor_codes_used.sort()
    shipping_flow.annotate_release_decisions(session)
    return True
