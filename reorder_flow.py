import math

import item_workflow
import performance_flow
import perf_trace
import storage
from rules import looks_like_hardware_pack_item, looks_like_reel_item


def _recalculate_item(app, item, *, annotate_release):
    try:
        app._recalculate_item(item, annotate_release=annotate_release)
    except TypeError:
        app._recalculate_item(item)


def get_cycle_weeks(app):
    cycle_var = getattr(app, "var_reorder_cycle", None)
    cycle = cycle_var.get() if cycle_var and hasattr(cycle_var, "get") else "Biweekly"
    return {"Weekly": 1, "Biweekly": 2, "Monthly": 4}.get(cycle, 2)


def base_suggest_min_max_from_annual_sales(annual_sales, cycle_weeks):
    weekly = annual_sales / 52
    sug_min = max(1, math.ceil(weekly * cycle_weeks))
    sug_max = max(sug_min + 1, math.ceil(weekly * cycle_weeks * 2))
    return sug_min, sug_max


def min_annual_sales_threshold(app, default=3):
    value = getattr(app, "min_annual_sales_for_suggestions", default)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def suggestion_source_label(source_code):
    return {
        "none": "No suggestion",
        "x4_mo12_sales": "X4 12-month sales",
        "detailed_sales_fallback": "Detailed sales fallback",
        "detailed_sales_applied": "Detailed sales (applied)",
        "provided": "Provided",
    }.get(source_code or "none", source_code or "none")


def tune_detailed_sales_fallback_suggestion(stats, sug_min, sug_max):
    shape = performance_flow.classify_detailed_sales_shape(stats).get("detailed_sales_shape", "")
    if shape in ("sparse_transactions", "lumpy_bulk"):
        return None, None

    if shape == "steady_repeat":
        txn_floor = max(
            int(math.ceil(float(stats.get("avg_units_per_transaction", 0) or 0))),
            int(math.ceil(float(stats.get("median_units_per_transaction", 0) or 0))),
        )
        if txn_floor > 0:
            sug_min = max(sug_min, txn_floor)
            sug_max = max(sug_max, sug_min + txn_floor)
    return sug_min, sug_max


def detailed_sales_suggest_min_max(app, key, min_annual_sales_for_suggestions=None):
    threshold = min_annual_sales_for_suggestions
    if threshold is None:
        threshold = min_annual_sales_threshold(app)
    stats = (getattr(app, "detailed_sales_stats_lookup", {}) or {}).get(key, {})
    annual_sales = stats.get("annualized_qty_sold", 0) or 0
    if not annual_sales or annual_sales <= 0:
        return None, None
    if annual_sales < threshold:
        return None, None
    get_cycle = getattr(app, "_get_cycle_weeks", None)
    weeks = get_cycle() if callable(get_cycle) else get_cycle_weeks(app)
    sug_min, sug_max = base_suggest_min_max_from_annual_sales(annual_sales, weeks)
    return tune_detailed_sales_fallback_suggestion(stats, sug_min, sug_max)


def suggest_min_max_with_source(app, key, min_annual_sales_for_suggestions):
    inv = app.inventory_lookup.get(key, {})
    annual_sales = inv.get("mo12_sales", 0)
    source = "x4_mo12_sales"
    use_detailed_fallback = False
    stats = {}
    if not annual_sales or annual_sales <= 0:
        stats = (getattr(app, "detailed_sales_stats_lookup", {}) or {}).get(key, {})
        annual_sales = stats.get("annualized_qty_sold", 0) or 0
        use_detailed_fallback = bool(annual_sales and annual_sales > 0)
        source = "detailed_sales_fallback" if use_detailed_fallback else "none"
    if not annual_sales or annual_sales <= 0:
        return None, None, "none"
    if annual_sales < min_annual_sales_for_suggestions:
        return None, None, "none"
    get_cycle = getattr(app, "_get_cycle_weeks", None)
    weeks = get_cycle() if callable(get_cycle) else get_cycle_weeks(app)
    sug_min, sug_max = base_suggest_min_max_from_annual_sales(annual_sales, weeks)
    if use_detailed_fallback:
        sug_min, sug_max = tune_detailed_sales_fallback_suggestion(stats, sug_min, sug_max)
        if sug_min is None and sug_max is None:
            return None, None, "none"
        receipt_balance = receipt_sales_balance_for_key(app, key)
        if receipt_balance.get("receipt_sales_balance") == "receipt_heavy":
            return None, None, "none"
    return sug_min, sug_max, source


