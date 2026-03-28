from collections import defaultdict

import item_workflow
import performance_flow
import reorder_flow
import shipping_flow
import storage
import ui_bulk
from item_workflow import apply_recent_order_context
from rules import enrich_item, get_rule_float, get_rule_int, get_rule_pack_size, has_exact_qty_override


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
    resolve_pack_size_with_source=None,
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

    def _protected_inventory_candidate_reason(key, inv, rule, pack_size):
        inventory_position = max(0, inv.get("qoh", 0) or 0) + session.on_po_qty.get(key, 0)
        current_min = inv.get("min")
        if isinstance(current_min, (int, float)) and current_min > 0 and inventory_position < current_min:
            return "below_current_min"

        trigger_candidates = []
        trigger_qty = get_rule_int(rule, "reorder_trigger_qty")
        if isinstance(trigger_qty, (int, float)) and trigger_qty > 0:
            trigger_candidates.append(trigger_qty)
        trigger_pct = get_rule_float(rule, "reorder_trigger_pct")
        if (
            isinstance(pack_size, (int, float))
            and pack_size > 0
            and isinstance(trigger_pct, (int, float))
            and trigger_pct > 0
        ):
            trigger_candidates.append(pack_size * (trigger_pct / 100.0))
        minimum_packs = get_rule_int(rule, "minimum_packs_on_hand")
        if (
            isinstance(pack_size, (int, float))
            and pack_size > 0
            and isinstance(minimum_packs, (int, float))
            and minimum_packs > 0
        ):
            trigger_candidates.append(pack_size * minimum_packs)
        if trigger_candidates and inventory_position < max(trigger_candidates):
            return "below_rule_trigger"
        return ""

    def _append_candidate(filtered_items, payload, key):
        filtered_items.append(payload)
        reorder_flow.apply_receipt_vendor_context(session, filtered_items[-1], key)
        seen_keys.add(key)

    def _append_review_reason(item, code, detail):
        item["review_required"] = True
        if code:
            reason_codes = list(item.get("reason_codes", []) or [])
            if code not in reason_codes:
                reason_codes.append(code)
            item["reason_codes"] = reason_codes
        base_why = str(item.get("core_why", item.get("why", "")) or "").strip()
        if detail and detail not in base_why:
            merged = f"{base_why} | {detail}" if base_why else detail
            item["core_why"] = merged
            item["why"] = merged

    filtered_items = []
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
        if callable(resolve_pack_size_with_source):
            pack_size, pack_source = resolve_pack_size_with_source(key)
        else:
            pack_size = resolve_pack_size(key)
            pack_source = ""
        _append_candidate(filtered_items, {
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
            "pack_size": pack_size,
            "pack_size_source": pack_source,
            "reorder_cycle_weeks": get_cycle_weeks(),
        }, key)

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
        if callable(resolve_pack_size_with_source):
            pack_size, pack_source = resolve_pack_size_with_source(key)
        else:
            pack_size = resolve_pack_size(key)
            pack_source = ""
        _append_candidate(filtered_items, {
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
            "pack_size": pack_size,
            "pack_size_source": pack_source,
            "reorder_cycle_weeks": get_cycle_weeks(),
        }, key)

    for key, inv in session.inventory_lookup.items():
        if key in seen_keys or key[0] in excluded_line_codes:
            continue
        if f"{key[0]}:{key[1]}" in ignored_keys:
            continue
        if callable(resolve_pack_size_with_source):
            pack_size, pack_source = resolve_pack_size_with_source(key)
        else:
            pack_size = resolve_pack_size(key)
            pack_source = ""
        rule = session.order_rules.get(get_rule_key(key[0], key[1]))
        preserved_reason = _protected_inventory_candidate_reason(key, inv or {}, rule, pack_size)
        if not preserved_reason:
            continue
        _append_candidate(filtered_items, {
            "line_code": key[0],
            "item_code": key[1],
            "description": str((inv or {}).get("description", "") or ""),
            "qty_sold": 0,
            "effective_qty_sold": 0,
            "qty_received": 0,
            "qty_suspended": 0,
            "effective_qty_suspended": 0,
            "suspense_carry_qty": 0,
            "demand_signal": 0,
            "qty_on_po": session.on_po_qty.get(key, 0),
            "gross_need": 0,
            "order_qty": 0,
            "vendor": default_vendor_for_key(key),
            "pack_size": pack_size,
            "pack_size_source": pack_source,
            "reorder_cycle_weeks": get_cycle_weeks(),
            "candidate_preserved": True,
            "candidate_preserved_source": "inventory_protection",
            "candidate_preserved_reason": preserved_reason,
        }, key)

    if not filtered_items:
        return False

    filtered_items.sort(key=lambda x: (x["line_code"], x["item_code"]))
    ui_bulk.replace_filtered_items(session, filtered_items)

    session.recent_orders = storage.get_recent_orders(order_history_path, lookback_days)
    missing_inventory_keys = set(getattr(session, "inventory_coverage_missing_keys", set()) or set())
    detailed_conflict_keys = set(getattr(session, "detailed_sales_conflict_keys", set()) or set())
    unresolved_item_codes = set(getattr(session, "unresolved_detailed_item_codes", set()) or set())

    for item in session.filtered_items:
        key = (item["line_code"], item["item_code"])
        inv = session.inventory_lookup.get(key, {})
        sug_min, sug_max, sug_source = reorder_flow.suggest_min_max_with_source(
            session,
            key,
            reorder_flow.min_annual_sales_threshold(session),
        )
        reorder_flow.apply_suggestion_context(session, item, key, (sug_min, sug_max), active_source=sug_source)
        apply_recent_order_context(item, session.recent_orders.get(key, []))
        rule_key = get_rule_key(item["line_code"], item["item_code"])
        rule = session.order_rules.get(rule_key)
        rule_pack = get_rule_pack_size(rule)
        if rule_pack is not None:
            item["pack_size"] = rule_pack
            item["pack_size_source"] = "rule"
        elif has_exact_qty_override(rule):
            item["pack_size"] = None
            item["pack_size_source"] = "rule_exact_qty"
        enrich_item(item, inv, item.get("pack_size"), rule)
        preserved_reason = str(item.get("candidate_preserved_reason", "") or "").strip()
        if preserved_reason:
            detail = {
                "below_current_min": "Candidate preserved: inventory is below current min even without loaded demand",
                "below_rule_trigger": "Candidate preserved: inventory is below an explicit rule-based trigger even without loaded demand",
            }.get(preserved_reason, "Candidate preserved by inventory protection rules")
            base_why = str(item.get("core_why", item.get("why", "")) or "").strip()
            if base_why and detail not in base_why:
                merged = f"{base_why} | {detail}"
                item["core_why"] = merged
                item["why"] = merged
            reason_codes = list(item.get("reason_codes", []) or [])
            for code in ("candidate_preserved", f"candidate_preserved_{preserved_reason}"):
                if code not in reason_codes:
                    reason_codes.append(code)
            item["reason_codes"] = reason_codes
            _append_review_reason(item, "", detail)
        if key in missing_inventory_keys:
            _append_review_reason(
                item,
                "inventory_coverage_gap",
                "Review: sales item is missing from inventory/min-max data, so reorder guidance is running on incomplete coverage",
            )
        if key in detailed_conflict_keys:
            _append_review_reason(
                item,
                "source_mapping_conflict",
                "Review: parsed detailed-sales line code conflicts with known inventory or receipt-history mapping",
            )
        if not item.get("line_code") and item.get("item_code") in unresolved_item_codes:
            _append_review_reason(
                item,
                "source_mapping_unresolved",
                "Review: detailed sales rows could not be resolved to a supported line code",
            )
        reorder_flow.append_suggestion_comparison_reason(item)
        item_workflow.apply_suggestion_gap_review_state(item)
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
