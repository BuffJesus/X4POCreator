"""Order Rules CSV round-trip — export and import.

Pure functions, no UI, no file I/O.  The caller is responsible for reading/
writing the CSV text and showing any dialogs.

Export columns (in order):
    Line Code, Item Code, Order Policy, Pack Qty, Min Order Qty,
    Cover Days, Cover Cycles, Trigger Qty, Trigger %, Notes

Import semantics:
    - Additive/override: existing rules absent from the CSV are left untouched.
    - A row with a recognised rule key but blank policy AND all-blank numeric
      fields is treated as "delete this rule entry."
    - Unknown header columns are silently ignored.
    - Rows with blank Line Code or blank Item Code are skipped.
"""

import csv
import io


_EXPORT_COLS = [
    ("line_code",    "Line Code"),
    ("item_code",    "Item Code"),
    ("order_policy", "Order Policy"),
    ("pack_size",    "Pack Qty"),
    ("min_order_qty","Min Order Qty"),
    ("cover_days",   "Cover Days"),
    ("cover_cycles", "Cover Cycles"),
    ("trigger_qty",  "Trigger Qty"),
    ("trigger_pct",  "Trigger %"),
    ("notes",        "Notes"),
]

# Map CSV header label → internal rule dict key
_HEADER_TO_RULE_KEY = {
    "Order Policy":  "order_policy",
    "Pack Qty":      "pack_size",
    "Min Order Qty": "min_order_qty",
    "Cover Days":    "minimum_cover_days",
    "Cover Cycles":  "minimum_cover_cycles",
    "Trigger Qty":   "reorder_trigger_qty",
    "Trigger %":     "reorder_trigger_pct",
    "Notes":         "notes",
}

_RULE_KEY_TO_CSV = {v: k for k, v in _HEADER_TO_RULE_KEY.items()}


def export_rules_csv(order_rules):
    """Serialise *order_rules* to a CSV string.

    *order_rules* is a dict keyed by 'LINE_CODE:ITEM_CODE' whose values are
    rule dicts (as stored in order_rules.json).

    Returns a UTF-8 CSV string with a header row, sorted by Line Code then
    Item Code.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([label for _, label in _EXPORT_COLS])

    def _sort_key(k):
        parts = k.split(":", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")

    for rule_key in sorted(order_rules.keys(), key=_sort_key):
        line_code, item_code = _split_rule_key(rule_key)
        rule = order_rules[rule_key] or {}
        row = [
            line_code,
            item_code,
            rule.get("order_policy", ""),
            _fmt_num(rule.get("pack_size")),
            _fmt_num(rule.get("min_order_qty")),
            _fmt_num(rule.get("minimum_cover_days")),
            _fmt_num(rule.get("minimum_cover_cycles")),
            _fmt_num(rule.get("reorder_trigger_qty")),
            _fmt_num(rule.get("reorder_trigger_pct")),
            rule.get("notes", ""),
        ]
        writer.writerow(row)

    return buf.getvalue()


def import_rules_csv(csv_text, existing_rules):
    """Parse *csv_text* and return an import diff against *existing_rules*.

    Returns a dict:
        {
            "added":     {rule_key: rule_dict, ...},   # new keys not in existing
            "changed":   {rule_key: rule_dict, ...},   # keys present in both, with changes
            "deleted":   {rule_key, ...},               # keys to delete (all-blank rule row)
            "unchanged": {rule_key, ...},               # keys where nothing changed
            "skipped":   int,                           # rows skipped (bad/blank keys)
            "errors":    [str, ...],                    # parse warnings
        }

    The caller applies the diff via apply_import_diff().
    """
    result = {
        "added": {},
        "changed": {},
        "deleted": set(),
        "unchanged": set(),
        "skipped": 0,
        "errors": [],
    }

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        result["errors"].append("CSV is empty or has no header row.")
        return result

    for row_num, row in enumerate(reader, start=2):
        line_code = str(row.get("Line Code", "") or "").strip()
        item_code = str(row.get("Item Code", "") or "").strip()
        if not line_code or not item_code:
            result["skipped"] += 1
            continue

        rule_key = f"{line_code}:{item_code}"
        new_rule = _parse_rule_from_row(row, result["errors"], row_num)

        is_delete = _is_delete_row(new_rule)
        existing = existing_rules.get(rule_key)

        if is_delete:
            if existing is not None:
                result["deleted"].add(rule_key)
            else:
                result["skipped"] += 1
        elif existing is None:
            result["added"][rule_key] = new_rule
        elif _rules_differ(existing, new_rule):
            result["changed"][rule_key] = new_rule
        else:
            result["unchanged"].add(rule_key)

    return result


def apply_import_diff(existing_rules, diff):
    """Apply a diff returned by import_rules_csv() to *existing_rules* (in-place).

    Returns the count of rules affected (added + changed + deleted).
    """
    for key, rule in diff.get("added", {}).items():
        existing_rules[key] = rule
    for key, rule in diff.get("changed", {}).items():
        existing_rules[key] = rule
    for key in diff.get("deleted", set()):
        existing_rules.pop(key, None)
    return len(diff.get("added", {})) + len(diff.get("changed", {})) + len(diff.get("deleted", set()))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_rule_key(rule_key):
    parts = str(rule_key).split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], ""


def _fmt_num(value):
    if value is None or value == "":
        return ""
    try:
        f = float(value)
        if f == int(f):
            return str(int(f))
        return str(f)
    except (TypeError, ValueError):
        return str(value)


def _parse_rule_from_row(row, errors, row_num):
    rule = {}

    policy = str(row.get("Order Policy", "") or "").strip()
    if policy:
        rule["order_policy"] = policy

    int_fields = [
        ("Pack Qty",      "pack_size"),
        ("Min Order Qty", "min_order_qty"),
        ("Trigger Qty",   "reorder_trigger_qty"),
    ]
    for header, key in int_fields:
        val = str(row.get(header, "") or "").strip()
        if val:
            try:
                rule[key] = int(float(val))
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: invalid {header!r} value {val!r}, skipped.")

    float_fields = [
        ("Cover Days",    "minimum_cover_days"),
        ("Cover Cycles",  "minimum_cover_cycles"),
        ("Trigger %",     "reorder_trigger_pct"),
    ]
    for header, key in float_fields:
        val = str(row.get(header, "") or "").strip()
        if val:
            try:
                rule[key] = float(val)
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: invalid {header!r} value {val!r}, skipped.")

    notes = str(row.get("Notes", "") or "").strip()
    if notes:
        rule["notes"] = notes

    return rule


def _is_delete_row(rule):
    """Return True when *rule* is effectively empty (all-blank = delete intent)."""
    return not rule


def _rules_differ(existing, new_rule):
    """Return True when *new_rule* would change at least one field in *existing*."""
    for key, value in new_rule.items():
        if existing.get(key) != value:
            return True
    return False
