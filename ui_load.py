import tkinter as tk
from tkinter import ttk

from ui_scroll import attach_vertical_mousewheel, sync_canvas_window


LOAD_FILE_SECTIONS = (
    {
        "title": "Core Files",
        "summary": "Preferred daily workflow. These files should cover the main assignment and reorder path.",
        "rows": (
            {
                "label": "Detailed Part Sales CSV",
                "attr_name": "var_detailed_sales_path",
                "browse_key": "detailedsales",
                "hint": "Preferred sales source. Use with Received Parts Detail.",
            },
            {
                "label": "Received Parts Detail CSV",
                "attr_name": "var_received_parts_path",
                "browse_key": "receivedparts",
                "hint": "Preferred receiving source. Use with Detailed Part Sales.",
            },
            {
                "label": "On Hand Min/Max Sales CSV",
                "attr_name": "var_minmax_path",
                "browse_key": "minmax",
                "hint": "Primary inventory/min-max source for reorder decisions.",
            },
            {
                "label": "Order Multiples / Pack Sizes CSV",
                "attr_name": "var_packsize_path",
                "browse_key": "packsize",
                "hint": "Pack-size source for ordering behavior.",
            },
        ),
    },
    {
        "title": "Optional Support Files",
        "summary": "Useful when available, but not required to load the core workflow.",
        "rows": (
            {
                "label": "On Hand Report CSV",
                "attr_name": "var_onhand_path",
                "browse_key": "onhand",
                "hint": "Adds inventory cost/QOH coverage where needed.",
            },
            {
                "label": "Open PO Listing CSV",
                "attr_name": "var_po_path",
                "browse_key": "po",
                "hint": "Adds open-PO protection and review context.",
            },
            {
                "label": "Suspended Items CSV",
                "attr_name": "var_susp_path",
                "browse_key": "susp",
                "hint": "Adds suspense demand and review context.",
            },
        ),
    },
)


def iter_load_file_rows():
    for section in LOAD_FILE_SECTIONS:
        for row in section["rows"]:
            yield row


def ensure_load_file_vars(app, *, var_factory=tk.StringVar):
    created = {}
    for row in iter_load_file_rows():
        attr_name = row["attr_name"]
        variable = getattr(app, attr_name, None)
        if variable is None:
            variable = var_factory()
            setattr(app, attr_name, variable)
        created[attr_name] = variable
    return created


def load_file_sections():
    return LOAD_FILE_SECTIONS


def refresh_load_file_sections(app):
    host = getattr(app, "_load_sections_host", None)
    if host is None:
        return
    for child in host.winfo_children():
        child.destroy()
    next_row = 0
    for section in LOAD_FILE_SECTIONS:
        next_row = _add_file_section(app, host, start_row=next_row, section=section)
    host.columnconfigure(1, weight=1)


