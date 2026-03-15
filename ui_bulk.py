import json
import tkinter as tk
from tkinter import ttk

from bulk_sheet import BulkSheetView, HAS_TKSHEET, TKSHEET_IMPORT_ERROR
from rules import get_buy_rule_summary


def bulk_row_id(item):
    key = (item.get("line_code", ""), item.get("item_code", ""))
    cached_key = item.get("_bulk_row_id_key")
    cached_row_id = item.get("_bulk_row_id")
    if cached_key == key and cached_row_id:
        return cached_row_id
    row_id = json.dumps([key[0], key[1]], separators=(",", ":"))
    item["_bulk_row_id_key"] = key
    item["_bulk_row_id"] = row_id
    return row_id


def invalidate_bulk_row_index(app):
    app._bulk_row_index_cache = None
    app._bulk_row_index_generation = getattr(app, "_bulk_row_index_generation", 0) + 1


def _build_bulk_row_index(app):
    filtered_items = list(getattr(app, "filtered_items", ()) or ())
    by_row_id = {}
    by_key = {}
    for idx, item in enumerate(filtered_items):
        row_key = bulk_row_id(item)
        key = (item.get("line_code"), item.get("item_code"))
        by_row_id[row_key] = (idx, item)
        by_key[key] = (idx, item)
    cache = {
        "generation": getattr(app, "_bulk_row_index_generation", 0),
        "by_row_id": by_row_id,
        "by_key": by_key,
    }
    app._bulk_row_index_cache = cache
    return cache


def bulk_row_index(app):
    cache = getattr(app, "_bulk_row_index_cache", None)
    generation = getattr(app, "_bulk_row_index_generation", 0)
    if cache and cache.get("generation") == generation:
        return cache
    return _build_bulk_row_index(app)


def find_filtered_item(app, key):
    if key is None:
        return None
    key = (key[0], key[1])
    resolved = bulk_row_index(app).get("by_key", {}).get(key)
    if resolved is None:
        return None
    _idx, item = resolved
    return item


def resolve_bulk_row_id(app, row_id):
    if row_id is None:
        return None, None
    row_id = str(row_id)
    filtered_items = getattr(app, "filtered_items", ()) or ()
    cache = bulk_row_index(app)
    direct = cache.get("by_row_id", {}).get(row_id)
    if direct is not None:
        return direct
    try:
        key = json.loads(row_id)
    except Exception:
        key = None
    if isinstance(key, list) and len(key) == 2:
        key = (key[0], key[1])
        resolved = cache.get("by_key", {}).get(key)
        if resolved is not None:
            return resolved
    try:
        idx = int(row_id)
    except (TypeError, ValueError):
        return None, None
    if 0 <= idx < len(filtered_items):
        return idx, filtered_items[idx]
    return None, None


