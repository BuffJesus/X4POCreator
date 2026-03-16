import tkinter as tk
from tkinter import ttk

from ui_scroll import attach_vertical_mousewheel, sync_canvas_window


def build_load_tab(app):
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
        text="Load either the legacy combined Part Sales & Receipts report, or the Detailed Part Sales + Received Parts Detail pair.",
        style="Info.TLabel",
        wraplength=900,
    ).grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 8))

    _add_file_row(
        app,
        file_frame,
        row=1,
        label="Order Multiples / Pack Sizes CSV",
        attr_name="var_packsize_path",
        browse_key="packsize",
        hint="Standard -> Inventory -> Items With Order Multiple",
    )
    _add_file_row(
        app,
        file_frame,
        row=2,
        label="On Hand Min/Max Sales CSV",
        attr_name="var_minmax_path",
        browse_key="minmax",
        hint="Standard -> Inventory -> On Hand Min Max Sales",
    )
    _add_file_row(
        app,
        file_frame,
        row=3,
        label="On Hand Report CSV",
        attr_name="var_onhand_path",
        browse_key="onhand",
        hint="Standard -> Inventory -> On Hand Report",
    )
    _add_file_row(
        app,
        file_frame,
        row=4,
        label="Open PO Listing CSV",
        attr_name="var_po_path",
        browse_key="po",
        hint="Standard -> Purchase Order -> POs by PG",
    )
    _add_file_row(
        app,
        file_frame,
        row=5,
        label="Part Sales & Receipts CSV",
        attr_name="var_sales_path",
        browse_key="sales",
        hint="Standard -> Sales -> Part Sales & Receipts",
    )
    _add_file_row(
        app,
        file_frame,
        row=6,
        label="Detailed Part Sales CSV",
        attr_name="var_detailed_sales_path",
        browse_key="detailedsales",
        hint="Detailed sales export used with Received Parts Detail",
    )
    _add_file_row(
        app,
        file_frame,
        row=7,
        label="Received Parts Detail CSV",
        attr_name="var_received_parts_path",
        browse_key="receivedparts",
        hint="Receiving detail export used with Detailed Part Sales",
    )
    _add_file_row(
        app,
        file_frame,
        row=8,
        label="Suspended Items CSV",
        attr_name="var_susp_path",
        browse_key="susp",
        hint="Standard -> Sales -> Suspended Items",
    )

    file_frame.columnconfigure(1, weight=1)

    app.lbl_load_status = ttk.Label(content, text="", style="Info.TLabel")
    app.lbl_load_status.pack(anchor="w", pady=(12, 0))

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


def _add_file_row(app, parent, row, label, attr_name, browse_key, hint):
    base_row = row * 2
    ttk.Label(parent, text=label).grid(row=base_row, column=0, sticky="w", padx=4, pady=(4, 2))
    variable = tk.StringVar()
    setattr(app, attr_name, variable)
    ttk.Entry(parent, textvariable=variable, width=60).grid(row=base_row, column=1, padx=4, pady=(4, 2), sticky="ew")
    ttk.Button(parent, text="Browse...", command=lambda: app._browse(browse_key)).grid(row=base_row, column=2, padx=4, pady=(4, 2))
    ttk.Label(parent, text=hint, style="Path.TLabel").grid(
        row=base_row + 1, column=1, columnspan=2, sticky="w", padx=4, pady=(0, 4)
    )
