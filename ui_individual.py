import tkinter as tk
from tkinter import ttk


def build_individual_tab(app):
    app.individual_items = []
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  5. Individual  ")

    ttk.Label(frame, text="Assign Remaining Items", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text="Step through unassigned items one by one. Press Enter or click Assign to move to the next item.",
        style="SubHeader.TLabel",
        wraplength=800,
    ).pack(anchor="w", pady=(2, 12))

    app.lbl_assign_progress = ttk.Label(frame, text="Item 0 / 0", style="Info.TLabel")
    app.lbl_assign_progress.pack(anchor="w")

    app.assign_progress = ttk.Progressbar(frame, mode="determinate")
    app.assign_progress.pack(fill=tk.X, pady=(4, 12))

    card = ttk.LabelFrame(frame, text="Current Item", padding=12)
    card.pack(fill=tk.X, pady=4)

    columns_frame = ttk.Frame(card)
    columns_frame.pack(fill=tk.X)

    left = ttk.Frame(columns_frame)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    left_labels = [
        "Line Code:",
        "Item Code:",
        "Description:",
        "Source:",
        "Qty Sold:",
        "Qty Suspended:",
        "Qty Received:",
        "Order Qty:",
        "Pack Size:",
    ]
    app.assign_detail_vars = {}
    for i, label in enumerate(left_labels):
        ttk.Label(left, text=label, font=("Segoe UI", 10, "bold")).grid(
            row=i, column=0, sticky="w", padx=(0, 12), pady=2
        )
        var = tk.StringVar()
        ttk.Label(left, textvariable=var, font=("Segoe UI", 10)).grid(row=i, column=1, sticky="w", pady=2)
        app.assign_detail_vars[label] = var

    right = ttk.LabelFrame(columns_frame, text="Inventory", padding=8)
    right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(16, 0))

    inv_labels = [
        "QOH:",
        "On PO:",
        "Min:",
        "Max:",
        "Sug Min:",
        "Sug Max:",
        "YTD Sales:",
        "12 Mo Sales:",
        "Supplier:",
        "Last Receipt:",
        "Last Sale:",
    ]
    for i, label in enumerate(inv_labels):
        ttk.Label(right, text=label, font=("Segoe UI", 9, "bold")).grid(
            row=i, column=0, sticky="w", padx=(0, 8), pady=1
        )
        var = tk.StringVar(value="-")
        ttk.Label(right, textvariable=var, font=("Segoe UI", 9)).grid(row=i, column=1, sticky="w", pady=1)
        app.assign_detail_vars[label] = var

    app.lbl_po_warning = ttk.Label(card, text="", style="Warning.TLabel", wraplength=700)
    app.lbl_po_warning.pack(anchor="w", pady=(8, 0))

    app.lbl_susp_warning = ttk.Label(card, text="", style="Warning.TLabel", wraplength=700)
    app.lbl_susp_warning.pack(anchor="w", pady=(2, 0))

    dup_frame = ttk.Frame(card)
    dup_frame.pack(anchor="w", fill=tk.X, pady=(2, 0))
    app.lbl_dup_warning = ttk.Label(dup_frame, text="", style="Info.TLabel", wraplength=600)
    app.lbl_dup_warning.pack(side=tk.LEFT)
    app.btn_dismiss_dup = ttk.Button(dup_frame, text="Dismiss", command=app._dismiss_dup_from_individual)

    app.lbl_recent_warning = ttk.Label(card, text="", style="Warning.TLabel", wraplength=700)
    app.lbl_recent_warning.pack(anchor="w", pady=(2, 0))

    vendor_frame = ttk.LabelFrame(frame, text="Vendor Code", padding=12)
    vendor_frame.pack(fill=tk.X, pady=(12, 4))

    ttk.Label(vendor_frame, text="Enter vendor code (type to filter):").pack(anchor="w")
    app.var_vendor_input = tk.StringVar()
    app.combo_vendor = ttk.Combobox(
        vendor_frame, textvariable=app.var_vendor_input, font=("Segoe UI", 11), width=30
    )
    app.combo_vendor.pack(anchor="w", pady=4)
    app.combo_vendor.bind("<Return>", lambda e: app._assign_current())
    app.combo_vendor.bind("<KeyRelease>", app._vendor_autocomplete)

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill=tk.X, pady=12)

    ttk.Button(btn_frame, text="<- Back", command=app._assign_back).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Skip Item", command=app._assign_skip).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Assign & Next ->", style="Big.TButton", command=app._assign_current).pack(
        side=tk.LEFT, padx=8
    )
    ttk.Button(btn_frame, text="Finish - Go to Review ->", style="Big.TButton", command=app._finish_assign).pack(
        side=tk.RIGHT, padx=4
    )