def compare_suggestion_pairs(active_pair, detailed_pair):
    active_min, active_max = active_pair
    detailed_min, detailed_max = detailed_pair
    if detailed_min is None and detailed_max is None:
        return "no_detailed"
    if active_min is None and active_max is None:
        return "detailed_only"
    if (active_min, active_max) == (detailed_min, detailed_max):
        return "aligned"
    if (
        isinstance(active_min, (int, float))
        and isinstance(active_max, (int, float))
        and isinstance(detailed_min, (int, float))
        and isinstance(detailed_max, (int, float))
    ):
        if detailed_min >= active_min and detailed_max >= active_max:
            return "detailed_higher"
        if detailed_min <= active_min and detailed_max <= active_max:
            return "detailed_lower"
    return "different"


def suggestion_compare_label(compare_code):
    return {
        "no_detailed": "No detailed comparison",
        "detailed_only": "Detailed only",
        "aligned": "Aligned",
        "detailed_higher": "Detailed higher",
        "detailed_lower": "Detailed lower",
        "different": "Different",
    }.get(compare_code, compare_code or "")


def suggestion_disagreement_metrics(active_pair, detailed_pair):
    active_min, active_max = active_pair
    detailed_min, detailed_max = detailed_pair
    metrics = {
        "ratio": None,
        "max_gap": None,
        "material": False,
    }
    if not (
        isinstance(active_min, (int, float))
        and isinstance(active_max, (int, float))
        and isinstance(detailed_min, (int, float))
        and isinstance(detailed_max, (int, float))
    ):
        return metrics
    max_gap = max(abs(float(detailed_min) - float(active_min)), abs(float(detailed_max) - float(active_max)))
    metrics["max_gap"] = max_gap
    positive_values = [value for value in (active_max, detailed_max, active_min, detailed_min) if isinstance(value, (int, float)) and value > 0]
    if len(positive_values) >= 2:
        low = min(positive_values)
        high = max(positive_values)
        if low > 0:
            metrics["ratio"] = high / low
    ratio = metrics["ratio"]
    metrics["material"] = bool((ratio is not None and ratio >= 2.0) or max_gap >= 6.0)
    return metrics


def apply_suggestion_context(app, item, key, active_pair=None, min_annual_sales_for_suggestions=None, active_source=None):
    if active_pair is None:
        active_min, active_max, active_source = suggest_min_max_with_source(
            app,
            key,
            min_annual_sales_for_suggestions or min_annual_sales_threshold(app),
        )
    else:
        active_min, active_max = active_pair
    if not active_source:
        active_source = "provided" if active_pair is not None else "none"
    detailed_min, detailed_max = detailed_sales_suggest_min_max(
        app,
        key,
        min_annual_sales_for_suggestions=min_annual_sales_for_suggestions,
    )
    # Record whether the detailed fallback was suppressed by receipt_heavy so that
    # downstream logic (apply_suggestion_gap_review_state) can distinguish
    # "no X4 suggestion + receipt_heavy" from "no X4 suggestion, safe to apply".
    if active_source == "none" and (detailed_min is not None or detailed_max is not None):
        receipt_balance = receipt_sales_balance_for_key(app, key)
        item["detailed_fallback_suppressed_reason"] = receipt_balance.get("receipt_sales_balance", "")
    else:
        item["detailed_fallback_suppressed_reason"] = ""
    item["suggested_min"] = active_min
    item["suggested_max"] = active_max
    item["suggested_source"] = active_source
    item["suggested_source_label"] = suggestion_source_label(active_source)
    item["detailed_suggested_min"] = detailed_min
    item["detailed_suggested_max"] = detailed_max
    compare_code = compare_suggestion_pairs((active_min, active_max), (detailed_min, detailed_max))
    item["detailed_suggestion_compare"] = compare_code
    item["detailed_suggestion_compare_label"] = suggestion_compare_label(compare_code)
    item["detailed_suggestion_gap"] = compare_code not in ("", "no_detailed", "aligned")
    disagreement = suggestion_disagreement_metrics((active_min, active_max), (detailed_min, detailed_max))
    item["detailed_suggestion_ratio"] = disagreement["ratio"]
    item["detailed_suggestion_max_gap"] = disagreement["max_gap"]
    item["material_suggestion_disagreement"] = bool(
        disagreement["material"] and compare_code not in ("", "no_detailed", "aligned")
    )
    return active_min, active_max


