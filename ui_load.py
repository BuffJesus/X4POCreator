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

    ttk.Label(content, text="Load Data Files", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        content,
        text="Point to a folder of X4 report CSVs to auto-detect, or select files individually below.",
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", pady=(2, 12))

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

    app.var_check_updates = tk.BooleanVar(value=app.update_check_enabled)
    ttk.Checkbutton(
        data_frame,
        text="Check GitHub for new releases on startup",
        variable=app.var_check_updates,
        command=app._set_update_check_enabled,
    ).pack(anchor="w", pady=(8, 0))
    app._refresh_data_folder_labels()

    scan_frame = ttk.LabelFrame(content, text="Auto-Detect from Folder", padding=10)
    scan_frame.pack(fill=tk.X, pady=(0, 8))

    scan_row = ttk.Frame(scan_frame)
    scan_row.pack(fill=tk.X)
    app.var_scan_dir = tk.StringVar()
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