def build_bulk_tab(app, editable_cols):
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  4. Assign Vendors  ")

    ttk.Label(frame, text="Assign Vendor Codes", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text="Use bulk actions to assign vendors quickly. Suggested Qty is the app's recommendation, Final Qty is what will export, and Why This Qty explains the calculation in plain language.",
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", pady=(2, 8))
    app.lbl_bulk_data_source = ttk.Label(frame, text="", style="Info.TLabel")
    app.lbl_bulk_data_source.pack(anchor="w", pady=(0, 8))
    app._refresh_data_folder_labels()

    top_frame = ttk.Frame(frame)
    top_frame.pack(fill=tk.X, pady=(0, 8))

    app.lbl_bulk_summary = ttk.Label(top_frame, text="", style="Info.TLabel")
    app.lbl_bulk_summary.pack(side=tk.LEFT)

    controls_frame = ttk.Frame(frame)
    controls_frame.pack(fill=tk.X, pady=(0, 8))

    action_frame = ttk.LabelFrame(controls_frame, text="Bulk Actions", padding=8)
    action_frame.pack(side=tk.LEFT, anchor="nw")

    vendor_row = ttk.Frame(action_frame)
    vendor_row.pack(fill=tk.X, pady=2)
    ttk.Label(vendor_row, text="Assign vendor to selected rows:").pack(side=tk.LEFT, padx=4)
    app.var_bulk_vendor = tk.StringVar()
    app.combo_bulk_vendor = ttk.Combobox(vendor_row, textvariable=app.var_bulk_vendor, width=20, font=("Segoe UI", 10))
    app.combo_bulk_vendor.pack(side=tk.LEFT, padx=4)
    app.combo_bulk_vendor.bind("<KeyRelease>", app._bulk_vendor_autocomplete)
    vendor_buttons = [
        ttk.Button(vendor_row, text="Apply to Selected", command=app._bulk_apply_selected),
        ttk.Button(vendor_row, text="Apply to All Visible", command=app._bulk_apply_visible),
        ttk.Button(vendor_row, text="Manage Vendors...", command=app._open_vendor_manager),
    ]
    vendor_buttons[0].pack(side=tk.LEFT, padx=8)
    vendor_buttons[1].pack(side=tk.LEFT, padx=4)
    vendor_buttons[2].pack(side=tk.LEFT, padx=8)

    edit_row = ttk.Frame(action_frame)
    edit_row.pack(fill=tk.X, pady=2)
    bulk_buttons = [
        ttk.Button(edit_row, text="Undo", command=app._bulk_undo),
        ttk.Button(edit_row, text="Redo", command=app._bulk_redo),
        ttk.Button(edit_row, text="Fill Selected Cells", command=app._bulk_fill_selected_cells),
        ttk.Button(edit_row, text="Clear Selected Cells", command=app._bulk_clear_selected_cells),
        ttk.Button(edit_row, text="Bulk Shortcuts...", command=app._show_bulk_shortcuts),
        ttk.Button(edit_row, text="Fit Columns To Window", command=app._bulk_fit_columns),
    ]
    for idx, button in enumerate(bulk_buttons):
        button.pack(side=tk.LEFT, padx=(8 if idx == 0 else 4, 0))

    removal_row = ttk.Frame(action_frame)
    removal_row.pack(fill=tk.X, pady=2)
    removal_buttons = [
        ttk.Button(removal_row, text="Remove Not Needed (On Screen)", command=app._bulk_remove_not_needed_visible),
        ttk.Button(removal_row, text="Remove Not Needed (Filtered)", command=app._bulk_remove_not_needed_filtered),
        ttk.Button(
            removal_row,
            text="Remove Assigned Too (On Screen)",
            command=lambda: app._bulk_remove_not_needed_visible(include_assigned=True),
        ),
        ttk.Button(
            removal_row,
            text="Remove Assigned Too (Filtered)",
            command=lambda: app._bulk_remove_not_needed_filtered(include_assigned=True),
        ),
        ttk.Button(removal_row, text="Add to Ignore List", command=app._ignore_from_bulk),
        ttk.Button(removal_row, text="Undo Last Remove", command=app._undo_last_bulk_removal),
    ]
    for idx, button in enumerate(removal_buttons):
        button.pack(side=tk.LEFT, padx=(8 if idx == 0 else 4, 0))

    filter_frame = ttk.LabelFrame(controls_frame, text="Filters", padding=8)
    filter_frame.pack(side=tk.LEFT, anchor="nw", padx=(16, 0))

    filter_row_1 = ttk.Frame(filter_frame)
    filter_row_1.pack(fill=tk.X, pady=(0, 2))
    ttk.Label(filter_row_1, text="Filter:").pack(side=tk.LEFT, padx=(0, 4))

    ttk.Label(filter_row_1, text="Line Code:").pack(side=tk.LEFT, padx=(8, 2))
    app.var_bulk_lc_filter = tk.StringVar(value="ALL")
    app.combo_bulk_lc = ttk.Combobox(filter_row_1, textvariable=app.var_bulk_lc_filter, state="readonly", width=10)
    app.combo_bulk_lc.pack(side=tk.LEFT, padx=2)
    app.combo_bulk_lc.bind("<<ComboboxSelected>>", lambda e: app._apply_bulk_filter())

    ttk.Label(filter_row_1, text="Status:").pack(side=tk.LEFT, padx=(12, 2))
    app.var_bulk_status_filter = tk.StringVar(value="ALL")
    app.combo_bulk_status = ttk.Combobox(
        filter_row_1,
        textvariable=app.var_bulk_status_filter,
        state="readonly",
        width=14,
        values=["ALL", "Unassigned", "Assigned"],
    )
    app.combo_bulk_status.pack(side=tk.LEFT, padx=2)
    app.combo_bulk_status.bind("<<ComboboxSelected>>", lambda e: app._apply_bulk_filter())

    ttk.Label(filter_row_1, text="Source:").pack(side=tk.LEFT, padx=(12, 2))
    app.var_bulk_source_filter = tk.StringVar(value="ALL")
    app.combo_bulk_source = ttk.Combobox(
        filter_row_1,
        textvariable=app.var_bulk_source_filter,
        state="readonly",
        width=8,
        values=["ALL", "Sales", "Susp", "Both"],
    )
    app.combo_bulk_source.pack(side=tk.LEFT, padx=2)
    app.combo_bulk_source.bind("<<ComboboxSelected>>", lambda e: app._apply_bulk_filter())

    filter_row_2 = ttk.Frame(filter_frame)
    filter_row_2.pack(fill=tk.X)

    ttk.Label(filter_row_2, text="Item Status:").pack(side=tk.LEFT, padx=(0, 2))
    app.var_bulk_item_status = tk.StringVar(value="ALL")
    app.combo_bulk_item_status = ttk.Combobox(
        filter_row_2,
        textvariable=app.var_bulk_item_status,
        state="readonly",
        width=11,
        values=["ALL", "OK", "Review", "Warning", "No Pack"],
    )
    app.combo_bulk_item_status.pack(side=tk.LEFT, padx=2)
    app.combo_bulk_item_status.bind("<<ComboboxSelected>>", lambda e: app._apply_bulk_filter())

    ttk.Label(filter_row_2, text="Performance:").pack(side=tk.LEFT, padx=(12, 2))
    app.var_bulk_performance_filter = tk.StringVar(value="ALL")
    app.combo_bulk_performance = ttk.Combobox(
        filter_row_2,
        textvariable=app.var_bulk_performance_filter,
        state="readonly",
        width=12,
        values=["ALL", "Top", "Steady", "Intermittent", "Legacy"],
    )
    app.combo_bulk_performance.pack(side=tk.LEFT, padx=2)
    app.combo_bulk_performance.bind("<<ComboboxSelected>>", lambda e: app._apply_bulk_filter())

    filter_row_3 = ttk.Frame(filter_frame)
    filter_row_3.pack(fill=tk.X, pady=(2, 0))

    ttk.Label(filter_row_3, text="Sales Health:").pack(side=tk.LEFT, padx=(0, 2))
    app.var_bulk_sales_health_filter = tk.StringVar(value="ALL")
    app.combo_bulk_sales_health = ttk.Combobox(
        filter_row_3,
        textvariable=app.var_bulk_sales_health_filter,
        state="readonly",
        width=12,
        values=["ALL", "Active", "Cooling", "Dormant", "Stale", "Unknown"],
    )
    app.combo_bulk_sales_health.pack(side=tk.LEFT, padx=2)
    app.combo_bulk_sales_health.bind("<<ComboboxSelected>>", lambda e: app._apply_bulk_filter())

    ttk.Label(filter_row_3, text="Attention:").pack(side=tk.LEFT, padx=(12, 2))
    app.var_bulk_attention_filter = tk.StringVar(value="ALL")
    app.combo_bulk_attention = ttk.Combobox(
        filter_row_3,
        textvariable=app.var_bulk_attention_filter,
        state="readonly",
        width=14,
        values=["ALL", "Normal", "Missed Reorder"],
    )
    app.combo_bulk_attention.pack(side=tk.LEFT, padx=2)
    app.combo_bulk_attention.bind("<<ComboboxSelected>>", lambda e: app._apply_bulk_filter())

    ttk.Label(filter_row_3, text="Reorder Cycle:").pack(side=tk.LEFT, padx=(12, 2))
    app.var_reorder_cycle = tk.StringVar(value="Biweekly")
    app.combo_cycle = ttk.Combobox(
        filter_row_3,
        textvariable=app.var_reorder_cycle,
        state="readonly",
        width=10,
        values=["Weekly", "Biweekly", "Monthly"],
    )
    app.combo_cycle.pack(side=tk.LEFT, padx=2)
    app.combo_cycle.bind("<<ComboboxSelected>>", lambda e: app._refresh_suggestions())

    ttk.Label(filter_row_3, text="History (days):").pack(side=tk.LEFT, padx=(12, 2))
    app.var_lookback_days = tk.IntVar(value=14)
    lookback_spin = ttk.Spinbox(filter_row_3, from_=1, to=90, textvariable=app.var_lookback_days, width=4)
    lookback_spin.pack(side=tk.LEFT, padx=2)
    lookback_spin.bind("<Return>", lambda e: app._refresh_recent_orders())
    lookback_spin.bind("<FocusOut>", lambda e: app._refresh_recent_orders())

    status_text = "Active edit column: none | Selected rows: 0" if HAS_TKSHEET else "Bulk sheet unavailable"
    app.lbl_bulk_cell_status = ttk.Label(frame, text=status_text, style="Info.TLabel")
    app.lbl_bulk_cell_status.pack(anchor="w", pady=(0, 4))

    tree_frame = ttk.Frame(frame)
    tree_frame.pack(fill=tk.BOTH, expand=True, pady=4)

    columns = (
        "vendor", "line_code", "item_code", "description", "source",
        "status", "raw_need", "suggested_qty", "final_qty", "buy_rule",
        "qoh", "cur_min", "cur_max", "sug_min", "sug_max",
        "pack_size", "supplier", "why",
    )
    widths = {
        "vendor": 80, "line_code": 48, "item_code": 92, "description": 150,
        "source": 40, "status": 52, "raw_need": 44, "suggested_qty": 54, "final_qty": 64,
        "buy_rule": 72, "qoh": 44, "cur_min": 44, "cur_max": 44,
        "sug_min": 48, "sug_max": 48, "pack_size": 40, "supplier": 72, "why": 180,
    }
    labels = {
        "vendor": "Vendor", "line_code": "LC", "item_code": "Item Code",
        "description": "Description", "source": "Src", "status": "Status",
        "raw_need": "Qty Needed Before Pack", "suggested_qty": "Suggested Qty", "final_qty": "Final Qty",
        "buy_rule": "Buy Rule", "qoh": "QOH", "cur_min": "Min", "cur_max": "Max",
        "sug_min": "Sug Min", "sug_max": "Sug Max", "pack_size": "Pack",
        "supplier": "Supplier", "why": "Why This Qty",
    }

    app.bulk_tree_labels = labels
    app.bulk_tree_columns = columns
    if HAS_TKSHEET:
        app.bulk_sheet = BulkSheetView(app, tree_frame, columns, labels, widths, editable_cols)
        tree_frame.bind(
            "<Configure>",
            lambda e: app.bulk_sheet.resize_to_container(width=e.width, height=e.height) if app.bulk_sheet else None,
        )
        app.root.bind(
            "<Configure>",
            lambda e: app.bulk_sheet.resize_to_container() if app.bulk_sheet else None,
            add="+",
        )
        frame.bind(
            "<Map>",
            lambda e: app.bulk_sheet.resize_to_container() if app.bulk_sheet else None,
            add="+",
        )
        app.notebook.bind(
            "<<NotebookTabChanged>>",
            lambda e: app.bulk_sheet.resize_to_container() if app.bulk_sheet else None,
            add="+",
        )
        app.bulk_sheet.sheet.bind("<Delete>", app._bulk_delete_selected)
        app.bulk_sheet.sheet.bind("<BackSpace>", app._bulk_delete_selected)
        app.bulk_sheet.sheet.bind("<Control-c>", app._bulk_copy_selection)
        app.bulk_sheet.sheet.bind("<Control-C>", app._bulk_copy_selection)
        app.bulk_sheet.sheet.bind("<Control-v>", app._bulk_paste_selection)
        app.bulk_sheet.sheet.bind("<Control-V>", app._bulk_paste_selection)
        app.bulk_sheet.sheet.bind("<Control-a>", app._bulk_select_all)
        app.bulk_sheet.sheet.bind("<Control-A>", app._bulk_select_all)
        app.bulk_sheet.sheet.bind("<Control-z>", app._bulk_undo)
        app.bulk_sheet.sheet.bind("<Control-Z>", app._bulk_undo)
        app.bulk_sheet.sheet.bind("<Control-y>", app._bulk_redo)
        app.bulk_sheet.sheet.bind("<Control-Y>", app._bulk_redo)
        app.bulk_sheet.sheet.bind("<Control-d>", app._bulk_fill_down_selection)
        app.bulk_sheet.sheet.bind("<Control-D>", app._bulk_fill_down_selection)
        app.bulk_sheet.sheet.bind("<Control-r>", app._bulk_fill_right_selection)
        app.bulk_sheet.sheet.bind("<Control-R>", app._bulk_fill_right_selection)
        app.bulk_sheet.sheet.bind("<Control-Return>", app._bulk_apply_current_value_to_selection)
        app.bulk_sheet.sheet.bind("<Control-KP_Enter>", app._bulk_apply_current_value_to_selection)
        app.bulk_sheet.sheet.bind("<F2>", app._bulk_begin_edit)
        app.bulk_sheet.sheet.bind("<Return>", app._bulk_begin_edit)
        app.bulk_sheet.sheet.bind("<Tab>", app._bulk_move_next_editable_cell)
        app.bulk_sheet.sheet.bind("<ISO_Left_Tab>", app._bulk_move_prev_editable_cell)
        app.bulk_sheet.sheet.bind("<Shift-Tab>", app._bulk_move_prev_editable_cell)
        app.bulk_sheet.sheet.bind("<Shift-Up>", app._bulk_extend_selection_up)
        app.bulk_sheet.sheet.bind("<Shift-Down>", app._bulk_extend_selection_down)
        app.bulk_sheet.sheet.bind("<Shift-Left>", app._bulk_extend_selection_left)
        app.bulk_sheet.sheet.bind("<Shift-Right>", app._bulk_extend_selection_right)
        app.bulk_sheet.sheet.bind("<Home>", app._bulk_jump_home)
        app.bulk_sheet.sheet.bind("<End>", app._bulk_jump_end)
        app.bulk_sheet.sheet.bind("<Control-Left>", app._bulk_jump_ctrl_left)
        app.bulk_sheet.sheet.bind("<Control-Right>", app._bulk_jump_ctrl_right)
        app.bulk_sheet.sheet.bind("<Control-Up>", app._bulk_jump_ctrl_up)
        app.bulk_sheet.sheet.bind("<Control-Down>", app._bulk_jump_ctrl_down)
        app.bulk_sheet.sheet.bind("<Double-Button-1>", app._bulk_begin_edit)
        app.bulk_sheet.sheet.bind("<Escape>", app._bulk_clear_selection)
        app.bulk_sheet.sheet.bind("<Button-3>", app.bulk_sheet.handle_right_click, add="+")
        app.bulk_sheet.sheet.bind("<Shift-space>", app._bulk_select_current_row)
        app.bulk_sheet.sheet.bind("<Control-space>", app._bulk_select_current_column)
        app.bulk_sheet.sheet.bind("<ButtonRelease-1>", lambda e: app._update_bulk_sheet_status())
        app.bulk_sheet.sheet.bind("<KeyRelease>", lambda e: app._update_bulk_sheet_status())
        app.bulk_sheet.sheet.popup_menu_add_command("Remove Selected Rows", app._bulk_remove_selected_rows)
        app.bulk_sheet.sheet.popup_menu_add_command("Bulk Edit Selection", app._bulk_begin_edit_from_menu)
        app.bulk_sheet.sheet.popup_menu_add_command("Select Current Row", app._bulk_select_current_row)
        app.bulk_sheet.sheet.popup_menu_add_command("Select Current Column", app._bulk_select_current_column)
        app.bulk_sheet.sheet.popup_menu_add_command("View Item Details", app._view_item_details)
        app.bulk_sheet.sheet.popup_menu_add_command("Edit Buy Rule", app._edit_buy_rule_from_bulk)
        app.bulk_sheet.sheet.popup_menu_add_command("Ignore Item", app._ignore_from_bulk)
        app.bulk_sheet.sheet.popup_menu_add_command("Mark Review Resolved", app._resolve_review_from_bulk)
        app.bulk_sheet.sheet.popup_menu_add_command("Dismiss duplicate warning", app._dismiss_duplicate_from_bulk)
    else:
        app.bulk_sheet = None
        detail = TKSHEET_IMPORT_ERROR or "Unknown import error"
        ttk.Label(
            tree_frame,
            text=(
                "The bulk spreadsheet editor requires the 'tksheet' package.\n"
                f"Install it with: pip install tksheet\n\nImport error: {detail}"
            ),
            style="Warning.TLabel",
            justify=tk.LEFT,
            wraplength=900,
        ).pack(anchor="w", padx=8, pady=8)
        for button in (*vendor_buttons, *bulk_buttons, *removal_buttons):
            button.state(["disabled"])

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill=tk.X, pady=8)

    left_btn_row = ttk.Frame(btn_frame)
    left_btn_row.pack(anchor="w", fill=tk.X)
    ttk.Button(left_btn_row, text="Assign Remaining Individually ->", command=app._go_to_individual).pack(
        side=tk.LEFT, padx=4
    )

    right_btn_row = ttk.Frame(btn_frame)
    right_btn_row.pack(anchor="e", fill=tk.X, pady=(8, 0))
    ttk.Button(
        right_btn_row,
        text="Remove Unassigned & Go to Review ->",
        style="Big.TButton",
        command=app._finish_bulk,
    ).pack(side=tk.RIGHT, padx=4)