def append_suggestion_comparison_reason(item):
    detailed_min = item.get("detailed_suggested_min")
    detailed_max = item.get("detailed_suggested_max")
    compare_code = item.get("detailed_suggestion_compare", "")
    if compare_code in ("", "no_detailed", "aligned"):
        return
    base_why = str(item.get("core_why", item.get("why", "")) or "").strip()
    if not base_why:
        return
    if compare_code == "detailed_only":
        detail = f"Detailed sales-only suggestion: {detailed_min if detailed_min is not None else '-'} / {detailed_max if detailed_max is not None else '-'}"
    else:
        detail = (
            f"Detailed sales comparison: active {item.get('suggested_min', '-') if item.get('suggested_min') is not None else '-'} / "
            f"{item.get('suggested_max', '-') if item.get('suggested_max') is not None else '-'} vs "
            f"detailed {detailed_min if detailed_min is not None else '-'} / {detailed_max if detailed_max is not None else '-'} "
            f"({suggestion_compare_label(compare_code).lower()})"
        )
    if detail in base_why:
        return
    merged = f"{base_why} | {detail}"
    item["core_why"] = merged
    item["why"] = merged


def suggest_min_max(app, key, min_annual_sales_for_suggestions):
    sug_min, sug_max, _source = suggest_min_max_with_source(app, key, min_annual_sales_for_suggestions)
    return sug_min, sug_max


def receipt_history_for_key(app, key):
    return dict((getattr(app, "receipt_history_lookup", {}) or {}).get(key, {}) or {})


def sales_history_for_key(app, key):
    """v0.8.12: per-session index replaces the O(n) linear scan."""
    cache = getattr(app, "_sales_history_index_cache", None)
    if cache is None:
        cache = {}
        for entry in getattr(app, "sales_items", None) or ():
            if not isinstance(entry, dict):
                continue
            k = (entry.get("line_code", ""), entry.get("item_code", ""))
            if k not in cache:
                cache[k] = entry
        app._sales_history_index_cache = cache
    entry = cache.get(key)
    return dict(entry) if entry else {}


def receipt_sales_balance_for_key(app, key):
    sales = sales_history_for_key(app, key)
    receipt_history = receipt_history_for_key(app, key)
    detailed_stats = dict((getattr(app, "detailed_sales_stats_lookup", {}) or {}).get(key, {}) or {})
    return performance_flow.classify_receipt_sales_balance({
        "qty_sold": sales.get("qty_sold", 0),
        "qty_received": sales.get("qty_received", 0),
        "receipt_count": receipt_history.get("receipt_count", 0),
        "avg_units_per_receipt": receipt_history.get("avg_units_per_receipt"),
        "avg_units_per_transaction": (
            detailed_stats.get("avg_units_per_transaction")
            if detailed_stats.get("avg_units_per_transaction") is not None
            else sales.get("avg_units_per_transaction")
        ),
    })


def _build_description_index(app):
    """Single-pass scan that builds a (line_code, item_code) → description
    index from every loaded source.

    v0.8.12: `_description_for_key` used to scan every sales item /
    receipt / open PO row linearly for every key it was asked about.
    On the 63K-item dataset with 59K lookups that was O(n²) ≈ 18
    billion dict comparisons and cost ~17 seconds inside
    `receipt_pack_size_for_key`.  One upfront O(n) sweep + O(1)
    lookups per query fixes it.
    """
    index = {}
    for attr in (
        "sales_items",
        "receipts_items",
        "open_po_items",
        "suspended_items",
        "detailed_sales_rows",
    ):
        collection = getattr(app, attr, None) or ()
        for entry in collection:
            if not isinstance(entry, dict):
                continue
            lc = entry.get("line_code", "")
            ic = entry.get("item_code", "")
            if not ic:
                continue
            key = (lc, ic)
            if key in index:
                continue
            description = entry.get("description", "")
            if description:
                text = str(description).strip()
                if text:
                    index[key] = text
    susp_lookup = getattr(app, "suspended_lookup", None) or {}
    for key, entries in susp_lookup.items():
        if key in index:
            continue
        for entry in entries or ():
            if not isinstance(entry, dict):
                continue
            description = entry.get("description", "")
            if description:
                text = str(description).strip()
                if text:
                    index[key] = text
                    break
    return index


