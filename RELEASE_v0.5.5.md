# Release Notes — v0.5.5

**Date:** 2026-04-08

---

## Summary

v0.5.5 closes out the Phase 4 ordering-algorithm fixes and the "no
Min/Max coverage" startup banner from the v0.6.x roadmap.  Three
internal-quality fixes; no behavior change for items the algorithm was
already getting right.

931 tests pass (4 new regression tests).

---

## Fixes

### 1. Description fallback walks every loaded source (`reorder_flow.py:269`)

`_description_for_key` only checked `inventory_lookup` and `sales_items`,
so items appearing only in receipts, open POs, suspended carry, or the
detailed-sales rollup came back with blank descriptions in the bulk
grid, review tab, and exported sheets.

**Fix:** the fallback chain now walks `sales_items`, `receipts_items`,
`open_po_items`, `suspended_items`, `detailed_sales_rows`, and
`suspended_lookup` (in that order) before giving up.

### 2. Post-receipt overstock is now visible to reviewers (`rules.py:1149`)

`assess_post_receipt_overstock` already stamped `projected_overstock_qty`
and `overstock_within_tolerance` on every item, but `evaluate_item_status`
ignored both — so an order that would push stock past max (typically
because rounding a partial pack overshoots) would silently export.

**Fix:** `evaluate_item_status` now raises two new data flags:

- **`would_overshoot_max`** — fires when `projected_overstock_qty > 0`
  and the projection is outside the per-item tolerance.  Catches the
  classic "qoh=300, max=496, pack=300 → suggested 300 → ending stock 600
  (104 past max)" trap.
- **`order_floor_above_max`** — fires when an aggressive
  `minimum_packs_on_hand` floor pushes the effective order floor past
  `target + acceptable_overstock` even before pack rounding.

Both flags appear in the data_flags column for review and can be filtered
on by downstream tooling.

### 3. "No Min/Max coverage" startup banner (`load_flow.py:792`)

The X4 "On Hand Min Max Sales" report has a "Show items with zero on
hand" toggle that, when off, omits items with QOH=0.  Operators had no
visible signal that the export was incomplete.  v0.5.2 added a
`would_overshoot_max` review reason for individual items but did not
surface the cross-item count.

**Fix:** `parse_all_files` now stamps `result["no_minmax_coverage_keys"]`
(items that are in `inventory_lookup` from the On Hand Report fallback
but have no min/max anchor) and emits a startup warning:

> N sales item(s) have inventory rows but no min/max anchor — sizing
> for these items is purely sales-driven.  If your X4 'On Hand Min Max
> Sales' export has the 'Show items with zero on hand' toggle off, turn
> it on and reload.

On the user's real toggle-off export this surfaces **6,006 items** with
no anchor.  The toggle-on export shrinks that to ~76 (verified in v0.5.2).

---

## Test count

| Release | Tests |
|---------|-------|
| v0.5.4  |   927 |
| v0.5.5  |   931 |

Four new regression tests:
- `test_evaluate_item_status_flags_would_overshoot_max`
- `test_evaluate_item_status_flags_order_floor_above_max`
- `test_description_for_key_walks_all_loaded_sources`
- `test_description_for_key_falls_back_to_suspended_lookup`

---

## Files changed

- `reorder_flow.py` — description fallback walks every loaded source
- `rules.py` — `evaluate_item_status` raises overshoot data flags
- `load_flow.py` — Min/Max coverage startup warning
- `tests/test_rules.py`, `tests/test_reorder_flow.py` — regression coverage
- `app_version.py` — bumped to 0.5.5
- `ROADMAP_v0.6.md` — Phase 4 + Min/Max coverage items closed

---

## Roadmap status after this release

Phase 4 (Ordering Algorithm Fixes) is closed apart from the
pack-rounding overshoot **defer** behavior, which is intentionally
deferred (no pun intended) — escalating to manual_only when the
overstock projection blows the tolerance is the safer default for now.
Phase 4b/4c are fully closed.  v0.6.x feature phases (Search, Supplier
Map, QOH Review) remain untouched and ready for a focused next session.
