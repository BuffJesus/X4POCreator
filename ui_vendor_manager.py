import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import shipping_flow


def vendor_policy_field_visibility(policy_name, *, advanced=False):
    policy = str(policy_name or "").strip() or "release_immediately"
    supports_weekdays = policy in ("hold_for_free_day", "hybrid_free_day_threshold")
    supports_threshold = policy in ("hold_for_threshold", "hybrid_free_day_threshold")
    supports_lead_days = supports_weekdays and advanced
    return {
        "weekdays": supports_weekdays,
        "threshold": supports_threshold,
        "urgent_floor": advanced,
        "urgent_mode": advanced,
        "lead_days": supports_lead_days,
    }


def should_expand_vendor_policy_advanced(policy):
    normalized = shipping_flow.normalize_vendor_policy(policy or {})
    if normalized.get("urgent_release_floor", 0) > 0:
        return True
    if normalized.get("urgent_release_mode", "release_now") != "release_now":
        return True
    if normalized.get("shipping_policy") in ("hold_for_free_day", "hybrid_free_day_threshold"):
        if int(normalized.get("release_lead_business_days", 1) or 1) != 1:
            return True
    return False


def apply_vendor_policy_preset(app, vendor, preset_name):
    preset = shipping_flow.get_vendor_policy_preset(preset_name)
    if not preset or not preset.get("label"):
        return False
    return apply_vendor_policy_changes(
        app,
        vendor,
        shipping_policy=preset.get("shipping_policy", "release_immediately"),
        weekdays=", ".join(preset.get("preferred_free_ship_weekdays", [])),
        threshold=preset.get("free_freight_threshold", 0.0),
        urgent_floor=preset.get("urgent_release_floor", 0.0),
        urgent_mode=preset.get("urgent_release_mode", "release_now"),
        release_lead_days=preset.get("release_lead_business_days", 1),
    )


def apply_vendor_policy_changes(app, vendor, *, shipping_policy, weekdays, threshold, urgent_floor, urgent_mode="release_now", release_lead_days=1):
    normalized_vendor = app._normalize_vendor_code(vendor)
    if not normalized_vendor:
        return False
    normalized_policy = shipping_flow.normalize_vendor_policy({
        "shipping_policy": shipping_policy,
        "preferred_free_ship_weekdays": weekdays,
        "free_freight_threshold": threshold,
        "urgent_release_floor": urgent_floor,
        "urgent_release_mode": urgent_mode,
        "release_lead_business_days": release_lead_days,
    })
    has_meaningful_values = any((
        normalized_policy.get("shipping_policy", "release_immediately") != "release_immediately",
        normalized_policy.get("preferred_free_ship_weekdays"),
        normalized_policy.get("free_freight_threshold", 0) > 0,
        normalized_policy.get("urgent_release_floor", 0) > 0,
        normalized_policy.get("urgent_release_mode", "release_now") != "release_now",
        normalized_policy.get("release_lead_business_days", 1) != 1,
    ))
    if has_meaningful_values:
        app.vendor_policies[normalized_vendor] = normalized_policy
    else:
        app.vendor_policies.pop(normalized_vendor, None)
    app._save_vendor_policies()
    if hasattr(app, "_annotate_release_decisions"):
        app._annotate_release_decisions()
    if hasattr(app, "_apply_bulk_filter"):
        app._apply_bulk_filter()
    if hasattr(app, "_update_bulk_summary"):
        app._update_bulk_summary()
    if hasattr(app, "_populate_review_tab") and hasattr(app, "tree"):
        app._populate_review_tab()
    return True


