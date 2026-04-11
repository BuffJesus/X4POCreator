"""Ctrl+K command palette — keystroke-first navigation for PO Builder.

Press Ctrl+K anywhere in the app to open a search dialog.  Type to filter
across three indexes:

- **Actions**: switch tabs, run top-of-workflow operations (load, export,
  review, help), open modal tools.
- **Items**: match by line code, item code, or description.  Selecting an
  item switches to the bulk grid tab, scrolls the row into view, and
  highlights it.
- **Vendors**: match any known vendor code; selecting filters the bulk grid
  down to that vendor.

The ranking is deliberately simple: prefix match on the key field beats a
substring match, which beats a description match.  Actions always sort
above items and vendors when score ties, because "run this thing" is the
dominant use case on the keyboard hot path.

The module is UI-agnostic at the index-building layer: ``build_action_index``,
``build_item_index``, ``build_vendor_index``, and ``rank_results`` are
plain-data functions with no Tk dependencies and are covered by headless
unit tests.  Only ``open_command_palette`` touches tkinter.
"""

from __future__ import annotations

import json
from typing import Callable, Iterable, Optional

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # pragma: no cover - tk missing on CI
    tk = None  # type: ignore
    ttk = None  # type: ignore


# Result entry: plain dict with these fields
# - kind: "action" | "item" | "vendor"
# - label: display text
# - sublabel: secondary text (shown greyed)
# - haystack: precomputed lowercased search string
# - run: zero-arg callable invoked on selection
# - sort_key: tuple used for stable sort within a kind


_MAX_RESULTS = 120   # cap listbox rows so a blank query doesn't try to render 63K


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def build_action_index(app) -> list[dict]:
    """Return the static list of navigate/run actions available right now.

    Each entry uses ``getattr(app, ..., None)`` so missing methods (when the
    palette is invoked mid-load or from a test double) simply get skipped
    instead of blowing up.
    """
    notebook = getattr(app, "notebook", None)
    def _switch_to(index):
        def _run():
            if notebook is not None:
                try:
                    notebook.select(index)
                except Exception:
                    pass
        return _run

    candidates = [
        # Tab navigation — the most common use case
        ("Go to Load tab", "load files open csvs", _switch_to(0), ("00", "load")),
        ("Go to Filters / Exclusions", "filter customer line code", _switch_to(1), ("01", "filter")),
        ("Go to Bulk Grid", "bulk grid assign vendor", _switch_to(3), ("02", "bulk")),
        ("Go to Review & Export", "review export finalize", _switch_to(4), ("03", "review")),
        ("Go to Help", "help documentation shortcuts", _switch_to(5), ("04", "help")),
        # Top-of-workflow actions
        ("Export POs", "export excel vendor finalize", getattr(app, "_proceed_to_review_with_enrich", None), ("10", "export")),
        ("Draft Review (Print)", "draft review print verify", getattr(app, "_export_draft_review", None), ("11", "draft")),
        ("Remove Not Needed", "remove not needed unassigned cleanup", getattr(app, "_bulk_remove_not_needed_filtered", None), ("20", "remove")),
        ("Undo Last Removal", "undo restore revert", getattr(app, "_undo_last_bulk_removal", None), ("21", "undo")),
        ("Manage Vendors...", "manage vendor codes list", getattr(app, "_open_vendor_manager", None), ("30", "vendor")),
        ("Vendor Review...", "vendor review summary", getattr(app, "_open_vendor_review", None), ("31", "vendor")),
        ("Supplier Map...", "supplier map auto-assign", getattr(app, "_open_supplier_map", None), ("32", "supplier")),
        ("QOH Changes...", "qoh quantity on hand review adjustments", getattr(app, "_open_qoh_review", None), ("33", "qoh")),
        ("Manage Ignored Items", "ignored skip ignore list", getattr(app, "_open_ignored_items_manager", None), ("34", "ignored")),
        ("Skip Cleanup...", "skip cleanup discontinued flag", getattr(app, "_open_skip_actions", None), ("35", "skip")),
        ("Bulk Shortcuts...", "shortcuts help keyboard", getattr(app, "_show_bulk_shortcuts", None), ("40", "shortcuts")),
        ("Export Order Rules CSV", "export rules csv", getattr(app, "_export_order_rules_csv", None), ("50", "rules")),
        ("Import Order Rules CSV", "import rules csv", getattr(app, "_import_order_rules_csv", None), ("51", "rules")),
    ]

    results = []
    for label, keywords, run, sort_key in candidates:
        if not callable(run):
            continue
        haystack = _normalize(f"{label} {keywords}")
        results.append({
            "kind": "action",
            "label": label,
            "sublabel": "",
            "haystack": haystack,
            "run": run,
            "sort_key": sort_key,
        })
    return results


