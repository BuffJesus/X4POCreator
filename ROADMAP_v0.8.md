# PO Builder Roadmap — v0.8.x

Status: In progress (v0.8.0 → v0.8.12 shipped)

Current app version: `0.8.13`

## Live confirmation (2026-04-08 22:10 operator run)

| Stage | v0.8.12 live | vs projection |
|---|---:|---|
| `parse_all_files` | 18.0 s | matches |
| `prepare_assignment_session` | **5.6 s** | **exact match — 6.2× win confirmed** |
| `populate_bulk_tree` | **1.5 s** | **better than projected** (was 8.9 s — index warm-up paid for itself) |
| `_do_load` total | 24.3 s | matches |
| **Pre-UI total** | **~32 s** | matches projection |

**The v0.8.12 fix landed exactly as measured.** The description-index
warm-up from `prepare_assignment_session` is also paying for
`build_bulk_sheet_rows` indirectly — first paint dropped 8.9 s → 1.0 s.

### New top targets surfaced by the live trace

1. **`parse_detailed_pair_aggregates` — 15.8 s** (88 % of parse).
   The fused-pass target listed in 2.1; promote to v0.8.13.
2. **`export_flow.do_export` — 8.4 s.** Not previously instrumented;
   needs a breakdown stamp pass before optimizing.
3. **`bulk_remove_flow.remove_filtered_rows` — 6.5 s.** Suspect deepcopy
   in the undo snapshot; matches the open item under 2.1.
4. **`finish_bulk` / `finish_bulk_final` — 3.9 s / 2.8 s.** Likely
   suspense carry + status reclassification on the full bulk set.

## Headline results so far

**Session load on the 63K-item / 8-year production dataset:
~85 s → ~32 s (2.7× faster)** across v0.8.9 → v0.8.12.

| Phase | v0.8.9 baseline | v0.8.12 |
|---|---:|---:|
| `parse_all_files` | 17.6 s | 17.1 s |
| `prepare_assignment_session` | **35.6 s** | **5.6 s** |
| `normalize_items_to_cycle` | 23.2 s | 0 s |
| `build_bulk_sheet_rows` first paint | 8.9 s | 8.9 s |
| **Pre-UI total** | **~85 s** | **~32 s** |

The big wins:
- **v0.8.10** eliminated the redundant `normalize_items_to_cycle` pass (−23 s)
- **v0.8.12** eliminated an O(n²) scan in `_description_for_key` (−29 s)

Both were found by the perf harness introduced in **v0.8.2** and its
instrumentation refinements through v0.8.11.  Without the harness
every fix would have been a guess; with it every fix landed with
measured before/after numbers.

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
- [x] Click column header to sort + ▲/▼ direction arrows in header text — v0.8.13
- [x] Ctrl+F focuses the bulk search box globally — v0.8.13
- [x] Ctrl+D fill-down selected column from the top cell (already implemented)
- [x] Double-click column header → auto-size to content — v0.8.13
- [x] Enter on selected row → open "View Item Details" — v0.8.13
- [ ] Shift+click header → secondary sort stack (optional)

### 1c. Per-item notes column (new, from operator feedback) — ✓ closed (v0.8.13)

- [x] `item_notes_flow.py` — pure helpers:
  `load_notes(path)`, `save_notes(path, notes)`,
  `apply_notes_to_items(items, notes)`,
  `clear_notes_for_keys(notes, keys)` — v0.8.13
- [x] New `notes` column on the bulk grid (editable), placed after `why` — v0.8.13
- [x] Persistence to `item_notes.json` keyed by `LC:IC`; loaded in
  `load_persistent_state` — v0.8.13
- [x] `export_vendor_po` picks up `item["notes"]` and writes a `Notes`
  column to the vendor xlsx — v0.8.13
- [ ] "Clear notes for selected rows" in the removal row toolbar
- [x] Tests for all four pure helpers — v0.8.13 (10 tests)

---

## Phase 2 — Performance instrumentation + measured fixes — ✓ **closed**

### 2.0 — Perf instrumentation harness (v0.8.2) — ✓ closed

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

### 2.1 — Measured perf wins — mostly ✓ closed

Shipped across v0.8.10 → v0.8.12, each informed by real harness
traces from the operator's 63K-item dataset.

- [x] **Generation-counter row render cache** (v0.8.10) — `ui_bulk`
  cache hits are now `int == int` compares instead of 20-field
  signature recomputes
- [x] **Memoized `_suggest_min_max`** per session with cycle-change
  invalidation (v0.8.10)
- [x] **Eliminate `normalize_items_to_cycle` redundant pass** (v0.8.10)
  — folded into `prepare_assignment_session`'s single loop; −23 s
- [x] **Memoized `_resolve_pack_size_with_source`** per session (v0.8.12)
- [x] **Memoized `suggest_min_max_with_source`** via session cache
  (v0.8.12)
- [x] **Short-circuit `receipt_pack_size_for_key`** when the key has
  no receipt history (v0.8.12)
- [x] **Lazy description index** — eliminated an **O(n²)** linear
  scan in `_description_for_key` that was dominating 29 seconds of
  prepare_assignment_session (v0.8.12) — **the biggest single perf
  win in the v0.8.x train**
- [x] **Lazy sales-history index** — same fix for
  `sales_history_for_key` (v0.8.12)
- [x] **`bulk_row_values` shared empty-dict sentinel** + hoisted locals
  in `build_bulk_sheet_rows` (v0.8.12)
- [x] **Hoisted locals in `prepare_assignment_session` candidate-build
  and enrich loops** (v0.8.10 / v0.8.12)
