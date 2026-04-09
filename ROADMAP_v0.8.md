# PO Builder Roadmap — v0.8.x

Status: In progress (v0.8.0 and v0.8.1 shipped)

Current app version: `0.8.1`

---

## What v0.8.x is about

v0.7.x added Session Diff, Vendor Review, Skip Cleanup, and a 2.6× parse
speedup on the 8-year dataset (47 s → 18 s via `parse_x4_date` memoization
and `_detail_row_signature` simplification).  v0.8.x is the **UX
modernization + performance + structural cleanup train**, informed by a
full architecture audit against the real 63K-item dataset.

Three parallel themes:

1. **UX modernization** — Help tab search, themed context menu, Delete
   key on sheet, click-header-to-sort, per-item notes, and the muscle-
   memory polish operators have been asking for.
2. **Performance** — measured fixes to the hot paths surfaced by the
   audit (cached row render, bucket rebuild, text filter, fused
   parse passes).  All pure-Python, no native code.
3. **Structural refactor** — split the three big "responsibility
   overload" modules (`rules.py`, `parsers.py`, the god-state
   `AppSessionState`) behind golden tests, without changing behavior.

The perf and structural phases are informed by the audit document at
the end of this file.

---

## Phase 1 — UX modernization (partially shipped)

### 1a. Help tab rebuild — ✓ closed (v0.8.0)

- [x] Live search box with cross-page highlights and count badge
- [x] Tagged body rendering (heading1/heading2/bullet/inline-code)
- [x] `focus_help_section(app, title)` + `open_help_for(app, key)` API
- [x] `CONTEXTUAL_HELP_MAP` with 18 stable keys
- [x] `build_context_help_button` factory for tiny "?" buttons
- [x] Dark-themed help body to match the rest of the app
- [x] 13 new regression tests

### 1b. Sheet muscle memory polish (v0.8.1–v0.8.4)

- [x] Delete key removes multi-row (including non-contiguous ctrl-click)
  selections — v0.8.1
- [x] Dark-themed right-click context menu — v0.8.1
- [ ] Click column header to sort + ▲/▼ direction arrows in header text
- [ ] Ctrl+F focuses the bulk search box globally
- [ ] Ctrl+D fill-down selected column from the top cell
- [ ] Double-click column header → auto-size to content
- [ ] Enter on selected row → open "View Item Details"
- [ ] Shift+click header → secondary sort stack (optional)

### 1c. Per-item notes column (new, from operator feedback)

- [ ] `item_notes_flow.py` — pure helpers:
  `load_notes(path)`, `save_notes(path, notes)`,
  `apply_notes_to_items(items, notes)`,
  `clear_notes_for_keys(notes, keys)`
- [ ] New `notes` column on the bulk grid (editable), placed after `why`
- [ ] Persistence to `item_notes.json` keyed by `LC:IC`; loaded in
  `apply_load_result` next to `order_rules`
- [ ] `export_flow` picks up `item["notes"]` and writes a `Notes` column
  to the vendor xlsx
- [ ] "Clear notes for selected rows" in the removal row toolbar
- [ ] Tests for all four pure helpers + one xlsx export round-trip

---

## Phase 2 — Performance instrumentation + measured fixes

### 2.0 — Perf instrumentation harness (v0.8.2) — ships first

Every perf claim below is either measured from a dev-box profile script
or estimated.  The harness turns those into "here's the exact ms
breakdown from the operator's real session."  **This is the foundation
for every subsequent perf decision** — without it, we're guessing about
the live app from outside it.

- [ ] New `perf_trace.py` module with:
  - `enable(log_path, *, session_label)` / `disable()` / `is_enabled()`
  - `span(event, **fields)` context manager
  - `stamp(event, **fields)` instantaneous event
  - `timed(event)` decorator
  - `write_summary(path=None)` aggregate report generator
  - JSONL output (one structured row per span/event)
  - In-memory ring buffer capped at 50K entries
  - Thread-safe via a simple lock; the harness runs on the Tk main
    thread today but locking keeps it safe if flows ever move off
- [ ] Instrumentation points:
  - **Parse:** `parsers.parse_all_files`, each individual parse function,
    `apply_load_result`, `prepare_assignment_session`,
    `normalize_items_to_cycle`
  - **Enrich (aggregate):** `rules.enrich_item`,
    `item_workflow.apply_suggestion_gap_review_state`,
    `performance_flow.annotate_items` — single counter + timer per
    session, not per-call, to avoid flooding
  - **Bulk grid:** `apply_bulk_filter`, `sync_bulk_session_metadata`,
    `build_bulk_sheet_rows`, `bulk_row_values`/`cached_bulk_row_values`
    hit counter, `bulk_remove_flow.remove_filtered_rows`,
    `refresh_bulk_view_after_edit`, `bulk_apply_editor_value`
  - **Reorder:** `refresh_suggestions`, `refresh_recent_orders`,
    `refresh_active_data_state`
  - **UI navigation:** notebook tab switch, dialog open/close
  - **Export:** `do_export`, per-vendor xlsx write, session snapshot
