"""'Supplier Map' dialog — view, edit, learn, and apply supplier→vendor pairs.

Pure helpers live in supplier_map_flow; this module wires them into a
small Tkinter dialog and the bulk tab.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import storage
import supplier_map_flow
import ui_bulk


def open_supplier_map_dialog(app):
    path = app._data_path("supplier_vendor_map")
    mapping = supplier_map_flow.load_supplier_map(path)

    dlg = tk.Toplevel(app.root)
    dlg.title("Supplier Map")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(
        dlg,
        text="Map an X4 supplier code to the vendor code you want assigned automatically.",
        style="Header.TLabel",
        wraplength=720,
    ).pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text=(
            "Apply to Session fills in unassigned items whose supplier matches a row below.  "
            "Manual vendor assignments are never overwritten."
        ),
        style="SubHeader.TLabel",
        wraplength=720,
    ).pack(anchor="w", padx=16, pady=(0, 8))

    container = ttk.Frame(dlg)
    container.pack(fill=tk.BOTH, expand=True, padx=16)

    columns = ("supplier", "vendor")
    tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="extended")
    tree.heading("supplier", text="Supplier Code")
    tree.heading("vendor", text="Mapped Vendor")
    tree.column("supplier", width=220, anchor="w")
    tree.column("vendor", width=220, anchor="w")
    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)

    # Local working copy — we don't write the file or touch the session
    # until the operator hits Save.
    working: dict[str, str] = dict(mapping)

    def _refresh():
        tree.delete(*tree.get_children())
        for supplier in sorted(working):
            tree.insert("", "end", iid=supplier, values=(supplier, working[supplier]))
        lbl_count.config(text=f"{len(working)} supplier mapping(s)")

    edit_row = ttk.Frame(dlg)
    edit_row.pack(fill=tk.X, padx=16, pady=(8, 0))
    ttk.Label(edit_row, text="Supplier:").pack(side=tk.LEFT)
    var_supplier = tk.StringVar()
    ttk.Entry(edit_row, textvariable=var_supplier, width=18).pack(side=tk.LEFT, padx=(4, 12))
    ttk.Label(edit_row, text="Vendor:").pack(side=tk.LEFT)
    var_vendor = tk.StringVar()
    ttk.Entry(edit_row, textvariable=var_vendor, width=18).pack(side=tk.LEFT, padx=(4, 12))

    def _add_or_update():
        supplier = str(var_supplier.get() or "").strip().upper()
        vendor = str(var_vendor.get() or "").strip().upper()
        if not supplier or not vendor:
            messagebox.showinfo("Missing Code", "Both supplier and vendor are required.", parent=dlg)
            return
        working[supplier] = vendor
        var_supplier.set("")
        var_vendor.set("")
        _refresh()

    ttk.Button(edit_row, text="Add / Update", command=_add_or_update).pack(side=tk.LEFT, padx=4)

    def _remove_selected():
        for iid in tree.selection():
            working.pop(iid, None)
        _refresh()

    ttk.Button(edit_row, text="Remove Selected", command=_remove_selected).pack(side=tk.LEFT, padx=4)

    def _learn_from_history():
        sessions_dir = app._data_path("sessions")
        snapshots = storage.load_session_snapshots(sessions_dir, max_count=25) or []
        inferred = supplier_map_flow.build_supplier_map_from_history(snapshots)
        if not inferred:
            messagebox.showinfo(
                "Nothing to Learn",
                "No supplier→vendor pairs could be inferred from recent session snapshots.",
                parent=dlg,
            )
            return
        before = len(working)
        merged = supplier_map_flow.merge_supplier_maps(working, inferred)  # base wins
        added = sum(1 for k in merged if k not in working)
        working.clear()
        working.update(merged)
        _refresh()
        messagebox.showinfo(
            "Auto-learn Complete",
            f"Scanned {len(snapshots)} snapshot(s).  Added {added} new mapping(s); "
            f"existing {before} entry/entries kept.",
            parent=dlg,
        )

    footer = ttk.Frame(dlg)
    footer.pack(fill=tk.X, padx=16, pady=(8, 0))
    lbl_count = ttk.Label(footer, text="", style="Info.TLabel")
    lbl_count.pack(side=tk.LEFT)
    ttk.Button(footer, text="Auto-learn from History", command=_learn_from_history).pack(side=tk.LEFT, padx=12)

    def _apply_to_session():
        items = list(getattr(app, "filtered_items", []) or [])
        pairs = supplier_map_flow.apply_supplier_map(items, working)
        if not pairs:
            messagebox.showinfo(
                "Nothing to Apply",
                "No unassigned items in the current session match a mapped supplier.",
                parent=dlg,
            )
            return
        for item, vendor in pairs:
            item["vendor"] = vendor
        if hasattr(app, "_apply_bulk_filter"):
            app._apply_bulk_filter()
        if hasattr(app, "_update_bulk_summary"):
            app._update_bulk_summary()
        messagebox.showinfo(
            "Applied",
            f"Auto-assigned {len(pairs)} item(s) from {len({v for _i, v in pairs})} vendor(s).",
            parent=dlg,
        )

    def _save_and_close():
        try:
            supplier_map_flow.save_supplier_map(path, working)
        except Exception as exc:
            messagebox.showerror("Save Failed", f"Could not write {path}:\n{exc}", parent=dlg)
            return
        dlg.destroy()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Apply to Session", command=_apply_to_session).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Save", style="Big.TButton", command=_save_and_close).pack(side=tk.RIGHT, padx=4)

    _refresh()
    if hasattr(app, "_autosize_dialog"):
        app._autosize_dialog(dlg, min_w=720, min_h=480, max_w_ratio=0.8, max_h_ratio=0.85)
    dlg.wait_window()
