from collections import Counter, defaultdict
import math
import tkinter as tk
from tkinter import ttk


def _column_count(item_count, max_rows, min_cols=1, max_cols=None):
    if item_count <= 0:
        cols = min_cols
    else:
        cols = max(min_cols, math.ceil(item_count / max_rows))
    if max_cols is not None:
        cols = min(cols, max_cols)
    return cols


def _configure_checkbox_grid(frame, item_count, max_rows, min_cols=1, max_cols=None):
    cols = _column_count(item_count, max_rows, min_cols=min_cols, max_cols=max_cols)
    for col in range(cols):
        frame.grid_columnconfigure(col, weight=1, uniform="filters")
    return cols


def build_exclude_tab(app):
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  2. Line Codes  ")

    ttk.Label(frame, text="Exclude Line Codes", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text="Uncheck any line codes you want to exclude from PO generation. Checked codes will be included.",
        style="SubHeader.TLabel",
        wraplength=800,
    ).pack(anchor="w", pady=(2, 12))

    toolbar = ttk.Frame(frame)
    toolbar.pack(fill=tk.X, pady=(0, 8))
    button_row = ttk.Frame(toolbar)
    button_row.pack(anchor="w")
    ttk.Button(button_row, text="Select All", command=lambda: app._toggle_all_lc(True)).pack(side=tk.LEFT, padx=4)
    ttk.Button(button_row, text="Deselect All", command=lambda: app._toggle_all_lc(False)).pack(side=tk.LEFT, padx=4)

    app.lbl_lc_count = ttk.Label(toolbar, text="", style="Info.TLabel")
    app.lbl_lc_count.pack(anchor="w", padx=8, pady=(6, 0))

    container = ttk.Frame(frame)
    container.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(container, highlightthickness=0, bg="#1e1e2e")
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    app.lc_inner_frame = ttk.Frame(canvas)

    app.lc_inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=app.lc_inner_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_mousewheel(event):
        if canvas.winfo_exists():
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    app.lc_vars = {}

    ttk.Button(frame, text="Continue ->", style="Big.TButton", command=app._do_exclude).pack(anchor="e", pady=12)


def populate_exclude_tab(app):
    for widget in app.lc_inner_frame.winfo_children():
        widget.destroy()
    app.lc_vars.clear()

    lc_counts = defaultdict(int)
    for item in app.sales_items:
        lc_counts[item["line_code"]] += 1

    cols = _configure_checkbox_grid(app.lc_inner_frame, len(app.all_line_codes), max_rows=18, min_cols=4)
    for i, line_code in enumerate(app.all_line_codes):
        var = tk.BooleanVar(value=True)
        app.lc_vars[line_code] = var
        text = f"{line_code}  ({lc_counts.get(line_code, 0)})"
        checkbox = ttk.Checkbutton(app.lc_inner_frame, text=text, variable=var, command=app._update_lc_count)
        checkbox.grid(row=i // cols, column=i % cols, sticky="w", padx=8, pady=2)

    update_lc_count(app)


def update_lc_count(app):
    included = sum(1 for var in app.lc_vars.values() if var.get())
    total = len(app.lc_vars)
    app.lbl_lc_count.config(text=f"{included} of {total} line codes included")


def build_customer_tab(app):
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  3. Customers  ")

    ttk.Label(frame, text="Exclude Customers", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text=(
            "Uncheck customers whose suspended items should be ignored when ordering. "
            "For example, CASH customers don't take items until paid - no need to reorder for them."
        ),
        style="SubHeader.TLabel",
        wraplength=800,
    ).pack(anchor="w", pady=(2, 12))

    toolbar = ttk.Frame(frame)
    toolbar.pack(fill=tk.X, pady=(0, 8))
    button_row = ttk.Frame(toolbar)
    button_row.pack(anchor="w")
    ttk.Button(button_row, text="Select All", command=lambda: app._toggle_all_cust(True)).pack(side=tk.LEFT, padx=4)
    ttk.Button(button_row, text="Deselect All", command=lambda: app._toggle_all_cust(False)).pack(side=tk.LEFT, padx=4)

    app.lbl_cust_count = ttk.Label(toolbar, text="", style="Info.TLabel")
    app.lbl_cust_count.pack(anchor="w", padx=8, pady=(6, 0))

    container = ttk.Frame(frame)
    container.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(container, highlightthickness=0, bg="#1e1e2e")
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    app.cust_inner_frame = ttk.Frame(canvas)

    app.cust_inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=app.cust_inner_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_mousewheel(event):
        if canvas.winfo_exists():
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    app.cust_vars = {}

    ttk.Button(
        frame, text="Continue to Vendor Assignment ->", style="Big.TButton", command=app._do_customer_exclude
    ).pack(anchor="e", pady=12)


def populate_customer_tab(app):
    for widget in app.cust_inner_frame.winfo_children():
        widget.destroy()
    app.cust_vars.clear()

    cust_counts = Counter()
    cust_names = {}
    for suspended_item in app.suspended_items:
        code = suspended_item.get("customer_code", "")
        if not code:
            continue
        cust_counts[code] += 1
        cust_names.setdefault(code, suspended_item.get("customer", ""))

    customer_codes = sorted(cust_counts.keys())
    cols = _configure_checkbox_grid(
        app.cust_inner_frame,
        len(customer_codes),
        max_rows=14,
        min_cols=1,
        max_cols=2,
    )
    for i, code in enumerate(customer_codes):
        var = tk.BooleanVar(value=True)
        app.cust_vars[code] = var
        name = cust_names.get(code, "")
        count = cust_counts[code]
        display = f"{code}  -  {name}  ({count})" if name else f"{code}  ({count})"
        checkbox = ttk.Checkbutton(
            app.cust_inner_frame,
            text=display,
            variable=var,
            command=app._update_cust_count,
            width=42,
        )
        checkbox.grid(row=i // cols, column=i % cols, sticky="nw", padx=8, pady=2)

    update_cust_count(app)


def update_cust_count(app):
    included = sum(1 for var in app.cust_vars.values() if var.get())
    total = len(app.cust_vars)
    excluded = total - included
    app.lbl_cust_count.config(text=f"{included} of {total} customers included ({excluded} excluded)")
