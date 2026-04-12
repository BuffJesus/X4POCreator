"""X4 report row shape knowledge — line code splitting, row checkers,
row builders, and the column-based line-code finder."""

import re

from parsers.normalize import _safe_cell, _coerce_int, _normalize_vendor_code


def _safe_float(value):
    """Coerce to float or None."""
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None
from parsers.dates import parse_x4_date


# ── Line code handling ───────────────────────────────────────────────

def _looks_like_x4_line_code_fragment(value):
    fragment = str(value or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z0-9/\-]{3}", fragment))


def _split_line_code_item_token(value):
    token = str(value or "").strip()
    if len(token) < 5:
        return "", token
    candidate = token[:3].upper()
    if token[3] == "-" and _looks_like_x4_line_code_fragment(candidate):
        item_code = token[4:]
        if item_code:
            return f"{candidate}-", item_code
    match = re.search(r"([A-Za-z0-9/]{3})\s+-\s+(.+)", token)
    if match:
        lc = match.group(1).upper()
        ic = match.group(2).strip()
        if ic:
            return f"{lc}-", ic
    return "", token


def _find_lc_column(row):
    for i, c in enumerate(row):
        val = c.strip()
        if val.endswith("-") and 2 <= len(val) <= 5 and re.fullmatch(r"[A-Za-z0-9/\-]+", val[:-1]):
            return i
    return None


# ── Description cleaning ─────────────────────────────────────────────

_DESC_STOP_PREFIXES = ("orig inv#", "orig po#", "orig invoice", "orig po", "data:", "page ")


def _clean_item_description(text):
    if text is None:
        return ""
    raw = str(text)
    if "\n" not in raw and "\r" not in raw:
        stripped = raw.strip()
        if not stripped:
            return ""
        low = stripped.lower()
        for pfx in _DESC_STOP_PREFIXES:
            if low.startswith(pfx):
                return ""
        return stripped
    lines = [ln.strip() for ln in raw.replace("\r", "\n").split("\n") if ln.strip()]
    if not lines:
        return ""
    kept = []
    for ln in lines:
        low = ln.lower()
        if any(low.startswith(pfx) for pfx in _DESC_STOP_PREFIXES):
            break
        kept.append(ln)
    if not kept:
        kept = [lines[0]]
    return " ".join(kept)


# ── Detailed Part Sales ──────────────────────────────────────────────

def _looks_like_x4_detailed_part_sales_row(row, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    if len(row) < 32:
        return False
    if parse_date(_safe_cell(row, 31)) is None:
        return False
    return bool(_safe_cell(row, 24) and _safe_cell(row, 25))


def _parse_x4_detailed_part_sales_row(row):
    line_code, item_code = _split_line_code_item_token(_safe_cell(row, 24))
    return {
        "line_code": line_code,
        "item_code": item_code,
        "description": _clean_item_description(_safe_cell(row, 25)),
        "qty_sold": _coerce_int(_safe_cell(row, 36)),
        "sale_date": _safe_cell(row, 31),
    }


def _parse_x4_detailed_part_sales_rows(rows):
    from parsers.csv_io import _dedupe_detail_rows
    items = []
    for row in _dedupe_detail_rows(rows):
        if not _looks_like_x4_detailed_part_sales_row(row):
            continue
        items.append(_parse_x4_detailed_part_sales_row(row))
    return items


# ── Received Parts Detail ────────────────────────────────────────────

def _looks_like_x4_received_parts_detail_row(row, *, parse_date=None):
    parse_date = parse_date or parse_x4_date
    if len(row) < 23:
        return False
    if parse_date(_safe_cell(row, 14)) is None:
        return False
    if not _safe_cell(row, 15).endswith("-"):
        return False
    return bool(_safe_cell(row, 16) and _safe_cell(row, 18))


def _parse_x4_received_parts_detail_row(row):
    return {
        "line_code": _safe_cell(row, 15),
        "item_code": _safe_cell(row, 16),
        "description": _clean_item_description(_safe_cell(row, 17)),
        "qty_received": _coerce_int(_safe_cell(row, 22)),
        "ext_cost": _safe_float(_safe_cell(row, 21)),
        "receipt_date": _safe_cell(row, 14),
        "vendor": _normalize_vendor_code(_safe_cell(row, 18)),
    }


def _parse_x4_received_parts_detail_rows(rows):
    from parsers.csv_io import _dedupe_detail_rows
    items = []
    for row in _dedupe_detail_rows(rows):
        if not _looks_like_x4_received_parts_detail_row(row):
            continue
        items.append(_parse_x4_received_parts_detail_row(row))
    return items
