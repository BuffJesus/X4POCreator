# Release Notes — v0.5.3

**Date:** 2026-04-08

---

## Summary

v0.5.3 closes out the follow-up items from the v0.5.2 investigation:
the data-quality report no longer drowns operators in false positives,
the `detailed_sales_stats_lookup` audit is complete, and the bulk
removal flow now actually surfaces its skipped-row notices.

925 tests pass (no behavioral test changes — this release is internal
plumbing on top of v0.5.2).

---

## Fixes

### 1. Data-quality report cross-references loaded files (`load_flow.py:917`)

`build_data_quality_report_rows` flagged "Missing last sale date" /
"Missing last receipt date" purely from `inv["last_sale"]` /
`inv["last_receipt"]`, which are populated only from the On Hand Min Max
Sales export.  Items missing from that report (X4's "Show Zero QOH"
toggle was off) generated false positives even when the loaded
Detailed Part Sales / Received Parts files showed real activity.

**Fix:** the warning loop now also checks
`session.detailed_sales_stats_lookup[key]["last_sale_date"]` and
`session.receipt_history_lookup[key]["last_receipt_date"]` before
emitting a flag.  An item only appears in the data-quality report when
*neither* the inventory record *nor* the loaded files have a date.

**Impact on the user's real `Order/` dataset:**
- Rescued **2,290** false-positive "missing last sale" rows.
- Rescued **1,982** false-positive "missing last receipt" rows.
- ~4,272 noise lines eliminated from the report.
- `4211-08-06` no longer appears in the data-quality report at all.

### 2. `detailed_sales_stats_lookup` audit (`parsers.py:807`)

The v0.5.2 column-26 → column-36 fix for `qty_sold` automatically
corrected this consumer too — `parse_detailed_pair_aggregates` builds
`qty_sold_total` and `_quantity_counter` from the same row builder that
the summary uses.

Verified end-to-end against `GR1-:4211-08-06`:
`transaction_count=6, qty_sold_total=13, median=1.5, max=4` — matches
the per-line qtys `[2,1,1,4,4,1]` exactly.  No code change needed; the
roadmap audit item is closed.

### 3. Bulk-removal "view shifted" notice is now wired up (`bulk_sheet_actions_flow.py:377`)

v0.5.2 added `app.last_skipped_bulk_removals` so the bulk removal flow
could record indices it had to skip (out-of-range or `expected_keys`
mismatch when the view changed between right-click and confirm), but no
caller actually read the payload — the data was being collected and
thrown away.

**Fix:** `bulk_remove_selected_rows` now compares `len(removed_payload)`
to the requested count and, if anything was skipped, routes a one-line
notice through `app._notify_bulk_status` (with `_show_bulk_status` as
fallback):

> Skipped K of N row(s) — the view shifted before confirm (filter or
> sort changed). Reselect and retry.

The same notice in the `bulk_remove_not_needed` confirm path is
tracked as a small follow-up in roadmap Phase 4c.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.5.2  |   925 |
| v0.5.3  |   925 |

No new tests — this release plugs in helpers that the v0.5.2 work
already exercised.  The data-quality and `_notify_bulk_status` hooks
were verified end-to-end against the user's real `Order/` dataset.

---

## Files changed

- `load_flow.py` — data-quality report cross-references loaded files
- `bulk_sheet_actions_flow.py` — surfaces `last_skipped_bulk_removals`
- `app_version.py` — bumped to 0.5.3
- `ROADMAP_v0.6.md` — Phase 4b/4c progress logged