def build_load_tab(app):
    ensure_load_file_vars(app)
    frame = ttk.Frame(app.notebook, padding=0)
    app.notebook.add(frame, text="  1. Load Files  ")

    canvas = tk.Canvas(frame, highlightthickness=0, bg="#1e1e2e")
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    content = ttk.Frame(canvas, padding=16)

    def _sync_scrollregion(_event=None):
        sync_canvas_window(canvas, content_window)

    def _resize_window(_event):
        sync_canvas_window(canvas, content_window, width=_event.width)

    content.bind("<Configure>", _sync_scrollregion)
    content_window = canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind("<Configure>", _resize_window)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    attach_vertical_mousewheel(canvas, canvas, content)

    # ── Welcome hero section ──
    hero = ttk.Frame(content)
    hero.pack(fill=tk.X, pady=(0, 16))
    tk.Label(
        hero, text="PO Builder",
        font=("Segoe UI", 22, "bold"), bg="#222222", fg="#4c9be8",
        anchor="w",
    ).pack(anchor="w")
    tk.Label(
        hero, text="Generate vendor purchase orders from X4 report exports",
        font=("Segoe UI", 11), bg="#222222", fg="#8898a8",
        anchor="w",
    ).pack(anchor="w", pady=(2, 0))
    ttk.Separator(hero, orient="horizontal").pack(fill=tk.X, pady=(12, 0))

    data_frame = ttk.LabelFrame(content, text="Shared Data Folder", padding=10)
    data_frame.pack(fill=tk.X, pady=(0, 8))

    app.lbl_data_source = ttk.Label(data_frame, text="", style="Info.TLabel")
    app.lbl_data_source.pack(anchor="w")

    data_button_row = ttk.Frame(data_frame)
    data_button_row.pack(anchor="w", pady=(8, 0))
    ttk.Button(data_button_row, text="Set Shared Folder...", command=app._set_shared_data_folder).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(data_button_row, text="Use Local Data", command=app._use_local_data_folder).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(data_button_row, text="Refresh Active Data", command=app._refresh_active_data_state).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(data_button_row, text="Open Active Folder", command=app._open_active_data_folder).pack(side=tk.LEFT)

    update_row = ttk.Frame(data_frame)
    update_row.pack(anchor="w", pady=(8, 0))
    app.var_check_updates = tk.BooleanVar(value=app.update_check_enabled)
    ttk.Checkbutton(
        update_row,
        text="Check GitHub for new releases on startup",
        variable=app.var_check_updates,
        command=app._set_update_check_enabled,
    ).pack(side=tk.LEFT)
    ttk.Button(update_row, text="Check Now", command=app._check_for_updates_now).pack(
        side=tk.LEFT, padx=(12, 0)
    )
    app._refresh_data_folder_labels()

    # ── Quick Load (one-click reload from last folder) ──
    last_folder = app.app_settings.get("last_scan_folder", "") if hasattr(app, "app_settings") else ""
    if last_folder:
        quick_frame = tk.Frame(content, bg="#1a2a3a", padx=16, pady=14, relief="ridge", bd=1)
        quick_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            quick_frame, text="Quick Start",
            font=("Segoe UI", 13, "bold"), bg="#1a2a3a", fg="#4c9be8",
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            quick_frame, text=f"Load from: {last_folder}",
            font=("Segoe UI", 9), bg="#1a2a3a", fg="#7898b0",
            anchor="w",
        ).pack(anchor="w", pady=(4, 8))

        def _quick_load():
            app.var_scan_dir.set(last_folder)
            app._scan_folder()
            app.root.after(200, app._do_load)

        ttk.Button(
            quick_frame, text="  Scan & Load Now  ",
            style="Big.TButton", command=_quick_load,
        ).pack(anchor="w")

    scan_frame = ttk.LabelFrame(content, text="Auto-Detect from Folder", padding=10)
    scan_frame.pack(fill=tk.X, pady=(0, 8))

    scan_row = ttk.Frame(scan_frame)
    scan_row.pack(fill=tk.X)
    app.var_scan_dir = tk.StringVar(value=last_folder)
    ttk.Entry(scan_row, textvariable=app.var_scan_dir, width=65).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

    scan_button_row = ttk.Frame(scan_frame)
    scan_button_row.pack(anchor="w", pady=(8, 0))
    ttk.Button(scan_button_row, text="Browse Folder...", command=app._browse_folder).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(scan_button_row, text="Scan & Populate", style="Big.TButton", command=app._scan_folder).pack(side=tk.LEFT)

    app.lbl_scan_status = ttk.Label(scan_frame, text="", style="Info.TLabel")
    app.lbl_scan_status.pack(anchor="w", pady=(6, 0))

    file_frame = ttk.LabelFrame(content, text="Input Files", padding=12)
    file_frame.pack(fill=tk.X, pady=4)

    ttk.Label(
        file_frame,
        text="Use the core files first. Optional files add context.",
        style="Info.TLabel",
        wraplength=900,
    ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 8))

    app._load_sections_host = ttk.Frame(file_frame)
    app._load_sections_host.grid(row=1, column=0, columnspan=3, sticky="ew")
    refresh_load_file_sections(app)

    file_frame.columnconfigure(1, weight=1)

    app.lbl_load_status = ttk.Label(content, text="", style="Info.TLabel")
    app.lbl_load_status.pack(anchor="w", pady=(12, 0))

    app._data_quality_frame = ttk.LabelFrame(content, text="Data Quality", padding=10)
    app._data_quality_frame.pack(fill=tk.X, pady=(8, 0))
    app._data_quality_frame.pack_forget()  # hidden until a load completes

    app._dq_lbl_total = ttk.Label(app._data_quality_frame, text="", style="Info.TLabel")
    app._dq_lbl_total.grid(row=0, column=0, sticky="w")
    app._dq_lbl_coverage = ttk.Label(app._data_quality_frame, text="", style="Info.TLabel")
    app._dq_lbl_coverage.grid(row=1, column=0, sticky="w")
    app._dq_lbl_unresolved = ttk.Label(app._data_quality_frame, text="", style="Info.TLabel")
    app._dq_lbl_unresolved.grid(row=2, column=0, sticky="w")
    app._dq_lbl_missing_sale = ttk.Label(app._data_quality_frame, text="", style="Info.TLabel")
    app._dq_lbl_missing_sale.grid(row=3, column=0, sticky="w")
    app._dq_lbl_missing_receipt = ttk.Label(app._data_quality_frame, text="", style="Info.TLabel")
    app._dq_lbl_missing_receipt.grid(row=4, column=0, sticky="w")
    app._dq_lbl_conflicts = ttk.Label(app._data_quality_frame, text="", style="Info.TLabel")
    app._dq_lbl_conflicts.grid(row=5, column=0, sticky="w")
    app._dq_lbl_score = ttk.Label(app._data_quality_frame, text="", style="Info.TLabel")
    app._dq_lbl_score.grid(row=6, column=0, sticky="w", pady=(6, 0))

    footer = ttk.Frame(content)
    footer.pack(fill=tk.X, pady=(12, 0))
    footer.columnconfigure(1, weight=1)
    app.btn_export_startup_warnings = ttk.Button(
        footer,
        text="Export Startup Warnings CSV",
        command=app._export_startup_warnings_csv,
        state="disabled",
    )
    app.btn_export_startup_warnings.grid(row=0, column=0, sticky="w")
    app.btn_export_dq_report = ttk.Button(
        footer,
        text="Export Data Quality Report",
        command=app._export_data_quality_report_csv,
        state="disabled",
    )
    app.btn_export_dq_report.grid(row=1, column=0, sticky="w", pady=(4, 0))
    ttk.Button(footer, text="View Session History", command=app._open_session_history).grid(
        row=2, column=0, sticky="w", pady=(4, 0)
    )
    ttk.Button(footer, text="Session Diff...", command=app._open_session_diff).grid(
        row=3, column=0, sticky="w", pady=(4, 0)
    )
    ttk.Button(footer, text="Load Files & Continue ->", style="Big.TButton", command=app._do_load).grid(
        row=0, column=2, sticky="e"
    )


