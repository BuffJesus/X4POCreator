# PO Builder Roadmap — v0.6.x

Status: Planning

Current app version: `0.5.1`

---

## What v0.6.x is about

v0.5.x addressed configuration pain points (ignore list, bulk rule edit, order
rules CSV). v0.6.x focuses on **Find & Configure**: three gaps that slow down
daily operation on large item lists.

- **Bulk Grid Text Search** — there is no way to locate an item by typing its
  code, description, or supplier. The seven combo filters work well for
  category-level slicing but cannot find a specific part number quickly.
- **Supplier → Vendor Auto-mapping** — every item has a `supplier` field from
  the X4 data but this is never used for vendor assignment. Operators who have
  consistent supplier→vendor relationships must re-assign the same vendor
  manually every run.
- **QOH Adjustment Review** — QOH edits are stored in session state and
  included in snapshots, but there is no way to see all adjustments for the
  current session in one place before exporting.

---

## Phase 1. Bulk Grid Text Search

Operators with large item lists have no way to locate a specific part number
without scrolling or knowing its line code.

- [x] Add a "Search:" entry field to the bulk tab filter row (row 1, before
  Line Code). Triggers `_apply_bulk_filter` on every keystroke.
- [x] Add `item_matches_text_filter(item, text)` to `ui_bulk.py` — matches
  case-insensitively against `line_code`, `item_code`, `description`,
  and `supplier`.  Returns `True` when text is blank (no filter).
- [x] Add `"text"` key to `bulk_filter_state(app)` and wire it into
  `item_matches_bulk_filter`.
- [x] Update `bulk_filter_is_default` to treat a non-empty text value as
  non-default.
- [x] Add tests for `item_matches_text_filter` and the updated
  `item_matches_bulk_filter` with text state.

---

## Phase 2. Supplier → Vendor Auto-mapping

Items already carry a `supplier` code from the X4 inventory data. Operators
who always order from the same vendor for a given supplier code re-type it
every run.

- [x] Add `supplier_map_flow.py` with pure functions:
  - `load_supplier_map(path)` / `save_supplier_map(path, mapping)` —
    persists `{supplier_code: vendor_code}` to `supplier_vendor_map.json`
    via atomic tempfile + rename.
  - `apply_supplier_map(items, mapping)` — returns `(item, vendor)`
    pairs for items whose supplier has a mapping and whose `vendor`
    field is currently blank.
  - `build_supplier_map_from_history(snapshots)` — scans session
    snapshots to infer `supplier → most-frequently-used vendor` pairs.
  - Bonus: `merge_supplier_maps(base, overlay, *, overlay_wins=False)`
    so the dialog can fold inferred suggestions in without losing
    manual edits.
- [x] Add `ui_supplier_map.py` — "Supplier Map" dialog with editable
  table, Add/Remove rows, Auto-learn from History (scans the 25 most
  recent snapshots), Apply to Session, and Save/Cancel.
- [x] Add "Supplier Map..." button to the bulk tab toolbar (vendor row).
- [x] Persist to `supplier_vendor_map.json` alongside other config
  files (added to `data_folder_flow.build_data_paths`).
- [x] 21 new tests in `tests/test_supplier_map_flow.py` covering all
  four pure functions (load/save round-trip, normalization, malformed
  input, history aggregation, merge precedence).

---

## Phase 3. QOH Adjustment Review

Operators who edit QOH in the bulk grid have no summary of what they changed
before exporting. A single-dialog review helps catch accidental edits.

- [x] Added `qoh_review_flow.py` with two pure helpers:
  - `format_qoh_adjustments(qoh_adjustments, inventory_lookup)` —
    sorted list of dicts with line_code, item_code, description,
    old_qoh, new_qoh, delta.  Drops zero-delta entries.
  - `revert_qoh_adjustments(adjustments, inv_lookup, keys)` — pure
    revert helper that restores `inv["qoh"]` and pops the adjustment
    entry; returns the count actually reverted.
- [x] Added `ui_qoh_review.py` — "QOH Adjustments" dialog with the
  Tree view, Revert Selected action (re-runs per-item recalculation
  for each reverted key and refreshes the bulk grid / summary), and
  "No adjustments this session" empty state.
- [x] Added "QOH Changes..." button to the bulk tab removal row.
- [x] 12 new tests in `tests/test_qoh_review_flow.py` covering normal
  cases, zero-delta filtering, sorting, missing inventory lookup,
  negative delta, non-numeric coercion, non-mapping payloads, and the
  full revert flow (single key, multi-key, missing key, empty input).

---

## Phase 4. Ordering Algorithm Fixes

Issues surfaced during a v0.5.1 review of `rules.py` / `reorder_flow.py`.

