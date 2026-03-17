import copy
import os
from collections import defaultdict
from tkinter import filedialog, messagebox

import storage
import ui_bulk
from rules import get_rule_pack_size


def build_data_paths(data_dir):
    return {
        "duplicate_whitelist": os.path.join(data_dir, "duplicate_whitelist.txt"),
        "order_history": os.path.join(data_dir, "order_history.json"),
        "order_rules": os.path.join(data_dir, "order_rules.json"),
        "suspense_carry": os.path.join(data_dir, "suspense_carry.json"),
        "sessions": os.path.join(data_dir, "sessions"),
        "vendor_codes": os.path.join(data_dir, "vendor_codes.txt"),
        "vendor_policies": os.path.join(data_dir, "vendor_policies.json"),
        "ignored_items": os.path.join(data_dir, "ignored_items.txt"),
    }


def configure_initial_data_dir(app):
    requested = str(app.app_settings.get("shared_data_dir", "") or "").strip()
    app.update_check_enabled = bool(app.app_settings.get("check_for_updates_on_startup", True))
    if requested:
        normalized = os.path.abspath(requested)
        ok, reason = storage.validate_storage_directory(normalized)
        if ok:
            app.shared_data_dir = normalized
            app.data_dir = normalized
        else:
            app._startup_data_dir_warning = (
                "Shared data folder is unavailable, so the app fell back to local data.\n\n"
                f"Requested folder:\n{normalized}\n\nReason:\n{reason}"
            )
            app.app_settings["shared_data_dir"] = ""
            app._save_app_settings()
    app.data_paths = build_data_paths(app.data_dir)


def load_persistent_state(app, known_vendors):
    dup_whitelist, _ = storage.load_duplicate_whitelist(app._data_path("duplicate_whitelist"), with_meta=True)
    ignored_item_keys, _ = storage.load_ignored_items(app._data_path("ignored_items"), with_meta=True)
    order_rules, _ = storage.load_order_rules_with_meta(app._data_path("order_rules"))
    suspense_carry, _ = storage.load_suspense_carry_with_meta(app._data_path("suspense_carry"))
    vendor_codes, _ = storage.load_vendor_codes(app._data_path("vendor_codes"), known_vendors, with_meta=True)
    vendor_policies, _ = storage.load_vendor_policies_with_meta(app._data_path("vendor_policies"))
    app.dup_whitelist = set(dup_whitelist)
    app.ignored_item_keys = set(ignored_item_keys)
    app.order_rules = dict(order_rules)
    app.suspense_carry = dict(suspense_carry)
    app.vendor_codes_used = list(vendor_codes)
    app.vendor_policies = dict(vendor_policies)
    app._loaded_dup_whitelist = set(app.dup_whitelist)
    app._loaded_ignored_item_keys = set(app.ignored_item_keys)
    app._loaded_order_rules = copy.deepcopy(app.order_rules)
    app._loaded_suspense_carry = copy.deepcopy(app.suspense_carry)
    app._loaded_vendor_codes = list(app.vendor_codes_used)
    app._loaded_vendor_policies = copy.deepcopy(app.vendor_policies)
    app._refresh_data_folder_labels()


def active_data_folder_label(app):
    if app.shared_data_dir:
        return f"Shared Folder: {app.data_dir}"
    return f"Local Data: {app.data_dir}"


def refresh_data_folder_labels(app):
    label_text = app._active_data_folder_label() if hasattr(app, "_active_data_folder_label") else active_data_folder_label(app)
    for attr_name in ("lbl_data_source", "lbl_bulk_data_source", "lbl_assign_data_source", "lbl_review_data_source"):
        if hasattr(app, attr_name):
            getattr(app, attr_name).config(text=label_text)


def rebuild_duplicate_ic_lookup(app):
    duplicate_ic_lookup = defaultdict(set)
    for line_code, item_code in app.inventory_lookup:
        duplicate_ic_lookup[item_code].add(line_code)
    app.duplicate_ic_lookup = {
        item_code: line_codes
        for item_code, line_codes in duplicate_ic_lookup.items()
        if len(line_codes) > 1 and item_code not in app.dup_whitelist
    }


