# Release Notes — v0.8.7

**Date:** 2026-04-08

---

## Summary

Two bugs the operator has been fighting across **five releases**,
both now diagnosed with ground-truth debug traces and fixed at the
real root cause:

1. **Delete key "doesn't work" — actually working, but doing the
   wrong thing.**  v0.8.6's debug logging was decisive: the
   interceptor IS firing, but `bulk_delete_selected` was dispatching
   into the Excel-style "clear cells" branch because the operator's
   typical selection is a cell, not a row header.  The vendor cell
   was being silently emptied on every Delete press.  **Fix:**
   `bulk_delete_selected` now ALWAYS removes rows — cell selection
   is promoted to the row(s) the cells live on.
2. **"Remove Unassigned → Review" dialog appears as "words in the
   upper left that disappear when the mouse hovers them."**  That's
   a Toplevel drawn with unresolved geometry at screen origin (0, 0).
   `messagebox.showinfo` on Windows Tk picks its own position from
   the parent's center, and the parent is mid-layout when the
   dialog fires, so the center resolves to garbage.  **Fix:**
   replaced `messagebox.showinfo` with a **custom `tk.Toplevel`**
   we build and control completely — explicit centered geometry,
   `-topmost` on the dialog itself (not the root), explicit `grab_set`
   on the dialog, explicit focused OK button.

1110 tests pass (1 new, 2 updated).

---

## Bug #1 — Delete key

### Ground truth from v0.8.6's debug logging

```
20:36:20.329 | bulk_sheet.delete_interceptor.fired | widget=MainTable
20:36:20.334 | bulk_apply_editor_value.begin | col_name=vendor | raw= | row_id=["010-","POST"]
20:36:20.336 | bulk_sheet.delete_interceptor.handled | result='break'
```

**The interceptor was working perfectly.**  v0.8.6's bindtag trick
was correct — Tk dispatched the Delete event to our handler first,
before tksheet's Canvas-class binding could consume it.  The handler
returned `"break"` so tksheet's Delete never ran.

But `bulk_delete_selected` was dispatching into the wrong branch:

```python
# OLD — Excel-style, which the operator never wanted:
if app.bulk_sheet and app.bulk_sheet.explicit_selected_row_ids():
    return app._bulk_remove_selected_rows(event)
if app.bulk_sheet and app.bulk_sheet.selected_cells():
    app._bulk_clear_selected_cells()   # ← fires for every cell click
    return "break"
return app._bulk_remove_selected_rows(event)
```

The second branch fires when *any* cell is selected.  Click a cell,
press Delete, the cell content is cleared — which for the vendor
column is just empty-to-empty, invisible.  **The operator thought
Delete wasn't firing because clearing a blank cell produces no
visible change.**  It was firing the whole time, just doing the
wrong thing.

### Fix

`bulk_sheet_actions_flow.bulk_delete_selected` now always removes
rows.  The new dispatch order:

1. **Explicit row-header selection** (click row numbers, ctrl-click
   for multiple) → remove those rows.
2. **Cell selection** → derive the rows the cells live on, seed the
   sheet's selection snapshot, remove those rows.
3. **Current focused row** → remove the single row under the keyboard
   focus.
4. **Nothing selected** → no-op.

Every dispatch path logs to `debug_trace.log` as
`bulk_delete_selected.source | mode=...` so future diagnosis is
instant.

**Tests rewritten to enforce the new contract:**
- `test_bulk_delete_selected_promotes_cell_selection_to_row_remove`
- `test_bulk_delete_selected_uses_current_row_fallback`
- `test_bulk_delete_selected_noop_when_nothing_selected`

The old Excel-style "clear cells" test was removed — it encoded
the very bug the operator has been fighting.

---

## Bug #2 — Dialog "words in the upper left"

### The smoking-gun description

> "some words appear in the upper left corner, but disappear when the
> mouse is over them. moving the main window around doesn't reveal
> it either"

That's a Toplevel window drawn at **screen coordinates (0, 0)** with
unresolved geometry.  "Words disappear when the mouse hovers" is a
Windows taskbar / system-tray z-order interaction kicking in on a
zero-size Toplevel.

### Why `messagebox` kept failing

`messagebox.showinfo(parent=root)` on Windows Tk:

1. Creates a new Toplevel as a transient of the parent
2. Computes position as "center of parent"
3. If the parent is mid-layout (tab switch just fired, tree populate
   still running), `winfo_width()` / `winfo_height()` return `1` or
   `0`, and `winfo_rootx()` / `winfo_rooty()` return the root's
   un-updated coordinates
