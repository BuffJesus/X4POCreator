# Release Notes — v0.6.6

**Date:** 2026-04-08

---

## Summary

v0.6.6 fixes a stale-row-cache bug found while auditing the bulk grid's
render-cache layer (the next layer down from the bucket fast path I
hardened in v0.6.3 / v0.6.4 / v0.6.5).

984 tests pass (1 new regression test).

---

## Fix

### `bulk_row_render_signature` was missing `stockout_risk_score` (`ui_bulk.py:556`)

The bulk grid caches the rendered tuple for each row keyed by a
"signature" snapshot of the fields the row reads.  When any field in
the signature changes, the cached tuple is discarded and the row
re-rendered.

`bulk_row_values` (line 588) renders `stockout_risk_score` as the **Risk**
column, but the signature didn't include it.  So when an edit
recalculated the item and shifted its risk percentage (e.g. a QOH
edit, a cycle change, a vendor switch that re-runs the
recency/order policy chain), the cached row kept showing the **old**
risk percentage until the entire grid was rebuilt.

**Fix:** add `item.get("stockout_risk_score")` to the signature so any
risk shift invalidates the cache entry for that row.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.6.5  |   983 |
| v0.6.6  |   984 |

One new test in `tests/test_ui_bulk.py`:
`BulkRowRenderSignatureTests.test_changing_stockout_risk_changes_signature`
asserts that flipping `stockout_risk_score` produces a different
signature tuple, so future drift on this field will fail loudly.

---

## Audit context

I also re-checked the rest of the render-cache invariants:

- **`_filter_depends_on_changes`** (line 1265) correctly rebuilds the
  Item Status, Assignment, and Attention buckets on the column edits
  that feed them (`vendor`, `final_qty`, `qoh`, `cur_min`, `cur_max`,
  `pack_size`).
- **Text filter** doesn't need rebuild logic because the fields it
  matches against (item_code, description, supplier) are static for
  the lifetime of an item in the session.
- **Other render fields** in the signature: vendor, line_code,
  item_code, description, source, status, raw_need, suggested_qty,
  final_qty, pack_size, why, order_policy, supplier, qoh, min, max,
  mo12_sales, cycle, rule JSON.  All match what `bulk_row_values`
  reads.  No other gaps found.

---

## Files changed

- `ui_bulk.py` — `bulk_row_render_signature` includes
  `stockout_risk_score`
- `tests/test_ui_bulk.py` — new `BulkRowRenderSignatureTests` class
- `app_version.py` — bumped to 0.6.6
