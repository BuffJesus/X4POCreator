import os
import tkinter as tk
from tkinter import ttk, messagebox

import export_flow
import shipping_flow
from rules import recency_review_bucket_label
from ui_grid_edit import TreeGridEditor
from ui_scroll import attach_vertical_mousewheel


def flush_pending_bulk_sheet_edit(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet and hasattr(bulk_sheet, "flush_pending_edit"):
        bulk_sheet.flush_pending_edit()


def release_filter_bucket(item):
    return {
        "held": "Held",
        "planned_today": "Planned Today",
        "release_now": "Release Now",
    }.get(shipping_flow.release_bucket(item), "Release Now")


def is_critical_shipping_hold(item):
    return shipping_flow.is_critical_shipping_hold(item)


def has_urgent_release_override(item):
    trigger = str(item.get("release_trigger", "") or "").strip().lower()
    if trigger in ("urgent_floor", "vendor_urgent_consolidation"):
        return True
    detail = str(item.get("release_decision_detail", "") or "").strip().lower()
    return detail in (
        "release_now_urgent_floor",
        "release_now_paid_urgent_freight",
        "release_now_vendor_urgent_consolidation",
        "release_now_paid_urgent_vendor_consolidation",
    )


def has_suggestion_gap(item):
    compare_code = str(item.get("detailed_suggestion_compare", "") or "").strip().lower()
    if compare_code:
        return compare_code not in ("no_detailed", "aligned")
    return bool(item.get("detailed_suggestion_gap"))


def is_review_exception(item):
    if has_urgent_release_override(item):
        return True
    if release_filter_bucket(item) != "Release Now":
        return True
    if str(item.get("status", "") or "").strip().lower() in ("review", "warning"):
        return True
    if bool(item.get("review_required")):
        return True
    if str(item.get("recency_confidence", "") or "").strip().lower() == "low":
        return True
    if str(item.get("vendor_value_coverage", "") or "").strip().lower() in ("partial", "missing"):
        return True
    if str(item.get("reorder_attention_signal", "") or "").strip().lower() == "review_missed_reorder":
        return True
    if str(item.get("reorder_attention_signal", "") or "").strip().lower() == "review_lumpy_demand":
        return True
    if str(item.get("reorder_attention_signal", "") or "").strip().lower() == "review_receipt_heavy":
        return True
    if bool(item.get("receipt_pack_mismatch")):
        return True
    if bool(item.get("receipt_vendor_ambiguous")):
        return True
    if has_suggestion_gap(item):
        return True
    return False


RECENCY_FILTER_LABELS = {
    "critical_min_rule_protected": "Critical / Explicit Min Rule",
    "critical_rule_protected": "Critical / Rule-Protected",
    "recent_local_po_protected": "Recent Local PO-Protected",
    "activity_protected": "Activity-Protected",
    "new_or_sparse": "New / Sparse",
    "missing_data_uncertain": "Missing-Data / Uncertain",
    "stale_or_likely_dead": "Stale / Likely Dead",
}


SUGGESTION_FILTER_LABELS = {
    "detailed_only": "Detailed Only",
    "detailed_higher": "Detailed Higher",
    "detailed_lower": "Detailed Lower",
    "different": "Different",
    "aligned": "Aligned",
    "no_detailed": "No Detailed",
}


SUGGESTION_SOURCE_FILTER_LABELS = {
    "x4_mo12_sales": "X4 12-month sales",
    "detailed_sales_fallback": "Detailed sales fallback",
    "none": "No suggestion",
    "provided": "Provided",
}


def recency_filter_label(item):
    bucket = item.get("recency_review_bucket")
    if not bucket:
        return "None"
    return RECENCY_FILTER_LABELS.get(bucket, recency_review_bucket_label(bucket) or str(bucket))


def suggestion_filter_label(item):
    code = str(item.get("detailed_suggestion_compare", "") or "").strip().lower()
    if not code:
        return "None"
    return SUGGESTION_FILTER_LABELS.get(code, str(item.get("detailed_suggestion_compare_label", "") or code))


def suggestion_source_filter_label(item):
    code = str(item.get("suggested_source", "") or "").strip().lower()
    if not code:
        return "None"
    return SUGGESTION_SOURCE_FILTER_LABELS.get(code, str(item.get("suggested_source_label", "") or code))


def review_focus_label_for_setting(setting):
    return "Exceptions Only" if str(setting or "").strip() == "exceptions_only" else "All Items"


def review_focus_setting_for_label(label):
    return "exceptions_only" if str(label or "").strip() == "Exceptions Only" else "all_items"


def on_review_focus_changed(app):
    focus_var = getattr(app, "var_review_focus_filter", None)
    focus_label = focus_var.get() if focus_var and hasattr(focus_var, "get") else "All Items"
    setter = getattr(app, "_set_review_export_focus", None)
    if callable(setter):
        setter(review_focus_setting_for_label(focus_label))
    if hasattr(app, "_apply_review_filter"):
        app._apply_review_filter()


def resolved_review_focus_label(app):
    focus = "All Items"
    current_focus_var = getattr(app, "var_review_focus_filter", None)
    current_focus = current_focus_var.get() if current_focus_var and hasattr(current_focus_var, "get") else ""
    if current_focus in ("All Items", "Exceptions Only"):
        focus = current_focus
    elif callable(getattr(app, "_get_review_export_focus", None)):
        focus = review_focus_label_for_setting(app._get_review_export_focus())
    auto_fallback = False
    if focus == "Exceptions Only":
        assigned_items = list(getattr(app, "assigned_items", []) or [])
        if assigned_items and not any(is_review_exception(item) for item in assigned_items):
            focus = "All Items"
            auto_fallback = True
    return focus, auto_fallback


def build_vendor_release_plan_rows(app):
    return shipping_flow.build_vendor_release_plan(getattr(app, "assigned_items", []))


def tree_selected_values_or_first(tree):
    selection = tree.selection()
    target = selection[0] if selection else ""
    if not target:
        children = tree.get_children()
        target = children[0] if children else ""
        if target and hasattr(tree, "selection_set"):
            try:
                tree.selection_set(target)
            except Exception:
                pass
    if not target:
        return ()
    values = tree.item(target, "values")
    return values or ()


def tree_selected_index_or_first(tree):
    selection = tree.selection()
    target = selection[0] if selection else ""
    if not target:
        children = tree.get_children()
        target = children[0] if children else ""
        if target and hasattr(tree, "selection_set"):
            try:
                tree.selection_set(target)
            except Exception:
                pass
    if target == "":
        return None
    try:
        return int(target)
    except Exception:
        return None


def compact_review_bucket(row):
    release_now_count = int(row.get("release_now_count", 0) or 0)
    planned_today_count = int(row.get("planned_today_count", 0) or 0)
    held_count = int(row.get("held_count", 0) or 0)
    critical_held_count = int(row.get("critical_held_count", 0) or 0)
    if critical_held_count > 0:
        return "Blocked"
    if release_now_count > 0:
        return "Ready Now"
    if planned_today_count > 0:
        return "Planned Today"
    if held_count > 0:
        return "Blocked"
    return "Ready Now"


def compact_review_reason(row):
    bucket = compact_review_bucket(row)
    paid_urgent_count = int(float(row.get("paid_urgent_count", 0) or 0))
    vendor_urgent_consolidation_count = int(float(row.get("vendor_urgent_consolidation_count", 0) or 0))
    urgent_release_count = int(float(row.get("urgent_release_count", 0) or 0))
    if paid_urgent_count > 0:
        detail = f"Paid urgent freight override is active for {paid_urgent_count} item(s)"
        if vendor_urgent_consolidation_count > 0:
            detail += f"; {vendor_urgent_consolidation_count} additional item(s) are riding the urgent vendor consolidation"
        detail += "."
        if shipping_flow.vendor_has_value_risk(row):
            detail += " Review value coverage before export."
        return detail
    if urgent_release_count > 0 or vendor_urgent_consolidation_count > 0:
        detail = f"Urgent release is active for {urgent_release_count} item(s)"
        if vendor_urgent_consolidation_count > 0:
            detail += f"; {vendor_urgent_consolidation_count} additional item(s) are being consolidated with the urgent vendor PO"
        detail += "."
        if shipping_flow.vendor_has_value_risk(row):
            detail += " Review value coverage before export."
        return detail
    if shipping_flow.vendor_has_value_risk(row):
        coverage = str(row.get("vendor_value_coverage", "") or "").strip() or "unknown"
        confidence = str(row.get("vendor_value_confidence", "") or "").strip() or "unknown"
        unknown = int(float(row.get("vendor_value_unknown_items", 0) or 0))
        missing_cost = int(float(row.get("vendor_value_missing_cost_items", 0) or 0))
        zero_cost = int(float(row.get("vendor_value_zero_cost_items", 0) or 0))
        invalid_cost = int(float(row.get("vendor_value_invalid_cost_items", 0) or 0))
        detail = (
            f"Vendor value coverage needs review: {coverage} ({confidence} confidence, "
            f"{unknown} unknown"
        )
        if missing_cost:
            detail += f", missing cost {missing_cost}"
        if zero_cost:
            detail += f", zero cost {zero_cost}"
        if invalid_cost:
            detail += f", invalid cost {invalid_cost}"
        detail += ")."
        if bucket != "Blocked":
            return detail
    if bucket == "Blocked":
        if int(row.get("critical_held_count", 0) or 0) > 0:
            return "Critical held items need review before waiting on policy."
        if str(row.get("release_plan_status", "") or "").strip() == "hold_accumulating_to_threshold":
            shortfall = float(row.get("vendor_threshold_shortfall", 0.0) or 0.0)
            suffix = compact_review_reason({
                **row,
                "release_now_count": 1,
                "planned_today_count": 0,
                "held_count": 0,
                "critical_held_count": 0,
            }) if shipping_flow.vendor_has_value_risk(row) else ""
            if suffix:
                return f"Held toward freight threshold; short {shortfall:.2f}. {suffix}"
            return f"Held toward freight threshold; short {shortfall:.2f}."
        next_free = str(row.get("next_free_ship_date", "") or "").strip()
        planned_export = str(row.get("planned_export_date", "") or "").strip()
        if planned_export:
            suffix = compact_review_reason({
                **row,
                "release_now_count": 1,
                "planned_today_count": 0,
                "held_count": 0,
                "critical_held_count": 0,
            }) if shipping_flow.vendor_has_value_risk(row) else ""
            if suffix:
                return f"Held until planned export date {planned_export}. {suffix}"
            return f"Held until planned export date {planned_export}."
        if next_free:
            suffix = compact_review_reason({
                **row,
                "release_now_count": 1,
                "planned_today_count": 0,
                "held_count": 0,
                "critical_held_count": 0,
            }) if shipping_flow.vendor_has_value_risk(row) else ""
            if suffix:
                return f"Held for free-ship day {next_free}. {suffix}"
            return f"Held for free-ship day {next_free}."
        return "Held by shipping policy."
    if bucket == "Planned Today":
        planned_export = str(row.get("planned_export_date", "") or "").strip()
        if planned_export:
            return f"Planned batch is due on {planned_export}."
        return "Planned-release items are ready to export."
    held_count = int(row.get("held_count", 0) or 0)
    if held_count > 0:
        return f"Exportable now; {held_count} held item(s) remain behind policy."
    return "Vendor has exportable items ready now."


def build_compact_review_rows(app):
    rows = []
    for row in build_vendor_release_plan_rows(app):
        compact_row = dict(row)
        compact_row["compact_bucket"] = compact_review_bucket(row)
        compact_row["compact_reason"] = compact_review_reason(row)
        rows.append(compact_row)
    bucket_order = {"Ready Now": 0, "Planned Today": 1, "Blocked": 2}
    rows.sort(key=lambda row: (bucket_order.get(row.get("compact_bucket", ""), 9), row.get("vendor", "")))
    return rows


def apply_release_plan_view(app, vendor, *, focus="Exceptions Only", release="ALL"):
    if hasattr(app, "var_vendor_filter"):
        app.var_vendor_filter.set(vendor or "ALL")
    if hasattr(app, "var_review_performance_filter"):
        app.var_review_performance_filter.set("ALL")
    if hasattr(app, "var_review_attention_filter"):
        app.var_review_attention_filter.set("ALL")
    if hasattr(app, "var_review_recency_filter"):
        app.var_review_recency_filter.set("ALL")
    if hasattr(app, "var_review_suggestion_filter"):
        app.var_review_suggestion_filter.set("ALL")
    if hasattr(app, "var_review_suggestion_source_filter"):
        app.var_review_suggestion_source_filter.set("ALL")
    if hasattr(app, "var_review_release_filter"):
        app.var_review_release_filter.set(release)
    if hasattr(app, "var_review_focus_filter"):
        app.var_review_focus_filter.set(focus)
    if hasattr(app, "_apply_review_filter"):
        app._apply_review_filter()
    notebook = getattr(app, "notebook", None)
    if notebook and hasattr(notebook, "select"):
        try:
            notebook.select(5)
        except Exception:
            pass


def export_release_plan_scope(app, vendor, *, release):
    bucket_map = {
        "Release Now": "release_now",
        "Planned Today": "planned_today",
        "Held": "held",
        "Critical Held": "held",
    }
    target_bucket = bucket_map.get(release, "")
    scoped_items = [
        item for item in getattr(app, "assigned_items", [])
        if str(item.get("vendor", "") or "").strip().upper() == str(vendor or "").strip().upper()
        and shipping_flow.release_bucket(item) == target_bucket
        and (not release == "Critical Held" or is_critical_shipping_hold(item))
    ]
    if not scoped_items:
        messagebox.showinfo("Release Plan", f"No {release.lower()} items are available for vendor {vendor}.")
        return
    export_flow.do_export(
        app,
        app._export_vendor_po,
        app._data_path("order_history"),
        app._data_path("sessions"),
        assigned_items=scoped_items,
        export_scope_label=f"{vendor} {release.lower()} items",
        selection_mode="all_exportable",
    )


def export_review_scope(app, scope):
    bucket_map = {
        "all_exportable": None,
        "immediate_only": "release_now",
        "planned_only": "planned_today",
    }
    scope_label_map = {
        "all_exportable": "all exportable items",
        "immediate_only": "immediate release items",
        "planned_only": "planned today items",
    }
    target_bucket = bucket_map.get(scope)
    if scope not in scope_label_map:
        raise ValueError(f"Unknown review export scope: {scope}")

    scoped_items = list(getattr(app, "assigned_items", []))
    if target_bucket:
        scoped_items = [
            item for item in scoped_items
            if shipping_flow.release_bucket(item) == target_bucket
        ]
    else:
        scoped_items = [
            item for item in scoped_items
            if shipping_flow.release_bucket(item) != "held"
        ]

    if not scoped_items:
        messagebox.showinfo("Review Export", f"No {scope_label_map[scope]} are currently available.")
        return

    export_flow.do_export(
        app,
        app._export_vendor_po,
        app._data_path("order_history"),
        app._data_path("sessions"),
        assigned_items=scoped_items,
        export_scope_label=scope_label_map[scope],
        selection_mode="all_exportable",
    )


def export_review_recommended(app):
    export_flow.do_export(
        app,
        app._export_vendor_po,
        app._data_path("order_history"),
        app._data_path("sessions"),
        export_scope_label="recommended export items",
        selection_mode="default",
    )


def show_export_preview_dialog(app, preview_data):
    """
    Show a modal preview dialog before export. Returns True to proceed, False to cancel.
    """
    result = [False]
    root = getattr(app, "root", None)
    dlg = tk.Toplevel(root)
    dlg.title("Export Preview")
    dlg.resizable(True, True)
    dlg.grab_set()

    summaries = preview_data.get("vendor_summaries", [])
    total_count = preview_data.get("total_item_count", 0)
    total_value = preview_data.get("total_estimated_value", 0.0)

    ttk.Label(dlg, text=f"Ready to export {total_count} item(s) across {len(summaries)} vendor(s).").pack(padx=12, pady=(12, 4), anchor="w")

    canvas_frame = ttk.Frame(dlg)
    canvas_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

    canvas = tk.Canvas(canvas_frame, height=min(len(summaries) * 28 + 32, 300))
    scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scroll_frame = ttk.Frame(canvas)
    scroll_frame_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

    def _on_frame_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    scroll_frame.bind("<Configure>", _on_frame_configure)

    def _on_canvas_configure(e):
        canvas.itemconfig(scroll_frame_id, width=e.width)

    canvas.bind("<Configure>", _on_canvas_configure)

    # Header row
    hdr = ttk.Frame(scroll_frame)
    hdr.pack(fill=tk.X, pady=(0, 2))
    ttk.Label(hdr, text="Vendor", width=14, anchor="w", font=("", 9, "bold")).pack(side=tk.LEFT)
    ttk.Label(hdr, text="Items", width=6, anchor="center", font=("", 9, "bold")).pack(side=tk.LEFT)
    ttk.Label(hdr, text="Est. Value", width=12, anchor="e", font=("", 9, "bold")).pack(side=tk.LEFT)
    ttk.Label(hdr, text="Scope", width=10, anchor="w", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(8, 0))

    vendor_rows = {}  # vendor -> StringVar
    for s in summaries:
        row = ttk.Frame(scroll_frame)
        row.pack(fill=tk.X, pady=1)
        var = tk.StringVar(value="Include")
        vendor_rows[s["vendor"]] = var
        ttk.Label(row, text=s["vendor"], width=14, anchor="w").pack(side=tk.LEFT)
        ttk.Label(row, text=str(s["item_count"]), width=6, anchor="center").pack(side=tk.LEFT)
        val_str = f"${s['estimated_value']:,.2f}" if s["estimated_value"] > 0 else "\u2014"
        ttk.Label(row, text=val_str, width=12, anchor="e").pack(side=tk.LEFT)
        ttk.Combobox(row, textvariable=var, values=["Include", "Defer", "Skip"],
                     state="readonly", width=8).pack(side=tk.LEFT, padx=(8, 0))

    # Total row
    total_row = ttk.Frame(scroll_frame)
    total_row.pack(fill=tk.X, pady=(4, 0))
    total_val_str = f"${total_value:,.2f}" if total_value > 0 else "\u2014"
    ttk.Label(total_row, text="TOTAL", width=14, anchor="w", font=("", 9, "bold")).pack(side=tk.LEFT)
    ttk.Label(total_row, text=str(total_count), width=6, anchor="center", font=("", 9, "bold")).pack(side=tk.LEFT)
    ttk.Label(total_row, text=total_val_str, width=12, anchor="e", font=("", 9, "bold")).pack(side=tk.LEFT)

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=12, pady=(4, 12))

    def proceed():
        overrides = {}
        for vendor, var in vendor_rows.items():
            choice = var.get().lower()  # "include", "defer", or "skip"
            if choice != "include":
                overrides[vendor] = choice
        if hasattr(app, "_vendor_export_scope_overrides"):
            app._vendor_export_scope_overrides = overrides
        result[0] = True
        dlg.destroy()

    def cancel():
        dlg.destroy()

    ttk.Button(btn_frame, text="Export", command=proceed).pack(side=tk.RIGHT, padx=(4, 0))
    ttk.Button(btn_frame, text="Cancel", command=cancel).pack(side=tk.RIGHT)

    if root:
        dlg.geometry(f"+{root.winfo_x() + 80}+{root.winfo_y() + 80}")
    dlg.wait_window()
    return result[0]


