# Release Notes — v0.8.14

**Date:** 2026-04-09

---

## Summary

Continuing the structural refactors and closing out remaining roadmap
items.  Adds "Clear Notes" button, precomputed text filter haystack,
and extracts `parsers/csv_io.py`.

1140 tests pass.

---

## New: Clear Notes button

"Clear Notes" button added to the bulk grid removal toolbar.  Clears
the notes field for all selected rows and persists the change to
`item_notes.json`.  Closes the last open Phase 1c item.

---

## Performance: precomputed text filter haystack

Text search on the bulk grid previously called `str.lower()` on 4-6
fields per item on every keystroke.  Now a single lowered haystack
string is stamped on each item during `build_bulk_sheet_rows` and
invalidated on edit.  The text filter does one `needle in haystack`
check per item.  Expected: **~83 ms → ~10 ms** on 59K items.

---

## Structural: `parsers/csv_io.py` extracted

Header matching, layout detection, dedup, and generic/X4 row
iterators moved from `parsers/__init__.py` to `parsers/csv_io.py`.
`HEADER_ALIASES` stays in `__init__.py` and is passed as a parameter
to the extracted functions.

**parsers/ package now:**

| Module | Contents |
|---|---|
| `parsers/__init__.py` | Re-export shim + `HEADER_ALIASES` + report parsers |
| `parsers/csv_io.py` | Header matching, layout detection, row iterators, dedup |
| `parsers/dates.py` | `parse_x4_date` + memoization cache |
| `parsers/normalize.py` | `_safe_cell`, `_coerce_int`, `_normalize_header_label`, etc. |

---

## Release history

| Release | Headline |
|---|---|
| v0.8.12 | O(n²) description scan eliminated (−29 s) |
| v0.8.13 | 5 bug fixes + 6 UX features + bulk edit 7.5× + rules/parsers/models refactor |
| **v0.8.14** | **Clear Notes + text filter perf + parsers/csv_io extraction** |
