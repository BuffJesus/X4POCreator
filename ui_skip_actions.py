"""'Skip Cleanup' dialog — bulk tooling for the items the v0.5.4 →
v0.6.5 fixes made visible in the Skip filter.

Pure helpers live in skip_actions_flow.  This module wires them into
a single dialog opened from the bulk tab toolbar.  The dialog
operates on the items currently in `app.filtered_items` that match
the skip predicate, regardless of which Item Status filter is
active — the operator can pre-narrow with the bulk grid filters or
ignore them and act on every skip item in the session.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import skip_actions_flow


def open_skip_actions_dialog(app):
    items = list(getattr(app, "filtered_items", []) or [])
    skip_items = skip_actions_flow.filter_skip_items(items)
    clusters = skip_actions_flow.count_skip_clusters_by_line_code(items)

    dlg = tk.Toplevel(app.root)
    dlg.title("Skip Cleanup Tools")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    header = (
        f"{len(skip_items)} skip item(s) across {len(clusters)} line code(s)."
        if skip_items
        else "No skip items in the current session."
    )
    ttk.Label(dlg, text=header, style="Header.TLabel", wraplength=900).pack(
        anchor="w", padx=16, pady=(16, 4)
    )
    ttk.Label(
        dlg,
        text=(
            "Select one or more line codes below to scope every action.  "
            "Leaving the selection empty applies the action to every skip "
            "item in the session.  All actions can be undone via the "
            "existing Ignore List Manager / Order Rules CSV."
        ),
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(0, 8))

    if not skip_items:
        ttk.Button(dlg, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=16, pady=12)
        if hasattr(app, "_autosize_dialog"):
            app._autosize_dialog(dlg, min_w=620, min_h=200, max_w_ratio=0.6, max_h_ratio=0.4)
        dlg.wait_window()
        return

    container = ttk.Frame(dlg)
    container.pack(fill=tk.BOTH, expand=True, padx=16)

    columns = ("lc", "count")
    tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="extended")
    tree.heading("lc",    text="Line Code")
    tree.heading("count", text="Skip Items")
    tree.column("lc",    width=160, anchor="w")
    tree.column("count", width=120, anchor="e")
    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)

    for cluster in clusters:
        tree.insert(
            "", "end",
            iid=cluster["line_code"],
            values=(cluster["line_code"] or "(blank)", cluster["count"]),
        )

    def _scoped_items() -> list:
        selected_codes = set(tree.selection())
        if not selected_codes:
            return list(skip_items)
        return [
            item for item in skip_items
            if str(item.get("line_code", "") or "") in selected_codes
        ]

    def _scope_label(scope_items) -> str:
        if not tree.selection():
            return f"all {len(scope_items)} skip item(s)"
        return f"{len(scope_items)} skip item(s) across {len(tree.selection())} line code(s)"

    def _ignore():
        scope = _scoped_items()
        if not scope:
            messagebox.showinfo("Nothing to Apply", "No skip items in the selected scope.", parent=dlg)
            return
        if not messagebox.askyesno(
            "Add to Ignore List",
            f"Add {_scope_label(scope)} to the persistent ignore list?\n\n"
            "These items will be skipped on future loads until removed via "
            "Manage Ignored Items.",
            parent=dlg,
        ):
            return
        keys = skip_actions_flow.collect_ignore_keys(scope)
        if not keys:
            messagebox.showinfo("Nothing to Apply", "No usable item codes in the selected scope.", parent=dlg)
            return
        added = app._ignore_items_by_keys(set(keys))
        messagebox.showinfo("Ignored", f"Added {added} item(s) to the ignore list.", parent=dlg)
        dlg.destroy()

    def _flag_discontinue():
        scope = _scoped_items()
        if not scope:
            messagebox.showinfo("Nothing to Apply", "No skip items in the selected scope.", parent=dlg)
            return
        if not messagebox.askyesno(
            "Flag for Discontinue Review",
            f"Flag {_scope_label(scope)} as discontinue candidates?\n\n"
            "This sets `discontinue_candidate = True` in order_rules.json "
            "for each item.  Items remain orderable until you formally "
            "discontinue them — this is a review marker only.",
            parent=dlg,
        ):
            return
        flagged = 0
        for lc, ic in skip_actions_flow.collect_keys_for_action(scope):
            rule_key = f"{lc}:{ic}"
            rule = app.order_rules.setdefault(rule_key, {})
            if not rule.get("discontinue_candidate"):
                rule["discontinue_candidate"] = True
                flagged += 1
        save_fn = getattr(app, "_save_order_rules", None)
        if callable(save_fn):
            save_fn()
        messagebox.showinfo(
            "Flagged",
            f"Flagged {flagged} item(s) as discontinue candidates.",
            parent=dlg,
        )

    def _export_csv():
        scope = _scoped_items()
        if not scope:
            messagebox.showinfo("Nothing to Export", "No skip items in the selected scope.", parent=dlg)
            return
        rows = skip_actions_flow.build_skip_export_rows(
            scope,
            getattr(app, "inventory_lookup", None) or {},
        )
        if not rows:
            messagebox.showinfo("Nothing to Export", "No usable rows to export.", parent=dlg)
            return
        default_name = "skip_review.csv"
        path = filedialog.asksaveasfilename(
            parent=dlg,
            title="Export Skip List",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            csv_text = skip_actions_flow.render_skip_csv(rows)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(csv_text)
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not write {path}:\n{exc}", parent=dlg)
            return
        messagebox.showinfo(
            "Exported",
            f"Wrote {len(rows)} skip row(s) to:\n{os.path.abspath(path)}",
            parent=dlg,
        )

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Export CSV", command=_export_csv).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn_frame, text="Flag Discontinue", command=_flag_discontinue).pack(side=tk.RIGHT, padx=4)
    ttk.Button(
        btn_frame, text="Add to Ignore List",
        style="Big.TButton", command=_ignore,
    ).pack(side=tk.RIGHT, padx=4)

    if hasattr(app, "_autosize_dialog"):
        app._autosize_dialog(dlg, min_w=720, min_h=520, max_w_ratio=0.7, max_h_ratio=0.85)
    dlg.wait_window()