def _description_for_key(app, key):
    inv = (getattr(app, "inventory_lookup", {}) or {}).get(key, {}) or {}
    description = str(inv.get("description", "") or "").strip()
    if description:
        return description
    # v0.8.12: lazy per-session description index — one O(n) sweep on
    # first call, O(1) lookup thereafter.  Eliminates the O(n²)
    # behavior that cost 17+ seconds inside the candidate-build loop
    # on the operator's 63K-item dataset.
    cache = getattr(app, "_description_index_cache", None)
    if cache is None:
        cache = _build_description_index(app)
        app._description_index_cache = cache
    return cache.get(key, "")


def receipt_vendor_evidence(app, key):
    history = receipt_history_for_key(app, key)
    candidates = receipt_vendor_candidates(app, key)
    return {
        "primary_vendor": str(history.get("primary_vendor", "") or "").strip().upper(),
        "most_recent_vendor": str(history.get("most_recent_vendor", "") or "").strip().upper(),
        "vendor_confidence": str(history.get("vendor_confidence", "none") or "none").strip().lower(),
        "vendor_confidence_reason": str(history.get("vendor_confidence_reason", "") or "").strip(),
        "vendor_ambiguous": bool(history.get("vendor_ambiguous")),
        "primary_vendor_qty_share": float(history.get("primary_vendor_qty_share", 0.0) or 0.0),
        "primary_vendor_receipt_share": float(history.get("primary_vendor_receipt_share", 0.0) or 0.0),
        "receipt_count": int(history.get("receipt_count", 0) or 0),
        "qty_received_total": int(history.get("qty_received_total", 0) or 0),
        "first_receipt_date": str(history.get("first_receipt_date", "") or "").strip(),
        "last_receipt_date": str(history.get("last_receipt_date", "") or "").strip(),
        "avg_units_per_receipt": history.get("avg_units_per_receipt"),
        "median_units_per_receipt": history.get("median_units_per_receipt"),
        "max_units_per_receipt": history.get("max_units_per_receipt"),
        "avg_days_between_receipts": history.get("avg_days_between_receipts"),
        "potential_vendor": str(history.get("primary_vendor", "") or "").strip().upper(),
        "potential_vendor_source": "receipt_history" if history.get("primary_vendor") else "",
        "receipt_pack_candidate": history.get("receipt_pack_candidate"),
        "receipt_pack_candidates": list(history.get("receipt_pack_candidates", []) or []),
        "receipt_pack_confidence": str(history.get("receipt_pack_confidence", "none") or "none").strip().lower(),
        "receipt_pack_candidate_share": float(history.get("receipt_pack_candidate_share", 0.0) or 0.0),
        "vendor_candidates": candidates,
    }


def receipt_pack_size_for_key(app, key, *, minimum_confidence="high"):
    # v0.8.12: fast short-circuit.  `receipt_vendor_evidence`,
    # `_description_for_key`, and the classification calls below are
    # each tens of microseconds.  On the real 63K-candidate dataset
    # this function ran 59K times and burned 17.6 seconds in the
    # candidate-build loop.  The vast majority of items don't have
    # receipt history for their specific key — an O(1) dict check
    # before any real work eliminates 95%+ of the cost.
    receipt_history = getattr(app, "receipt_history_lookup", None) or {}
    if key not in receipt_history:
        return None
    evidence = receipt_vendor_evidence(app, key)
    confidence = evidence["receipt_pack_confidence"]
    candidate = evidence["receipt_pack_candidate"]
    if candidate is None:
        return None
    if minimum_confidence == "high" and confidence != "high":
        return None
    if minimum_confidence == "medium" and confidence not in ("high", "medium"):
        return None
    # `dict((...).get(key, {}) or {})` was a per-call copy that
    # contributed a meaningful chunk on 59K calls.  Read the inv dict
    # directly — the classifiers below only read fields, never mutate.
    inv = (getattr(app, "inventory_lookup", {}) or {}).get(key) or {}
    description = _description_for_key(app, key)
    item_context = {
        "line_code": key[0],
        "item_code": key[1],
        "description": description,
    }
    if not (
        looks_like_reel_item(item_context, inv)
        or looks_like_hardware_pack_item(item_context, inv)
    ):
        return None
    return candidate


