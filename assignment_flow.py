import time
from collections import defaultdict

import item_workflow
import performance_flow
import perf_trace
import reorder_flow
import shipping_flow
import storage
import ui_bulk
from item_workflow import apply_recent_order_context
from rules import enrich_item, get_rule_float, get_rule_int, get_rule_pack_size, has_exact_qty_override


def _compute_override_pattern(entries):
    """Return 'always_up', 'always_down', 'mixed', or None based on full order history entries."""
    directions = []
    for e in entries:
        final = e.get("final_qty")
        suggested = e.get("suggested_qty")
        if final is None or suggested is None:
            continue
        if final > suggested:
            directions.append("up")
        elif final < suggested:
            directions.append("down")
    if not directions:
        return None
    if all(d == "up" for d in directions):
        return "always_up"
    if all(d == "down" for d in directions):
        return "always_down"
    return "mixed"


@perf_trace.timed("assignment_flow.prepare_assignment_session")
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

    perf_trace.stamp("assignment_flow.stage", stage="begin")
    filtered_items = []
    seen_keys = set()
    cb_vendor_time = 0.0
    cb_pack_time = 0.0
    cb_suspense_time = 0.0
    cb_other_time = 0.0

    # ── Hot-loop locals (v0.8.10 perf pass) ──────────────────────────
    # Python's attribute / function resolution is slow when done 60K
    # times.  Hoist every per-item lookup + callable to a local so the
    # inner loop runs on fast LOAD_FAST opcodes.
    inv_lookup = session.inventory_lookup
    on_po_qty = session.on_po_qty
    cycle_weeks_now = get_cycle_weeks()
    span_days = getattr(session, "sales_span_days", None)
    cycle_days_cached = cycle_weeks_now * 7 if isinstance(cycle_weeks_now, (int, float)) else 14
    span_divisor = span_days if isinstance(span_days, (int, float)) and span_days > 0 else 0
    has_pack_with_source = callable(resolve_pack_size_with_source)
    local_resolve_pack_with_source = resolve_pack_size_with_source
    local_resolve_pack = resolve_pack_size
    local_default_vendor = default_vendor_for_key
    local_suspense_carry = get_suspense_carry_qty
    local_suspended_qty = suspended_qty
    local_append = _append_candidate

    def _cycle_normalize(raw_demand):
        """Inline demand → per-cycle demand.  Matches the logic in
        reorder_flow._normalize_demand_signal but without the function
        call overhead."""
        if span_divisor <= 0:
            return raw_demand
        if raw_demand <= 0:
            return 0
        normalized = raw_demand * cycle_days_cached / span_divisor
        return int(round(normalized))

    _perf_counter = time.perf_counter
    for item in session.sales_items:
        _t0 = _perf_counter()
        line_code = item["line_code"]
        if line_code in excluded_line_codes:
            continue
        item_code = item["item_code"]
        key = (line_code, item_code)
        if f"{line_code}:{item_code}" in ignored_keys:
            continue
        _t_suspense_start = _perf_counter()
        sq = local_suspended_qty.get(key, 0)
        carry_qty = local_suspense_carry(key)
        _t_suspense_end = _perf_counter()
        cb_suspense_time += _t_suspense_end - _t_suspense_start
        effective_sales = int(item.get("qty_sold", 0)) - carry_qty
        if effective_sales < 0:
            effective_sales = 0
        effective_susp = sq - carry_qty
        if effective_susp < 0:
            effective_susp = 0
        raw_demand = effective_sales + effective_susp
        inv = inv_lookup.get(key) or {}
        po_qty = on_po_qty.get(key, 0)
        current_min = inv.get("min")
        # Pre-normalize filter: cheap short-circuit before the demand
        # normalization + candidate dict allocation
        if raw_demand <= 0:
            inventory_position = (inv.get("qoh", 0) or 0) + po_qty
            if not (
                isinstance(current_min, (int, float)) and inventory_position < current_min
            ):
                continue
        # v0.8.10: normalize demand in-place here so the second pass
        # (`normalize_items_to_cycle`) becomes a no-op.
        demand_signal = _cycle_normalize(raw_demand)
        _t_pack_start = _perf_counter()
        if has_pack_with_source:
            pack_size, pack_source = local_resolve_pack_with_source(key)
        else:
            pack_size = local_resolve_pack(key)
            pack_source = ""
        _t_pack_end = _perf_counter()
        cb_pack_time += _t_pack_end - _t_pack_start
        _t_vendor_start = _perf_counter()
        vendor_choice = local_default_vendor(key)
        _t_vendor_end = _perf_counter()
        cb_vendor_time += _t_vendor_end - _t_vendor_start
        candidate = dict(item)
        candidate["qty_suspended"] = sq
        candidate["effective_qty_sold"] = effective_sales
        candidate["effective_qty_suspended"] = effective_susp
        candidate["suspense_carry_qty"] = carry_qty
        candidate["demand_signal"] = demand_signal
        candidate["qty_on_po"] = po_qty
        candidate["gross_need"] = demand_signal
        candidate["order_qty"] = 0
        candidate["vendor"] = vendor_choice
        candidate["pack_size"] = pack_size
        candidate["pack_size_source"] = pack_source
        candidate["reorder_cycle_weeks"] = cycle_weeks_now
        candidate["sales_span_days"] = span_days
        local_append(filtered_items, candidate, key)
        cb_other_time += _perf_counter() - _t0 - (
            _t_suspense_end - _t_suspense_start
            + _t_pack_end - _t_pack_start
            + _t_vendor_end - _t_vendor_start
        )

    for key, susp_list in session.suspended_lookup.items():
        if key in seen_keys or key[0] in excluded_line_codes:
            continue
        if f"{key[0]}:{key[1]}" in ignored_keys:
            continue
        sq = local_suspended_qty.get(key, 0)
        if sq <= 0:
            continue
        carry_qty = local_suspense_carry(key)
        effective_susp = max(0, sq - carry_qty)
        if effective_susp <= 0:
            continue
        po_qty = on_po_qty.get(key, 0)
        first = susp_list[0]
        if has_pack_with_source:
            pack_size, pack_source = local_resolve_pack_with_source(key)
        else:
            pack_size = local_resolve_pack(key)
            pack_source = ""
        demand_signal = _cycle_normalize(effective_susp)
        local_append(filtered_items, {
            "line_code": key[0],
            "item_code": key[1],
            "description": first.get("description", ""),
            "qty_sold": 0,
            "effective_qty_sold": 0,
            "qty_received": 0,
            "qty_suspended": sq,
            "effective_qty_suspended": effective_susp,
            "suspense_carry_qty": carry_qty,
            "demand_signal": demand_signal,
            "qty_on_po": po_qty,
            "gross_need": demand_signal,
            "order_qty": 0,
            "vendor": local_default_vendor(key),
            "pack_size": pack_size,
            "pack_size_source": pack_source,
            "reorder_cycle_weeks": cycle_weeks_now,
            "sales_span_days": span_days,
        }, key)

    local_order_rules = session.order_rules
    local_rule_key = get_rule_key
    for key, inv in inv_lookup.items():
        if key in seen_keys or key[0] in excluded_line_codes:
            continue
        if f"{key[0]}:{key[1]}" in ignored_keys:
            continue
        if has_pack_with_source:
            pack_size, pack_source = local_resolve_pack_with_source(key)
        else:
            pack_size = local_resolve_pack(key)
            pack_source = ""
        rule = local_order_rules.get(local_rule_key(key[0], key[1]))
        preserved_reason = _protected_inventory_candidate_reason(key, inv or {}, rule, pack_size)
        if not preserved_reason:
            continue
        local_append(filtered_items, {
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
            "qty_on_po": on_po_qty.get(key, 0),
            "gross_need": 0,
            "order_qty": 0,
            "vendor": local_default_vendor(key),
            "pack_size": pack_size,
            "pack_size_source": pack_source,
            "reorder_cycle_weeks": cycle_weeks_now,
            "sales_span_days": span_days,
            "candidate_preserved": True,
            "candidate_preserved_source": "inventory_protection",
            "candidate_preserved_reason": preserved_reason,
        }, key)

    if not filtered_items:
        return False

    filtered_items.sort(key=lambda x: (x["line_code"], x["item_code"]))
    ui_bulk.replace_filtered_items(session, filtered_items)

    perf_trace.stamp(
        "assignment_flow.candidates_build_breakdown",
        vendor_ms=round(cb_vendor_time * 1000, 2),
        pack_ms=round(cb_pack_time * 1000, 2),
        suspense_ms=round(cb_suspense_time * 1000, 2),
        other_ms=round(cb_other_time * 1000, 2),
    )
    perf_trace.stamp("assignment_flow.stage", stage="candidates_built", count=len(filtered_items))
    session.recent_orders = storage.get_recent_orders(order_history_path, lookback_days)
    missing_inventory_keys = set(getattr(session, "inventory_coverage_missing_keys", set()) or set())
    detailed_conflict_keys = set(getattr(session, "detailed_sales_conflict_keys", set()) or set())
    unresolved_item_codes = set(getattr(session, "unresolved_detailed_item_codes", set()) or set())

    # ── Hot-loop locals for the enrich pass (v0.8.11) ────────────────
    # Same technique as the candidate-build loop: hoist every per-item
    # attribute / dict / function to a local so inner-loop dispatches
    # are LOAD_FAST opcodes instead of LOAD_ATTR chains.
    enrich_inv_lookup = session.inventory_lookup
    session_recent_orders = session.recent_orders
    session_order_rules = session.order_rules
    session_history_dict = getattr(session, "session_history", {}) or {}
    full_order_history_dict = getattr(session, "full_order_history", {}) or {}
    vendor_policies_dict = getattr(session, "vendor_policies", None) or {}
    min_annual_threshold = reorder_flow.min_annual_sales_threshold(session)
    # v0.8.12: memoize suggest_min_max_with_source per enrich pass.
    # The v0.8.11 trace showed the "other" enrich bucket at 11.9 s on
    # 59K items, and profiling suggested this function was dominating
    # — each call walks session.detailed_sales_stats_lookup +
    # inventory_lookup + order_rules.  Per-key is deterministic so a
    # local cache is safe; session also gets the cache afterwards so
    # later callers (ui_bulk row rendering, etc.) can hit it too.
    session_suggest_cache = getattr(session, "_suggest_min_max_source_cache", None)
    if session_suggest_cache is None:
        session_suggest_cache = {}
        session._suggest_min_max_source_cache = session_suggest_cache
    _raw_suggest_fn = reorder_flow.suggest_min_max_with_source

    def _cached_suggest(key):
        hit = session_suggest_cache.get(key)
        if hit is not None:
            return hit
        result = _raw_suggest_fn(session, key, min_annual_threshold)
        session_suggest_cache[key] = result
        return result

    suggest_min_max_fn = _cached_suggest
    apply_suggestion_ctx = reorder_flow.apply_suggestion_context
    local_enrich_item = enrich_item
    local_apply_recent = apply_recent_order_context
    local_get_rule_pack = get_rule_pack_size
    local_has_exact_qty = has_exact_qty_override
    local_compute_override = _compute_override_pattern
    local_append_suggestion_reason = reorder_flow.append_suggestion_comparison_reason
    local_apply_suggestion_gap = item_workflow.apply_suggestion_gap_review_state
    enrich_time_total = 0.0
    gap_time_total = 0.0
    other_time_total = 0.0

    for item in session.filtered_items:
        _t_start = time.perf_counter()
        line_code = item["line_code"]
        item_code = item["item_code"]
        key = (line_code, item_code)
        inv = enrich_inv_lookup.get(key) or {}
        sug_min, sug_max, sug_source = suggest_min_max_fn(key)
        apply_suggestion_ctx(session, item, key, (sug_min, sug_max), active_source=sug_source)
        local_apply_recent(item, session_recent_orders.get(key, []))
        rule_key = f"{line_code}:{item_code}"
        rule = session_order_rules.get(rule_key)
        rule_pack = local_get_rule_pack(rule)
        if rule_pack is not None:
            item["pack_size"] = rule_pack
            item["pack_size_source"] = "rule"
        elif local_has_exact_qty(rule):
            item["pack_size"] = None
            item["pack_size_source"] = "rule_exact_qty"
        history_qtys = session_history_dict.get(key)
        if history_qtys:
            sorted_qtys = sorted(history_qtys)
            mid = len(sorted_qtys) // 2
            item["historical_order_qty"] = sorted_qtys[mid] if len(sorted_qtys) % 2 != 0 else (sorted_qtys[mid - 1] + sorted_qtys[mid]) // 2
        full_entries = full_order_history_dict.get(key, [])
        if len(full_entries) >= 2:
            item["suggestion_override_pattern"] = local_compute_override(full_entries)
        else:
            item["suggestion_override_pattern"] = None
        _vendor = str(item.get("vendor") or "").strip().upper()
        _vp = vendor_policies_dict.get(_vendor, {}) if _vendor else {}
        _t_before_enrich = time.perf_counter()
        other_time_total += _t_before_enrich - _t_start
        local_enrich_item(item, inv, item.get("pack_size"), rule, lead_time_days=_vp.get("estimated_lead_days"))
        _t_after_enrich = time.perf_counter()
        enrich_time_total += _t_after_enrich - _t_before_enrich
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
        _t_before_gap = time.perf_counter()
        local_append_suggestion_reason(item)
        local_apply_suggestion_gap(item)
        _t_after_gap = time.perf_counter()
        gap_time_total += _t_after_gap - _t_before_gap
    perf_trace.stamp(
        "assignment_flow.enrich_breakdown",
        enrich_ms=round(enrich_time_total * 1000, 2),
        gap_ms=round(gap_time_total * 1000, 2),
        other_ms=round(other_time_total * 1000, 2),
    )
    perf_trace.stamp("assignment_flow.stage", stage="enriched", count=len(session.filtered_items))
    performance_flow.annotate_items(
        session.filtered_items,
        inventory_lookup=session.inventory_lookup,
    )
    perf_trace.stamp("assignment_flow.stage", stage="performance_annotated")

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
    perf_trace.stamp("assignment_flow.stage", stage="release_annotated")
    return True