- [x] **`_finish_bulk_final` defensive row build** — bad rows are
  logged and skipped instead of crashing the whole pass (v0.8.4)
- [x] **`check_stock_warnings` short-circuit** when >50 flagged items
  (was building 12,000 Tk widgets) (v0.8.9)

**Still open (not yet worth the risk):**

- [ ] **Precomputed `_text_haystack`** per item — expected 83 ms → ~10 ms
  on text filter (small interactive win, no user complaint yet)
- [ ] **Fused warning-generation loop** in `parse_all_files` — expected
  ~80 ms saved (negligible on the 17 s parse)
- [ ] **Fused `parse_detailed_pair_aggregates` three-pass loop** into
  one — expected 2-4 s saved on parse
- [ ] **`build_bulk_sheet_rows` first-paint optimization** — still 8.9 s
  on 59K items; see the audit in v0.8.11 notes.  No O(n²) bug found,
  the cost is genuine per-row tuple construction.  Target for v0.8.13
  or a Cython `bulk_row_values` if push comes to shove.
- [x] **Per-row-id snapshot in bulk history capture** instead of
  `deepcopy` of full `filtered_items` — v0.8.13
- [ ] **`sheet.set_rows` on 59K rows** — measured 24 ms in v0.8.11, not a
  target

---

## Phase 3 — Structural refactor (behind golden tests)

From the audit: three "responsibility overload" modules, ordered by
payoff.

### 3.1 — Characterization tests (no code changes)

Lock current behavior down before touching a line.  All three are
Phase 3 prerequisites.

- [x] **`tests/test_enrich_golden.py`** — 20 golden fixtures covering
  exact_qty, standard, soft_pack, pack_trigger, manual_only,
  reel/large pack, dead stock, confirmed stocking, suspense,
  open PO offset, recency levels, overstock, receipt pack mismatch,
  min packs on hand.  Pins full post-enrich shape. — v0.8.13
- [ ] **`tests/test_parse_golden.py`** — loads the full 293 MB dataset,
  asserts top-line counts (sales_items, inventory_lookup, window dates,
  no_minmax_coverage_keys).  Marked `skipUnless` so CI skips and dev
  machine runs.
- [ ] **`tests/test_prepare_assignment_golden.py`** — 100-item subset,
  pins the post-pass filtered_items shape.

### 3.2 — `rules.py` split (R1 from the audit)

Biggest long-term payoff.  Splits the 380-line `enrich_item` monolith.

- [x] Extract `rules/calc.py` — `calculate_inventory_position`,
  `determine_target_stock`, `determine_reorder_trigger_threshold`,
  `evaluate_reorder_trigger`, `calculate_raw_need`,
  `determine_acceptable_overstock_qty`, `assess_post_receipt_overstock`,
  `calculate_suggested_qty`, `compute_stockout_risk_score` — v0.8.13
- [x] Extract `rules/status.py` — `evaluate_item_status` — v0.8.13
- [x] Extract `rules/explanation.py` — `build_reason_codes` and
  `build_detail_parts` extracted (~200 lines); `enrich_item` slimmed
  from ~380 to ~177 lines — v0.8.13
- [x] Extract `rules/policy.py` — `determine_order_policy`,
  `should_force_recency_review`, `should_suppress_manual_only_qty`,
  `classify_package_profile`, `classify_replenishment_unit_mode`,
  `classify_recency_confidence`, `classify_low_confidence_recency`,
  `classify_dead_stock`, pattern matchers, graduation logic — v0.8.13
- [x] Extract `rules/_constants.py` — all shared constants — v0.8.13
- [x] Extract `rules/_helpers.py` — rule field accessors (`get_rule_int`,
  `get_rule_float`, `has_exact_qty_override`, `apply_rule_fields`,
  `has_pack_trigger_fields`, `get_rule_pack_size`) — v0.8.13
- [ ] Slim `rules.enrich_item` orchestrator further (now ~177 lines,
  target ≤ 60; remaining bulk is policy escalation + history gap
  detection)

### 3.3 — `AppSessionState` sub-states (R2 from the audit) — partially shipped (v0.8.13)

- [x] New `models/session_bundle.py` with four dataclasses:
  `LoadedData`, `DerivedAnalysis`, `UserDecisions`, `SessionMetadata`
  — v0.8.13
- [x] Backwards-compat: `AppSessionState` uses `__getattr__`/`__setattr__`
  forwarding so existing code keeps working (`state.sales_items` →
  `state.loaded.sales_items`) — v0.8.13
- [ ] Migrate flows one at a time to take sub-states by name; start
  with `export_flow` (read-only)

### 3.4 — `parsers.py` split (R3 from the audit) — partially shipped (v0.8.13)

- [x] `parsers/dates.py` — `parse_x4_date` + memoization cache — v0.8.13
- [x] `parsers/normalize.py` — `_safe_cell`, `_coerce_int`,
  `_normalize_vendor_code`, `_normalize_header_label` — v0.8.13
- [x] `parsers/__init__.py` becomes re-export shim — v0.8.13
- [x] Fixed pre-existing HEADER_ALIASES bug: underscore forms
  (`qty_sold`, `sale_date`, `qty_received`, `receipt_date`) were
  missing from alias sets — v0.8.13
- [ ] `parsers/csv_io.py` — raw CSV iteration + layout detection
- [ ] `parsers/x4_dialect.py` — X4 row shape knowledge + row builders
- [ ] `parsers/aggregators.py` — `parse_detailed_pair_aggregates` etc.

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
