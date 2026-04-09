# Release Notes — v0.8.3

**Date:** 2026-04-08

---

## Summary

v0.8.3 fixes the **"Remove Unassigned & Go to Review locks up"** bug
the operator reported.  The app wasn't actually frozen — the "Items
Excluded" messagebox was being opened *after* the tab switch to Review
and without an explicit `parent=app.root`, so on Windows Tk builds it
landed behind the freshly-activated Review tab with an active modal
`grab_set` but no visible surface.  Clicks on the main window belled
silently and the app looked dead.

1107 tests pass (1 new regression test).

---

## The bug

Exact sequence in `ui_bulk_dialogs.finish_bulk_final`:

```python
# OLD ORDER
app._populate_review_tab()
app.notebook.tab(5, state="normal")
app.notebook.select(5)                          # ← tab switches here

if skip_parts:
    messagebox.showinfo(
        "Items Excluded",
        f"Excluded from PO: {', '.join(skip_parts)}.",
    )                                           # ← fires AFTER tab switch,
                                                #   WITHOUT parent=app.root
```

Two problems stacked on top of each other:

1. **No explicit `parent=`**: `messagebox.showinfo` without a parent
   falls back to the default root, which after `notebook.select(5)`
   has reparented focus into the Review tab's widget tree.  Tk then
   creates the dialog Toplevel as a child of something other than the
   user-visible main window.
2. **The grab is alive but the surface is hidden**: the
   messagebox applies a `grab_set` to its new Toplevel, so clicks on
   the main window are absorbed into the void.  The operator sees
   "the app is frozen."

The "Unresolved Reviews" `askyesno` dialog earlier in the same
function had the same missing-parent issue, but in practice it was
rarely hit because most operators resolve reviews before clicking
Remove Unassigned.

---

## The fix

Two changes in `ui_bulk_dialogs.finish_bulk_final`:

1. **Show the "Items Excluded" dialog BEFORE `notebook.select(5)`.**
   The notice is informational — it doesn't need to wait for the
   tab switch.  Showing it while the Bulk tab is still focused means
   the dialog has a stable parent and is guaranteed to land on top.
2. **Pass `parent=app.root` on every messagebox in the function**
   (`askyesno` for unresolved reviews, `showwarning` for no items,
   `showinfo` for items excluded).  This ensures the dialogs stay
   modal to the main window and can't be orphaned by any focus shift
   between invocation and destruction.

```python
# NEW ORDER
if hasattr(app, "_annotate_release_decisions"):
    app._annotate_release_decisions()

if skip_parts:
    messagebox.showinfo(
        "Items Excluded",
        f"Excluded from PO: {', '.join(skip_parts)}.",
        parent=app.root,                        # ← explicit parent
    )                                           # ← and shown FIRST

app._populate_review_tab()
app.notebook.tab(5, state="normal")
app.notebook.select(5)                          # ← then switch tabs
```

---

## Regression test

`tests/test_ui_bulk_dialogs.py::test_finish_bulk_final_items_excluded_dialog_fires_before_tab_switch`
builds a fake app with one assigned row and one unassigned row (so
"Items Excluded" is triggered), patches `messagebox.showinfo` to
record the call order, and asserts:

1. The dialog is invoked exactly once
2. `parent=app.root` is passed explicitly
3. The dialog is invoked *before* `notebook.select(5)` in the event
   stream

The test will fail loudly if any future refactor re-introduces the
bad ordering.

---

## Files changed

- `ui_bulk_dialogs.py` — `finish_bulk_final` reordered + every
  messagebox now carries `parent=app.root`
- `tests/test_ui_bulk_dialogs.py` — new regression test + the existing
  test fake gained a `root=None` attribute for the parent kwarg
- `app_version.py` — bumped to 0.8.3

---

## What this release does NOT fix

Next on the list from the v0.8.2 perf harness findings:
- **`prepare_assignment_session` 16.8 s surprise** — the harness
  showed it's ~3× slower than the pre-harness audit estimate, and
  finer-grained spans in a future release will pinpoint which stage
  is super-linear.

The bug the operator reported was urgent and independent of the perf
work, so v0.8.3 ships the fix immediately.  v0.8.4 will dig into the
perf hotspot.