- [ ] Enable mechanism:
  - Dev mode: auto-enable when `DEBUG_PERF=1` env var OR
    `perf_trace.enabled` file exists in data folder
  - Packaged exe: **Help → Enable Performance Trace** menu entry with
    toast confirmation
  - `atexit` hook writes the aggregate summary on clean shutdown
- [ ] Aggregate summary format with count / total / avg / min / max /
  p50 / p95 / p99 per event + top-10 slowest individual events
- [ ] `tests/test_perf_trace.py` — span/stamp unit tests, aggregate math
  tests, enable/disable smoke test, summary format golden

**Ships as v0.8.2.**  Zero behavior change.  Every subsequent perf fix
lands with before/after numbers from the operator's real session.

### 2.1 — Phase 1 perf wins (informed by the harness)

Land as v0.8.3, v0.8.4 etc., one focused release per fix, each measured
against the harness output from the previous release.

- [ ] **Generation-counter row render cache** (`ui_bulk`) — expected
  328 ms → ~20 ms on filter change
- [ ] **Precomputed `_text_haystack`** per item — expected 83 ms → ~10 ms
  on text filter
- [ ] **Fused warning-generation loop** in `parse_all_files` — expected
  ~80 ms saved
- [ ] **String-intern hot path values** in `_parse_x4_detailed_part_sales_row`
- [ ] **Preallocated bucket dicts** in `sync_bulk_session_metadata`
- [ ] **No-op filter guard** — skip metadata rebuild when nothing
  affecting it changed
- [ ] **Memoized `_suggest_min_max`** per session with edit-driven
  invalidation
- [ ] **Per-row-id snapshot in bulk history capture** instead of
  `deepcopy` of full `filtered_items`
- [ ] **Lazy `receipt_history_lookup` finalization**
- [ ] **Fast-path `classify_package_profile`**
- [ ] **Parse cache generation bump on app version change** (already
  done in v0.6.7; verify render cache has the same discipline)
- [ ] **Drop redundant `annotate_release_decisions` sweep** on
  cycle-only changes

---

## Phase 3 — Structural refactor (behind golden tests)

From the audit: three "responsibility overload" modules, ordered by
payoff.

### 3.1 — Characterization tests (no code changes)

Lock current behavior down before touching a line.  All three are
Phase 3 prerequisites.

- [ ] **`tests/test_enrich_golden.py`** — 50-item fixture captured from
  the real `CSVs/` dataset, one per interesting status / performance /
  attention / data-flag combination.  Each fixture asserts the full
  post-enrich shape (`status`, `final_qty`, `suggested_qty`,
  `order_policy`, `raw_need`, `data_flags`, `reason_codes`, `why`,
  `projected_overstock_qty`, `overstock_within_tolerance`,
  `recency_confidence`, `heuristic_confidence`, `confirmed_stocking`).
- [ ] **`tests/test_parse_golden.py`** — loads the full 293 MB dataset,
  asserts top-line counts (sales_items, inventory_lookup, window dates,
  no_minmax_coverage_keys).  Marked `skipUnless` so CI skips and dev
  machine runs.
- [ ] **`tests/test_prepare_assignment_golden.py`** — 100-item subset,
  pins the post-pass filtered_items shape.

### 3.2 — `rules.py` split (R1 from the audit)

Biggest long-term payoff.  Splits the 380-line `enrich_item` monolith.

- [ ] Extract `rules/calc.py` with `compute_calc_inputs(item, inv, rule)`
  and `run_calc_kernel(inputs) → CalcResult` (pure, no mutation,
  returns a dataclass)
- [ ] Extract `rules/explanation.py` with `build_why(item, calc_result,
  rule) → str` — currently interleaved with calculation
- [ ] Extract `rules/policy.py` with the escalation ladder and
  `should_force_recency_review`
- [ ] Extract `rules/status.py` with `evaluate_item_status` (already
  small; move for consistency)
- [ ] `rules.enrich_item` becomes a thin orchestrator calling the four
  extracted kernels in order, preserving the current signature exactly
- [ ] New implementation runs behind a feature flag alongside the old
  one for one release; characterization tests compare both on every
  fixture; flag flips to new-only once green

### 3.3 — `AppSessionState` sub-states (R2 from the audit)

- [ ] New `models/session_bundle.py` with four dataclasses:
  - `LoadedData` — raw parse output, immutable after load
  - `DerivedAnalysis` — computed lookups (inventory_lookup,
    receipt_history_lookup, detailed_sales_stats_lookup),
    invalidated on edits
  - `UserDecisions` — vendor assignments, QOH adjustments, order
    rules, ignore keys, supplier map
  - `SessionMetadata` — session history, vendor_codes_used,
    recent_orders, snapshot info