def show_release_plan(app):
    rows = build_vendor_release_plan_rows(app)
    if not rows:
        messagebox.showinfo("Release Plan", "No assigned vendor items are available for release planning.")
        return

    dlg = tk.Toplevel(app.root)
    dlg.title("Vendor Release Plan")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text="Vendor Release Plan", style="Header.TLabel").pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text="This view summarizes immediate, planned-today, and held items by vendor using the current shipping policy annotations.",
        style="SubHeader.TLabel",
        wraplength=980,
    ).pack(anchor="w", padx=16, pady=(0, 10))

    frame = ttk.Frame(dlg)
    frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

    columns = (
        "vendor", "recommended", "policy", "plan", "immediate", "planned", "held", "total_value",
        "shortfall", "progress", "coverage", "confidence", "known_pct", "cost_issues", "detail", "timing", "next_free", "planned_export",
    )
    tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
    headings = {
        "vendor": "Vendor",
        "recommended": "Recommended",
        "policy": "Policy",
        "plan": "Plan",
        "immediate": "Immediate",
        "planned": "Planned",
        "held": "Held",
        "total_value": "Vendor Value",
        "shortfall": "Shortfall",
        "progress": "Progress %",
        "coverage": "Coverage",
        "confidence": "Confidence",
        "known_pct": "Known %",
        "cost_issues": "Cost Issues",
        "detail": "Release Detail",
        "timing": "Timing",
        "next_free": "Next Free-Ship",
        "planned_export": "Planned Export",
    }
    widths = {
        "vendor": 110,
        "recommended": 170,
        "policy": 150,
        "plan": 180,
        "immediate": 70,
        "planned": 70,
        "held": 70,
        "total_value": 90,
        "shortfall": 90,
        "progress": 80,
        "coverage": 80,
        "confidence": 85,
        "known_pct": 75,
        "cost_issues": 95,
        "detail": 160,
        "timing": 170,
        "next_free": 100,
        "planned_export": 100,
    }
    for col in columns:
        tree.heading(col, text=headings[col])
        tree.column(col, width=widths[col], anchor="center" if col not in ("vendor", "policy") else "w")

    for idx, row in enumerate(rows):
        tree.insert(
            "",
            "end",
            iid=str(idx),
            values=(
                row["vendor"],
                row.get("recommended_action", "") or "-",
                row.get("shipping_policy", "") or "-",
                row.get("release_plan_label", "") or "-",
                row["release_now_count"],
                row["planned_today_count"],
                row["held_count"],
                f'{row["vendor_order_value_total"]:.2f}',
                f'{row["vendor_threshold_shortfall"]:.2f}',
                f'{row["vendor_threshold_progress_pct"]:.2f}',
                row.get("vendor_value_coverage", "") or "-",
                row.get("vendor_value_confidence", "") or "-",
                f'{float(row.get("vendor_value_known_pct", 0.0) or 0.0):.0f}',
                (
                    f'M{int(row.get("vendor_value_missing_cost_items", 0) or 0)}/'
                    f'Z{int(row.get("vendor_value_zero_cost_items", 0) or 0)}/'
                    f'I{int(row.get("vendor_value_invalid_cost_items", 0) or 0)}'
                ),
                row.get("release_decision_detail_label", "") or "-",
                row.get("release_timing_mode", "") or "-",
                row.get("next_free_ship_date", "") or "-",
                row.get("planned_export_date", "") or "-",
            ),
        )

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    attach_vertical_mousewheel(tree)

    action_row = ttk.Frame(dlg)
    action_row.pack(fill=tk.X, padx=16, pady=(4, 12))

    children = tree.get_children()
    if children:
        tree.selection_set(children[0])

    def _selected_vendor():
        values = tree_selected_values_or_first(tree)
        return values[0] if values else ""

    def _open_review(focus, release):
        vendor = _selected_vendor()
        if not vendor:
            messagebox.showinfo("Release Plan", "Select a vendor first.")
            return
        apply_release_plan_view(app, vendor, focus=focus, release=release)
        dlg.destroy()

    def _export_scope(release):
        vendor = _selected_vendor()
        if not vendor:
            messagebox.showinfo("Release Plan", "Select a vendor first.")
            return
        export_release_plan_scope(app, vendor, release=release)

    ttk.Button(action_row, text="View Vendor Exceptions", command=lambda: _open_review("Exceptions Only", "ALL")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="View Planned Today", command=lambda: _open_review("All Items", "Planned Today")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="View All Vendor Items", command=lambda: _open_review("All Items", "ALL")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Export Immediate", command=lambda: _export_scope("Release Now")).pack(side=tk.LEFT, padx=14)
    ttk.Button(action_row, text="Export Planned", command=lambda: _export_scope("Planned Today")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    app._autosize_dialog(dlg, min_w=920, min_h=360, max_w_ratio=0.92, max_h_ratio=0.85)
    dlg.wait_window()


def show_compact_review(app):
    rows = build_compact_review_rows(app)
    if not rows:
        messagebox.showinfo("Compact Review", "No assigned vendor items are available for compact review.")
        return

    dlg = tk.Toplevel(app.root)
    dlg.title("Compact Vendor Review")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text="Compact Vendor Review", style="Header.TLabel").pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text="This view groups vendors into ready-now, planned-today, and blocked states so you can act without scanning every item row.",
        style="SubHeader.TLabel",
        wraplength=920,
    ).pack(anchor="w", padx=16, pady=(0, 10))

    frame = ttk.Frame(dlg)
    frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

    columns = ("bucket", "vendor", "recommended", "immediate", "planned", "held", "reason")
    tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
    headings = {
        "bucket": "State",
        "vendor": "Vendor",
        "recommended": "Recommended",
        "immediate": "Immediate",
        "planned": "Planned",
        "held": "Held",
        "reason": "Why",
    }
    widths = {
        "bucket": 110,
        "vendor": 100,
        "recommended": 170,
        "immediate": 70,
        "planned": 70,
        "held": 70,
        "reason": 360,
    }
    for col in columns:
        tree.heading(col, text=headings[col])
        tree.column(col, width=widths[col], anchor="center" if col not in ("vendor", "recommended", "reason") else "w")

    for idx, row in enumerate(rows):
        tree.insert(
            "",
            "end",
            iid=str(idx),
            values=(
                row.get("compact_bucket", ""),
                row.get("vendor", ""),
                row.get("recommended_action", "") or "-",
                row.get("release_now_count", 0),
                row.get("planned_today_count", 0),
                row.get("held_count", 0),
                row.get("compact_reason", "") or "-",
            ),
        )

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    attach_vertical_mousewheel(tree)

    action_row = ttk.Frame(dlg)
    action_row.pack(fill=tk.X, padx=16, pady=(4, 12))

    children = tree.get_children()
    if children:
        tree.selection_set(children[0])

    def _selected_vendor_row():
        idx = tree_selected_index_or_first(tree)
        if idx is None:
            return None
        return rows[idx] if 0 <= idx < len(rows) else None

    def _open_selected(focus, release):
        row = _selected_vendor_row()
        if not row:
            messagebox.showinfo("Compact Review", "Select a vendor first.")
            return
        apply_release_plan_view(app, row.get("vendor", ""), focus=focus, release=release)
        dlg.destroy()

    def _export_selected(release):
        row = _selected_vendor_row()
        if not row:
            messagebox.showinfo("Compact Review", "Select a vendor first.")
            return
        export_release_plan_scope(app, row.get("vendor", ""), release=release)

    ttk.Button(action_row, text="View Vendor Exceptions", command=lambda: _open_selected("Exceptions Only", "ALL")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="View Planned Today", command=lambda: _open_selected("All Items", "Planned Today")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="View All Vendor Items", command=lambda: _open_selected("All Items", "ALL")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Export Immediate", command=lambda: _export_selected("Release Now")).pack(side=tk.LEFT, padx=14)
    ttk.Button(action_row, text="Export Planned", command=lambda: _export_selected("Planned Today")).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    app._autosize_dialog(dlg, min_w=860, min_h=320, max_w_ratio=0.9, max_h_ratio=0.8)
    dlg.wait_window()


def build_review_tab(app):
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  6. Review & Export  ")

    ttk.Label(frame, text="Review & Export", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text="Common path: review exceptions, then use Export Recommended. Final Qty is what will export. Why This Qty explains the calculation. Shipping planning columns show release posture, threshold shortfall, and planned timing. Double-click Final Qty, Vendor, or Pack to edit. Select rows and press Delete to remove.",
        style="SubHeader.TLabel",
        wraplength=800,
    ).pack(anchor="w", pady=(2, 8))
    app.lbl_review_data_source = ttk.Label(frame, text="", style="Info.TLabel")
    app.lbl_review_data_source.pack(anchor="w", pady=(0, 8))
    app._refresh_data_folder_labels()

    app.lbl_review_summary = ttk.Label(frame, text="", style="Info.TLabel")
    app.lbl_review_summary.pack(anchor="w", pady=(0, 8))

    filter_frame = ttk.Frame(frame)
    filter_frame.pack(fill=tk.X, pady=(0, 4))
    ttk.Label(filter_frame, text="Filter by Vendor:").pack(side=tk.LEFT, padx=(0, 6))
    app.var_vendor_filter = tk.StringVar(value="ALL")
    app.combo_vendor_filter = ttk.Combobox(
        filter_frame, textvariable=app.var_vendor_filter, state="readonly", width=20
    )
    app.combo_vendor_filter.pack(side=tk.LEFT)
    app.combo_vendor_filter.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Performance:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_performance_filter = tk.StringVar(value="ALL")
    app.combo_review_performance = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_performance_filter,
        state="readonly",
        width=12,
        values=["ALL", "Top", "Steady", "Intermittent", "Legacy"],
    )
    app.combo_review_performance.pack(side=tk.LEFT)
    app.combo_review_performance.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Attention:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_attention_filter = tk.StringVar(value="ALL")
    app.combo_review_attention = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_attention_filter,
        state="readonly",
        width=14,
        values=["ALL", "Normal", "Missed Reorder", "Lumpy Demand", "Receipt Heavy", "Pack Mismatch"],
    )
    app.combo_review_attention.pack(side=tk.LEFT)
    app.combo_review_attention.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Recency:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_recency_filter = tk.StringVar(value="ALL")
    app.combo_review_recency = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_recency_filter,
        state="readonly",
        width=24,
        values=["ALL"] + list(RECENCY_FILTER_LABELS.values()),
    )
    app.combo_review_recency.pack(side=tk.LEFT)
    app.combo_review_recency.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Suggestions:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_suggestion_filter = tk.StringVar(value="ALL")
    app.combo_review_suggestion = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_suggestion_filter,
        state="readonly",
        width=16,
        values=["ALL"] + list(SUGGESTION_FILTER_LABELS.values()),
    )
    app.combo_review_suggestion.pack(side=tk.LEFT)
    app.combo_review_suggestion.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Sug Source:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_suggestion_source_filter = tk.StringVar(value="ALL")
    app.combo_review_suggestion_source = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_suggestion_source_filter,
        state="readonly",
        width=20,
        values=["ALL"] + list(SUGGESTION_SOURCE_FILTER_LABELS.values()),
    )
    app.combo_review_suggestion_source.pack(side=tk.LEFT)
    app.combo_review_suggestion_source.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Release:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_release_filter = tk.StringVar(value="ALL")
    app.combo_review_release = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_release_filter,
        state="readonly",
        width=14,
        values=["ALL", "Release Now", "Planned Today", "Held", "Critical Held"],
    )
    app.combo_review_release.pack(side=tk.LEFT)
    app.combo_review_release.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Focus:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_focus_filter = tk.StringVar(value="All Items")
    app.combo_review_focus = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_focus_filter,
        state="readonly",
        width=16,
        values=["All Items", "Exceptions Only"],
    )
    app.combo_review_focus.pack(side=tk.LEFT)
    app.combo_review_focus.bind("<<ComboboxSelected>>", lambda e: on_review_focus_changed(app))

    tree_frame = ttk.Frame(frame)
    tree_frame.pack(fill=tk.BOTH, expand=True, pady=4)

    cols = (
        "vendor", "line_code", "item_code", "description", "order_qty", "status", "recommended_action",
        "release_decision", "release_decision_detail", "threshold_shortfall", "next_free_ship_date", "planned_export_date", "why", "pack_size",
    )
    app.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")

    col_widths = {
        "vendor": 90,
        "line_code": 60,
        "item_code": 110,
        "description": 200,
        "order_qty": 60,
        "status": 55,
        "recommended_action": 140,
        "release_decision": 120,
        "release_decision_detail": 150,
        "threshold_shortfall": 85,
        "next_free_ship_date": 95,
        "planned_export_date": 100,
        "why": 180,
        "pack_size": 45,
    }
    col_labels = {
        "vendor": "Vendor",
        "line_code": "LC",
        "item_code": "Item Code",
        "description": "Description",
        "order_qty": "Final Qty",
        "status": "Action",
        "recommended_action": "Recommended",
        "release_decision": "Release",
        "release_decision_detail": "Release Detail",
        "threshold_shortfall": "Shortfall",
        "next_free_ship_date": "Next Free",
        "planned_export_date": "Planned Export",
        "why": "Why This Qty",
        "pack_size": "Pack",
    }

    for col in cols:
        app.tree.heading(col, text=col_labels[col], command=lambda c=col: app._sort_tree(c))
        anchor = "center" if col in (
            "order_qty", "pack_size", "status", "threshold_shortfall", "next_free_ship_date", "planned_export_date",
        ) else "w"
        app.tree.column(col, width=col_widths[col], anchor=anchor)
    app.review_tree_labels = col_labels
    app.review_tree_columns = cols

    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=app.tree.yview)
    app.tree.configure(yscrollcommand=vsb.set)
    app.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    attach_vertical_mousewheel(app.tree)

    app.tree.bind("<Double-1>", app._on_tree_double_click)
    app.tree.bind("<Button-1>", app._on_review_tree_click)
    app.tree.bind("<Return>", app._on_review_tree_keyboard_edit)
    app.tree.bind("<F2>", app._on_review_tree_keyboard_edit)
    app.tree.bind("<Left>", app._on_review_tree_horizontal_nav)
    app.tree.bind("<Right>", app._on_review_tree_horizontal_nav)
    app.tree.bind("<Delete>", app._delete_selected)
    app.review_grid_editor = TreeGridEditor(
        app.root,
        app.tree,
        app.REVIEW_EDITABLE_COLS if hasattr(app, "REVIEW_EDITABLE_COLS") else ("vendor", "order_qty", "pack_size"),
        app._review_editor_widget,
        app._review_editor_value,
        app._review_apply_editor_value,
        app._review_refresh_editor_row,
    )

    memo_frame = ttk.Frame(frame)
    memo_frame.pack(fill=tk.X, pady=(0, 4))
    ttk.Label(memo_frame, text="PO Memo:").pack(side=tk.LEFT, padx=(0, 4))
    if getattr(app, "var_po_memo", None) is None:
        app.var_po_memo = tk.StringVar(value="")
    ttk.Entry(memo_frame, textvariable=app.var_po_memo, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(memo_frame, text="(written to Notes column in exported files)", style="Hint.TLabel").pack(side=tk.LEFT, padx=(6, 0))

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill=tk.X, pady=8)

    left_btn_row = ttk.Frame(btn_frame)
    left_btn_row.pack(anchor="w", fill=tk.X)
    ttk.Button(left_btn_row, text="Delete Selected", command=app._delete_selected).pack(side=tk.LEFT, padx=4)
    ttk.Button(left_btn_row, text="Back to Assignment", command=app._back_to_assign).pack(side=tk.LEFT, padx=4)
    ttk.Button(left_btn_row, text="Compact Review", command=lambda: show_compact_review(app)).pack(side=tk.LEFT, padx=4)
    ttk.Button(left_btn_row, text="Release Plan", command=lambda: show_release_plan(app)).pack(side=tk.LEFT, padx=4)

    right_btn_row = ttk.Frame(btn_frame)
    right_btn_row.pack(anchor="e", fill=tk.X, pady=(8, 0))
    ttk.Button(
        right_btn_row,
        text="Export Recommended",
        style="Big.TButton",
        command=lambda: export_review_recommended(app),
    ).pack(side=tk.RIGHT, padx=4)
    ttk.Button(
        right_btn_row,
        text="Export Planned Only",
        command=lambda: export_review_scope(app, "planned_only"),
    ).pack(side=tk.RIGHT, padx=4)
    ttk.Button(
        right_btn_row,
        text="Export Immediate Only",
        command=lambda: export_review_scope(app, "immediate_only"),
    ).pack(side=tk.RIGHT, padx=4)