def refresh_data_quality_card(app, summary):
    """
    Populate and show the data quality card with the provided summary dict.
    summary is the dict returned by load_flow.compute_data_quality_summary().
    """
    frame = getattr(app, "_data_quality_frame", None)
    if frame is None:
        return

    total = summary.get("total_items", 0)
    covered = summary.get("inventory_covered", 0)
    unresolved = summary.get("unresolved_item_codes", 0)
    missing_sale = summary.get("missing_last_sale", 0)
    missing_receipt = summary.get("missing_last_receipt", 0)
    conflicts = summary.get("conflicting_items", 0)
    score = summary.get("quality_score", 1.0)
    gate = summary.get("gate_required", False)

    app._dq_lbl_total.config(text=f"Items loaded: {total}")
    app._dq_lbl_coverage.config(
        text=f"Inventory coverage: {covered} of {total} items ({100*covered//max(total,1)}%)"
    )
    unresolved_text = (
        f"Unresolved detailed-sales item codes: {unresolved}"
        if unresolved == 0
        else f"Unresolved detailed-sales item codes: {unresolved}  ← check X4 line-code mapping"
    )
    app._dq_lbl_unresolved.config(text=unresolved_text)
    app._dq_lbl_missing_sale.config(
        text=f"Items with no last-sale date: {missing_sale}"
    )
    app._dq_lbl_missing_receipt.config(
        text=f"Items with no last-receipt date: {missing_receipt}"
    )
    app._dq_lbl_conflicts.config(
        text=f"Detailed-sales vs X4 signal conflicts: {conflicts}"
    )
    score_pct = int(score * 100)
    gate_note = "  ← acknowledgment required before assignment" if gate else ""
    app._dq_lbl_score.config(
        text=f"Quality score: {score_pct}%{gate_note}"
    )

    frame.pack(fill=tk.X, pady=(8, 0))

    # Enable the Export DQ Report button when any flags are present.
    has_flags = unresolved > 0 or missing_sale > 0 or missing_receipt > 0 or conflicts > 0
    btn_dq = getattr(app, "btn_export_dq_report", None)
    if btn_dq is not None:
        btn_dq.config(state="normal" if has_flags else "disabled")


def _add_file_row(app, parent, row, label, attr_name, browse_key, hint):
    base_row = row * 2
    ttk.Label(parent, text=label).grid(row=base_row, column=0, sticky="w", padx=4, pady=(4, 2))
    variable = getattr(app, attr_name, None)
    if variable is None:
        variable = tk.StringVar()
        setattr(app, attr_name, variable)
    ttk.Entry(parent, textvariable=variable, width=60).grid(row=base_row, column=1, padx=4, pady=(4, 2), sticky="ew")
    ttk.Button(parent, text="Browse...", command=lambda: app._browse(browse_key)).grid(row=base_row, column=2, padx=4, pady=(4, 2))
    ttk.Label(parent, text=hint, style="Path.TLabel").grid(
        row=base_row + 1, column=1, columnspan=2, sticky="w", padx=4, pady=(0, 4)
    )


def _add_file_section(app, parent, *, start_row, section):
    section_row = start_row * 2
    ttk.Label(parent, text=section["title"], style="Header.TLabel").grid(
        row=section_row, column=0, columnspan=3, sticky="w", padx=4, pady=(8, 2)
    )
    ttk.Label(parent, text=section["summary"], style="Info.TLabel", wraplength=900).grid(
        row=section_row + 1, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 6)
    )
    next_row = start_row + 1
    for row in section["rows"]:
        _add_file_row(
            app,
            parent,
            row=next_row,
            label=row["label"],
            attr_name=row["attr_name"],
            browse_key=row["browse_key"],
            hint=row["hint"],
        )
        next_row += 1
    return next_row
