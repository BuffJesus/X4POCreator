# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

**PO Builder** is a Windows desktop application (**v0.10.0**, built on PySide6) that converts X4 ERP report exports (CSV) into vendor-specific purchase order Excel files. It merges sales, receipts, inventory, open PO, and suspended-item reports, calculates order quantities, and lets the user assign vendors before exporting per-vendor `.xlsx` files in X4 import format.

The operator runs it weekly against a large production dataset (~63K candidate items, 8 years of history, ~293 MB Detailed Part Sales CSV). **Session load perf on that dataset is a first-class concern** — see the Performance Notes section below.

## Commands

**Run from source:**
```bash
python -m pip install -r requirements.txt
python po_builder.py
```

**Run tests:**
```bash
python -m unittest discover -s tests -q
```
As of v0.10.0: **873 tests**.

**Run a single test file:**
```bash
python -m unittest tests.test_rules -v
```

**Build the executable:**
```bash
build.bat          # Release: dist\POBuilder.exe
build.bat debug    # Debug build with console window visible
```
Build installs dependencies, runs the full test suite (must pass), then bundles via PyInstaller (`PO_Builder.spec`).

## Architecture

### Module Layers

**1. Core Logic** — pure business rules, no UI dependencies:
- `rules/` package (7 modules):
  - `__init__.py` — `enrich_item` orchestrator
  - `calc.py` — inventory position, target stock, raw need, suggested qty, overstock
  - `policy.py` — order policy determination, recency, dead stock, package classification
  - `explanation.py` — `build_reason_codes`, `build_detail_parts`
  - `status.py` — `evaluate_item_status`
  - `not_needed.py` — `not_needed_reason`
  - `_constants.py`, `_helpers.py` — shared constants and rule accessors
- `parsers/` package (5 modules):
  - `csv_io.py` — header matching, layout detection, row iterators, dedup
  - `x4_dialect.py` — X4 row checkers/builders, line code splitting
  - `aggregators.py` — pair aggregates, receipt history, sales stats
  - `dates.py` — `parse_x4_date` + memoization cache
  - `normalize.py` — `_safe_cell`, `_coerce_int`, header normalization
- `models/` package:
  - `__init__.py` — `ItemKey`, `AppSessionState` (with sub-state forwarding), `SessionSnapshot`
  - `session_bundle.py` — `LoadedData`, `DerivedAnalysis`, `UserDecisions`, `SessionMetadata`
  - `schemas.py` — TypedDict definitions for `BulkItem`, `InventoryEntry`, etc.
- `reorder_flow.py` — reorder trigger evaluation, cached description/sales indexes, `suggest_min_max`
- `storage.py` — atomic JSON/text file I/O, lock handling, shared-folder merge logic
- `perf_trace.py` — opt-in timing harness (see Performance Notes)
- `auto_assign_flow.py` — auto-assign vendors from receipt history
- `item_notes_flow.py` — per-item notes persistence

**2. Flow Modules** — discrete, testable workflow controllers (no direct UI):
- `load_flow.py` — CSV loading, pickle-based parse caching (invalidated by file signature + schema version), line-code resolution, data-quality warnings
- `assignment_flow.py` — vendor/qty assignment, candidate building, per-item enrich orchestration
- `shipping_flow.py` — vendor release/hold policies
- `export_flow.py` — export grouping, vendor scoping, per-vendor xlsx writing, session snapshot
- `session_diff_flow.py` — session-over-session comparison (new items, qty changes, vendor changes)
- `supplier_map_flow.py` — supplier → vendor auto-mapping
- `qoh_review_flow.py` — QOH adjustment review + revert
- `skip_actions_flow.py` — bulk skip cleanup (ignore / flag discontinue / export CSV)
- `vendor_summary_flow.py` — per-vendor activity summaries
- `persistent_state_flow.py` — load/save `order_rules.json`, `vendor_codes.txt`, etc.
- `draft_report_flow.py` — per-vendor print-formatted xlsx export for physical verification