def open_vendor_policy_editor(app, vendor, parent):
    normalized_vendor = app._normalize_vendor_code(vendor)
    if not normalized_vendor:
        return
    saved_policy = app.vendor_policies.get(normalized_vendor, {})
    policy = shipping_flow.normalize_vendor_policy(saved_policy)
    default_preset_name = ""
    get_default_preset = getattr(app, "_get_default_vendor_policy_preset", None)
    if callable(get_default_preset):
        default_preset_name = get_default_preset()
    default_preset = shipping_flow.get_vendor_policy_preset(default_preset_name) if default_preset_name else {}
    if not saved_policy and default_preset.get("label"):
        policy = shipping_flow.normalize_vendor_policy(default_preset)

    dlg = tk.Toplevel(parent)
    dlg.title(f"Shipping Policy - {normalized_vendor}")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(parent)
    dlg.grab_set()

    ttk.Label(dlg, text=f"Shipping Policy: {normalized_vendor}", style="Header.TLabel").pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text="Configure release timing for this vendor. Leave everything blank/default to clear the saved policy.",
        style="SubHeader.TLabel",
        wraplength=620,
    ).pack(anchor="w", padx=16, pady=(0, 10))

    grid = ttk.Frame(dlg)
    grid.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
    grid.columnconfigure(1, weight=1)

    var_policy = tk.StringVar(value=policy.get("shipping_policy", "release_immediately"))
    var_weekdays = tk.StringVar(value=", ".join(policy.get("preferred_free_ship_weekdays", [])))
    var_threshold = tk.StringVar(
        value=str(int(policy["free_freight_threshold"])) if float(policy.get("free_freight_threshold", 0) or 0).is_integer() and policy.get("free_freight_threshold", 0) else (str(policy.get("free_freight_threshold", "")) if policy.get("free_freight_threshold", 0) else "")
    )
    var_urgent = tk.StringVar(
        value=str(int(policy["urgent_release_floor"])) if float(policy.get("urgent_release_floor", 0) or 0).is_integer() and policy.get("urgent_release_floor", 0) else (str(policy.get("urgent_release_floor", "")) if policy.get("urgent_release_floor", 0) else "")
    )
    var_urgent_mode = tk.StringVar(value=policy.get("urgent_release_mode", "release_now"))
    var_lead_days = tk.StringVar(value=str(int(policy.get("release_lead_business_days", 1) or 1)))
    var_show_advanced = tk.BooleanVar(value=should_expand_vendor_policy_advanced(policy))
    preset_options = shipping_flow.vendor_policy_preset_options()
    preset_by_label = {label: key for key, label in preset_options}
    var_preset = tk.StringVar(value=default_preset.get("label", "") if not saved_policy else "")
    widgets = {
        "preset": (
            ttk.Label(grid, text="Preset"),
            ttk.Combobox(grid, textvariable=var_preset, state="readonly", values=[""] + [label for _, label in preset_options], width=28),
        ),
        "policy": (
            ttk.Label(grid, text="Policy"),
            ttk.Combobox(grid, textvariable=var_policy, state="readonly", values=[
                "release_immediately",
                "hold_for_free_day",
                "hold_for_threshold",
                "hybrid_free_day_threshold",
            ], width=28),
        ),
        "weekdays": (
            ttk.Label(grid, text="Free-Ship Days"),
            ttk.Entry(grid, textvariable=var_weekdays, width=36),
        ),
        "threshold": (
            ttk.Label(grid, text="Freight Threshold"),
            ttk.Entry(grid, textvariable=var_threshold, width=20),
        ),
        "urgent_floor": (
            ttk.Label(grid, text="Urgent Floor"),
            ttk.Entry(grid, textvariable=var_urgent, width=20),
        ),
        "urgent_mode": (
            ttk.Label(grid, text="Urgent Override"),
            ttk.Combobox(grid, textvariable=var_urgent_mode, state="readonly", values=[
                "release_now",
                "paid_urgent_freight",
            ], width=28),
        ),
        "lead_days": (
            ttk.Label(grid, text="Lead Days"),
            ttk.Entry(grid, textvariable=var_lead_days, width=20),
        ),
    }
    advanced_toggle = ttk.Checkbutton(
        grid,
        text="Show Advanced",
        variable=var_show_advanced,
    )
    helper_label = ttk.Label(
        grid,
        text=(
            "Common path: choose a preset or set Policy plus the matching day/threshold field. "
            "Use Advanced only for urgent overrides or custom lead days."
        ),
        style="SubHeader.TLabel",
        wraplength=620,
    )
    default_label = None
    if not saved_policy and default_preset.get("label"):
        default_label = ttk.Label(
            grid,
            text=f"No saved vendor-specific policy yet. Prefilled from default preset: {default_preset['label']}.",
            style="Info.TLabel",
            wraplength=620,
        )

    def _place_row(row_idx, field_key):
        label, widget = widgets[field_key]
        label.grid(row=row_idx, column=0, sticky="w", padx=(0, 8), pady=4)
        widget.grid(row=row_idx, column=1, sticky="ew", pady=4)

    def _refresh_layout(*_args):
        for label, widget in widgets.values():
            label.grid_remove()
            widget.grid_remove()
        advanced_toggle.grid_remove()
        helper_label.grid_remove()
        if default_label is not None:
            default_label.grid_remove()

        row_idx = 0
        _place_row(row_idx, "preset")
        row_idx += 1
        _place_row(row_idx, "policy")
        row_idx += 1

        advanced_toggle.grid(row=row_idx, column=0, columnspan=2, sticky="w", pady=(2, 4))
        row_idx += 1

        visibility = vendor_policy_field_visibility(var_policy.get(), advanced=var_show_advanced.get())
        for field_key in ("weekdays", "threshold", "urgent_floor", "urgent_mode", "lead_days"):
            if visibility.get(field_key):
                _place_row(row_idx, field_key)
                row_idx += 1

        helper_label.grid(row=row_idx, column=0, columnspan=2, sticky="w", pady=(6, 0))
        row_idx += 1
        if default_label is not None:
            default_label.grid(row=row_idx, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _apply_preset():
        preset_name = preset_by_label.get(var_preset.get().strip(), "")
        preset = shipping_flow.get_vendor_policy_preset(preset_name)
        if not preset:
            return
        var_policy.set(preset.get("shipping_policy", "release_immediately"))
        var_weekdays.set(", ".join(preset.get("preferred_free_ship_weekdays", [])))
        threshold = preset.get("free_freight_threshold", 0.0)
        urgent_floor = preset.get("urgent_release_floor", 0.0)
        urgent_mode = preset.get("urgent_release_mode", "release_now")
        lead_days = int(preset.get("release_lead_business_days", 1) or 1)
        var_threshold.set("" if not threshold else (str(int(threshold)) if float(threshold).is_integer() else str(threshold)))
        var_urgent.set("" if not urgent_floor else (str(int(urgent_floor)) if float(urgent_floor).is_integer() else str(urgent_floor)))
        var_urgent_mode.set(urgent_mode)
        var_lead_days.set(str(lead_days))
        var_show_advanced.set(should_expand_vendor_policy_advanced(preset))
        _refresh_layout()

    def _save():
        apply_vendor_policy_changes(
            app,
            normalized_vendor,
            shipping_policy=var_policy.get().strip(),
            weekdays=var_weekdays.get().strip(),
            threshold=var_threshold.get().strip(),
            urgent_floor=var_urgent.get().strip(),
            urgent_mode=var_urgent_mode.get().strip(),
            release_lead_days=var_lead_days.get().strip(),
        )
        dlg.destroy()

    def _clear():
        var_policy.set("release_immediately")
        var_weekdays.set("")
        var_threshold.set("")
        var_urgent.set("")
        var_urgent_mode.set("release_now")
        var_lead_days.set("1")
        var_show_advanced.set(False)
        _refresh_layout()

    widgets["policy"][1].bind("<<ComboboxSelected>>", _refresh_layout)
    advanced_toggle.configure(command=_refresh_layout)
    _refresh_layout()

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    ttk.Button(btn_frame, text="Apply Preset", command=_apply_preset).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Clear Policy", command=_clear).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Save Policy", command=_save).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    app._autosize_dialog(dlg, min_w=520, min_h=300, max_w_ratio=0.7, max_h_ratio=0.7)
    dlg.wait_window()


