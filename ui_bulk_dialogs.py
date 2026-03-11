import copy
import math
import tkinter as tk
from tkinter import ttk, messagebox

import storage
from rules import enrich_item, evaluate_item_status, get_rule_pack_size, infer_default_order_policy
from ui_scroll import attach_vertical_mousewheel


def not_needed_reason(app, item, max_exceed_abs_buffer):
    reasons = []
    auto_remove = False
    key = (item["line_code"], item["item_code"])
    inv = app.inventory_lookup.get(key, {})
    qoh = inv.get("qoh", 0)
    mx = inv.get("max")
    ps = item.get("pack_size")
    po_qty = item.get("qty_on_po", app.on_po_qty.get(key, 0))
    final_qty = item.get("final_qty", item.get("order_qty", 0))
    suggested_qty = item.get("suggested_qty", final_qty)
    gross_need = item.get("gross_need", item.get("raw_need", final_qty))
    inventory_position = item.get("inventory_position", qoh + po_qty)
    target_stock = item.get("target_stock")
    demand_signal = item.get("demand_signal", gross_need)
    effective_susp = item.get("effective_qty_suspended", item.get("qty_suspended", 0))
    effective_sales = item.get("effective_qty_sold", item.get("qty_sold", 0))

    if item.get("status") == "skip" or final_qty <= 0:
        reasons.append("No net need (skip/zero final qty)")
        auto_remove = True

    if target_stock is None:
        _, sug_max = app._suggest_min_max(key)
        target_candidates = [
            value for value in (mx, sug_max) if isinstance(value, (int, float)) and value > 0
        ]
        target_stock = max(target_candidates) if target_candidates else 0
    else:
        _, sug_max = app._suggest_min_max(key)

    if target_stock and inventory_position >= target_stock and final_qty > 0:
        reasons.append(
            f"Inventory position already meets target (pos {inventory_position:g} >= target {target_stock:g})"
        )
        auto_remove = True

    if demand_signal <= 0 and inventory_position > 0 and final_qty > 0:
        reasons.append(f"No uncovered demand signal (sales {effective_sales:g}, susp {effective_susp:g})")
        auto_remove = True

    if ps and qoh >= gross_need and gross_need > 0:
        reasons.append(f"QOH covers demand signal (QOH {qoh:g} >= need {gross_need:g})")
        auto_remove = True

    resulting_stock = inventory_position + final_qty

    hard_max = mx if isinstance(mx, (int, float)) and mx > 0 else None
    soft_candidates = [
        value for value in (target_stock, hard_max, sug_max) if isinstance(value, (int, float)) and value > 0
    ]
    soft_max = max(soft_candidates) if soft_candidates else None

    pack_margin = math.ceil(ps * 0.5) if isinstance(ps, (int, float)) and ps > 0 else 0

    def _margin(max_ref):
        return max(max_exceed_abs_buffer, math.ceil(max_ref * 0.25), pack_margin)

    hard_excess = False
    soft_excess = False
    if hard_max is not None:
        hard_threshold = hard_max + _margin(hard_max)
        hard_excess = resulting_stock > hard_threshold
    else:
        hard_threshold = None

    if soft_max is not None:
        soft_threshold = soft_max + _margin(soft_max)
        soft_excess = resulting_stock > soft_threshold
    else:
        soft_threshold = None

    if soft_excess:
        reasons.append(
            f"Strong target exceed (stock {resulting_stock:g} > soft limit {soft_threshold:g}; "
            f"target {target_stock if target_stock is not None else '-'}, "
            f"cur max {hard_max if hard_max is not None else '-'}, sug max {sug_max if sug_max is not None else '-'})"
        )
        auto_remove = True
    elif hard_excess:
        reasons.append(
            f"Review: exceeds current max (stock {resulting_stock:g} > hard limit {hard_threshold:g}; "
            f"cur max {hard_max:g}, sug max {sug_max if sug_max is not None else '-'})"
        )

    if isinstance(suggested_qty, (int, float)) and suggested_qty >= 0 and final_qty > 0:
        if isinstance(ps, (int, float)) and ps > 0:
            qty_tolerance = ps
        else:
            qty_tolerance = max(1, math.ceil(suggested_qty * 0.5))
        if final_qty > (suggested_qty + qty_tolerance):
            if hard_excess or soft_excess:
                reasons.append(
                    f"Final qty far above suggestion ({final_qty:g} vs suggested {suggested_qty:g}, tol {qty_tolerance:g})"
                )
                auto_remove = auto_remove or soft_excess
            else:
                reasons.append(
                    f"Review: final qty above suggestion ({final_qty:g} vs suggested {suggested_qty:g}, tol {qty_tolerance:g})"
                )

    if target_stock and final_qty > 0 and resulting_stock > target_stock and suggested_qty <= 0:
        reasons.append(
            f"Review: order pushes stock above target despite zero suggestion (stock {resulting_stock:g} vs target {target_stock:g})"
        )

    return "; ".join(reasons), auto_remove


