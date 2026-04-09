# Release Notes — v0.8.1

**Date:** 2026-04-08

---

## Summary

v0.8.1 closes two concrete UX issues the operator flagged while
reviewing v0.8.0:

1. **Delete key didn't remove rows** — the handler existed but was
   never bound to any key on the sheet.
2. **The right-click context menu stuck out in default gray** —
   pure-tk `tk.Menu` doesn't inherit ttk theming, so the menu was
   cream-on-gray on every other operation while the rest of the app
   is dark purple.

1083 tests pass (1 new regression test).

---

## Fixes

### Delete key removes selected rows (`bulk_sheet.py`)

The right-click context menu's "Remove Selected Rows" handler
already worked on non-contiguous multi-row selections — the data
path reads `get_selected_rows()` which is a set and honors
ctrl-click selection.  But no key on the sheet was bound to invoke
it, so Delete did nothing in practice.

**Fix:** a new `_bind_row_delete_keys()` method disables tksheet's
internal Delete capture, then binds `<Delete>` and `<KP_Delete>`
on the Sheet composite plus its internal MainTable / RowIndex /
ColumnHeader children.  Every surface the key could land on routes
to the existing `bulk_delete_selected` handler.

**Behavior after the fix:**

- Click a row number → press Delete → that row is removed.
- Ctrl-click several row numbers (non-contiguous) → press Delete →
  all of them are removed.  Matches the operator's muscle memory
  exactly.
- Shift-click a row number range → press Delete → range removed.
- Cell selection → press Delete → cell contents cleared (unchanged
  behavior; matches Excel).
- No selection → no-op.

Same confirmation dialog, same history capture, same undo.  The
change is purely the missing key binding.

### Themed right-click context menu (`bulk_sheet.py`)

`tk.Menu` is one of the last classic (non-ttk) widgets the app
still touches.  It doesn't pick up ttk style settings at all, so
the context menu rendered in the OS default gray on top of the
app's dark purple theme.

**Fix:** the context menu is now constructed with explicit
`bg`, `fg`, `activebackground`, `activeforeground`, `bd`, and
`font` options pulled from a local palette that matches the clam
theme block in `po_builder.py`:

```python
_CONTEXT_MENU_BG        = "#2a2a40"
_CONTEXT_MENU_FG        = "#d6d6e5"
_CONTEXT_MENU_ACTIVE_BG = "#5b4670"   # PURPLE_DARK
_CONTEXT_MENU_ACTIVE_FG = "#ffffff"
```

Flat relief, `tearoff=0`, `Segoe UI 10` font to match everywhere
else.  The menu now visually belongs to the app.

---

## Architecture

Two small additions to `BulkSheetView` in `bulk_sheet.py`:

- `_bind_row_delete_keys()` — idempotent (add="+"), tolerant of
  tksheet versions that don't expose every child widget (try/except
  per target).  Logs to `write_debug` on handler errors so a future
  tksheet API change doesn't silently swallow Delete.
- Context menu construction uses the local dark-theme palette
  constants at the top of the module.

Nothing else changed.  The existing confirmation flow, history
capture, undo path, and `bulk_delete_selected` routing are
unchanged.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.8.0  |  1082 |
| v0.8.1  |  1083 |

One new regression test in
`tests/test_bulk_cell_selection.py::test_bulk_delete_selected_removes_multiple_noncontiguous_rows`.
Builds a fake sheet with `explicit_selected_row_ids=("0", "2", "4")`
and asserts that after `_bulk_delete_selected` runs, exactly rows
at indices 0, 2, 4 are gone and rows 2, 4 remain (in item_code
terms: `["2", "4"]` remain from `["1","2","3","4","5"]`).

The existing two delete-selection tests still cover the
single-row explicit-selection case and the current-row fallback
case.

---

## Files changed

- `bulk_sheet.py` — themed context menu + Delete key wiring
- `tests/test_bulk_cell_selection.py` — non-contiguous multi-row
  regression test
- `app_version.py` — bumped to 0.8.1

---

## What's still open in the UX modernization plan

| Phase | Status |
|---|---|
| 1 — Help tab rebuild | ✓ closed (v0.8.0) |
| 2 — Bulk grid Excel/Sheets polish | **in progress** |
| 2a — Click header to sort | open — biggest remaining muscle-memory miss |
| 2b — Sheet perf on 59K items | open — filter changes ~640ms today |
| 2c — Per-item notes column | open |
| 3-5 — Toolbar / Load tab / Review tab | planning |

v0.8.1 cleans up two concrete irritants; v0.8.2 will be the
click-header-to-sort fix (plus sort-direction arrows in the header
text), which I expect to be the single biggest remaining
muscle-memory win.
