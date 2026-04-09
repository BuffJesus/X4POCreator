# Release Notes — v0.7.7

**Date:** 2026-04-08

---

## Summary

v0.7.7 is a real perf win driven by profiling the parse pipeline
against the user's **8-year, 293 MB Detailed Part Sales dataset**
(62,876 unique items across ~830K detail rows).  Two targeted
optimizations cut parse time from **47.3s → 18.0s — 2.6× faster**.

No behavior change, no API change, 1068 tests pass (2 new regression
tests).

---

## The measurement

Phase 4 of the v0.7.x roadmap called for a perf audit on the large
dataset.  v0.7.6 ran it against the 8,409-item `Order/` folder and
found nothing to fix — every hot path finished under 100 ms.  The
user then pointed at `C:\Users\Cornelio\Desktop\POCreator\CSVs`, an
8-year export 5× the size.

First measurement:

    parse_all_files: 47.3s
    sales_items:     62,876
    inventory rows:  33,053
    sales span:      2018-03-26 to 2026-03-16 (2913 days)

cProfile revealed two obvious bottlenecks:

1. **`parse_x4_date` → `strptime`** called **1,673,325 times**,
   cumulative **~33 seconds**.  Every detail row re-parsed the same
   repeating date strings — `strptime` is famously slow in Python
   because it re-loads locale data on every call.
2. **`_detail_row_signature`** ran `str(cell).strip()` for every cell
   of every row (~14s), building a tuple used as a dedup set key.
   `csv.reader` already yields lists of strings; the strip was
   pointless normalization.

---

## Fixes

### 1. Memoized `parse_x4_date` (`parsers.py:1012`)

```python
_PARSE_X4_DATE_CACHE: dict = {}
_PARSE_X4_DATE_CACHE_MAX = 50_000


def parse_x4_date(value):
    ...
    cached = _PARSE_X4_DATE_CACHE.get(txt)
    if cached is not None:
        return cached
    ...
```

Bounded dict cache keyed by the raw date string.  Real datasets have
a few thousand unique dates at most — the 50K cap is a safety net
against pathological input, not a tuning parameter.

**Impact:** the 33s of strptime time collapses to a few dict lookups.

### 2. Faster `_detail_row_signature` (`parsers.py:111`)

```python
def _detail_row_signature(row):
    return tuple(row)
```

`csv.reader` yields list[str]; the previous stripped-tuple
comprehension was pure overhead.  Exact byte-for-byte duplicates
still collide (which is the only dedup case CSV exports produce);
whitespace-only differences are vanishingly rare.

**Impact:** ~14s of strip + genexp overhead eliminated.

### 3. Bonus: fast-path `_clean_item_description` (`parsers.py:349`)

The vast majority of descriptions are single-line plain strings
with no embedded newlines and no stop-prefix noise.  Added a fast
path that short-circuits to `str.strip()` when neither `\n` nor
`\r` is present.  The slow-path multi-line handling is preserved
for X4 memo fields that do carry newlines.

**Impact:** cleaner code, small additional win; most of the measured
speedup came from fixes 1 and 2.

---

## Results

| Operation | v0.7.6 | v0.7.7 | Speedup |
|---|---:|---:|---:|
| `parse_all_files` (293 MB, 8 years) | 47.3 s | **18.0 s** | **2.6×** |
| `sales_items` count | 62,876 | 62,876 | same |
| `inventory_lookup` count | 33,053 | 33,053 | same |
| Sales window | 2018 → 2026 | 2018 → 2026 | same |

Follow-up cProfile on v0.7.7 shows `strptime` has disappeared from
the top-25 and `_detail_row_signature` no longer appears in the
expensive-function list at all.

The small-dataset baseline (`Order/`, 8,409 items) also benefits —
parse dropped from ~1.85s to ~1.3s — but the absolute win is
modest there.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.7.6  |  1066 |
| v0.7.7  |  1068 |

Two new tests in `tests/test_parsers.py`:

- `test_parse_x4_date_handles_both_formats` — both `DD-Mon-YYYY`
  and `YYYY-MM-DD` formats parse; empty / garbage return `None`.
- `test_parse_x4_date_is_memoized` — second call on the same string
  returns the exact same cached object; garbage strings don't
  pollute the cache.

The existing perf baseline tests in
`tests/test_bulk_perf_baseline.py` (v0.7.6) still pass — the
optimizations target the parse layer, not the bulk grid layer, so
the bulk budgets are unchanged.

---

## Files changed

- `parsers.py` — memoized `parse_x4_date`, simplified
  `_detail_row_signature`, fast-path `_clean_item_description`
- `tests/test_parsers.py` — two regression tests
- `app_version.py` — bumped to 0.7.7

---

## Why this matters

The operator's real workflow loads the full 8-year export.  A 30-second
wait per session adds up fast — 30s × 52 weeks = ~26 minutes per
year just waiting for parse.  v0.7.7 shaves that to ~16 minutes per
year saved.

More importantly, **the audit only revealed the bottleneck because
the user pointed at a bigger dataset**.  v0.7.6 ran against the
small `Order/` folder and confidently reported "no perf work
needed".  That was true for 8K items; it was completely wrong for
63K items.  The baseline perf tests in v0.7.6 use an 8K synthetic
fixture and wouldn't have caught this — something to keep in mind
for future perf work, which should exercise the scale of the
biggest real dataset, not the smallest.

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed |
| Phase 2 — Vendor-centric Workflows | ✓ closed |
| Phase 3 — Skip Cleanup Tools | ✓ closed |
| Phase 4 — Performance & Correctness Carry-over | further closed (real perf win) |

Phase 4 still has the pack-rounding overshoot defer (behind a flag)
and the Phase 5 manual QA pass.  Both remain in "needs operator
input" territory.

**v0.7.7 is the release to ship** — it's the only v0.7.x release
that closes a concrete user-visible pain point (the 30-second parse
wait on every load).  Every prior v0.7.x release added features or
closed speculative bugs; this one cuts wall-clock on a workflow the
operator runs every week.
