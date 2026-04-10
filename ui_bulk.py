import json
import tkinter as tk
from tkinter import ttk

import perf_trace
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


from bulk_cache import BulkCacheState


def invalidate_bulk_row_index(app):
    BulkCacheState.get(app).invalidate_row_index()
    app._bulk_row_index_cache = None
    app._bulk_row_index_generation = getattr(app, "_bulk_row_index_generation", 0) + 1


def invalidate_bulk_filter_result_cache(app):
    BulkCacheState.get(app).invalidate_filter_result()
    app._bulk_filter_result_cache = None
    app._bulk_filter_result_generation = getattr(app, "_bulk_filter_result_generation", 0) + 1


def invalidate_bulk_visible_rows_cache(app):
    BulkCacheState.get(app).invalidate_visible_rows()
    app._bulk_visible_rows_cache = None
    app._bulk_visible_rows_generation = getattr(app, "_bulk_visible_rows_generation", 0) + 1


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

    # Assignment progress bar
    app._bulk_progress = ttk.Progressbar(top_frame, length=160, mode="determinate")
    app._bulk_progress.pack(side=tk.LEFT, padx=(12, 4))
    app._bulk_progress_label = ttk.Label(top_frame, text="", style="Info.TLabel")
    app._bulk_progress_label.pack(side=tk.LEFT)

    controls_frame = ttk.Frame(frame)
    controls_frame.pack(fill=tk.X, pady=(0, 8))

    action_frame = ttk.LabelFrame(controls_frame, text="Actions", padding=8)
    action_frame.pack(side=tk.LEFT, anchor="nw")

    # ── Primary actions row 1: assign + remove ──
    primary_row = ttk.Frame(action_frame)
    primary_row.pack(fill=tk.X, pady=2)
    ttk.Label(primary_row, text="Vendor:").pack(side=tk.LEFT, padx=(0, 4))
    app.var_bulk_vendor = tk.StringVar()
    app.combo_bulk_vendor = ttk.Combobox(primary_row, textvariable=app.var_bulk_vendor, width=16, font=("Segoe UI", 10))
    app.combo_bulk_vendor.pack(side=tk.LEFT, padx=(0, 4))
    app.combo_bulk_vendor.bind("<KeyRelease>", app._bulk_vendor_autocomplete)
    ttk.Button(primary_row, text="Apply to Selected", command=app._bulk_apply_selected).pack(side=tk.LEFT, padx=4)
    ttk.Button(primary_row, text="Apply to All Visible", command=app._bulk_apply_visible).pack(side=tk.LEFT, padx=4)
    ttk.Separator(primary_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8)
    ttk.Button(primary_row, text="Remove Not Needed", command=app._bulk_remove_not_needed_filtered).pack(side=tk.LEFT, padx=4)
    ttk.Button(primary_row, text="Undo Remove", command=app._undo_last_bulk_removal).pack(side=tk.LEFT, padx=4)
    ttk.Separator(primary_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8)
    ttk.Button(primary_row, text="Undo", command=app._bulk_undo).pack(side=tk.LEFT, padx=2)
    ttk.Button(primary_row, text="Redo", command=app._bulk_redo).pack(side=tk.LEFT, padx=2)
    ttk.Separator(primary_row, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8)
    ttk.Button(primary_row, text="Batch Edit Rules", command=app._edit_rule_for_selection).pack(side=tk.LEFT, padx=2)

    # Vendor suggestion on its own line so it doesn't push buttons off-screen
    app._vendor_suggestion_label = ttk.Label(action_frame, text="", style="Info.TLabel")
    app._vendor_suggestion_label.pack(anchor="w", padx=4)

    # ── Expandable advanced actions ──
    app._more_actions_visible = False
    _more_frame = ttk.Frame(action_frame)

    def _toggle_more_actions():
        if app._more_actions_visible:
            _more_frame.pack_forget()
            _more_toggle.configure(text="▸ More Actions")
        else:
            _more_frame.pack(fill=tk.X, pady=(4, 0))
            _more_toggle.configure(text="▾ More Actions")
        app._more_actions_visible = not app._more_actions_visible

    _more_toggle = ttk.Button(action_frame, text="▸ More Actions", command=_toggle_more_actions)
    _more_toggle.pack(anchor="w", pady=(4, 0))

    # Advanced row 1: vendor management
    adv_row1 = ttk.Frame(_more_frame)
    adv_row1.pack(fill=tk.X, pady=1)
    for text, cmd in [
        ("Manage Vendors...", app._open_vendor_manager),
        ("Vendor Review...", app._open_vendor_review),
        ("Supplier Map...", app._open_supplier_map),
        ("Fill Selected", app._bulk_fill_selected_cells),
        ("Clear Selected", app._bulk_clear_selected_cells),
        ("Fit Columns", app._bulk_fit_columns),
    ]:
        ttk.Button(adv_row1, text=text, command=cmd).pack(side=tk.LEFT, padx=2)

    # Advanced row 2: removal & maintenance
    adv_row2 = ttk.Frame(_more_frame)
    adv_row2.pack(fill=tk.X, pady=1)
    for text, cmd in [
        ("Remove Not Needed (On Screen)", app._bulk_remove_not_needed_visible),
        ("Remove Assigned Too", lambda: app._bulk_remove_not_needed_filtered(include_assigned=True)),
        ("Add to Ignore List", app._ignore_from_bulk),
        ("Manage Ignored", app._open_ignored_items_manager),
        ("Skip Cleanup...", app._open_skip_actions),
        ("QOH Changes...", app._open_qoh_review),
        ("Clear Notes", app._clear_notes_for_selected),
    ]:
        ttk.Button(adv_row2, text=text, command=cmd).pack(side=tk.LEFT, padx=2)

    # Advanced row 3: rules
    adv_row3 = ttk.Frame(_more_frame)
    adv_row3.pack(fill=tk.X, pady=1)
    for text, cmd in [
        ("Export Rules CSV", app._export_order_rules_csv),
        ("Import Rules CSV", app._import_order_rules_csv),
        ("Bulk Shortcuts...", app._show_bulk_shortcuts),
    ]:
        ttk.Button(adv_row3, text=text, command=cmd).pack(side=tk.LEFT, padx=2)

    # ── Quick filter presets (pill buttons) ──
    filter_outer = ttk.Frame(controls_frame)
    filter_outer.pack(side=tk.LEFT, anchor="nw", padx=(16, 0))

    quick_filter_row = ttk.Frame(filter_outer)
    quick_filter_row.pack(fill=tk.X, pady=(0, 4))
    ttk.Label(quick_filter_row, text="Quick:", style="Info.TLabel").pack(side=tk.LEFT, padx=(0, 4))

    def _quick_filter(status="ALL", item_status="ALL", attention="ALL"):
        """Apply a quick filter preset."""
        try:
            app.var_bulk_status_filter.set(status)
        except Exception:
            pass
        try:
            app.var_bulk_item_status.set(item_status)
        except Exception:
            pass
        try:
            app.var_bulk_attention_filter.set(attention)
        except Exception:
            pass
        app._apply_bulk_filter()

    for label, kwargs in [
        ("All", {}),
        ("Unassigned", {"status": "Unassigned"}),
        ("Needs Review", {"item_status": "Review"}),
        ("Warnings", {"item_status": "Warning"}),
        ("High Risk", {"attention": "High Risk"}),
    ]:
        ttk.Button(quick_filter_row, text=label, command=lambda kw=kwargs: _quick_filter(**kw)).pack(side=tk.LEFT, padx=2)

    app._filter_badge_var = tk.StringVar(value="Filters")
    filter_frame = ttk.LabelFrame(filter_outer, text="Filters", padding=8)
    filter_frame.pack(fill=tk.X)

    def _update_filter_badge():
        """Update the Filters label to show active filter count."""
        fs = bulk_filter_state(app)
        active = sum(1 for k, v in fs.items() if v and v != "ALL" and k != "text")
        if fs.get("text"):
            active += 1
        label = f"Filters ({active})" if active > 0 else "Filters"
        try:
            filter_frame.configure(text=label)
        except Exception:
            pass
    app._update_filter_badge = _update_filter_badge

    filter_row_1 = ttk.Frame(filter_frame)
    filter_row_1.pack(fill=tk.X, pady=(0, 2))
    ttk.Label(filter_row_1, text="Filter:").pack(side=tk.LEFT, padx=(0, 4))

    ttk.Label(filter_row_1, text="Search:").pack(side=tk.LEFT, padx=(0, 2))
    app.var_bulk_text_filter = tk.StringVar(value="")
    app.entry_bulk_text_filter = ttk.Entry(filter_row_1, textvariable=app.var_bulk_text_filter, width=18)
    app.entry_bulk_text_filter.pack(side=tk.LEFT, padx=(0, 4))
    # Live filter on every keystroke; matches item code, description, supplier
    app.entry_bulk_text_filter.bind("<KeyRelease>", lambda e: app._apply_bulk_filter())

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
        values=["ALL", "OK", "Review", "Warning", "No Pack", "Skip", "Dead Stock"],
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
        values=["ALL", "Normal", "Missed Reorder", "High Risk"],
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

    filter_row_4 = ttk.Frame(filter_frame)
    filter_row_4.pack(fill=tk.X, pady=(2, 0))

    ttk.Label(filter_row_4, text="Preset:").pack(side=tk.LEFT, padx=(0, 2))
    app.var_bulk_preset = tk.StringVar(value="")
    app.combo_bulk_preset = ttk.Combobox(
        filter_row_4,
        textvariable=app.var_bulk_preset,
        state="readonly",
        width=18,
        values=[""],
    )
    app.combo_bulk_preset.pack(side=tk.LEFT, padx=2)
    # Applying a preset must NOT trigger save_bulk_filter_sort_state automatically
    app.combo_bulk_preset.bind(
        "<<ComboboxSelected>>",
        lambda e: apply_bulk_filter_preset(app, app.var_bulk_preset.get()) if app.var_bulk_preset.get() else None,
    )

    ttk.Button(
        filter_row_4,
        text="Save Preset\u2026",
        command=lambda: _save_preset_dialog(app),
    ).pack(side=tk.LEFT, padx=(8, 2))

    ttk.Button(
        filter_row_4,
        text="Delete Preset",
        command=lambda: delete_bulk_filter_preset(app, app.var_bulk_preset.get()) if app.var_bulk_preset.get() else None,
    ).pack(side=tk.LEFT, padx=2)

    status_text = "Active edit column: none | Selected rows: 0" if HAS_TKSHEET else "Bulk sheet unavailable"
    app.lbl_bulk_cell_status = ttk.Label(frame, text=status_text, style="Info.TLabel")
    app.lbl_bulk_cell_status.pack(anchor="w", pady=(0, 4))

    # ── Inline tips bar (dismissible, persisted) ──
    tips_dismissed = app.app_settings.get("bulk_tips_dismissed", False) if hasattr(app, "app_settings") else False
    if not tips_dismissed:
        tips_frame = ttk.Frame(frame)
        tips_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            tips_frame,
            text="💡  Click column headers to sort  ·  Right-click headers to show/hide columns  ·  F2 to edit  ·  Press ? for all shortcuts",
            font=("Segoe UI", 9), bg="#2a2a40", fg="#8898b0",
            padx=10, pady=5, anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _dismiss_tips():
            tips_frame.pack_forget()
            if hasattr(app, "app_settings"):
                app.app_settings["bulk_tips_dismissed"] = True
                if hasattr(app, "_save_app_settings"):
                    app._save_app_settings()

        ttk.Button(tips_frame, text="✕", command=_dismiss_tips, width=3).pack(side=tk.RIGHT, padx=4)

    # ── Vendor worksheet tabs + grid area ──
    workspace = ttk.Frame(frame)
    workspace.pack(fill=tk.BOTH, expand=True, pady=4)

    # Vendor worksheet selector — combobox instead of tabs (scales to 178+ vendors)
    vendor_bar = ttk.Frame(workspace)
    vendor_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 4))
    ttk.Label(vendor_bar, text="View:", style="Info.TLabel").pack(side=tk.LEFT, padx=(0, 4))
    app.var_vendor_worksheet = tk.StringVar(value="All Items")
    app._vendor_worksheet_combo = ttk.Combobox(
        vendor_bar, textvariable=app.var_vendor_worksheet,
        state="readonly", width=28, font=("Segoe UI", 10),
    )
    app._vendor_worksheet_combo.pack(side=tk.LEFT, padx=(0, 8))
    app._vendor_worksheet_values = ["All Items", "Overview", "Unassigned", "Exceptions"]
    app._vendor_worksheet_combo["values"] = app._vendor_worksheet_values

    def _on_vendor_worksheet_changed(_event=None):
        from debug_log import write_debug as _wd
        choice = app.var_vendor_worksheet.get().strip()
        vendor = choice.split(" (")[0].strip() if " (" in choice else choice
        _wd("vendor_worksheet.changed", choice=choice, vendor=vendor)
        if choice == "Overview":
            _show_overview_panel(app)
            return
        _hide_overview_panel(app)
        if vendor == "All Items":
            app.var_bulk_vendor_filter_internal = ""
            try:
                app.var_bulk_status_filter.set("ALL")
                app.var_bulk_item_status.set("ALL")
            except Exception:
                pass
        elif vendor == "Unassigned":
            app.var_bulk_vendor_filter_internal = ""
            try:
                app.var_bulk_status_filter.set("Unassigned")
            except Exception:
                pass
        elif vendor == "Exceptions":
            app.var_bulk_vendor_filter_internal = ""
            try:
                app.var_bulk_status_filter.set("ALL")
                app.var_bulk_item_status.set("Review")
            except Exception:
                pass
        else:
            app.var_bulk_vendor_filter_internal = vendor
            try:
                app.var_bulk_status_filter.set("ALL")
                app.var_bulk_item_status.set("ALL")
            except Exception:
                pass
        _wd("vendor_worksheet.applying_filter", vendor_tab=app.var_bulk_vendor_filter_internal)
        app._apply_bulk_filter()

    app._vendor_worksheet_combo.bind("<<ComboboxSelected>>", _on_vendor_worksheet_changed)
    app.var_bulk_vendor_filter_internal = ""

    # Overview panel (hidden by default, shown when "Overview" is selected)
    app._overview_panel = ttk.Frame(workspace)
    app._overview_visible = False

    tree_frame = ttk.Frame(workspace)
    tree_frame.pack(fill=tk.BOTH, expand=True)
    app._bulk_grid_tree_frame = tree_frame

    columns = (
        "vendor", "line_code", "item_code", "description", "source",
        "status", "raw_need", "suggested_qty", "final_qty", "buy_rule",
        "qoh", "cur_min", "cur_max", "sug_min", "sug_max",
        "pack_size", "supplier", "why", "notes", "risk",
    )
    widths = {
        "vendor": 80, "line_code": 48, "item_code": 92, "description": 150,
        "source": 40, "status": 52, "raw_need": 44, "suggested_qty": 54, "final_qty": 64,
        "buy_rule": 72, "qoh": 44, "cur_min": 44, "cur_max": 44,
        "sug_min": 48, "sug_max": 48, "pack_size": 40, "supplier": 72, "why": 180,
        "notes": 100, "risk": 44,
    }
    labels = {
        "vendor": "Vendor", "line_code": "LC", "item_code": "Item Code",
        "description": "Description", "source": "Src", "status": "Status",
        "raw_need": "Qty Needed Before Pack", "suggested_qty": "Suggested Qty", "final_qty": "Final Qty",
        "buy_rule": "Buy Rule", "qoh": "QOH", "cur_min": "Min", "cur_max": "Max",
        "sug_min": "Sug Min", "sug_max": "Sug Max", "pack_size": "Pack",
        "supplier": "Supplier", "why": "Why This Qty", "notes": "Notes", "risk": "Risk",
    }

    app.bulk_tree_labels = labels
    app.bulk_tree_columns = columns
    if HAS_TKSHEET:
        app.bulk_sheet = BulkSheetView(app, tree_frame, columns, labels, widths, editable_cols)
        # Default hidden columns — reduce visual clutter for ADHD-friendly view.
        # Operator can show them via right-click on column headers.
        app._hidden_columns = {"raw_need", "sug_min", "sug_max", "source", "supplier", "risk", "buy_rule", "cur_min", "cur_max"}
        _apply_column_visibility(app)
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
        # Header click to sort, double-click to auto-size
        ch = getattr(app.bulk_sheet.sheet, "CH", None)
        if ch is not None:
            ch.bind("<Button-1>", lambda e: _header_click_sort(app, e), add="+")
            ch.bind("<Double-Button-1>", lambda e: _header_double_click_autosize(app, e))
            ch.bind("<Button-3>", lambda e: _header_right_click_columns(app, e))
        app.bulk_sheet.sheet.bind("<Delete>", app._bulk_delete_selected)
        app.bulk_sheet.sheet.bind("<BackSpace>", app._bulk_delete_selected)
        app.bulk_sheet.sheet.bind("<Control-c>", app._bulk_copy_selection)
        app.bulk_sheet.sheet.bind("<Control-C>", app._bulk_copy_selection)
        app.bulk_sheet.sheet.bind("<Control-v>", app._bulk_paste_selection)
        app.bulk_sheet.sheet.bind("<Control-V>", app._bulk_paste_selection)
        app.bulk_sheet.sheet.bind("<Control-a>", app._bulk_select_all)
        app.bulk_sheet.sheet.bind("<Control-A>", app._bulk_select_all)
        app.bulk_sheet.sheet.bind("<Control-Shift-a>", app._bulk_select_all_rows)
        app.bulk_sheet.sheet.bind("<Control-Shift-A>", app._bulk_select_all_rows)
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
        app.bulk_sheet.sheet.bind("<Return>", lambda e: app._view_item_details())
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
        app.bulk_sheet.sheet.bind("?", lambda e: _show_shortcut_overlay(app))
        app.bulk_sheet.sheet.bind("<question>", lambda e: _show_shortcut_overlay(app))
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


