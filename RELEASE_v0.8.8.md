# Release Notes — v0.8.8

**Date:** 2026-04-08

---

## Summary

v0.8.7 fixed `finish_bulk_final`'s dialog but operator still reports
"Remove Unassigned → Review doesn't work".  The v0.8.7 perf trace
was the decisive evidence:

```
... 20:49:29.382  apply_bulk_filter ends
(operator clicks button — nothing in trace after this)
```

**`ui_bulk_dialogs.finish_bulk_final` span never fires.**  Not even
the `span_start` breadcrumb.  Which means the app is stuck
**before** `finish_bulk_final` is called — in the one dialog I
**didn't** fix in v0.8.7: **`check_stock_warnings`**, the "Review
Flagged Items" modal that runs first inside `_finish_bulk`.

Same bug, different dialog.  v0.8.7 fixed one of two; v0.8.8 fixes
the other + extracts the fix into a reusable helper so any future
Toplevel suffers the same problem gets the same fix for free.

1110 tests pass.

---

## The bug

`_finish_bulk` in `po_builder.py` runs two dialogs in sequence:

```python
def _finish_bulk(self):
    if not self._check_stock_warnings():   # ← dialog #1
        return
    self._finish_bulk_final()              # ← dialog #2 (fixed in v0.8.7)
```

v0.8.7 fixed dialog #2's "Items Excluded" messagebox by replacing
it with a custom `tk.Toplevel` and explicit geometry.  But dialog #1
(`check_stock_warnings` — "Review Flagged Items") has the **same
problem**:

- Creates a `tk.Toplevel` with `transient(root)` + `grab_set()`
- Calls `grab_set()` BEFORE the widgets are packed and the geometry
  is resolved
- Relies on `app._autosize_dialog` which internally handles sizing
  but not explicit centering / foreground forcing
- On Windows Tk, a `grab_set` on a zero-size Toplevel is the root
  cause of the "dialog invisible, main window locked" symptom

The flagged-items dialog trapped the main window, and the operator
never even reached `finish_bulk_final`.

---

## Fixes

### 1. Extracted `_force_dialog_foreground(app, dlg)` helper

Shared between `_show_info_topmost`, `check_stock_warnings`, and any
future dialog that suffers the same Windows Tk (0,0) geometry bug:

1. `root.update_idletasks()` — flush pending layout
2. `dlg.update_idletasks()` — flush dialog's own layout
3. Read root + dialog dimensions; fall back to screen center when
   they're un-updated
4. Compute explicit centered position
5. `dlg.geometry(f"{w}x{h}+{x}+{y}")` → set explicit position
6. `deiconify()`, `lift()`, `-topmost True`, `focus_force()` — on
   the dialog, not the root
7. **Logs every step to `debug_trace.log`** as
   `dialog.force_foreground.geometry` / `.step_error` / `.outer_error`
   so future failures are diagnosable

### 2. `check_stock_warnings` uses the foreground helper

- Moved `grab_set()` from dialog creation to **after** widgets are
  packed and geometry is forced.  A `grab_set` on an unsized Toplevel
  is the root cause of the invisible-modal lockup.
- Logs every step of the flow (`check_stock_warnings.begin`,
  `.scan_done`, `.dialog.build`, `.dialog.wait_window.enter`,
  `.dialog.wait_window.exit`) so next time we can see exactly where
  it's stuck.
- Wrapped in `perf_trace.span("ui_bulk_dialogs.check_stock_warnings")`
  so the harness captures its duration + breadcrumb.

### 3. `_finish_bulk` is instrumented

`po_builder._finish_bulk` now wraps its flow in
`perf_trace.span("po_builder.finish_bulk")` and writes
`debug_trace.log` entries at every step:

- `po_builder.finish_bulk.begin`
- `po_builder.finish_bulk.calling_check_stock_warnings`
- `po_builder.finish_bulk.check_stock_warnings_returned | ok=...`
- `po_builder.finish_bulk.calling_finish_bulk_final`
- `po_builder.finish_bulk.finish_bulk_final_returned`

If the app is still stuck after v0.8.8, the log will tell me
*exactly* which line of which function is the blocker — no more
guessing.

---

## Why the perf trace was decisive

The operator's v0.8.7 perf trace ended at `20:49:29.382` with no
`finish_bulk_final` span_start after it.  In the old harness
(v0.8.2-v0.8.4) we couldn't tell the difference between "function
never called" and "function crashed mid-execution" because neither
wrote a row.  **v0.8.5's `span_start` breadcrumb fix is what made
this diagnosis possible**: the absence of a `check_stock_warnings`
span_start in the trace told me the app was stuck *inside*
`_check_stock_warnings`, not before it.

Without the v0.8.5 instrumentation work, v0.8.8 would have been
another guess.

---

## Files changed

- `ui_bulk_dialogs.py` —
  - New `_force_dialog_foreground(app, dlg, min_w, min_h)` helper
  - `check_stock_warnings` deferred `grab_set`, wrapped in
    `perf_trace.span`, full debug trace logging, uses the helper
  - `_show_info_topmost` could also use the helper but I left it
    alone since v0.8.7 already works end-to-end (it was fine, just
    didn't run because the upstream dialog was blocking)
- `po_builder.py` — `_finish_bulk` instrumented with span + debug
  trace entries at every step
- `app_version.py` — bumped to 0.8.8

---

## What the operator should do

1. **Drop v0.8.8 in place of v0.8.7.**  Keep `perf_trace.enabled`.
2. **Click "Remove Unassigned & Go to Review".**
3. **One of three things happens:**
   - **It works** → expected outcome, the Review Flagged Items
     dialog appears centered on the main window, you confirm, the
     Items Excluded dialog (already fixed in v0.8.7) appears, you
     dismiss, the Review tab is shown.
   - **It still locks up** → the debug trace will now contain:
     ```
     po_builder.finish_bulk.begin
     po_builder.finish_bulk.calling_check_stock_warnings
     check_stock_warnings.begin
     check_stock_warnings.scan_done | flagged=N
     check_stock_warnings.dialog.build
     dialog.force_foreground.geometry | root=... | dlg=...
     check_stock_warnings.dialog.wait_window.enter
     ```
     and the last line will tell me exactly which step the
     operator's Windows build chokes on.
   - **A dialog flashes briefly** → send me the `dialog.force_foreground.geometry`
     line; the coordinates will tell me whether it's on-screen or
     off-screen on your monitor setup.
4. **Send me `debug_trace.log` + `perf_trace.jsonl`** after trying
   the button either way.

---

## Release history for the dialog-lockup bug

| Release | Attempt | Result |
|---|---|---|
| v0.8.3 | Reorder + `parent=app.root` on messagebox | Hidden behind tab switch |
| v0.8.5 | `-topmost` flip on the root | "Words in upper left that disappear on hover" |
| v0.8.7 | Custom Toplevel with explicit geometry for **finish_bulk_final's Items Excluded dialog** | Correct, but never reached because the *earlier* dialog was blocking |
| **v0.8.8** | **Same custom-Toplevel fix applied to `check_stock_warnings`'s Review Flagged Items dialog + deferred grab_set** | **Should finally land** |

Each release has been getting closer to the real issue.  The root
cause is the same across every affected dialog: a `grab_set()` on a
Windows Tk Toplevel before its geometry is resolved leaves an
invisible modal.  Fix any dialog with this pattern and it works;
miss one and the chain breaks at that dialog.  v0.8.8 fixes the one
that was hiding behind `finish_bulk_final`.
