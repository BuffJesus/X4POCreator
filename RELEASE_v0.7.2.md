# Release Notes — v0.7.2

**Date:** 2026-04-08

---

## Summary

v0.7.2 closes Phase 3 of the v0.7.x roadmap: **Skip Cleanup Tools**.
The v0.5.4 → v0.6.5 fixes made 5,317 logically-skip items visible on
the user's real dataset, but the only thing the operator could do
with them was "Remove Not Needed" one filter scope at a time.  v0.7.2
adds bulk tooling that matches the scale of what's now visible.

1050 tests pass (24 new regression tests).

---

## What's new

### Skip Cleanup dialog

A new **Skip Cleanup...** button on the bulk tab removal row opens a
dialog with a **per-line-code cluster table** at the top and three
action buttons at the bottom.  The header shows "N skip items across
M line codes" so the operator sees the cluster shape immediately.

**Cluster table** lists every line code that has at least one skip
item, sorted by count descending.  The operator can:

- **Select one or more line codes** to scope every action to those
  clusters only.  Multiselect.
- **Leave the selection empty** to apply the action to every skip
  item in the session.

**Three actions** at the bottom of the dialog:

1. **Add to Ignore List** — pipes through the existing
   `_ignore_items_by_keys` flow.  Items are added to
   `ignored_items.txt` and removed from the current session in one
   pass; future loads will skip them until removed via Manage
   Ignored Items.
2. **Flag Discontinue** — sets `discontinue_candidate = True` on
   each item's order rule and saves `order_rules.json`.  This is a
   review marker only — items remain orderable until you formally
   discontinue them, but the marker shows up in the maintenance
   report.
3. **Export CSV** — writes a stand-alone CSV with line code, item
   code, description, qoh, current/suggested min/max, supplier,
   last sale date, last receipt date.  Designed for an offline
   review pass before triggering ignore / discontinue.

---

## Architecture

`skip_actions_flow.py` (new) hosts five pure helpers, all
unit-tested without a UI:

- `is_skip_item(item)` — canonical predicate (`final_qty <= 0` AND
  `raw_need <= 0`).  Reads the underlying numbers, not
  `item["status"]`, because that field is sometimes stale on items
  copied around between flows.
- `filter_skip_items(items)` — pure filter using the predicate.
- `count_skip_clusters_by_line_code(items)` — `[{"line_code": ...,
  "count": ...}, ...]` sorted by `(-count, line_code)`.
- `collect_keys_for_action(items)` / `collect_ignore_keys(items)` —
  builds the `(lc, ic)` tuples / `LC:IC` strings the existing
  ignore / discontinue flows expect, dropping items with blank
  item codes.
- `build_skip_export_rows(items, inventory_lookup)` and
  `render_skip_csv(rows)` — together produce the CSV export string.

`ui_skip_actions.py` (new) wires the helpers into the dialog with a
ttk Treeview for the cluster table and buttons for each action.  The
dialog operates on `app.filtered_items` regardless of which Item
Status filter is currently active, so the operator can pre-narrow
with the bulk grid filters or skip them and act on every skip item.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.7.1  |  1026 |
| v0.7.2  |  1050 |

24 new tests in `tests/test_skip_actions_flow.py` covering:

- `is_skip_item` predicate including non-numeric coercion and the
  non-mapping guard
- `filter_skip_items` end-to-end
- `count_skip_clusters_by_line_code` (groups, sorts, drops
  non-skip items, alphabetical tie-break)
- `collect_keys_for_action` and `collect_ignore_keys` including
  the blank-item-code skip
- `build_skip_export_rows` with inventory lookup, with the
  inventory-on-item fallback, with item-supplied last-sale-date,
  with suggested min/max, and the row sort order
- `render_skip_csv` header + row formatting, empty-rows path, and
  extras-ignored guard

---

## Files changed / added

- `skip_actions_flow.py` (new) — five pure helpers
- `ui_skip_actions.py` (new) — dialog
- `ui_bulk.py` — "Skip Cleanup..." button on the removal row
- `po_builder.py` — `_open_skip_actions` hook + import
- `tests/test_skip_actions_flow.py` (new) — 24 regression tests
- `app_version.py` — bumped to 0.7.2
- `ROADMAP_v0.7.md` — Phase 3 closed

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed (v0.7.0) |
| Phase 2 — Vendor-centric Workflows | ✓ closed (v0.7.1, 2 polish items deferred) |
| Phase 3 — Skip Cleanup Tools | ✓ closed (v0.7.2) |
| Phase 4 — Performance & Correctness Carry-over | open |

**All three feature phases of v0.7.x are now closed.**  Phase 4 is
the performance / carry-over bucket — pack-rounding overshoot defer,
bulk grid render perf audit on 8,409 items, the deferred Phase 2
vendor-combobox lead-time hint, and the Phase 5 manual QA pass.
None of those are urgent and they can be batched into a v0.7.3.
