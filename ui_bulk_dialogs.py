import copy
import math
import tkinter as tk
from tkinter import ttk, messagebox

import bulk_remove_flow
import storage
import ui_bulk
from debug_log import write_debug
from rules import (
    determine_acceptable_overstock_qty,
    enrich_item,
    evaluate_item_status,
    get_rule_float,
    get_rule_int,
    get_rule_pack_size,
    infer_default_order_policy,
    package_profile_label,
    replenishment_unit_mode_label,
    recency_review_bucket_label,
)
from ui_scroll import attach_vertical_mousewheel, sync_canvas_window


def flush_pending_bulk_sheet_edit(app):
    bulk_sheet = getattr(app, "bulk_sheet", None)
    if bulk_sheet and hasattr(bulk_sheet, "flush_pending_edit"):
        bulk_sheet.flush_pending_edit()


def resolve_bulk_row(app, row_id):
    resolver = getattr(app, "_resolve_bulk_row_id", None)
    if callable(resolver):
        return resolver(row_id)
    return ui_bulk.resolve_bulk_row_id(app, row_id)


def buy_rule_field_visibility(*, advanced=False):
    return {
        "trigger_qty": advanced,
        "trigger_pct": advanced,
        "min_packs": advanced,
        "cover_days": advanced,
        "cover_cycles": advanced,
        "overstock_qty": advanced,
        "overstock_pct": advanced,
        "notes": advanced,
    }


def should_expand_buy_rule_advanced(rule):
    if not rule:
        return False
    advanced_keys = (
        "reorder_trigger_qty",
        "reorder_trigger_pct",
        "minimum_packs_on_hand",
        "minimum_cover_days",
        "minimum_cover_cycles",
        "acceptable_overstock_qty",
        "acceptable_overstock_pct",
        "notes",
    )
    for key in advanced_keys:
        value = rule.get(key)
        if value not in (None, "", 0, 0.0, False):
            return True
    return False


def not_needed_reason(app, item, max_exceed_abs_buffer):
    reasons = []
    auto_remove = False
    key = (item["line_code"], item["item_code"])
    inv = app.inventory_lookup.get(key, {})
    qoh = inv.get("qoh", 0)
    if qoh is None:
        qoh = 0
    mx = inv.get("max")
    ps = item.get("pack_size")
    po_qty = item.get("qty_on_po", app.on_po_qty.get(key, 0))
    final_qty = item.get("final_qty", item.get("order_qty", 0))
    suggested_qty = item.get("suggested_qty", final_qty)
    gross_need = item.get("gross_need", item.get("raw_need", final_qty))
    inventory_position = item.get("inventory_position", qoh + po_qty)
    target_stock = item.get("target_stock")
    effective_target_stock = item.get("effective_target_stock")
    demand_signal = item.get("demand_signal", gross_need)
    effective_susp = item.get("effective_qty_suspended", item.get("qty_suspended", 0))
    effective_sales = item.get("effective_qty_sold", item.get("qty_sold", 0))
    performance_profile = item.get("performance_profile", "")
    sales_health_signal = item.get("sales_health_signal", "")
    possible_missed_reorder = bool(item.get("possible_missed_reorder"))
    reorder_trigger_threshold = item.get("reorder_trigger_threshold")
    reorder_trigger_basis = item.get("reorder_trigger_basis", "")
    reorder_needed = bool(item.get("reorder_needed"))
    acceptable_overstock = item.get("acceptable_overstock_qty_effective")
    if acceptable_overstock in (None, ""):
        acceptable_overstock = determine_acceptable_overstock_qty(item)

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

    if (
        isinstance(effective_target_stock, (int, float))
        and effective_target_stock > 0
        and (
            not isinstance(target_stock, (int, float))
            or effective_target_stock > target_stock
        )
    ):
        target_stock = effective_target_stock

    if target_stock and inventory_position >= target_stock and final_qty > 0:
        reasons.append(
            f"Inventory position already meets target (pos {inventory_position:g} >= target {target_stock:g})"
        )
        auto_remove = True

    if demand_signal <= 0 and inventory_position > 0 and final_qty > 0:
        reasons.append(f"No uncovered demand signal (sales {effective_sales:g}, susp {effective_susp:g})")
        auto_remove = True

    if (
        ps
        and qoh >= gross_need
        and gross_need > 0
        and not (
            reorder_needed
            and isinstance(reorder_trigger_threshold, (int, float))
            and reorder_trigger_threshold > 0
        )
    ):
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
        hard_threshold = hard_max + _margin(hard_max) + acceptable_overstock
        hard_excess = resulting_stock > hard_threshold
    else:
        hard_threshold = None

    if soft_max is not None:
        soft_threshold = soft_max + _margin(soft_max) + acceptable_overstock
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
    elif acceptable_overstock > 0 and resulting_stock > (soft_max or 0):
        reasons.append(
            f"Review: intentional overstock is within tolerance (stock {resulting_stock:g}; allowed over target {acceptable_overstock:g})"
        )
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

    protect_from_auto_remove = False
    if possible_missed_reorder:
        reasons.append("Review: likely missed reorder candidate based on historical sales and stale recency")
        protect_from_auto_remove = True
    elif (
        reorder_needed
        and isinstance(reorder_trigger_threshold, (int, float))
        and reorder_trigger_threshold > 0
    ):
        basis_label = {
            "minimum_packs_on_hand": "minimum packs on hand",
            "trigger_qty": "trigger quantity",
            "trigger_pct": "trigger percent",
            "current_min": "current min",
            "configured_trigger": "configured trigger",
        }.get(reorder_trigger_basis, "trigger threshold")
        reasons.append(
            f"Review: trigger-based replenishment is active (pos {inventory_position:g} <= trigger {reorder_trigger_threshold:g}; basis {basis_label})"
        )
        protect_from_auto_remove = True
    elif performance_profile in ("top_performer", "steady") and sales_health_signal == "dormant":
        reasons.append("Review: historically meaningful item is dormant, so removal should be confirmed manually")
        protect_from_auto_remove = True

    if protect_from_auto_remove:
        auto_remove = False

    return "; ".join(reasons), auto_remove