def populate_bulk_tree(app):
    sync_bulk_cache_state(app, filtered_items_changed=True)
    metadata = getattr(app, "_bulk_line_code_values", None), getattr(app, "_bulk_summary_counts", None)
    line_codes, counts = metadata
    if not counts or counts.get("total") != len(app.filtered_items) or line_codes is None:
        metadata = sync_bulk_session_metadata(app)
        counts = metadata["counts"]
        line_codes = list(metadata["line_codes"])
    row_ids, rows = build_bulk_sheet_rows(app, app.filtered_items, row_id_factory=lambda _item, idx: str(idx))

    set_combobox_values_if_changed(getattr(app, "combo_bulk_lc", None), ["ALL"] + list(line_codes))
    set_combobox_values_if_changed(getattr(app, "combo_bulk_vendor", None), app.vendor_codes_used)
    update_bulk_summary(app, counts=counts)
    if app.bulk_sheet:
        app.bulk_sheet.set_rows(rows, row_ids)


def item_source(item):
    has_sales = item.get("qty_sold", 0) > 0
    has_susp = item.get("qty_suspended", 0) > 0
    return "Both" if (has_sales and has_susp) else ("Susp" if has_susp else "Sales")


def _bulk_row_render_cache(app):
    cache = getattr(app, "_bulk_row_render_cache", None)
    if cache is None:
        cache = {}
        app._bulk_row_render_cache = cache
    return cache


