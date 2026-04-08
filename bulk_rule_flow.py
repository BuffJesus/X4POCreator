"""Bulk buy-rule editing logic.

apply_bulk_rule_edit(app, keys, changes) — pure business logic, no UI.

*changes* is a dict of field names → values.  Only fields that are present
in *changes* are written; existing rule fields not mentioned are preserved.

Supported change keys:
    order_policy     (str)   — sets rule["order_policy"] and locks it
    pack_size        (int)   — sets rule["pack_size"]
    min_order_qty    (int)   — sets rule["min_order_qty"]
    cover_days       (float) — sets rule["minimum_cover_days"]
"""


_POLICY_VALUES = frozenset({
    "standard",
    "pack_trigger",
    "soft_pack",
    "exact_qty",
    "reel_review",
    "reel_auto",
    "large_pack_review",
    "manual_only",
})


def apply_bulk_rule_edit(app, keys, changes):
    """Apply *changes* to every rule keyed by *keys*.

    Only rule keys that correspond to a known order-policy or a positive
    numeric value are applied; invalid entries in *changes* are skipped.

    Returns the count of rule entries that were actually modified.
    """
    if not keys or not changes:
        return 0

    order_policy = changes.get("order_policy", "")
    pack_size = changes.get("pack_size", "")
    min_order_qty = changes.get("min_order_qty", "")
    cover_days = changes.get("cover_days", "")

    parsed_policy = str(order_policy).strip() if order_policy else ""
    parsed_pack = _parse_positive_int(pack_size)
    parsed_min = _parse_positive_int(min_order_qty)
    parsed_cover = _parse_positive_float(cover_days)

    if not parsed_policy and parsed_pack is None and parsed_min is None and parsed_cover is None:
        return 0
    if parsed_policy and parsed_policy not in _POLICY_VALUES:
        parsed_policy = ""

    modified = 0
    for key in keys:
        rule = dict(app.order_rules.get(key) or {})
        changed = False

        if parsed_policy:
            rule["order_policy"] = parsed_policy
            rule["policy_locked"] = True
            changed = True

        if parsed_pack is not None:
            rule["pack_size"] = parsed_pack
            changed = True

        if parsed_min is not None:
            rule["min_order_qty"] = parsed_min
            changed = True

        if parsed_cover is not None:
            rule["minimum_cover_days"] = parsed_cover
            changed = True

        if changed:
            app.order_rules[key] = rule
            modified += 1

    if modified:
        if hasattr(app, "_save_order_rules"):
            app._save_order_rules()

    return modified


def _parse_positive_int(value):
    """Return a positive int from *value*, or None if blank/invalid."""
    s = str(value).strip()
    if not s:
        return None
    try:
        v = int(float(s))
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_positive_float(value):
    """Return a positive float from *value*, or None if blank/invalid."""
    s = str(value).strip()
    if not s:
        return None
    try:
        v = float(s)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None
