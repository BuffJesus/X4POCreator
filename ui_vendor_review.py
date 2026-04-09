"""'Vendor Review' dialog — per-vendor activity from session snapshots.

Pure helpers live in vendor_summary_flow; this module wires them into a
Tkinter dialog opened from the bulk tab vendor row.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import storage
import vendor_summary_flow


def _format_session_date(value: str) -> str:
    if not value:
        return ""
    # snapshots use ISO timestamps; show just the date for readability
    return value.split("T", 1)[0]


def _format_lead(days):
    label = vendor_summary_flow.format_lead_time_label(days)
    return label or "—"


def open_vendor_review_dialog(app, *, focus_vendor=None):
    sessions_dir = app._data_path("sessions")
    snapshots = storage.load_session_snapshots(sessions_dir, max_count=25) or []
    lead_times = storage.infer_vendor_lead_times(snapshots) or {}
    vendor_codes = list(getattr(app, "vendor_codes_used", None) or [])
    summaries = vendor_summary_flow.summarize_all_vendors(
        snapshots,
        vendor_codes=vendor_codes or None,
        lead_times=lead_times,
        top_n=5,
    )

    dlg = tk.Toplevel(app.root)
    dlg.title("Vendor Review")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(
        dlg,
        text=f"{len(summaries)} vendor(s) — most-active first.",
        style="Header.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text=(
            "Lead times are inferred from snapshot pairs where an item moved "
            "from On PO to Received between sessions.  Click a row to see the "
            "vendor's top items in the bottom panel."
        ),
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(0, 8))

    if not summaries:
        ttk.Label(
            dlg,
            text=(
                "No vendor activity found in sessions/.  Run an export first or "
                "check that the sessions folder contains snapshot files."
            ),
            style="Info.TLabel",
            wraplength=900,
        ).pack(anchor="w", padx=16, pady=(0, 12))
        ttk.Button(dlg, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=16, pady=12)
        if hasattr(app, "_autosize_dialog"):
            app._autosize_dialog(dlg, min_w=620, min_h=220, max_w_ratio=0.6, max_h_ratio=0.4)
        dlg.wait_window()
        return

    paned = ttk.PanedWindow(dlg, orient=tk.VERTICAL)
    paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

    # Top: vendor table
    top_frame = ttk.Frame(paned)
    paned.add(top_frame, weight=3)

    columns = ("vendor", "orders", "qty_ordered", "qty_received", "last_session", "lead")
    col_cfg = [
        ("vendor",       "Vendor",        140, "w"),
        ("orders",       "Orders",        70,  "e"),
        ("qty_ordered",  "Qty Ordered",   100, "e"),
        ("qty_received", "Qty Received",  100, "e"),
        ("last_session", "Last Session",  120, "w"),
        ("lead",         "Lead Time",     90,  "e"),
    ]
    tree = ttk.Treeview(top_frame, columns=columns, show="headings", selectmode="browse")
    for col, heading, width, anchor in col_cfg:
        tree.heading(col, text=heading)
        tree.column(col, width=width, anchor=anchor, stretch=(col == "vendor"))
    vsb = ttk.Scrollbar(top_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    top_frame.grid_rowconfigure(0, weight=1)
    top_frame.grid_columnconfigure(0, weight=1)

    summary_by_iid: dict[str, dict] = {}
    for idx, summary in enumerate(summaries):
        iid = str(idx)
        summary_by_iid[iid] = summary
        tree.insert(
            "", "end", iid=iid,
            values=(
                summary.get("vendor_code", ""),
                summary.get("order_count", 0),
                summary.get("total_qty_ordered", 0),
                summary.get("total_qty_received", 0),
                _format_session_date(summary.get("last_session_date", "")),
                _format_lead(summary.get("inferred_lead_days")),
            ),
        )

    # Bottom: top items for the selected vendor
    bottom_frame = ttk.Frame(paned)
    paned.add(bottom_frame, weight=2)

    ttk.Label(
        bottom_frame,
        text="Top items for selected vendor (by total qty ordered across loaded snapshots):",
        style="SubHeader.TLabel",
    ).pack(anchor="w", pady=(0, 4))

    item_columns = ("lc", "item_code", "description", "qty")
    item_tree = ttk.Treeview(bottom_frame, columns=item_columns, show="headings", selectmode="browse")
    item_tree.heading("lc",          text="LC")
    item_tree.heading("item_code",   text="Item Code")
    item_tree.heading("description", text="Description")
    item_tree.heading("qty",         text="Qty")
    item_tree.column("lc",          width=60,  anchor="w")
    item_tree.column("item_code",   width=130, anchor="w")
    item_tree.column("description", width=320, anchor="w", stretch=True)
    item_tree.column("qty",         width=80,  anchor="e")
    item_vsb = ttk.Scrollbar(bottom_frame, orient="vertical", command=item_tree.yview)
    item_tree.configure(yscrollcommand=item_vsb.set)
    item_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    item_vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _refresh_top_items(event=None):
        item_tree.delete(*item_tree.get_children())
        sel = tree.selection()
        if not sel:
            return
        summary = summary_by_iid.get(sel[0])
        if not summary:
            return
        for top in summary.get("top_items", []) or []:
            item_tree.insert(
                "", "end",
                values=(
                    top.get("line_code", ""),
                    top.get("item_code", ""),
                    top.get("description", ""),
                    top.get("qty", 0),
                ),
            )

    tree.bind("<<TreeviewSelect>>", _refresh_top_items)
    if summaries:
        target = str(focus_vendor or "").strip().upper()
        focus_iid = "0"
        if target:
            for iid, summary in summary_by_iid.items():
                if str(summary.get("vendor_code", "") or "").strip().upper() == target:
                    focus_iid = iid
                    break
        tree.selection_set(focus_iid)
        tree.see(focus_iid)
        _refresh_top_items()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Close", style="Big.TButton", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    if hasattr(app, "_autosize_dialog"):
        app._autosize_dialog(dlg, min_w=860, min_h=580, max_w_ratio=0.85, max_h_ratio=0.85)
    dlg.wait_window()