def pack_size_source_label(source_code):
    return {
        "": "",
        "rule": "Saved Rule",
        "rule_exact_qty": "Saved Exact Qty Override",
        "x4_exact": "X4 Exact",
        "x4_item": "X4 Item Fallback",
        "x4_item_fallback": "X4 Generic Fallback",
        "receipt_history": "Receipt History",
    }.get(source_code or "", source_code or "")


def apply_receipt_vendor_context(app, item, key):
    evidence = receipt_vendor_evidence(app, key)
    item["receipt_primary_vendor"] = evidence["primary_vendor"]
    item["receipt_most_recent_vendor"] = evidence["most_recent_vendor"]
    item["receipt_vendor_confidence"] = evidence["vendor_confidence"]
    item["receipt_vendor_confidence_reason"] = evidence["vendor_confidence_reason"]
    item["receipt_vendor_ambiguous"] = evidence["vendor_ambiguous"]
    item["receipt_vendor_qty_share"] = evidence["primary_vendor_qty_share"]
    item["receipt_vendor_receipt_share"] = evidence["primary_vendor_receipt_share"]
    item["receipt_count"] = evidence["receipt_count"]
    item["receipt_qty_total"] = evidence["qty_received_total"]
    item["first_receipt_date"] = evidence["first_receipt_date"]
    item["last_receipt_date_loaded"] = evidence["last_receipt_date"]
    item["avg_units_per_receipt"] = evidence["avg_units_per_receipt"]
    item["median_units_per_receipt"] = evidence["median_units_per_receipt"]
    item["max_units_per_receipt"] = evidence["max_units_per_receipt"]
    item["avg_days_between_receipts"] = evidence["avg_days_between_receipts"]
    item["potential_vendor"] = evidence["potential_vendor"]
    item["potential_vendor_source"] = evidence["potential_vendor_source"]
    item["potential_pack_size"] = evidence["receipt_pack_candidate"]
    item["potential_pack_candidates"] = list(evidence["receipt_pack_candidates"])
    item["potential_pack_confidence"] = evidence["receipt_pack_confidence"]
    item["potential_pack_share"] = evidence["receipt_pack_candidate_share"]
    item["receipt_vendor_candidates"] = list(evidence["vendor_candidates"])
    return evidence


def receipt_vendor_candidates(app, key):
    history = receipt_history_for_key(app, key)
    candidates = []
    for vendor in list(history.get("vendor_candidates", []) or []):
        normalized = str(vendor or "").strip().upper()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    primary_vendor = str(history.get("primary_vendor", "") or "").strip().upper()
    if primary_vendor and primary_vendor not in candidates:
        candidates.insert(0, primary_vendor)
    return candidates


def default_vendor_for_key(app, key):
    evidence = receipt_vendor_evidence(app, key)
    if evidence["primary_vendor"]:
        return evidence["primary_vendor"]
    inv = app.inventory_lookup.get(key, {})
    supplier = (inv.get("supplier", "") or "").strip().upper()
    return supplier or ""


def _normalize_demand_signal(raw_demand, cycle_weeks, sales_span_days):
    """Normalize a raw period-total demand signal down to one reorder cycle's worth.

    E.g. 40 sold over 365 days on a weekly (7-day) cycle -> 40 * 7 / 365 ~= 0.77 -> 1.
    Returns the raw value unchanged when span_days is unknown/zero.

    Intentionally does NOT floor at 1 — items that normalize below 0.5 round to
    zero demand and are dropped from suggestions unless X4 shows they are below
    their set minimum.  This prevents one-off sales from a long export window from
    producing spurious reorder suggestions.
    """
    if not sales_span_days or sales_span_days <= 0:
        return raw_demand
    cycle_days = cycle_weeks * 7
    normalized = raw_demand * cycle_days / sales_span_days
    return round(normalized) if raw_demand > 0 else 0


def _rebuild_bulk_metadata_after_inplace_recalc(app):
    """Backwards-compat shim — the canonical helper now lives in ui_bulk."""
    import ui_bulk
    ui_bulk.rebuild_bulk_metadata_after_inplace_recalc(app)