def open_vendor_manager(app):
    dlg = tk.Toplevel(app.root)
    dlg.title("Vendor Manager")
    dlg.configure(bg="#1e1e2e")
    dlg.transient(app.root)
    dlg.grab_set()

    ttk.Label(dlg, text="Vendor Manager", style="Header.TLabel").pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        dlg,
        text=(
            "Add, rename, or remove vendor codes used by the app. "
            "Renaming a vendor also updates matching vendor assignments in the current session."
        ),
        style="SubHeader.TLabel",
        wraplength=680,
    ).pack(anchor="w", padx=16, pady=(0, 10))

    list_frame = ttk.Frame(dlg)
    list_frame.pack(fill=tk.BOTH, expand=True, padx=16)

    vendor_list = tk.Listbox(
        list_frame,
        activestyle="none",
        exportselection=False,
        width=36,
        height=18,
        bg="#1f2330",
        fg="#f4f4f6",
        selectbackground="#5b4cc4",
        selectforeground="#ffffff",
        relief="flat",
        highlightthickness=0,
    )
    vendor_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=vendor_list.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    vendor_list.configure(yscrollcommand=scrollbar.set)

    def _refresh(selected_code=None):
        current = selected_code
        if current is None:
            selection = vendor_list.curselection()
            if selection:
                current = vendor_list.get(selection[0])
        vendor_list.delete(0, tk.END)
        for code in app.vendor_codes_used:
            vendor_list.insert(tk.END, code)
        if current:
            try:
                idx = app.vendor_codes_used.index(current)
            except ValueError:
                idx = None
            if idx is not None:
                vendor_list.selection_set(idx)
                vendor_list.see(idx)

    def _selected_vendor():
        selection = vendor_list.curselection()
        if not selection:
            return ""
        return vendor_list.get(selection[0])

    def _add():
        value = simpledialog.askstring("Add Vendor", "Enter the new vendor code:", parent=dlg)
        if value is None:
            return
        normalized = app._remember_vendor_code(value)
        if not normalized:
            messagebox.showinfo("Invalid Vendor", "Enter a vendor code before saving.", parent=dlg)
            return
        _refresh(normalized)

    def _edit():
        current = _selected_vendor()
        if not current:
            messagebox.showinfo("Select Vendor", "Select a vendor to rename first.", parent=dlg)
            return
        value = simpledialog.askstring("Rename Vendor", "Enter the updated vendor code:", initialvalue=current, parent=dlg)
        if value is None:
            return
        renamed = app._rename_vendor_code(current, value)
        if not renamed:
            messagebox.showinfo("Invalid Vendor", "Enter a vendor code before saving.", parent=dlg)
            return
        _refresh(renamed)

    def _remove():
        current = _selected_vendor()
        if not current:
            messagebox.showinfo("Select Vendor", "Select a vendor to remove first.", parent=dlg)
            return
        if not messagebox.askyesno(
            "Remove Vendor",
            (
                f"Remove vendor '{current}' from the saved vendor list?\n\n"
                "This does not clear existing vendor assignments already on rows."
            ),
            parent=dlg,
        ):
            return
        app._remove_vendor_code(current)
        _refresh()

    def _edit_policy():
        current = _selected_vendor()
        if not current:
            messagebox.showinfo("Select Vendor", "Select a vendor to edit shipping policy first.", parent=dlg)
            return
        open_vendor_policy_editor(app, current, dlg)
        _refresh(current)

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill=tk.X, padx=16, pady=12)
    action_row = ttk.Frame(btn_frame)
    action_row.pack(anchor="w", fill=tk.X)
    ttk.Button(action_row, text="Add", command=_add).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Rename", command=_edit).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Remove", command=_remove).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="Shipping Policy...", command=_edit_policy).pack(side=tk.LEFT, padx=4)

    close_row = ttk.Frame(btn_frame)
    close_row.pack(anchor="e", fill=tk.X, pady=(8, 0))
    ttk.Button(close_row, text="Close", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    _refresh()
    app._autosize_dialog(dlg, min_w=520, min_h=420, max_w_ratio=0.75, max_h_ratio=0.8)
    dlg.wait_window()