def prune_ignored_items_from_session(app):
    before_counts = (
        len(app.filtered_items),
        len(app.assigned_items),
        len(app.individual_items),
    )
    ui_bulk.replace_filtered_items(app, [
        item for item in app.filtered_items
        if app._ignore_key(item.get("line_code", ""), item.get("item_code", "")) not in app.ignored_item_keys
    ])
    app.assigned_items = [
        item for item in app.assigned_items
        if app._ignore_key(item.get("line_code", ""), item.get("item_code", "")) not in app.ignored_item_keys
    ]
    app.individual_items = [
        item for item in app.individual_items
        if app._ignore_key(item.get("line_code", ""), item.get("item_code", "")) not in app.ignored_item_keys
    ]
    return before_counts != (
        len(app.filtered_items),
        len(app.assigned_items),
        len(app.individual_items),
    )


def has_active_assignment_session(app):
    return bool(app.filtered_items or app.assigned_items or app.individual_items)


def refresh_active_data_state(app, known_vendors, get_rule_key, notify=True):
    app._load_persistent_state()
    app._refresh_vendor_inputs()
    if not app._has_active_assignment_session():
        if notify:
            messagebox.showinfo(
                "Active Data Refreshed",
                "Reloaded shared/local rules, history, vendor codes, ignores, and other saved data from disk.",
            )
        return {"session_updated": False, "ignored_changed_session": False}

    ignored_changed_session = app._prune_ignored_items_from_session()
    app._rebuild_duplicate_ic_lookup()
    try:
        days = app.var_lookback_days.get()
    except Exception:
        days = 14
    app.recent_orders = storage.get_recent_orders(app._data_path("order_history"), days)

    for item in app.filtered_items:
        key = (item["line_code"], item["item_code"])
        rule_pack = get_rule_pack_size(app.order_rules.get(get_rule_key(*key)))
        if rule_pack is not None:
            item["pack_size"] = rule_pack
            item["pack_size_source"] = "rule"
        elif not item.get("pack_size"):
            if hasattr(app, "_resolve_pack_size_with_source"):
                item["pack_size"], item["pack_size_source"] = app._resolve_pack_size_with_source(key)
            else:
                item["pack_size"] = app._resolve_pack_size(key)
        app._recalculate_item(item)

    for item in app.assigned_items:
        app._sync_review_item_to_filtered(item)
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()

    if app.individual_items:
        if not hasattr(app, "assign_index"):
            app.assign_index = 0
        app.assign_index = min(app.assign_index, max(0, len(app.individual_items) - 1))
        if app.individual_items:
            app._populate_assign_item()

    app._apply_bulk_filter()
    app._update_bulk_summary()
    if hasattr(app, "tree"):
        app._populate_review_tab()

    detail = " Current session updated to match the active shared/local data where possible."
    if ignored_changed_session:
        detail += " Ignored items were removed from the current session."
    if notify:
        messagebox.showinfo(
            "Active Data Refreshed",
            "Reloaded shared/local rules, history, vendor codes, ignores, and other saved data from disk." + detail,
        )
    return {"session_updated": True, "ignored_changed_session": ignored_changed_session}


def set_shared_data_folder(app, known_vendors, get_rule_key):
    selected = filedialog.askdirectory(
        title="Select Shared Data Folder",
        initialdir=app.data_dir,
        mustexist=False,
    )
    if not selected:
        return
    normalized = os.path.abspath(selected)
    ok, reason = storage.validate_storage_directory(normalized)
    if not ok:
        messagebox.showerror("Shared Data Folder", f"Cannot use that folder:\n{reason}")
        return
    app.shared_data_dir = normalized
    app.data_dir = normalized
    app.data_paths = app._build_data_paths(app.data_dir)
    app.app_settings["shared_data_dir"] = normalized
    app._save_app_settings()
    result = app._refresh_active_data_state(notify=False)
    if result["session_updated"]:
        messagebox.showinfo(
            "Shared Data Folder Updated",
            "Switched to the shared data folder and refreshed the current session to match the active shared/local data where possible.",
        )


def use_local_data_folder(app, local_data_dir, known_vendors, get_rule_key):
    app.shared_data_dir = ""
    app.data_dir = local_data_dir
    app.data_paths = app._build_data_paths(app.data_dir)
    app.app_settings["shared_data_dir"] = ""
    app._save_app_settings()
    result = app._refresh_active_data_state(notify=False)
    if result["session_updated"]:
        messagebox.showinfo(
            "Local Data Enabled",
            "Switched to local data and refreshed the current session to match the active shared/local data where possible.",
        )