@perf_trace.timed("ui_bulk.populate_bulk_tree")
def populate_bulk_tree(app):
    perf_trace.stamp("populate_bulk_tree.stage", stage="begin")
    sync_bulk_cache_state(app)
    metadata = getattr(app, "_bulk_line_code_values", None), getattr(app, "_bulk_summary_counts", None)
    line_codes, counts = metadata
    if not counts or counts.get("total") != len(app.filtered_items) or line_codes is None:
        with perf_trace.span("populate_bulk_tree.sync_metadata"):
            metadata = sync_bulk_session_metadata(app)
        counts = metadata["counts"]
        line_codes = list(metadata["line_codes"])
    visible_scope = ("populate", len(app.filtered_items))
    cached_rows = cached_bulk_visible_rows(app, visible_scope)
    if cached_rows is None:
        row_ids, rows = build_bulk_sheet_rows(app, app.filtered_items, row_id_factory=lambda _item, idx: str(idx))
        with perf_trace.span("populate_bulk_tree.store_visible_rows"):
            store_bulk_visible_rows(app, visible_scope, row_ids, rows)
    else:
        row_ids, rows = cached_rows
    perf_trace.stamp("populate_bulk_tree.stage", stage="rows_ready", count=len(rows))

    with perf_trace.span("populate_bulk_tree.combobox_values"):
        set_combobox_values_if_changed(getattr(app, "combo_bulk_lc", None), ["ALL"] + list(line_codes))
        set_combobox_values_if_changed(getattr(app, "combo_bulk_vendor", None), app.vendor_codes_used)
    with perf_trace.span("populate_bulk_tree.update_summary"):
        update_bulk_summary(app, counts=counts)
    if app.bulk_sheet:
        with perf_trace.span("populate_bulk_tree.sheet_set_rows", rows=len(rows)):
            app.bulk_sheet.set_rows(rows, row_ids)
    perf_trace.stamp("populate_bulk_tree.stage", stage="done")


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