def review_row_values(item):
    ps = item.get("pack_size")
    threshold_shortfall = item.get("vendor_threshold_shortfall")
    return (
        item["vendor"],
        item["line_code"],
        item["item_code"],
        item["description"],
        item["order_qty"],
        item.get("status", "ok"),
        item.get("recommended_action", "") or "-",
        item.get("release_decision", "") or "-",
        item.get("release_decision_detail_label", "") or item.get("release_decision_detail", "") or "-",
        f"{float(threshold_shortfall):.2f}" if isinstance(threshold_shortfall, (int, float)) else "-",
        item.get("next_free_ship_date", "") or "-",
        item.get("planned_export_date", "") or "-",
        item.get("why", ""),
        ps if ps else "",
    )


def populate_review_tab(app):
    flush_pending_bulk_sheet_edit(app)
    for item in app.tree.get_children():
        app.tree.delete(item)
    vendors = sorted(set(item["vendor"] for item in app.assigned_items))
    app.combo_vendor_filter["values"] = ["ALL"] + vendors
    app.var_vendor_filter.set("ALL")
    app.var_review_performance_filter.set("ALL")
    app.var_review_attention_filter.set("ALL")
    app.var_review_recency_filter.set("ALL")
    app.var_review_suggestion_filter.set("ALL")
    if hasattr(app, "var_review_suggestion_source_filter"):
        app.var_review_suggestion_source_filter.set("ALL")
    app.var_review_release_filter.set("ALL")
    focus, auto_fallback = resolved_review_focus_label(app)
    app._review_focus_auto_fallback = auto_fallback
    app.var_review_focus_filter.set(focus)
    apply_review_filter(app)
    update_review_summary(app)


