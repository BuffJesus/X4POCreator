"""Small rule-field extraction helpers used across the rules package."""


def has_exact_qty_override(rule):
    """Return True when a rule explicitly forces exact-quantity behavior."""
    if not rule:
        return False
    if rule.get("exact_qty_override"):
        return True
    value = rule.get("pack_size")
    if value in (None, ""):
        return False
    try:
        return int(float(value)) <= 0
    except (TypeError, ValueError):
        return False


def get_rule_int(rule, field_name):
    """Return an integer-like persisted rule field, if present."""
    if not rule:
        return None
    value = rule.get(field_name)
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def get_rule_float(rule, field_name):
    """Return a float-like persisted rule field, if present."""
    if not rule:
        return None
    value = rule.get(field_name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_rule_fields(item, rule):
    """Copy persisted rule fields onto the working item for visibility and later logic."""
    item["reorder_trigger_qty"] = get_rule_int(rule, "reorder_trigger_qty")
    item["reorder_trigger_pct"] = get_rule_float(rule, "reorder_trigger_pct")
    item["minimum_packs_on_hand"] = get_rule_int(rule, "minimum_packs_on_hand")
    item["minimum_packs_on_hand_source"] = "rule" if item["minimum_packs_on_hand"] is not None else None
    item["minimum_cover_days"] = get_rule_float(rule, "minimum_cover_days")
    item["minimum_cover_days_source"] = "rule" if item["minimum_cover_days"] is not None else None
    item["minimum_cover_cycles"] = get_rule_float(rule, "minimum_cover_cycles")
    item["minimum_cover_cycles_source"] = "rule" if item["minimum_cover_cycles"] is not None else None
    item["acceptable_overstock_qty"] = get_rule_int(rule, "acceptable_overstock_qty")
    item["acceptable_overstock_pct"] = get_rule_float(rule, "acceptable_overstock_pct")


def has_pack_trigger_fields(rule):
    """Return True when a saved rule defines trigger-style replenishment fields."""
    return any(
        value is not None and value > 0
        for value in (
            get_rule_int(rule, "reorder_trigger_qty"),
            get_rule_float(rule, "reorder_trigger_pct"),
            get_rule_int(rule, "minimum_packs_on_hand"),
            get_rule_float(rule, "minimum_cover_days"),
            get_rule_float(rule, "minimum_cover_cycles"),
        )
    )


def get_rule_pack_size(rule):
    """Return a persisted pack-size override from a saved rule, if present."""
    if not rule:
        return None
    value = rule.get("pack_size")
    if value in (None, ""):
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
