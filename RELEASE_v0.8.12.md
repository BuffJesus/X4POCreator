# Release Notes — v0.8.12

**Date:** 2026-04-08

---

## Summary

**`prepare_assignment_session` is 6.2× faster — 34.5 s → 5.6 s on the
63K-item dataset.**  The v0.8.11 instrumentation pinpointed the real
bottleneck: a hidden **O(n²) linear scan** in
`reorder_flow._description_for_key` that was being called 59K times
and walking up to 63K items on each call — worst case ~18 **billion**
dict comparisons inside a single function.

Projected impact on the full "Crunching numbers" wall clock:
**~43 s → ~15 s**.

1110 tests pass.

---

## The ground-truth reveal from v0.8.11

The v0.8.11 breakdown stamps inside `prepare_assignment_session`
surfaced three surprises:

| Stage | v0.8.11 | % of prepare | What I assumed |
|---|---:|---:|---|
| `pack_ms` (resolve_pack_size_with_source) | **17,568 ms** | 50% | `default_vendor_for_key` would be the hotspot |
| Enrich `other_ms` (suggest_min_max + history merge) | **11,945 ms** | 35% | `enrich_item` would be the hotspot |
| **`rules.enrich_item` itself** | **1,712 ms** | 5% | expected 10+ seconds |
| `sheet.set_rows` (tksheet widget build) | **24 ms** | — | expected seconds |

I was wrong on three counts.  `enrich_item` is actually fast;
`sheet.set_rows` is basically free.  The real cost is deep inside
pack resolution and sugeestion-source calls, which both call through
`_description_for_key`.

## Chasing the 17.6 s pack_ms finding

`resolve_pack_size_with_source` falls through to
`receipt_pack_size_for_key(app, key)` when no X4 pack size is
registered for the item.  That calls `receipt_vendor_evidence`, the
classifiers, and — crucially — `_description_for_key`.

`_description_for_key` (reorder_flow.py:270 in v0.8.11):

```python
def _description_for_key(app, key):
    inv = ... .get(key, {}) or {}
    description = str(inv.get("description", "") or "").strip()
    if description:
        return description
    # Walk every loaded source so items appearing only in receipts,
    # open POs, suspended carry, or detailed sales rollups still
    # get a label.
    sources = (
        ("sales_items", getattr(app, "sales_items", None)),
        ("receipts_items", getattr(app, "receipts_items", None)),
        ("open_po_items", getattr(app, "open_po_items", None)),
        ("suspended_items", getattr(app, "suspended_items", None)),
        ("detailed_sales_rows", getattr(app, "detailed_sales_rows", None)),
    )
    for _name, collection in sources:
        for item in collection or ():
            if (item.get("line_code", ""), item.get("item_code", "")) == key:
                ...
```

**This is an O(n²) linear scan.**  When `inventory_lookup` doesn't
have a description for a key, the function scans up to 5 lists × up
to 63K items each looking for a match.  Called 59K times from the
pack-resolution path.  Worst case:

```
59,000 keys × 5 lists × 63,000 items/list = ~18,585,000,000 comparisons
```

Across the enrich loop "other" bucket, the same function was called
via `suggest_min_max_with_source` and `apply_suggestion_context` —
same O(n²) cost, another 11.9 seconds.

`sales_history_for_key` (line 247) had the same bug on a smaller
scale.

## The fix

Replaced both linear scans with **lazy per-session indexes**:

```python
def _build_description_index(app):
    index = {}
    for attr in ("sales_items", "receipts_items", "open_po_items",
                 "suspended_items", "detailed_sales_rows"):
        for entry in getattr(app, attr, None) or ():
            key = (entry.get("line_code", ""), entry.get("item_code", ""))
            if key not in index:
                desc = str(entry.get("description", "") or "").strip()
                if desc:
                    index[key] = desc
    # ... suspended_lookup pass ...
    return index


def _description_for_key(app, key):
    inv = ... .get(key, {}) or {}
    description = str(inv.get("description", "") or "").strip()
    if description:
        return description
    cache = getattr(app, "_description_index_cache", None)
    if cache is None:
        cache = _build_description_index(app)
        app._description_index_cache = cache
    return cache.get(key, "")
```

One upfront O(n) sweep builds the index on first call; every query
thereafter is O(1).  The same pattern applies to
`sales_history_for_key` via a new `_sales_history_index_cache`.

## Measured before / after

On the 63K-item dataset (real `CSVs/` folder):