def invalidate_bulk_row_render_entries(app, row_ids):
    cache = getattr(app, "_bulk_row_render_cache", None)
    if not cache:
        return 0
    removed = 0
    for row_id in tuple(str(row_id) for row_id in (row_ids or ()) if row_id is not None):
        if cache.pop(row_id, None) is not None:
            removed += 1
    return removed


def sync_bulk_cache_state(app, *, filtered_items_changed=False, retain_items=None):
    if filtered_items_changed:
        invalidate_bulk_row_index(app)
        invalidate_bulk_filter_result_cache(app)
        # v0.8.10: bump render generation on any filtered_items
        # replacement so cached row tuples are invalidated in one op
        bump_bulk_row_render_generation(app)
        invalidate_bulk_visible_rows_cache(app)
    return prune_bulk_row_render_cache(app, retain_items=retain_items)


def rebuild_bulk_metadata_after_inplace_recalc(app):
    """Refresh the bulk-grid bucket index after an in-place recalc loop.

    Several flows (`reorder_flow.refresh_suggestions`,
    `reorder_flow.refresh_recent_orders`,
    `reorder_flow.normalize_items_to_cycle`,
    `data_folder_flow.refresh_active_data_state`) mutate
    `app.filtered_items` in place instead of replacing it.
    `replace_filtered_items` (which would normally rebuild the bucket
    index and invalidate the filter caches) is therefore never
    called, so the next bulk filter pass sees stale Item Status /
    Attention buckets.

    This is the v0.6.3 / v0.6.4 / v0.7.4 family of bugs on the
    *recalc* surfaces.  Call this helper at the end of any flow that
    mutates items in place before invoking `_apply_bulk_filter`.
    """
    items = list(getattr(app, "filtered_items", ()) or ())
    sync_bulk_session_metadata(app, items)
    sync_bulk_cache_state(app, filtered_items_changed=True, retain_items=items)


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
        # stockout_risk_score is rendered as the Risk column — must be
        # in the signature so a recalculation that shifts risk
        # invalidates the cached row.  Without this the bulk grid keeps
        # showing the old risk percentage after a QOH edit / cycle change.
        item.get("stockout_risk_score"),
        inventory.get("supplier", ""),
        inventory.get("qoh", ""),
        inventory.get("min", ""),
        inventory.get("max", ""),
        inventory.get("mo12_sales", ""),
        cycle,
        json.dumps(rule, sort_keys=True, separators=(",", ":")),
    )


_EMPTY_INV: dict = {}


def _short_why(item):
    """Build a concise why summary for the grid. Full why stays in tooltip."""
    raw = item.get("raw_need", 0) or 0
    suggested = item.get("suggested_qty", 0) or 0
    final = item.get("final_qty", 0) or 0
    pack = item.get("pack_size")
    policy = item.get("order_policy", "")
    status = item.get("status", "")
    inv = item.get("inventory") or {}
    qoh = inv.get("qoh", 0) or 0
    target = item.get("target_stock", 0) or 0
    position = item.get("inventory_position", 0) or 0

    if status == "skip" or (raw <= 0 and final <= 0):
        if item.get("stale_demand_below_threshold"):
            ann = item.get("annualized_demand", 0)
            return f"Very low demand ({ann:.1f}/yr) — not worth ordering"
        if position >= target and target > 0:
            return f"Stock OK ({int(position)} on hand, target {int(target)})"
        return "No order needed"
    if policy == "manual_only":
        reason = item.get("recency_review_bucket", "")
        if reason == "stale_or_likely_dead":
            return "Needs review — may be dead stock"
        if reason == "new_or_sparse":
            return "Needs review — new or low-volume item"
        if reason == "receipt_heavy_unverified":
            return "Needs review — more received than sold"
        return "Needs review before ordering"
    if policy in ("reel_review", "large_pack_review"):
        return f"Needs review — large pack ({pack or '?'} per pack, need {raw})"

    parts = []
    if raw > 0:
        parts.append(f"Low stock: have {int(position)}, need {int(target)}")
    if suggested != raw and suggested > 0 and pack:
        parts.append(f"ordering {suggested} (pack of {pack})")
    elif suggested > 0:
        parts.append(f"ordering {suggested}")

    if item.get("zero_demand_min_protection"):
        parts.append("⚠ no recent sales, ordering to min")
    if item.get("reorder_trigger_high_vs_max"):
        parts.append("⚠ trigger much higher than max")

    return " → ".join(parts) if parts else item.get("why", "")[:80]


def bulk_row_values(app, item):
    line_code = item["line_code"]
    item_code = item["item_code"]
    key = (line_code, item_code)
    # v0.8.12: shared empty-dict sentinel avoids a per-call allocation
    # on 59K first-paint calls.
    inventory = app.inventory_lookup.get(key) or _EMPTY_INV
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
    rule = app.order_rules.get(f"{line_code}:{item_code}")
    buy_rule = get_buy_rule_summary(item, rule)
    why = _short_why(item)
    notes = item.get("notes", "")
    risk_score = item.get("stockout_risk_score")
    risk_display = f"{int(round(risk_score * 100))}%" if isinstance(risk_score, float) else ""
    return (
        item.get("vendor", ""),
        line_code,
        item_code,
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
        notes,
        risk_display,
    )


def _bulk_row_render_generation(app):
    return getattr(app, "_bulk_row_render_generation_counter", 0)


def bump_bulk_row_render_generation(app):
    """Invalidate every cached row render tuple in a single O(1) op.

    v0.8.10: row render cache is now generation-keyed — cache entries
    are `(generation, values)` and a hit just compares two ints.
    Previously the cache stored `(signature, values)` and every hit
    recomputed the signature (~280 ms on 59K items for every filter
    change).  Generation-bumping moves the invalidation cost from
    per-render to per-edit.
    """
    app._bulk_row_render_generation_counter = _bulk_row_render_generation(app) + 1


def cached_bulk_row_values(app, item):
    row_id = bulk_row_id(item)
    cache = _bulk_row_render_cache(app)
    generation = _bulk_row_render_generation(app)
    cached = cache.get(row_id)
    if cached is not None and cached[0] == generation:
        return cached[1]
    renderer = getattr(app, "_bulk_row_values", None)
    values = renderer(item) if callable(renderer) else bulk_row_values(app, item)
    cache[row_id] = (generation, values)
    return values