- [ ] **Pack-rounding overshoot guard** in `calculate_suggested_qty`
  (`rules.py:1061`). All pack branches (`standard`, `pack_trigger`,
  `reel_auto`) round `raw_need` up to a full pack with no overshoot check.
  Repro: qoh=300, max=496, pack=300 → suggests 300, ending stock 600
  (104 past max). Fix: after computing `rounded`, if
  `rounded > raw_need + acceptable_overstock_qty_effective` **and**
  `raw_need < pack_qty`, defer the order this cycle (return 0 with reason
  `"defer: full pack would overshoot max"`). Reel material with 60%+ on
  hand can wait for the next cycle.
- [x] **Wire `assess_post_receipt_overstock` into review routing**
  (`rules.py:846`).  `evaluate_item_status` now raises a
  `would_overshoot_max` data flag whenever `projected_overstock_qty > 0`
  and the projection is outside tolerance.  A separate
  `order_floor_above_max` flag fires when an aggressive
  `minimum_packs_on_hand` floor pushes the order past
  `target + acceptable_overstock` even before pack rounding.  Two
  regression tests added in `tests/test_rules.py`.
- [x] **Description fallback chain** in `_description_for_key`
  (`reorder_flow.py:269`).  Now walks `sales_items`, `receipts_items`,
  `open_po_items`, `suspended_items`, `detailed_sales_rows`, and
  `suspended_lookup` before giving up.  Two regression tests added in
  `tests/test_reorder_flow.py`.

---

## Phase 4b. Detailed Sales Parser Bugs (URGENT)

Surfaced 2026-04-08 while diagnosing why item `GR1-:4211-08-06` (ORB MALE
CRIMP FITTING — QOH 0, X4 max 8) was never appearing as a reorder
candidate. Two independent bugs combined to silently suppress it.

- [x] **Per-row qty_sold reads the item-level total, not the line qty.**
  `_parse_x4_detailed_part_sales_row` reads column 26 (`Total Quantity`,
  the X4 group total that is repeated on every detail row for the item)
  and `build_sales_receipt_summary` / `parse_detailed_pair_aggregates`
  then **sum it across every detail row**. Result: an item with N detail
  lines reports `qty_sold = N × actual_total`. Repro with
  `C:\Users\Cornelio\Desktop\Order\DETAILED PART SALES.csv`:
  `GR1-:4211-08-06` has 6 detail rows, each col26=`13`, true sum of
  per-line qty (col36) = 13 → parser yields 78. Fix: read the per-line
  qty from column 36 (`row[36]`, the `Quantity` column after price), or
  alternatively keep one Total-Quantity reading per `(line_code, item_code)`
  key and stop summing. Per-line is preferable because it preserves
  per-transaction stats used by `build_detailed_sales_stats_lookup`
  (transaction_count, quantity_counter, etc., currently all corrupted by
  the same wrong column).
- [x] **Recency classifier ignored loaded sales/receipt dates.**
  `rules.py:classify_recency_confidence` only checked `inv["last_sale"]`
  and `inv["last_receipt"]`, which are populated only from On Hand Min
  Max Sales. When an item is missing from that report (X4 skips some
  QOH=0 items) but still has loaded Detailed Part Sales and Received
  Parts data, both flags were false → `data_completeness =
  "missing_recency_activity_protected"` → `review_required = True`
  (`manual_only`) → `order_qty` forced to 0. The item was in
  `filtered_items` but invisible/blocked in the reorder list. Fix
  (rules.py:538) now also accepts `item["last_sale_date"]` and
  `item["last_receipt_date"]` from the loaded files.

- [x] **`detailed_sales_stats_lookup` is corrupted by the same bug.**
  Audited 2026-04-08 after the col36 fix.  `parse_detailed_pair_aggregates`
  builds `qty_sold_total` and `_quantity_counter` from the same row
  builder that the summary uses, so the col36 fix automatically
  corrected this consumer too.  Verified against `GR1-:4211-08-06`:
  `transaction_count=6, qty_sold_total=13, median=1.5, max=4` —
  matches the per-line qtys `[2,1,1,4,4,1]` exactly.
- [x] **`maintain_confirmed_stocking_counter` had the same blind spot.**
  `rules.py:1189` computed `has_new_evidence` from `inv["last_sale"]`
  and `inv["last_receipt"]` only.  Items missing from Min/Max would
  tick the "sessions without evidence" counter on every run and
  eventually expire their `confirmed_stocking` flag despite real
  loaded sales/receipt activity.  Fix mirrors the recency-classifier
  fix: also accept `item["last_sale_date"]` / `item["last_receipt_date"]`.