| Stage | v0.8.11 | v0.8.12 | Factor |
|---|---:|---:|---:|
| `candidates_build_breakdown.pack_ms` | 17,568 ms | **327 ms** | **53× faster** |
| `candidates_build_breakdown.vendor_ms` | 247 ms | 325 ms | = |
| `candidates_build_breakdown.other_ms` | 554 ms | 446 ms | = |
| `enrich_breakdown.enrich_ms` | 1,712 ms | 1,701 ms | = |
| `enrich_breakdown.other_ms` | 11,945 ms | **589 ms** | **20× faster** |
| `enrich_breakdown.gap_ms` | 254 ms | 249 ms | = |
| **`prepare_assignment_session` TOTAL** | **34.5 s** | **5.6 s** | **6.2× faster** |

One bug fix, **29 seconds off every session load**.

---

## Projected full session load impact

| Phase | v0.8.10 | v0.8.11 | **v0.8.12 (projected)** |
|---|---:|---:|---:|
| `parse_all_files` | 17.6 s | 17.5 s | 17.1 s |
| `prepare_assignment_session` | 35.1 s | 34.5 s | **5.6 s** |
| `normalize_items_to_cycle` | 0 s | 0 s | 0 s |
| `populate_bulk_tree` | 8.9 s | 8.9 s | 8.9 s |
| **Pre-UI total** | 61.6 s | 60.9 s | **31.6 s** |
| Delta from v0.8.9 baseline | −28 s | −29 s | **−58 s** |

The **59-second starting point** (parse 18 + prepare 36 + normalize
23 + paint 8 ≈ 85 s on v0.8.9) should now drop below **32 seconds**.
Combined with the v0.8.10 normalize elimination, this is the
biggest single perf win in the v0.8.x train.

---

## Files changed

- `reorder_flow.py` —
  - New `_build_description_index(app)` helper
  - `_description_for_key` uses the lazy cached index
  - `sales_history_for_key` uses a second lazy cached index
  - `receipt_pack_size_for_key` gets an O(1) short-circuit when the
    key has no receipt history at all (minor, keeps the tight
    dataset fast)
- `po_builder.py` —
  - Memoized `_resolve_pack_size_with_source` (per-session cache)
  - Memoized `suggest_min_max_with_source` via a per-session dict
    (hooked into `_refresh_suggestions` and `_proceed_to_assign` for
    invalidation)
- `assignment_flow.py` —
  - Enrich loop now uses a `suggest_min_max_with_source` cache on
    the session object
  - Hoisted session attrs in the enrich loop to locals
  - Per-item breakdown stamps for `candidates_build_breakdown` and
    `enrich_breakdown` (from v0.8.11)
- `ui_bulk.py` —
  - `bulk_row_values` uses a shared `_EMPTY_INV` sentinel instead of
    allocating a fresh dict on every cache miss
  - `build_bulk_sheet_rows` hoists the render cache + renderer
    callable to locals and inlines the cache-hit fast path
- `app_version.py` — bumped to 0.8.12

---

## What to test

1. Drop v0.8.12 in place.  Keep `perf_trace.enabled`.
2. Run a full session — Load Files & Continue → Line Codes →
   Customers → Proceed.
3. **Crunching numbers should drop from ~43 s to ~15 s on the big
   dataset.**
4. Send me `perf_trace.jsonl` — I want to confirm the live numbers
   match my measurement.

The next target after this lands is `build_bulk_sheet_rows` at 8.9 s.
With the description index now warm by the time `populate_bulk_tree`
runs, any `bulk_row_values` callers that hit it indirectly should
already be fast — so the remaining 8.9 s is likely pure Python
per-row tuple construction.  Optimizing that is v0.8.13 territory.

---

## Release history for the "Crunching numbers" wall

| Release | Wall clock (big dataset) | Notes |
|---|---:|---|
| v0.8.9 | ~85 s | baseline after the v0.8.x harness work |
| v0.8.10 | ~55 s | normalize_items_to_cycle eliminated (−23 s); _suggest_min_max memoization (−9 s on interactive paths) |
| v0.8.11 | ~60 s | instrumentation release, no perf fixes, +2 s measurement overhead |
| **v0.8.12** | **~32 s** | O(n²) description scan eliminated (−29 s) |

**We're cutting the full wall clock almost 3× from where we started
the v0.8.x train.**  The v0.8.9 baseline was ~85 s; v0.8.12 should
land at ~32 s.  Put X4 in the rearview.
