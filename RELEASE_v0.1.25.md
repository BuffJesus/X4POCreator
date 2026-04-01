# Release Notes — v0.1.25

**Date:** 2026-04-01

---

## Summary

This release delivers three focused improvements across reorder logic, the detailed-sales pipeline, and the bulk editor's edit-integrity and undo/history model.

---

## Phase 4 — Reorder floor / operational target separation

**Problem:** When a trigger threshold (e.g. `minimum_packs_on_hand = 2` with pack size 100) sat above the operational `target_stock`, `calculate_raw_need()` inflated `effective_target_stock` to the trigger level. This caused the displayed ordering target to look like the safety floor rather than the preferred operational ceiling, and caused `assess_post_receipt_overstock()` to compare against an artificially raised target.

**Fix:**

- `effective_target_stock` now always equals the preferred operational target (`target_stock`). It is never inflated.
- A new `effective_order_floor` field = `max(target_stock, trigger_threshold)` is the quantity basis for the actual order when a trigger fires. This is what `calculate_raw_need()` and `assess_post_receipt_overstock()` use for computation.
- The `why` text now reads `Effective reorder floor: X` from `effective_order_floor` rather than from `effective_target_stock`, so the label only appears when the floor genuinely differs from the preferred target.
- The "remove not needed" dialog (`ui_bulk_dialogs.py`) uses `effective_order_floor` to decide whether inventory position already meets the order basis, preserving correct removal protection for trigger-driven items.

**Impact:** No change in ordering quantities or trigger behavior. Only the stored field semantics and display are corrected.

---

## Phase 2A — Detailed-sales auto-apply for `detailed_only` gap (completed previous session)

Already shipped — `detailed_only` items (X4 has no suggestion but detailed sales does) now have the detailed suggestion auto-promoted to the active suggestion, except when `detailed_fallback_suppressed_reason == "receipt_heavy"`. Legacy `Part Sales & Receipts` parser path fully removed.

---

## Phase 8 — Bulk editor integrity and undo/history boundary hardening

Three targeted fixes to the bulk editor's edit-commit and undo/redo paths:

### 1. Undo/redo now flushes pending edits first

**Problem:** If the user made a cell edit and then pressed Ctrl+Z before the async `after(1, ...)` post-edit callback had fired, the undo operation captured and restored state before the edit committed — then the `after(1, ...)` callback fired afterward and re-applied the edit on top of the restored state. Net result: Ctrl+Z appeared to do nothing.

**Fix:** `_bulk_undo()` and `_bulk_redo()` in `po_builder.py` now call `bulk_sheet.flush_pending_edit()` as their first action, draining any queued edit before capturing or restoring history state.

### 2. Filter refresh creates a new history epoch

**Problem:** When a filter or sort was applied (re-rendering `set_rows()`), history entries from before the render could coalesce with entries from after it (same `selection_serial`), causing unrelated edits to merge into a single undo operation.

**Fix:** `BulkSheetView.set_rows()` now increments `_selection_serial` whenever the sheet data actually changes. This ensures any edit started before a filter refresh cannot coalesce with edits started after it.

### 3. Row re-lookup by stable ID in post-edit callback

**Problem:** `_run_post_edit_refresh()` read sheet cell data using the positional `row` index captured at edit time. If the sheet was re-rendered between the edit event and the async callback (e.g. by a concurrent selection change), the positional index could point to a different row, producing incorrect debug log output.

**Fix:** Before reading cell data for comparison, the callback now re-looks up the live row position from `row_lookup` using the stable `row_id`. The actual edit commit still uses stable `target_row_ids` and was never affected; only the verification/debug read path is corrected.

---

## Test coverage

- 4 new tests in `tests/test_bulk_cell_selection.py`:
  - `test_bulk_undo_flushes_pending_edit_before_restoring`
  - `test_bulk_redo_flushes_pending_edit_before_restoring`
  - `test_set_rows_bumps_selection_serial_on_data_change`
  - `test_set_rows_does_not_bump_selection_serial_when_rows_unchanged`
- Updated 3 tests in `tests/test_rules.py` to assert `effective_order_floor` and `effective_target_stock` separately
- Updated 1 test in `tests/test_ui_bulk_dialogs.py` to use the new field structure

**Total test count:** 693 (all passing)

---

## Upgrade

Replace `POBuilder.exe` with the new build. No data-file migration required. `order_rules.json`, `vendor_codes.txt`, and all session snapshots are fully compatible.