**3. UI Package** — `ui_qt/` (PySide6):
- `shell.py` — main window: sidebar nav, stacked pages, tab lifecycle, workflow dialogs
- `bulk_tab.py` — primary bulk assignment surface with toolbar, filters, grid
- `bulk_model.py` — `BulkTableModel` + `BulkFilterProxyModel` (6-axis filtering)
- `bulk_delegate.py` — row tinting, combo/spinbox editors
- `load_tab.py` — file picker, folder scan, QThread parse worker
- `review_tab.py` — exception review + export guided finish-line layout
- `filter_tab.py` — line code / customer exclusion checkboxes
- `help_tab.py` — markdown→HTML help sections
- `session_controller.py` — non-UI controller running full load→assign→enrich→auto-assign pipeline
- `workflow_dialogs.py` — 12 workflow modals (remove not needed, stock warnings, vendor review, etc.)
- `dialogs.py` — item details + buy rule editor modals
- `export_dialogs.py` — export finish dialogs
- `command_palette.py` — Ctrl+K search/action palette
- `undo_stack.py` — snapshot-based undo/redo for edits
- `shortcut_overlay.py` — press-? keyboard shortcut reference overlay
- `assignment_worker.py` — QThread worker for enrich pipeline

**4. Shared Data Modules** (UI-agnostic, used by Qt UI):
- `theme.py` — framework-independent design tokens (5 bg × 5 text × 5 accent palette)
- `theme_qt.py` — Qt stylesheet helpers consuming `theme.py` tokens
- `ui_help_data.py` — help section content (used by `ui_qt/help_tab.py`)
- `ui_load_data.py` — load file section data (used by `ui_qt/load_tab.py`)
- `command_palette_data.py` — command palette indexing and ranking functions
- `shortcut_data.py` — keyboard shortcut group definitions

**5. Entry Point:**
- `po_builder.py` — creates `QApplication`, applies global stylesheet, instantiates `ui_qt.shell.POBuilderShell`, runs event loop

### Session Lifecycle (Data Flow)

```
Load CSVs → Parse & cache → Build AppSessionState → Apply rules → Filter by line code/customer
→ Bulk/Individual assignment → Review exceptions → Export per-vendor .xlsx → Save session snapshot
```

### Key Data Structures (`models/`)

- `ItemKey`: `(line_code, item_code)` tuple — primary key throughout
- `AppSessionState`: central mutable state with four sub-state dataclasses (`LoadedData`, `DerivedAnalysis`, `UserDecisions`, `SessionMetadata`). Forwarding properties provide backward compat: `state.sales_items` → `state.loaded.sales_items`.
- `SessionSnapshot`: written to `sessions/` on export — full audit record
- `BulkItem`, `InventoryEntry`, `ExportItem` (TypedDict in `schemas.py`) — field documentation for editor autocompletion

### Persistence

- **Local**: JSON/text files next to the executable (or script directory)
- **Shared**: Optional network/OneDrive folder configured in `po_builder_settings.json` → `shared_data_dir`
- Shared-folder writes use atomic rename + lock files + merge logic for concurrency
- Parse results cached as `parse_result_cache.pkl`, invalidated when source file signatures change OR when `PARSE_CACHE_SCHEMA_VERSION` is bumped (currently 2 — bump on any change to the shape of `result`)

### Key Config Files (not committed, user-managed)

| File | Purpose |
|------|---------|
| `po_builder_settings.json` | UI settings, shared data folder path |
| `order_rules.json` | Per-item buy rules (pack size, triggers, cover days) |
| `vendor_codes.txt` | Known vendor codes |
| `vendor_policies.json` | Per-vendor shipping/release hold policies |
| `ignored_items.txt` | `line_code:item_code` pairs to skip |
| `suspense_carry.json` | Suspense items carried between sessions |
| `supplier_vendor_map.json` | Supplier → vendor auto-mapping |
| `item_notes.json` | Per-item notes keyed by `LC:IC` |
| `sessions/` | Timestamped JSON snapshots for audit trail |

### Rule Key Format

Order rules in `order_rules.json` are keyed as `"LINE-:ITEMCODE"` (line code + colon + item code). The slash-bearing X4 line codes require careful handling — see parsers.py and tests for edge cases.

## Performance Notes (critical context)

The operator runs this against a large production dataset. The performance profile is measured by the built-in `perf_trace` harness (enable via `DEBUG_PERF=1` env var or a `perf_trace.enabled` flag file next to the exe).