def build_item_index(filtered_items, jump_callback: Callable[[str, str], None]) -> list[dict]:
    """Index every item in the bulk grid by LC, IC, and description."""
    index = []
    for item in filtered_items or []:
        lc = str(item.get("line_code", "") or "")
        ic = str(item.get("item_code", "") or "")
        desc = str(item.get("description", "") or "")
        vendor = str(item.get("vendor", "") or "")
        haystack = _normalize(f"{lc}{ic} {lc} {ic} {desc} {vendor}")
        if not haystack:
            continue
        def make_run(_lc=lc, _ic=ic):
            return lambda: jump_callback(_lc, _ic)
        sublabel_parts = []
        if desc:
            sublabel_parts.append(desc)
        if vendor:
            sublabel_parts.append(f"vendor {vendor}")
        index.append({
            "kind": "item",
            "label": f"{lc}{ic}",
            "sublabel": " — ".join(sublabel_parts),
            "haystack": haystack,
            "run": make_run(),
            "sort_key": (lc, ic),
        })
    return index


def build_vendor_index(known_vendors, filter_callback: Callable[[str], None]) -> list[dict]:
    seen = set()
    index = []
    for vendor in known_vendors or []:
        vendor = str(vendor or "").strip()
        if not vendor or vendor in seen:
            continue
        seen.add(vendor)
        def make_run(_vendor=vendor):
            return lambda: filter_callback(_vendor)
        index.append({
            "kind": "vendor",
            "label": f"Filter: {vendor}",
            "sublabel": "Filter bulk grid to this vendor",
            "haystack": _normalize(f"{vendor} filter vendor"),
            "run": make_run(),
            "sort_key": (vendor,),
        })
    return index


def _score(entry: dict, query: str) -> Optional[int]:
    """Return a ranking score for ``entry`` given ``query``, or None if no match.

    Lower is better — the sort is ascending.  The breakdown:
    - 0: query prefix-matches the label (e.g., "gr1-3504" matches item "GR1-3504-04-04")
    - 10: query substring-matches the label
    - 20: query substring-matches the haystack (description / keywords)
    - None: no match
    """
    if not query:
        return 30  # every entry is a candidate when the query is empty
    label = _normalize(entry.get("label", ""))
    haystack = entry.get("haystack", "")
    if label.startswith(query):
        return 0
    if query in label:
        return 10
    if query in haystack:
        return 20
    return None


_KIND_ORDER = {"action": 0, "item": 1, "vendor": 2}


def rank_results(query: str, *indexes: Iterable[dict], limit: int = _MAX_RESULTS) -> list[dict]:
    query_norm = _normalize(query)
    scored: list[tuple[int, int, tuple, dict]] = []
    for index in indexes:
        for entry in index:
            score = _score(entry, query_norm)
            if score is None:
                continue
            kind_rank = _KIND_ORDER.get(entry.get("kind", "item"), 9)
            scored.append((score, kind_rank, entry.get("sort_key", ()), entry))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [entry for _s, _k, _sk, entry in scored[:limit]]


# ─── Tk-facing shell ────────────────────────────────────────────────────────

def _default_jump_to_item(app, line_code: str, item_code: str) -> None:
    """Switch to the bulk grid tab and scroll the target row into view.

    Missing app pieces (no notebook, no bulk sheet, row filtered out) degrade
    to a no-op rather than an exception, because the palette is invoked from
    every tab and cannot assume the grid is fully built.
    """
    notebook = getattr(app, "notebook", None)
    if notebook is not None:
        try:
            notebook.select(3)
        except Exception:
            pass
    bulk_view = getattr(app, "bulk_view", None)
    sheet = getattr(bulk_view, "sheet", None) if bulk_view else None
    if sheet is None:
        return
    row_id = json.dumps([line_code, item_code], separators=(",", ":"))
    row_idx = None
    row_lookup = getattr(bulk_view, "row_lookup", None) or {}
    if row_id in row_lookup:
        row_idx = row_lookup[row_id]
    if row_idx is None:
        # Row is filtered out of the current view.  Rather than silently
        # failing, leave a breadcrumb the operator can read.
        status_setter = getattr(app, "_set_bulk_status", None)
        msg = f"{line_code}{item_code} is not in the current filter — clear filters to see it."
        if callable(status_setter):
            status_setter(msg)
        return
    try:
        sheet.deselect("all", redraw=False)
        sheet.select_row(row_idx, redraw=False)
        sheet.see(row=row_idx, column=0)
    except Exception:
        pass


def _default_filter_to_vendor(app, vendor: str) -> None:
    """Apply a vendor filter by mirroring the vendor-worksheet dropdown logic.

    Sets ``var_bulk_vendor_filter_internal`` directly (same field
    ``_on_vendor_worksheet_changed`` writes when the operator picks a vendor
    tab), resets the status filters to ALL so the vendor's full roster shows,
    and runs ``_apply_bulk_filter`` to re-populate the grid.
    """
    notebook = getattr(app, "notebook", None)
    if notebook is not None:
        try:
            notebook.select(3)
        except Exception:
            pass
    try:
        setattr(app, "var_bulk_vendor_filter_internal", vendor)
    except Exception:
        pass
    for var_name, value in (("var_bulk_status_filter", "ALL"), ("var_bulk_item_status", "ALL")):
        var = getattr(app, var_name, None)
        if var is None:
            continue
        try:
            var.set(value)
        except Exception:
            pass
    # Sync the vendor-worksheet combobox so the UI reflects the new filter.
    combo = getattr(app, "_vendor_worksheet_combo", None)
    if combo is not None:
        try:
            current_values = list(combo.cget("values") or [])
            for choice in current_values:
                stripped = choice.split(" (")[0].strip() if " (" in choice else choice
                if stripped == vendor:
                    combo.set(choice)
                    break
            else:
                combo.set(vendor)
        except Exception:
            pass
    apply_filter = getattr(app, "_apply_bulk_filter", None)
    if callable(apply_filter):
        try:
            apply_filter()
        except Exception:
            pass


