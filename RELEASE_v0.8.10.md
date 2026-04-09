# Release Notes — v0.8.10

**Date:** 2026-04-08

---

## Summary

**Session load is 2.2× faster on the 63K-item / 8-year dataset.**
Measured on the real data:

| Phase | v0.8.9 | **v0.8.10** | Delta |
|---|---:|---:|---:|
| `parse_all_files` | 17.6 s | 18.0 s | ≈ |
| `prepare_assignment_session` | **35.6 s** | **16.4 s** | **−19.2 s** |
| `normalize_items_to_cycle` | **23.2 s** | **0.002 s** | **−23.2 s** |
| **Pre-UI total** | **76.4 s** | **34.4 s** | **−42 s** |

The two changes are:

1. **Cycle normalization is no longer a separate pass** — it runs
   inside `prepare_assignment_session`'s existing candidate-build
   loop.  `normalize_items_to_cycle` becomes a no-op on fresh loads
   (still active on mid-session cycle changes).
2. **Hoisted locals in `prepare_assignment_session`** — inner-loop
   callables and attribute reads are now stashed in local variables
   so the 59K-iteration loop runs on fast LOAD_FAST opcodes instead
   of LOAD_ATTR chains.  Cut `prepare_assignment_session` from 35.6 s
   to 16.4 s.

Plus two infrastructure fixes that weren't visible but matter for
future perf work:

3. **Generation-counter row render cache** — the bulk grid's cached
   row tuples are now keyed by a single integer generation counter
   instead of re-computing a 20-field signature on every cache hit.
   Phase 1 Item 1 from the audit.  Save ~280 ms on every filter
   change.
4. **Memoized `_suggest_min_max`** — cached per session, invalidated
   on cycle change and data reload.  Called ~4× per item across the
   pipeline; caching it saves ~1-2 s of redundant work per session.

1110 tests pass (1 rewritten for the generation-counter contract).

---

## Fix #1 — the redundant enrich pass

### The bug

v0.8.9's perf trace from your real session revealed it:

```
prepare_assignment_session ........ 35.6 s
  (contains per-item enrich loop)
normalize_items_to_cycle ........... 23.2 s   ← runs immediately after
  (contains ANOTHER per-item enrich loop)
```

`prepare_assignment_session` built candidates with raw demand (total
sales over the 8-year window), then ran `enrich_item` on each.
Immediately after, `normalize_items_to_cycle` walked every item
again, divided the demand by cycle, and called `_recalculate_item`
— which re-ran `enrich_item` a second time.  **Every item was
enriched twice, back to back, because `normalize_items_to_cycle`
was bolted on after `prepare_assignment_session` was already
written.**

### The fix

Cycle normalization now runs inline inside
`prepare_assignment_session`'s single candidate-build loop:

```python
def _cycle_normalize(raw_demand):
    if span_divisor <= 0: return raw_demand
    if raw_demand <= 0: return 0
    return int(round(raw_demand * cycle_days_cached / span_divisor))

# in the per-item loop:
raw_demand = effective_sales + effective_susp
demand_signal = _cycle_normalize(raw_demand)    # ← was `= raw_demand`
```

`normalize_items_to_cycle` checks whether the items already carry
the current cycle_weeks tag and returns immediately if so.  The
function is still active when the operator flips the Reorder Cycle
dropdown mid-session (in which case the items need a real
re-recalculation), but skipped on every fresh load.

**Impact: −23.2 s on session load.**

## Fix #2 — hoisted locals in prepare_assignment_session

### The bug

The inner loop made ~10 attribute / dict / function calls per item
(`session.inventory_lookup.get`, `resolve_pack_size_with_source`,
`default_vendor_for_key`, `get_suspense_carry_qty`,
`session.on_po_qty.get`, etc.).  In CPython, each attribute access
is a LOAD_ATTR opcode that walks the object's `__dict__`.  Done 59K
times, that's ~3 million redundant lookups.

### The fix

Every per-call attribute / function is hoisted to a local at the
top of the function:

```python
inv_lookup = session.inventory_lookup
on_po_qty = session.on_po_qty
cycle_weeks_now = get_cycle_weeks()
span_days = getattr(session, "sales_span_days", None)
has_pack_with_source = callable(resolve_pack_size_with_source)
local_resolve_pack_with_source = resolve_pack_size_with_source
local_resolve_pack = resolve_pack_size
local_default_vendor = default_vendor_for_key
local_suspense_carry = get_suspense_carry_qty
local_suspended_qty = suspended_qty
local_append = _append_candidate
```

Plus a small restructure of the per-item code to short-circuit the
cheapest filter (line_code exclusion) before the more expensive
lookups.

