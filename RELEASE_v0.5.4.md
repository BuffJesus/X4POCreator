# Release Notes — v0.5.4

**Date:** 2026-04-08

---

## Summary

v0.5.4 fixes the "Skip filter is missing items / they don't get removed
from the unfiltered view" report.  Two cooperating bugs were responsible:
a status-classification bug that hid ~16% of would-be skip items behind
the Review status, and a silent vendor-assigned exclusion in the not-needed
removal dialog that left those items behind in the bulk grid even after
the operator confirmed the dialog.

927 tests pass (2 new regression tests).

---

## Fixes

### 1. Items with nothing to order were being hidden under "Review" (`rules.py:1159`)

`evaluate_item_status` set `status = "skip"` when both `final_qty <= 0`
and `raw_need <= 0`, then unconditionally upgraded to `"review"` whenever
any `review_required` flag was set.  Items the system had nothing to
order on were being labelled "review" — invisible in the Skip filter and
invisible to the not-needed removal flow even though there was nothing
for the operator to decide.

**Repro on the user's real `Order/` dataset (8,409 candidates):**
- Before: 4,457 status=skip + **860 hidden under review** = 5,317
  logically-skip items, only 4,457 visible in the Skip filter.
- After: 5,317 status=skip, **0 hidden** — all 860 previously-hidden
  items now appear in the Skip filter.

**Fix:** the review-promotion clause now requires
`raw_need > 0 or final_qty > 0`.  Review-required items still escalate
when there is something to decide on; items with nothing to order stay
"skip".

Two regression tests added:
- `test_evaluate_item_status_zero_need_stays_skip_even_with_review_required`
- `test_evaluate_item_status_review_required_still_promotes_when_need_exists`

### 2. "Remove Not Needed" silently dropped vendor-assigned items (`ui_bulk_dialogs.py:276`)

`bulk_remove_not_needed` excluded any candidate already carrying a vendor
when `include_assigned=False` (the default), with no count surfaced.
The operator would filter to "Skip", run "Remove Not Needed (Filtered)",
see fewer candidates than they expected, and notice that the missing
items were still in the bulk grid after confirm.

**Fix:** the dialog now tracks `excluded_assigned_with_reason` (count of
items that match the not-needed criteria but were skipped because they
already have a vendor) and surfaces it in two places:

1. **The header banner** ("N items flagged… (M additional items matched
   the criteria but already have a vendor — toggle 'Include assigned
   items' to review them.)")
2. **The "Nothing to Remove" message** when *every* match was excluded by
   the vendor filter.

### 3. Not-needed confirm path now surfaces `last_skipped_bulk_removals`

v0.5.2 added the skipped-payload recording and v0.5.3 wired it into
`bulk_remove_selected_rows`, but the `bulk_remove_not_needed` confirm
path still ignored it.  Now the post-removal "Removed N items" dialog
also reports any rows that the flow had to skip because the view shifted
between dialog open and confirm.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.5.3  |   925 |
| v0.5.4  |   927 |

Two new regression tests in `tests/test_rules.py` covering both branches
of the review-promotion fix.

---

## Files changed

- `rules.py` — review-promotion now requires non-zero need
- `ui_bulk_dialogs.py` — vendor-assigned exclusion is counted and surfaced;
  not-needed confirm path reports skipped rows
- `tests/test_rules.py` — two new regression tests
- `app_version.py` — bumped to 0.5.4