@perf_trace.timed("ui_bulk.build_bulk_sheet_rows")
def build_bulk_sheet_rows(app, items, *, row_id_factory=bulk_row_id):
    # v0.8.12: hoist the cache + renderer lookups to locals.  Inside
    # the 59K-row loop, every attribute access was a LOAD_ATTR chain;
    # stashing them as locals cuts the per-row dispatch cost.
    cache = _bulk_row_render_cache(app)
    generation = _bulk_row_render_generation(app)
    renderer = getattr(app, "_bulk_row_values", None)
    if not callable(renderer):
        renderer = lambda i, _app=app: bulk_row_values(_app, i)
    default_row_id = row_id_factory is bulk_row_id
    row_ids = []
    rows = []
    local_bulk_row_id = bulk_row_id
    row_ids_append = row_ids.append
    rows_append = rows.append
    _build_hay = _build_text_haystack
    for idx, item in enumerate(items):
        row_ids_append(local_bulk_row_id(item) if default_row_id else row_id_factory(item, idx))
        # Stamp text haystack for fast filtering (avoids per-filter
        # str.lower on 4 fields × 59K items).
        if "_text_haystack" not in item:
            item["_text_haystack"] = _build_hay(item)
        # Inline cache lookup — cached_bulk_row_values fast path, no
        # function-call overhead.
        rid = local_bulk_row_id(item)
        cached = cache.get(rid)
        if cached is not None and cached[0] == generation:
            rows_append(list(cached[1]))
            continue
        values = renderer(item)
        cache[rid] = (generation, values)
        rows_append(list(values))
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
    return {"total": total, "assigned": 0, "review": 0, "warning": 0, "skip": 0, "dead_stock": 0}


def _accumulate_summary_counts(counts, item, sign=1):
    if item.get("vendor"):
        counts["assigned"] += sign
    if item.get("status") == "review":
        counts["review"] += sign
    if item.get("status") == "warning":
        counts["warning"] += sign
    if item.get("status") == "skip":
        counts["skip"] += sign
    if item.get("dead_stock"):
        counts["dead_stock"] += sign


def _recompute_summary_counts(items):
    counts = _blank_summary_counts(total=len(items))
    for item in items:
        _accumulate_summary_counts(counts, item)
    return counts


def bulk_assignment_status(item):
    return "Assigned" if item.get("vendor") else "Unassigned"


def bulk_item_status(item):
    # An item can belong to multiple Item Status buckets — the matcher
    # at item_matches_bulk_filter treats No Pack / Dead Stock as
    # *additive* tags rather than mutually-exclusive statuses.  Returning
    # a tuple keeps the fast bucket path consistent with the matcher.
    # Examples:
    #   - status=skip + missing_pack → ("Skip", "No Pack")
    #   - status=ok + missing_pack    → ("No Pack",)        # OK excludes missing_pack
    #   - status=skip + dead_stock    → ("Skip", "Dead Stock")
    buckets = []
    status = (item.get("status", "ok") or "ok").lower()
    has_missing_pack = "missing_pack" in (item.get("data_flags", []) or [])
    is_dead_stock = bool(item.get("dead_stock"))
    status_label = {
        "ok": "OK",
        "review": "Review",
        "warning": "Warning",
        "skip": "Skip",
    }.get(status)
    # The matcher's OK rule excludes items with missing_pack, so the OK
    # bucket must mirror that.  Skip / Review / Warning are unaffected.
    if status_label == "OK" and has_missing_pack:
        status_label = None
    if status_label:
        buckets.append(status_label)
    if has_missing_pack:
        buckets.append("No Pack")
    if is_dead_stock:
        buckets.append("Dead Stock")
    return tuple(buckets) if buckets else None


def bulk_filter_bucket_snapshot(item):
    return {
        "vendor": item.get("vendor", ""),
        "status": item.get("status", ""),
        "data_flags": tuple(item.get("data_flags", ()) or ()),
        "dead_stock": bool(item.get("dead_stock")),
        "performance_profile": item.get("performance_profile", ""),
        "sales_health_signal": item.get("sales_health_signal", ""),
        "reorder_attention_signal": item.get("reorder_attention_signal", ""),
    }


def bulk_performance_bucket(item):
    profile = (item.get("performance_profile", "") or "").lower()
    return {
        "top_performer": "Top",
        "steady": "Steady",
        "intermittent": "Intermittent",
        "legacy": "Legacy",
    }.get(profile)


def bulk_sales_health_bucket(item):
    signal = (item.get("sales_health_signal", "") or "").lower()
    return {
        "active": "Active",
        "cooling": "Cooling",
        "dormant": "Dormant",
        "stale": "Stale",
        "unknown": "Unknown",
    }.get(signal)


def bulk_attention_bucket(item):
    # Like bulk_item_status, the matcher treats "High Risk" as an
    # additive tag (driven by stockout_risk_score) rather than an
    # exclusive replacement for the reorder_attention_signal label.
    # Return every applicable bucket so the fast path stays consistent.
    buckets = []
    signal = (item.get("reorder_attention_signal", "") or "").lower()
    label = {
        "normal": "Normal",
        "review_missed_reorder": "Missed Reorder",
    }.get(signal)
    if label:
        buckets.append(label)
    risk = item.get("stockout_risk_score", 0.0) or 0.0
    try:
        if float(risk) >= 0.6:
            buckets.append("High Risk")
    except (TypeError, ValueError):
        pass
    return tuple(buckets) if buckets else None


def _append_bucket_item(buckets, key, item):
    if key is None:
        return
    # Some bucket helpers (e.g. bulk_item_status) return multiple bucket
    # labels for a single item — the matcher treats labels like "No Pack"
    # and "Dead Stock" as additive tags, not exclusive statuses.  Accept
    # an iterable of keys so the bucket index stays consistent with the
    # matcher.
    if isinstance(key, (list, tuple, set)):
        for sub_key in key:
            if sub_key is None:
                continue
            buckets.setdefault(sub_key, []).append(item)
        return
    buckets.setdefault(key, []).append(item)


def build_bulk_session_metadata(items):
    normalized = list(items or [])
    items_by_line_code = {}
    items_by_source = {}
    items_by_line_code_source = {}
    items_by_assignment_status = {}
    items_by_item_status = {}
    items_by_performance = {}
    items_by_sales_health = {}
    items_by_attention = {}
    for item in normalized:
        line_code = item.get("line_code", "")
        source = item_source(item)
        if not line_code:
            line_code = ""
        if line_code:
            items_by_line_code.setdefault(line_code, []).append(item)
        items_by_source.setdefault(source, []).append(item)
        items_by_line_code_source.setdefault((line_code, source), []).append(item)
        _append_bucket_item(items_by_assignment_status, bulk_assignment_status(item), item)
        _append_bucket_item(items_by_item_status, bulk_item_status(item), item)
        _append_bucket_item(items_by_performance, bulk_performance_bucket(item), item)
        _append_bucket_item(items_by_sales_health, bulk_sales_health_bucket(item), item)
        _append_bucket_item(items_by_attention, bulk_attention_bucket(item), item)
    return {
        "counts": _recompute_summary_counts(normalized),
        "line_codes": tuple(sorted({item.get("line_code", "") for item in normalized if item.get("line_code", "")})),
        "items_by_line_code": {line_code: tuple(group) for line_code, group in items_by_line_code.items()},
        "items_by_source": {source: tuple(group) for source, group in items_by_source.items()},
        "items_by_line_code_source": {key: tuple(group) for key, group in items_by_line_code_source.items()},
        "items_by_assignment_status": {key: tuple(group) for key, group in items_by_assignment_status.items()},
        "items_by_item_status": {key: tuple(group) for key, group in items_by_item_status.items()},
        "items_by_performance": {key: tuple(group) for key, group in items_by_performance.items()},
        "items_by_sales_health": {key: tuple(group) for key, group in items_by_sales_health.items()},
        "items_by_attention": {key: tuple(group) for key, group in items_by_attention.items()},
    }


@perf_trace.timed("ui_bulk.sync_bulk_session_metadata")
def sync_bulk_session_metadata(app, items=None):
    normalized = list(getattr(app, "filtered_items", ()) or ()) if items is None else list(items or [])
    metadata = build_bulk_session_metadata(normalized)
    app._bulk_summary_counts = dict(metadata["counts"])
    app._bulk_line_code_values = list(metadata["line_codes"])
    app._bulk_items_by_line_code = dict(metadata["items_by_line_code"])
    app._bulk_items_by_source = dict(metadata["items_by_source"])
    app._bulk_items_by_line_code_source = dict(metadata["items_by_line_code_source"])
    app._bulk_items_by_assignment_status = dict(metadata["items_by_assignment_status"])
    app._bulk_items_by_item_status = dict(metadata["items_by_item_status"])
    app._bulk_items_by_performance = dict(metadata["items_by_performance"])
    app._bulk_items_by_sales_health = dict(metadata["items_by_sales_health"])
    app._bulk_items_by_attention = dict(metadata["items_by_attention"])
    return metadata