def open_command_palette(app) -> Optional[object]:
    """Open the Ctrl+K palette.  Returns the Toplevel or None on failure."""
    if tk is None:  # pragma: no cover - tk missing
        return None
    root = getattr(app, "root", None)
    if root is None:
        return None

    actions = build_action_index(app)
    filtered_items = getattr(app.session, "filtered_items", None) if getattr(app, "session", None) else None
    items = build_item_index(
        filtered_items or [],
        lambda lc, ic: _default_jump_to_item(app, lc, ic),
    )
    known_vendors = getattr(app, "known_vendors", None)
    if not known_vendors:
        # Fall back to the module-level KNOWN_VENDORS if the app instance
        # hasn't stored its own copy.
        try:
            from po_builder import KNOWN_VENDORS as _KV
            known_vendors = _KV
        except Exception:
            known_vendors = []
    vendors = build_vendor_index(
        known_vendors,
        lambda vendor: _default_filter_to_vendor(app, vendor),
    )

    dlg = tk.Toplevel(root)
    dlg.title("Command Palette")
    dlg.transient(root)
    try:
        dlg.grab_set()
    except tk.TclError:
        pass
    dlg.geometry("640x420")
    # Center on the root window
    root.update_idletasks()
    try:
        x = root.winfo_rootx() + max(0, (root.winfo_width() - 640) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - 420) // 3)
        dlg.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass

    outer = ttk.Frame(dlg, padding=(12, 10))
    outer.pack(fill=tk.BOTH, expand=True)

    prompt = ttk.Label(outer, text="Type an item code, vendor, or action…", anchor="w")
    prompt.pack(fill=tk.X, pady=(0, 6))

    query_var = tk.StringVar()
    entry = ttk.Entry(outer, textvariable=query_var, font=("TkDefaultFont", 11))
    entry.pack(fill=tk.X)

    list_frame = ttk.Frame(outer)
    list_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    listbox = tk.Listbox(
        list_frame,
        activestyle="none",
        yscrollcommand=scrollbar.set,
        font=("TkFixedFont", 10),
    )
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=listbox.yview)

    footer = ttk.Label(
        outer,
        text=f"{len(items)} item(s) · {len(vendors)} vendor(s) · {len(actions)} action(s)  —  Enter to run · Esc to close",
        foreground="#8a93a6",
    )
    footer.pack(fill=tk.X, pady=(6, 0))

    current_results: list[dict] = []

    def render_results(results: list[dict]):
        listbox.delete(0, tk.END)
        for entry_dict in results:
            label = entry_dict.get("label", "")
            sublabel = entry_dict.get("sublabel", "")
            kind = entry_dict.get("kind", "")
            tag = {"action": "▶", "item": "◆", "vendor": "◇"}.get(kind, "·")
            line = f"{tag}  {label}"
            if sublabel:
                line += f"   — {sublabel}"
            if len(line) > 160:
                line = line[:157] + "..."
            listbox.insert(tk.END, line)
        if results:
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(0)
            listbox.activate(0)

    def do_search(*_):
        nonlocal current_results
        q = query_var.get()
        current_results = rank_results(q, actions, items, vendors, limit=_MAX_RESULTS)
        render_results(current_results)

    def run_selected(_event=None):
        sel = listbox.curselection()
        if not sel or not current_results:
            return "break"
        idx = sel[0]
        if idx >= len(current_results):
            return "break"
        chosen = current_results[idx]
        dlg.destroy()
        run = chosen.get("run")
        if callable(run):
            try:
                run()
            except Exception:
                pass
        return "break"

    def close_palette(_event=None):
        dlg.destroy()
        return "break"

    def move_selection(step):
        size = listbox.size()
        if size == 0:
            return "break"
        sel = listbox.curselection()
        idx = sel[0] if sel else 0
        idx = (idx + step) % size
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.activate(idx)
        listbox.see(idx)
        return "break"

    query_var.trace_add("write", lambda *_: do_search())
    entry.bind("<Return>", run_selected)
    entry.bind("<Escape>", close_palette)
    entry.bind("<Down>", lambda e: move_selection(1))
    entry.bind("<Up>", lambda e: move_selection(-1))
    entry.bind("<Next>", lambda e: move_selection(10))
    entry.bind("<Prior>", lambda e: move_selection(-10))
    listbox.bind("<Double-Button-1>", run_selected)
    listbox.bind("<Return>", run_selected)
    listbox.bind("<Escape>", close_palette)
    dlg.bind("<Escape>", close_palette)
    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

    entry.focus_set()
    do_search()
    return dlg
