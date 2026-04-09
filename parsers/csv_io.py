"""Low-level CSV iteration, header detection, layout detection, and dedup."""

import csv

from parsers.normalize import _normalize_header_label


def _match_header_columns(rows, required_fields, optional_fields=(), *, header_aliases):
    for row_index, row in enumerate(rows):
        normalized = [_normalize_header_label(cell) for cell in row]
        if not any(normalized):
            continue
        indexes = {}
        matched = True
        for field_name in required_fields:
            aliases = header_aliases[field_name]
            index = next((i for i, value in enumerate(normalized) if value in aliases), None)
            if index is None:
                matched = False
                break
            indexes[field_name] = index
        if not matched:
            continue
        for field_name in optional_fields:
            aliases = header_aliases[field_name]
            indexes[field_name] = next((i for i, value in enumerate(normalized) if value in aliases), None)
        return row_index, indexes
    return None, {}


def _detail_row_signature(row):
    return tuple(row)


def _first_nonempty_csv_row(filepath):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row_number, row in enumerate(reader):
            if any(str(cell).strip() for cell in row):
                return row_number, row
    return None, None


def _detect_detail_layout(filepath, required_fields, *, optional_fields=(),
                          x4_row_checker=None, sample_limit=64, header_aliases):
    sampled_rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for _index, row in enumerate(reader):
            sampled_rows.append(row)
            header_index, indexes = _match_header_columns(
                sampled_rows, required_fields,
                optional_fields=optional_fields,
                header_aliases=header_aliases,
            )
            if header_index is not None:
                return "generic", header_index, indexes
            if x4_row_checker is not None and x4_row_checker(row):
                return "x4", None, {}
            if len(sampled_rows) >= sample_limit:
                break
    header_index, indexes = _match_header_columns(
        sampled_rows, required_fields,
        optional_fields=optional_fields,
        header_aliases=header_aliases,
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
