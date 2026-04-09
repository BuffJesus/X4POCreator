# Release Notes — v0.8.13

**Date:** 2026-04-09

---

## Summary

**Critical bug fix: cell edits on the bulk grid were not displaying.**
Values were applied to the data model but the grid showed stale
pre-edit values because the render cache was not evicted for edited
rows.  A second fix corrects an invalid tksheet binding name that
prevented inline cell editing from working at all.  This release also
adds Ctrl+F to focus the bulk search box and deeper perf
instrumentation for the next optimization pass.

1120 tests pass (10 new for item_notes_flow).

---

## Bug fix 1: edited values not displaying (primary issue)

### Symptom

Editing a cell on the Assign Vendors bulk grid (vendor, pack_size,
etc.) via the dialog prompt applied the value to the data model, but
the grid continued to show the old value.  The edit was silently
correct underneath — exports and session snapshots would have the
right data — but the operator couldn't see the change.

### Root cause

`refresh_bulk_view_after_edit` (ui_bulk.py) called
`cached_bulk_row_values(app, item)` to get the rendered row tuple.
The render cache is generation-keyed (v0.8.10 optimization): entries
are `(generation, values)` and a hit just compares two ints.  But
single-item edits never bumped the generation counter and never evicted
the specific row from the cache.  Result: every edit-time refresh
returned the stale pre-edit tuple.

### Fix

Before rendering each edited row, evict its cache entry so
`cached_bulk_row_values` recomputes from the updated item dict:

```python
cache = _bulk_row_render_cache(app)
for row_id in row_ids:
    idx, item = resolve_bulk_row_id(app, row_id)
    ...
    cache.pop(bulk_row_id(item), None)   # <-- new
    app.bulk_sheet.refresh_row(effective_row_id, cached_bulk_row_values(app, item))
```

Targeted per-row eviction, not a full generation bump — no perf
regression on the 59K-item dataset.

---

## Bug fix 2: inline cell editing callback (secondary)

### Root cause

The tksheet inline-edit callback was registered with `"end_edit_table"`,
which is not a valid binding name in tksheet 7.5.19.  The call silently
did nothing — `_handle_edit` was never registered.

### Fix

Changed to `"end_edit_cell"` in `bulk_sheet.py:102`.  Also added a
`begin_edit_cell` callback for diagnostic logging.

Note: inline cell editing was already supplemented by the dialog-prompt
path (Double-click / F2 / Return → `bulk_begin_edit` → `askstring`),
which is why editing appeared functional in earlier versions despite the
broken binding.

---

## New features (Roadmap Phase 1b + 1c)

### Click column header to sort + ▲/▼ arrows

Clicking any column header sorts the bulk grid by that column.
Clicking again reverses the direction.  The sorted column header
shows ▲ (ascending) or ▼ (descending).  Sort state persists across
filter changes and is saved to settings.

### Double-click column header to auto-size

Double-clicking any column header auto-sizes all columns to fit the
window width, distributing space based on content.

### Enter key opens View Item Details

Pressing Enter on the bulk grid now opens the item details dialog
instead of the edit dialog.  F2 and double-click still open the editor.

### Ctrl+F global shortcut

When on the Assign Vendors tab, pressing Ctrl+F focuses the text
search entry and selects its contents.

### Per-item notes column (Phase 1c)

New editable **Notes** column on the bulk grid, placed after "Why
This Qty".  Notes are persisted to `item_notes.json` keyed by
`LC:IC`, loaded on startup, and included in the exported vendor
xlsx when any item has a note.  Backed by `item_notes_flow.py` with
10 new unit tests.

---

## Perf instrumentation additions

Substep stamps added to two of the remaining top-4 targets from the
live trace, preparing for the next optimization pass:

- **`bulk_remove_flow._remove_filtered_rows_inner`** — new
  `capture_history` span around the undo snapshot (suspected deepcopy
  bottleneck at 6.5 s on the 63K-item dataset) and a `loop_done`
  stamp with removed/protected/skipped counts.
