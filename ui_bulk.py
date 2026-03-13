import tkinter as tk
from tkinter import ttk

from bulk_sheet import BulkSheetView, HAS_TKSHEET, TKSHEET_IMPORT_ERROR
from rules import get_buy_rule_summary


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
    lc_set = set()
    row_ids = []
    rows = []
    for i, item in enumerate(app.filtered_items):
        lc_set.add(item["line_code"])
        row_ids.append(str(i))
        rows.append(list(bulk_row_values(app, item)))

    app.combo_bulk_lc["values"] = ["ALL"] + sorted(lc_set)
    app.combo_bulk_vendor["values"] = app.vendor_codes_used
    update_bulk_summary(app)
    if app.bulk_sheet:
        app.bulk_sheet.set_rows(rows, row_ids)


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
    has_sales = item.get("qty_sold", 0) > 0
    has_susp = item.get("qty_suspended", 0) > 0
    source = "Both" if (has_sales and has_susp) else ("Susp" if has_susp else "Sales")
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


def update_bulk_summary(app):
    total = len(app.filtered_items)
    assigned = sum(1 for item in app.filtered_items if item.get("vendor"))
    unassigned = total - assigned
    review_count = sum(1 for item in app.filtered_items if item.get("status") == "review")
    warning_count = sum(1 for item in app.filtered_items if item.get("status") == "warning")
    parts = [f"{total} total", f"{assigned} assigned", f"{unassigned} unassigned"]
    if review_count:
        parts.append(f"{review_count} review")
    if warning_count:
        parts.append(f"{warning_count} warning")
    app.lbl_bulk_summary.config(text="  ·  ".join(parts))


def _filter_value(app, attr_name, default="ALL"):
    var = getattr(app, attr_name, None)
    if var is None:
        return default
    try:
        return var.get()
    except Exception:
        return default


def flush_pending_bulk_sheet_edit(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet and hasattr(bulk_sheet, "flush_pending_edit"):
        bulk_sheet.flush_pending_edit()


def can_incremental_refresh(app):
    if not getattr(app, "bulk_sheet", None):
        return False
    if getattr(app, "_bulk_sort_col", None):
        return False
    return (
        _filter_value(app, "var_bulk_lc_filter") == "ALL"
        and _filter_value(app, "var_bulk_status_filter") == "ALL"
        and _filter_value(app, "var_bulk_source_filter") == "ALL"
        and _filter_value(app, "var_bulk_item_status") == "ALL"
        and _filter_value(app, "var_bulk_performance_filter") == "ALL"
        and _filter_value(app, "var_bulk_sales_health_filter") == "ALL"
        and _filter_value(app, "var_bulk_attention_filter") == "ALL"
    )


def refresh_bulk_view_after_edit(app, row_ids):
    if not can_incremental_refresh(app):
        app._apply_bulk_filter()
        return False
    if not getattr(app, "bulk_sheet", None):
        return False
    for row_id in row_ids:
        try:
            idx = int(row_id)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(app.filtered_items):
            app.bulk_sheet.refresh_row(str(row_id), app._bulk_row_values(app.filtered_items[idx]))
    return True


def apply_bulk_filter(app):
    flush_pending_bulk_sheet_edit(app)
    lc_filter = _filter_value(app, "var_bulk_lc_filter")
    status_filter = _filter_value(app, "var_bulk_status_filter")
    source_filter = _filter_value(app, "var_bulk_source_filter")
    item_status_filter = _filter_value(app, "var_bulk_item_status")
    performance_filter = _filter_value(app, "var_bulk_performance_filter")
    sales_health_filter = _filter_value(app, "var_bulk_sales_health_filter")
    attention_filter = _filter_value(app, "var_bulk_attention_filter")

    rows = []
    row_ids = []
    for i, item in enumerate(app.filtered_items):
        if lc_filter != "ALL" and item["line_code"] != lc_filter:
            continue
        if status_filter == "Assigned" and not item.get("vendor"):
            continue
        if status_filter == "Unassigned" and item.get("vendor"):
            continue
        if source_filter != "ALL":
            has_sales = item.get("qty_sold", 0) > 0
            has_susp = item.get("qty_suspended", 0) > 0
            item_source = "Both" if (has_sales and has_susp) else ("Susp" if has_susp else "Sales")
            if item_source != source_filter:
                continue
        if item_status_filter != "ALL":
            item_status = item.get("status", "ok")
            if item_status_filter == "OK" and item_status != "ok":
                continue
            if item_status_filter == "Review" and item_status != "review":
                continue
            if item_status_filter == "Warning" and item_status != "warning":
                continue
            if item_status_filter == "No Pack" and "missing_pack" not in item.get("data_flags", []):
                continue
        if performance_filter != "ALL":
            performance = (item.get("performance_profile", "") or "").lower()
            expected = {
                "Top": "top_performer",
                "Steady": "steady",
                "Intermittent": "intermittent",
                "Legacy": "legacy",
            }.get(performance_filter, "")
            if performance != expected:
                continue
        if sales_health_filter != "ALL":
            sales_health = (item.get("sales_health_signal", "") or "").lower()
            if sales_health != sales_health_filter.lower():
                continue
        if attention_filter != "ALL":
            attention = (item.get("reorder_attention_signal", "") or "").lower()
            expected_attention = {
                "Normal": "normal",
                "Missed Reorder": "review_missed_reorder",
            }.get(attention_filter, "")
            if attention != expected_attention:
                continue
        row_ids.append(str(i))
        rows.append(list(bulk_row_values(app, item)))
    if app.bulk_sheet:
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
        row = bulk_row_values(app, item)
        value = row[app.bulk_tree_columns.index(col)]
        try:
            return (0, float(value))
        except Exception:
            return (1, str(value).lower())

    app.filtered_items.sort(key=_sort_key, reverse=reverse)
    apply_bulk_filter(app)