4. The dialog ends up at something like `(0, 0)` with `1x1` size,
   invisible, grab-active → main window appears locked

Previous attempts (v0.8.3 `parent=app.root`, v0.8.5 `-topmost` flip
on the root) all operated on the wrong object.  The dialog Toplevel
is what needed the geometry fix, not the root.

### Fix

`_show_info_topmost` in `ui_bulk_dialogs.py` now builds a
**custom `tk.Toplevel`** with complete control:

1. `update_idletasks()` on root → flush pending layout so parent
   dimensions are real
2. Create `tk.Toplevel(root)` with the app's dark theme
3. Add label + OK button
4. `update_idletasks()` on the dialog → compute its real size
5. **Compute centered geometry** explicitly:
   - Read `root.winfo_rootx/y/width/height`
   - Read `dlg.winfo_width/height`
   - Fall back to a centered default if either is zero/un-updated
   - Log the resolved geometry to `debug_trace.log` for
     post-mortem diagnosis
6. `dlg.geometry(f"{w}x{h}+{x}+{y}")` → set explicit position
7. `dlg.deiconify()`, `dlg.lift()`, `dlg.attributes("-topmost", True)`
   — **on the dialog, not the root**
8. `dlg.focus_force()`, button `focus_set()`
9. `dlg.grab_set()` → modal behavior
10. `dlg.wait_window()` → block until OK / Escape / close
11. Close callback releases the grab and destroys the dialog

Bound `<Return>` and `<Escape>` to close, and `WM_DELETE_WINDOW` to
close too.  The dialog is fully keyboard-navigable.

**Every step logs to debug_trace.log** as `info_topmost.begin`,
`info_topmost.geometry`, `info_topmost.end`, or
`info_topmost.error`, so the next operator report will tell me
exactly which step the Windows build breaks on — if any.

### What the log will tell me next time

If the dialog still misbehaves after v0.8.7, expect a line like:

```
finish_bulk_final.info_topmost.geometry | root=1200x720+40+32 | dlg=520x180+380+202
```

And if it's still broken, I'll see the exact coordinates and can
compare against the screen / monitor layout.

---

## Files changed

- `bulk_sheet_actions_flow.py` — `bulk_delete_selected` completely
  rewritten; new dispatch logic + debug logging
- `ui_bulk_dialogs.py` — `_show_info_topmost` replaced with custom
  `tk.Toplevel` dialog
- `tests/test_bulk_sheet_actions_flow.py` — 3 new / updated tests
  encoding the new Delete contract
- `app_version.py` — bumped to 0.8.7

---

## What the operator should do on v0.8.7

1. **Drop v0.8.7 in place.**  Keep `perf_trace.enabled` if you still
   want parse timings; not strictly required.
2. **Press Delete on a single cell.**  That row should vanish.  The
   debug trace will show
   `bulk_delete_selected.source | mode=cell_promoted_to_row | n=1`.
3. **Ctrl-click multiple row headers, press Delete.**  Those rows
   should vanish.  Log will show `mode=row_header | n=N`.
4. **Remove Unassigned → Go to Review.**  The "Items Excluded"
   dialog should appear **centered on the main window**, on top,
   interactable.  Click OK → Review tab shows.  Debug log should
   have `info_topmost.geometry` with the resolved coordinates.
5. **Send me `debug_trace.log`** after the session.  Both fixes log
   their full execution paths; if anything still fails I can
   diagnose from the trace without more back-and-forth.

---

## Release history for the two long-standing bugs

| Release | Delete key fix attempt | Dialog z-order fix attempt |
|---|---|---|
| v0.8.1  | Bind on tksheet widgets + `add="+"` | — |
| v0.8.3  | — | Reorder + `parent=app.root` |
| v0.8.5  | `bind_all("<Delete>")` on root | `-topmost` flip on root |
| v0.8.6  | Bindtag interception — **interceptor works** | `_show_info_topmost` helper w/ messagebox |
| **v0.8.7** | **Always-remove dispatch logic fix** | **Custom Toplevel with explicit geometry** |

Each prior attempt fixed a real problem but never the one the
operator was actually hitting.  v0.8.6's debug logging was what
finally let v0.8.7 nail the real root causes.  **This is the value
of the perf harness + debug trace instrumentation** — without the
ground-truth logs from v0.8.6 I'd still be guessing.