- **`ui_bulk_dialogs._finish_bulk_final_inner`** — new
  `row_build_start` / `row_build_done` stamps bracketing the
  assigned-items loop, and an `annotate_release_decisions` span.

Substep stamps in `parse_detailed_pair_aggregates` now log row
counts and timing for the sales pass vs. receipts pass separately.

---

## Bug fix 3: multi-row selection lost on F2/double-click

Drag-selecting multiple cells and pressing F2 only edited the first
row.  `selected_target_row_ids` checked the snapshot (overwritten by
intermediate `cell_select` events) before the live selection.  Fixed
to check the live `get_selected_cells()` first, which preserves the
full drag range.

---

## Performance: batched bulk edit persistence

Editing multiple rows at once (e.g., setting pack_size on 10 rows)
was ~7 s because each row individually:
- Wrote `order_rules.json` to disk (for pack_size edits)
- Ran `annotate_release_decisions` over all ~59K items

Now deferred to a single call after the loop via `_bulk_apply_and_flush`.
Measured: **8-row pack_size edit ~5.6 s → ~750 ms** (7.5x faster).

### Per-row-id undo snapshot for bulk remove

`bulk_remove_flow` now passes the removal indices to the history
capture spec, so `capture_bulk_history_state` deepcopies only the
affected rows instead of all ~59K `filtered_items`.  Expected
improvement: **~6.5 s → < 50 ms** on the 63K-item dataset.

---

## Dependency pinning

`requirements.txt` now pins `tksheet>=7.5.19` to prevent silent
binding-name regressions if a future tksheet release changes the
registry again.

---

## Files changed

- `ui_bulk.py` — evict stale render-cache entries for edited rows in
  `refresh_bulk_view_after_edit`; invalidate visible-rows and
  filter-result caches before any refresh path
- `bulk_sheet.py` — fix `end_edit_table` -> `end_edit_cell` binding;
  suppress inline editor via `begin_edit_cell` returning None;
  fix multi-row selection in `selected_target_row_ids` to prefer
  live cell selection over snapshot
- `bulk_sheet_actions_flow.py` — new `_bulk_apply_and_flush` helper
  that defers `_save_order_rules` and `annotate_release_decisions`
  to a single call after the multi-row loop
- `bulk_edit_flow.py` — `apply_editor_value` accepts `defer_save`
  flag to skip per-row persistence and release annotation
- `po_builder.py` — `_bulk_apply_editor_value` passes through
  `defer_save`; add `_global_ctrl_f_handler` + Ctrl+F bind_all
- `bulk_remove_flow.py` — add `capture_history` span + `loop_done`
  stamp
- `ui_bulk_dialogs.py` — add `row_build_start` / `row_build_done`
  stamps + `annotate_release_decisions` span
- `requirements.txt` — pin `tksheet>=7.5.19`
- `app_version.py` — bumped to 0.8.13
- `VERSION` — synced to 0.8.13
- `CLAUDE.md` — version reference updated

---

## What to test

1. Drop v0.8.13 in place of v0.8.12.
2. Load a session and go to Assign Vendors.
3. **Double-click a vendor cell, type a vendor code, press Enter** —
   the value should stick.  Repeat for pack_size and final_qty.
4. **Press Ctrl+F** — the search box should focus with its text
   selected.
5. Keep `perf_trace.enabled` in place.  After a full session, send
   `perf_trace.jsonl` — the new substep stamps will show where
   `remove_filtered_rows` and `finish_bulk_final` spend their time.

---

## Release history

| Release | Headline |
|---|---|
| v0.8.9 | Dialog lock-up fix (short-circuit >50 flagged items) |
| v0.8.10 | normalize_items_to_cycle eliminated (-23 s) |
| v0.8.11 | Full span instrumentation of prepare_assignment_session |
| v0.8.12 | O(n^2) description scan eliminated (-29 s) |
| **v0.8.13** | **Cell editing fix + header sort/autosize + bulk edit perf (7s→0.75s)** |
