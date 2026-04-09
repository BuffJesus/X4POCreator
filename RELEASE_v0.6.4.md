# Release Notes — v0.6.4

**Date:** 2026-04-08

---

## Summary

v0.6.4 closes two more bucket-vs-matcher inconsistencies in the bulk
grid filter, found while auditing the rest of the bucket helpers after
the v0.6.3 fix:

1. **Text search was silently ignored on the fast path** — a regression
   introduced in v0.6.0 when the search field was added.
2. **The "High Risk" attention filter resolved to an empty list** —
   `bulk_attention_bucket` only emitted Normal / Missed Reorder, so the
   bucket index had no "High Risk" key for the fast path to find.

982 tests pass (6 new regression tests).

---

## Fixes

### 1. Text search filter now actually filters (`ui_bulk.py:910`)

`uses_only_bucket_filters` always returned `True`, so the
`apply_bulk_filter` fast path took `candidate_items` straight from the
bucket index without calling `item_matches_bulk_filter`.  When v0.6.0
added the text search field, that fast path silently bypassed the
search.  Typing into the new Search box would refresh the cache key but
return the same unfiltered items.

**Repro (verified before fix):** items `[GH781/HOSE, GH999/GASKET]`
with `text="hose"` returned both items via the fast path.

**Fix:** `uses_only_bucket_filters` returns `False` when
`filter_state.get("text")` is non-empty, forcing the matcher to run.

### 2. "High Risk" attention filter now finds items (`ui_bulk.py:746`)

`bulk_attention_bucket` only returned `"Normal"` or `"Missed Reorder"`
based on `reorder_attention_signal`, but the matcher's "High Risk" rule
uses `stockout_risk_score >= 0.6` — completely separate signal.  So an
item with risk 0.9 was bucketed as `"Normal"` and never appeared in the
High Risk filter.

**Repro (verified before fix):** items with risk 0.9 / 0.1, attention
filter `"High Risk"` → fast path returned 0 items.

**Fix:** mirror the v0.6.3 multi-bucket pattern from `bulk_item_status`.
`bulk_attention_bucket` now returns a tuple, e.g. `("Normal", "High Risk")`
or `("Missed Reorder", "High Risk")`, so the same item lives in every
bucket the matcher would accept it for.  Items with risk below 0.6 are
unchanged.

### Audit

I also re-checked every other bucket helper:

- **`bulk_assignment_status`** (Assigned/Unassigned) — clean binary,
  matcher and bucket use the same field.  No bug.
- **`bulk_performance_bucket`** (Top/Steady/Intermittent/Legacy) —
  matcher and bucket map from the same `performance_profile` field
  the same way.  No bug.
- **`bulk_sales_health_bucket`** (Active/Cooling/Dormant/Stale/Unknown)
  — same.  No bug.

So this release plus v0.6.3 closes every known matcher/bucket
inconsistency.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.6.3  |   976 |
| v0.6.4  |   982 |

Six new regression tests in `tests/test_ui_bulk.py`:

- `BulkAttentionBucketTests` — high-risk-with-normal-signal,
  low-risk-stays-normal-only, missed-reorder-with-high-risk,
  empty item returns None.
- `UsesOnlyBucketFiltersTests` — text filter disables fast path;
  blank text keeps fast path.

---

## Files changed

- `ui_bulk.py` — `uses_only_bucket_filters` honors text filter;
  `bulk_attention_bucket` returns multi-bucket tuple
- `tests/test_ui_bulk.py` — `BulkAttentionBucketTests` +
  `UsesOnlyBucketFiltersTests`
- `app_version.py` — bumped to 0.6.4

---

## v0.5.4 / v0.6.3 / v0.6.4 — the full skip-filter saga

The "skip filter is missing items" report turned out to need three
independent fixes:

| | Layer | What was wrong |
|---|---|---|
| v0.5.4 | `rules.py:1159` | Items with nothing to order were force-promoted from "skip" to "review" by any review_required flag.  860 items affected on the user's data. |
| v0.6.3 | `ui_bulk.bulk_item_status` | Items with `status=skip` AND `missing_pack` were bucketed as "No Pack" only, hiding them from the Skip filter.  5,317 items affected. |
| v0.6.4 | `ui_bulk.uses_only_bucket_filters` | Text search added in v0.6.0 was ignored by the fast bucket path. |
| v0.6.4 | `ui_bulk.bulk_attention_bucket` | "High Risk" attention filter resolved to empty bucket. |

All four are independent bugs that surfaced in the same code area.