def populate_assign_item(app):
    if app.assign_index >= len(app.individual_items):
        app._finish_assign()
        return

    item = app.individual_items[app.assign_index]
    total = len(app.individual_items)

    app.lbl_assign_progress.config(text=f"Item {app.assign_index + 1} of {total}")
    app.assign_progress["maximum"] = total
    app.assign_progress["value"] = app.assign_index

    app.assign_detail_vars["Line Code:"].set(item["line_code"])
    app.assign_detail_vars["Item Code:"].set(item["item_code"])
    app.assign_detail_vars["Description:"].set(item["description"])
    has_sales = item.get("qty_sold", 0) > 0
    has_susp = item.get("qty_suspended", 0) > 0
    source = "Both" if (has_sales and has_susp) else ("Suspense" if has_susp else "Sales")
    app.assign_detail_vars["Source:"].set(source)
    app.assign_detail_vars["Qty Sold:"].set(str(item["qty_sold"]))
    app.assign_detail_vars["Qty Suspended:"].set(str(item.get("qty_suspended", 0)))
    app.assign_detail_vars["Qty Received:"].set(str(item["qty_received"]))
    app.assign_detail_vars["Order Qty:"].set(str(item.get("order_qty", item["qty_sold"])))
    pack_size = item.get("pack_size")
    app.assign_detail_vars["Pack Size:"].set(str(pack_size) if pack_size else "-")

    key = (item["line_code"], item["item_code"])
    inventory = app.inventory_lookup.get(key, {})
    if inventory:
        qoh = inventory.get("qoh", 0)
        app.assign_detail_vars["QOH:"].set(f"{qoh:g}")
        on_po = app.on_po_qty.get(key, 0)
        app.assign_detail_vars["On PO:"].set(f"{on_po:g}" if on_po else "-")
        minimum = inventory.get("min")
        maximum = inventory.get("max")
        app.assign_detail_vars["Min:"].set(str(minimum) if minimum is not None else "-")
        app.assign_detail_vars["Max:"].set(str(maximum) if maximum is not None else "-")
        sug_min, sug_max = app._suggest_min_max(key)
        app.assign_detail_vars["Sug Min:"].set(str(sug_min) if sug_min is not None else "-")
        app.assign_detail_vars["Sug Max:"].set(str(sug_max) if sug_max is not None else "-")
        app.assign_detail_vars["YTD Sales:"].set(str(inventory.get("ytd_sales", 0)) or "-")
        app.assign_detail_vars["12 Mo Sales:"].set(str(inventory.get("mo12_sales", 0)) or "-")
        app.assign_detail_vars["Supplier:"].set(inventory.get("supplier", "") or "-")
        app.assign_detail_vars["Last Receipt:"].set(inventory.get("last_receipt", "") or "-")
        app.assign_detail_vars["Last Sale:"].set(inventory.get("last_sale", "") or "-")
    else:
        for label in (
            "QOH:",
            "On PO:",
            "Min:",
            "Max:",
            "Sug Min:",
            "Sug Max:",
            "YTD Sales:",
            "12 Mo Sales:",
            "Supplier:",
            "Last Receipt:",
            "Last Sale:",
        ):
            app.assign_detail_vars[label].set("-")

    po_matches = app.open_po_lookup.get(key, [])
    if po_matches:
        lines = [
            f"Already on a {po['po_type']} - Qty: {po['qty']:.0f}, Issued: {po['date_issued']}"
            for po in po_matches
        ]
        app.lbl_po_warning.config(text="\n".join(lines))
    else:
        app.lbl_po_warning.config(text="")

    susp_matches = app.suspended_lookup.get(key, [])
    if susp_matches:
        lines = []
        for suspended_item in susp_matches:
            parts = ["SUSPENDED"]
            if suspended_item.get("customer"):
                parts.append(f"for {suspended_item['customer']}")
            if suspended_item.get("qty_ordered"):
                parts.append(f"- Qty: {suspended_item['qty_ordered']}")
            if suspended_item.get("date"):
                parts.append(f"({suspended_item['date']})")
            lines.append(" ".join(parts))
        app.lbl_susp_warning.config(text="\n".join(lines))
    elif key in app.suspended_set:
        app.lbl_susp_warning.config(text="This item is on the suspended list.")
    else:
        app.lbl_susp_warning.config(text="")

    other_line_codes = app.duplicate_ic_lookup.get(item["item_code"], set())
    others = sorted(line_code for line_code in other_line_codes if line_code != item["line_code"])
    if others:
        other_details = []
        for line_code in others:
            other_inventory = app.inventory_lookup.get((line_code, item["item_code"]), {})
            other_qoh = other_inventory.get("qoh", 0)
            other_details.append(f"{line_code} (QOH: {other_qoh:g})")
        app.lbl_dup_warning.config(text=f"Also exists under: {', '.join(other_details)}", foreground="#f0c060")
        app.btn_dismiss_dup.pack(side=tk.LEFT, padx=(8, 0))
    else:
        app.lbl_dup_warning.config(text="")
        app.btn_dismiss_dup.pack_forget()

    recent_list = app.recent_orders.get(key, [])
    if recent_list:
        total_recent = sum(row["qty"] for row in recent_list)
        entries = [f"{row['qty']} via {row['vendor']} on {row['date']}" for row in recent_list]
        app.lbl_recent_warning.config(text=f"Recently ordered {total_recent} total: " + "; ".join(entries))
    else:
        app.lbl_recent_warning.config(text="")

    app.combo_vendor["values"] = app.vendor_codes_used
    app.var_vendor_input.set("")
    app.combo_vendor.focus_set()
