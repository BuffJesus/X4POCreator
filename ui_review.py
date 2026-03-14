import os
import tkinter as tk
from tkinter import ttk, messagebox

from ui_grid_edit import TreeGridEditor
from ui_scroll import attach_vertical_mousewheel


def flush_pending_bulk_sheet_edit(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet and hasattr(bulk_sheet, "flush_pending_edit"):
        bulk_sheet.flush_pending_edit()


def release_filter_bucket(item):
    decision = str(item.get("release_decision", "") or "").strip()
    if decision in ("hold_for_free_day", "hold_for_threshold"):
        return "Held"
    if decision == "export_next_business_day_for_free_day":
        return "Planned Today"
    return "Release Now"


def build_review_tab(app):
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  6. Review & Export  ")

    ttk.Label(frame, text="Review & Export", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text="Review assigned items below. Final Qty is what will export. Why This Qty explains the calculation. Double-click Final Qty, Vendor, or Pack to edit. Select rows and press Delete to remove.",
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
        values=["ALL", "Normal", "Missed Reorder"],
    )
    app.combo_review_attention.pack(side=tk.LEFT)
    app.combo_review_attention.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    ttk.Label(filter_frame, text="Release:").pack(side=tk.LEFT, padx=(12, 6))
    app.var_review_release_filter = tk.StringVar(value="ALL")
    app.combo_review_release = ttk.Combobox(
        filter_frame,
        textvariable=app.var_review_release_filter,
        state="readonly",
        width=14,
        values=["ALL", "Release Now", "Planned Today", "Held"],
    )
    app.combo_review_release.pack(side=tk.LEFT)
    app.combo_review_release.bind("<<ComboboxSelected>>", lambda e: app._apply_review_filter())

    tree_frame = ttk.Frame(frame)
    tree_frame.pack(fill=tk.BOTH, expand=True, pady=4)

    cols = ("vendor", "line_code", "item_code", "description", "order_qty", "status", "why", "pack_size")
    app.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")

    col_widths = {
        "vendor": 90,
        "line_code": 60,
        "item_code": 110,
        "description": 200,
        "order_qty": 60,
        "status": 55,
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
        "why": "Why This Qty",
        "pack_size": "Pack",
    }

    for col in cols:
        app.tree.heading(col, text=col_labels[col], command=lambda c=col: app._sort_tree(c))
        anchor = "center" if col in ("order_qty", "pack_size", "status") else "w"
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

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill=tk.X, pady=8)

    left_btn_row = ttk.Frame(btn_frame)
    left_btn_row.pack(anchor="w", fill=tk.X)
    ttk.Button(left_btn_row, text="Delete Selected", command=app._delete_selected).pack(side=tk.LEFT, padx=4)
    ttk.Button(left_btn_row, text="Back to Assignment", command=app._back_to_assign).pack(side=tk.LEFT, padx=4)

    right_btn_row = ttk.Frame(btn_frame)
    right_btn_row.pack(anchor="e", fill=tk.X, pady=(8, 0))
    ttk.Button(right_btn_row, text="Export POs", style="Big.TButton", command=app._do_export).pack(
        side=tk.RIGHT, padx=4
    )


def review_row_values(item):
    ps = item.get("pack_size")
    return (
        item["vendor"],
        item["line_code"],
        item["item_code"],
        item["description"],
        item["order_qty"],
        item.get("status", "ok"),
        item.get("why", ""),
        ps if ps else "",
    )


def populate_review_tab(app):
    flush_pending_bulk_sheet_edit(app)
    for item in app.tree.get_children():
        app.tree.delete(item)
    for i, item in enumerate(app.assigned_items):
        app.tree.insert("", "end", iid=str(i), values=review_row_values(item))
    vendors = sorted(set(item["vendor"] for item in app.assigned_items))
    app.combo_vendor_filter["values"] = ["ALL"] + vendors
    app.var_vendor_filter.set("ALL")
    app.var_review_performance_filter.set("ALL")
    app.var_review_attention_filter.set("ALL")
    app.var_review_release_filter.set("ALL")
    update_review_summary(app)


def update_review_summary(app):
    vendors = set(item["vendor"] for item in app.assigned_items)
    held_count = sum(1 for item in app.assigned_items if release_filter_bucket(item) == "Held")
    planned_count = sum(1 for item in app.assigned_items if release_filter_bucket(item) == "Planned Today")
    immediate_count = sum(1 for item in app.assigned_items if release_filter_bucket(item) == "Release Now")
    exportable_count = immediate_count + planned_count
    hold_summary = f" | Exportable now: {exportable_count} | Immediate: {immediate_count}"
    if planned_count:
        hold_summary += f" | Planned today: {planned_count}"
    if held_count:
        hold_summary += f" | Held by shipping policy: {held_count}"
    app.lbl_review_summary.config(
        text=(
            f"{len(app.assigned_items)} items across {len(vendors)} vendor PO(s): {', '.join(sorted(vendors))} | "
            f"Final Qty exports. Why This Qty explains the recommendation.{hold_summary}"
        )
    )


def apply_review_filter(app):
    flush_pending_bulk_sheet_edit(app)
    vendor_filter = app.var_vendor_filter.get()
    performance_filter = app.var_review_performance_filter.get()
    attention_filter = app.var_review_attention_filter.get()
    release_filter = app.var_review_release_filter.get()
    for item_id in app.tree.get_children():
        app.tree.delete(item_id)
    for i, item in enumerate(app.assigned_items):
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
            expected_attention = {
                "Normal": "normal",
                "Missed Reorder": "review_missed_reorder",
            }.get(attention_filter, "")
            if attention != expected_attention:
                continue
        if release_filter != "ALL" and release_filter_bucket(item) != release_filter:
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