@perf_trace.timed("reorder_flow.refresh_suggestions")
def refresh_suggestions(app):
    """Recalculate suggestions when the reorder cycle changes.

    Explicitly stamps suggested_min/suggested_max AND a cycle-normalized
    demand_signal onto each item before calling _recalculate_item, so that
    enrich_item -> calculate_raw_need uses values appropriate to the new cycle.
    """
    span_days = getattr(app, "sales_span_days", None)
    get_cycle = getattr(app, "_get_cycle_weeks", None)
    cycle_weeks = get_cycle() if callable(get_cycle) else 2
    suggest = getattr(app, "_suggest_min_max", None)
    for item in app.filtered_items:
        if callable(suggest):
            key = (item["line_code"], item["item_code"])
            sug_min, sug_max = suggest(key)
            item["suggested_min"] = sug_min
            item["suggested_max"] = sug_max
        item["reorder_cycle_weeks"] = cycle_weeks
        raw_eff_sales = item.get("effective_qty_sold", item.get("qty_sold", 0))
        raw_eff_susp = item.get("effective_qty_suspended", item.get("qty_suspended", 0))
        raw_demand = raw_eff_sales + raw_eff_susp
        item["demand_signal"] = _normalize_demand_signal(raw_demand, cycle_weeks, span_days)
        item["gross_need"] = item["demand_signal"]
        _recalculate_item(app, item, annotate_release=False)
    for item in app.assigned_items:
        app._sync_review_item_to_filtered(item)
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()
    _rebuild_bulk_metadata_after_inplace_recalc(app)
    app._apply_bulk_filter()


@perf_trace.timed("reorder_flow.normalize_items_to_cycle")
def normalize_items_to_cycle(app):
    """Normalize demand_signal on all filtered_items to match the current reorder cycle.

    v0.8.10: cycle normalization now runs inside
    `assignment_flow.prepare_assignment_session`'s single candidate-build
    loop, so this function is a **redundant second pass on fresh session
    loads** — it used to take ~23 s on the 63K-item dataset because it
    re-enriches every item via `_recalculate_item`.  We detect the
    "fresh load" case by checking whether the cycle has actually
    changed since prepare_assignment_session ran; if not, this is a
    no-op that completes in < 1 ms.

    The full recalculation loop is still needed when the operator
    flips the Reorder Cycle dropdown mid-session — in that case the
    previously-stored `reorder_cycle_weeks` on each item is stale and
    we have to re-enrich.
    """
    cycle_weeks = app._get_cycle_weeks()
    items = getattr(app, "filtered_items", None) or []
    if items:
        sample = items[0]
        if sample.get("reorder_cycle_weeks") == cycle_weeks:
            # Fast path: prepare_assignment_session already normalized
            # to this cycle (v0.8.10).  No re-enrich needed — the bulk
            # metadata is already in sync.  This saves ~23 s on the
            # real 63K dataset.
            return
    span_days = getattr(app, "sales_span_days", None)

    for item in items:
        item["reorder_cycle_weeks"] = cycle_weeks
        raw_eff_sales = item.get("effective_qty_sold", item.get("qty_sold", 0))
        raw_eff_susp = item.get("effective_qty_suspended", item.get("qty_suspended", 0))
        raw_demand = raw_eff_sales + raw_eff_susp
        item["demand_signal"] = _normalize_demand_signal(raw_demand, cycle_weeks, span_days)
        item["gross_need"] = item["demand_signal"]
        key = (item["line_code"], item["item_code"])
        sug_min, sug_max = app._suggest_min_max(key)
        item["suggested_min"] = sug_min
        item["suggested_max"] = sug_max
        _recalculate_item(app, item, annotate_release=False)
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()
    _rebuild_bulk_metadata_after_inplace_recalc(app)


@perf_trace.timed("reorder_flow.refresh_recent_orders")
def refresh_recent_orders(app):
    try:
        days = app.var_lookback_days.get()
    except Exception:
        days = 14
    app.recent_orders = storage.get_recent_orders(app._data_path("order_history"), days)
    for item in getattr(app, "filtered_items", []) or []:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        item_workflow.apply_recent_order_context(item, app.recent_orders.get(key, []))
        _recalculate_item(app, item, annotate_release=False)
    for item in getattr(app, "assigned_items", []) or []:
        key = (item.get("line_code", ""), item.get("item_code", ""))
        item_workflow.apply_recent_order_context(item, app.recent_orders.get(key, []))
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()
    _rebuild_bulk_metadata_after_inplace_recalc(app)
    app._apply_bulk_filter()