def update_review_summary(app):
    vendors = set(item["vendor"] for item in app.assigned_items)
    held_count = sum(1 for item in app.assigned_items if release_filter_bucket(item) == "Held")
    critical_held_count = sum(1 for item in app.assigned_items if is_critical_shipping_hold(item))
    planned_count = sum(1 for item in app.assigned_items if release_filter_bucket(item) == "Planned Today")
    immediate_count = sum(1 for item in app.assigned_items if release_filter_bucket(item) == "Release Now")
    exception_count = sum(1 for item in app.assigned_items if is_review_exception(item))
    low_recency_counts = {}
    ambiguous_receipt_vendor_count = 0
    lumpy_demand_count = 0
    receipt_heavy_count = 0
    pack_mismatch_count = 0
    suggestion_gap_count = 0
    suggestion_gap_breakdown = {}
    suggestion_source_counts = {}
    value_coverage_issue_count = 0
    urgent_override_count = 0
    for item in app.assigned_items:
        bucket = item.get("recency_review_bucket")
        if bucket:
            low_recency_counts[bucket] = low_recency_counts.get(bucket, 0) + 1
        if has_urgent_release_override(item):
            urgent_override_count += 1
        if item.get("receipt_vendor_ambiguous"):
            ambiguous_receipt_vendor_count += 1
        if str(item.get("reorder_attention_signal", "") or "").strip().lower() == "review_lumpy_demand":
            lumpy_demand_count += 1
        if str(item.get("reorder_attention_signal", "") or "").strip().lower() == "review_receipt_heavy":
            receipt_heavy_count += 1
        if item.get("receipt_pack_mismatch"):
            pack_mismatch_count += 1
        if has_suggestion_gap(item):
            suggestion_gap_count += 1
            code = str(item.get("detailed_suggestion_compare", "") or "").strip().lower()
            if code:
                suggestion_gap_breakdown[code] = suggestion_gap_breakdown.get(code, 0) + 1
        source_code = str(item.get("suggested_source", "") or "").strip().lower()
        if source_code:
            suggestion_source_counts[source_code] = suggestion_source_counts.get(source_code, 0) + 1
        if str(item.get("vendor_value_coverage", "") or "").strip().lower() in ("partial", "missing"):
            value_coverage_issue_count += 1
    exportable_count = immediate_count + planned_count
    hold_summary = f" | Exportable now: {exportable_count} | Immediate: {immediate_count} | Exceptions: {exception_count}"
    if planned_count:
        hold_summary += f" | Planned today: {planned_count}"
    if held_count:
        hold_summary += f" | Held by shipping policy: {held_count}"
    if critical_held_count:
        hold_summary += f" | Critical held: {critical_held_count}"
    if urgent_override_count:
        hold_summary += f" | Urgent overrides: {urgent_override_count}"
    if value_coverage_issue_count:
        hold_summary += f" | Value coverage issues: {value_coverage_issue_count}"
    if ambiguous_receipt_vendor_count:
        hold_summary += f" | Receipt vendor ambiguity: {ambiguous_receipt_vendor_count}"
    if lumpy_demand_count:
        hold_summary += f" | Lumpy demand: {lumpy_demand_count}"
    if receipt_heavy_count:
        hold_summary += f" | Receipt-heavy vs sales: {receipt_heavy_count}"
    if pack_mismatch_count:
        hold_summary += f" | Receipt pack mismatch: {pack_mismatch_count}"
    if suggestion_gap_count:
        hold_summary += f" | Suggestion gaps: {suggestion_gap_count}"
        gap_parts = []
        for code in ("detailed_only", "detailed_higher", "detailed_lower", "different"):
            count = suggestion_gap_breakdown.get(code)
            if count:
                gap_parts.append(f"{count} {SUGGESTION_FILTER_LABELS.get(code, code).lower()}")
        if gap_parts:
            hold_summary += f" ({', '.join(gap_parts)})"
    if suggestion_source_counts:
        source_parts = []
        for code in ("detailed_sales_fallback", "x4_mo12_sales", "provided"):
            count = suggestion_source_counts.get(code)
            if count:
                source_parts.append(f"{count} {SUGGESTION_SOURCE_FILTER_LABELS.get(code, code).lower()}")
        if source_parts:
            hold_summary += f" | Suggestion sources: {', '.join(source_parts)}"
    if low_recency_counts:
        parts = []
        for bucket in (
            "stale_or_likely_dead",
            "new_or_sparse",
            "missing_data_uncertain",
            "recent_local_po_protected",
            "activity_protected",
            "receipt_heavy_unverified",
            "critical_min_rule_protected",
            "critical_rule_protected",
        ):
            count = low_recency_counts.get(bucket)
            if count:
                parts.append(f"{count} {recency_filter_label({'recency_review_bucket': bucket}).lower()}")
        hold_summary += f" | Low-confidence recency: {sum(low_recency_counts.values())}"
        if parts:
            hold_summary += f" ({', '.join(parts)})"
    app.lbl_review_summary.config(
        text=(
            f"{len(app.assigned_items)} items across {len(vendors)} vendor PO(s): {', '.join(sorted(vendors))} | "
            f"Final Qty exports. Why This Qty explains the recommendation."
            f"{' No review exceptions were found, so all items are shown.' if getattr(app, '_review_focus_auto_fallback', False) else ''}"
            f"{hold_summary}"
        )
    )


