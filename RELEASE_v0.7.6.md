# Release Notes — v0.7.6

**Date:** 2026-04-08

---

## Summary

v0.7.6 is the **bulk grid render perf audit** from Phase 4.  The
audit ran the hot paths against the user's real 8,409-item `Order/`
dataset and found no pathological bottlenecks — every pure-Python
layer finishes well under the "feels instant" threshold.  The
valuable deliverable is a **permanent perf baseline test** that
catches catastrophic future regressions so the audit doesn't have
to be re-done by hand.

1066 tests pass (5 new perf baseline tests).

---

## Measurements

On the user's real 8,409-item `Order/` dataset:

| Operation | Time | Notes |
|---|---|---|
| `parse_all_files`                     | 1,854 ms | CSV-parser bound |
| `apply_load_result`                   |   132 ms | |
| `prepare_assignment_session`          |   806 ms | 95 µs/item enrich_item |
| `sync_bulk_session_metadata`          |    33 ms | bucket index build |
| `bulk_row_values` × 8,409             |    86 ms | 10 µs/row |
| `bulk_row_render_signature` × 8,409   |    35 ms | 4 µs/row |
| `cached_bulk_row_values` × 8,409 (all hits) | 47 ms | signature recompute |
| `filtered_candidate_items` (Skip)     |  0.01 ms | index lookup |
| `item_matches_bulk_filter` × 8,409    |     6 ms | |

**Conclusions:**

- **Total session load: ~2.8s** for 8K items.  CSV parsing is the
  dominant cost (65%) — parallel parsing could shave this but would
  risk the other bugs we've been hunting, so not worth it without
  real user complaint.
- **Bulk grid first paint: ~86ms** (uncached row rendering).
- **Filter change: ~47ms** (cached second pass).
- **Everything under the 100ms "feels instant" threshold** for user
  interactions.  No perf work needed on the pure-Python layer.

The one minor observation: the cached second pass (47ms) is only
~2× faster than uncached (86ms), because `bulk_row_render_signature`
alone takes 35ms — almost as expensive as the row rendering itself.
A smarter cache could skip signature recomputation on a generation
bump, but the v0.6.6 invariant (stockout_risk_score in signature)
requires per-field comparison, so any optimization here risks
correctness.  **Deferred — not worth the risk without a user complaint.**

---

## Permanent perf baseline test

`tests/test_bulk_perf_baseline.py` (new) runs the hot paths against
an **8,000-item synthetic fixture** and asserts each stays under a
wall-clock budget.  Budgets are deliberately loose (~5-10× the
measured time on the user's real data) so the suite stays stable
across CI environments but still fails loudly if a future change
introduces an O(n²) loop or other catastrophic regression.

Five test cases:

- `test_sync_bulk_session_metadata_under_200ms` — budget 200ms
  (measured 33ms)
- `test_bulk_row_render_signature_under_250ms` — budget 250ms
  (measured 35ms)
- `test_item_matches_bulk_filter_under_100ms` — budget 100ms
  (measured 6ms)
- `test_filtered_candidate_items_fast_path_under_50ms` — budget 50ms
  (measured <1ms)
- `test_matcher_and_fast_path_agree_on_fixture` — correctness
  double-check: every single-dim Item Status filter must produce
  identical sets via matcher and fast path on the synthetic fixture

The last test is the most important — it's a second layer of defense
against the matcher/fast-path drift family (v0.6.3 → v0.7.5), using
a larger and more diverse fixture than the unit tests.

The fixture spreads items across every status bucket (3 statuses,
`missing_pack` on half, a varied `stockout_risk_score` distribution)
so the Skip / No Pack / High Risk edge cases are all covered.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.7.5  |  1061 |
| v0.7.6  |  1066 |

5 new tests in `tests/test_bulk_perf_baseline.py`.

---

## Files changed

- `tests/test_bulk_perf_baseline.py` (new) — 5 perf + correctness tests
- `app_version.py` — bumped to 0.7.6

No production code changes in this release — the audit found no
bugs to fix and no pathological paths to optimize.

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed |
| Phase 2 — Vendor-centric Workflows | ✓ closed |
| Phase 3 — Skip Cleanup Tools | ✓ closed |
| Phase 4 — Performance & Correctness Carry-over | further closed (perf audit + baseline test) |

Phase 4 still has the pack-rounding overshoot **defer** behavior
(behind a feature flag) and the Phase 5 manual QA pass.  Both need
a design decision or field input before I can do them unilaterally:

- **Overshoot defer** is a behavior change that would surprise
  existing operators who have been ordering full packs up to now.
  The right time to ship it is after an operator says "stop
  ordering full packs for items with 60%+ on hand".
- **Phase 5 manual QA** is by definition a pass that needs a human
  with the real files running the whole workflow.

**v0.7.6 is a clean stopping point.**  Six speculative releases
since v0.7.0 have all shipped working code, but the remaining open
items all genuinely need operator input before I can prioritize them
with any confidence.  This is the right time to ship the v0.7.x train
and wait for feedback.
