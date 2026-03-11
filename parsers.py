import csv
import os
import re
from collections import defaultdict
from datetime import datetime


def identify_report_type(filepath):
    """
    Read the first row of a CSV and identify which X4 report it is.
    Returns one of: 'sales', 'minmax', 'onhand', 'po', 'susp', 'packsize', or None.
    """
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            row = next(reader, [])
        first_cols = " ".join(str(c).upper() for c in row[:16])
        if "PART SALES & RECEIPTS" in first_cols:
            return "sales"
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
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
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
    first = rows[0]
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
        for row in rows[1:]:
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
    first = rows[0]
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
            f"Could not find required columns. Found headers: {rows[0]}\n"
            f"Need at least 'item code' and 'pack size' (or similar) columns."
        )
    for row in rows[1:]:
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
                "qoh": _float(_safe(row, lc_col + 3)),
                "repl_cost": _float(_safe(row, lc_col + 4)),
                "min": _int(min_val) if min_val else None,
                "max": _int(max_val) if max_val else None,
                "ytd_sales": _int(_safe(row, lc_col + 9)),
                "mo12_sales": _int(_safe(row, lc_col + 10)),
                "supplier": _safe(row, lc_col + 11),
                "last_receipt": _safe(row, lc_col + 12),
                "last_sale": _safe(row, lc_col + 13),
            }
    return lookup
