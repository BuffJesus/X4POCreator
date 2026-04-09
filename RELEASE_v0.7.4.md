# Release Notes — v0.7.4

**Date:** 2026-04-08

---

## Summary

v0.7.4 closes the **Phase 4 cache invalidation audit** with one real
fix.  Three flows in `reorder_flow.py` (`refresh_suggestions`,
`normalize_items_to_cycle`, `refresh_recent_orders`) mutate
`filtered_items` in place and then call `_apply_bulk_filter` —
without rebuilding the bulk grid's bucket index in between.  When a
recalculation flipped an item's status, attention, or other
bucket-driving field, the next bulk filter pass returned the **old**
buckets via the fast path.

This is the same family of bugs as v0.6.3 / v0.6.4 / v0.6.5, but on
a different surface — the *recalc* paths instead of the *edit* paths.

1059 tests pass (1 new regression test).

---

## The bug

`refresh_suggestions`, `normalize_items_to_cycle`, and
`refresh_recent_orders` all loop over `app.filtered_items` and call
`_recalculate_item` per item.  The recalc may shift `status`,
`recency_confidence`, `data_flags`, `stockout_risk_score`, and other
fields that drive the Item Status / Attention bucket index.

But the items are mutated **in place** — the same list object — so
`replace_filtered_items` (which is the only caller of
`sync_bulk_session_metadata`) is never invoked.  The bucket index
keeps the old labels.

`_apply_bulk_filter` then runs and uses the bucket fast path
(`filtered_candidate_items`), reading the stale buckets.  Operators
who triggered a cycle change or a History (days) change would see
the bulk grid filter on data that didn't match what the items
actually said anymore — until the next full session reload reset
everything.

**Verified before fix** with a small probe: an item with
`status=review`, sync metadata to bucket it under "Review", flip
`status="ok"` in place, and the bucket index still reports it under
"Review" with no membership in "OK".

---

## The fix

New helper `_rebuild_bulk_metadata_after_inplace_recalc(app)` in
`reorder_flow.py` calls `ui_bulk.sync_bulk_session_metadata` and
`ui_bulk.sync_bulk_cache_state(filtered_items_changed=True)` to
rebuild the bucket index and invalidate the per-filter result cache.

The helper is called at the end of all three offending flows, just
before `_apply_bulk_filter`:

- `refresh_suggestions` — fires when the operator changes the
  Reorder Cycle dropdown.
- `normalize_items_to_cycle` — fires once after
  `assignment_flow.prepare_assignment_session`.
- `refresh_recent_orders` — fires when the operator edits the
  History (days) spinbox or hits Enter / Tab on it.

**Verified after fix** with the same probe: the rebuild correctly
moves the item from "Review" to "OK".

---

## Tests

| Release | Tests |
|---------|-------|
| v0.7.3  |  1058 |
| v0.7.4  |  1059 |

One new test in `tests/test_reorder_flow.py`:
`test_rebuild_bulk_metadata_after_inplace_recalc_refreshes_buckets`.

---

## Related — the matcher/bucket bug family

This is the **fifth** matcher-vs-fast-path drift fix in the
v0.6.x / v0.7.x sequence.  All five share the same root cause:
the bulk grid's bucket index is a write-once snapshot, and any
in-place mutation that should change a bucket needs to explicitly
rebuild the index.

| Release | Layer | Symptom |
|---|---|---|
| v0.6.3 | `bulk_item_status` | skip + missing_pack hidden under No Pack |
| v0.6.4 | `bulk_attention_bucket` | High Risk filter empty |
| v0.6.4 | `uses_only_bucket_filters` | Text search bypassed by fast path |
| v0.6.5 | (audit + permanent guard) | catches future drift via test fixture |
| v0.6.6 | `bulk_row_render_signature` | stale Risk column after recalc |
| v0.7.4 | `reorder_flow` recalc paths | stale bucket index after in-place recalc |

The v0.6.5 audit guard wouldn't have caught this one because it
exercises the *bucket helpers* against a fixture, not the *callers*
that mutate items in place.  Worth doing a follow-up audit pass that
also covers in-place mutation paths — added as a Phase 4 carry-over
in the roadmap.

---

## Files changed

- `reorder_flow.py` — new `_rebuild_bulk_metadata_after_inplace_recalc`
  helper, called from all three in-place recalc flows
- `tests/test_reorder_flow.py` — regression test
- `app_version.py` — bumped to 0.7.4

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed (v0.7.0) |
| Phase 2 — Vendor-centric Workflows | ✓ closed (v0.7.1 + v0.7.3) |
| Phase 3 — Skip Cleanup Tools | ✓ closed (v0.7.2) |
| Phase 4 — Performance & Correctness Carry-over | partially closed |

Phase 4 still has the pack-rounding overshoot defer (behind a flag),
the bulk grid render perf audit on 8,409 items, and the Phase 5
manual QA pass.  This release closes the cache audit subitem.