def prune_bulk_row_render_cache(app, retain_items=None):
    cache = getattr(app, "_bulk_row_render_cache", None)
    if not cache:
        return 0
    if retain_items is None:
        retain_items = getattr(app, "filtered_items", ()) or ()
    retain_row_ids = {bulk_row_id(item) for item in retain_items}
    removed = [row_id for row_id in tuple(cache.keys()) if row_id not in retain_row_ids]
    for row_id in removed:
        cache.pop(row_id, None)
    return len(removed)


def sync_bulk_cache_state(app, *, filtered_items_changed=False, retain_items=None):
    if filtered_items_changed:
        invalidate_bulk_row_index(app)
    return prune_bulk_row_render_cache(app, retain_items=retain_items)


def replace_filtered_items(app, items):
    normalized = list(items or [])
    descriptor = getattr(type(app), "filtered_items", None)
    if isinstance(descriptor, property) and descriptor.fset is not None:
        descriptor.fset(app, normalized)
        return normalized
    setattr(app, "filtered_items", normalized)
    sync_bulk_cache_state(app, filtered_items_changed=True, retain_items=normalized)
    sync_bulk_session_metadata(app, normalized)
    return normalized


def sort_filtered_items(app, *, key=None, reverse=False):
    normalized = list(getattr(app, "filtered_items", ()) or ())
    normalized.sort(key=key, reverse=reverse)
    return replace_filtered_items(app, normalized)


