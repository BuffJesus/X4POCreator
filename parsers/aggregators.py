"""Aggregation functions: summary builders, receipt history lookup,
detailed sales stats, and the fused pair-aggregates pass."""

import math
from collections import Counter
from statistics import median

import perf_trace
from parsers.dates import parse_x4_date
from parsers.normalize import _coerce_int, _normalize_vendor_code


def _iter_detailed_part_sales_csv(path):
    import parsers
    return parsers._iter_detailed_part_sales_csv(path)


def _iter_received_parts_detail_csv(path):
    import parsers
    return parsers._iter_received_parts_detail_csv(path)


def parse_detailed_sales_date_range(sales_rows, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    dates = []
    for row in sales_rows or []:
        sale_dt = parse_date(row.get("sale_date", "")) if row.get("sale_date") else None
        if sale_dt is not None:
            dates.append(sale_dt)
    if not dates:
        return None, None
    return min(dates), max(dates)


def build_sales_receipt_summary(sales_rows, receipt_rows):
    agg = {}
    for row in sales_rows or []:
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        entry = agg.setdefault(key, {
            "line_code": key[0],
            "item_code": key[1],
            "description": "",
            "qty_received": 0,
            "qty_sold": 0,
        })
        entry["qty_sold"] += max(0, _coerce_int(row.get("qty_sold", 0)))
        if not entry["description"] and row.get("description"):
            entry["description"] = row.get("description", "")
    for row in receipt_rows or []:
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        entry = agg.setdefault(key, {
            "line_code": key[0],
            "item_code": key[1],
            "description": "",
            "qty_received": 0,
            "qty_sold": 0,
        })
        entry["qty_received"] += max(0, _coerce_int(row.get("qty_received", 0)))
        if not entry["description"] and row.get("description"):
            entry["description"] = row.get("description", "")
    return list(agg.values())


def build_receipt_history_lookup(receipt_rows, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    history = {}
    for row in receipt_rows or []:
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        vendor = _normalize_vendor_code(row.get("vendor", ""))
        qty_received = max(0, _coerce_int(row.get("qty_received", 0)))
        receipt_date = str(row.get("receipt_date", "") or "").strip()
        receipt_dt = parse_date(receipt_date) if receipt_date else None
        entry = history.setdefault(key, {
            "last_receipt_date": "",
            "primary_vendor": "",
            "vendor_candidates": [],
            "most_recent_vendor": "",
            "vendor_confidence": "none",
            "vendor_confidence_reason": "",
            "vendor_ambiguous": False,
            "primary_vendor_qty_share": 0.0,
            "primary_vendor_receipt_share": 0.0,
            "receipt_count": 0,
            "qty_received_total": 0,
            "first_receipt_date": "",
            "avg_units_per_receipt": None,
            "median_units_per_receipt": None,
            "max_units_per_receipt": None,
            "avg_days_between_receipts": None,
            "vendors": {},
            "_receipt_quantity_counter": Counter(),
            "_receipt_dates": set(),
        })
        entry["receipt_count"] += 1
        entry["qty_received_total"] += qty_received
        entry["_receipt_quantity_counter"][qty_received] += 1
        if receipt_dt is not None:
            iso_date = receipt_dt.date().isoformat()
            entry["_receipt_dates"].add(receipt_dt.date())
            if not entry["first_receipt_date"] or iso_date < entry["first_receipt_date"]:
                entry["first_receipt_date"] = iso_date
            if iso_date > entry["last_receipt_date"]:
                entry["last_receipt_date"] = iso_date
                entry["most_recent_vendor"] = vendor
        vendor_entry = entry["vendors"].setdefault(vendor, {
            "qty_received": 0,
            "receipt_count": 0,
            "last_receipt_date": "",
        })
        vendor_entry["qty_received"] += qty_received
        vendor_entry["receipt_count"] += 1
        if receipt_dt is not None:
            iso_date = receipt_dt.date().isoformat()
            if iso_date > vendor_entry["last_receipt_date"]:
                vendor_entry["last_receipt_date"] = iso_date
    for entry in history.values():
        ranked_vendors = sorted(
            entry["vendors"].items(),
            key=lambda vendor_row: (
                vendor_row[1].get("last_receipt_date", ""),
                vendor_row[1].get("qty_received", 0),
                vendor_row[1].get("receipt_count", 0),
                vendor_row[0],
            ),
            reverse=True,
        )
        entry["vendor_candidates"] = [vendor for vendor, _info in ranked_vendors if vendor]
        entry["primary_vendor"] = entry["vendor_candidates"][0] if entry["vendor_candidates"] else ""
        total_qty = sum(max(0, info.get("qty_received", 0) or 0) for _vendor, info in ranked_vendors)
        total_receipts = sum(max(0, info.get("receipt_count", 0) or 0) for _vendor, info in ranked_vendors)
        if ranked_vendors:
            primary_info = ranked_vendors[0][1]
            qty_share = (float(primary_info.get("qty_received", 0) or 0) / float(total_qty)) if total_qty > 0 else 0.0
            receipt_share = (
                float(primary_info.get("receipt_count", 0) or 0) / float(total_receipts)
            ) if total_receipts > 0 else 0.0
            entry["primary_vendor_qty_share"] = qty_share
            entry["primary_vendor_receipt_share"] = receipt_share
            vendor_count = len(entry["vendor_candidates"])
            if vendor_count <= 1:
                entry["vendor_confidence"] = "high"
                entry["vendor_confidence_reason"] = "single_vendor_history"
            elif (
                qty_share >= 0.80
                and receipt_share >= 0.60
                and entry.get("most_recent_vendor", "") == entry["primary_vendor"]
            ):
                entry["vendor_confidence"] = "high"
                entry["vendor_confidence_reason"] = "dominant_recent_vendor"
            elif qty_share >= 0.60 or receipt_share >= 0.60:
                entry["vendor_confidence"] = "medium"
                entry["vendor_confidence_reason"] = "dominant_but_mixed_vendor"
            else:
                entry["vendor_confidence"] = "low"
                entry["vendor_confidence_reason"] = "mixed_vendor_history"
            entry["vendor_ambiguous"] = vendor_count > 1 and entry["vendor_confidence"] != "high"
        quantity_counter = entry.pop("_receipt_quantity_counter", Counter())
        quantities = sorted(quantity_counter.elements())
        unique_dates = sorted(entry.pop("_receipt_dates", set()))
        entry["avg_units_per_receipt"] = (
            float(entry["qty_received_total"]) / float(entry["receipt_count"])
            if entry["receipt_count"] > 0 else None
        )
        entry["median_units_per_receipt"] = median(quantities) if quantities else None
        entry["max_units_per_receipt"] = max(quantities) if quantities else None
        positive_receipt_lots = [qty for qty in quantities if qty > 1]
        lot_counter = Counter(positive_receipt_lots)
        ranked_lots = sorted(lot_counter.items(), key=lambda item: (-item[1], -item[0]))
        entry["receipt_pack_candidates"] = [qty for qty, _count in ranked_lots[:3]]
        entry["receipt_pack_candidate"] = entry["receipt_pack_candidates"][0] if entry["receipt_pack_candidates"] else None
        if ranked_lots and entry["receipt_count"] > 0:
            _top_qty, top_count = ranked_lots[0]
            candidate_share = float(top_count) / float(entry["receipt_count"])
            entry["receipt_pack_candidate_share"] = candidate_share
            if top_count >= 2 and candidate_share >= 0.50:
                entry["receipt_pack_confidence"] = "high"
            elif top_count >= 2 or candidate_share >= 0.34:
                entry["receipt_pack_confidence"] = "medium"
            else:
                entry["receipt_pack_confidence"] = "low"
        else:
            entry["receipt_pack_candidate_share"] = 0.0
            entry["receipt_pack_confidence"] = "none"
        if len(unique_dates) >= 2:
            gaps = []
            for idx in range(1, len(unique_dates)):
                gap_days = (unique_dates[idx] - unique_dates[idx - 1]).days
                if gap_days >= 0:
                    gaps.append(gap_days)
            entry["avg_days_between_receipts"] = (
                float(sum(gaps)) / float(len(gaps)) if gaps else None
            )
    return history


def build_detailed_sales_stats_lookup(sales_rows, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    stats_lookup = {}
    for row in sales_rows or []:
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        qty_sold = max(0, _coerce_int(row.get("qty_sold", 0)))
        sale_date_raw = str(row.get("sale_date", "") or "").strip()
        sale_dt = parse_date(sale_date_raw) if sale_date_raw else None
        entry = stats_lookup.setdefault(key, {
            "transaction_count": 0,
            "qty_sold_total": 0,
            "_sale_dates": set(),
            "_quantity_counter": Counter(),
            "first_sale_date": "",
            "last_sale_date": "",
            "annualized_qty_sold": None,
        })
        entry["transaction_count"] += 1
        entry["qty_sold_total"] += qty_sold
        entry["_quantity_counter"][qty_sold] += 1
        if sale_dt is not None:
            iso_date = sale_dt.date().isoformat()
            entry["_sale_dates"].add(sale_dt.date())
            if not entry["first_sale_date"] or iso_date < entry["first_sale_date"]:
                entry["first_sale_date"] = iso_date
            if iso_date > entry["last_sale_date"]:
                entry["last_sale_date"] = iso_date

    for entry in stats_lookup.values():
        quantity_counter = entry.pop("_quantity_counter", Counter())
        quantities = sorted(quantity_counter.elements())
        unique_dates = sorted(entry.pop("_sale_dates", set()))
        entry["sale_day_count"] = len(unique_dates)
        entry["avg_units_per_transaction"] = (
            float(entry["qty_sold_total"]) / float(entry["transaction_count"])
            if entry["transaction_count"] > 0 else None
        )
        entry["median_units_per_transaction"] = median(quantities) if quantities else None
        entry["max_units_per_transaction"] = max(quantities) if quantities else None
        if len(unique_dates) >= 2:
            gaps = []
            for idx in range(1, len(unique_dates)):
                gap_days = (unique_dates[idx] - unique_dates[idx - 1]).days
                if gap_days >= 0:
                    gaps.append(gap_days)
            entry["avg_days_between_sales"] = (
                float(sum(gaps)) / float(len(gaps)) if gaps else None
            )
        else:
            entry["avg_days_between_sales"] = None
    return stats_lookup


def _finalize_streamed_receipt_history(history):
    for entry in history.values():
        ranked_vendors = sorted(
            entry["vendors"].items(),
            key=lambda vendor_row: (
                vendor_row[1].get("last_receipt_date", ""),
                vendor_row[1].get("qty_received", 0),
                vendor_row[1].get("receipt_count", 0),
                vendor_row[0],
            ),
            reverse=True,
        )
        entry["vendor_candidates"] = [vendor for vendor, _info in ranked_vendors if vendor]
        entry["primary_vendor"] = entry["vendor_candidates"][0] if entry["vendor_candidates"] else ""
        total_qty = sum(max(0, info.get("qty_received", 0) or 0) for _vendor, info in ranked_vendors)
        total_receipts = sum(max(0, info.get("receipt_count", 0) or 0) for _vendor, info in ranked_vendors)
        if ranked_vendors:
            primary_info = ranked_vendors[0][1]
            qty_share = (float(primary_info.get("qty_received", 0) or 0) / float(total_qty)) if total_qty > 0 else 0.0
            receipt_share = (
                float(primary_info.get("receipt_count", 0) or 0) / float(total_receipts)
            ) if total_receipts > 0 else 0.0
            entry["primary_vendor_qty_share"] = qty_share
            entry["primary_vendor_receipt_share"] = receipt_share
            vendor_count = len(entry["vendor_candidates"])
            if vendor_count <= 1:
                entry["vendor_confidence"] = "high"
                entry["vendor_confidence_reason"] = "single_vendor_history"
            elif (
                qty_share >= 0.80
                and receipt_share >= 0.60
                and entry.get("most_recent_vendor", "") == entry["primary_vendor"]
            ):
                entry["vendor_confidence"] = "high"
                entry["vendor_confidence_reason"] = "dominant_recent_vendor"
            elif qty_share >= 0.60 or receipt_share >= 0.60:
                entry["vendor_confidence"] = "medium"
                entry["vendor_confidence_reason"] = "dominant_but_mixed_vendor"
            else:
                entry["vendor_confidence"] = "low"
                entry["vendor_confidence_reason"] = "mixed_vendor_history"
            entry["vendor_ambiguous"] = vendor_count > 1 and entry["vendor_confidence"] != "high"
        quantity_counter = entry.pop("_receipt_quantity_counter", Counter())
        quantities = sorted(quantity_counter.elements())
        unique_dates = sorted(entry.pop("_receipt_dates", set()))
        entry["avg_units_per_receipt"] = (
            float(entry["qty_received_total"]) / float(entry["receipt_count"])
            if entry["receipt_count"] > 0 else None
        )
        entry["median_units_per_receipt"] = median(quantities) if quantities else None
        entry["max_units_per_receipt"] = max(quantities) if quantities else None
        positive_receipt_lots = [qty for qty in quantities if qty > 1]
        lot_counter = Counter(positive_receipt_lots)
        ranked_lots = sorted(lot_counter.items(), key=lambda item: (-item[1], -item[0]))
        entry["receipt_pack_candidates"] = [qty for qty, _count in ranked_lots[:3]]
        entry["receipt_pack_candidate"] = entry["receipt_pack_candidates"][0] if entry["receipt_pack_candidates"] else None
        if ranked_lots and entry["receipt_count"] > 0:
            _top_qty, top_count = ranked_lots[0]
            candidate_share = float(top_count) / float(entry["receipt_count"])
            entry["receipt_pack_candidate_share"] = candidate_share
            if top_count >= 2 and candidate_share >= 0.50:
                entry["receipt_pack_confidence"] = "high"
            elif top_count >= 2 or candidate_share >= 0.34:
                entry["receipt_pack_confidence"] = "medium"
            else:
                entry["receipt_pack_confidence"] = "low"
        else:
            entry["receipt_pack_candidate_share"] = 0.0
            entry["receipt_pack_confidence"] = "none"
        if len(unique_dates) >= 2:
            gaps = []
            for idx in range(1, len(unique_dates)):
                gap_days = (unique_dates[idx] - unique_dates[idx - 1]).days
                if gap_days >= 0:
                    gaps.append(gap_days)
            entry["avg_days_between_receipts"] = (
                float(sum(gaps)) / float(len(gaps)) if gaps else None
            )
    return history


def _finalize_streamed_sales_stats(stats_lookup):
    for entry in stats_lookup.values():
        quantity_counter = entry.pop("_quantity_counter", Counter())
        quantities = sorted(quantity_counter.elements())
        unique_dates = sorted(entry.pop("_sale_dates", set()))
        entry["sale_day_count"] = len(unique_dates)
        entry["avg_units_per_transaction"] = (
            float(entry["qty_sold_total"]) / float(entry["transaction_count"])
            if entry["transaction_count"] > 0 else None
        )
        entry["median_units_per_transaction"] = median(quantities) if quantities else None
        entry["max_units_per_transaction"] = max(quantities) if quantities else None
        if len(unique_dates) >= 2:
            gaps = []
            for idx in range(1, len(unique_dates)):
                gap_days = (unique_dates[idx] - unique_dates[idx - 1]).days
                if gap_days >= 0:
                    gaps.append(gap_days)
            entry["avg_days_between_sales"] = (
                float(sum(gaps)) / float(len(gaps)) if gaps else None
            )
        else:
            entry["avg_days_between_sales"] = None
    return stats_lookup


@perf_trace.timed("parsers.parse_detailed_pair_aggregates")
def parse_detailed_pair_aggregates(detailed_sales_path, received_parts_path, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    sales_summary = {}
    detailed_stats_lookup = {}
    detailed_sales_rollup = {}
    sales_start = None
    sales_end = None
    # Hoist locals for the 830K-row inner loop
    _coerce = _coerce_int
    _max = max
    sales_row_count = 0

    for row in _iter_detailed_part_sales_csv(detailed_sales_path):
        sales_row_count += 1
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        description = row.get("description", "")
        qty_sold = _max(0, _coerce(row.get("qty_sold", 0)))
        sale_date = str(row.get("sale_date", "") or "").strip()

        summary_entry = sales_summary.setdefault(key, {
            "line_code": key[0],
            "item_code": key[1],
            "description": "",
            "qty_received": 0,
            "qty_sold": 0,
        })
        summary_entry["qty_sold"] += qty_sold
        if not summary_entry["description"] and description:
            summary_entry["description"] = description

        stats_entry = detailed_stats_lookup.setdefault(key, {
            "transaction_count": 0,
            "qty_sold_total": 0,
            "_sale_dates": set(),
            "_quantity_counter": Counter(),
            "first_sale_date": "",
            "last_sale_date": "",
            "annualized_qty_sold": None,
        })
        stats_entry["transaction_count"] += 1
        stats_entry["qty_sold_total"] += qty_sold
        stats_entry["_quantity_counter"][qty_sold] += 1

        rollup_key = (key[0], key[1], description)
        rollup_entry = detailed_sales_rollup.setdefault(rollup_key, {
            "line_code": key[0],
            "item_code": key[1],
            "description": description,
            "qty_sold": 0,
            "row_count": 0,
        })
        rollup_entry["qty_sold"] += qty_sold
        rollup_entry["row_count"] += 1

        if sale_date:
            sale_dt = parse_date(sale_date)
            if sale_dt is not None:
                iso_date = sale_dt.date().isoformat()
                stats_entry["_sale_dates"].add(sale_dt.date())
                if not stats_entry["first_sale_date"] or iso_date < stats_entry["first_sale_date"]:
                    stats_entry["first_sale_date"] = iso_date
                if iso_date > stats_entry["last_sale_date"]:
                    stats_entry["last_sale_date"] = iso_date
                if sales_start is None or sale_dt < sales_start:
                    sales_start = sale_dt
                if sales_end is None or sale_dt > sales_end:
                    sales_end = sale_dt

    perf_trace.stamp(
        "parse_detailed_pair_aggregates.sales_done",
        rows=sales_row_count,
        keys=len(sales_summary),
    )
    receipt_history_lookup = {}
    receipt_cost_accum = {}  # key → {"total_cost": float, "total_qty": float}
    receipt_row_count = 0
    for row in _iter_received_parts_detail_csv(received_parts_path):
        receipt_row_count += 1
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        description = row.get("description", "")
        qty_received = _max(0, _coerce(row.get("qty_received", 0)))
        vendor = _normalize_vendor_code(row.get("vendor", ""))
        receipt_date = str(row.get("receipt_date", "") or "").strip()

        # Accumulate cost data for receipt-based unit cost fallback
        ext_cost = row.get("ext_cost")
        if ext_cost is not None and qty_received > 0:
            accum = receipt_cost_accum.get(key)
            if accum is None:
                accum = {"total_cost": 0.0, "total_qty": 0.0}
                receipt_cost_accum[key] = accum
            accum["total_cost"] += ext_cost
            accum["total_qty"] += qty_received

        summary_entry = sales_summary.setdefault(key, {
            "line_code": key[0],
            "item_code": key[1],
            "description": "",
            "qty_received": 0,
            "qty_sold": 0,
        })
        summary_entry["qty_received"] += qty_received
        if not summary_entry["description"] and description:
            summary_entry["description"] = description

        history_entry = receipt_history_lookup.setdefault(key, {
            "last_receipt_date": "",
            "primary_vendor": "",
            "vendor_candidates": [],
            "most_recent_vendor": "",
            "vendor_confidence": "none",
            "vendor_confidence_reason": "",
            "vendor_ambiguous": False,
            "primary_vendor_qty_share": 0.0,
            "primary_vendor_receipt_share": 0.0,
            "receipt_count": 0,
            "qty_received_total": 0,
            "first_receipt_date": "",
            "avg_units_per_receipt": None,
            "median_units_per_receipt": None,
            "max_units_per_receipt": None,
            "avg_days_between_receipts": None,
            "vendors": {},
            "_receipt_quantity_counter": Counter(),
            "_receipt_dates": set(),
        })
        history_entry["receipt_count"] += 1
        history_entry["qty_received_total"] += qty_received
        history_entry["_receipt_quantity_counter"][qty_received] += 1

        receipt_dt = parse_date(receipt_date) if receipt_date else None
        if receipt_dt is not None:
            iso_date = receipt_dt.date().isoformat()
            history_entry["_receipt_dates"].add(receipt_dt.date())
            if not history_entry["first_receipt_date"] or iso_date < history_entry["first_receipt_date"]:
                history_entry["first_receipt_date"] = iso_date
            if iso_date > history_entry["last_receipt_date"]:
                history_entry["last_receipt_date"] = iso_date
                history_entry["most_recent_vendor"] = vendor
        vendor_entry = history_entry["vendors"].setdefault(vendor, {
            "qty_received": 0,
            "receipt_count": 0,
            "last_receipt_date": "",
        })
        vendor_entry["qty_received"] += qty_received
        vendor_entry["receipt_count"] += 1
        if receipt_dt is not None:
            iso_date = receipt_dt.date().isoformat()
            if iso_date > vendor_entry["last_receipt_date"]:
                vendor_entry["last_receipt_date"] = iso_date

    perf_trace.stamp(
        "parse_detailed_pair_aggregates.receipts_done",
        rows=receipt_row_count,
        keys=len(receipt_history_lookup),
    )
    # Build receipt-cost lookup: weighted average unit cost from all receipts
    receipt_cost_lookup = {}
    for key, accum in receipt_cost_accum.items():
        if accum["total_qty"] > 0:
            receipt_cost_lookup[key] = round(accum["total_cost"] / accum["total_qty"], 4)

    return {
        "sales_items": list(sales_summary.values()),
        "sales_window": (sales_start, sales_end),
        "receipt_history_lookup": _finalize_streamed_receipt_history(receipt_history_lookup),
        "receipt_cost_lookup": receipt_cost_lookup,
        "detailed_sales_stats_lookup": _finalize_streamed_sales_stats(detailed_stats_lookup),
        "detailed_sales_rows": list(detailed_sales_rollup.values()),
    }