def filtered_candidate_items(app, filter_state):
    filtered_items = getattr(app, "filtered_items", ()) or ()
    if bulk_filter_is_default(filter_state):
        return list(filtered_items)
    line_code = filter_state.get("lc", "ALL")
    source = filter_state.get("source", "ALL")
    assignment_status = filter_state.get("status", "ALL")
    item_status = filter_state.get("item_status", "ALL")
    performance = filter_state.get("performance", "ALL")
    sales_health = filter_state.get("sales_health", "ALL")
    attention = filter_state.get("attention", "ALL")
    line_code_buckets = getattr(app, "_bulk_items_by_line_code", None)
    source_buckets = getattr(app, "_bulk_items_by_source", None)
    assignment_buckets = getattr(app, "_bulk_items_by_assignment_status", None)
    item_status_buckets = getattr(app, "_bulk_items_by_item_status", None)
    performance_buckets = getattr(app, "_bulk_items_by_performance", None)
    sales_health_buckets = getattr(app, "_bulk_items_by_sales_health", None)
    attention_buckets = getattr(app, "_bulk_items_by_attention", None)
    if line_code != "ALL" and not isinstance(line_code_buckets, dict):
        return list(filtered_items)
    if source != "ALL" and not isinstance(source_buckets, dict):
        return list(filtered_items)
    if assignment_status != "ALL" and not isinstance(assignment_buckets, dict):
        return list(filtered_items)
    if item_status != "ALL" and not isinstance(item_status_buckets, dict):
        return list(filtered_items)
    if performance != "ALL" and not isinstance(performance_buckets, dict):
        return list(filtered_items)
    if sales_health != "ALL" and not isinstance(sales_health_buckets, dict):
        return list(filtered_items)
    if attention != "ALL" and not isinstance(attention_buckets, dict):
        return list(filtered_items)
    line_code_buckets = line_code_buckets or {}
    source_buckets = source_buckets or {}
    assignment_buckets = assignment_buckets or {}
    item_status_buckets = item_status_buckets or {}
    performance_buckets = performance_buckets or {}
    sales_health_buckets = sales_health_buckets or {}
    attention_buckets = attention_buckets or {}
    candidate_groups = []
    if line_code != "ALL":
        candidate_groups.append(tuple(line_code_buckets.get(line_code, ())))
    if source != "ALL":
        candidate_groups.append(tuple(source_buckets.get(source, ())))
    if assignment_status != "ALL":
        candidate_groups.append(tuple(assignment_buckets.get(assignment_status, ())))
    if item_status != "ALL":
        candidate_groups.append(tuple(item_status_buckets.get(item_status, ())))
    if performance != "ALL":
        candidate_groups.append(tuple(performance_buckets.get(performance, ())))
    if sales_health != "ALL":
        candidate_groups.append(tuple(sales_health_buckets.get(sales_health, ())))
    if attention != "ALL":
        candidate_groups.append(tuple(attention_buckets.get(attention, ())))
    if candidate_groups:
        if len(candidate_groups) == 1:
            return list(candidate_groups[0])
        ordered_groups = sorted(candidate_groups, key=len)
        base_group = ordered_groups[0]
        membership_sets = [{bulk_row_id(item) for item in group} for group in ordered_groups[1:]]
        return [
            item for item in base_group
            if all(bulk_row_id(item) in membership for membership in membership_sets)
        ]
    return list(filtered_items)


def uses_only_bucket_filters(filter_state):
    # The bucket fast path only knows about the seven combo filters.
    # Any non-bucket filter (text search, vendor worksheet) needs the
    # per-item matcher to run.
    if filter_state.get("text"):
        return False
    if filter_state.get("vendor_tab"):
        return False
    return True


def can_fully_resolve_bucket_filters(app, filter_state):
    bucket_requirements = (
        ("lc", "_bulk_items_by_line_code"),
        ("source", "_bulk_items_by_source"),
        ("status", "_bulk_items_by_assignment_status"),
        ("item_status", "_bulk_items_by_item_status"),
        ("performance", "_bulk_items_by_performance"),
        ("sales_health", "_bulk_items_by_sales_health"),
        ("attention", "_bulk_items_by_attention"),
    )
    for key, attr_name in bucket_requirements:
        if filter_state.get(key, "ALL") != "ALL" and not isinstance(getattr(app, attr_name, None), dict):
            return False
    return True


def cached_bulk_filter_result(app, filter_state):
    cache = getattr(app, "_bulk_filter_result_cache", None)
    generation = getattr(app, "_bulk_filter_result_generation", 0)
    if not isinstance(cache, dict):
        return None
    if cache.get("generation") != generation:
        return None
    if cache.get("filter_state") != tuple(sorted(filter_state.items())):
        return None
    return list(cache.get("visible_items", ()))


def store_bulk_filter_result(app, filter_state, visible_items):
    app._bulk_filter_result_cache = {
        "generation": getattr(app, "_bulk_filter_result_generation", 0),
        "filter_state": tuple(sorted(filter_state.items())),
        "visible_items": tuple(visible_items),
    }
    return visible_items


def _bulk_visible_rows_cache_key(app, scope):
    cycle_var = getattr(app, "var_reorder_cycle", None)
    cycle = cycle_var.get() if cycle_var and hasattr(cycle_var, "get") else ""
    return (scope, cycle)


def cached_bulk_visible_rows(app, scope):
    cache = getattr(app, "_bulk_visible_rows_cache", None)
    generation = getattr(app, "_bulk_visible_rows_generation", 0)
    if not isinstance(cache, dict):
        return None
    if cache.get("generation") != generation:
        return None
    if cache.get("key") != _bulk_visible_rows_cache_key(app, scope):
        return None
    return list(cache.get("row_ids", ())), [list(row) for row in cache.get("rows", ())]


def store_bulk_visible_rows(app, scope, row_ids, rows):
    app._bulk_visible_rows_cache = {
        "generation": getattr(app, "_bulk_visible_rows_generation", 0),
        "key": _bulk_visible_rows_cache_key(app, scope),
        "row_ids": tuple(row_ids),
        "rows": tuple(tuple(row) for row in rows),
    }
    return row_ids, rows


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
    skip_count = counts.get("skip", 0)
    dead_stock_count = counts.get("dead_stock", 0)
    unassigned = total - assigned
    parts = [f"{total} total", f"{assigned} assigned", f"{unassigned} unassigned"]
    if review_count:
        parts.append(f"{review_count} review")
    if warning_count:
        parts.append(f"{warning_count} warning")
    if skip_count:
        parts.append(f"{skip_count} skip")
    if dead_stock_count:
        parts.append(f"{dead_stock_count} dead stock")
    label = getattr(app, "lbl_bulk_summary", None)
    if label is not None and hasattr(label, "config"):
        label.config(text="  ·  ".join(parts))
    # Update progress bar
    pbar = getattr(app, "_bulk_progress", None)
    plabel = getattr(app, "_bulk_progress_label", None)
    if pbar is not None:
        pct = int(100 * assigned / total) if total > 0 else 0
        try:
            pbar.configure(value=pct)
        except Exception:
            pass
    # Empty state guidance
    _empty_state = getattr(app, "_bulk_empty_state_label", None)
    _parent = getattr(app, "root", None)
    if total > 0 and unassigned == 0 and assigned > 0 and _parent is not None:
        if _empty_state is None:
            try:
                _empty_state = ttk.Label(
                    _parent,
                    text="✓  All items assigned!  Click the Review & Export tab to continue.",
                    style="Header.TLabel",
                    anchor="center",
                )
                app._bulk_empty_state_label = _empty_state
            except Exception:
                _empty_state = None
        if _empty_state is not None:
            try:
                _empty_state.pack(side=tk.BOTTOM, pady=8)
            except Exception:
                pass
    elif _empty_state is not None:
        try:
            _empty_state.pack_forget()
        except Exception:
            pass
    if plabel is not None:
        pct = int(100 * assigned / total) if total > 0 else 0
        try:
            plabel.config(text=f"{pct}%")
        except Exception:
            pass


def _normalize_bucket_keys(key):
    """Coerce a single key or iterable of keys into a tuple of non-None keys."""
    if key is None:
        return ()
    if isinstance(key, (list, tuple, set)):
        return tuple(k for k in key if k is not None)
    return (key,)