def bulk_row_render_signature(app, item):
    key = (item["line_code"], item["item_code"])
    inventory_lookup = getattr(app, "inventory_lookup", {}) or {}
    inventory = inventory_lookup.get(key, {}) or {}
    rule_key = f"{item['line_code']}:{item['item_code']}"
    order_rules = getattr(app, "order_rules", {}) or {}
    rule = order_rules.get(rule_key) or {}
    cycle_var = getattr(app, "var_reorder_cycle", None)
    cycle = cycle_var.get() if cycle_var and hasattr(cycle_var, "get") else ""
    return (
        item.get("vendor", ""),
        item.get("line_code", ""),
        item.get("item_code", ""),
        item.get("description", ""),
        item_source(item),
        item.get("status", ""),
        item.get("raw_need", item.get("order_qty", 0)),
        item.get("suggested_qty", item.get("raw_need", item.get("order_qty", 0))),
        item.get("final_qty", item.get("order_qty", 0)),
        item.get("pack_size"),
        item.get("why", ""),
        item.get("order_policy", ""),
        inventory.get("supplier", ""),
        inventory.get("qoh", ""),
        inventory.get("min", ""),
        inventory.get("max", ""),
        inventory.get("mo12_sales", ""),
        cycle,
        json.dumps(rule, sort_keys=True, separators=(",", ":")),
    )


def bulk_row_values(app, item):
    key = (item["line_code"], item["item_code"])
    inventory = app.inventory_lookup.get(key, {})
    supplier = inventory.get("supplier", "")
    qoh = inventory.get("qoh", "")
    if qoh not in ("", None):
        qoh = f"{qoh:g}"
    else:
        qoh = ""
    cur_min = inventory.get("min")
    cur_max = inventory.get("max")
    sug_min, sug_max = app._suggest_min_max(key)
    pack_size = item.get("pack_size")
    source = item_source(item)
    status = item.get("status", "").upper()[:6]
    raw_need = item.get("raw_need", item.get("order_qty", 0))
    suggested_qty = item.get("suggested_qty", raw_need)
    final_qty = item.get("final_qty", item.get("order_qty", 0))
    rule_key = f"{item['line_code']}:{item['item_code']}"
    rule = app.order_rules.get(rule_key)
    buy_rule = get_buy_rule_summary(item, rule)
    why = item.get("why", "")
    return (
        item.get("vendor", ""),
        item["line_code"],
        item["item_code"],
        item["description"],
        source,
        status,
        raw_need,
        suggested_qty,
        final_qty,
        buy_rule,
        qoh,
        cur_min if cur_min is not None else "",
        cur_max if cur_max is not None else "",
        sug_min if sug_min is not None else "",
        sug_max if sug_max is not None else "",
        pack_size if pack_size else "",
        supplier,
        why,
    )