def bulk_remove_not_needed(app, scope, max_exceed_abs_buffer, *, include_assigned=None):
    flush_pending_bulk_sheet_edit(app)
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

    if include_assigned is None:
        get_scope = getattr(app, "_get_remove_not_needed_scope", None)
        if callable(get_scope):
            include_assigned = get_scope() == "include_assigned"
        else:
            settings = getattr(app, "app_settings", {}) or {}
            include_assigned = str(
                settings.get("remove_not_needed_scope", "unassigned_only") or ""
            ).strip() == "include_assigned"

    candidates = []
    for iid in row_ids:
        idx, item = resolve_bulk_row(app, iid)
        if idx is None or item is None:
            continue
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
        text="Click the Remove column to toggle. Checked items (☑) will be removed from this session.",
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", padx=16, pady=(0, 12))

    container = ttk.Frame(dlg)
    container.pack(fill=tk.BOTH, expand=True, padx=16)

    columns = ("remove", "lc", "item_code", "description", "final_qty", "qoh", "max", "sug_max", "reason")
    tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="extended")

    col_cfg = [
        ("remove",      "Remove",    52,  "center"),
        ("lc",          "LC",        52,  "w"),
        ("item_code",   "Item Code", 110, "w"),
        ("description", "Desc",      200, "w"),
        ("final_qty",   "Qty",       52,  "center"),
        ("qoh",         "QOH",       52,  "center"),
        ("max",         "Max",       52,  "center"),
        ("sug_max",     "Sug Max",   64,  "center"),
        ("reason",      "Why This Qty", 400, "w"),
    ]
    for col, heading, width, anchor in col_cfg:
        tree.heading(col, text=heading)
        tree.column(col, width=width, anchor=anchor, stretch=(col == "reason"))

    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)

    # checked_set holds the tree iid strings of rows marked for removal
    checked_set = set()

    for r, (idx, item, reason, auto_remove) in enumerate(candidates):
        key = (item["line_code"], item["item_code"])
        inv = app.inventory_lookup.get(key, {})
        qoh = inv.get("qoh", 0)
        cur_max = inv.get("max")
        _, sug_max = app._suggest_min_max(key)
        final_qty = item.get("final_qty", item.get("order_qty", 0))
        iid = str(r)
        mark = "☑" if auto_remove else "☐"
        tree.insert(
            "", "end", iid=iid,
            values=(
                mark,
                item["line_code"],
                item["item_code"],
                item.get("description", "")[:80],
                f"{final_qty:g}",
                f"{qoh:g}",
                str(cur_max) if cur_max is not None else "",
                str(sug_max) if sug_max is not None else "",
                reason,
            ),
        )
        if auto_remove:
            checked_set.add(iid)

    result = {"removed": 0}

    footer = ttk.Frame(dlg)
    footer.pack(fill=tk.X, padx=16, pady=(4, 0))
    lbl_selected = ttk.Label(footer, text="", style="Info.TLabel")
    lbl_selected.pack(side=tk.LEFT)

    def _update_count():
        lbl_selected.config(text=f"{len(checked_set)} selected for removal")

    def _toggle(event):
        region = tree.identify_region(event.x, event.y)
        col = tree.identify_column(event.x)
        iid = tree.identify_row(event.y)
        if not iid:
            return
        # toggle on click anywhere in the Remove column, or on double-click anywhere
        if region == "cell" and (col == "#1" or event.type == tk.EventType.Double):
            if iid in checked_set:
                checked_set.discard(iid)
                tree.set(iid, "remove", "☐")
            else:
                checked_set.add(iid)
                tree.set(iid, "remove", "☑")
            _update_count()

    tree.bind("<ButtonRelease-1>", _toggle)

    def _set_all(state):
        for r in range(len(candidates)):
            iid = str(r)
            if state:
                checked_set.add(iid)
                tree.set(iid, "remove", "☑")
            else:
                checked_set.discard(iid)
                tree.set(iid, "remove", "☐")
        _update_count()

    ttk.Button(footer, text="Select All",   command=lambda: _set_all(True)).pack(side=tk.RIGHT, padx=4)
    ttk.Button(footer, text="Deselect All", command=lambda: _set_all(False)).pack(side=tk.RIGHT, padx=4)
    _update_count()

    def _confirm():
        # map tree iid -> original candidate index
        remove_indices = sorted(
            [candidates[int(iid)][0] for iid in checked_set],
            reverse=True,
        )
        removed_payload = bulk_remove_flow.remove_filtered_rows(
            app,
            remove_indices,
            copy.deepcopy,
            history_label=f"remove:not_needed:{scope}",
        )
        result["removed"] = len(removed_payload)
        dlg.destroy()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Cancel",         command=dlg.destroy).pack(side=tk.LEFT,  padx=4)
    ttk.Button(btn_frame, text="Remove Checked", style="Big.TButton", command=_confirm).pack(side=tk.RIGHT, padx=4)

    attach_vertical_mousewheel(tree)
    app._autosize_dialog(dlg, min_w=1120, min_h=560, max_w_ratio=0.98, max_h_ratio=0.92)
    dlg.wait_window()

    if result["removed"] > 0:
        app._apply_bulk_filter()
        app._update_bulk_summary()
        messagebox.showinfo("Removed", f"Removed {result['removed']} item(s) from this session.")


