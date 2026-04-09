"""'Session Diff' dialog — what changed since the most recent snapshot.

Pure helpers live in session_diff_flow; this module wires them into a
Tkinter dialog with one tab per change category.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import session_diff_flow


_TAB_DEFS = (
    ("new_items",     "New",            ("lc", "item_code", "description", "qty", "vendor")),
    ("removed_items", "Removed",        ("lc", "item_code", "description", "qty", "vendor")),
    ("qty_increased", "Qty Up",         ("lc", "item_code", "description", "old_qty", "new_qty", "delta")),
    ("qty_decreased", "Qty Down",       ("lc", "item_code", "description", "old_qty", "new_qty", "delta")),
    ("vendor_changed","Vendor Changed", ("lc", "item_code", "description", "old_vendor", "new_vendor")),
)


_HEADINGS = {
    "lc":          ("LC",          60,  "w"),
    "item_code":   ("Item Code",   130, "w"),
    "description": ("Description", 320, "w"),
    "qty":         ("Qty",         80,  "e"),
    "old_qty":     ("Old Qty",     80,  "e"),
    "new_qty":     ("New Qty",     80,  "e"),
    "delta":       ("Delta",       80,  "e"),
    "vendor":      ("Vendor",      120, "w"),
    "old_vendor":  ("Old Vendor",  120, "w"),
    "new_vendor":  ("New Vendor",  120, "w"),
}


def _build_current_snapshot(app):
    """Pull the in-progress session into a snapshot-shaped dict."""
    items = []
    for source in (
        getattr(app, "assigned_items", []) or [],
        getattr(app, "filtered_items", []) or [],
    ):
        for item in source:
            if not isinstance(item, dict):
                continue
            items.append(item)
        if items:
            break  # prefer assigned_items if non-empty
    return {"exported_items": items}


def open_session_diff_dialog(app):
    sessions_dir = app._data_path("sessions")
    previous = session_diff_flow.load_previous_snapshot(sessions_dir)
    current = _build_current_snapshot(app)
    diff = session_diff_flow.diff_sessions(previous, current)

    dlg = tk.Toplevel(app.root)
    dlg.title("Session Diff")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    summary_text = session_diff_flow.format_diff_summary(diff) or "No changes since the last session."
    label_text = "Compared against the most recent snapshot in sessions/."
    prev_label = session_diff_flow.snapshot_label(previous)
    if prev_label:
        label_text = f"Compared against snapshot from {prev_label}."

    ttk.Label(dlg, text=summary_text, style="Header.TLabel", wraplength=900).pack(
        anchor="w", padx=16, pady=(16, 4)
    )
    ttk.Label(dlg, text=label_text, style="SubHeader.TLabel", wraplength=900).pack(
        anchor="w", padx=16, pady=(0, 12)
    )

    if previous is None:
        ttk.Label(
            dlg,
            text="No prior snapshots found — load a previous session "
                 "or run an export first to populate sessions/.",
            style="Info.TLabel",
            wraplength=900,
        ).pack(anchor="w", padx=16, pady=(0, 12))
        ttk.Button(dlg, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=16, pady=12)
        if hasattr(app, "_autosize_dialog"):
            app._autosize_dialog(dlg, min_w=620, min_h=220, max_w_ratio=0.6, max_h_ratio=0.4)
        dlg.wait_window()
        return

    notebook = ttk.Notebook(dlg)
    notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

    for bucket_key, label, columns in _TAB_DEFS:
        rows = diff.get(bucket_key, []) or []
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=f"{label} ({len(rows)})")

        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            heading, width, anchor = _HEADINGS[col]
            tree.heading(col, text=heading)
            tree.column(col, width=width, anchor=anchor, stretch=(col == "description"))
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        for row in rows:
            values = []
            for col in columns:
                if col == "lc":
                    values.append(row.get("line_code", ""))
                elif col == "delta":
                    delta = row.get("delta", 0)
                    values.append(("+" if delta > 0 else "") + str(delta))
                else:
                    values.append(row.get(col, ""))
            tree.insert("", "end", values=values)

        if not rows:
            ttk.Label(frame, text=f"No {label.lower()} items.", style="Info.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w", padx=8, pady=8
            )

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Close", style="Big.TButton", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    if hasattr(app, "_autosize_dialog"):
        app._autosize_dialog(dlg, min_w=900, min_h=520, max_w_ratio=0.9, max_h_ratio=0.85)
    dlg.wait_window()