def cached_bulk_row_values(app, item):
    row_id = bulk_row_id(item)
    signature = bulk_row_render_signature(app, item)
    cache = _bulk_row_render_cache(app)
    cached = cache.get(row_id)
    if cached and cached[0] == signature:
        return cached[1]
    renderer = getattr(app, "_bulk_row_values", None)
    values = renderer(item) if callable(renderer) else bulk_row_values(app, item)
    cache[row_id] = (signature, values)
    return values


def build_bulk_sheet_rows(app, items, *, row_id_factory=bulk_row_id):
    row_ids = []
    rows = []
    for idx, item in enumerate(items):
        row_ids.append(row_id_factory(item, idx) if row_id_factory is not bulk_row_id else bulk_row_id(item))
        rows.append(list(cached_bulk_row_values(app, item)))
    return row_ids, rows


def set_combobox_values_if_changed(combo, values):
    if combo is None:
        return False
    normalized = tuple(values or ())
    try:
        current = tuple(combo["values"])
    except Exception:
        current = tuple(getattr(combo, "values", ()) or ())
    if current == normalized:
        return False
    combo["values"] = normalized
    return True


def _blank_summary_counts(total=0):
    return {"total": total, "assigned": 0, "review": 0, "warning": 0}


def _accumulate_summary_counts(counts, item, sign=1):
    if item.get("vendor"):
        counts["assigned"] += sign
    if item.get("status") == "review":
        counts["review"] += sign
    if item.get("status") == "warning":
        counts["warning"] += sign


def _recompute_summary_counts(items):
    counts = _blank_summary_counts(total=len(items))
    for item in items:
        _accumulate_summary_counts(counts, item)
    return counts


def build_bulk_session_metadata(items):
    normalized = list(items or [])
    items_by_line_code = {}
    items_by_source = {}
    items_by_line_code_source = {}
    for item in normalized:
        line_code = item.get("line_code", "")
        source = item_source(item)
        if not line_code:
            line_code = ""
        if line_code:
            items_by_line_code.setdefault(line_code, []).append(item)
        items_by_source.setdefault(source, []).append(item)
        items_by_line_code_source.setdefault((line_code, source), []).append(item)
    return {
        "counts": _recompute_summary_counts(normalized),
        "line_codes": tuple(sorted({item.get("line_code", "") for item in normalized if item.get("line_code", "")})),
        "items_by_line_code": {line_code: tuple(group) for line_code, group in items_by_line_code.items()},
        "items_by_source": {source: tuple(group) for source, group in items_by_source.items()},
        "items_by_line_code_source": {key: tuple(group) for key, group in items_by_line_code_source.items()},
    }


def sync_bulk_session_metadata(app, items=None):
    normalized = list(getattr(app, "filtered_items", ()) or ()) if items is None else list(items or [])
    metadata = build_bulk_session_metadata(normalized)
    app._bulk_summary_counts = dict(metadata["counts"])
    app._bulk_line_code_values = list(metadata["line_codes"])
    app._bulk_items_by_line_code = dict(metadata["items_by_line_code"])
    app._bulk_items_by_source = dict(metadata["items_by_source"])
    app._bulk_items_by_line_code_source = dict(metadata["items_by_line_code_source"])
    return metadata


def filtered_candidate_items(app, filter_state):
    filtered_items = getattr(app, "filtered_items", ()) or ()
    if bulk_filter_is_default(filter_state):
        return list(filtered_items)
    line_code = filter_state.get("lc", "ALL")
    source = filter_state.get("source", "ALL")
    line_code_buckets = getattr(app, "_bulk_items_by_line_code", None) or {}
    source_buckets = getattr(app, "_bulk_items_by_source", None) or {}
    combined_buckets = getattr(app, "_bulk_items_by_line_code_source", None) or {}
    if line_code != "ALL" and source != "ALL":
        return list(combined_buckets.get((line_code, source), ()))
    if line_code != "ALL":
        return list(line_code_buckets.get(line_code, ()))
    if source != "ALL":
        return list(source_buckets.get(source, ()))
    return list(filtered_items)


def uses_only_stable_bucket_filters(filter_state):
    return (
        filter_state.get("status", "ALL") == "ALL"
        and filter_state.get("item_status", "ALL") == "ALL"
        and filter_state.get("performance", "ALL") == "ALL"
        and filter_state.get("sales_health", "ALL") == "ALL"
        and filter_state.get("attention", "ALL") == "ALL"
    )


def update_bulk_summary(app, counts=None):
    if counts is None:
        cached = getattr(app, "_bulk_summary_counts", None)
        if cached and cached.get("total") == len(app.filtered_items):
            counts = dict(cached)
        else:
            counts = _recompute_summary_counts(app.filtered_items)
    else:
        counts = dict(counts)
    app._bulk_summary_counts = counts
    total = counts["total"]
    assigned = counts["assigned"]
    review_count = counts["review"]
    warning_count = counts["warning"]
    unassigned = total - assigned
    parts = [f"{total} total", f"{assigned} assigned", f"{unassigned} unassigned"]
    if review_count:
        parts.append(f"{review_count} review")
    if warning_count:
        parts.append(f"{warning_count} warning")
    label = getattr(app, "lbl_bulk_summary", None)
    if label is not None and hasattr(label, "config"):
        label.config(text="  ·  ".join(parts))