def open_buy_rule_editor(app, idx, order_rules_file):
    flush_pending_bulk_sheet_edit(app)
    item = app.filtered_items[idx]
    key = (item["line_code"], item["item_code"])
    rule_key = f"{item['line_code']}:{item['item_code']}"
    rule = app.order_rules.get(rule_key, {})
    inv = app.inventory_lookup.get(key, {})
    write_debug(
        "buy_rule_editor.open",
        idx=idx,
        line_code=item["line_code"],
        item_code=item["item_code"],
        item_pack=item.get("pack_size"),
        item_policy=item.get("order_policy", ""),
        rule=repr(rule),
    )
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
        values=["standard", "pack_trigger", "soft_pack", "exact_qty", "reel_review", "large_pack_review", "manual_only"]
    )
    combo_policy.grid(row=0, column=1, sticky="w", padx=8, pady=4)

    var_allow = tk.BooleanVar(value=rule.get("allow_below_pack", False))
    ttk.Checkbutton(form, text="Allow ordering below pack/reel qty", variable=var_allow).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=4
    )

    var_min = tk.StringVar(value=str(rule.get("min_order_qty", "")))
    var_pack = tk.StringVar(value=str(get_rule_pack_size(rule) or item.get("pack_size", "") or ""))
    var_trigger_qty = tk.StringVar(value=str(get_rule_int(rule, "reorder_trigger_qty") or ""))
    var_trigger_pct = tk.StringVar(value=str(get_rule_float(rule, "reorder_trigger_pct") or ""))
    var_min_packs = tk.StringVar(value=str(get_rule_int(rule, "minimum_packs_on_hand") or ""))
    var_cover_days = tk.StringVar(value=str(get_rule_float(rule, "minimum_cover_days") or ""))
    var_cover_cycles = tk.StringVar(value=str(get_rule_float(rule, "minimum_cover_cycles") or ""))
    var_overstock_qty = tk.StringVar(value=str(get_rule_int(rule, "acceptable_overstock_qty") or ""))
    var_overstock_pct = tk.StringVar(value=str(get_rule_float(rule, "acceptable_overstock_pct") or ""))
    var_show_advanced = tk.BooleanVar(value=should_expand_buy_rule_advanced(rule))
    notes_entry = ttk.Entry(form, width=30)
    notes_entry.insert(0, rule.get("notes", ""))

    field_widgets = {
        "min_order_qty": (ttk.Label(form, text="Min Order Qty:"), ttk.Entry(form, textvariable=var_min, width=10)),
        "pack_qty": (ttk.Label(form, text="Pack Qty:"), ttk.Entry(form, textvariable=var_pack, width=10)),
        "trigger_qty": (ttk.Label(form, text="Trigger Qty:"), ttk.Entry(form, textvariable=var_trigger_qty, width=10)),
        "trigger_pct": (ttk.Label(form, text="Trigger %:"), ttk.Entry(form, textvariable=var_trigger_pct, width=10)),
        "min_packs": (ttk.Label(form, text="Min Packs:"), ttk.Entry(form, textvariable=var_min_packs, width=10)),
        "cover_days": (ttk.Label(form, text="Cover Days:"), ttk.Entry(form, textvariable=var_cover_days, width=10)),
        "cover_cycles": (ttk.Label(form, text="Cover Cycles:"), ttk.Entry(form, textvariable=var_cover_cycles, width=10)),
        "overstock_qty": (ttk.Label(form, text="Overstock Qty:"), ttk.Entry(form, textvariable=var_overstock_qty, width=10)),
        "overstock_pct": (ttk.Label(form, text="Overstock %:"), ttk.Entry(form, textvariable=var_overstock_pct, width=10)),
        "notes": (ttk.Label(form, text="Notes:"), notes_entry),
    }
    advanced_toggle = ttk.Checkbutton(form, text="Show Advanced", variable=var_show_advanced)
    helper_label = ttk.Label(
        form,
        text=(
            "Common path: set policy, allow-below-pack, min order, and pack. "
            "Use Advanced for trigger floors, cover rules, overstock tolerance, and notes."
        ),
        style="Info.TLabel",
        wraplength=620,
        justify="left",
    )

    def _place_field(row_idx, field_key):
        label, widget = field_widgets[field_key]
        sticky = "nw" if field_key == "notes" else "w"
        label.grid(row=row_idx, column=0, sticky=sticky, pady=4)
        widget.grid(row=row_idx, column=1, sticky="w", padx=8, pady=4)

    def _safe_grid_remove(widget):
        remover = getattr(widget, "grid_remove", None)
        if callable(remover):
            remover()

    def _refresh_rule_layout(*_args):
        for label, widget in field_widgets.values():
            _safe_grid_remove(label)
            _safe_grid_remove(widget)
        _safe_grid_remove(advanced_toggle)
        _safe_grid_remove(helper_label)

        row_idx = 2
        for field_key in ("min_order_qty", "pack_qty"):
            _place_field(row_idx, field_key)
            row_idx += 1

        advanced_toggle.grid(row=row_idx, column=0, columnspan=2, sticky="w", pady=(2, 4))
        row_idx += 1

        visibility = buy_rule_field_visibility(advanced=var_show_advanced.get())
        for field_key in ("trigger_qty", "trigger_pct", "min_packs", "cover_days", "cover_cycles", "overstock_qty", "overstock_pct", "notes"):
            if visibility.get(field_key):
                _place_field(row_idx, field_key)
                row_idx += 1

        helper_label.grid(row=row_idx, column=0, columnspan=2, sticky="w", pady=(6, 0))

    advanced_toggle.configure(command=_refresh_rule_layout)
    _refresh_rule_layout()

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

    inferred_frame = None
    inferred_actions = []
    if (
        item.get("minimum_packs_on_hand_source") == "heuristic"
        and get_rule_int(rule, "minimum_packs_on_hand") is None
        and item.get("minimum_packs_on_hand") is not None
    ) or (
        item.get("minimum_cover_cycles_source") == "heuristic"
        and get_rule_float(rule, "minimum_cover_cycles") is None
        and item.get("minimum_cover_cycles") is not None
    ):
        inferred_frame = ttk.LabelFrame(dlg, text="Inferred Package Floors", padding=8)
        inferred_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(
            inferred_frame,
            text=(
                "This item currently uses inferred hardware/package floors. "
                "Use the buttons below to explicitly adopt them into the saved buy rule."
            ),
            style="Info.TLabel",
            wraplength=760,
            justify="left",
        ).pack(anchor="w")

        action_row = ttk.Frame(inferred_frame)
        action_row.pack(fill=tk.X, pady=(8, 0))

        if (
            item.get("minimum_packs_on_hand_source") == "heuristic"
            and get_rule_int(rule, "minimum_packs_on_hand") is None
            and item.get("minimum_packs_on_hand") is not None
        ):
            inferred_min_packs = int(float(item.get("minimum_packs_on_hand") or 0))

            def _use_inferred_min_packs():
                var_min_packs.set(str(inferred_min_packs))

            inferred_actions.append(
                ttk.Button(action_row, text="Use Inferred Min Packs", command=_use_inferred_min_packs)
            )

        if (
            item.get("minimum_cover_cycles_source") == "heuristic"
            and get_rule_float(rule, "minimum_cover_cycles") is None
            and item.get("minimum_cover_cycles") is not None
        ):
            inferred_cover_cycles = float(item.get("minimum_cover_cycles") or 0)

            def _use_inferred_cover_cycles():
                var_cover_cycles.set(str(int(inferred_cover_cycles)) if inferred_cover_cycles.is_integer() else str(inferred_cover_cycles))

            inferred_actions.append(
                ttk.Button(action_row, text="Use Inferred Cover Cycles", command=_use_inferred_cover_cycles)
            )

        for btn in inferred_actions:
            btn.pack(side=tk.LEFT, padx=4)

    def _save_rule():
        new_rule = {
            "allow_below_pack": var_allow.get(),
            "notes": notes_entry.get().strip(),
        }
        write_debug(
            "buy_rule_editor.save.begin",
            idx=idx,
            line_code=item["line_code"],
            item_code=item["item_code"],
            selected_policy=var_policy.get(),
            allow_below_pack=var_allow.get(),
            min_order_qty=var_min.get().strip(),
            pack_qty=var_pack.get().strip(),
            reorder_trigger_qty=var_trigger_qty.get().strip(),
            reorder_trigger_pct=var_trigger_pct.get().strip(),
            minimum_packs_on_hand=var_min_packs.get().strip(),
            minimum_cover_days=var_cover_days.get().strip(),
            minimum_cover_cycles=var_cover_cycles.get().strip(),
            acceptable_overstock_qty=var_overstock_qty.get().strip(),
            acceptable_overstock_pct=var_overstock_pct.get().strip(),
            initial_policy=initial_policy,
            initial_policy_locked=initial_policy_locked,
        )
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

        trigger_qty_val = var_trigger_qty.get().strip()
        if trigger_qty_val:
            try:
                new_rule["reorder_trigger_qty"] = int(float(trigger_qty_val))
            except ValueError:
                pass

        trigger_pct_val = var_trigger_pct.get().strip()
        if trigger_pct_val:
            try:
                new_rule["reorder_trigger_pct"] = float(trigger_pct_val)
            except ValueError:
                pass

        min_packs_val = var_min_packs.get().strip()
        if min_packs_val:
            try:
                new_rule["minimum_packs_on_hand"] = int(float(min_packs_val))
            except ValueError:
                pass

        cover_days_val = var_cover_days.get().strip()
        if cover_days_val:
            try:
                new_rule["minimum_cover_days"] = float(cover_days_val)
            except ValueError:
                pass

        cover_cycles_val = var_cover_cycles.get().strip()
        if cover_cycles_val:
            try:
                new_rule["minimum_cover_cycles"] = float(cover_cycles_val)
            except ValueError:
                pass

        overstock_qty_val = var_overstock_qty.get().strip()
        if overstock_qty_val:
            try:
                new_rule["acceptable_overstock_qty"] = int(float(overstock_qty_val))
            except ValueError:
                pass

        overstock_pct_val = var_overstock_pct.get().strip()
        if overstock_pct_val:
            try:
                new_rule["acceptable_overstock_pct"] = float(overstock_pct_val)
            except ValueError:
                pass

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
        if hasattr(app, "_save_order_rules"):
            app._save_order_rules()
        else:
            storage.save_order_rules(order_rules_file, app.order_rules)
        enrich_item(item, inv, item.get("pack_size"), new_rule)
        write_debug(
            "buy_rule_editor.save.applied",
            idx=idx,
            line_code=item["line_code"],
            item_code=item["item_code"],
            inferred_policy=inferred_policy,
            saved_rule=repr(new_rule),
            result_policy=item.get("order_policy", ""),
            raw_need=item.get("raw_need"),
            suggested=item.get("suggested_qty"),
            final=item.get("final_qty"),
            why=item.get("why", ""),
        )
        app._apply_bulk_filter()
        app._update_bulk_summary()
        if getattr(app, "bulk_sheet", None):
            try:
                rendered = app._bulk_row_values(item)
                write_debug(
                    "buy_rule_editor.save.rendered_row",
                    idx=idx,
                    row=" || ".join("" if cell is None else str(cell) for cell in rendered),
                )
            except Exception as exc:
                write_debug("buy_rule_editor.save.rendered_row_error", idx=idx, error=str(exc))
            app.bulk_sheet.refresh_row(ui_bulk.bulk_row_id(item), app._bulk_row_values(item))
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
    flush_pending_bulk_sheet_edit(app)
    row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
    )
    if row_id is None:
        return
    idx, item = resolve_bulk_row(app, row_id)
    if idx is None or item is None:
        return
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

    details = item_details_rows(app, item, inv, key)

    for r, (label, value) in enumerate(details):
        if label == "":
            ttk.Separator(grid, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
            continue
        ttk.Label(grid, text=f"{label}:", font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=1)
        ttk.Label(grid, text=value, font=("Segoe UI", 9), wraplength=640, justify="left").grid(row=r, column=1, sticky="ew", pady=1)

    ttk.Button(dlg, text="Close", command=dlg.destroy).pack(pady=12)
    app._autosize_dialog(dlg, min_w=560, min_h=420, max_w_ratio=0.8, max_h_ratio=0.9)
    dlg.wait_window()


def item_details_rows(app, item, inv, key):
    minimum_packs = item.get("minimum_packs_on_hand")
    minimum_packs_source = item.get("minimum_packs_on_hand_source")
    if minimum_packs is None:
        minimum_packs_display = "-"
    else:
        source_suffix = {
            "heuristic": " (Inferred)",
            "rule": " (Saved Rule)",
        }.get(minimum_packs_source, "")
        minimum_packs_display = f"{minimum_packs}{source_suffix}"
    minimum_cover_days = item.get("minimum_cover_days")
    minimum_cover_days_source = item.get("minimum_cover_days_source")
    if minimum_cover_days is None:
        minimum_cover_days_display = "-"
    else:
        source_suffix = {
            "heuristic": " (Inferred)",
            "rule": " (Saved Rule)",
        }.get(minimum_cover_days_source, "")
        minimum_cover_days_display = f"{_format_metric(minimum_cover_days)}{source_suffix}"
    minimum_cover_cycles = item.get("minimum_cover_cycles")
    minimum_cover_cycles_source = item.get("minimum_cover_cycles_source")
    if minimum_cover_cycles is None:
        minimum_cover_cycles_display = "-"
    else:
        source_suffix = {
            "heuristic": " (Inferred)",
            "rule": " (Saved Rule)",
        }.get(minimum_cover_cycles_source, "")
        minimum_cover_cycles_display = f"{_format_metric(minimum_cover_cycles)}{source_suffix}"
    shipping_policy_source = {
        "saved_policy": "Saved Vendor Policy",
        "default_preset": f"Default Preset ({item.get('shipping_policy_preset_label') or '-'})",
        "none": "None",
    }.get(item.get("shipping_policy_source"), item.get("shipping_policy_source") or "-")

    details = [
        ("QOH", f"{inv.get('qoh', 0):g}"),
        ("On PO", f"{app.on_po_qty.get(key, 0):g}"),
        ("Min / Max", f"{inv.get('min', '-')} / {inv.get('max', '-')}"),
        ("Sug Min / Max", "/".join(str(x) if x else "-" for x in app._suggest_min_max(key))),
        ("Supplier", inv.get("supplier", "-")),
        ("Receipt Vendor", item.get("receipt_primary_vendor") or "-"),
        ("Receipt Confidence", item.get("receipt_vendor_confidence") or "-"),
        ("Last Receipt", inv.get("last_receipt", "-")),
        ("Last Sale", inv.get("last_sale", "-")),
        ("Days Since Last Sale", str(item.get("days_since_last_sale", "-") if item.get("days_since_last_sale") is not None else "-")),
        ("Recency Confidence", item.get("recency_confidence") or "-"),
        ("Data Completeness", item.get("data_completeness") or "-"),
        ("Recency Review Type", recency_review_bucket_label(item.get("recency_review_bucket")) or "-"),
        ("YTD Sales", str(inv.get("ytd_sales", "-"))),
        ("12 Mo Sales", str(inv.get("mo12_sales", "-"))),
        ("Sales Window", _sales_window_label(item)),
        ("Avg Weekly Sales", _format_metric(item.get("avg_weekly_sales_loaded"))),
        ("Avg Monthly Sales", _format_metric(item.get("avg_monthly_sales_loaded"))),
        ("Annualized Sales", _format_metric(item.get("annualized_sales_loaded"))),
        ("Txn Count", str(item.get("transaction_count", "-") if item.get("transaction_count") is not None else "-")),
        ("Sale Days", str(item.get("sale_day_count", "-") if item.get("sale_day_count") is not None else "-")),
        ("Avg Units / Txn", _format_metric(item.get("avg_units_per_transaction"))),
        ("Median Units / Txn", _format_metric(item.get("median_units_per_transaction"))),
        ("Max Units / Txn", _format_metric(item.get("max_units_per_transaction"))),
        ("Avg Days Between Sales", _format_metric(item.get("avg_days_between_sales"))),
        ("Performance", item.get("performance_profile") or "-"),
        ("Sales Health", item.get("sales_health_signal") or "-"),
        ("Attention", item.get("reorder_attention_signal") or "-"),
        ("", ""),
        ("Qty Sold", str(item.get("qty_sold", 0))),
        ("Qty Suspended", str(item.get("qty_suspended", 0))),
        ("Qty Received", str(item.get("qty_received", 0))),
        ("On PO (report)", f"{item.get('qty_on_po', 0):g}"),
        ("Raw Need", str(item.get("raw_need", 0))),
        ("Suggested Qty", str(item.get("suggested_qty", 0))),
        ("Final Qty", str(item.get("final_qty", 0))),
        ("Order Policy", item.get("order_policy", "-")),
        ("Package Profile", package_profile_label(item.get("package_profile")) or "-"),
        ("Replenishment Mode", replenishment_unit_mode_label(item.get("replenishment_unit_mode")) or "-"),
        ("Trigger Qty", str(item.get("reorder_trigger_qty", "-") if item.get("reorder_trigger_qty") is not None else "-")),
        ("Trigger %", _format_metric(item.get("reorder_trigger_pct")) if item.get("reorder_trigger_pct") is not None else "-"),
        ("Min Packs", minimum_packs_display),
        ("Cover Days", minimum_cover_days_display),
        ("Cover Cycles", minimum_cover_cycles_display),
        ("Overstock Qty", str(item.get("acceptable_overstock_qty", "-") if item.get("acceptable_overstock_qty") is not None else "-")),
        ("Overstock %", _format_metric(item.get("acceptable_overstock_pct")) if item.get("acceptable_overstock_pct") is not None else "-"),
        ("Allowed Overstock", str(item.get("acceptable_overstock_qty_effective", "-") if item.get("acceptable_overstock_qty_effective") is not None else "-")),
        ("Projected Overstock", str(item.get("projected_overstock_qty", "-") if item.get("projected_overstock_qty") is not None else "-")),
        ("Recommended Action", item.get("recommended_action") or "-"),
        ("Shipping Policy", item.get("shipping_policy") or "-"),
        ("Policy Source", shipping_policy_source),
        ("Urgent Override", item.get("urgent_release_mode") or "-"),
        ("Release Lead Days", str(item.get("release_lead_business_days", "-") if item.get("release_lead_business_days") is not None else "-")),
        ("Timing Mode", item.get("release_timing_mode") or "-"),
        ("Release Decision", item.get("release_decision") or "-"),
        ("Release Reason", item.get("release_reason") or "-"),
        ("Vendor Order Value", _format_metric(item.get("vendor_order_value_total")) if item.get("vendor_order_value_total") is not None else "-"),
        ("Vendor Value Coverage", item.get("vendor_value_coverage") or "-"),
        ("Threshold Shortfall", _format_metric(item.get("vendor_threshold_shortfall")) if item.get("vendor_threshold_shortfall") is not None else "-"),
        ("Threshold Progress %", _format_metric(item.get("vendor_threshold_progress_pct")) if item.get("vendor_threshold_progress_pct") is not None else "-"),
        ("Next Free-Ship Date", item.get("next_free_ship_date") or "-"),
        ("Planned Export Date", item.get("planned_export_date") or "-"),
        ("Target Order Date", item.get("target_order_date") or "-"),
        ("Target Release Date", item.get("target_release_date") or "-"),
        ("Status", item.get("status", "-")),
        ("Flags", ", ".join(item.get("data_flags", [])) or "none"),
    ]

    recent_list = app.recent_orders.get(key, [])
    if recent_list:
        total_recent = sum(row["qty"] for row in recent_list)
        entries = "; ".join(f"{row['qty']}x via {row['vendor']} ({row['date']})" for row in recent_list)
        details.append(("Recent Orders", f"{total_recent} total: {entries}"))
    receipt_candidates = list(item.get("receipt_vendor_candidates", []) or [])
    if receipt_candidates:
        details.append(("Receipt Vendor Candidates", ", ".join(receipt_candidates[:5])))

    other_lcs = app.duplicate_ic_lookup.get(item["item_code"], set())
    others = sorted(lc for lc in other_lcs if lc != item["line_code"])
    if others:
        details.append(("Also Under", ", ".join(others)))
    return details


def _format_metric(value):
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _sales_window_label(item):
    start = item.get("sales_window_start", "") or ""
    end = item.get("sales_window_end", "") or ""
    span_days = item.get("sales_span_days")
    if start and end and span_days:
        return f"{start} to {end} ({span_days} days)"
    if span_days:
        return f"{span_days} days"
    return "-"


def edit_buy_rule_from_bulk(app):
    flush_pending_bulk_sheet_edit(app)
    right_click_context = getattr(app, "_right_click_bulk_context", None) or {}
    row_id = right_click_context.get("row_id")
    if row_id is None:
        row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
        )
    write_debug(
        "bulk_edit_buy_rule.command",
        resolved_row_id="" if row_id is None else row_id,
        right_click_context=repr(right_click_context),
    )
    if row_id is None:
        return
    idx, _item = resolve_bulk_row(app, row_id)
    if idx is None:
        return
    app._open_buy_rule_editor(idx)