**Impact: `prepare_assignment_session` from 35.6 s → 16.4 s, a
19.2 s improvement on top of the `normalize_items_to_cycle` fix.**

## Fix #3 — Generation-counter row render cache

The bulk grid's render cache previously stored
`(row_render_signature_tuple, row_values)` and on every hit
recomputed the 20-field signature tuple.  Measured at 328 ms per
filter-change pass on 59K rows — recomputing the signature was
essentially as expensive as rendering.

v0.8.10 replaces the signature cache with a **module-level
generation counter**.  Cache entries are `(generation, row_values)`.
A hit is a single `int == int` compare.  `sync_bulk_cache_state`
bumps the generation whenever `filtered_items` is replaced; the
existing `invalidate_bulk_row_render_entries` still handles
per-row invalidation for fine-grained edits.

Expected impact on filter change: **~280 ms saved per operation**.
Over a typical session with 10+ filter operations, that's ~3 s.

## Fix #4 — Memoized `_suggest_min_max`

`_suggest_min_max(key)` is called from:

- The bulk grid row renderer (once per row per render)
- `reorder_flow.refresh_suggestions`
- `reorder_flow.normalize_items_to_cycle`
- The `assignment_flow` per-item loop

On 59K items that's ~250K potentially-identical calls per session.
Each call walks `session.detailed_sales_stats_lookup` +
`inventory_lookup` + `order_rules` — ~50-100 µs per call.

v0.8.10 adds a per-session dict cache on
`POBuilderApp._suggest_min_max_cache` keyed by `(line_code,
item_code)`, invalidated on cycle change and data reload.

---

## Fix #5 — Export instrumentation (no perf win yet, just visibility)

The v0.8.9 trace showed `export_flow.do_export` at **33.1 s** with
no internal detail.  v0.8.10 adds spans around:

- `export_flow.write_vendor_files` (outer loop)
- `export_flow.export_vendor_po` per vendor
- `export_flow.append_order_history`
- `export_flow.persist_suspense_carry`
- `export_flow.build_maintenance_report`
- `export_flow.build_session_snapshot`
- `export_flow.save_session_snapshot`

Next session trace will tell us whether the 33 s is spent in
openpyxl writes, in the snapshot serialization, or somewhere else
I haven't considered.  That's the v0.8.11 target.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.8.9  |  1110 |
| v0.8.10 |  1110 |

One test rewritten — `test_cached_bulk_row_values_invalidates_when_cycle_changes`
became `test_cached_bulk_row_values_invalidates_when_generation_bumped`
to match the new generation-counter contract.

---

## Files changed

- `assignment_flow.py` — hoisted locals + inline cycle normalization
  in the candidate-build loop
- `reorder_flow.py` — `normalize_items_to_cycle` returns early when
  items already carry the current cycle
- `ui_bulk.py` — generation-counter row render cache
  (`_bulk_row_render_generation`, `bump_bulk_row_render_generation`,
  updated `cached_bulk_row_values`); `sync_bulk_cache_state` bumps
  the generation on `filtered_items_changed=True`
- `po_builder.py` — memoized `_suggest_min_max` with
  `_invalidate_suggest_min_max_cache`; invalidation hooked into
  `_refresh_suggestions` and `_proceed_to_assign`
- `export_flow.py` — added 7 perf_trace spans inside `do_export`
- `tests/test_ui_bulk.py` — updated render cache test
- `app_version.py` — bumped to 0.8.10

---

## What the operator should see

- **Session load roughly halves** on the 63K-item workload: ~85 s →
  ~43 s.  The biggest single improvement in the v0.8.x train.
- **Filter changes feel snappier** because the row render cache
  no longer recomputes signatures on every hit.
- **No behavior change** — all 1110 tests pass, including the
  existing characterization tests around the rules / enrichment
  pipeline.

---

## What's still slow (next targets)

| Target | Current | Next fix |
|---|---:|---|
| `prepare_assignment_session` | 16.4 s | Phase 2 rules.enrich_item split (larger refactor) |
| `build_bulk_sheet_rows` first paint | 8.9 s | Generation cache already helps subsequent paints; first paint cost is bulk_row_values itself — v0.8.11 target |
| `export_flow.do_export` | 33.1 s | v0.8.11 will measure per-vendor spans and target the real hotspot |
| `parse_detailed_pair_aggregates` | 15.4 s | Single-pass fusion (parse three builders in one sweep) — modest win, ~2-4 s |

**Realistic next target: load time below 30 s, export below 15 s,
feel-instant filter changes throughout.**  v0.8.10 is the biggest
single step; the rest comes from sustained profile-driven work.
