import csv
import os
import re
from collections import defaultdict
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
        if val.endswith("-") and 2 <= len(val) <= 5 and val[:-1].isalnum():
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
    with open(filepath, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header_index, indexes = _match_header_columns(
        rows,
        ("line_code", "item_code", "qty_sold"),
        optional_fields=("description", "sale_date"),
    )
    if header_index is None:
        return []
    items = []
    for row in _dedupe_detail_rows(rows[header_index + 1:]):
        line_code = _safe_cell(row, indexes["line_code"])
        item_code = _safe_cell(row, indexes["item_code"])
        if not item_code:
            continue
        items.append({
            "line_code": line_code,
            "item_code": item_code,
            "description": _clean_item_description(_safe_cell(row, indexes.get("description"))),
            "qty_sold": _coerce_int(_safe_cell(row, indexes["qty_sold"])),
            "sale_date": _safe_cell(row, indexes.get("sale_date")),
        })
    return items


def parse_received_parts_detail_csv(filepath):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header_index, indexes = _match_header_columns(
        rows,
        ("line_code", "item_code", "qty_received", "vendor"),
        optional_fields=("description", "receipt_date"),
    )
    if header_index is None:
        return []
    items = []
    for row in _dedupe_detail_rows(rows[header_index + 1:]):
        line_code = _safe_cell(row, indexes["line_code"])
        item_code = _safe_cell(row, indexes["item_code"])
        if not item_code:
            continue
        items.append({
            "line_code": line_code,
            "item_code": item_code,
            "description": _clean_item_description(_safe_cell(row, indexes.get("description"))),
            "qty_received": _coerce_int(_safe_cell(row, indexes["qty_received"])),
            "receipt_date": _safe_cell(row, indexes.get("receipt_date")),
            "vendor": _normalize_vendor_code(_safe_cell(row, indexes["vendor"])),
        })
    return items


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
            "vendors": {},
        })
        if receipt_dt is not None:
            iso_date = receipt_dt.date().isoformat()
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
            "sale_dates": [],
            "quantities": [],
            "first_sale_date": "",
            "last_sale_date": "",
            "annualized_qty_sold": None,
        })
        entry["transaction_count"] += 1
        entry["qty_sold_total"] += qty_sold
        entry["quantities"].append(qty_sold)
        if sale_dt is not None:
            iso_date = sale_dt.date().isoformat()
            entry["sale_dates"].append(sale_dt.date())
            if not entry["first_sale_date"] or iso_date < entry["first_sale_date"]:
                entry["first_sale_date"] = iso_date
            if iso_date > entry["last_sale_date"]:
                entry["last_sale_date"] = iso_date

    for entry in stats_lookup.values():
        quantities = [max(0, int(qty)) for qty in entry.pop("quantities", [])]
        unique_dates = sorted(set(entry.pop("sale_dates", [])))
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
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return items, seen
    first_idx = next((i for i, row in enumerate(rows) if any(str(c).strip() for c in row)), None)
    if first_idx is None:
        return items, seen
    first = rows[first_idx]
    is_suspense_report = any("SUSPENSE REPORT" in str(c).upper() for c in first[:10])
    if is_suspense_report:
        seen_rows = set()
        for row in rows:
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
        for row in rows[first_idx + 1:]:
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
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return lookup
    first_idx = next((i for i, row in enumerate(rows) if any(str(c).strip() for c in row)), None)
    if first_idx is None:
        return lookup
    first = rows[first_idx]
    is_x4_om = any("ORDER MULTIPLE" in str(c).upper() for c in first[:7])
    if is_x4_om:
        seen = set()
        for row in rows:
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
    if len(rows) < 2:
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
    for row in rows[first_idx + 1:]:
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
