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
