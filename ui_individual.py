import tkinter as tk
from tkinter import ttk

import reorder_flow


def vendor_history_suggestions(app, key):
    recent_list = list((getattr(app, "recent_orders", {}) or {}).get(key, []) or [])
    ranked = {}
    for row in recent_list:
        vendor = str(row.get("vendor", "") or "").strip().upper()
        if not vendor:
            continue
        entry = ranked.setdefault(vendor, {"qty": 0.0, "date": ""})
        try:
            entry["qty"] += float(row.get("qty", 0) or 0)
        except (TypeError, ValueError):
            pass
        date_text = str(row.get("date", "") or "").strip()
        if date_text > entry["date"]:
            entry["date"] = date_text
    ordered = sorted(
        ranked.items(),
        key=lambda item: (-item[1]["qty"], item[1]["date"], item[0]),
    )
    return [vendor for vendor, _meta in ordered]


def receipt_vendor_suggestions(app, key):
    return reorder_flow.receipt_vendor_candidates(app, key)


def receipt_vendor_hint(app, key):
    evidence = reorder_flow.receipt_vendor_evidence(app, key)
    vendors = evidence["vendor_candidates"]
    if not vendors:
        return ""
    if evidence["vendor_confidence"] == "high" and evidence["primary_vendor"]:
        if evidence.get("vendor_confidence_reason") == "dominant_recent_vendor":
            return (
                f"Receipt vendor history strongly favors {evidence['primary_vendor']} "
                f"({evidence['primary_vendor_qty_share']:.0%} of received qty)."
            )
        return f"Receipt vendor history consistently points to {evidence['primary_vendor']}."
    if evidence["primary_vendor"]:
        return f"Receipt vendor history is mixed; top vendor {evidence['primary_vendor']}. Other candidates: {', '.join(vendors[1:3])}" if len(vendors) > 1 else ""
    return f"Receipt vendor history: {', '.join(vendors[:3])}"


def suggested_vendor_for_item(app, item, inventory):
    current_vendor = str(item.get("vendor", "") or "").strip().upper()
    if current_vendor:
        return current_vendor, "current assignment"
    key = (item.get("line_code", ""), item.get("item_code", ""))
    receipt_evidence = reorder_flow.receipt_vendor_evidence(app, key)
    if receipt_evidence["primary_vendor"] and receipt_evidence["vendor_confidence"] == "high":
        return receipt_evidence["primary_vendor"], "receipt history"
    if receipt_evidence["vendor_candidates"]:
        return "", ""
    supplier = str(inventory.get("supplier", "") or "").strip().upper()
    if supplier:
        return supplier, "report supplier"
    history_vendors = vendor_history_suggestions(app, key)
    if len(history_vendors) == 1:
        return history_vendors[0], "recent local order history"
    return "", ""


