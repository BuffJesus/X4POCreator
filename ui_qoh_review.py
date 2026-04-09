"""'QOH Adjustments' review dialog.

Surfaces every QOH edit the operator has made in the current session,
with a Revert Selected action.  Pure helpers live in qoh_review_flow.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import qoh_review_flow


def open_qoh_review_dialog(app):
    adjustments = getattr(app, "qoh_adjustments", {}) or {}
    inv_lookup = getattr(app, "inventory_lookup", {}) or {}

    dlg = tk.Toplevel(app.root)
    dlg.title("QOH Adjustments")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(
        dlg,
        text="Every QOH edit you've made this session.",
        style="Header.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text=(
            "Select rows and click Revert Selected to restore the original "
            "on-hand value.  Reverting also drops the row from this list."
        ),
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(0, 8))

    container = ttk.Frame(dlg)
    container.pack(fill=tk.BOTH, expand=True, padx=16)

    columns = ("lc", "item_code", "description", "old_qoh", "new_qoh", "delta")
    tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="extended")
    col_cfg = [
        ("lc",          "LC",        60,  "w"),
        ("item_code",   "Item Code", 130, "w"),
        ("description", "Description", 320, "w"),
        ("old_qoh",     "Old QOH",   80,  "e"),
        ("new_qoh",     "New QOH",   80,  "e"),
        ("delta",       "Delta",     80,  "e"),
    ]
    for col, heading, width, anchor in col_cfg:
        tree.heading(col, text=heading)
        tree.column(col, width=width, anchor=anchor, stretch=(col == "description"))
    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)

    # Map iid → key so revert can look the row back up.
    iid_to_key: dict[str, tuple[str, str]] = {}

    def _format_qty(value: float) -> str:
        if value == int(value):
            return f"{int(value)}"
        return f"{value:g}"

    def _refresh():
        tree.delete(*tree.get_children())
        iid_to_key.clear()
        rows = qoh_review_flow.format_qoh_adjustments(adjustments, inv_lookup)
        for r, row in enumerate(rows):
            iid = str(r)
            iid_to_key[iid] = (row["line_code"], row["item_code"])
            tree.insert(
                "", "end", iid=iid,
                values=(
                    row["line_code"],
                    row["item_code"],
                    row["description"],
                    _format_qty(row["old_qoh"]),
                    _format_qty(row["new_qoh"]),
                    ("+" if row["delta"] > 0 else "") + _format_qty(row["delta"]),
                ),
            )
        if rows:
            lbl_count.config(text=f"{len(rows)} adjustment(s) this session")
        else:
            lbl_count.config(text="No adjustments this session")

    footer = ttk.Frame(dlg)
    footer.pack(fill=tk.X, padx=16, pady=(8, 0))
    lbl_count = ttk.Label(footer, text="", style="Info.TLabel")
    lbl_count.pack(side=tk.LEFT)

    def _revert_selected():
        selected = list(tree.selection())
        if not selected:
            messagebox.showinfo("No Selection", "Select at least one row to revert.", parent=dlg)
            return
        keys = [iid_to_key[iid] for iid in selected if iid in iid_to_key]
        if not keys:
            return
        if not messagebox.askyesno(
            "Confirm Revert",
            f"Revert {len(keys)} QOH edit(s) to their original value?",
            parent=dlg,
        ):
            return
        reverted = qoh_review_flow.revert_qoh_adjustments(adjustments, inv_lookup, keys)
        if reverted:
            # Re-run per-item recalculation for the affected rows so the
            # bulk grid reflects the restored QOH and downstream order
            # quantities snap back to their pre-edit suggestions.
            recalculate = getattr(app, "_recalculate_item", None)
            for key in keys:
                for source in (
                    getattr(app, "filtered_items", []) or [],
                    getattr(app, "assigned_items", []) or [],
                ):
                    for item in source:
                        if (item.get("line_code", ""), item.get("item_code", "")) == key:
                            inv = inv_lookup.get(key, {}) or {}
                            if "inventory" in item:
                                item["inventory"] = inv
                            if callable(recalculate):
                                try:
                                    recalculate(item)
                                except Exception:
                                    pass
            if hasattr(app, "_apply_bulk_filter"):
                app._apply_bulk_filter()
            if hasattr(app, "_update_bulk_summary"):
                app._update_bulk_summary()
        _refresh()

    ttk.Button(footer, text="Revert Selected", command=_revert_selected).pack(side=tk.LEFT, padx=12)

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Close", style="Big.TButton", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    _refresh()
    if hasattr(app, "_autosize_dialog"):
        app._autosize_dialog(dlg, min_w=860, min_h=480, max_w_ratio=0.85, max_h_ratio=0.85)
    dlg.wait_window()