def bulk_remove_not_needed(app, scope, max_exceed_abs_buffer):
    if scope == "screen":
        row_ids = list(app.bulk_sheet.visible_row_ids()) if getattr(app, "bulk_sheet", None) else [
            iid for iid in app.bulk_tree.get_children() if app.bulk_tree.bbox(iid)
        ]
        scope_label = "on-screen"
    else:
        row_ids = list(app.bulk_sheet.visible_row_ids()) if getattr(app, "bulk_sheet", None) else list(app.bulk_tree.get_children())
        scope_label = "filtered"

    if not row_ids:
        messagebox.showinfo("No Items", f"No {scope_label} rows to review.")
        return

    include_assigned = messagebox.askyesno(
        "Include Assigned?",
        "Include vendor-assigned items in this removal review?\n\n"
        "Yes = include assigned and unassigned\n"
        "No = unassigned only (safer default)"
    )

    candidates = []
    for iid in row_ids:
        idx = int(iid)
        if idx >= len(app.filtered_items):
            continue
        item = app.filtered_items[idx]
        if not include_assigned and item.get("vendor"):
            continue
        reason, auto_remove = not_needed_reason(app, item, max_exceed_abs_buffer)
        if reason:
            candidates.append((idx, item, reason, auto_remove))

    if not candidates:
        messagebox.showinfo("Nothing to Remove", f"No {scope_label} items were flagged as not needed.")
        return

    dlg = tk.Toplevel(app.root)
    dlg.title("Remove Not Needed Items")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(
        dlg,
        text=f"{len(candidates)} {scope_label} item(s) are flagged as likely not needed.",
        style="Header.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text="Uncheck any item you want to keep. Checked items will be removed from this session.",
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(0, 12))

    container = ttk.Frame(dlg)
    container.pack(fill=tk.BOTH, expand=True, padx=16)

    canvas = tk.Canvas(container, highlightthickness=0, bg="#1e1e2e")
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    headers = ["Remove", "LC", "Item Code", "Description", "Final Qty", "QOH", "Max", "Sug Max", "Why This Qty"]
    widths = [7, 6, 14, 24, 7, 7, 6, 8, 18]
    for c, (hdr, width) in enumerate(zip(headers, widths)):
        ttk.Label(inner, text=hdr, width=width, font=("Segoe UI", 9, "bold"), foreground="#c9a0dc").grid(
            row=0, column=c, sticky="w", padx=2, pady=4
        )
    inner.grid_columnconfigure(8, weight=1)

    checks = []
    for r, (idx, item, reason, auto_remove) in enumerate(candidates, 1):
        key = (item["line_code"], item["item_code"])
        inv = app.inventory_lookup.get(key, {})
        qoh = inv.get("qoh", 0)
        cur_max = inv.get("max")
        _, sug_max = app._suggest_min_max(key)
        final_qty = item.get("final_qty", item.get("order_qty", 0))

        var = tk.BooleanVar(value=auto_remove)
        checks.append((var, idx))
        ttk.Checkbutton(inner, variable=var).grid(row=r, column=0, sticky="w", padx=2, pady=1)
        ttk.Label(inner, text=item["line_code"], width=6).grid(row=r, column=1, sticky="w", padx=2)
        ttk.Label(inner, text=item["item_code"], width=14).grid(row=r, column=2, sticky="w", padx=2)
        ttk.Label(
            inner,
            text=item.get("description", "")[:64],
            width=24,
            wraplength=240,
            justify="left",
        ).grid(row=r, column=3, sticky="w", padx=2)
        ttk.Label(inner, text=str(final_qty), width=7).grid(row=r, column=4, sticky="w", padx=2)
        ttk.Label(inner, text=f"{qoh:g}", width=7).grid(row=r, column=5, sticky="w", padx=2)
        ttk.Label(inner, text=str(cur_max) if cur_max is not None else "", width=6).grid(row=r, column=6, sticky="w", padx=2)
        ttk.Label(inner, text=str(sug_max) if sug_max is not None else "", width=8).grid(row=r, column=7, sticky="w", padx=2)
        ttk.Label(inner, text=reason, foreground="#f0c060", wraplength=560, justify="left").grid(
            row=r, column=8, sticky="ew", padx=2
        )

    result = {"removed": 0}
    footer = ttk.Frame(dlg)
    footer.pack(fill=tk.X, padx=16, pady=(4, 0))
    lbl_selected = ttk.Label(footer, text="", style="Info.TLabel")
    lbl_selected.pack(side=tk.LEFT)

    def _update_selected_count():
        selected = sum(1 for var, _ in checks if var.get())
        lbl_selected.config(text=f"{selected} selected for removal")

    def _set_all(state):
        for var, _ in checks:
            var.set(state)
        _update_selected_count()

    ttk.Button(footer, text="Select All", command=lambda: _set_all(True)).pack(side=tk.RIGHT, padx=4)
    ttk.Button(footer, text="Deselect All", command=lambda: _set_all(False)).pack(side=tk.RIGHT, padx=4)
    for var, _ in checks:
        var.trace_add("write", lambda *_: _update_selected_count())
    _update_selected_count()

    def _confirm():
        remove_indices = sorted([idx for var, idx in checks if var.get()], reverse=True)
        removed_payload = []
        for idx in remove_indices:
            if 0 <= idx < len(app.filtered_items):
                removed_payload.append((idx, copy.deepcopy(app.filtered_items[idx])))
                app.filtered_items.pop(idx)
        app.last_removed_bulk_items = removed_payload
        result["removed"] = len(remove_indices)
        dlg.destroy()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Remove Checked", style="Big.TButton", command=_confirm).pack(side=tk.RIGHT, padx=4)

    attach_vertical_mousewheel(canvas, canvas, inner)
    app._autosize_dialog(dlg, min_w=1120, min_h=560, max_w_ratio=0.98, max_h_ratio=0.92)
    dlg.wait_window()

    if result["removed"] > 0:
        app._apply_bulk_filter()
        app._update_bulk_summary()
        messagebox.showinfo("Removed", f"Removed {result['removed']} item(s) from this session.")


