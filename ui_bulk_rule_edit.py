"""Bulk Buy Rule Edit dialog.

open_bulk_rule_edit(app, keys) opens a dialog that applies a partial rule
change to every item in *keys* at once.  Only filled-in fields are written;
blank fields leave the existing rule value for each item untouched.
"""
import tkinter as tk
from tkinter import ttk, messagebox

import bulk_rule_flow


_POLICY_OPTIONS = [
    "",
    "standard",
    "pack_trigger",
    "soft_pack",
    "exact_qty",
    "reel_review",
    "reel_auto",
    "large_pack_review",
    "manual_only",
]

_BG = "#1e1e2e"


def open_bulk_rule_edit(app, keys):
    """Open the Bulk Rule Edit dialog for the given item *keys*.

    *keys* is a collection of 'LINE_CODE:ITEM_CODE' strings.
    """
    keys = list(keys)
    if not keys:
        return

    dlg = tk.Toplevel(app.root)
    dlg.title(f"Edit Rule — {len(keys)} item{'s' if len(keys) != 1 else ''}")
    dlg.configure(bg=_BG)
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text="Edit Buy Rule — Multiple Items", style="Header.TLabel").pack(
        anchor="w", padx=16, pady=(16, 2)
    )
    ttk.Label(
        dlg,
        text=(
            f"Applies to {len(keys)} selected item{'s' if len(keys) != 1 else ''}. "
            "Leave a field blank to leave each item's existing value unchanged."
        ),
        style="SubHeader.TLabel",
        wraplength=480,
    ).pack(anchor="w", padx=16, pady=(0, 10))

    form = ttk.LabelFrame(dlg, text="Fields to Apply", padding=12)
    form.pack(fill=tk.X, padx=16, pady=4)
    form.columnconfigure(1, weight=1)

    # Order Policy
    ttk.Label(form, text="Order Policy:").grid(row=0, column=0, sticky="w", pady=6)
    var_policy = tk.StringVar(value="")
    ttk.Combobox(
        form, textvariable=var_policy, state="readonly",
        values=_POLICY_OPTIONS, width=20,
    ).grid(row=0, column=1, sticky="w", padx=8, pady=6)
    ttk.Label(form, text="(blank = don't change)", style="SubHeader.TLabel").grid(
        row=0, column=2, sticky="w"
    )

    # Pack Qty
    ttk.Label(form, text="Pack Qty:").grid(row=1, column=0, sticky="w", pady=6)
    var_pack = tk.StringVar()
    ttk.Entry(form, textvariable=var_pack, width=10).grid(
        row=1, column=1, sticky="w", padx=8, pady=6
    )

    # Min Order Qty
    ttk.Label(form, text="Min Order Qty:").grid(row=2, column=0, sticky="w", pady=6)
    var_min = tk.StringVar()
    ttk.Entry(form, textvariable=var_min, width=10).grid(
        row=2, column=1, sticky="w", padx=8, pady=6
    )

    # Cover Days
    ttk.Label(form, text="Cover Days:").grid(row=3, column=0, sticky="w", pady=6)
    var_cover = tk.StringVar()
    ttk.Entry(form, textvariable=var_cover, width=10).grid(
        row=3, column=1, sticky="w", padx=8, pady=6
    )

    def _apply():
        changes = {
            "order_policy": var_policy.get(),
            "pack_size": var_pack.get().strip(),
            "min_order_qty": var_min.get().strip(),
            "cover_days": var_cover.get().strip(),
        }
        modified = bulk_rule_flow.apply_bulk_rule_edit(app, keys, changes)
        if modified == 0:
            messagebox.showinfo(
                "No Changes",
                "No fields were filled in, or all values were invalid.\n"
                "Enter at least one value to apply.",
                parent=dlg,
            )
            return
        # Refresh suggestions and bulk grid for all affected items
        _refresh_after_bulk_rule_edit(app, keys)
        dlg.destroy()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn_frame, text="Apply to All Selected", style="Big.TButton", command=_apply).pack(
        side=tk.RIGHT, padx=4
    )

    dlg.update_idletasks()
    dlg.minsize(440, dlg.winfo_reqheight())
    dlg.wait_window()


def _refresh_after_bulk_rule_edit(app, keys):
    """Re-enrich affected items and refresh the bulk grid."""
    from rules import enrich_item, get_rule_pack_size, has_exact_qty_override

    key_set = set(keys)
    for item in getattr(app, "filtered_items", []):
        rule_key = f"{item.get('line_code', '')}:{item.get('item_code', '')}"
        if rule_key not in key_set:
            continue
        rule = app.order_rules.get(rule_key) or {}
        rule_pack = get_rule_pack_size(rule)
        if has_exact_qty_override(rule):
            item["pack_size"] = 0
            item["pack_size_source"] = "rule"
            item["exact_qty_override"] = True
        elif rule_pack is not None:
            item["pack_size"] = rule_pack
            item["pack_size_source"] = "rule"
            item["exact_qty_override"] = False
        inv = getattr(app, "inventory_lookup", {}).get(
            (item.get("line_code"), item.get("item_code")), {}
        )
        enrich_item(item, inv, item.get("pack_size"), rule)
        if getattr(app, "bulk_sheet", None):
            try:
                app.bulk_sheet.refresh_row(
                    __import__("ui_bulk").bulk_row_id(item),
                    app._bulk_row_values(item),
                )
            except Exception:
                pass

    if hasattr(app, "_apply_bulk_filter"):
        app._apply_bulk_filter()
    if hasattr(app, "_update_bulk_summary"):
        app._update_bulk_summary()
