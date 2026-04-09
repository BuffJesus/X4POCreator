# Release Notes — v0.8.6

**Date:** 2026-04-08

---

## Summary

Two stubborn bugs the operator has been fighting for multiple releases
finally diagnosed with ground-truth debug traces and fixed at the
correct level:

1. **Delete key never worked** because `bind_all` and widget-level
   bindings were being preempted by tksheet's own Canvas-class
   binding, which runs before the `"all"` bindtag in Tk's dispatch
   order.  v0.8.5's debug logging proved it — zero
   `delete_key.fired` entries in `debug_trace.log` means the event
   was eaten before reaching us.  **Fix: bindtag interception** —
   insert a custom bindtag at position 0 on every tksheet sub-widget
   so our handler runs *first* in Tk's dispatch order.
2. **Items Excluded dialog still landed behind the main window** even
   with `parent=app.root`.  `messagebox.showinfo` on Windows Tk
   respects the parent for *modality* but not always for *z-order*,
   especially right after a cascade of tree operations.  **Fix:**
   `_show_info_topmost` helper that pumps `update_idletasks`,
   force-lifts the root, briefly flips `-topmost`, and only then
   shows the dialog.

1109 tests pass (1 updated + 0 new — the v0.8.3 test was rewritten
to enforce the new, stronger contract).

---

## Delete key — bindtag interception

### Why the previous attempts failed

v0.8.1 bound `<Delete>` on the Sheet + MT + RI + CH widgets with
`add="+"`.  v0.8.5 added a root-level `bind_all("<Delete>", ...)`.
Neither worked because of how Tk dispatches keyboard events through
**bindtags**.

Every Tk widget has a list of bindtags (e.g.
`("canvas_widget_name", "Canvas", ".", "all")`).  When a key event
fires, Tk walks the bindtags in order, running any binding registered
on each tag.  A binding that returns `"break"` stops further
propagation.

tksheet registers its `<Delete>` handler at the **`Canvas` class**
level (via `bind_class`).  The `Canvas` tag runs *before* the `"all"`
tag in the dispatch order, so `bind_all` can never preempt it.
`add="+"` on the widget tag doesn't help either because tksheet's
class-level handler runs on the tag that comes after the widget tag.

The v0.8.5 debug logging in `_global_delete_key_handler` wrote
`po_builder.delete_key.fired` to `debug_trace.log` on every Delete
keystroke… and zero entries appeared in the operator's log after a
full session of pressing Delete.  Ground truth: the event never
reaches our handler because tksheet eats it at the Canvas class
level and returns `"break"`.

### The fix

`BulkSheetView._bind_row_delete_keys` in `bulk_sheet.py` now:

1. **Registers a custom bindtag** `"POBuilderSheetDelete"` via
   `bind_class` with our handler.
2. **Prepends the custom bindtag** to the bindtags list of every
   tksheet sub-widget (Sheet, MT, RI, CH, TL).
3. Because our custom tag is at **position 0**, Tk dispatches the
   event to our binding **before** the widget tag, before the
   `Canvas` class tag, before `"."`, before `"all"`.
4. The handler returns `"break"` so tksheet's Canvas handler never
   runs — this is what makes our handler *replace* tksheet's Delete
   instead of running alongside it.
5. Still logs every fired event via `write_debug` so the operator
   and I can verify it's working on the next run.

The legacy widget-level bindings from v0.8.1 are kept as a fallback
for tksheet versions where bindtags don't behave as expected —
harmless when the bindtag interception works.

---

## Items Excluded dialog — Windows z-order fix

### Why `parent=app.root` wasn't enough

`messagebox.showinfo(title, msg, parent=...)` on Windows Tk sets the
dialog's **owner window** for modality purposes (the parent becomes
non-interactive while the dialog is up) but does **not** guarantee
the dialog lands on top in the window z-order.  When the dialog is
created right after a cascade of tree / notebook operations, Windows
can place the new Toplevel below the main window if the main
window's HWND is still being updated by a pending redraw.

The operator's exact symptom: the dialog's `grab_set` activates, so
the main window stops accepting clicks (it bells instead).  But the
dialog itself is invisible because it's below the main window in
z-order.  The app looks frozen, but it's actually waiting on a modal
you can't see or click.

### The fix

New `_show_info_topmost(app, title, message)` helper does five
things before showing the dialog:

1. **`root.update_idletasks()`** — flushes pending geometry updates
   so the HWND is in a fully-visible state.
2. **`root.deiconify()`** — no-op if not minimized, but cheap insurance.
3. **`root.lift()`** — raises the root to the top of the stacking
   order.
4. **`root.attributes("-topmost", True)`** then **`after(50ms) →
   -topmost False`** — the well-known Windows trick to force the
   window manager to re-evaluate z-order without permanently pinning
   the app over every other window.
5. **`root.focus_force()`** — puts keyboard focus on the root so
   the dialog inherits it.

Only *then* does `messagebox.showinfo` run, with an explicit
`parent=root`.  The dialog now appears on top of the main window
every time.

### Where it's used

`finish_bulk_final` ("Items Excluded" notice).  Other dialogs in the
same file that have the same risk profile (`showwarning` for no
items, `askyesno` for unresolved reviews) still use the
`parent=app.root` pattern — those fire *before* the heavy tree
populate, so z-order is stable.  If the operator reports a similar
issue on those, the helper is easy to reuse.

---

## Files changed

- `bulk_sheet.py` — `_bind_row_delete_keys` now uses bindtag
  interception via a custom `POBuilderSheetDelete` bindtag registered
  via `bind_class` + inserted at position 0 on every sheet sub-widget.
  Every fired event logs to `debug_trace.log` for verification.
- `ui_bulk_dialogs.py` — new `_show_info_topmost` helper; `finish_bulk_final`
  routes the Items Excluded notice through it; the dialog now fires
  *after* the tab switch (the v0.8.3 reorder is reverted — with the
  topmost helper in place, showing after the switch is fine AND
  preserves the "user sees the new tab first" UX).
- `tests/test_ui_bulk_dialogs.py` — the v0.8.3 "dialog fires before
  tab switch" assertion was rewritten as
  `test_finish_bulk_final_items_excluded_dialog_uses_topmost_helper`
  which asserts the topmost helper is called rather than testing
  event ordering.  Stronger contract, matches the real fix.
- `app_version.py` — bumped to 0.8.6

---

## What the operator should do

1. **Drop v0.8.6 in place of v0.8.5.**  Keep `perf_trace.enabled`.
2. **Press Delete on selected rows in the bulk grid.**  Whether it
   works or not, `debug_trace.log` will now have entries like:
   ```
   bulk_sheet.delete_interceptor.tag_installed | widget=MainTable | ...
   bulk_sheet.delete_interceptor.fired | widget=MainTable
   bulk_sheet.delete_interceptor.handled | result='break'
   ```
   If those appear → the interception is working.  If they don't →
   tksheet's Delete event is being handled at an even lower level and
   I need more data.
3. **Run Remove Unassigned → Go to Review.**  The Items Excluded
   dialog should now land on top, on Windows, every time.  If it
   doesn't, the `finish_bulk_final.info_topmost.begin` /
   `.end` / `.error` entries in `debug_trace.log` will tell me
   exactly which step of the topmost helper failed.
4. **Send me `debug_trace.log` + `perf_trace.jsonl`** after a
   typical session.