def open_buy_rule_editor(app, idx, order_rules_file):
    item = app.filtered_items[idx]
    key = (item["line_code"], item["item_code"])
    rule_key = f"{item['line_code']}:{item['item_code']}"
    rule = app.order_rules.get(rule_key, {})
    inv = app.inventory_lookup.get(key, {})
    initial_policy = rule.get("order_policy", item.get("order_policy", "standard"))
    initial_policy_locked = bool(rule.get("policy_locked"))

    dlg = tk.Toplevel(app.root)
    dlg.title(f"Buy Rule - {item['line_code']}{item['item_code']}")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text=f"{item['line_code']} {item['item_code']}", style="Header.TLabel").pack(anchor="w", padx=16, pady=(12, 2))
    ttk.Label(dlg, text=item.get("description", ""), style="SubHeader.TLabel", wraplength=760, justify="left").pack(anchor="w", padx=16, pady=(0, 12))

    form = ttk.LabelFrame(dlg, text="Ordering Rule", padding=12)
    form.pack(fill=tk.X, padx=16, pady=4)

    ttk.Label(form, text="Order Policy:").grid(row=0, column=0, sticky="w", pady=4)
    var_policy = tk.StringVar(value=initial_policy)
    combo_policy = ttk.Combobox(
        form, textvariable=var_policy, state="readonly", width=16,
        values=["standard", "soft_pack", "exact_qty", "reel_review", "manual_only"]
    )
    combo_policy.grid(row=0, column=1, sticky="w", padx=8, pady=4)

    var_allow = tk.BooleanVar(value=rule.get("allow_below_pack", False))
    ttk.Checkbutton(form, text="Allow ordering below pack/reel qty", variable=var_allow).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=4
    )

    ttk.Label(form, text="Min Order Qty:").grid(row=2, column=0, sticky="w", pady=4)
    var_min = tk.StringVar(value=str(rule.get("min_order_qty", "")))
    ttk.Entry(form, textvariable=var_min, width=10).grid(row=2, column=1, sticky="w", padx=8, pady=4)

    ttk.Label(form, text="Pack Qty:").grid(row=3, column=0, sticky="w", pady=4)
    var_pack = tk.StringVar(value=str(get_rule_pack_size(rule) or item.get("pack_size", "") or ""))
    ttk.Entry(form, textvariable=var_pack, width=10).grid(row=3, column=1, sticky="w", padx=8, pady=4)

    ttk.Label(form, text="Notes:").grid(row=4, column=0, sticky="nw", pady=4)
    notes_entry = ttk.Entry(form, width=30)
    notes_entry.grid(row=4, column=1, sticky="w", padx=8, pady=4)
    notes_entry.insert(0, rule.get("notes", ""))

    info = ttk.LabelFrame(dlg, text="Current Data", padding=8)
    info.pack(fill=tk.X, padx=16, pady=8)
    qoh = inv.get("qoh", 0)
    mx = inv.get("max")
    _, sug_max = app._suggest_min_max(key)
    ttk.Label(
        info,
        text=f"QOH: {qoh:g}  |  Max: {mx or '-'}  |  Sug Max: {sug_max or '-'}  |  "
        f"Raw Need: {item.get('raw_need', 0)}  |  Suggested: {item.get('suggested_qty', 0)}",
        style="Info.TLabel",
    ).pack(anchor="w")

    def _save_rule():
        new_rule = {
            "allow_below_pack": var_allow.get(),
            "notes": notes_entry.get().strip(),
        }
        min_val = var_min.get().strip()
        if min_val:
            try:
                new_rule["min_order_qty"] = int(float(min_val))
            except ValueError:
                pass
        pack_val = var_pack.get().strip()
        if pack_val:
            try:
                item["pack_size"] = int(float(pack_val))
                new_rule["pack_size"] = item["pack_size"]
            except ValueError:
                pass
        elif pack_val == "":
            item["pack_size"] = None
            new_rule.pop("pack_size", None)

        selected_policy = var_policy.get()
        inferred_policy = infer_default_order_policy(
            item,
            inv,
            item.get("pack_size"),
            allow_below_pack=new_rule.get("allow_below_pack", False),
        )
        user_changed_policy = selected_policy != initial_policy
        keep_existing_locked_policy = initial_policy_locked and not user_changed_policy
        if keep_existing_locked_policy and selected_policy != inferred_policy:
            new_rule["order_policy"] = selected_policy
            new_rule["policy_locked"] = True
        elif user_changed_policy and selected_policy != inferred_policy:
            new_rule["order_policy"] = selected_policy
            new_rule["policy_locked"] = True
        else:
            new_rule.pop("order_policy", None)
            new_rule.pop("policy_locked", None)

        app.order_rules[rule_key] = new_rule
        storage.save_order_rules(order_rules_file, app.order_rules)
        enrich_item(item, inv, item.get("pack_size"), new_rule)
        app._apply_bulk_filter()
        app._update_bulk_summary()
        if getattr(app, "bulk_sheet", None):
            app.bulk_sheet.refresh_row(str(idx), app._bulk_row_values(item))
        else:
            for child in app.bulk_tree.get_children():
                if int(child) == idx:
                    app.bulk_tree.item(child, values=app._bulk_row_values(item))
                    break
        dlg.destroy()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn_frame, text="Save Rule", style="Big.TButton", command=_save_rule).pack(side=tk.RIGHT, padx=4)

    app._autosize_dialog(dlg, min_w=460, min_h=380, max_w_ratio=0.65, max_h_ratio=0.85)
    dlg.wait_window()