def _replace_bucket_membership(bucket_map, old_key, new_key, item):
    if not isinstance(bucket_map, dict) or item is None:
        return False
    old_keys = set(_normalize_bucket_keys(old_key))
    new_keys = set(_normalize_bucket_keys(new_key))
    changed = False
    # Drop the item from any old buckets that aren't also new buckets.
    for key in old_keys - new_keys:
        old_group = [existing for existing in bucket_map.get(key, ()) if existing is not item]
        if old_group:
            bucket_map[key] = tuple(old_group)
        elif key in bucket_map:
            bucket_map.pop(key, None)
        changed = True
    # Add the item to any new buckets it isn't already a member of.
    for key in new_keys:
        new_group = list(bucket_map.get(key, ()))
        if not any(existing is item for existing in new_group):
            new_group.append(item)
            bucket_map[key] = tuple(new_group)
            changed = True
    return changed


def adjust_bulk_filter_buckets_for_item_change(app, before_item, after_item, item=None):
    changed = False
    assignment_buckets = getattr(app, "_bulk_items_by_assignment_status", None)
    if isinstance(assignment_buckets, dict):
        changed = _replace_bucket_membership(
            assignment_buckets,
            bulk_assignment_status(before_item),
            bulk_assignment_status(after_item),
            item,
        ) or changed
    item_status_buckets = getattr(app, "_bulk_items_by_item_status", None)
    if isinstance(item_status_buckets, dict):
        changed = _replace_bucket_membership(
            item_status_buckets,
            bulk_item_status(before_item),
            bulk_item_status(after_item),
            item,
        ) or changed
    performance_buckets = getattr(app, "_bulk_items_by_performance", None)
    if isinstance(performance_buckets, dict):
        changed = _replace_bucket_membership(
            performance_buckets,
            bulk_performance_bucket(before_item),
            bulk_performance_bucket(after_item),
            item,
        ) or changed
    sales_health_buckets = getattr(app, "_bulk_items_by_sales_health", None)
    if isinstance(sales_health_buckets, dict):
        changed = _replace_bucket_membership(
            sales_health_buckets,
            bulk_sales_health_bucket(before_item),
            bulk_sales_health_bucket(after_item),
            item,
        ) or changed
    attention_buckets = getattr(app, "_bulk_items_by_attention", None)
    if isinstance(attention_buckets, dict):
        changed = _replace_bucket_membership(
            attention_buckets,
            bulk_attention_bucket(before_item),
            bulk_attention_bucket(after_item),
            item,
        ) or changed
    return changed


def adjust_bulk_summary_for_item_change(app, before_item, after_item, *, item=None):
    cached = getattr(app, "_bulk_summary_counts", None)
    invalidate_bulk_filter_result_cache(app)
    invalidate_bulk_visible_rows_cache(app)
    adjusted = adjust_bulk_filter_buckets_for_item_change(app, before_item, after_item, item=item)
    if not cached or cached.get("total") != len(app.filtered_items):
        return adjusted
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
    text_var = getattr(app, "var_bulk_text_filter", None)
    text_value = ""
    if text_var is not None and hasattr(text_var, "get"):
        try:
            text_value = str(text_var.get() or "").strip()
        except Exception:
            text_value = ""
    vendor_tab = getattr(app, "var_bulk_vendor_filter_internal", "") or ""
    return {
        "lc": _filter_value(app, "var_bulk_lc_filter"),
        "status": _filter_value(app, "var_bulk_status_filter"),
        "source": _filter_value(app, "var_bulk_source_filter"),
        "item_status": _filter_value(app, "var_bulk_item_status"),
        "performance": _filter_value(app, "var_bulk_performance_filter"),
        "sales_health": _filter_value(app, "var_bulk_sales_health_filter"),
        "attention": _filter_value(app, "var_bulk_attention_filter"),
        "text": text_value,
        "vendor_tab": vendor_tab,
    }


def bulk_filter_is_default(filter_state):
    for key, value in filter_state.items():
        if key == "text":
            if value:
                return False
        elif value != "ALL":
            return False
    return True


def _build_text_haystack(item):
    """Build a lowered search string for fast text filtering."""
    inv = item.get("inventory") or {}
    return "\0".join((
        item.get("line_code", ""),
        item.get("item_code", ""),
        item.get("description", ""),
        inv.get("supplier", ""),
        item.get("vendor", ""),
        item.get("notes", ""),
    )).lower()


def item_matches_text_filter(item, text):
    """Case-insensitive substring match against key item fields.

    Uses a precomputed ``_text_haystack`` when available (stamped by
    ``build_bulk_sheet_rows`` or ``refresh_bulk_view_after_edit``).
    Falls back to building one on the fly.
    """
    if not text:
        return True
    needle = str(text or "").strip().lower()
    if not needle:
        return True
    haystack = item.get("_text_haystack")
    if haystack is None:
        haystack = _build_text_haystack(item)
        item["_text_haystack"] = haystack
    return needle in haystack


def item_matches_bulk_filter(item, filter_state):
    # Vendor worksheet filter (from vendor combobox)
    vendor_tab = filter_state.get("vendor_tab", "")
    if vendor_tab:
        item_vendor = str(item.get("vendor", "") or "").strip().upper()
        if item_vendor != vendor_tab.strip().upper():
            return False
    text_value = filter_state.get("text", "")
    if text_value and not item_matches_text_filter(item, text_value):
        return False
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
        if filter_state["item_status"] == "OK" and (
            item_status != "ok" or "missing_pack" in item.get("data_flags", [])
        ):
            return False
        if filter_state["item_status"] == "Review" and item_status != "review":
            return False
        if filter_state["item_status"] == "Warning" and item_status != "warning":
            return False
        if filter_state["item_status"] == "No Pack" and "missing_pack" not in item.get("data_flags", []):
            return False
        if filter_state["item_status"] == "Skip" and item.get("status", "ok") != "skip":
            return False
        if filter_state["item_status"] == "Dead Stock" and not item.get("dead_stock"):
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
        if filter_state["attention"] == "High Risk":
            risk = item.get("stockout_risk_score", 0.0) or 0.0
            if risk < 0.6:
                return False
        else:
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
        "risk": {"qoh"},
    }
    return bool(dependencies.get(sort_col, {sort_col}) & set(changed_cols))


def refresh_bulk_view_after_edit(app, row_ids, changed_cols=None):
    # Evict stale caches for edited rows BEFORE any refresh path.
    # Three caches can hold pre-edit data:
    #   1. Per-row render cache (generation-keyed tuples)
    #   2. Visible-rows cache (full row set for current filter state)
    #   3. Filter-result cache (item lists for current filter state)
    # Evicting all three ensures both the incremental and full-rebuild
    # paths recompute from the updated item dicts.
    cache = _bulk_row_render_cache(app)
    for row_id in row_ids:
        idx, item = resolve_bulk_row_id(app, row_id)
        if idx is not None and item is not None:
            cache.pop(bulk_row_id(item), None)
            item.pop("_text_haystack", None)
    invalidate_bulk_visible_rows_cache(app)
    invalidate_bulk_filter_result_cache(app)
    filter_state = bulk_filter_state(app)
    needs_rebuild = _changed_columns_require_rebuild(app, changed_cols, filter_state=filter_state)
    from debug_log import write_debug as _wd
    _wd(
        "refresh_bulk_view_after_edit.path",
        changed_cols=",".join(changed_cols or ()),
        row_ids=",".join(str(r) for r in row_ids),
        needs_rebuild=needs_rebuild,
    )
    if needs_rebuild:
        with perf_trace.span(
            "ui_bulk.refresh_bulk_view_after_edit.rebuild",
            changed_cols=",".join(changed_cols or ()),
            row_count=len(row_ids),
        ):
            targeted = _try_targeted_filtered_refresh(app, row_ids, filter_state=filter_state)
            _wd("refresh_bulk_view_after_edit.rebuild", targeted=targeted)
            if targeted:
                return True
            app._apply_bulk_filter()
        return False
    if not getattr(app, "bulk_sheet", None):
        return False
    with perf_trace.span(
        "ui_bulk.refresh_bulk_view_after_edit.incremental",
        row_count=len(row_ids),
    ):
        for row_id in row_ids:
            idx, item = resolve_bulk_row_id(app, row_id)
            if idx is None or item is None:
                _wd("refresh_bulk_view_after_edit.incremental.skip", row_id=row_id, reason="not_found")
                continue
            effective_row_id = str(row_id)
            if effective_row_id not in getattr(app.bulk_sheet, "row_lookup", {}):
                effective_row_id = bulk_row_id(item)
            in_lookup = effective_row_id in getattr(app.bulk_sheet, "row_lookup", {})
            _wd(
                "refresh_bulk_view_after_edit.incremental.row",
                row_id=row_id,
                effective_row_id=effective_row_id,
                in_lookup=in_lookup,
                item_pack=item.get("pack_size"),
            )
            if in_lookup:
                values = cached_bulk_row_values(app, item)
                app.bulk_sheet.refresh_row(effective_row_id, values)
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


