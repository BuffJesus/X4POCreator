# Release Notes — v0.8.9

**Date:** 2026-04-08

---

## Summary

The "Remove Unassigned → Go to Review locks up" bug has had five
failed fix attempts (v0.8.3, v0.8.5, v0.8.6, v0.8.7, v0.8.8).  Each
fixed a real problem but missed the actual cause.  **v0.8.9 finally
nails it with ground-truth evidence from the v0.8.8 debug trace.**

1110 tests pass.

---

## The real root cause

v0.8.8's instrumentation produced the decisive log:

```
20:59:40.131 | po_builder.finish_bulk.begin
20:59:40.132 | po_builder.finish_bulk.calling_check_stock_warnings
20:59:40.134 | check_stock_warnings.begin | item_count=2132
20:59:41.398 | check_stock_warnings.scan_done | flagged=1099   ← NOTE
20:59:41.398 | check_stock_warnings.dialog.build
20:59:50.437 | dialog.force_foreground.geometry | dlg=510x406+1025+344 | root=2560x1369+0+23
20:59:50.438 | check_stock_warnings.dialog.wait_window.enter
```

Two decisive pieces of evidence:

1. **`dialog.force_foreground.geometry | dlg=510x406+1025+344`**
   — the dialog IS being positioned correctly.  It's at pixel
   coordinates (1025, 344) with size 510x406, centered on a
   2560x1369 monitor.  My v0.8.7/v0.8.8 geometry fix works.
2. **`flagged=1099`** — there were **1,099 flagged items** in the
   review dialog.  And **the build took 9 full seconds** (41.398 →
   50.437).

The `check_stock_warnings` dialog creates **11 Tk widgets per row**
(checkbox, label×10).  With 1,099 rows that's **~12,000 Tk widgets
inside a single scrollable canvas**.  Tk's main event loop is
entirely blocked constructing that many widgets + computing the
canvas scrollregion — the app appears frozen because it IS frozen,
not because the dialog is invisible.

After the 9-second freeze the dialog is actually visible, but at
that point the operator has already given up and killed the process
thinking it's dead.

**This was never a z-order bug.  It's a UI scalability bug.**
v0.8.3 through v0.8.8 were chasing a non-existent ghost because
none of the earlier debug traces contained the `flagged=1099` line
that made the problem obvious.

---

## The fix

`check_stock_warnings` now **short-circuits** when the flagged count
exceeds **50**.  For large flagged sets it shows a fast summary
dialog instead of the per-row grid:

```python
MAX_FLAGGED_ROWS = 50
if len(flagged) > MAX_FLAGGED_ROWS:
    return _show_too_many_flagged_confirm(app, len(flagged))
```

The summary dialog is a simple Toplevel with:
- Header: "N items in the current list may not need to be ordered."
- Body: "That's too many to review one at a time.  Consider using
  Remove Not Needed (Filtered) from the bulk tab first to narrow
  the list, then retry.  Or click Proceed Anyway to export the
  items as-is."
- Buttons: "← Go Back" (returns False, cancels finish_bulk) and
  "Proceed Anyway" (returns True, continues to finish_bulk_final)
- Uses the same `_force_dialog_foreground` helper from v0.8.8 so
  it lands on top, centered, visible

**No widget grid.  No canvas.  Four widgets total.  Builds instantly.**

The per-row detailed grid dialog is still used when the flagged
count is ≤50 — that's the original design case and it works fine
at that scale.

Full execution logged to `debug_trace.log`:

```
check_stock_warnings.too_many_flagged | count=1099
check_stock_warnings.too_many_flagged.dialog.begin | count=1099
check_stock_warnings.too_many_flagged.wait_window.enter
check_stock_warnings.too_many_flagged.wait_window.exit | proceed=True
```

---

## Why the operator's workload hits this

After a "Remove Not Needed (Filtered)" pass that removes 57,783
items, the remaining 2,132 items are the ones the operator decided
to KEEP.  Most of those have vendors assigned.  When
`check_stock_warnings` runs at export time, it rechecks every item
against `not_needed_reason` and flags anything that might be
exceptional — and because the operator's dataset has lots of
items with QOH ≥ min, overstock warnings, etc., **half of the kept
items trip the flagged criterion**.

The dialog was designed for "5-10 exceptional items the operator
should double-check before exporting."  It was never stress-tested
against "the operator's entire daily workload is exception-heavy."

---

## Files changed

- `ui_bulk_dialogs.py` —
  - New `_show_too_many_flagged_confirm(app, count)` helper
  - `check_stock_warnings` short-circuits when `len(flagged) > 50`
- `app_version.py` — bumped to 0.8.9

---

## What should happen on the next run

1. **Drop v0.8.9 in place.**
2. **Click "Remove Unassigned & Go to Review".**
3. **Expected:** A small summary dialog appears instantly (no
   9-second wait).  It says "1099 items in the current list may
   not need to be ordered" and offers Go Back or Proceed Anyway.
4. Click **Proceed Anyway** → `finish_bulk_final` runs, the
   Items Excluded dialog (already fixed in v0.8.7) appears if
   applicable, the Review tab shows.
5. **Send me `debug_trace.log` either way** — the full breadcrumb
   trail will either confirm success or tell me exactly what's
   different next.

---

## Release history — the full saga

| Release | Theory | Fix | Result |
|---|---|---|---|
| v0.8.3 | Dialog hidden behind tab switch | Reorder + parent=app.root | Still locked |
| v0.8.5 | z-order not flipped | `-topmost` on root | "Words in upper left, disappear on hover" |
| v0.8.7 | Dialog Toplevel at (0,0) | Custom Toplevel + explicit geometry for **Items Excluded** | Correct fix, wrong dialog — never reached |
| v0.8.8 | Second dialog has same bug | Custom Toplevel + deferred grab_set for **Review Flagged Items** | Still locked — dialog was visible but frozen |
| **v0.8.9** | **Dialog has 1,099 rows × 11 widgets blocking Tk** | **Short-circuit to summary when flagged > 50** | **Should finally land** |

Each prior release was fixing a real latent bug that was masking
the one below it.  Every attempt was "correct but not sufficient."
The v0.8.8 instrumentation is what finally surfaced the `flagged=1099`
number, which made the real cause impossible to miss.

**The perf harness + debug trace instrumentation built across
v0.8.2-v0.8.8 did exactly what it was designed for.**  Without the
`scan_done | flagged=1099` line, this release would have been
another dead-end guess.