def view_item_details(app):
    row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
    )
    if row_id is None:
        return
    idx = int(row_id)
    item = app.filtered_items[idx]
    key = (item["line_code"], item["item_code"])
    inv = app.inventory_lookup.get(key, {})

    dlg = tk.Toplevel(app.root)
    dlg.title(f"Details - {item['line_code']}{item['item_code']}")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text=f"{item['line_code']} {item['item_code']}", style="Header.TLabel").pack(anchor="w", padx=16, pady=(12, 2))
    ttk.Label(dlg, text=item.get("description", ""), style="SubHeader.TLabel", wraplength=820, justify="left").pack(anchor="w", padx=16, pady=(0, 12))

    grid = ttk.Frame(dlg, padding=16)
    grid.pack(fill=tk.BOTH, expand=True)
    grid.grid_columnconfigure(1, weight=1)

    details = [
        ("QOH", f"{inv.get('qoh', 0):g}"),
        ("On PO", f"{app.on_po_qty.get(key, 0):g}"),
        ("Min / Max", f"{inv.get('min', '-')} / {inv.get('max', '-')}"),
        ("Sug Min / Max", "/".join(str(x) if x else "-" for x in app._suggest_min_max(key))),
        ("Supplier", inv.get("supplier", "-")),
        ("Last Receipt", inv.get("last_receipt", "-")),
        ("Last Sale", inv.get("last_sale", "-")),
        ("YTD Sales", str(inv.get("ytd_sales", "-"))),
        ("12 Mo Sales", str(inv.get("mo12_sales", "-"))),
        ("", ""),
        ("Qty Sold", str(item.get("qty_sold", 0))),
        ("Qty Suspended", str(item.get("qty_suspended", 0))),
        ("Qty Received", str(item.get("qty_received", 0))),
        ("On PO (report)", f"{item.get('qty_on_po', 0):g}"),
        ("Raw Need", str(item.get("raw_need", 0))),
        ("Suggested Qty", str(item.get("suggested_qty", 0))),
        ("Final Qty", str(item.get("final_qty", 0))),
        ("Order Policy", item.get("order_policy", "-")),
        ("Status", item.get("status", "-")),
        ("Flags", ", ".join(item.get("data_flags", [])) or "none"),
    ]

    recent_list = app.recent_orders.get(key, [])
    if recent_list:
        total_recent = sum(row["qty"] for row in recent_list)
        entries = "; ".join(f"{row['qty']}x via {row['vendor']} ({row['date']})" for row in recent_list)
        details.append(("Recent Orders", f"{total_recent} total: {entries}"))

    other_lcs = app.duplicate_ic_lookup.get(item["item_code"], set())
    others = sorted(lc for lc in other_lcs if lc != item["line_code"])
    if others:
        details.append(("Also Under", ", ".join(others)))

    for r, (label, value) in enumerate(details):
        if label == "":
            ttk.Separator(grid, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
            continue
        ttk.Label(grid, text=f"{label}:", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=1)
        ttk.Label(grid, text=value, font=("Segoe UI", 9), wraplength=640, justify="left").grid(row=r, column=1, sticky="ew", pady=1)

    ttk.Button(dlg, text="Close", command=dlg.destroy).pack(pady=12)
    app._autosize_dialog(dlg, min_w=560, min_h=420, max_w_ratio=0.8, max_h_ratio=0.9)
    dlg.wait_window()


def edit_buy_rule_from_bulk(app):
    row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
    )
    if row_id is None:
        return
    app._open_buy_rule_editor(int(row_id))


