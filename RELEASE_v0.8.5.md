# Release Notes — v0.8.5

**Date:** 2026-04-08

---

## Summary

Two concrete fixes driven by the operator's latest bug report
("crash during parsing, delete key still broken"):

1. **Perf harness writes a `span_start` breadcrumb on entry** — not
   just on exit.  The last operator session crashed inside the parse
   and left **zero** spans in the trace because the old harness only
   wrote on successful completion.  v0.8.5 makes mid-function crashes
   visible.
2. **Delete key now binds at the Tk root level** via `bind_all`,
   routing every Delete keystroke through a global handler that
   logs the event and dispatches to the existing
   `_bulk_delete_selected` flow only when the bulk grid has focus.
   Previous attempts bound on tksheet's internal widgets, which the
   operator reported as unreliable since day one — tksheet's own
   bindings eat the event before ours can fire.

1109 tests pass (2 new).

---

## The invisible-crash problem

The operator sent a `perf_trace.jsonl` with exactly **two events**:

```json
{"event":"perf_trace.enabled", ...}
{"event":"notebook.tab_switch","old":"","new":"1. Load Files", ...}
```

Then nothing.  Process died mid-parse.  No `parsers.parse_all_files`
span, no `parse_detailed_pair_aggregates` span.

**Why?** The old `perf_trace.span` used a `try / finally` that only
wrote the row on exit.  The duration_ms is computed when the block
completes — so mid-block crashes never hit the finally's write.  The
harness was blind to the exact scenario it was built to diagnose.

### Fix

`span` now emits **two** events:

- **On entry:** `{"kind": "span_start", "event": ..., "ts": ..., fields}`
  — written and `fsync`'d immediately so even a hard process crash
  leaves it on disk.
- **On exit:** the existing `{"kind": "span", ..., "duration_ms": N}`
  row, unchanged.

`summarize_events` and `top_slowest` skip `span_start` rows so the
summary report stays clean — they're breadcrumbs, not duration
records.

Plus a new `fsync` call on every JSONL write guarantees the row is
on disk before the next line runs, so OS buffering can't hide the
last event before a crash.

### Two new regression tests

- `test_span_start_written_before_exception_inside_block` — raises
  inside a `with perf_trace.span(...)` and asserts both the
  start row AND the completion row land in the JSONL (the span's
  `try/finally` handles exceptions gracefully).
- `test_span_start_allows_crash_diagnosis_without_completion_row` —
  manually writes a lone `span_start` row and asserts
  `summarize_events` ignores it, so the summary aggregator can't
  be fooled into counting an orphaned crash breadcrumb.

---

## Delete key — root-level binding via `bind_all`

The operator reported Delete has been broken **since the beginning**
of the application.  v0.8.1 tried to fix it by disabling tksheet's
internal `"delete"` binding and binding our handler on the Sheet
composite + its MainTable / RowIndex / ColumnHeader children.  That
approach is fragile because:

1. tksheet's binding names vary across versions; `disable_bindings("delete")`
   may not exist or may not catch every surface.
2. tksheet uses `bind_class` at load time, so `add="+"` on the Sheet
   widget fires *after* tksheet's internal handler — which may have
   already consumed the event with a `return "break"`.
3. Sheet internals can be rebuilt on `set_rows`, invalidating the
   binding.

### Fix

New `POBuilderApp._global_delete_key_handler` bound via
`self.root.bind_all("<Delete>", ..., add="+")` at app startup.  This
fires on **every** Delete keystroke in the entire Tk process,
regardless of which widget has focus or what internal tksheet
binding exists.  The handler:

1. **Always logs** the keystroke to `debug_trace.log` via
   `write_debug("po_builder.delete_key.fired", focus=..., active_tab=...)`
   so the operator and I can verify events are actually being
   received.  Previous attempts failed silently; now we get
   ground truth.
2. **Only acts** when the operator is on the "Assign Vendors" tab
   (via the tab-switch stamp bookkeeping already added in v0.8.2).
3. **Skips Entry / Text / Combobox / Spinbox** focus — so Delete
   inside the search box or an inline cell editor still deletes a
   character instead of a row.
4. **Routes to `_bulk_delete_selected`** which already handles
   multi-row (including non-contiguous ctrl-click) selection via the
   existing code path.
5. **Returns `"break"`** on successful handling so tksheet's own
   Delete handling doesn't also fire.
6. **Logs every outcome** (`handled`, `skip_editor`, `error`) so
   future failures are diagnosable without a repro video.

This is bulletproof against tksheet internals because `bind_all`
operates at the Tk event-dispatch level, which runs before any
widget-specific binding.

---

## What v0.8.5 does NOT fix

- **The parse crash itself is not yet diagnosed.** v0.8.5 ships the
  instrumentation that will let the next operator run **show** where
  the crash is.  With `span_start` breadcrumbs and `fsync` writes,
  the next `perf_trace.jsonl` will have a last-event row pointing
  directly at the function the process died in.
- **The 35.6 s `prepare_assignment_session` perf target** is still
  the real next work item.  The stage stamps from v0.8.4 will pay
  off as soon as the operator can complete a load without crashing
  again.

---

## What the operator should do

1. **Drop v0.8.5 in place of v0.8.4.**  Keep the `perf_trace.enabled`
   file next to the exe.
2. **Try the Delete key on the bulk grid.**  Select rows (single or
   ctrl-click), press Delete.  Every keystroke lands in
   `debug_trace.log` as `po_builder.delete_key.fired` regardless of
   whether it worked — so even if it still fails, we'll have
   concrete evidence of where it's being intercepted.
3. **Run a normal parse.**  The crash that hit v0.8.4 should now
   leave breadcrumbs in `perf_trace.jsonl` — specifically, the last
   event should be a `span_start` row pointing at the exact function
   where the process died.
4. **Send me the files** (`perf_trace.jsonl`, `debug_trace.log`,
   `perf_summary.txt` if it exists).

If the parse still crashes, v0.8.5's breadcrumbs will tell me
exactly which function to focus on — for the first time in this
session I'll have ground-truth data on where it dies instead of
guessing.

---

## Files changed

- `perf_trace.py` — `span` emits `span_start` on entry; `_write_jsonl`
  adds `flush + fsync`; `summarize_events` ignores `span_start`
- `po_builder.py` — `bind_all` for `<Delete>` / `<KP_Delete>`; new
  `_global_delete_key_handler` with full debug trace logging
- `tests/test_perf_trace.py` — updated JSONL append test for the
  new breadcrumb row; two new `CrashDiagnosisBreadcrumbTests`
- `app_version.py` — bumped to 0.8.5

---

## Roadmap position

| Phase | Status |
|---|---|
| 2.0 — Perf harness | ✓ closed (v0.8.2) |
| 2.0a — Crash hardening of finish_bulk_final | ✓ closed (v0.8.4) |
| 2.0b — Stage stamps in prepare_assignment_session | ✓ closed (v0.8.4) |
| **2.0c — Harness span_start breadcrumbs** | **✓ closed (v0.8.5)** |
| **2.0d — Delete key at Tk root level** | **✓ closed (v0.8.5)** |
| 2.1 — Phase 1 perf wins | pending the next clean operator session |