def save_bulk_filter_sort_state(app):
    """Persist the current bulk-editor filter and sort state to app_settings."""
    app_settings = getattr(app, "app_settings", None)
    if app_settings is None:
        return
    app_settings["bulk_filter_state"] = bulk_filter_state(app)
    app_settings["bulk_sort_col"] = getattr(app, "_bulk_sort_col", None)
    app_settings["bulk_sort_reverse"] = getattr(app, "_bulk_sort_reverse", False)
    save_fn = getattr(app, "_save_app_settings", None)
    if save_fn:
        save_fn()


def restore_bulk_filter_sort_state(app):
    """
    Restore bulk-editor filter and sort state from app_settings.
    Safe to call before the filter vars exist — missing vars are silently skipped.
    """
    app_settings = getattr(app, "app_settings", None)
    if app_settings is None:
        return
    saved_filter = app_settings.get("bulk_filter_state") or {}
    var_map = {
        "lc": "var_bulk_lc_filter",
        "status": "var_bulk_status_filter",
        "source": "var_bulk_source_filter",
        "item_status": "var_bulk_item_status",
        "performance": "var_bulk_performance_filter",
        "sales_health": "var_bulk_sales_health_filter",
        "attention": "var_bulk_attention_filter",
    }
    for key, attr in var_map.items():
        value = saved_filter.get(key, "ALL")
        var = getattr(app, attr, None)
        if var is not None:
            try:
                var.set(value)
            except Exception:
                pass
    sort_col = app_settings.get("bulk_sort_col")
    if sort_col:
        app._bulk_sort_col = sort_col
        app._bulk_sort_reverse = bool(app_settings.get("bulk_sort_reverse", False))
    refresh_preset_combobox(app)


def apply_bulk_filter(app):
    with perf_trace.span(
        "ui_bulk.apply_bulk_filter",
        items_total=len(getattr(app, "filtered_items", []) or []),
    ):
        _apply_bulk_filter_inner(app)
    badge_fn = getattr(app, "_update_filter_badge", None)
    if callable(badge_fn):
        try:
            badge_fn()
        except Exception:
            pass


def _apply_bulk_filter_inner(app):
    flush_pending_bulk_sheet_edit(app)
    sync_bulk_cache_state(app)
    filter_state = bulk_filter_state(app)

    counts = getattr(app, "_bulk_summary_counts", None)
    if not counts or counts.get("total") != len(app.filtered_items):
        counts = _recompute_summary_counts(app.filtered_items)
    visible_items = cached_bulk_filter_result(app, filter_state)
    from debug_log import write_debug as _wd2
    _wd2("_apply_bulk_filter_inner.filter_cache", hit=visible_items is not None)
    if visible_items is None:
        candidate_items = filtered_candidate_items(app, filter_state)
        if bulk_filter_is_default(filter_state) or (
            uses_only_bucket_filters(filter_state) and can_fully_resolve_bucket_filters(app, filter_state)
        ):
            visible_items = candidate_items
        else:
            visible_items = [item for item in candidate_items if item_matches_bulk_filter(item, filter_state)]
        store_bulk_filter_result(app, filter_state, visible_items)
    update_bulk_summary(app, counts=counts)
    if app.bulk_sheet:
        cached_rows = cached_bulk_visible_rows(app, tuple(sorted(filter_state.items())))
        _wd2("_apply_bulk_filter_inner.visible_cache", hit=cached_rows is not None)
        if cached_rows is None:
            row_ids, rows = build_bulk_sheet_rows(app, visible_items)
            store_bulk_visible_rows(app, tuple(sorted(filter_state.items())), row_ids, rows)
        else:
            row_ids, rows = cached_rows
        app.bulk_sheet.set_rows(rows, row_ids)
    save_bulk_filter_sort_state(app)


def autosize_bulk_tree(app):
    if not getattr(app, "bulk_sheet", None):
        return
    return


def _show_overview_panel(app):
    """Show the overview cards, hide the grid."""
    panel = getattr(app, "_overview_panel", None)
    if panel is None or getattr(app, "_overview_visible", False):
        return
    panel.pack(fill=tk.BOTH, expand=True, before=getattr(app, "_bulk_grid_tree_frame", None))
    app._overview_visible = True
    _refresh_overview_cards(app)


def _hide_overview_panel(app):
    """Hide the overview cards, show the grid."""
    panel = getattr(app, "_overview_panel", None)
    if panel is None or not getattr(app, "_overview_visible", False):
        return
    panel.pack_forget()
    app._overview_visible = False


def refresh_vendor_worksheet_tabs(app):
    """Rebuild the vendor worksheet combobox values."""
    combo = getattr(app, "_vendor_worksheet_combo", None)
    if combo is None:
        return
    perf_trace.stamp("vendor_tabs.refresh_start", items=len(getattr(app, "filtered_items", []) or []))

    vendor_counts = {}
    unassigned = 0
    exceptions = 0
    for item in getattr(app, "filtered_items", []) or []:
        vendor = str(item.get("vendor", "") or "").strip().upper()
        if vendor:
            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
        else:
            unassigned += 1
        if item.get("status") == "review":
            exceptions += 1

    values = ["All Items", "Overview"]
    for vendor, count in sorted(vendor_counts.items(), key=lambda kv: -kv[1]):
        values.append(f"{vendor} ({count})")
    if unassigned > 0:
        values.append(f"Unassigned ({unassigned})")
    if exceptions > 0:
        values.append(f"Exceptions ({exceptions})")

    app._vendor_worksheet_values = values
    combo["values"] = values
    perf_trace.stamp("vendor_tabs.refresh_done", vendor_count=len(vendor_counts))


def _refresh_overview_cards(app):
    """Build vendor summary cards in the Overview panel."""
    overview = getattr(app, "_overview_panel", None)
    if overview is None:
        return
    for child in overview.winfo_children():
        try:
            child.destroy()
        except Exception:
            pass

    vendor_counts = {}
    vendor_values = {}
    unassigned = 0
    exceptions = 0
    for item in getattr(app, "filtered_items", []) or []:
        vendor = str(item.get("vendor", "") or "").strip().upper()
        if vendor:
            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
            inv = (item.get("inventory") or {})
            cost = inv.get("repl_cost", 0) or 0
            qty = item.get("final_qty", item.get("order_qty", 0)) or 0
            vendor_values[vendor] = vendor_values.get(vendor, 0) + cost * qty
        else:
            unassigned += 1
        if item.get("status") == "review":
            exceptions += 1

    if not vendor_counts and unassigned == 0:
        tk.Label(
            overview, text="No items loaded yet",
            font=("Segoe UI", 11), bg="#222222", fg="#666666",
        ).pack(pady=20)
        return

    cards_frame = ttk.Frame(overview)
    cards_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    row_idx = 0
    col_idx = 0
    max_cols = 4

    # Precompute exceptions per vendor in one pass (avoids O(n × vendors))
    vendor_exceptions = {}
    for item in getattr(app, "filtered_items", []) or []:
        if item.get("status") == "review":
            v = str(item.get("vendor", "") or "").strip().upper()
            if v:
                vendor_exceptions[v] = vendor_exceptions.get(v, 0) + 1

    for vendor, count in sorted(vendor_counts.items(), key=lambda kv: -kv[1]):
        value = vendor_values.get(vendor, 0)
        has_exceptions = vendor_exceptions.get(vendor, 0) > 0
        _build_vendor_card(cards_frame, app, vendor, count, value, has_exceptions, row_idx, col_idx)
        col_idx += 1
        if col_idx >= max_cols:
            col_idx = 0
            row_idx += 1

    # Unassigned card
    if unassigned > 0:
        _build_summary_card(cards_frame, app, "Unassigned", unassigned, "Need vendor assignment", "#3a2a1a", row_idx, col_idx)
        col_idx += 1
        if col_idx >= max_cols:
            col_idx = 0
            row_idx += 1

    # Exceptions card
    if exceptions > 0:
        _build_summary_card(cards_frame, app, "Exceptions", exceptions, "Need review", "#3a1a1a", row_idx, col_idx)