def resolve_review_from_bulk(app):
    row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
    )
    if row_id is None:
        return
    idx = int(row_id)
    item = app.filtered_items[idx]
    item["review_resolved"] = True
    item["status"], item["data_flags"] = evaluate_item_status(item)
    if item.get("review_required") and item.get("review_resolved"):
        item["status"] = "ok"
    if getattr(app, "bulk_sheet", None):
        app.bulk_sheet.refresh_row(row_id, app._bulk_row_values(item))
    else:
        app.bulk_tree.item(row_id, values=app._bulk_row_values(item))
    app._update_bulk_summary()


def dismiss_duplicate_from_bulk(app):
    row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
    )
    if row_id is None:
        return
    idx = int(row_id)
    item = app.filtered_items[idx]
    app._dismiss_duplicate(item["item_code"])


def check_stock_warnings(app):
    flagged = []
    for item in app.filtered_items:
        if not item.get("vendor"):
            continue
        key = (item["line_code"], item["item_code"])
        inv = app.inventory_lookup.get(key, {})
        qoh = inv.get("qoh", 0)
        mn = inv.get("min")
        mx = inv.get("max")
        ps = item.get("pack_size")
        reason_text, _ = not_needed_reason(app, item, max_exceed_abs_buffer=5)
        if reason_text:
            reasons = [part.strip() for part in reason_text.split(";") if part.strip()]
            flagged.append((item, qoh, mn, mx, ps, reasons))

    if not flagged:
        return True

    dlg = tk.Toplevel(app.root)
    dlg.title("Review Flagged Items")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text="The following items may not need to be ordered manually.", style="Header.TLabel", wraplength=840).pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(dlg, text="Uncheck items you want to remove from the PO. Checked items will stay.", style="SubHeader.TLabel", wraplength=840).pack(anchor="w", padx=16, pady=(0, 12))

    container = ttk.Frame(dlg)
    container.pack(fill=tk.BOTH, expand=True, padx=16)
    canvas = tk.Canvas(container, highlightthickness=0, bg="#1e1e2e")
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    headers = ["Keep", "Line Code", "Item Code", "Description", "QOH", "Final Qty", "Pack", "Min", "Max", "Sug Max", "Why This Qty"]
    col_widths = [5, 7, 13, 22, 6, 6, 5, 5, 5, 7, 16]
    for c, (hdr, width) in enumerate(zip(headers, col_widths)):
        ttk.Label(inner, text=hdr, font=("Segoe UI", 9, "bold"), foreground="#c9a0dc", width=width).grid(row=0, column=c, sticky="w", padx=2, pady=4)
    inner.grid_columnconfigure(10, weight=1)

    check_vars = []
    for r, (item, qoh, mn, mx, ps, reasons) in enumerate(flagged, 1):
        key = (item["line_code"], item["item_code"])
        _, sug_max = app._suggest_min_max(key)
        var = tk.BooleanVar(value=True)
        check_vars.append((var, item))
        ttk.Checkbutton(inner, variable=var).grid(row=r, column=0, padx=2, pady=1)
        ttk.Label(inner, text=item["line_code"], width=7).grid(row=r, column=1, sticky="w", padx=2)
        ttk.Label(inner, text=item["item_code"], width=13).grid(row=r, column=2, sticky="w", padx=2)
        ttk.Label(inner, text=item["description"][:80], width=22, wraplength=260, justify="left").grid(row=r, column=3, sticky="w", padx=2)
        ttk.Label(inner, text=f"{qoh:g}", width=6).grid(row=r, column=4, sticky="w", padx=2)
        ttk.Label(inner, text=str(max(0, int(item["order_qty"]))), width=6).grid(row=r, column=5, sticky="w", padx=2)
        ttk.Label(inner, text=str(ps) if ps else "", width=5).grid(row=r, column=6, sticky="w", padx=2)
        ttk.Label(inner, text=str(mn) if mn is not None else "", width=5).grid(row=r, column=7, sticky="w", padx=2)
        ttk.Label(inner, text=str(mx) if mx is not None else "", width=5).grid(row=r, column=8, sticky="w", padx=2)
        ttk.Label(inner, text=str(sug_max) if sug_max is not None else "", width=7).grid(row=r, column=9, sticky="w", padx=2)
        ttk.Label(inner, text="; ".join(reasons), foreground="#f0c060", wraplength=560, justify="left").grid(row=r, column=10, sticky="ew", padx=2)

    result = {"proceed": False}

    def _confirm():
        for var, item in check_vars:
            if not var.get():
                item["vendor"] = ""
        app._populate_bulk_tree()
        result["proceed"] = True
        dlg.destroy()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="<- Go Back", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text=f"Confirm ({len(flagged)} item(s) flagged)", style="Big.TButton", command=_confirm).pack(side=tk.RIGHT, padx=4)

    attach_vertical_mousewheel(canvas, canvas, inner)
    app._autosize_dialog(dlg, min_w=900, min_h=520, max_w_ratio=0.95, max_h_ratio=0.92)
    dlg.wait_window()
    return result["proceed"]