def apply_review_filter(app):
    flush_pending_bulk_sheet_edit(app)
    vendor_filter = app.var_vendor_filter.get()
    performance_filter = app.var_review_performance_filter.get()
    attention_filter = app.var_review_attention_filter.get()
    recency_filter = app.var_review_recency_filter.get()
    suggestion_filter_var = getattr(app, "var_review_suggestion_filter", None)
    suggestion_filter = suggestion_filter_var.get() if suggestion_filter_var and hasattr(suggestion_filter_var, "get") else "ALL"
    suggestion_source_filter_var = getattr(app, "var_review_suggestion_source_filter", None)
    suggestion_source_filter = (
        suggestion_source_filter_var.get()
        if suggestion_source_filter_var and hasattr(suggestion_source_filter_var, "get")
        else "ALL"
    )
    release_filter = app.var_review_release_filter.get()
    focus_filter = app.var_review_focus_filter.get()
    for item_id in app.tree.get_children():
        app.tree.delete(item_id)
    for i, item in enumerate(app.assigned_items):
        if focus_filter == "Exceptions Only" and not is_review_exception(item):
            continue
        if vendor_filter != "ALL" and item["vendor"] != vendor_filter:
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
        if attention_filter != "ALL":
            attention = (item.get("reorder_attention_signal", "") or "").lower()
            if attention_filter == "Pack Mismatch":
                if not item.get("receipt_pack_mismatch"):
                    continue
                attention = "review_receipt_pack_mismatch"
            expected_attention = {
                "Normal": "normal",
                "Missed Reorder": "review_missed_reorder",
                "Lumpy Demand": "review_lumpy_demand",
                "Receipt Heavy": "review_receipt_heavy",
                "Pack Mismatch": "review_receipt_pack_mismatch",
            }.get(attention_filter, "")
            if attention != expected_attention:
                continue
        if recency_filter != "ALL" and recency_filter_label(item) != recency_filter:
            continue
        if suggestion_filter != "ALL" and suggestion_filter_label(item) != suggestion_filter:
            continue
        if suggestion_source_filter != "ALL" and suggestion_source_filter_label(item) != suggestion_source_filter:
            continue
        if release_filter != "ALL":
            if release_filter == "Critical Held":
                if not is_critical_shipping_hold(item):
                    continue
            elif release_filter_bucket(item) != release_filter:
                continue
        app.tree.insert("", "end", iid=str(i), values=review_row_values(item))


