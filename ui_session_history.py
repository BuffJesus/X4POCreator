"""Session History Viewer dialog.

Provides open_session_history(app, sessions_dir) to browse past session
snapshots without opening JSON files manually.

Pure helper functions (_snapshot_summary, _snapshot_items,
_item_history_rows, _format_tsv) carry no tkinter dependency and are
tested independently in tests/test_session_history.py.
"""
import tkinter as tk
from tkinter import ttk

import storage


# ── Pure helpers (no tkinter) ────────────────────────────────────────────────

def _snapshot_summary(snap):
    """Return a display-ready dict for one raw snapshot dict.

    Keys: date_str (str), item_count (int), vendor_count (int), scope (str).
    """
    created_at = snap.get("created_at") or ""
    date_str = created_at[:19].replace("T", " ") if created_at else "—"

    assigned = snap.get("assigned_items") or []
    item_count = len(assigned)
    vendors = {str(item.get("vendor") or "").strip().upper() for item in assigned}
    vendors.discard("")
    vendor_count = len(vendors)

    scope = snap.get("export_scope_label") or "—"
    return {
        "date_str": date_str,
        "item_count": item_count,
        "vendor_count": vendor_count,
        "scope": scope,
    }


def _snapshot_items(snap, filter_text=""):
    """Return item rows from one snapshot, optionally filtered.

    filter_text is matched case-insensitively against item_code and vendor.
    Returns a list of dicts with keys:
        line_code, item_code, description, vendor, suggested_qty, final_qty.
    """
    assigned = snap.get("assigned_items") or []
    needle = filter_text.strip().lower()
    rows = []
    for item in assigned:
        line_code = str(item.get("line_code") or "")
        item_code = str(item.get("item_code") or "")
        description = str(item.get("description") or "")
        vendor = str(item.get("vendor") or "").strip().upper()
        suggested_qty = item.get("suggested_qty")
        final_qty = item.get("final_qty")

        if needle and needle not in item_code.lower() and needle not in vendor.lower():
            continue

        rows.append({
            "line_code": line_code,
            "item_code": item_code,
            "description": description,
            "vendor": vendor,
            "suggested_qty": int(suggested_qty) if isinstance(suggested_qty, (int, float)) and suggested_qty > 0 else "",
            "final_qty": int(final_qty) if isinstance(final_qty, (int, float)) and final_qty > 0 else "",
        })
    return rows


def _item_history_rows(snapshots, line_code, item_code):
    """Collect one item's history across all snapshots (most-recent first).

    Returns a list of dicts:
        date_str, line_code, item_code, vendor, suggested_qty, final_qty.
    Only entries where the item appears in assigned_items are included.
    """
    rows = []
    for snap in snapshots:
        created_at = snap.get("created_at") or ""
        date_str = created_at[:19].replace("T", " ") if created_at else "—"
        for item in (snap.get("assigned_items") or []):
            if (str(item.get("line_code") or "") == line_code
                    and str(item.get("item_code") or "") == item_code):
                suggested_qty = item.get("suggested_qty")
                final_qty = item.get("final_qty")
                rows.append({
                    "date_str": date_str,
                    "line_code": line_code,
                    "item_code": item_code,
                    "vendor": str(item.get("vendor") or "").strip().upper(),
                    "suggested_qty": int(suggested_qty) if isinstance(suggested_qty, (int, float)) and suggested_qty > 0 else "",
                    "final_qty": int(final_qty) if isinstance(final_qty, (int, float)) and final_qty > 0 else "",
                })
                break  # one entry per snapshot
    return rows


def _format_tsv(rows, columns):
    """Format a list of dicts as a tab-separated string with a header row.

    columns is a list of (key, header_label) pairs.
    """
    lines = ["\t".join(label for _, label in columns)]
    for row in rows:
        lines.append("\t".join(str(row.get(key, "")) for key, _ in columns))
    return "\n".join(lines)


# ── Dialog ───────────────────────────────────────────────────────────────────

_SESSION_COLS = [
    ("date_str",     "Date",    180),
    ("item_count",   "Items",    60),
    ("vendor_count", "Vendors",  65),
    ("scope",        "Scope",   200),
]

_ITEM_COLS = [
    ("line_code",     "Line Code",   90),
    ("item_code",     "Item Code",  110),
    ("description",   "Description", 220),
    ("vendor",        "Vendor",       90),
    ("suggested_qty", "Sugg Qty",     72),
    ("final_qty",     "Final Qty",    72),
]

_COPY_COLUMNS = [
    ("date_str",      "Session Date"),
    ("line_code",     "Line Code"),
    ("item_code",     "Item Code"),
    ("vendor",        "Vendor"),
    ("suggested_qty", "Suggested Qty"),
    ("final_qty",     "Final Qty"),
]

_BG = "#1e1e2e"
_TREE_BG = "#1f2330"
_TREE_FG = "#f4f4f6"
_TREE_SEL = "#5b4cc4"
_TREE_HEAD = "#2a2a3e"


