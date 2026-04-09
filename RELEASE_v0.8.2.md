# Release Notes — v0.8.2

**Date:** 2026-04-08

---

## Summary

v0.8.2 ships the **perf instrumentation harness** that was called out
as Phase 2.0 in `ROADMAP_v0.8.md`.  It's the foundation for every
subsequent perf fix in the v0.8.x train.  The harness paid for itself
on the very first run: it exposed a **10-second miscalculation** in the
pre-harness estimate for `assignment_flow.prepare_assignment_session`
(audit said ~6 s, reality on the 63K-item 8-year dataset is **16.8 s**).

Zero behavior change.  1106 tests pass (23 new).

---

## What's new — `perf_trace` module

A new `perf_trace.py` module exposes a low-overhead, opt-in timing
harness the app can enable on the operator's real machine.

### API

```python
perf_trace.enable(log_path, *, session_label, summary_path)
perf_trace.disable(write_summary=True)
perf_trace.is_enabled()

with perf_trace.span("event_name", **fields):    # time a block
    ...
perf_trace.stamp("event_name", **fields)           # record a moment
@perf_trace.timed("event_name")                     # decorator form
def func(...): ...
with perf_trace.aggregate_span("hot_loop_event"):  # for 60K+-call hot loops
    ...
perf_trace.flush_aggregate("hot_loop_event")

perf_trace.recorded_events()                       # ring buffer contents
perf_trace.summarize_events(events)                # pure aggregate builder
perf_trace.format_summary_report(events)           # pretty-print summary
perf_trace.write_summary_report(path)              # write summary to disk
perf_trace.maybe_auto_enable()                     # env-driven auto-enable
```

### Storage

- **JSONL file** (`perf_trace.jsonl`): one JSON object per span / stamp,
  grep/awk-friendly, appended across sessions.  Easy to send in a
  support bundle.
- **In-memory ring buffer** (cap 50K entries) so `write_summary` can
  aggregate without re-reading the file.
- **Aggregate summary** (`perf_summary.txt`): plain text, count /
  total / avg / min / max / p50 / p95 / p99 per event plus a
  "top 10 slowest individual events" table.
- Session start + stop markers written to the JSONL so multi-session
  files are easy to separate.

### Overhead

- `time.perf_counter()` ≈ 50 ns on Windows
- One JSONL append per span ≈ 10-50 µs (dominant cost)
- Ring buffer append ≈ 100 ns
- **`aggregate_span` for hot loops** avoids the per-call JSONL write
  entirely — only the flushed summary row lands in the log

### Enable / disable

- **Dev mode:** set `DEBUG_PERF=1` in the environment OR drop a
  `perf_trace.enabled` file next to the executable/script.
  `POBuilderApp.__init__` calls `maybe_auto_enable()` at startup.
- **Packaged exe:** new `_toggle_perf_trace` method on `POBuilderApp`
  (ready to wire into the Help menu in a follow-up — the method itself
  is in place).
- **Clean shutdown:** `atexit` hook flushes aggregate counters and
  writes the summary file automatically.

---

## Instrumentation points wired in this release

Every hot path the audit flagged now has a span or decorator:

**Parse / load:**
- `parsers.parse_detailed_pair_aggregates` (the dominant parse cost)
- `load_flow.parse_all_files` (whole orchestration)
- `load_flow.apply_load_result`

**Assignment / reorder:**
- `assignment_flow.prepare_assignment_session`
- `reorder_flow.refresh_suggestions`
- `reorder_flow.normalize_items_to_cycle`
- `reorder_flow.refresh_recent_orders`

**Bulk grid:**
- `ui_bulk.apply_bulk_filter` (wrapped with `items_total` field)
- `ui_bulk.sync_bulk_session_metadata`
- `ui_bulk.build_bulk_sheet_rows`
- `bulk_remove_flow.remove_filtered_rows` (wrapped with `history_label`
  and `requested` fields)

**Export:**
- `export_flow.do_export`

**UI navigation:**
- `notebook.tab_switch` stamp from a new
  `POBuilderApp._on_notebook_tab_changed` handler bound to
  `<<NotebookTabChanged>>`.  Records old → new tab transitions.

Every span is silent (no-op, sub-nanosecond) when the harness is
disabled, so the overhead in the default packaged exe is zero.

---

## First real-world measurements (validation run)

Ran the harness against the 63K-item / 8-year `CSVs/` dataset during
v0.8.2 development.  Results:

```
event                                             count   total_ms
─────────────────────────────────────────────────────────────────────
load_flow.parse_all_files                             1   16,921
assignment_flow.prepare_assignment_session            1   16,838
parsers.parse_detailed_pair_aggregates                1   15,040
ui_bulk.sync_bulk_session_metadata                    1      228
load_flow.apply_load_result                           1      128
```

**Headline finding:** `prepare_assignment_session` is **16.8 s** on
63K items, not the ~6 s the audit estimated.  The per-item enrich_item
loop is running at ~260 µs/item at that scale instead of the ~95 µs I
measured earlier on 8K items.  **Per-item cost is scaling worse than
linear**, which suggests an O(n log n) or O(n²) in one of the
downstream helpers (probably the lookup derivation inside
`apply_suggestion_gap_review_state` or `performance_flow.annotate_items`).

This is **exactly** what the harness was built for.  Without it the
audit estimate would have led v0.8.3 to optimize the wrong thing.
The next release will chase this down with finer-grained spans around
each stage of `prepare_assignment_session`.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.8.1  |  1083 |
| v0.8.2  |  1106 |

23 new tests in `tests/test_perf_trace.py`:

- **`PerfTraceLifecycleTests`** — enable/disable state, span records
  duration, stamp records event, JSONL file appends one row per event,
  disable writes summary report
- **`SummarizeEventsTests`** — empty input, single-span percentiles,
  grouping by event, sort order, aggregate rolling, p95 picks near
  top, malformed row filtering
- **`TopSlowestTests`** — sort by duration descending, skip non-span
- **`AggregateSpanTests`** — no per-call rows, flush emits single
  summary row, flush is idempotent
- **`FormatSummaryReportTests`** — summary contains headline sections
- **`TimedDecoratorTests`** — decorator records a span
- **`MaybeAutoEnableTests`** — respects `DEBUG_PERF=1`, no-op when unset

---

## Files changed

- `perf_trace.py` (new, ~330 lines) — harness
- `tests/test_perf_trace.py` (new, ~250 lines) — 23 regression tests
- `parsers.py` — `parse_detailed_pair_aggregates` decorator
- `load_flow.py` — `parse_all_files`, `apply_load_result` decorators
- `assignment_flow.py` — `prepare_assignment_session` decorator
- `reorder_flow.py` — `refresh_suggestions`, `normalize_items_to_cycle`,
  `refresh_recent_orders` decorators
- `ui_bulk.py` — `apply_bulk_filter` span, `sync_bulk_session_metadata`
  and `build_bulk_sheet_rows` decorators
- `bulk_remove_flow.py` — `remove_filtered_rows` span wrapper
- `export_flow.py` — `do_export` decorator
- `po_builder.py` — `maybe_auto_enable` call in `__init__`, tab-change
  handler `_on_notebook_tab_changed`, `_toggle_perf_trace` method for
  menu wiring
- `ROADMAP_v0.8.md` (new) — full v0.8.x plan from the audit
- `app_version.py` — bumped to 0.8.2

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| 1a — Help tab rebuild | ✓ closed (v0.8.0) |
| 1b — Sheet muscle memory | partial (Delete key + themed menu in v0.8.1) |
| 1c — Per-item notes column | open |
| **2.0 — Perf instrumentation harness** | **✓ closed (v0.8.2)** |
| 2.1 — Phase 1 perf wins | open — **informed by v0.8.2 real measurements** |
| 3.x — Structural refactors | open (characterization tests first) |
| 4 — Optional native acceleration | do not proceed (audit verdict) |

---

## What's next

v0.8.3 will dig into `prepare_assignment_session`'s 16.8 s surprise.
The harness is already wired to pick up finer-grained spans — the
next release will add spans around each stage of the per-item loop
(enrich_item aggregate, suggestion_gap annotation, performance
annotation, history lookup merges) and produce a second summary
showing which stage is the actual super-linear culprit.

The generation-counter row render cache and precomputed text haystack
wins from the audit are still queued, but the new measurement makes
it clear the biggest single win is in `prepare_assignment_session`, not
in the bulk grid layer.  **The harness just saved us from optimizing
the wrong thing.**

---

## How to enable the trace on your own machine

Easiest: drop an empty file named `perf_trace.enabled` next to
`POBuilder.exe`.  On next launch the harness records everything and
writes `perf_trace.jsonl` + `perf_summary.txt` next to the exe when
the app closes cleanly.  Email me the `perf_summary.txt` after a
typical session and I can point at the real hotspots for v0.8.3.
