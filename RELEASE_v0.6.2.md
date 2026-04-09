# Release Notes — v0.6.2

**Date:** 2026-04-08

---

## Summary

v0.6.2 closes Phase 3 of the v0.6.x roadmap: **QOH Adjustment Review**.
Operators can now see every QOH edit they've made in the current session
and revert any of them in one click before exporting.

970 tests pass (12 new regression tests).

---

## What's new

### QOH Adjustments dialog

A new **QOH Changes...** button on the bulk tab removal row opens a
dialog showing every QOH edit made during the current session:

- **Columns**: Line Code, Item Code, Description, Old QOH, New QOH, Delta.
- **Sorted** by `(line_code, item_code)` so related parts cluster.
- **Zero-delta entries are dropped** — the operator only sees edits
  that actually changed something.
- **Revert Selected** restores the original QOH on every selected row,
  drops the adjustment entry, re-runs per-item recalculation so
  downstream order quantities snap back to their pre-edit
  suggestions, and refreshes the bulk grid + summary.
- Empty state shows "No adjustments this session".

---

## Architecture

`qoh_review_flow.py` (new) hosts two pure helpers, both unit-tested
without a UI:

- `format_qoh_adjustments(qoh_adjustments, inventory_lookup)` — turns
  the session's `{(line_code, item_code): {"old": float, "new": float}}`
  dict into a sorted list of review-friendly row dicts.  Cross-references
  `inventory_lookup` for the description, drops zero-delta rows, and
  tolerates non-mapping payloads.
- `revert_qoh_adjustments(adjustments, inv_lookup, keys)` — pure revert
  helper.  Mutates both dicts (restores `inv["qoh"]` to the original
  value, pops the adjustment entry) and returns the count actually
  reverted.  Missing keys are a no-op.  The caller handles
  per-item recalculation and grid refresh — keeping that out of the
  helper makes it trivially testable.

`ui_qoh_review.py` (new) wires the helpers into the dialog and the
bulk grid.  The dialog reads the live `qoh_adjustments` dict, so
opening it after a revert reflects the new state immediately.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.6.1  |   958 |
| v0.6.2  |   970 |

12 new regression tests in `tests/test_qoh_review_flow.py` covering
normal cases, zero-delta filtering, sort order, missing inventory
lookup, negative delta, non-numeric coercion, non-mapping payload
guard, and the full revert flow (single key, multi-key, missing key,
empty input).

---

## Files changed / added

- `qoh_review_flow.py` (new) — pure helpers
- `ui_qoh_review.py` (new) — dialog
- `ui_bulk.py` — "QOH Changes..." button on the removal row
- `po_builder.py` — `_open_qoh_review` hook + import
- `tests/test_qoh_review_flow.py` (new) — 12 regression tests
- `app_version.py` — bumped to 0.6.2
- `ROADMAP_v0.6.md` — Phase 3 closed

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Bulk Grid Text Search | ✓ closed (v0.6.0) |
| Phase 2 — Supplier → Vendor Auto-mapping | ✓ closed (v0.6.1) |
| Phase 3 — QOH Adjustment Review | ✓ closed (v0.6.2) |
| Phase 4 — Ordering Algorithm Fixes | ✓ closed (v0.5.5) |
| Phase 4b — Parser/Min/Max bugs | ✓ closed (v0.5.5) |
| Phase 4c — Bulk Removal Edge Cases | ✓ closed (v0.5.4) |
| Phase 5 — Manual QA | carry-over (intentionally manual) |

**Every coded item on the v0.6.x roadmap is now closed.**  The only
remaining bullet is Phase 5 (Manual QA pass against real-world data),
which is by definition not something the harness can run.