def prioritized_vendor_choices(app, item, inventory):
    ordered = []

    def _add(vendor):
        normalized = str(vendor or "").strip().upper()
        if normalized and normalized not in ordered:
            ordered.append(normalized)

    suggested_vendor, _source = suggested_vendor_for_item(app, item, inventory)
    _add(suggested_vendor)

    key = (item.get("line_code", ""), item.get("item_code", ""))
    for vendor in receipt_vendor_suggestions(app, key):
        _add(vendor)

    supplier = str(inventory.get("supplier", "") or "").strip().upper()
    _add(supplier)

    for vendor in vendor_history_suggestions(app, key):
        _add(vendor)

    for vendor in getattr(app, "vendor_codes_used", []) or []:
        _add(vendor)

    return ordered


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
    app.lbl_assign_data_source = ttk.Label(frame, text="", style="Info.TLabel")
    app.lbl_assign_data_source.pack(anchor="w", pady=(0, 8))
    app._refresh_data_folder_labels()

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
        "Dtl Sug Min:",
        "Dtl Sug Max:",
        "Sug Compare:",
        "YTD Sales:",
        "12 Mo Sales:",
        "Supplier:",
        "Receipt Vendor:",
        "Receipt Confidence:",
        "Demand Shape:",
        "Shape Confidence:",
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
    app.lbl_vendor_suggestion = ttk.Label(vendor_frame, text="", style="Info.TLabel", wraplength=700)
    app.lbl_vendor_suggestion.pack(anchor="w", pady=(0, 4))
    vendor_button_row = ttk.Frame(vendor_frame)
    vendor_button_row.pack(anchor="w", pady=(2, 0))
    ttk.Button(vendor_button_row, text="Manage Vendors...", command=app._open_vendor_manager).pack(side=tk.LEFT)

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill=tk.X, pady=12)

    nav_row = ttk.Frame(btn_frame)
    nav_row.pack(anchor="w", fill=tk.X)
    ttk.Button(nav_row, text="<- Back", command=app._assign_back).pack(side=tk.LEFT, padx=4)
    ttk.Button(nav_row, text="Skip Item", command=app._assign_skip).pack(side=tk.LEFT, padx=4)
    ttk.Button(nav_row, text="Assign & Next ->", style="Big.TButton", command=app._assign_current).pack(
        side=tk.LEFT, padx=8
    )

    finish_row = ttk.Frame(btn_frame)
    finish_row.pack(anchor="e", fill=tk.X, pady=(8, 0))
    ttk.Button(finish_row, text="Finish - Go to Review ->", style="Big.TButton", command=app._finish_assign).pack(
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
        app.assign_detail_vars["Dtl Sug Min:"].set(str(item.get("detailed_suggested_min")) if item.get("detailed_suggested_min") is not None else "-")
        app.assign_detail_vars["Dtl Sug Max:"].set(str(item.get("detailed_suggested_max")) if item.get("detailed_suggested_max") is not None else "-")
        app.assign_detail_vars["Sug Compare:"].set(item.get("detailed_suggestion_compare_label", "") or "-")
        app.assign_detail_vars["YTD Sales:"].set(str(inventory.get("ytd_sales", 0)) or "-")
        app.assign_detail_vars["12 Mo Sales:"].set(str(inventory.get("mo12_sales", 0)) or "-")
        app.assign_detail_vars["Supplier:"].set(inventory.get("supplier", "") or "-")
        receipt_vendor = item.get("receipt_primary_vendor", "") or "-"
        receipt_confidence = item.get("receipt_vendor_confidence", "") or "-"
        app.assign_detail_vars["Receipt Vendor:"].set(receipt_vendor)
        app.assign_detail_vars["Receipt Confidence:"].set(receipt_confidence)
        app.assign_detail_vars["Demand Shape:"].set(item.get("detailed_sales_shape", "") or "-")
        app.assign_detail_vars["Shape Confidence:"].set(item.get("detailed_sales_shape_confidence", "") or "-")
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
            "Dtl Sug Min:",
            "Dtl Sug Max:",
            "Sug Compare:",
            "YTD Sales:",
            "12 Mo Sales:",
            "Supplier:",
            "Receipt Vendor:",
            "Receipt Confidence:",
            "Demand Shape:",
            "Shape Confidence:",
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

    vendor_choices = prioritized_vendor_choices(app, item, inventory)
    app.combo_vendor["values"] = vendor_choices
    suggested_vendor, suggestion_source = suggested_vendor_for_item(app, item, inventory)
    if suggested_vendor:
        app.var_vendor_input.set(suggested_vendor)
        app.lbl_vendor_suggestion.config(text=f"Auto-filled vendor from {suggestion_source}: {suggested_vendor}")
    else:
        receipt_hint = receipt_vendor_hint(app, key)
        if receipt_hint:
            app.lbl_vendor_suggestion.config(text=receipt_hint)
        else:
            history_vendors = vendor_history_suggestions(app, key)
            if history_vendors:
                app.lbl_vendor_suggestion.config(text=f"Recent vendor history: {', '.join(history_vendors[:3])}")
            else:
                app.lbl_vendor_suggestion.config(text="")
        app.var_vendor_input.set("")
    app.combo_vendor.focus_set()
