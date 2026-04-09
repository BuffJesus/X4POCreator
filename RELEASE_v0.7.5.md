# Release Notes — v0.7.5

**Date:** 2026-04-08

---

## Summary

v0.7.5 is the **follow-up audit** the v0.7.4 release notes called for.
v0.7.4 fixed three in-place recalc paths in `reorder_flow.py`; this
release finds the **fourth** instance of the same bug pattern (in
`data_folder_flow.refresh_active_data_state`) and promotes the fix
helper to the canonical home in `ui_bulk.py` so future callers get
the same guarantee for free.

1061 tests pass (2 new regression tests).

---

## Fix

### `data_folder_flow.refresh_active_data_state` left bucket index stale

When the operator clicks "Refresh Active Data" on the Load tab,
`refresh_active_data_state` mutates `app.filtered_items` in place
(rebuilding pack-size + rule lookups, calling `_recalculate_item`)
and then triggers `_apply_bulk_filter`.  Same bug as the three
`reorder_flow` fixes in v0.7.4 — the bulk grid bucket index never
gets rebuilt, so a recalc that flips an item's status / data_flags /
attention bucket leaves the next filter pass reading stale buckets.

This is the *fourth* instance of the v0.6.3 / v0.6.4 / v0.7.4 family
of bugs.

**Fix:** call the canonical rebuild helper at the end of the recalc
loop, before `_apply_bulk_filter`.

### Helper promoted to canonical home

The `_rebuild_bulk_metadata_after_inplace_recalc` helper that v0.7.4
introduced in `reorder_flow.py` now lives in `ui_bulk.py` as
`rebuild_bulk_metadata_after_inplace_recalc` (no underscore prefix —
it's part of the public bulk-grid contract now).  The
`reorder_flow.py` symbol is kept as a thin shim so v0.7.4 callers
keep working without churn.

The helper rebuilds the bucket index via
`sync_bulk_session_metadata` and invalidates the per-filter result
cache via `sync_bulk_cache_state(filtered_items_changed=True)`.

**Any future flow that mutates `filtered_items` in place must call
this helper before `_apply_bulk_filter`.**  The release notes are
the contract; the docstring on the helper repeats it.

---

## Audit clean-up

I re-walked every `_recalculate_item` caller to confirm there are no
other instances:

| Caller | Status |
|---|---|
| `bulk_edit_flow.bulk_apply_editor_value` (vendor / final_qty / qoh / cur_min / cur_max / pack_size) | ✓ single-item; goes through `refresh_bulk_view_after_edit` → `adjust_bulk_summary_for_item_change` which already updates buckets correctly |
| `data_folder_flow.refresh_active_data_state` | ✓ **fixed in this release** |
| `reorder_flow.refresh_suggestions` | ✓ fixed in v0.7.4 |
| `reorder_flow.normalize_items_to_cycle` | ✓ fixed in v0.7.4 |
| `reorder_flow.refresh_recent_orders` | ✓ fixed in v0.7.4 |
| `ui_qoh_review` revert path | ✓ single-item per revert; the dialog calls `_apply_bulk_filter` after the loop, but the per-item bucket adjustment is implicit because no field that drives the bucket index changes (only QOH on the inventory record) |

So the matcher/fast-path drift family is now fully closed across all
known mutation paths.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.7.4  |  1059 |
| v0.7.5  |  1061 |

Two new tests in `tests/test_ui_bulk.py::RebuildBulkMetadataAfterInplaceRecalcTests`:

- Status flip (review → ok) refreshes Item Status buckets
- Risk score flip (0.1 → 0.9) refreshes Attention buckets including
  the additive `High Risk` tag

These exercise the canonical `ui_bulk` helper directly, so any
future caller (no matter where it lives) inherits the same coverage.

---

## Files changed

- `ui_bulk.py` — new public `rebuild_bulk_metadata_after_inplace_recalc` helper
- `reorder_flow.py` — `_rebuild_bulk_metadata_after_inplace_recalc` is now a
  thin shim that delegates to `ui_bulk`
- `data_folder_flow.py` — `refresh_active_data_state` now rebuilds
  the bucket index after the recalc loop
- `tests/test_ui_bulk.py` — two new regression tests
- `app_version.py` — bumped to 0.7.5

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed |
| Phase 2 — Vendor-centric Workflows | ✓ closed |
| Phase 3 — Skip Cleanup Tools | ✓ closed |
| Phase 4 — Performance & Correctness Carry-over | further closed (cache audit + audit follow-up) |

Phase 4 still has the pack-rounding overshoot defer (behind a flag),
the bulk grid render perf audit on 8,409 items, and the Phase 5
manual QA pass.  Cache invariant audit is now done across every
known caller.
