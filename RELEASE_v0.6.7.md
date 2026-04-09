# Release Notes — v0.6.7

**Date:** 2026-04-08

---

## Summary

v0.6.7 fixes a real upgrade-path correctness bug: the parse cache
schema version had never been bumped despite multiple semantic changes
to `result` since v0.5.1.  Operators upgrading from v0.5.1 with
unchanged source CSVs would silently keep loading the old broken
`qty_sold` values from `parse_result_cache.pkl` until they re-exported
from X4.

985 tests pass (1 new regression test).

---

## Fix

### `PARSE_CACHE_SCHEMA_VERSION` bumped from 1 → 2 (`load_flow.py:13`)

`_load_parse_cache` rejects cached payloads whose stored
`schema_version` doesn't match the current constant.  The constant has
been frozen at `1` since the cache was added, but the shape and
semantics of `result` have changed in three releases since then:

- **v0.5.2** — `qty_sold` reads column 36 instead of column 26.  A
  cached `sales_items` from v0.5.1 reports the X4 group total
  multiplied by the detail-row count (typically 6× the real qty).
- **v0.5.3** — data-quality report cross-references
  `detailed_sales_stats_lookup` and `receipt_history_lookup`.  Cached
  results don't include the corrected warning rows.
- **v0.5.5** — added `no_minmax_coverage_keys` field for the Min/Max
  coverage warning.  Old caches don't have it.

The cache key is the file mtime + size of every loaded source.  An
operator who upgrades the executable but keeps using the same
already-loaded CSVs would silently get the v0.5.1 broken `qty_sold`
back until they re-exported from X4 (which most operators won't notice
needs doing).

**Fix:** bump `PARSE_CACHE_SCHEMA_VERSION` to `2` and add a comment
explaining when to bump it again.  On first launch of v0.6.7 the
existing `parse_result_cache.pkl` is silently rejected and a fresh
parse runs against the current code.

### Test added

`tests/test_load_flow.py::test_load_parse_cache_rejects_payload_from_older_schema_version`
writes a pickled payload with `schema_version = current - 1` and
asserts `_load_parse_cache` returns `None`.  This guards against the
schema-bump being forgotten on a future shape change.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.6.6  |   984 |
| v0.6.7  |   985 |

---

## Files changed

- `load_flow.py` — bumped `PARSE_CACHE_SCHEMA_VERSION` to 2 with a
  comment listing the changes that should have triggered earlier bumps
- `tests/test_load_flow.py` — schema-version rejection regression test
- `app_version.py` — bumped to 0.6.7

---

## Severity note

This fix matters most for operators who:

1. Were running v0.5.1 or earlier
2. Have a `parse_result_cache.pkl` file from that version
3. Upgraded to v0.5.2+ without re-exporting CSVs from X4

Operators who always re-export before each session, or who have never
hit the cache fast path, are unaffected.  The first launch of v0.6.7
makes the issue moot for everyone.
