# Release Notes — v0.8.4

**Date:** 2026-04-08

---

## Summary

v0.8.4 fixes the **v0.8.3 crash** the operator hit on the real 63K-
item session and ships **finer-grained perf spans** for the 35.6 s
`prepare_assignment_session` bottleneck the harness surfaced in the
same report.

1107 tests pass.

---

## The crash

The v0.8.2 perf harness captured the lead-up to the crash in
`perf_trace.jsonl`.  The last recorded event was an
`apply_bulk_filter` at `20:03:06.703`; no `notebook.tab_switch` to
Review ever appeared, and no `perf_trace.disabled` marker from a
clean shutdown — the process died between the button press and the
review tab being populated.

Root cause: `finish_bulk_final` built `assigned_items` via a list
comprehension that called `int(item.get("final_qty", ...))` and
`item["qty_sold"]` (hard access).  On the 63K-item session at least
one row had either a `None` `final_qty` or a missing `qty_sold`
after the mass Remove Not Needed + multiple edit cycles.  The crash
was a `TypeError` / `KeyError` inside the comprehension — which
takes down the whole flow because list comprehensions can't raise
partial results.

### Fix — defensive row build + per-row diagnostic

- New helpers `_coerce_int_safe(value, default=0)` and
  `_resolve_final_qty(item)` in `ui_bulk_dialogs.py`.
- The list comprehension is now a plain `for` loop with a `try`
  around each row.  A single bad row is logged via
  `debug_log.write_debug("finish_bulk_final.row_error", ...)`
  (including the offending line_code / item_code / raw final_qty
  shape) and the loop keeps going.  After the loop, if any row
  errored, a summary line lands in the debug trace so the count is
  visible to support.
- Every numeric field that used to rely on `int(item.get(...))`
  now goes through `_coerce_int_safe`.  Every `item["..."]` hard
  access becomes `item.get("...", "")`.
- `finish_bulk_final` is now wrapped in a `perf_trace.span` so
  future crashes show up in the trace with exactly when they
  started.

The fix is defensive: a single bad row never blocks the export, and
the root cause is now visible in `debug_trace.log` for the next
support cycle.

---

## Perf harness findings (from the operator's real 63K session)

`perf_trace.jsonl` captured on the operator's machine against the
live 63K / 8-year dataset:

```
event                                     duration
──────────────────────────────────────────────────
parsers.parse_detailed_pair_aggregates    15.4 s
load_flow.parse_all_files                 17.6 s
load_flow.apply_load_result              122 ms
assignment_flow.prepare_assignment_...    35.6 s   ← 2.1× the v0.8.2 estimate
reorder_flow.normalize_items_to_cycle     23.0 s   ← wasn't on the radar
ui_bulk.build_bulk_sheet_rows (first)      8.9 s   ← wasn't on the radar
ui_bulk.sync_bulk_session_metadata        315 ms
bulk_remove_flow.remove_filtered_rows      6.4 s   (removing 57,783 items)
```

Total pre-interaction cost: **~87 s** (parse + assign + normalize +
first paint).  `prepare_assignment_session` + `normalize_items_to_cycle`
+ `build_bulk_sheet_rows` is **68 seconds of enrich/recalc work** on
top of the 17.6 s parse — far worse than my v0.8.2 estimate.

### New finer-grained stamps in `prepare_assignment_session`

v0.8.4 adds four stage stamps so the next real session breaks the
35.6 s into its phases:

- `assignment_flow.stage | stage=begin`
- `assignment_flow.stage | stage=candidates_built | count=N`
- `assignment_flow.stage | stage=enriched | count=N`
- `assignment_flow.stage | stage=performance_annotated`
- `assignment_flow.stage | stage=release_annotated`

The delta between consecutive stamps is the per-stage duration.
v0.8.5 will use this to target whichever stage is actually eating
the 35 s (my suspects: the per-item enrich loop, performance_flow,
or shipping_flow).

---

## Test count

| Release | Tests |
|---------|-------|
| v0.8.3  |  1107 |
| v0.8.4  |  1107 |

The defensive rewrite is covered by the existing
`test_finish_bulk_final_*` suite in `tests/test_ui_bulk_dialogs.py`.
The stage stamps are `stamp()` calls that no-op when the harness
is disabled, so they don't need new tests.

---

## Files changed

- `ui_bulk_dialogs.py` — `_coerce_int_safe` / `_resolve_final_qty`
  helpers; `finish_bulk_final` defensive rewrite + per-row
  diagnostic logging; outer `perf_trace.span` wrapper
- `assignment_flow.py` — four stage stamps around the build /
  enrich / performance / release stages
- `app_version.py` — bumped to 0.8.4

---

## What the operator should do

Drop v0.8.4 in place of v0.8.3.  Keep the `perf_trace.enabled`
flag file in place.  Run a normal session, then send me the
`perf_trace.jsonl` + `perf_summary.txt` from next to the exe.  The
trace will show:

1. The stage stamps inside `prepare_assignment_session` — v0.8.5
   will target whichever stage is the actual 35-second culprit.
2. If any bad-row diagnostic landed in `debug_trace.log` — I want
   to know which upstream path is producing the None / missing
   fields so the *source* can be fixed in v0.8.5 too.
3. Most importantly: the button click should now complete without
   crashing even if a bad row exists, because the bad rows are
   logged and skipped instead of killing the whole build.

---

## Roadmap position

| Phase | Status |
|---|---|
| 2.0 — Perf harness | ✓ closed (v0.8.2) |
| **2.0a — crash hardening of finish_bulk_final** | **✓ closed (v0.8.4)** |
| **2.0b — fine-grained stamps in prepare_assignment_session** | **✓ closed (v0.8.4)** |
| 2.1 — Phase 1 perf wins | next (v0.8.5+), targeted by the new stage stamps |

The generation-counter row render cache and precomputed text
haystack wins from the audit are still queued behind the bigger
`prepare_assignment_session` target — there's no point optimizing
filter change (328 ms) when the operator sits through 35.6 s of
assignment setup on every session load.