- [ ] Backwards-compat: `AppSessionState` gains forwarding properties
  so existing code keeps working (`state.sales_items` →
  `state.loaded.sales_items`)
- [ ] Migrate flows one at a time to take sub-states by name; start
  with `export_flow` (read-only)

### 3.4 — `parsers.py` split (R3 from the audit)

Last structural refactor.  Wait until 3.2 and 3.3 are stable.

- [ ] `parsing/csv_io.py` — raw CSV iteration + layout detection
- [ ] `parsing/x4_dialect.py` — X4 row shape knowledge + `_looks_like_*`
  predicates + row builders
- [ ] `parsing/generic_dialect.py` — non-X4 row builders
- [ ] `parsing/aggregators.py` — `parse_detailed_pair_aggregates`,
  `build_receipt_history_lookup`, `build_detailed_sales_stats_lookup`
  (ideally fused into one pass)
- [ ] `parsing/dates.py` — `parse_x4_date` + cache (already done, just
  relocates)
- [ ] `parsing/normalize.py` — `_safe_cell`, `_coerce_int`,
  `_normalize_code`
- [ ] `parsers.py` becomes a thin re-export shim

### 3.5 — `po_builder.POBuilderApp` slim down (R4 from the audit)

Last of the structural items.  Natural outcome of 3.2 + 3.3.

- [ ] Extract `app/bootstrap.py` with theme setup
- [ ] Extract `app/settings.py` with settings load/save (already
  partially split)
- [ ] `SessionController` (non-tk) owns the state bundle and the
  `_recalculate_item` / `_suggest_min_max` methods flows call on `app`
- [ ] `POBuilderApp` becomes the Tk root + view controller with a
  `SessionController` reference

---

## Phase 4 — Optional native acceleration

**Don't do this yet.**  After Phase 1-3 land and operator has a month of
field time on the instrumented build, revisit.

- [ ] Re-profile against the `perf_trace.jsonl` output from a real
  session
- [ ] Only if a single kernel shows >30% of session load time AND has
  been structurally stable for 2+ months AND has a narrow numeric-in /
  numeric-out contract: evaluate Cython compile of that kernel
- [ ] nanobind over pybind11 if a C++ extension is ever built —
  smaller binaries, faster compile, better Python 3.14 support
- [ ] Build toolchain cost is real on Windows; don't commit until
  measurements demand it

**Current expected outcome: no C++ needed.**  The audit identified zero
candidates that survive the "Python cleanup first" bar.

---

## Phase 5 — Long-term maintainability

- [ ] Typed row schemas (`TypedDict`) for bulk grid items, sales items,
  inventory entries — catches field-name typos at import time
- [ ] Move `not_needed_reason` out of `ui_bulk_dialogs` into
  `rules/not_needed.py` — it duplicates logic already in `rules.py`
- [ ] Single generation-keyed cache object replacing the three
  independent caches (`_bulk_row_index_cache` /
  `_bulk_filter_result_cache` / `_bulk_visible_rows_cache`)
- [ ] Consider collapsing `filtered_items` / `assigned_items` /
  `individual_items` into `items_by_status` for simpler undo

---

## Audit context (reference for future sessions)

Full architecture + performance audit lives in the chat history for the
session that produced this roadmap.  Key findings:

- **Post-v0.7.7 hotspots** (measured on 59K-item dataset):
  - `cached_bulk_row_values` second pass: 328 ms → fixable with
    generation counter
  - `sync_bulk_session_metadata`: 309 ms → fixable with incremental
    updates
  - `rules.enrich_item` aggregate: ~6 s per session load → fixable with
    the 3.2 refactor + hoisted attribute reads
- **Responsibility overloads** (ordered by payoff): `rules.enrich_item`
  > `AppSessionState` > `parsers.py` > `po_builder.POBuilderApp`
- **C++ skepticism**: there is no kernel today that is *all four of*
  dense, stable, narrow, and frequent enough to justify the maintenance
  cost of a cross-language boundary.  12+ Python-level wins are
  cheaper, safer, and easier to validate.

---

## Definition of "Done Enough" for v0.8.x

- Perf harness enabled on the operator's real dataset produces a
  summary showing every measured operation under 200 ms.
- Every sheet muscle-memory gesture from Excel works: click-to-sort,
  Ctrl+F, Ctrl+D, Delete-selected.
- `rules.py` is split into at least calc / explanation / policy, with
  the enrich_item orchestrator ≤ 60 lines.
- `AppSessionState` has sub-states available (backwards compat
  preserved); at least `export_flow` migrated off the god-object.
- `parsers.py` is either split into `parsing/` or a concrete plan
  exists.
- Zero behavior regressions — characterization tests protecting every
  refactor in 3.x.