**Post-v0.8.12 baseline on 63K-item / 8-year dataset:**

| Phase | Time | Notes |
|---|---:|---|
| `parse_all_files` | ~17 s | CSV-bound; 87% is `parse_detailed_pair_aggregates` on the 293 MB detailed sales file |
| `prepare_assignment_session` | **~5.6 s** | Was 35 s before v0.8.12; dropped from fixing an O(n²) `_description_for_key` scan |
| `normalize_items_to_cycle` | ~0 ms | Was 23 s before v0.8.10; folded into `prepare_assignment_session` |
| `build_bulk_sheet_rows` (first paint) | ~8.9 s | Pure Python row-tuple building on 59K items |
| **Total pre-UI** | **~32 s** | Was ~85 s on v0.8.9 — 2.7× faster |

**Key perf invariants to preserve:**

1. **Never put O(n) scans inside the per-item hot loops.** Prefer lazy per-session indexes. The `_description_for_key` / `sales_history_for_key` caches in `reorder_flow.py` are examples.
2. **Memoize anything deterministic that's called per-item.** See `QtSessionController._suggest_min_max` and `_resolve_pack_size_with_source` — both are per-session dict caches, invalidated on cycle change / data reload.
3. **Run the harness on the biggest real dataset**, not a synthetic 8K fixture. The v0.8.2 → v0.8.12 arc proved that small-dataset measurements give wrong answers — what felt "fine on the dev box" took 35+ seconds on the operator's 63K workload.
4. **Instrument before optimizing.** The perf harness's `span_start` breadcrumbs (v0.8.5) + per-loop breakdown stamps (v0.8.11) are what made every subsequent fix possible. Don't rip them out.

**Perf harness output files** (when enabled):
- `perf_trace.jsonl` — one JSON row per span/stamp event (also writes `span_start` breadcrumbs on entry so mid-function crashes leave a trail)
- `perf_summary.txt` — aggregate count/total/avg/min/max/p50/p95/p99 table written on clean shutdown via `atexit`
- `debug_trace.log` — append-only trace of business events (removal counts, delete keystrokes, dialog visibility, etc.)

## Testing Notes

- ~45 test files under `tests/`, one per major module
- Tests are plain `unittest` — no pytest required
- The build script (`build.bat`) runs the full suite and aborts on failure
- Parse caching uses pickle; if tests touch cached state, the cache file (`parse_result_cache.pkl`) may need deletion between runs
- Qt tests skip gracefully when `QApplication` can't instantiate (headless CI)

## Lessons learned (for future sessions)

1. **The harness is the most important piece of code in this repo.** Every speculative fix from v0.8.3 onward missed the real cause until the trace data told us what was actually happening.
2. **The operator workflow is exception-heavy.** `check_stock_warnings` was designed for "5-10 exceptions"; on the real data it had to handle 1,099. Always consider "what if this has 1000× the expected input?"
3. **Match the operator's mental model over Excel convention.** Delete key = remove row (not clear cell) on this app. Audit: whose workflow are you optimizing for?
4. **O(n²) hides in innocent-looking helpers.** `_description_for_key` looked like a one-off fallback lookup. It was the single biggest perf bug in the entire codebase. Always ask "is this O(1)?" when it's called per-item in a 60K-item loop.
5. **Design for the operator, not the developer.** The ADHD-friendly v0.9.0 redesign reduced the operator's work from 4,000+ manual assignments to ~150 exceptions. Auto-assign, quick filters, and reduced columns matter more than code elegance.
6. **Demand normalization over long windows needs an annualized floor.** Items with <1 sale/year over 8 years should skip ordering. The MIN_ANNUALIZED_DEMAND_FOR_AUTO_ORDER threshold (1.0/yr) prevents stale one-off sales from generating POs.
7. **Near-pack tolerance must be directional.** Round UP for the first pack, tolerance only for multi-pack boundaries. `need=1, pack=40` → must order 40, not 1.

## Known Open Items

- Phase 4 native acceleration — deferred pending operator field time
- `test_parse_golden.py` — needs real 293 MB dataset
- Shift+click secondary sort — optional
