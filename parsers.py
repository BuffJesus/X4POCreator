import csv
import os
import re
from collections import Counter, defaultdict
from statistics import median
from datetime import datetime


HEADER_ALIASES = {
    "line_code": {"linecode", "line_code", "line", "pg", "productgroup", "product_group"},
    "item_code": {"itemcode", "item_code", "item", "partnumber", "part_number", "part"},
    "description": {"description", "desc", "itemdescription", "item_description"},
    "qty_sold": {"qtysold", "soldqty", "quantitysold", "salesqty", "invoiceqty", "qty"},
    "sale_date": {"saledate", "salesdate", "invoicedate", "transdate", "transactiondate", "date", "dated"},
    "qty_received": {"qtyreceived", "receivedqty", "quantityreceived", "receiptqty", "receivedquantity", "qty"},
    "receipt_date": {"receiptdate", "receiveddate", "datereceived", "rcvdate", "receivingdate", "date", "dated"},
    "vendor": {"vendor", "vendorcode", "supplier", "suppliercode", "vend", "vendorid"},
}


def _normalize_header_label(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _safe_cell(row, index):
    if index is None or index < 0 or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _coerce_int(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _normalize_vendor_code(value):
    return str(value or "").strip().upper()


def _looks_like_x4_line_code_fragment(value):
    fragment = str(value or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z0-9/\-]{3}", fragment))


def _split_line_code_item_token(value):
    # X4 line codes are always exactly 3 characters (letters, digits, '/', or '-')
    # followed by a '-' separator.  Using a fixed-width split avoids misreading the
    # first '-' inside a dash-bearing line code (e.g. "A-B-12345") as the separator.
    token = str(value or "").strip()
    if len(token) < 5:
        return "", token
    candidate = token[:3].upper()
    if token[3] == "-" and _looks_like_x4_line_code_fragment(candidate):
        item_code = token[4:]
        if item_code:
            return f"{candidate}-", item_code
    # Fallback: handle optional whitespace around the separator for non-dash line
    # codes (e.g. "010 - 00055062").  Only matches letter/digit/slash fragments so
    # it does not conflict with dash-bearing line codes handled above.
    match = re.search(r"([A-Za-z0-9/]{3})\s+-\s+(.+)", token)
    if match:
        lc = match.group(1).upper()
        ic = match.group(2).strip()
        if ic:
            return f"{lc}-", ic
    return "", token


def _match_header_columns(rows, required_fields, optional_fields=()):
    for row_index, row in enumerate(rows):
        normalized = [_normalize_header_label(cell) for cell in row]
        if not any(normalized):
            continue
        indexes = {}
        matched = True
        for field_name in required_fields:
            aliases = HEADER_ALIASES[field_name]
            index = next((i for i, value in enumerate(normalized) if value in aliases), None)
            if index is None:
                matched = False
                break
            indexes[field_name] = index
        if not matched:
            continue
        for field_name in optional_fields:
            aliases = HEADER_ALIASES[field_name]
            indexes[field_name] = next((i for i, value in enumerate(normalized) if value in aliases), None)
        return row_index, indexes
    return None, {}


def _dedupe_detail_rows(rows):
    seen_rows = set()
    unique_rows = []
    for row in rows:
        normalized = tuple(str(cell).strip() for cell in row)
        if not any(normalized):
            continue
        if normalized in seen_rows:
            continue
        seen_rows.add(normalized)
        unique_rows.append(row)
    return unique_rows


def _detail_row_signature(row):
    return tuple(str(cell).strip() for cell in row)


def _first_nonempty_csv_row(filepath):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row_number, row in enumerate(reader):
            if any(str(cell).strip() for cell in row):
                return row_number, row
    return None, None


def _detect_detail_layout(filepath, required_fields, *, optional_fields=(), x4_row_checker=None, sample_limit=64):
    sampled_rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for _index, row in enumerate(reader):
            sampled_rows.append(row)
            header_index, indexes = _match_header_columns(
                sampled_rows,
                required_fields,
                optional_fields=optional_fields,
            )
            if header_index is not None:
                return "generic", header_index, indexes
            if x4_row_checker is not None and x4_row_checker(row):
                return "x4", None, {}
            if len(sampled_rows) >= sample_limit:
                break
    header_index, indexes = _match_header_columns(
        sampled_rows,
        required_fields,
        optional_fields=optional_fields,
    )
    if header_index is not None:
        return "generic", header_index, indexes
    return "x4", None, {}


def _iter_generic_detail_rows(filepath, *, header_index, indexes, row_builder):
    seen_rows = set()
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row_number, row in enumerate(reader):
            if row_number <= header_index:
                continue
            signature = _detail_row_signature(row)
            if not any(signature):
                continue
            if signature in seen_rows:
                continue
            seen_rows.add(signature)
            parsed = row_builder(row, indexes)
            if parsed is not None:
                yield parsed


def _iter_x4_detail_rows(filepath, *, row_checker, row_builder):
    seen_rows = set()
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            signature = _detail_row_signature(row)
            if not any(signature):
                continue
            if signature in seen_rows:
                continue
            seen_rows.add(signature)
            if not row_checker(row):
                continue
            parsed = row_builder(row)
            if parsed is not None:
                yield parsed


def _generic_detailed_sales_row_builder(row, indexes):
    line_code = _safe_cell(row, indexes["line_code"])
    item_code = _safe_cell(row, indexes["item_code"])
    if not item_code:
        return None
    return {
        "line_code": line_code,
        "item_code": item_code,
        "description": _clean_item_description(_safe_cell(row, indexes.get("description"))),
        "qty_sold": _coerce_int(_safe_cell(row, indexes["qty_sold"])),
        "sale_date": _safe_cell(row, indexes.get("sale_date")),
    }


def _generic_received_parts_row_builder(row, indexes):
    line_code = _safe_cell(row, indexes["line_code"])
    item_code = _safe_cell(row, indexes["item_code"])
    if not item_code:
        return None
    return {
        "line_code": line_code,
        "item_code": item_code,
        "description": _clean_item_description(_safe_cell(row, indexes.get("description"))),
        "qty_received": _coerce_int(_safe_cell(row, indexes["qty_received"])),
        "receipt_date": _safe_cell(row, indexes.get("receipt_date")),
        "vendor": _normalize_vendor_code(_safe_cell(row, indexes["vendor"])),
    }


def _iter_detailed_part_sales_csv(filepath):
    layout, header_index, indexes = _detect_detail_layout(
        filepath,
        ("line_code", "item_code", "qty_sold"),
        optional_fields=("description", "sale_date"),
        x4_row_checker=_looks_like_x4_detailed_part_sales_row,
    )
    if layout == "generic":
        yield from _iter_generic_detail_rows(
            filepath,
            header_index=header_index,
            indexes=indexes,
            row_builder=_generic_detailed_sales_row_builder,
        )
        return
    yield from _iter_x4_detail_rows(
        filepath,
        row_checker=_looks_like_x4_detailed_part_sales_row,
        row_builder=_parse_x4_detailed_part_sales_row,
    )


def _iter_received_parts_detail_csv(filepath):
    layout, header_index, indexes = _detect_detail_layout(
        filepath,
        ("line_code", "item_code", "qty_received", "vendor"),
        optional_fields=("description", "receipt_date"),
        x4_row_checker=_looks_like_x4_received_parts_detail_row,
    )
    if layout == "generic":
        yield from _iter_generic_detail_rows(
            filepath,
            header_index=header_index,
            indexes=indexes,
            row_builder=_generic_received_parts_row_builder,
        )
        return
    yield from _iter_x4_detail_rows(
        filepath,
        row_checker=_looks_like_x4_received_parts_detail_row,
        row_builder=_parse_x4_received_parts_detail_row,
    )


def identify_report_type(filepath):
    """
    Read a CSV and identify which X4 report it is.
    Returns one of: 'sales', 'detailedsales', 'receivedparts', 'minmax', 'onhand',
    'po', 'susp', 'packsize', or None.
    """
    filename_key = re.sub(r"[^a-z0-9]+", "", os.path.basename(filepath).lower())
    if "detailedpartsales" in filename_key:
        return "detailedsales"
    if "receivedpartsdetail" in filename_key:
        return "receivedparts"
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            sampled_rows = []
            for row in reader:
                sampled_rows.append(row)
                if not any(str(c).strip() for c in row):
                    continue
                first_cols = " ".join(str(c).upper() for c in row[:16])
                if "PART SALES & RECEIPTS" in first_cols:
                    return "sales"
                if "DETAILED PART SALES" in first_cols:
                    return "detailedsales"
                if "RECEIVED PARTS DETAIL" in first_cols:
                    return "receivedparts"
                if "SUSPENSE REPORT" in first_cols:
                    return "susp"
                if "PO PART LISTING BY PRODUCT GROUP" in first_cols:
                    return "po"
                if "ON HAND REPORT" in first_cols:
                    return "onhand"
                if "ITEMS WITH ORDER MULTIPLE" in first_cols:
                    return "packsize"
                upper_cols = [str(c).strip().upper() for c in row]
                if "PG" in upper_cols and "QOH" in upper_cols and "ITEM CODE" in upper_cols:
                    pg_idx = upper_cols.index("PG")
                    qoh_idx = upper_cols.index("QOH")
                    if qoh_idx > pg_idx:
                        return "minmax"
            header_idx, _ = _match_header_columns(
                sampled_rows,
                ("line_code", "item_code", "qty_sold"),
                optional_fields=("sale_date",),
            )
            if header_idx is not None:
                return "detailedsales"
            header_idx, _ = _match_header_columns(
                sampled_rows,
                ("line_code", "item_code", "qty_received", "vendor"),
                optional_fields=("receipt_date",),
            )
            if header_idx is not None:
                return "receivedparts"
    except Exception:
        pass
    return None


def scan_directory_for_reports(directory):
    """Scan a directory for CSV files and identify each one."""
    found = {}
    for filename in sorted(os.listdir(directory)):
        if not filename.lower().endswith(".csv"):
            continue
        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath):
            continue
        report_type = identify_report_type(filepath)
        if report_type and report_type not in found:
            found[report_type] = filepath
    return found


def _find_lc_column(row):
    for i, c in enumerate(row):
        val = c.strip()
        if val.endswith("-") and 2 <= len(val) <= 5 and re.fullmatch(r"[A-Za-z0-9/\-]+", val[:-1]):
            return i
    return None


def _clean_item_description(text):
    if text is None:
        return ""
    raw = str(text).replace("\r", "\n")
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    if not lines:
        return ""
    stop_prefixes = ("orig inv#", "orig po#", "orig invoice", "orig po", "data:", "page ")
    kept = []
    for ln in lines:
        low = ln.lower()
        if any(low.startswith(pfx) for pfx in stop_prefixes):
            break
        kept.append(ln)
    if not kept:
        kept = [lines[0]]
    return " ".join(kept)


def parse_part_sales_csv(filepath):
    agg = {}
    seen_rows = set()
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            normalized_row = tuple(str(cell).strip() for cell in row)
            if normalized_row in seen_rows:
                continue
            seen_rows.add(normalized_row)
            lc = _find_lc_column(row)
            if lc is None or lc + 5 >= len(row):
                continue
            try:
                line_code = row[lc].strip()
                item_code = row[lc + 1].strip()
                description = _clean_item_description(row[lc + 2])
                qty_received = int(float(row[lc + 3].replace(",", "")))
                qty_sold = int(float(row[lc + 5].replace(",", "")))
            except (ValueError, IndexError):
                continue
            if not item_code:
                continue
            key = (line_code, item_code)
            if key not in agg:
                agg[key] = {
                    "line_code": line_code,
                    "item_code": item_code,
                    "description": description,
                    "qty_received": qty_received,
                    "qty_sold": qty_sold,
                }
            else:
                agg[key]["qty_received"] += qty_received
                agg[key]["qty_sold"] += qty_sold
                if not agg[key].get("description") and description:
                    agg[key]["description"] = description
    return list(agg.values())


def parse_detailed_part_sales_csv(filepath):
    return list(_iter_detailed_part_sales_csv(filepath))


def parse_received_parts_detail_csv(filepath):
    return list(_iter_received_parts_detail_csv(filepath))


def _looks_like_x4_received_parts_detail_row(row, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    if len(row) < 23:
        return False
    if parse_date(_safe_cell(row, 14)) is None:
        return False
    if not _safe_cell(row, 15).endswith("-"):
        return False
    return bool(_safe_cell(row, 16) and _safe_cell(row, 18))


def _parse_x4_received_parts_detail_rows(rows):
    items = []
    for row in _dedupe_detail_rows(rows):
        if not _looks_like_x4_received_parts_detail_row(row):
            continue
        items.append(_parse_x4_received_parts_detail_row(row))
    return items


def _parse_x4_received_parts_detail_row(row):
    return {
        "line_code": _safe_cell(row, 15),
        "item_code": _safe_cell(row, 16),
        "description": _clean_item_description(_safe_cell(row, 17)),
        "qty_received": _coerce_int(_safe_cell(row, 22)),
        "receipt_date": _safe_cell(row, 14),
        "vendor": _normalize_vendor_code(_safe_cell(row, 18)),
    }


def _looks_like_x4_detailed_part_sales_row(row, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    if len(row) < 32:
        return False
    if parse_date(_safe_cell(row, 31)) is None:
        return False
    return bool(_safe_cell(row, 24) and _safe_cell(row, 25))


def _parse_x4_detailed_part_sales_rows(rows):
    items = []
    for row in _dedupe_detail_rows(rows):
        if not _looks_like_x4_detailed_part_sales_row(row):
            continue
        items.append(_parse_x4_detailed_part_sales_row(row))
    return items


def _parse_x4_detailed_part_sales_row(row):
    line_code, item_code = _split_line_code_item_token(_safe_cell(row, 24))
    return {
        "line_code": line_code,
        "item_code": item_code,
        "description": _clean_item_description(_safe_cell(row, 25)),
        "qty_sold": _coerce_int(_safe_cell(row, 26)),
        "sale_date": _safe_cell(row, 31),
    }


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


def parse_detailed_pair_aggregates(detailed_sales_path, received_parts_path, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    sales_summary = {}
    detailed_stats_lookup = {}
    detailed_sales_rollup = {}
    sales_start = None
    sales_end = None

    for row in _iter_detailed_part_sales_csv(detailed_sales_path):
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        description = row.get("description", "")
        qty_sold = max(0, _coerce_int(row.get("qty_sold", 0)))
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

    receipt_history_lookup = {}
    for row in _iter_received_parts_detail_csv(received_parts_path):
        key = (row.get("line_code", ""), row.get("item_code", ""))
        if not key[1]:
            continue
        description = row.get("description", "")
        qty_received = max(0, _coerce_int(row.get("qty_received", 0)))
        vendor = _normalize_vendor_code(row.get("vendor", ""))
        receipt_date = str(row.get("receipt_date", "") or "").strip()

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

    return {
        "sales_items": list(sales_summary.values()),
        "sales_window": (sales_start, sales_end),
        "receipt_history_lookup": _finalize_streamed_receipt_history(receipt_history_lookup),
        "detailed_sales_stats_lookup": _finalize_streamed_sales_stats(detailed_stats_lookup),
        "detailed_sales_rows": list(detailed_sales_rollup.values()),
    }


def parse_sales_date_range(filepath):
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            head = f.read(8192)
    except Exception:
        return None, None
    m = re.search(
        r"From:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4}).*?thru\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4})",
        head,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None, None
    try:
        return datetime.strptime(m.group(1), "%d-%b-%Y"), datetime.strptime(m.group(2), "%d-%b-%Y")
    except Exception:
        return None, None


def parse_suspended_csv(filepath):
    items = []
    seen = set()
    first_idx, first = _first_nonempty_csv_row(filepath)
    if first_idx is None or first is None:
        return items, seen
    is_suspense_report = any("SUSPENSE REPORT" in str(c).upper() for c in first[:10])
    if is_suspense_report:
        seen_rows = set()
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                lc_col = _find_lc_column(row)
                if lc_col is None or lc_col + 16 >= len(row):
                    continue
                lc = row[lc_col].strip()
                ic = row[lc_col + 1].strip()
                desc = _clean_item_description(row[lc_col + 2])
                if not ic:
                    continue
                customer_code = row[lc_col + 11].strip()
                customer = row[lc_col + 12].strip()
                date = row[lc_col + 10].strip()
                cust_ref = row[lc_col + 14].strip()
                try:
                    qty_ord = int(float(row[lc_col + 15].replace(",", "")))
                    qty_ship = int(float(row[lc_col + 16].replace(",", "")))
                except (ValueError, IndexError):
                    qty_ord, qty_ship = 0, 0
                dedup_key = (lc, ic, customer_code, date, cust_ref, qty_ord, qty_ship)
                if dedup_key in seen_rows:
                    continue
                seen_rows.add(dedup_key)
                items.append({
                    "line_code": lc, "item_code": ic, "description": desc,
                    "qty_ordered": qty_ord, "qty_shipped": qty_ship,
                    "customer_code": customer_code, "customer": customer, "date": date,
                })
                seen.add((lc, ic))
        return items, seen
    header = [c.strip().lower() for c in first]
    pg_idx = None
    ic_idx = None
    for i, h in enumerate(header):
        if h in ("pg", "product group", "line code", "line_code", "linecode"):
            pg_idx = i
        if h in ("item code", "item_code", "itemcode", "part number", "part"):
            ic_idx = i
    if ic_idx is not None:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row_number, row in enumerate(reader):
                if row_number <= first_idx:
                    continue
                if len(row) > max(x for x in [pg_idx or 0, ic_idx] if x is not None):
                    lc = row[pg_idx].strip() if pg_idx is not None else ""
                    ic = row[ic_idx].strip()
                    if ic:
                        seen.add((lc, ic))
                        items.append({"line_code": lc, "item_code": ic,
                                      "description": "", "qty_ordered": 0,
                                      "qty_shipped": 0, "customer": "", "date": ""})
    return items, seen


def parse_po_listing_csv(filepath):
    po_items = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            lc = _find_lc_column(row)
            if lc is None or lc + 5 >= len(row):
                continue
            try:
                po_number = row[lc - 1].strip() if lc > 0 else ""
                line_code = row[lc].strip()
                item_code = row[lc + 1].strip()
                po_type = row[lc + 2].strip()
                qty = float(row[lc + 3].replace(",", ""))
                date_issued = row[lc + 5].strip()
            except (ValueError, IndexError):
                continue
            if not item_code:
                continue
            po_items.append({
                "po_number": po_number,
                "line_code": line_code,
                "item_code": item_code,
                "po_type": po_type,
                "qty": qty,
                "date_issued": date_issued,
            })
    return po_items


def parse_x4_date(value):
    if not value:
        return None
    txt = str(value).strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt)
        except ValueError:
            continue
    return None


def build_pack_size_fallbacks(pack_size_lookup):
    by_item = defaultdict(set)
    for (_, item_code), pack in pack_size_lookup.items():
        if pack and pack > 0:
            by_item[item_code].add(int(pack))
    fallback = {}
    conflicts = set()
    for item_code, packs in by_item.items():
        if len(packs) == 1:
            fallback[item_code] = next(iter(packs))
        elif len(packs) > 1:
            conflicts.add(item_code)
    return fallback, conflicts


def parse_pack_sizes_csv(filepath):
    lookup = {}
    first_idx, first = _first_nonempty_csv_row(filepath)
    if first_idx is None or first is None:
        return lookup
    is_x4_om = any("ORDER MULTIPLE" in str(c).upper() for c in first[:7])
    if is_x4_om:
        seen = set()
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                lc_col = _find_lc_column(row)
                if lc_col is None or lc_col + 3 >= len(row):
                    continue
                lc = row[lc_col].strip()
                ic = row[lc_col + 1].strip()
                if not ic:
                    continue
                try:
                    ps = int(float(row[lc_col + 3].replace(",", "")))
                except (ValueError, IndexError):
                    continue
                key = (lc, ic)
                if key not in seen and ps > 0:
                    seen.add(key)
                    lookup[key] = ps
        return lookup
    header = [c.strip().lower() for c in first]
    pg_idx = None
    ic_idx = None
    ps_idx = None
    for i, h in enumerate(header):
        if h in ("pg", "product group", "line code", "line_code", "linecode"):
            pg_idx = i
        if h in ("item code", "item_code", "itemcode", "part number", "part", "item"):
            ic_idx = i
        if h in ("pack size", "pack_size", "packsize", "pack qty", "pack_qty",
                  "case qty", "case_qty", "order multiple", "order_multiple",
                  "qty per", "qty_per", "multiple", "pack"):
            ps_idx = i
    if ic_idx is None or ps_idx is None:
        raise ValueError(
            f"Could not find required columns. Found headers: {first}\n"
            f"Need at least 'item code' and 'pack size' (or similar) columns."
        )
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row_number, row in enumerate(reader):
            if row_number <= first_idx:
                continue
            if len(row) <= max(ic_idx, ps_idx):
                continue
            lc = row[pg_idx].strip() if pg_idx is not None else ""
            ic = row[ic_idx].strip()
            try:
                ps = int(float(row[ps_idx].replace(",", "")))
            except (ValueError, IndexError):
                continue
            if ic and ps > 0:
                lookup[(lc, ic)] = ps
    return lookup


def parse_on_hand_report(filepath):
    lookup = {}
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            lc_col = _find_lc_column(row)
            if lc_col is None or lc_col + 8 >= len(row):
                continue
            lc = row[lc_col].strip()
            ic = row[lc_col + 5].strip()
            if not ic or ic in ("0000", "ZZZZ"):
                continue
            try:
                qoh = float(row[lc_col + 7].replace(",", ""))
            except (ValueError, IndexError):
                qoh = 0.0
            try:
                repl_cost = float(row[lc_col + 8].replace(",", ""))
            except (ValueError, IndexError):
                repl_cost = 0.0
            lookup[(lc, ic)] = {"qoh": qoh, "repl_cost": repl_cost}
    return lookup


def parse_on_hand_min_max(filepath):
    def _float(val):
        try:
            return float(val.replace(",", ""))
        except (ValueError, AttributeError):
            return 0.0

    def _optional_float(val):
        if val is None:
            return None
        text = str(val).strip()
        if not text:
            return None
        try:
            return float(text.replace(",", ""))
        except (ValueError, AttributeError):
            return None

    def _int(val):
        try:
            return int(float(val.replace(",", "")))
        except (ValueError, AttributeError):
            return 0

    def _safe(row, idx):
        return row[idx].strip() if idx < len(row) else ""

    lookup = {}
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            lc_col = _find_lc_column(row)
            if lc_col is None or lc_col + 11 >= len(row):
                continue
            lc = row[lc_col].strip()
            ic = row[lc_col + 1].strip()
            if not ic or ic in ("0000", "ZZZZ"):
                continue
            min_val = _safe(row, lc_col + 7)
            max_val = _safe(row, lc_col + 8)
            lookup[(lc, ic)] = {
                "qoh": _optional_float(_safe(row, lc_col + 3)),
                "repl_cost": _optional_float(_safe(row, lc_col + 4)),
                "min": _int(min_val) if min_val else None,
                "max": _int(max_val) if max_val else None,
                "ytd_sales": _int(_safe(row, lc_col + 9)),
                "mo12_sales": _int(_safe(row, lc_col + 10)),
                "supplier": _safe(row, lc_col + 11),
                "last_receipt": _safe(row, lc_col + 12),
                "last_sale": _safe(row, lc_col + 13),
            }
    return lookup