- [x] **Audit every other `inv.get("last_sale" / "last_receipt" /
  "mo12_sales" / "ytd_sales")` for the same Min/Max blind spot.**
  Audited 2026-04-08:
  - `performance_flow.classify_item` (perf_flow.py:166) takes
    `max(annualized_sales_loaded, mo12_sales)` so it tolerates a
    missing inv value — left alone.
  - `load_flow.build_data_quality_report_rows` (load_flow.py:917) —
    **fixed**.  Now cross-references `detailed_sales_stats_lookup`
    and `receipt_history_lookup` so loaded activity suppresses the
    false positives.  Verified on the user's real `Order/` dataset:
    rescued 2,290 "missing last sale" rows and 1,982 "missing last
    receipt" rows (~4,272 noise lines eliminated).
    `4211-08-06` no longer appears in the data-quality report.
  - `assignment_flow.py:84,145` `current_min = inv.get("min")` —
    items missing from Min/Max have no min so the
    `_protected_inventory_candidate_reason` "below current min"
    branch is unreachable for them.  Currently masked by
    `demand_signal > 0` keeping them as candidates anyway, but worth
    surfacing as a separate "missing min/max coverage" review bucket
    rather than hiding the gap.  Tracked under the "no Min/Max
    coverage" startup count item below.

- [ ] **Items missing from On Hand Min Max are silently demoted.**
  `4211-08-06` exists in On Hand Report and Received Parts but not in
  On Hand Min Max Sales (X4 evidently filters out some QOH=0 fittings
  from that export).  `inventory_lookup` for the key is built from
  the On Hand Report fallback in `load_flow.py:522` with `min=None`,
  `max=None`, `supplier=""`.  After the recency-classifier fix the
  item now reaches the bulk grid with a sales-driven suggestion, but
  the X4-set max (8 in the user's case) is still invisible to us.
  Scope of the gap on the user's real `Order/` dataset:
  **2,352 items have loaded sales but no Min/Max row** (out of 23,508
  Min/Max rows total).  Decide: surface these in a dedicated review
  bucket, fall back to a different X4 export that includes max for
  zero-QOH rows, or instruct operators to fix the X4 export filter.

- [x] **Add a "no Min/Max coverage" startup count.**
  `load_flow.parse_all_files` now stamps
  `result["no_minmax_coverage_keys"]` and emits a "Min/Max Coverage
  Warning" naming the count and pointing operators at the X4 "Show
  items with zero on hand" toggle.  On the user's real toggle-off
  export this surfaces 6,006 items with no anchor (sizing is purely
  sales-driven for those rows).
- [ ] Add a regression test in `tests/test_parsers.py` that loads a
  fixture with multiple detail rows for one item and asserts
  `qty_sold` equals the sum of per-line qty (col36), not the repeated
  Total Quantity.
- [ ] Add a regression test ensuring an item present only in On Hand
  Report (not Min Max) still produces a candidate with non-zero
  reorder guidance, not a silent zero.

---

## Phase 4c. Bulk Removal Edge Cases

Surfaced 2026-04-08 during a focused review of `bulk_remove_flow.py` and
`ui_bulk_dialogs.bulk_remove_not_needed`.

- [x] **"On Screen" vs "Filtered" not-needed scopes were identical** in the
  tksheet UI.  Both called `visible_row_ids()`, which returns the full
  filtered set.  Added `BulkSheet.viewport_row_ids()` (wraps tksheet
  `sheet.visible_rows()` with safe fallbacks) and wired the "screen"
  scope to use it.
- [x] **No-op removals left stale `last_removed_bulk_items`** behind, so
  undo and the status banner could replay an earlier removal.  Reset
  the payload on the early-return path; regression test added.
- [x] **Mismatched / out-of-range indices were silently dropped.**  The
  flow now records each skip on `app.last_skipped_bulk_removals` as
  `(idx, reason)` for downstream UI surfacing.

- [x] **Surface `last_skipped_bulk_removals` in the UI** — partial.
  `bulk_sheet_actions_flow.bulk_remove_selected_rows` now reads the
  payload after the call and routes a one-line "Skipped K of N row(s)
  — the view shifted before confirm" notice through
  `app._notify_bulk_status` (or `_show_bulk_status` as fallback).
  Wiring the same notice into the `bulk_remove_not_needed` confirm
  path is a small follow-up.
- [ ] **Manual QA**: scroll a long bulk list, right-click "Remove Not
  Needed (On Screen)", confirm only viewport rows are offered; repeat
  with "Filtered" and confirm the dialog covers the full filtered
  set.  Then change the filter while the not-needed dialog is open
  and confirm — verify the skipped-count banner appears.

---

## Phase 5. Manual QA (carry-over)

- [ ] Run full load → assign → review → export workflow against representative
  real-world CSVs in the packaged exe.
- [ ] Add any targeted regression tests discovered during live testing.

---

## Definition of "Done Enough" for v0.6.x

- Typing in the Search field narrows the bulk grid live.
- Supplier→vendor mappings can be persisted and applied with one click.
- All QOH adjustments for the current session are reviewable and reversible
  before export.
- Phase 4 manual QA completed against at least one real-world dataset.
