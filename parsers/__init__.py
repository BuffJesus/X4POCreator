import csv
import os
import re
from collections import Counter, defaultdict
from statistics import median
from datetime import datetime

import perf_trace


HEADER_ALIASES = {
    "line_code": {"linecode", "line_code", "line", "pg", "productgroup", "product_group"},
    "item_code": {"itemcode", "item_code", "item", "partnumber", "part_number", "part"},
    "description": {"description", "desc", "itemdescription", "item_description"},
    "qty_sold": {"qtysold", "qty_sold", "soldqty", "quantitysold", "salesqty", "invoiceqty", "qty"},
    "sale_date": {"saledate", "sale_date", "salesdate", "invoicedate", "transdate", "transactiondate", "date", "dated"},
    "qty_received": {"qtyreceived", "qty_received", "receivedqty", "quantityreceived", "receiptqty", "receivedquantity", "qty"},
    "receipt_date": {"receiptdate", "receipt_date", "receiveddate", "datereceived", "rcvdate", "receivingdate", "date", "dated"},
    "vendor": {"vendor", "vendorcode", "supplier", "suppliercode", "vend", "vendorid"},
}


def _coerce_float(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


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


_DESC_STOP_PREFIXES = ("orig inv#", "orig po#", "orig invoice", "orig po", "data:", "page ")


def parse_detailed_part_sales_csv(filepath):
    return list(_iter_detailed_part_sales_csv(filepath))


def parse_received_parts_detail_csv(filepath):
    return list(_iter_received_parts_detail_csv(filepath))


@perf_trace.timed("parsers.parse_detailed_pair_aggregates")
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


# Memoize parse_x4_date — profiling the 8-year sales dataset showed
# `strptime` being called 1.67M times and consuming ~33s of parse time,
# because every detail row re-parses the same repeating date strings.
# A simple string→datetime cache eliminates the redundant work.  Bounded
# size cap guards against pathological inputs; a real dataset never has
# more than ~3,000 unique dates over 8 years.
_PARSE_X4_DATE_CACHE: dict = {}
_PARSE_X4_DATE_CACHE_MAX = 50_000


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
                "description": _safe(row, lc_col + 2),
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


# --- Extracted sub-modules override local definitions ---
from parsers.dates import parse_x4_date, _PARSE_X4_DATE_CACHE  # noqa: E402, F811
from parsers.normalize import (  # noqa: E402, F811
    _normalize_header_label,
    _safe_cell,
    _coerce_int,
    _normalize_vendor_code,
)
from parsers.csv_io import (  # noqa: E402, F811
    _detail_row_signature,
    _first_nonempty_csv_row,
    _iter_generic_detail_rows,
    _iter_x4_detail_rows,
    _dedupe_detail_rows,
)
from parsers.csv_io import (
    _match_header_columns as _csv_io_match_header_columns,
    _detect_detail_layout as _csv_io_detect_detail_layout,
)


def _match_header_columns(rows, required_fields, optional_fields=()):  # noqa: F811
    return _csv_io_match_header_columns(rows, required_fields, optional_fields, header_aliases=HEADER_ALIASES)


def _detect_detail_layout(filepath, required_fields, *, optional_fields=(), x4_row_checker=None, sample_limit=64):  # noqa: F811
    return _csv_io_detect_detail_layout(filepath, required_fields, optional_fields=optional_fields,
                                        x4_row_checker=x4_row_checker, sample_limit=sample_limit,
                                        header_aliases=HEADER_ALIASES)


from parsers.x4_dialect import (  # noqa: E402, F811
    _looks_like_x4_line_code_fragment,
    _split_line_code_item_token,
    _find_lc_column,
    _clean_item_description,
    _looks_like_x4_detailed_part_sales_row,
    _parse_x4_detailed_part_sales_row,
    _parse_x4_detailed_part_sales_rows,
    _looks_like_x4_received_parts_detail_row,
    _parse_x4_received_parts_detail_row,
    _parse_x4_received_parts_detail_rows,
)
from parsers.aggregators import (  # noqa: E402, F811
    parse_detailed_sales_date_range,
    build_sales_receipt_summary,
    build_receipt_history_lookup,
    build_detailed_sales_stats_lookup,
    _finalize_streamed_receipt_history,
    _finalize_streamed_sales_stats,
    parse_detailed_pair_aggregates,
)
