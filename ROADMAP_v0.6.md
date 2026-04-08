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

- [ ] Add a "Search:" entry field to the bulk tab filter row (row 1, before
  Line Code). Triggers `_apply_bulk_filter` on every keystroke.
- [ ] Add `item_matches_text_filter(item, text)` to `ui_bulk.py` — matches
  case-insensitively against `item_code`, `description`, and `supplier`.
  Returns `True` when text is blank (no filter).
- [ ] Add `"text"` key to `bulk_filter_state(app)` and wire it into
  `item_matches_bulk_filter`.
- [ ] Update `bulk_filter_is_default` to treat a non-empty text value as
  non-default.
- [ ] Add tests for `item_matches_text_filter` and the updated
  `item_matches_bulk_filter` with text state.

---

## Phase 2. Supplier → Vendor Auto-mapping

Items already carry a `supplier` code from the X4 inventory data. Operators
who always order from the same vendor for a given supplier code re-type it
every run.

- [ ] Add `supplier_map_flow.py` with pure functions:
  - `load_supplier_map(path)` / `save_supplier_map(path, mapping)` —
    persists `{supplier_code: vendor_code}` to `supplier_vendor_map.json`.
  - `apply_supplier_map(items, mapping)` — returns a list of
    `(item, vendor)` pairs for items whose supplier has a mapping and whose
    `vendor` field is currently blank.
  - `build_supplier_map_from_history(snapshots)` — scans session snapshots
    to infer `supplier → most-frequently-used vendor` pairs.
- [ ] Add `ui_supplier_map.py` — "Supplier Map" dialog:
  - Table: Supplier Code | Mapped Vendor (editable).
  - "Auto-learn from history" button — runs `build_supplier_map_from_history`
    and merges suggestions (existing manual entries win).
  - "Apply to Session" button — calls `apply_supplier_map` and auto-fills
    unassigned items in the current session, then refreshes the bulk grid.
- [ ] Add "Supplier Map…" button to the bulk tab toolbar (vendor row).
- [ ] Persist to `supplier_vendor_map.json` alongside other config files.
- [ ] Add tests for all three pure functions.

---

## Phase 3. QOH Adjustment Review

Operators who edit QOH in the bulk grid have no summary of what they changed
before exporting. A single-dialog review helps catch accidental edits.

- [ ] Add `format_qoh_adjustments(qoh_adjustments, inventory_lookup)` to a
  new `qoh_review_flow.py` — returns a sorted list of dicts (line_code,
  item_code, description, old_qoh, new_qoh, delta) for all non-zero
  adjustments in the current session.
- [ ] Add `ui_qoh_review.py` — "QOH Adjustments" dialog:
  - Tree view: Line Code, Item Code, Description, Old QOH, New QOH, Delta.
  - "Revert Selected" action — restores the original QOH for selected rows
    and removes the adjustment entry.
  - Shows "No adjustments this session" when the dict is empty.
- [ ] Add "QOH Changes…" button to the bulk tab toolbar (removal row).
- [ ] Add tests for `format_qoh_adjustments` covering normal cases, zero-delta
  filtering, and sorting.

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
- [ ] **Wire `assess_post_receipt_overstock` into review routing**
  (`rules.py:838`). The function already computes
  `projected_overstock_qty` and `overstock_within_tolerance` but nothing
  consumes them. At minimum, raise a `would_overshoot_max` data_flag in
  `evaluate_item_status` so reviewers can spot these before export. Also
  flag when `effective_order_floor > target + acceptable_overstock`
  (aggressive `minimum_packs_on_hand` rules currently order past max
  silently).
- [ ] **Description fallback chain** in `_description_for_key`
  (`reorder_flow.py:269`). Currently only checks `inventory_lookup` and
  `sales_items`, so items appearing only in receipts / open POs /
  suspended reports get blank descriptions. Extend the fallback to also
  walk `receipts_items`, `open_po_items`, and `suspended_items`.
- [ ] Tests in `tests/test_rules.py` for the hose-overshoot scenario and
  in `tests/test_reorder_flow.py` for the description fallback chain.

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

- [ ] **`detailed_sales_stats_lookup` is corrupted by the same bug.**
  `parse_detailed_pair_aggregates` (parsers.py:807-809) increments
  `transaction_count` once per row but feeds the inflated col26 value
  into `qty_sold_total` and `_quantity_counter`. After the column fix,
  audit the median/mean/max stats those feed into
  (`detailed_sales_suggest_min_max` in `reorder_flow.py:63`).
- [x] **`maintain_confirmed_stocking_counter` had the same blind spot.**
  `rules.py:1189` computed `has_new_evidence` from `inv["last_sale"]`
  and `inv["last_receipt"]` only.  Items missing from Min/Max would
  tick the "sessions without evidence" counter on every run and
  eventually expire their `confirmed_stocking` flag despite real
  loaded sales/receipt activity.  Fix mirrors the recency-classifier
  fix: also accept `item["last_sale_date"]` / `item["last_receipt_date"]`.

- [ ] **Audit every other `inv.get("last_sale" / "last_receipt" /
  "mo12_sales" / "ytd_sales")` for the same Min/Max blind spot.**
  Confirmed scan results from 2026-04-08:
  - `performance_flow.classify_item` (perf_flow.py:166) takes
    `max(annualized_sales_loaded, mo12_sales)` so it tolerates a
    missing inv value — leave alone.
  - `load_flow._collect_data_quality_warnings` (load_flow.py:920,928)
    emits "Missing last sale date" / "Missing last receipt date"
    rows for every inv key that lacks them.  On the user's real
    `Order/` dataset that's **9,973 false-positive warnings** because
    those items have loaded sales/receipts but are absent from
    Min/Max.  Same fallback fix applies.
  - `assignment_flow.py:84,145` `current_min = inv.get("min")` —
    items missing from Min/Max have no min so the
    `_protected_inventory_candidate_reason` "below current min"
    branch is unreachable for them.  Currently masked by
    `demand_signal > 0` keeping them as candidates anyway, but worth
    surfacing as a separate "missing min/max coverage" review bucket
    rather than hiding the gap.

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

- [ ] **Add a "no Min/Max coverage" startup count.**
  Today the only signal is `inventory_coverage_missing_keys` flowing
  into per-item `inventory_coverage_gap` review reasons.  A single
  startup banner ("2,352 sales items have no Min/Max row — sizing is
  sales-driven only") would let operators catch a broken X4 export
  before they trust the suggestions.
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

- [ ] **Surface `last_skipped_bulk_removals` in the UI.**  Today the data
  is recorded but no caller reads it.  Wire a one-line status banner
  ("Skipped K row(s) because the view shifted before confirm") into
  `bulk_sheet_actions_flow.bulk_remove_selected_rows` and the
  `bulk_remove_not_needed` confirm path.
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