def finish_bulk_final(app):
    unresolved = [
        item for item in app.filtered_items
        if item.get("vendor") and item.get("review_required") and not item.get("review_resolved")
    ]
    if unresolved:
        names = "\n".join(f"  - {item['line_code']}{item['item_code']}: {item.get('why', '')}" for item in unresolved[:10])
        suffix = f"\n  ... and {len(unresolved) - 10} more" if len(unresolved) > 10 else ""
        resp = messagebox.askyesno(
            "Unresolved Reviews",
            f"{len(unresolved)} item(s) need review before export:\n\n{names}{suffix}\n\n"
            "Include them anyway? (Select No to go back and resolve them.)"
        )
        if not resp:
            return

    app.assigned_items = [
        {
            "line_code": item["line_code"],
            "item_code": item["item_code"],
            "description": item["description"],
            "order_qty": max(0, int(item.get("final_qty", item.get("order_qty", 0)))),
            "qty_sold": item["qty_sold"],
            "qty_suspended": item.get("qty_suspended", 0),
            "qty_received": item.get("qty_received", 0),
            "vendor": item["vendor"],
            "pack_size": item.get("pack_size"),
            "status": item.get("status", "ok"),
            "why": item.get("why", ""),
            "order_policy": item.get("order_policy", ""),
            "data_flags": item.get("data_flags", []),
        }
        for item in app.filtered_items
        if item.get("vendor") and item.get("final_qty", item.get("order_qty", 0)) > 0
    ]
    if not app.assigned_items:
        messagebox.showwarning("No Items", "No items have a vendor and a final qty > 0.")
        return

    skipped_no_vendor = sum(1 for item in app.filtered_items if not item.get("vendor"))
    skipped_zero = sum(1 for item in app.filtered_items if item.get("vendor") and item.get("final_qty", item.get("order_qty", 0)) <= 0)

    app._populate_review_tab()
    app.notebook.tab(5, state="normal")
    app.notebook.select(5)

    skip_parts = []
    if skipped_no_vendor:
        skip_parts.append(f"{skipped_no_vendor} unassigned")
    if skipped_zero:
        skip_parts.append(f"{skipped_zero} with zero qty")
    if skip_parts:
        messagebox.showinfo("Items Excluded", f"Excluded from PO: {', '.join(skip_parts)}.")
