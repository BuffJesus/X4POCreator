"""Ignored Items Manager dialog.

Provides open_ignored_items_manager(app) — a dialog that lets operators view,
filter, and remove items from the persistent ignore list without editing
ignored_items.txt by hand.

Pure helpers (_parse_ignore_key, _filter_keys) have no tkinter dependency
and are tested in tests/test_ignored_items.py.
"""
import tkinter as tk
from tkinter import ttk, messagebox


# ── Pure helpers ─────────────────────────────────────────────────────────────

def _parse_ignore_key(key):
    """Split a 'LINE_CODE:ITEM_CODE' key into a (line_code, item_code) tuple.

    Returns ('', key) when no colon is found.
    """
    key = str(key)
    if ":" in key:
        idx = key.index(":")
        return key[:idx], key[idx + 1:]
    return "", key


def _filter_keys(keys, filter_text):
    """Return the subset of *keys* matching *filter_text*.

    Matches case-insensitively against either part of the LINE:ITEM key.
    An empty filter returns all keys unchanged.
    """
    needle = filter_text.strip().lower()
    if not needle:
        return list(keys)
    result = []
    for key in keys:
        line_code, item_code = _parse_ignore_key(key)
        if needle in line_code.lower() or needle in item_code.lower():
            result.append(key)
    return result


# ── Dialog ────────────────────────────────────────────────────────────────────

_BG = "#1e1e2e"
_LIST_BG = "#1f2330"
_LIST_FG = "#f4f4f6"
_LIST_SEL = "#5b4cc4"


def open_ignored_items_manager(app):
    """Open the Ignored Items Manager dialog."""
    dlg = tk.Toplevel(app.root)
    dlg.title("Ignored Items")
    dlg.configure(bg=_BG)
    dlg.transient(app.root)
    dlg.grab_set()
    dlg.geometry("560x480")
    dlg.minsize(400, 300)

    # ── Header ────────────────────────────────────────────────────────────
    ttk.Label(dlg, text="Ignored Items", style="Header.TLabel").pack(
        anchor="w", padx=16, pady=(16, 2)
    )
    ttk.Label(
        dlg,
        text=(
            "Items on this list are excluded from every session. "
            "Select items and click Remove to restore them. "
            "Restored items reappear on the next file load."
        ),
        style="SubHeader.TLabel",
        wraplength=520,
    ).pack(anchor="w", padx=16, pady=(0, 8))

    # ── Filter bar ────────────────────────────────────────────────────────
    filter_frame = ttk.Frame(dlg)
    filter_frame.pack(fill=tk.X, padx=16, pady=(0, 6))
    ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT)
    var_filter = tk.StringVar()
    filter_entry = ttk.Entry(filter_frame, textvariable=var_filter, width=28)
    filter_entry.pack(side=tk.LEFT, padx=(6, 0))

    # ── List ──────────────────────────────────────────────────────────────
    list_frame = ttk.Frame(dlg)
    list_frame.pack(fill=tk.BOTH, expand=True, padx=16)

    tree = ttk.Treeview(
        list_frame,
        columns=("line_code", "item_code"),
        show="headings",
        selectmode="extended",
    )
    tree.heading("line_code", text="Line Code")
    tree.heading("item_code", text="Item Code")
    tree.column("line_code", width=160, minwidth=80)
    tree.column("item_code", width=280, minwidth=100, stretch=True)

    vscroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vscroll.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vscroll.pack(side=tk.RIGHT, fill=tk.Y)

    # ── Count label ───────────────────────────────────────────────────────
    var_count = tk.StringVar()
    ttk.Label(dlg, textvariable=var_count, style="SubHeader.TLabel").pack(
        anchor="w", padx=16, pady=(4, 0)
    )

    # ── Footer ────────────────────────────────────────────────────────────
    footer = ttk.Frame(dlg)
    footer.pack(fill=tk.X, padx=16, pady=(8, 12))

    btn_remove = ttk.Button(footer, text="Remove from Ignore List", command=lambda: _remove_selected())
    btn_remove.pack(side=tk.LEFT)
    btn_remove_all = ttk.Button(footer, text="Remove All", command=lambda: _remove_all())
    btn_remove_all.pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(footer, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)

    # ── State and helpers ─────────────────────────────────────────────────
    _displayed_keys = []  # keys currently shown in tree (same order as tree rows)

    def _refresh(keep_selection=None):
        all_keys = sorted(app.ignored_item_keys)
        visible = _filter_keys(all_keys, var_filter.get())
        _displayed_keys.clear()
        _displayed_keys.extend(visible)

        tree.delete(*tree.get_children())
        for key in visible:
            lc, ic = _parse_ignore_key(key)
            tree.insert("", tk.END, iid=key, values=(lc, ic))

        total = len(all_keys)
        shown = len(visible)
        if shown == total:
            var_count.set(f"{total} item{'s' if total != 1 else ''} ignored")
        else:
            var_count.set(f"Showing {shown} of {total} ignored items")

        # Restore selection if requested
        if keep_selection:
            for key in keep_selection:
                if tree.exists(key):
                    tree.selection_add(key)

        btn_remove.configure(state="normal" if visible else "disabled")
        btn_remove_all.configure(state="normal" if all_keys else "disabled")

    def _remove_selected():
        sel = list(tree.selection())
        if not sel:
            return
        removed = app._un_ignore_item_keys(set(sel))
        if removed:
            _refresh()

    def _remove_all():
        all_keys = sorted(app.ignored_item_keys)
        if not all_keys:
            return
        if not messagebox.askyesno(
            "Remove All",
            f"Remove all {len(all_keys)} item{'s' if len(all_keys) != 1 else ''} from the ignore list?\n\n"
            "They will reappear on the next file load.",
            parent=dlg,
        ):
            return
        app._un_ignore_item_keys(set(all_keys))
        _refresh()

    var_filter.trace_add("write", lambda *_: _refresh())

    _refresh()
    filter_entry.focus_set()
    dlg.wait_window()
