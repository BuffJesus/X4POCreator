# Release Notes — v0.8.11

**Date:** 2026-04-08

---

## Summary

v0.8.11 is a **measurement release**.  The operator reported that
"Crunching numbers" feels longer than the captured numbers show, and
they were right — the v0.8.10 trace was missing **every** step in the
click-to-grid path except the three biggest ones.  v0.8.11 closes
that gap with end-to-end wall-clock spans and per-stage breakdowns
so the next trace captures the full picture.

No perf fixes in this release.  The goal is to **see what's actually
eating the 85+ seconds**, then target the hot path in v0.8.12 with
real data.

1110 tests pass.

---

## What v0.8.10 was missing

The "Crunching numbers" phase covers two distinct flows:

**Flow A — Load Files & Continue (`_do_load`):**

| Step | v0.8.10 coverage | v0.8.11 |
|---|---|---|
| Outer wall-clock of `_do_load` | ❌ not captured | ✓ `po_builder._do_load` |
| `load_flow.parse_all_files` | ✓ | ✓ |
| `apply_load_result` + warnings | ❌ | ✓ `po_builder.apply_load_result_and_warnings` |
| `compute_data_quality_summary` | ❌ | ✓ `po_builder.compute_data_quality_summary` |
| `refresh_data_quality_card` | ❌ | ✓ `po_builder.refresh_data_quality_card` |
| `_populate_exclude_tab` | ❌ | ✓ `po_builder.populate_exclude_tab` |

**Flow B — Proceed to Assign (`_proceed_to_assign`):**

| Step | v0.8.10 coverage | v0.8.11 |
|---|---|---|
| Outer wall-clock of `_proceed_to_assign` | ❌ not captured | ✓ `po_builder.proceed_to_assign` |
| `prepare_assignment_session` (total) | ✓ | ✓ |
| ├─ candidate-build loop breakdown | ❌ | ✓ `assignment_flow.candidates_build_breakdown` with `vendor_ms` / `pack_ms` / `suspense_ms` / `other_ms` |
| ├─ enrich loop breakdown | ❌ | ✓ `assignment_flow.enrich_breakdown` with `enrich_ms` / `gap_ms` / `other_ms` |
| `normalize_items_to_cycle` | ✓ | ✓ (still fast) |
| `_refresh_vendor_inputs` | ❌ | ✓ `po_builder.refresh_vendor_inputs` |
| `restore_bulk_filter_sort_state` | ❌ | ✓ `po_builder.restore_bulk_filter_sort_state` |
| `_populate_bulk_tree` | ⚠ (only the inner `build_bulk_sheet_rows`) | ✓ `ui_bulk.populate_bulk_tree` total |
| ├─ `sync_metadata` if rebuilt | ❌ | ✓ `populate_bulk_tree.sync_metadata` |
| ├─ `build_bulk_sheet_rows` | ✓ | ✓ |
| ├─ `store_visible_rows` | ❌ | ✓ `populate_bulk_tree.store_visible_rows` |
| ├─ combobox value updates | ❌ | ✓ `populate_bulk_tree.combobox_values` |
| ├─ `update_bulk_summary` | ❌ | ✓ `populate_bulk_tree.update_summary` |
| └─ `sheet.set_rows` (tksheet cost) | ❌ | ✓ `populate_bulk_tree.sheet_set_rows` ← **likely biggest first-paint win** |

Plus stage stamps at every phase transition so deltas between
consecutive stamps give wall-clock per stage.

---

## Why the outer wrappers matter

The v0.8.10 trace captured the **inner** functions but not the
**wrappers** that call them.  That meant time spent in:

- Tk event pumping between stages
- Per-stage Python glue code
- messagebox warnings that appear during load
- `_populate_exclude_tab` building one checkbox per line code
- `sheet.set_rows` (tksheet's own widget-rebuilding cost)

…was **completely invisible** to the harness.  On the 63K dataset
with 4,500+ line codes, `_populate_exclude_tab` could be several
seconds alone, and `sheet.set_rows` on 59K rows is almost certainly
the single biggest chunk of the "first paint" 8.7 s.

v0.8.11 surfaces every one of them as a discrete span.

---

## Breakdown instrumentation

Inside the per-item loops of `prepare_assignment_session`, v0.8.11
now tracks four separate accumulators per loop:

**Candidate-build loop:**
- `vendor_ms` — time spent in `default_vendor_for_key(key)` calls
- `pack_ms` — time spent in `resolve_pack_size_with_source(key)` calls
- `suspense_ms` — time spent in `suspended_qty.get` + `get_suspense_carry_qty`
- `other_ms` — everything else (dict build, key filters, normalization)

**Enrich loop:**
- `enrich_ms` — time spent in `rules.enrich_item` itself
- `gap_ms` — time spent in `append_suggestion_comparison_reason` +
  `apply_suggestion_gap_review_state`
- `other_ms` — the per-item glue (`suggest_min_max_with_source`,
  `apply_suggestion_context`, `apply_recent_order_context`, rule
  lookup, history merge, etc.)

The breakdowns land in the trace as `stamp` events.  Summed across
all 59K items, they'll tell us exactly which sub-function is the
dominant cost.  My current hypothesis is that **`default_vendor_for_key`
is ~5-8 s** (it walks receipt_history per call), but let's measure
instead of guess.

---

## Hoisted enrich-loop locals (small perf, mostly prep for v0.8.12)

Same technique as the v0.8.10 candidate-build loop: every per-item
`session.xxx`, `getattr(session, ...)` and `reorder_flow.xxx`
reference is now stashed in a local variable at the top of the
enrich loop.  Expected marginal win ~0.3-0.5 s; more importantly,
it makes the v0.8.12 memoization work easier because the call
sites are already isolated.

---

## What to do

1. **Drop v0.8.11 in place of v0.8.10.**
2. **Run a full session** — Load Files & Continue, walk through
   Line Codes / Customers, click Proceed, wait for the grid.
3. **Don't click anything else** — we only need the initial load
   path measurement.
4. **Send me `perf_trace.jsonl`** after the grid appears.

The next trace will have:

- A single top-level `po_builder._do_load` span → the full Load
  Files wall clock
- A single top-level `po_builder.proceed_to_assign` span → the
  full Crunching Numbers wall clock
- Sub-spans for every phase inside each
- Per-item breakdowns for the candidate-build and enrich loops
- `sheet.set_rows` tksheet cost for the first paint

That's enough detail to target v0.8.12 at the real hotspot instead
of guessing.  **The 33-second `prepare_assignment_session` number is
solid, but the remaining ~20 s of "Crunching numbers" wall-clock
has been invisible until now.**

---

## Files changed

- `po_builder.py` — wrapped `_do_load`, `_proceed_to_assign`, plus
  `compute_data_quality_summary`, `refresh_data_quality_card`,
  `populate_exclude_tab`, `refresh_vendor_inputs`,
  `restore_bulk_filter_sort_state`, `populate_bulk_tree`,
  `apply_load_result_and_warnings`
- `assignment_flow.py` — candidate-build and enrich loops each
  emit a per-stage `_breakdown` stamp; hoisted session attrs in
  the enrich loop
- `ui_bulk.py` — `populate_bulk_tree` is `@perf_trace.timed` plus
  emits substep stamps around sync_metadata, store_visible_rows,
  combobox_values, update_summary, and `sheet.set_rows`
- `app_version.py` — bumped to 0.8.11

---

## What's NOT in v0.8.11

- No actual perf fixes beyond the marginal enrich-loop hoisting.
- No new behavior changes.
- No new tests — the instrumentation is additive and
  non-behavioral.

This release exists **purely to see the 20+ seconds of invisible
time** the operator is feeling.  v0.8.12 will target it.