def resolve_review_from_bulk(app):
    flush_pending_bulk_sheet_edit(app)
    row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
    )
    if row_id is None:
        return
    idx, item = resolve_bulk_row(app, row_id)
    if idx is None or item is None:
        return
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
    flush_pending_bulk_sheet_edit(app)
    row_id = getattr(app, "_right_click_row_id", None) or (
        app.bulk_sheet.current_row_id() if getattr(app, "bulk_sheet", None) else None
    )
    if row_id is None:
        return
    idx, item = resolve_bulk_row(app, row_id)
    if idx is None or item is None:
        return
    app._dismiss_duplicate(item["item_code"])


def check_stock_warnings(app):
    flush_pending_bulk_sheet_edit(app)
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
    inner.bind("<Configure>", lambda e: sync_canvas_window(canvas, content_window))
    content_window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind("<Configure>", lambda e: sync_canvas_window(canvas, content_window, width=e.width))
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
    flush_pending_bulk_sheet_edit(app)
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
            "final_qty": max(0, int(item.get("final_qty", item.get("order_qty", 0)))),
            "qty_sold": item["qty_sold"],
            "qty_suspended": item.get("qty_suspended", 0),
            "qty_received": item.get("qty_received", 0),
            "vendor": item["vendor"],
            "pack_size": item.get("pack_size"),
            "status": item.get("status", "ok"),
            "why": item.get("why", ""),
            "core_why": item.get("core_why", item.get("why", "")),
            "order_policy": item.get("order_policy", ""),
            "data_flags": item.get("data_flags", []),
            "review_required": item.get("review_required", False),
            "review_resolved": item.get("review_resolved", False),
            "suggested_qty": item.get("suggested_qty", 0),
            "raw_need": item.get("raw_need", 0),
            "recency_confidence": item.get("recency_confidence", ""),
            "data_completeness": item.get("data_completeness", ""),
            "recency_review_bucket": item.get("recency_review_bucket"),
            "performance_profile": item.get("performance_profile", ""),
            "sales_health_signal": item.get("sales_health_signal", ""),
            "reorder_attention_signal": item.get("reorder_attention_signal", ""),
            "recent_local_order_count": item.get("recent_local_order_count", 0),
            "recent_local_order_qty": item.get("recent_local_order_qty", 0),
            "recent_local_order_date": item.get("recent_local_order_date", ""),
            "receipt_primary_vendor": item.get("receipt_primary_vendor", ""),
            "receipt_most_recent_vendor": item.get("receipt_most_recent_vendor", ""),
            "receipt_vendor_confidence": item.get("receipt_vendor_confidence", ""),
            "receipt_vendor_confidence_reason": item.get("receipt_vendor_confidence_reason", ""),
            "receipt_vendor_ambiguous": item.get("receipt_vendor_ambiguous", False),
            "receipt_vendor_qty_share": item.get("receipt_vendor_qty_share"),
            "receipt_vendor_receipt_share": item.get("receipt_vendor_receipt_share"),
            "receipt_vendor_candidates": list(item.get("receipt_vendor_candidates", []) or []),
            "inventory_position": item.get("inventory_position", 0),
        }
        for item in app.filtered_items
        if item.get("vendor") and item.get("final_qty", item.get("order_qty", 0)) > 0
    ]
    if not app.assigned_items:
        messagebox.showwarning("No Items", "No items have a vendor and a final qty > 0.")
        return

    skipped_no_vendor = sum(1 for item in app.filtered_items if not item.get("vendor"))
    skipped_zero = sum(1 for item in app.filtered_items if item.get("vendor") and item.get("final_qty", item.get("order_qty", 0)) <= 0)

    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()
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