def open_session_history(app, sessions_dir):
    """Open the Session History dialog.

    Loads all session snapshots from sessions_dir and presents them in a
    two-pane layout: a session list on top and item detail below.
    """
    snapshots = storage.load_session_snapshots(sessions_dir, max_count=None)

    dlg = tk.Toplevel(app.root)
    dlg.title("Session History")
    dlg.configure(bg=_BG)
    dlg.transient(app.root)
    dlg.grab_set()
    dlg.geometry("860x600")
    dlg.minsize(680, 400)

    # ── Header ────────────────────────────────────────────────────────────
    ttk.Label(dlg, text="Session History", style="Header.TLabel").pack(
        anchor="w", padx=16, pady=(16, 2)
    )
    session_count = len(snapshots)
    sub = (
        f"{session_count} session{'s' if session_count != 1 else ''} found. "
        "Select a session to browse its items. "
        "Select an item then click Copy Item History to copy its full order history."
    )
    ttk.Label(dlg, text=sub, style="SubHeader.TLabel", wraplength=820).pack(
        anchor="w", padx=16, pady=(0, 8)
    )

    # ── Session list (top pane) ───────────────────────────────────────────
    top_frame = ttk.Frame(dlg)
    top_frame.pack(fill=tk.X, padx=16, pady=(0, 4))

    sess_tree = ttk.Treeview(
        top_frame,
        columns=[c[0] for c in _SESSION_COLS],
        show="headings",
        height=5,
        selectmode="browse",
    )
    for key, label, width in _SESSION_COLS:
        sess_tree.heading(key, text=label)
        sess_tree.column(key, width=width, minwidth=50, stretch=(key == "scope"))

    sess_scrollbar = ttk.Scrollbar(top_frame, orient="vertical", command=sess_tree.yview)
    sess_tree.configure(yscrollcommand=sess_scrollbar.set)
    sess_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
    sess_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Populate session list
    _iid_to_snap = {}
    for i, snap in enumerate(snapshots):
        summary = _snapshot_summary(snap)
        iid = f"sess_{i}"
        sess_tree.insert(
            "",
            tk.END,
            iid=iid,
            values=(
                summary["date_str"],
                summary["item_count"],
                summary["vendor_count"],
                summary["scope"],
            ),
        )
        _iid_to_snap[iid] = snap

    # ── Filter bar ────────────────────────────────────────────────────────
    filter_frame = ttk.Frame(dlg)
    filter_frame.pack(fill=tk.X, padx=16, pady=(4, 4))

    ttk.Label(filter_frame, text="Filter by item code or vendor:").pack(side=tk.LEFT)
    var_filter = tk.StringVar()
    filter_entry = ttk.Entry(filter_frame, textvariable=var_filter, width=30)
    filter_entry.pack(side=tk.LEFT, padx=(6, 0))

    # ── Item detail pane (bottom) ─────────────────────────────────────────
    bottom_frame = ttk.Frame(dlg)
    bottom_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 4))

    item_tree = ttk.Treeview(
        bottom_frame,
        columns=[c[0] for c in _ITEM_COLS],
        show="headings",
        selectmode="browse",
    )
    for key, label, width in _ITEM_COLS:
        item_tree.heading(key, text=label)
        item_tree.column(
            key,
            width=width,
            minwidth=40,
            stretch=(key == "description"),
            anchor="e" if key in ("suggested_qty", "final_qty") else "w",
        )

    item_vscroll = ttk.Scrollbar(bottom_frame, orient="vertical", command=item_tree.yview)
    item_hscroll = ttk.Scrollbar(bottom_frame, orient="horizontal", command=item_tree.xview)
    item_tree.configure(yscrollcommand=item_vscroll.set, xscrollcommand=item_hscroll.set)
    item_tree.grid(row=0, column=0, sticky="nsew")
    item_vscroll.grid(row=0, column=1, sticky="ns")
    item_hscroll.grid(row=1, column=0, sticky="ew")
    bottom_frame.rowconfigure(0, weight=1)
    bottom_frame.columnconfigure(0, weight=1)

    # ── Footer buttons ────────────────────────────────────────────────────
    footer = ttk.Frame(dlg)
    footer.pack(fill=tk.X, padx=16, pady=(4, 12))

    btn_copy = ttk.Button(footer, text="Copy Item History", command=lambda: _copy_item_history())
    btn_copy.pack(side=tk.LEFT)

    ttk.Label(footer, text="(copies selected item's history across all sessions)", style="SubHeader.TLabel").pack(
        side=tk.LEFT, padx=(8, 0)
    )

    ttk.Button(footer, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)

    # ── State and event wiring ─────────────────────────────────────────────
    _current_snap = [None]  # mutable cell

    def _populate_items(snap, filter_text=""):
        item_tree.delete(*item_tree.get_children())
        if snap is None:
            return
        rows = _snapshot_items(snap, filter_text)
        for row in rows:
            item_tree.insert(
                "",
                tk.END,
                values=(
                    row["line_code"],
                    row["item_code"],
                    row["description"],
                    row["vendor"],
                    row["suggested_qty"],
                    row["final_qty"],
                ),
            )

    def _on_session_select(event=None):
        sel = sess_tree.selection()
        if not sel:
            return
        snap = _iid_to_snap.get(sel[0])
        _current_snap[0] = snap
        _populate_items(snap, var_filter.get())

    def _on_filter_change(*_):
        _populate_items(_current_snap[0], var_filter.get())

    def _copy_item_history():
        sel = item_tree.selection()
        if not sel:
            dlg.bell()
            return
        values = item_tree.item(sel[0], "values")
        if not values or len(values) < 2:
            return
        line_code = values[0]
        item_code = values[1]
        rows = _item_history_rows(snapshots, line_code, item_code)
        tsv = _format_tsv(rows, _COPY_COLUMNS)
        dlg.clipboard_clear()
        dlg.clipboard_append(tsv)

    sess_tree.bind("<<TreeviewSelect>>", _on_session_select)
    var_filter.trace_add("write", _on_filter_change)

    # Select the most recent session automatically
    if snapshots:
        first_iid = f"sess_0"
        sess_tree.selection_set(first_iid)
        sess_tree.see(first_iid)
        _on_session_select()

    filter_entry.focus_set()
    dlg.wait_window()