def _build_vendor_card(parent, app, vendor, count, value, has_exceptions, row, col):
    bg = "#1a2a3a" if not has_exceptions else "#2a2a1a"
    card = tk.Frame(parent, bg=bg, padx=12, pady=10, relief="ridge", bd=1)
    card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
    parent.columnconfigure(col, weight=1)

    status = "⚠ Needs attention" if has_exceptions else "✓ Ready"
    status_fg = "#d0a040" if has_exceptions else "#60b060"

    tk.Label(card, text=vendor, font=("Segoe UI", 12, "bold"), bg=bg, fg="#d0d8e0", anchor="w").pack(fill=tk.X)
    tk.Label(card, text=f"{count} items  ·  ${value:,.0f} est.", font=("Segoe UI", 9), bg=bg, fg="#8898a8", anchor="w").pack(fill=tk.X)
    tk.Label(card, text=status, font=("Segoe UI", 9), bg=bg, fg=status_fg, anchor="w").pack(fill=tk.X)

    def _click(v=vendor):
        # Find the tab for this vendor and select it
        tabs_nb = getattr(app, "_vendor_tabs", None)
        if tabs_nb:
            for tab_id in tabs_nb.tabs():
                text = tabs_nb.tab(tab_id, "text").strip()
                if text.startswith(v):
                    tabs_nb.select(tab_id)
                    break
    card.bind("<Button-1>", lambda e: _click())
    for child in card.winfo_children():
        child.bind("<Button-1>", lambda e: _click())


def _build_summary_card(parent, app, title, count, subtitle, bg, row, col):
    card = tk.Frame(parent, bg=bg, padx=12, pady=10, relief="ridge", bd=1)
    card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
    parent.columnconfigure(col, weight=1)

    tk.Label(card, text=title, font=("Segoe UI", 12, "bold"), bg=bg, fg="#d0d8e0", anchor="w").pack(fill=tk.X)
    tk.Label(card, text=f"{count} items", font=("Segoe UI", 9), bg=bg, fg="#8898a8", anchor="w").pack(fill=tk.X)
    tk.Label(card, text=subtitle, font=("Segoe UI", 9), bg=bg, fg="#a0a8b0", anchor="w").pack(fill=tk.X)

    def _click(t=title):
        tabs_nb = getattr(app, "_vendor_tabs", None)
        if tabs_nb:
            for tab_id in tabs_nb.tabs():
                text = tabs_nb.tab(tab_id, "text").strip()
                if text.startswith(t):
                    tabs_nb.select(tab_id)
                    break
    card.bind("<Button-1>", lambda e: _click())
    for child in card.winfo_children():
        child.bind("<Button-1>", lambda e: _click())


def _show_shortcut_overlay(app):
    """Show the keyboard shortcut overlay."""
    try:
        import ui_shortcut_overlay
        ui_shortcut_overlay.show_shortcut_overlay(app)
    except Exception:
        pass


def _header_right_click_columns(app, event):
    """Show a checkbutton menu to toggle column visibility."""
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if not bulk_sheet:
        return
    pinned = {"vendor", "line_code", "item_code", "description", "status", "final_qty"}
    hidden = getattr(app, "_hidden_columns", set())

    menu = tk.Menu(app.root, tearoff=0)
    for col_name in bulk_sheet.columns:
        if col_name in pinned:
            continue
        label = bulk_sheet.labels.get(col_name, col_name)
        var = tk.BooleanVar(value=col_name not in hidden)
        menu.add_checkbutton(label=label, variable=var,
                             command=lambda cn=col_name, v=var: _toggle_column(app, cn, v.get()))
    menu.add_separator()
    menu.add_command(label="Show All", command=lambda: _show_all_columns(app))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    except Exception:
        pass


def _toggle_column(app, col_name, visible):
    hidden = getattr(app, "_hidden_columns", set())
    if visible:
        hidden.discard(col_name)
    else:
        hidden.add(col_name)
    app._hidden_columns = hidden
    _apply_column_visibility(app)


def _show_all_columns(app):
    app._hidden_columns = set()
    _apply_column_visibility(app)


def _apply_column_visibility(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if not bulk_sheet:
        return
    hidden = getattr(app, "_hidden_columns", set())
    for col_name in bulk_sheet.columns:
        col_idx = bulk_sheet.col_index.get(col_name)
        if col_idx is None:
            continue
        if col_name in hidden:
            try:
                bulk_sheet.sheet.column_width(col_idx, 0)
            except Exception:
                pass
        else:
            width = bulk_sheet.base_widths.get(col_name, 100)
            try:
                bulk_sheet.sheet.column_width(col_idx, width)
            except Exception:
                pass
    try:
        bulk_sheet.sheet.redraw()
    except Exception:
        pass


def _header_click_sort(app, event):
    """Sort by the clicked column header."""
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if not bulk_sheet:
        return
    try:
        col_idx = bulk_sheet.sheet.identify_column(event)
    except Exception:
        return
    if col_idx is None or col_idx < 0 or col_idx >= len(bulk_sheet.columns):
        return
    col_name = bulk_sheet.columns[col_idx]
    with perf_trace.span("ui_bulk.header_click_sort", col=col_name):
        app._sort_bulk_tree(col_name)


def _header_double_click_autosize(app, event):
    """Auto-size columns on header double-click."""
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet:
        bulk_sheet.fit_columns_to_window()
    return "break"


def _update_sort_arrows(app):
    """Add ▲/▼ arrow to the sorted column header."""
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if not bulk_sheet or not hasattr(bulk_sheet, "columns"):
        return
    sort_col = getattr(app, "_bulk_sort_col", None)
    reverse = getattr(app, "_bulk_sort_reverse", False)
    headers = []
    for col_name in bulk_sheet.columns:
        label = bulk_sheet.labels.get(col_name, col_name)
        # Strip any existing arrows
        label = label.rstrip(" ▲▼")
        if col_name == sort_col:
            label = f"{label} {'▼' if reverse else '▲'}"
        headers.append(label)
    try:
        bulk_sheet.sheet.headers(headers, redraw=False)
        bulk_sheet.sheet.redraw()
    except Exception:
        pass


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

    with perf_trace.span("ui_bulk.sort_bulk_tree.sort", col=col, items=len(getattr(app, "filtered_items", []) or [])):
        sort_filtered_items(app, key=_sort_key, reverse=reverse)
    with perf_trace.span("ui_bulk.sort_bulk_tree.apply_filter"):
        apply_bulk_filter(app)
    _update_sort_arrows(app)
    save_bulk_filter_sort_state(app)


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
    if col == "notes":
        return item.get("notes", "")
    if col == "risk":
        return item.get("stockout_risk_score", 0.0) or 0.0
    return ""


# ─── Named Filter Presets ─────────────────────────────────────────────────────

def get_bulk_filter_presets(app):
    """Return the saved preset dict from app_settings, or {} if none."""
    settings = getattr(app, "app_settings", None) or {}
    return dict(settings.get("bulk_filter_presets") or {})


def save_bulk_filter_preset(app, name):
    """Save the current filter state under the given name."""
    settings = getattr(app, "app_settings", None)
    if settings is None:
        return
    presets = dict(settings.get("bulk_filter_presets") or {})
    presets[name] = bulk_filter_state(app)
    settings["bulk_filter_presets"] = presets
    save_fn = getattr(app, "_save_app_settings", None)
    if callable(save_fn):
        save_fn()
    refresh_preset_combobox(app)


def delete_bulk_filter_preset(app, name):
    """Delete the named preset."""
    settings = getattr(app, "app_settings", None)
    if settings is None:
        return
    presets = dict(settings.get("bulk_filter_presets") or {})
    presets.pop(name, None)
    settings["bulk_filter_presets"] = presets
    save_fn = getattr(app, "_save_app_settings", None)
    if callable(save_fn):
        save_fn()
    refresh_preset_combobox(app)


def apply_bulk_filter_preset(app, name):
    """Apply the named preset to the filter vars and refresh the view."""
    presets = get_bulk_filter_presets(app)
    state = presets.get(name)
    if not state:
        return
    var_map = {
        "lc": "var_bulk_lc_filter",
        "status": "var_bulk_status_filter",
        "source": "var_bulk_source_filter",
        "item_status": "var_bulk_item_status",
        "performance": "var_bulk_performance_filter",
        "sales_health": "var_bulk_sales_health_filter",
        "attention": "var_bulk_attention_filter",
    }
    for key, var_name in var_map.items():
        var = getattr(app, var_name, None)
        if var is not None and key in state:
            var.set(state[key])
    apply_bulk_filter(app)


def refresh_preset_combobox(app):
    """Repopulate the preset combobox from current settings."""
    combo = getattr(app, "combo_bulk_preset", None)
    if combo is None:
        return
    presets = get_bulk_filter_presets(app)
    names = sorted(presets.keys())
    set_combobox_values_if_changed(combo, [""] + names)


def _save_preset_dialog(app):
    from tkinter import simpledialog
    name = simpledialog.askstring("Save Filter Preset", "Preset name:", parent=getattr(app, "root", None))
    if name and name.strip():
        save_bulk_filter_preset(app, name.strip())