def adjust_bulk_summary_for_item_change(app, before_item, after_item):
    cached = getattr(app, "_bulk_summary_counts", None)
    if not cached or cached.get("total") != len(app.filtered_items):
        return False
    counts = dict(cached)
    _accumulate_summary_counts(counts, before_item, sign=-1)
    _accumulate_summary_counts(counts, after_item, sign=1)
    app._bulk_summary_counts = counts
    return True


def _filter_value(app, attr_name, default="ALL"):
    var = getattr(app, attr_name, None)
    if var is None:
        return default
    try:
        return var.get()
    except Exception:
        return default


def bulk_filter_state(app):
    return {
        "lc": _filter_value(app, "var_bulk_lc_filter"),
        "status": _filter_value(app, "var_bulk_status_filter"),
        "source": _filter_value(app, "var_bulk_source_filter"),
        "item_status": _filter_value(app, "var_bulk_item_status"),
        "performance": _filter_value(app, "var_bulk_performance_filter"),
        "sales_health": _filter_value(app, "var_bulk_sales_health_filter"),
        "attention": _filter_value(app, "var_bulk_attention_filter"),
    }


def bulk_filter_is_default(filter_state):
    return all(value == "ALL" for value in filter_state.values())


def item_matches_bulk_filter(item, filter_state):
    if filter_state["lc"] != "ALL" and item["line_code"] != filter_state["lc"]:
        return False
    if filter_state["status"] == "Assigned" and not item.get("vendor"):
        return False
    if filter_state["status"] == "Unassigned" and item.get("vendor"):
        return False
    if filter_state["source"] != "ALL":
        if item_source(item) != filter_state["source"]:
            return False
    if filter_state["item_status"] != "ALL":
        item_status = item.get("status", "ok")
        if filter_state["item_status"] == "OK" and item_status != "ok":
            return False
        if filter_state["item_status"] == "Review" and item_status != "review":
            return False
        if filter_state["item_status"] == "Warning" and item_status != "warning":
            return False
        if filter_state["item_status"] == "No Pack" and "missing_pack" not in item.get("data_flags", []):
            return False
    if filter_state["performance"] != "ALL":
        performance = (item.get("performance_profile", "") or "").lower()
        expected = {
            "Top": "top_performer",
            "Steady": "steady",
            "Intermittent": "intermittent",
            "Legacy": "legacy",
        }.get(filter_state["performance"], "")
        if performance != expected:
            return False
    if filter_state["sales_health"] != "ALL":
        sales_health = (item.get("sales_health_signal", "") or "").lower()
        if sales_health != filter_state["sales_health"].lower():
            return False
    if filter_state["attention"] != "ALL":
        attention = (item.get("reorder_attention_signal", "") or "").lower()
        expected_attention = {
            "Normal": "normal",
            "Missed Reorder": "review_missed_reorder",
        }.get(filter_state["attention"], "")
        if attention != expected_attention:
            return False
    return True


