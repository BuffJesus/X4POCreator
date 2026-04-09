# Release Notes — v0.6.5

**Date:** 2026-04-08

---

## Summary

v0.6.5 is a quality release: a systematic audit confirmed that every
single-dim and two-dim filter combination in the bulk grid produces the
same set of items via the matcher and the bucket fast path on the
user's real `Order/` dataset.  No code changes — just a permanent
regression test that bakes the audit into the test suite so the
v0.5.4 / v0.6.3 / v0.6.4 family of bugs cannot silently come back.

983 tests pass (1 new audit test).

---

## What I checked

After fixing four matcher/fast-path inconsistencies across v0.5.4,
v0.6.3, and v0.6.4, I wanted to be sure no others were lurking.

I built an audit script that, for every value in every Item Status /
Assignment Status / Source / Performance / Sales Health / Attention
filter, runs both the matcher (`item_matches_bulk_filter`) and the
fast bucket path (`filtered_candidate_items`) against the user's real
8,409-item `Order/` dataset and compares the resulting sets.

**Results:**
- 23 single-dimension filter values → **0 mismatches**
- 155 two-dimension filter combinations → **0 mismatches**

The bucket fast path is fully consistent with the matcher.

I also verified `_bulk_filter_result_cache` correctly invalidates when
the text key changes (it sorts the entire `filter_state` dict into a
tuple before keying, so any field flip is a cache miss).

---

## What's new in the test suite

`tests/test_ui_bulk.py::MatcherFastPathConsistencyTests` is a permanent
guard against the v0.5.4 / v0.6.3 / v0.6.4 bug family.  It builds a
small fixture that exercises every interesting overlap:

- `status=skip + missing_pack` (must appear in Skip and No Pack)
- `status=ok + dead_stock` (OK and Dead Stock)
- `stockout_risk_score=0.95 + reorder_attention_signal=normal`
  (Normal and High Risk)
- `reorder_attention_signal=review_missed_reorder + risk=0.7`
  (Missed Reorder and High Risk)
- A plain ok item

Then it runs both the matcher and the fast bucket path for every value
of `item_status`, `status`, `performance`, `sales_health`, and
`attention`, and asserts the result sets are identical.

If a future bucket helper drifts from its matcher rule, this test
fails on the very first mismatch and prints the offending dimension,
value, and the symmetric difference between the two sets.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.6.4  |   982 |
| v0.6.5  |   983 |

One new test:
`MatcherFastPathConsistencyTests.test_every_single_dim_filter_value_matches`.

---

## Files changed

- `tests/test_ui_bulk.py` — new `MatcherFastPathConsistencyTests` class
- `app_version.py` — bumped to 0.6.5

---

## Roadmap status

| Phase | Status |
|---|---|
| Phase 1 — Bulk Grid Text Search | ✓ closed (v0.6.0) |
| Phase 2 — Supplier → Vendor Auto-mapping | ✓ closed (v0.6.1) |
| Phase 3 — QOH Adjustment Review | ✓ closed (v0.6.2) |
| Phase 4 — Ordering Algorithm Fixes | ✓ closed (v0.5.5) |
| Phase 4b — Parser/Min/Max bugs | ✓ closed (v0.5.5) |
| Phase 4c — Bulk Removal Edge Cases | ✓ closed (v0.5.4) |
| Skip-filter saga | ✓ closed (v0.5.4 / v0.6.3 / v0.6.4 / v0.6.5 audit) |
| Phase 5 — Manual QA | carry-over (intentionally manual) |

Every coded item on the v0.6.x roadmap is closed and the bucket-vs-matcher
invariant is now enforced by automated test.  From here the natural
next steps are (a) operator field testing on the new build, (b) a
v0.7.x roadmap, or (c) shipping and waiting for feedback.