def sort_tree(app, col):
    flush_pending_bulk_sheet_edit(app)
    items = [(app.tree.set(k, col), k) for k in app.tree.get_children("")]
    try:
        items.sort(key=lambda t: float(t[0]))
    except ValueError:
        items.sort(key=lambda t: t[0].lower())
    for index, (_, k) in enumerate(items):
        app.tree.move(k, "", index)


def show_maintenance_report(app, output_dir, issues):
    if not issues:
        return

    dlg = tk.Toplevel(app.root)
    dlg.title("X4 Maintenance Report")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    n_supplier = sum(1 for r in issues if "supplier" in r.issue.lower())
    n_minmax = sum(1 for r in issues if "min/max" in r.issue.lower())
    n_mult = sum(1 for r in issues if "order multiple" in r.issue.lower())
    n_qoh = sum(1 for r in issues if "QOH adjusted" in r.issue)

    ttk.Label(
        dlg,
        text=f"{len(issues)} item(s) to update in X4",
        style="Header.TLabel",
        wraplength=1000,
    ).pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text=(
            "This report is a follow-up checklist for X4. It does not change X4 automatically. "
            "Use it to review supplier, pack, min/max, and QOH differences after export."
        ),
        style="SubHeader.TLabel",
        wraplength=1000,
    ).pack(anchor="w", padx=16, pady=(0, 10))

    summary_parts = []
    if n_supplier:
        summary_parts.append(f"{n_supplier} supplier")
    if n_minmax:
        summary_parts.append(f"{n_minmax} min/max")
    if n_mult:
        summary_parts.append(f"{n_mult} order multiple")
    if n_qoh:
        summary_parts.append(f"{n_qoh} QOH adjustment")
    ttk.Label(
        dlg,
        text="Issues found: " + ", ".join(summary_parts),
        style="SubHeader.TLabel",
        wraplength=1000,
    ).pack(anchor="w", padx=16, pady=(0, 12))

    tree_frame = ttk.Frame(dlg)
    tree_frame.pack(fill=tk.BOTH, expand=True, padx=16)

    cols = ("line_code", "item_code", "vendor", "x4_supplier", "x4_mm", "target_mm", "sug_mm", "qoh_adj", "issue")
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="none")

    col_cfg = {
        "line_code": ("LC", 55),
        "item_code": ("Item Code", 105),
        "vendor": ("Vendor", 78),
        "x4_supplier": ("X4 Supp", 78),
        "x4_mm": ("X4 M/M", 62),
        "target_mm": ("App M/M", 62),
        "sug_mm": ("Sug M/M", 62),
        "qoh_adj": ("QOH Adj", 80),
        "issue": ("Details", 360),
    }
    for col in cols:
        label, width = col_cfg[col]
        tree.heading(col, text=label)
        tree.column(col, width=width, anchor="w")

    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    attach_vertical_mousewheel(tree)
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)

    for i, row in enumerate(issues):
        x4_mm = f"{row.x4_min}/{row.x4_max}" if row.x4_min != "" or row.x4_max != "" else ""
        target_mm = f"{row.target_min}/{row.target_max}" if row.target_min != "" or row.target_max != "" else ""
        sug_mm = f"{row.sug_min}/{row.sug_max}" if row.sug_min != "" or row.sug_max != "" else ""
        qoh_adj = f"{row.qoh_old} -> {row.qoh_new}" if row.qoh_old else ""

        tree.insert(
            "",
            "end",
            iid=str(i),
            values=(
                row.line_code,
                row.item_code,
                row.assigned_vendor,
                row.x4_supplier,
                x4_mm,
                target_mm,
                sug_mm,
                qoh_adj,
                row.issue,
            ),
        )

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)

    def _export_csv():
        try:
            path = app._export_maintenance_csv(issues, output_dir)
            messagebox.showinfo("Saved", f"Maintenance report saved to:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save CSV:\n{e}")

    ttk.Button(btn_frame, text="Save as CSV", style="Big.TButton", command=_export_csv).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    app._autosize_dialog(dlg, min_w=1020, min_h=540, max_w_ratio=0.97, max_h_ratio=0.92)
    dlg.wait_window()
