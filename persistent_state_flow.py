import copy
from datetime import datetime

import storage


def normalize_vendor_code(value):
    return str(value or "").strip().upper()


def save_vendor_codes(app):
    result = storage.save_vendor_codes(
        app._data_path("vendor_codes"),
        app.vendor_codes_used,
        base_vendor_codes=app._loaded_vendor_codes,
    )
    app.vendor_codes_used = list(result["payload"])
    app._loaded_vendor_codes = list(app.vendor_codes_used)


def save_order_rules(app):
    result = storage.save_order_rules(
        app._data_path("order_rules"),
        app.order_rules,
        base_rules=app._loaded_order_rules,
    )
    app.order_rules = dict(result["payload"])
    app._loaded_order_rules = copy.deepcopy(app.order_rules)


def save_vendor_policies(app):
    result = storage.save_vendor_policies(
        app._data_path("vendor_policies"),
        app.vendor_policies,
        base_policies=app._loaded_vendor_policies,
    )
    app.vendor_policies = dict(result["payload"])
    app._loaded_vendor_policies = copy.deepcopy(app.vendor_policies)


def save_duplicate_whitelist(app):
    result = storage.save_duplicate_whitelist(
        app._data_path("duplicate_whitelist"),
        app.dup_whitelist,
        base_whitelist=app._loaded_dup_whitelist,
    )
    app.dup_whitelist = set(result["payload"])
    app._loaded_dup_whitelist = set(app.dup_whitelist)


def save_ignored_item_keys(app):
    result = storage.save_ignored_items(
        app._data_path("ignored_items"),
        app.ignored_item_keys,
        base_ignored_items=app._loaded_ignored_item_keys,
    )
    app.ignored_item_keys = set(result["payload"])
    app._loaded_ignored_item_keys = set(app.ignored_item_keys)


def get_suspense_carry_qty(app, key):
    entry = app.suspense_carry.get(key, {})
    try:
        return max(0, int(float(entry.get("qty", 0))))
    except Exception:
        return 0


def persist_suspense_carry(app, write_debug):
    next_carry = {}
    current_stamp = datetime.now().isoformat()
    for item in app.filtered_items:
        key = (item["line_code"], item["item_code"])
        prior_qty = app._get_suspense_carry_qty(key)
        sales_qty = max(0, int(item.get("qty_sold", 0) or 0))
        remaining_prior = max(0, prior_qty - sales_qty)
        newly_covered = 0
        if item.get("vendor"):
            ordered_qty = max(0, int(item.get("final_qty", item.get("order_qty", 0)) or 0))
            newly_covered = min(ordered_qty, max(0, int(item.get("effective_qty_suspended", 0) or 0)))
        next_qty = remaining_prior + newly_covered
        if next_qty > 0:
            next_carry[key] = {"qty": next_qty, "updated_at": current_stamp}
    app.suspense_carry = next_carry
    result = storage.save_suspense_carry(
        app._data_path("suspense_carry"),
        app.suspense_carry,
        base_carry=app._loaded_suspense_carry,
    )
    app.suspense_carry = dict(result["payload"])
    app._loaded_suspense_carry = copy.deepcopy(app.suspense_carry)
    if result.get("conflict"):
        write_debug(
            "suspense_carry.merge_conflict",
            path=app._data_path("suspense_carry"),
            merged_entries=len(app.suspense_carry),
        )
    return result


def remember_vendor_code(app, vendor):
    normalized = app._normalize_vendor_code(vendor)
    if not normalized:
        return ""
    if normalized not in app.vendor_codes_used:
        app.vendor_codes_used.append(normalized)
        app.vendor_codes_used.sort()
        app._save_vendor_codes()
        app._refresh_vendor_inputs()
    return normalized


def rename_vendor_code(app, old_vendor, new_vendor):
    old_normalized = app._normalize_vendor_code(old_vendor)
    new_normalized = app._normalize_vendor_code(new_vendor)
    if not old_normalized or not new_normalized:
        return ""

    for collection_name in ("filtered_items", "individual_items", "assigned_items"):
        collection = getattr(app, collection_name, [])
        for item in collection:
            if app._normalize_vendor_code(item.get("vendor", "")) == old_normalized:
                item["vendor"] = new_normalized

    if old_normalized in getattr(app, "vendor_policies", {}):
        policy = copy.deepcopy(app.vendor_policies.get(old_normalized, {}))
        app.vendor_policies.pop(old_normalized, None)
        app.vendor_policies[new_normalized] = policy

    app.vendor_codes_used = [code for code in app.vendor_codes_used if code != old_normalized]
    if new_normalized not in app.vendor_codes_used:
        app.vendor_codes_used.append(new_normalized)
    app.vendor_codes_used.sort()
    app._save_vendor_codes()
    if hasattr(app, "_save_vendor_policies"):
        app._save_vendor_policies()
    app._refresh_vendor_inputs()
    return new_normalized