def flush_pending_bulk_sheet_edit(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet and hasattr(bulk_sheet, "flush_pending_edit"):
        bulk_sheet.flush_pending_edit()


def can_incremental_refresh(app):
    if not getattr(app, "bulk_sheet", None):
        return False
    if getattr(app, "_bulk_sort_col", None):
        return False
    return bulk_filter_is_default(bulk_filter_state(app))


def _filter_depends_on_changes(filter_state, changed_cols):
    changed = set(changed_cols or ())
    if not changed:
        return not bulk_filter_is_default(filter_state)
    if filter_state["status"] != "ALL" and "vendor" in changed:
        return True
    if filter_state["item_status"] != "ALL" and changed.intersection({"final_qty", "qoh", "cur_min", "cur_max", "pack_size"}):
        return True
    if filter_state["attention"] != "ALL" and changed.intersection({"final_qty", "qoh", "cur_min", "cur_max", "pack_size"}):
        return True
    return False


def _changed_columns_require_rebuild(app, changed_cols, *, filter_state=None):
    filter_state = filter_state or bulk_filter_state(app)
    changed = {col for col in (changed_cols or ()) if col}
    if not changed:
        return not can_incremental_refresh(app)
    sort_col = getattr(app, "_bulk_sort_col", None)
    if sort_col and _sort_column_depends_on_changes(sort_col, changed):
        return True
    if _filter_depends_on_changes(filter_state, changed):
        return True
    return False


def _sort_column_depends_on_changes(sort_col, changed_cols):
    dependencies = {
        "vendor": {"vendor"},
        "final_qty": {"final_qty", "qoh", "cur_min", "cur_max", "pack_size"},
        "status": {"final_qty", "qoh", "cur_min", "cur_max", "pack_size"},
        "why": {"final_qty", "qoh", "cur_min", "cur_max", "pack_size"},
        "raw_need": {"qoh", "cur_min", "cur_max", "pack_size"},
        "suggested_qty": {"qoh", "cur_min", "cur_max", "pack_size"},
        "buy_rule": {"pack_size"},
        "qoh": {"qoh"},
        "cur_min": {"cur_min"},
        "cur_max": {"cur_max"},
        "sug_min": {"qoh", "cur_min", "cur_max", "pack_size"},
        "sug_max": {"qoh", "cur_min", "cur_max", "pack_size"},
        "pack_size": {"pack_size"},
    }
    return bool(dependencies.get(sort_col, {sort_col}) & set(changed_cols))


def refresh_bulk_view_after_edit(app, row_ids, changed_cols=None):
    filter_state = bulk_filter_state(app)
    if _changed_columns_require_rebuild(app, changed_cols, filter_state=filter_state):
        if _try_targeted_filtered_refresh(app, row_ids, filter_state=filter_state):
            return True
        app._apply_bulk_filter()
        return False
    if not getattr(app, "bulk_sheet", None):
        return False
    for row_id in row_ids:
        idx, item = resolve_bulk_row_id(app, row_id)
        if idx is None or item is None:
            continue
        effective_row_id = str(row_id)
        if effective_row_id not in getattr(app.bulk_sheet, "row_lookup", {}):
            effective_row_id = bulk_row_id(item)
        if effective_row_id in getattr(app.bulk_sheet, "row_lookup", {}):
            app.bulk_sheet.refresh_row(effective_row_id, cached_bulk_row_values(app, item))
    return True


def _try_targeted_filtered_refresh(app, row_ids, *, filter_state):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if not bulk_sheet:
        return False
    if getattr(app, "_bulk_sort_col", None):
        return False
    if bulk_filter_is_default(filter_state):
        return False
    visible_lookup = getattr(bulk_sheet, "row_lookup", {}) or {}
    pending_refreshes = []
    for row_id in row_ids:
        idx, item = resolve_bulk_row_id(app, row_id)
        if idx is None or item is None:
            continue
        effective_row_id = str(row_id)
        if effective_row_id not in visible_lookup:
            effective_row_id = bulk_row_id(item)
        was_visible = effective_row_id in visible_lookup
        matches_now = item_matches_bulk_filter(item, filter_state)
        if was_visible != matches_now:
            return False
        if matches_now:
            pending_refreshes.append((effective_row_id, cached_bulk_row_values(app, item)))
    for effective_row_id, values in pending_refreshes:
        bulk_sheet.refresh_row(effective_row_id, values)
    return True


def apply_bulk_filter(app):
    flush_pending_bulk_sheet_edit(app)
    sync_bulk_cache_state(app)
    filter_state = bulk_filter_state(app)

    counts = getattr(app, "_bulk_summary_counts", None)
    if not counts or counts.get("total") != len(app.filtered_items):
        counts = _recompute_summary_counts(app.filtered_items)
    candidate_items = filtered_candidate_items(app, filter_state)
    if bulk_filter_is_default(filter_state) or uses_only_stable_bucket_filters(filter_state):
        visible_items = candidate_items
    else:
        visible_items = [item for item in candidate_items if item_matches_bulk_filter(item, filter_state)]
    update_bulk_summary(app, counts=counts)
    if app.bulk_sheet:
        row_ids, rows = build_bulk_sheet_rows(app, visible_items)
        app.bulk_sheet.set_rows(rows, row_ids)


def autosize_bulk_tree(app):
    if not getattr(app, "bulk_sheet", None):
        return
    return


def sort_bulk_tree(app, col):
    flush_pending_bulk_sheet_edit(app)
    reverse = getattr(app, "_bulk_sort_reverse", False)
    if getattr(app, "_bulk_sort_col", None) == col:
        reverse = not reverse
    else:
        reverse = False
    app._bulk_sort_col = col
    app._bulk_sort_reverse = reverse

    def _sort_key(item):
        value = bulk_sort_value(app, item, col)
        try:
            return (0, float(value))
        except Exception:
            return (1, str(value).lower())

    sort_filtered_items(app, key=_sort_key, reverse=reverse)
    apply_bulk_filter(app)


def bulk_sort_value(app, item, col):
    key = (item["line_code"], item["item_code"])
    inventory = app.inventory_lookup.get(key, {})
    if col == "vendor":
        return item.get("vendor", "")
    if col == "line_code":
        return item.get("line_code", "")
    if col == "item_code":
        return item.get("item_code", "")
    if col == "description":
        return item.get("description", "")
    if col == "source":
        return item_source(item)
    if col == "status":
        return item.get("status", "").upper()[:6]
    if col == "raw_need":
        return item.get("raw_need", item.get("order_qty", 0))
    if col == "suggested_qty":
        return item.get("suggested_qty", item.get("raw_need", item.get("order_qty", 0)))
    if col == "final_qty":
        return item.get("final_qty", item.get("order_qty", 0))
    if col == "buy_rule":
        rule_key = f"{item['line_code']}:{item['item_code']}"
        rule = app.order_rules.get(rule_key)
        return get_buy_rule_summary(item, rule)
    if col == "qoh":
        return inventory.get("qoh", "")
    if col == "cur_min":
        return inventory.get("min", "")
    if col == "cur_max":
        return inventory.get("max", "")
    if col == "sug_min":
        sug_min, _sug_max = app._suggest_min_max(key)
        return "" if sug_min is None else sug_min
    if col == "sug_max":
        _sug_min, sug_max = app._suggest_min_max(key)
        return "" if sug_max is None else sug_max
    if col == "pack_size":
        return item.get("pack_size", "")
    if col == "supplier":
        return inventory.get("supplier", "")
    if col == "why":
        return item.get("why", "")
    return ""
