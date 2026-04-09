"""Low-level normalization helpers for CSV field values."""

import re


def _normalize_header_label(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _safe_cell(row, index):
    if index is None or index < 0 or index >= len(row):
        return ""
    return str(row[index]).strip()


def _coerce_int(value):
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _normalize_vendor_code(value):
    return str(value).strip().upper() if value else ""


def _clean_item_description(text):
    """Strip control characters and excessive whitespace from a description."""
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", str(text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
