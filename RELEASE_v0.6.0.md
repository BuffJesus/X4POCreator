# Release Notes — v0.6.0

**Date:** 2026-04-08

---

## Summary

v0.6.0 opens the v0.6.x feature train with **Phase 1: Bulk Grid Text
Search** — a "Find a part by typing" entry field on the bulk tab filter
row.  The seven combo filters work well for category-level slicing but
have always been useless for locating a specific part number on a long
list.

937 tests pass (6 new regression tests).

---

## What's new

### Bulk Grid Text Search

A **Search:** entry field is now the first control on the bulk tab
filter row.  As you type, the bulk grid filters live to rows whose
**line code, item code, description, or supplier** contain the search
term (case-insensitive substring match).  Blank search = no filter.

The search composes with every other filter — the seven existing combos
(Line Code, Status, Source, Item Status, Performance, Sales Health,
Attention) still apply.  Clearing the search field restores the prior
filtered set.

**Implementation:**

- `var_bulk_text_filter` (Tk `StringVar`) drives a new `Entry` widget at
  the start of filter row 1.  Bound to `<KeyRelease>` so the filter
  re-applies on every keystroke.
- `bulk_filter_state(app)` now reads `text` from the StringVar.
- `bulk_filter_is_default(filter_state)` treats any non-blank text value
  as non-default, so the cached fast path correctly invalidates.
- New helper `ui_bulk.item_matches_text_filter(item, text)` does the
  case-insensitive substring match against `line_code`, `item_code`,
  `description`, and `inventory.supplier`.  Returns `True` for blank
  search so callers can pass it through unconditionally.
- `item_matches_bulk_filter` checks the text filter first (cheapest
  rejection) before evaluating the combo filters.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.5.5  |   931 |
| v0.6.0  |   937 |

Six new regression tests in `tests/test_ui_bulk.py` covering blank
search, item code / description / supplier matches, the
`bulk_filter_is_default` text invalidation, and `item_matches_bulk_filter`
end-to-end with the text key set.

---

## Files changed

- `ui_bulk.py` — search field, helper, state key, matcher wiring
- `tests/test_ui_bulk.py` — new `BulkTextFilterTests` class
- `app_version.py` — bumped to 0.6.0
- `ROADMAP_v0.6.md` — Phase 1 closed

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Bulk Grid Text Search | ✓ closed |
| Phase 2 — Supplier → Vendor Auto-mapping | open |
| Phase 3 — QOH Adjustment Review | open |
| Phase 4 — Ordering Algorithm Fixes | ✓ closed (apart from the optional pack-rounding defer behavior) |
| Phase 4b — Detailed Sales Parser Bugs | ✓ closed |
| Phase 4c — Bulk Removal Edge Cases | ✓ closed |
| Phase 5 — Manual QA | carry-over |
