# Release Notes — v0.2.0

**Date:** 2026-04-01

---

## Summary

v0.2.0 is the first stable release of the v0.2.x line. All code items in the consolidated roadmap are complete. The release satisfies every criterion in the "Definition of Done Enough for v0.2.x":

- Reorder behavior is explainable for pack, reel, hardware, confidence, and shipping cases.
- Reorder-worthy items are not silently lost due to source gaps, stale row state, or over-aggressive removal paths.
- Shared/local persistence behavior is operationally trustworthy.
- Shipping policy affects the release workflow, not just display text.
- Bulk editor rapid-edit correctness is no longer a known risk.
- Packaged update flow is safe enough for end users to rely on.

The two remaining open items in Phase 1 (smoke-testing the packaged `.exe` with representative real-world CSVs) are manual QA steps, not code gaps. They do not block this release.

---

## What changed since v0.1.24

The v0.2.0 line was built across v0.1.24 → v0.1.25 → v0.2.0. The full set of changes since v0.1.24:

### Detailed-sales pipeline (Phase 2A, completed in v0.1.25)

- **Legacy parser removed.** The `Part Sales & Receipts` combined CSV path (`parse_part_sales_csv`, `parse_sales_date_range`) is gone. The `DETAILED PART SALES.csv` + `ReceivedPartsDetail.csv` pair is now the only supported load path.
- **Auto-apply for `detailed_only` gap.** When X4 has no `mo12_sales`-driven suggestion but detailed sales data suggests stocking, the detailed suggestion is now automatically promoted to the active suggestion and the item is routed to review. Exception: when `detailed_fallback_suppressed_reason == "receipt_heavy"`, the promotion is suppressed and the item enters review as blank-suggestion only.
- **`detailed_fallback_suppressed_reason` field.** Set at suggestion-compute time in `reorder_flow.apply_suggestion_context()` so downstream review-state logic can distinguish receipt-heavy suppression from genuine data absence without re-querying the balance at the wrong execution phase.

### Reorder floor / target separation (Phase 4, completed in v0.1.25)

- **`effective_target_stock` is never inflated.** It always equals `target_stock` (the preferred operational target). Previously, `calculate_raw_need()` inflated it to `trigger_threshold` when the trigger sat above the target, producing misleading display values.
- **New `effective_order_floor` field.** Equals `max(target_stock, trigger_threshold)`. This is what `calculate_raw_need()`, `assess_post_receipt_overstock()`, and the "remove not needed" dialog use for order-quantity computation and overstock assessment.
- **`why` text corrected.** The `Effective reorder floor: X` detail line now reads from `effective_order_floor` and only appears when the floor genuinely differs from the preferred target.
- **No ordering-quantity change.** Computed order quantities are identical to before; only field semantics and display are corrected.

### Bulk editor integrity (Phase 8, completed in v0.1.25)

- **Undo/redo now flush pending edits first.** `_bulk_undo` and `_bulk_redo` call `flush_pending_edit()` before touching history state. Previously, pressing Ctrl+Z while an `after(1,...)` commit was queued caused the undo to restore state, then the queued commit re-applied the edit on top — making undo appear broken.
- **Filter refresh creates a new history epoch.** `BulkSheetView.set_rows()` bumps `_selection_serial` whenever data changes. Edits before a filter refresh can no longer coalesce into the same undo entry as edits after it.
- **Stale row-position guard.** The post-edit callback re-resolves row position via `row_lookup[row_id]` before reading cell data for debug comparison, avoiding wrong-cell reads after async re-renders.

---

## Test coverage

**693 tests, all passing.**

New tests added since v0.1.24:
- `test_apply_suggestion_gap_review_state_applies_detailed_suggestion_when_detailed_only`
- `test_apply_suggestion_gap_review_state_does_not_apply_when_receipt_heavy_suppressed`
- `test_bulk_undo_flushes_pending_edit_before_restoring`
- `test_bulk_redo_flushes_pending_edit_before_restoring`
- `test_set_rows_bumps_selection_serial_on_data_change`
- `test_set_rows_does_not_bump_selection_serial_when_rows_unchanged`

---

## Open items (non-blocking)

These two Phase 1 items remain open and require manual QA with real-world CSV files:

- Add stronger packaged `.exe` smoke-test evidence for the full user workflow.
- Confirm release-candidate workflow coverage from load through export at the packaged-app level.

---

## Upgrade

Replace `POBuilder.exe` with the new build. No data-file migration required. All existing `order_rules.json`, `vendor_codes.txt`, `vendor_policies.json`, and session snapshots are fully compatible.

The one behavioral change that may be visible: items with a trigger threshold above their operational `target_stock` will now show `Target stock: N` (the real target) rather than the inflated trigger value in their `why` detail, and will show a separate `Effective reorder floor: M` line. Order quantities are unchanged.
