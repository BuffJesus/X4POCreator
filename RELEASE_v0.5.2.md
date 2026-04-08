# Release Notes — v0.5.2

**Date:** 2026-04-08

---

## Summary

v0.5.2 is a bug-fix release driven by an investigation into why item
`GR1-:4211-08-06` (ORB MALE CRIMP FITTING — QOH 0, X4 max 8) was never
appearing as a reorder candidate. The investigation surfaced **two
ordering bugs and three bulk-removal edge cases**, all fixed here.

925 tests pass.

---

## Fixes

### 1. Detailed Part Sales parser was overcounting `qty_sold` (`parsers.py:419`)

`_parse_x4_detailed_part_sales_row` read column 26 (`Total Quantity`) as
the per-row sale quantity. In the X4 export, column 26 is the **item-level
group total repeated on every detail row** — the actual per-line quantity
is column 36 (`Quantity`, after the unit price). Both
`build_sales_receipt_summary` and `parse_detailed_pair_aggregates` then
**summed that repeated total across every detail row**, multiplying each
item's reported sales by its detail-row count.

**Repro:** `GR1-:4211-08-06` has 6 detail rows in the user's real export,
each with col26=`13` and per-line qtys `[2,1,1,4,4,1]` summing to 13.
Parser produced `qty_sold = 78` (6 × 13). Now produces `qty_sold = 13`.

Regression test added: `test_parse_detailed_part_sales_x4_layout_uses_per_line_qty_not_repeated_total`.

### 2. Recency classifier was blind to loaded sales/receipt history (`rules.py:538`)

`classify_recency_confidence` checked `inv["last_sale"]` and
`inv["last_receipt"]`, which are populated **only** from On Hand Min Max
Sales. Items missing from that report (X4's "Show Zero QOH" toggle was
off) had both flags blank → `data_completeness =
"missing_recency_activity_protected"` → `review_required = True` with
policy `manual_only` → **`order_qty` forced to 0**. The item appeared in
`filtered_items` but was effectively invisible/blocked in the reorder list.

**Fix:** also accept `item["last_sale_date"]` / `item["last_receipt_date"]`
populated by the loaded Detailed Part Sales / Received Parts files.

End-to-end verification on the user's real `Order/` dataset:
`GR1-:4211-08-06` now produces `order_qty = 6`, `review_required = False`,
`recency_confidence = medium`.

### 3. Confirmed-stocking evidence counter had the same blind spot (`rules.py:1189`)

`maintain_confirmed_stocking_counter` computed `has_new_evidence` from
`inv["last_sale"]` / `inv["last_receipt"]` only. Items missing from
Min/Max would tick the "sessions without evidence" counter on every run
and eventually expire their `confirmed_stocking` flag despite real loaded
activity. Fix mirrors the recency-classifier fix.

### 4. Bulk "Remove Not Needed (On Screen)" was identical to "(Filtered)" (`ui_bulk_dialogs.py:247`, `bulk_sheet.py`)

Both branches called `app.bulk_sheet.visible_row_ids()`, which returns the
**entire filtered set** rather than the rows currently in the viewport.
On a long bulk list, clicking "On Screen" silently swept thousands of
off-screen rows into the not-needed dialog.

**Fix:** added `BulkSheet.viewport_row_ids()` (wraps tksheet's
`sheet.visible_rows()` API with safe fallbacks) and wired the `screen`
scope to use it.

### 5. No-op bulk removals left stale `last_removed_bulk_items` behind (`bulk_remove_flow.py`)

When a removal call removed nothing (every index out of range, or every
candidate protected, or every `expected_keys` check failed), the function
returned early **before** resetting `app.last_removed_bulk_items`. The
prior call's payload stayed in place, so undo and the "X items removed"
status banner could replay or show a record from an earlier action.

**Fix:** explicitly reset `app.last_removed_bulk_items = []` on the
no-op return path. Regression test added.

### 6. Silently-dropped removal indices (`bulk_remove_flow.py`)

When the filter shifted between right-click and confirm, or row IDs were
stale, mismatched / out-of-range indices were silently `continue`'d. The
user was told "removed N item(s)" with no indication that part of their
selection didn't apply.

**Fix:** the flow now records each skip on
`app.last_skipped_bulk_removals` as `(idx, reason)` (`"out_of_range"`
or `"key_mismatch"`) so a follow-up UI surface can show a "skipped K
rows because the view shifted" notice. Regression test added. UI
surfacing is tracked in roadmap Phase 4c.

---

## Configuration tip — On Hand Min Max "Show Zero QOH"

The user discovered during this investigation that the X4 "On Hand Min
Max Sales" report has a **"Show items with zero on hand"** toggle that
was off. With the toggle off, items like `4211-08-06` (QOH=0) are
omitted from the export entirely, leaving the app with no min/max anchor.

Coverage on the user's real dataset:

| Toggle | Min/Max rows | Sales items missing from Min/Max |
|---|---|---|
| Off | 23,508 | 2,352 |
| On  | 33,494 |    76 |

**Recommendation:** turn the toggle on in X4. The fixes in this release
keep the residual 76-item gap from silently blocking reorder
suggestions, but the toggle is the canonical fix.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.5.1  |   922 |
| v0.5.2  |   925 |

Three new regression tests covering the qty_sold parsing fix, the
no-op-removal payload reset, and the skipped-payload recording.

---

## Files changed

- `parsers.py` — column 36 instead of 26 for per-line qty
- `rules.py` — recency + confirmed-stocking fallbacks to per-item dates
- `bulk_sheet.py` — new `viewport_row_ids()` helper
- `ui_bulk_dialogs.py` — `bulk_remove_not_needed` "screen" scope wired to viewport
- `bulk_remove_flow.py` — no-op payload reset + skipped-removal recording
- `tests/test_parsers.py`, `tests/test_workflow_smoke.py`,
  `tests/test_bulk_remove_flow.py` — regression coverage
- `app_version.py` — bumped to 0.5.2
- `ROADMAP_v0.6.md` — Phase 4b/4c progress logged
