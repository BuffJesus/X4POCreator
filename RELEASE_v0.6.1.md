# Release Notes — v0.6.1

**Date:** 2026-04-08

---

## Summary

v0.6.1 closes Phase 2 of the v0.6.x roadmap: **Supplier → Vendor
Auto-mapping**.  Operators with consistent supplier→vendor relationships
can now persist them once and have unassigned items auto-filled on
every subsequent session.

958 tests pass (21 new regression tests).

---

## What's new

### Supplier Map dialog

A new **Supplier Map...** button on the bulk tab vendor row opens a
dialog with three workflows:

1. **Manual edit** — Add / Update / Remove individual `supplier → vendor`
   pairs.  Both codes are normalized to upper case.
2. **Auto-learn from History** — scans the 25 most recent session
   snapshots and proposes a mapping for every supplier whose orders
   went predominantly to one vendor.  Existing manual entries always
   win on conflict.
3. **Apply to Session** — fills the `vendor` field on every unassigned
   item in the current session whose supplier matches a row in the map.
   Manual vendor assignments are never overwritten.

The map persists to `supplier_vendor_map.json` alongside the other
config files (local data folder or shared data folder).  Save uses
atomic tempfile + rename so a crashed write can never leave a
half-formed JSON file in place.

---

## Architecture

`supplier_map_flow.py` (new) hosts four pure functions, all unit-tested
without a UI:

- `load_supplier_map(path)` — tolerant loader; missing / malformed
  files return `{}`.
- `save_supplier_map(path, mapping)` — atomic write with normalization
  and blank-entry stripping.
- `apply_supplier_map(items, mapping)` — returns `(item, vendor)` pairs
  to apply, skipping items that already have a vendor or whose
  supplier isn't covered.
- `build_supplier_map_from_history(snapshots)` — counts
  `(supplier, vendor)` co-occurrences across `exported_items` (with
  `assigned_items` fallback) and returns the most-frequent vendor per
  supplier.
- `merge_supplier_maps(base, overlay, *, overlay_wins=False)` — bonus
  helper used by the dialog to fold inferred suggestions in without
  trampling manual entries.

`ui_supplier_map.py` (new) wires the four helpers into the dialog and
the bulk grid.  The dialog operates on a local working copy and only
touches `filtered_items` / `supplier_vendor_map.json` when the operator
explicitly clicks Apply or Save.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.6.0  |   937 |
| v0.6.1  |   958 |

21 new tests in `tests/test_supplier_map_flow.py` covering load/save
round-trip, code normalization, malformed-JSON tolerance, the
unassigned-only `apply` semantics, the history-aggregation tie-breaker,
and the merge precedence.

---

## Files changed / added

- `supplier_map_flow.py` (new) — pure helpers
- `ui_supplier_map.py` (new) — dialog
- `data_folder_flow.py` — registers `supplier_vendor_map` data path
- `ui_bulk.py` — "Supplier Map..." button on the vendor row
- `po_builder.py` — `_open_supplier_map` hook + import
- `tests/test_supplier_map_flow.py` (new) — 21 regression tests
- `app_version.py` — bumped to 0.6.1
- `ROADMAP_v0.6.md` — Phase 2 closed

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Bulk Grid Text Search | ✓ closed (v0.6.0) |
| Phase 2 — Supplier → Vendor Auto-mapping | ✓ closed (v0.6.1) |
| Phase 3 — QOH Adjustment Review | open |
| Phase 4 — Ordering Algorithm Fixes | ✓ closed (v0.5.5) |
| Phase 4b — Parser/Min/Max bugs | ✓ closed (v0.5.5) |
| Phase 4c — Bulk Removal Edge Cases | ✓ closed (v0.5.4) |
| Phase 5 — Manual QA | carry-over |
