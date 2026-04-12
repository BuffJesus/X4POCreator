# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

**PO Builder** is a Windows desktop application (**v0.10.0-alpha2**, migrating from tkinter to PySide6 during the 0.10.x cycle) that converts X4 ERP report exports (CSV) into vendor-specific purchase order Excel files. It merges sales, receipts, inventory, open PO, and suspended-item reports, calculates order quantities, and lets the user assign vendors before exporting per-vendor `.xlsx` files in X4 import format.

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
As of v0.10.0-alpha2: **1,252 tests** (tkinter + Qt combined).

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
- `rules/` package (7 modules, was single 1,670-line file):
  - `__init__.py` — `enrich_item` orchestrator (~110 lines, was 380)
  - `calc.py` — inventory position, target stock, raw need, suggested qty, overstock
  - `policy.py` — order policy determination, recency, dead stock, package classification
  - `explanation.py` — `build_reason_codes`, `build_detail_parts`
  - `status.py` — `evaluate_item_status`
  - `not_needed.py` — `not_needed_reason` (moved from UI layer)
  - `_constants.py`, `_helpers.py` — shared constants and rule accessors
- `parsers/` package (5 modules, was single 1,220-line file):
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
- `bulk_cache.py` — consolidated `BulkCacheState` object

**2. Flow Modules** — discrete, testable workflow controllers (no direct UI):
- `load_flow.py` — CSV loading, pickle-based parse caching (invalidated by file signature + schema version), line-code resolution, data-quality warnings
- `session_state_flow.py` — session initialization, bulk history capture/restore, ignore-key management
- `assignment_flow.py` — vendor/qty assignment, candidate building, per-item enrich orchestration
- `shipping_flow.py` — vendor release/hold policies
- `export_flow.py` — export grouping, vendor scoping, per-vendor xlsx writing, session snapshot
- `bulk_remove_flow.py` — bulk row removal with per-row diagnostic logging
- `bulk_sheet_actions_flow.py` — Delete-key dispatch, undo/redo plumbing
- `bulk_edit_flow.py` — per-cell editor handling
- `session_diff_flow.py` — session-over-session comparison (new items, qty changes, vendor changes)
- `supplier_map_flow.py` — supplier → vendor auto-mapping
- `qoh_review_flow.py` — QOH adjustment review + revert
- `skip_actions_flow.py` — bulk skip cleanup (ignore / flag discontinue / export CSV)
- `vendor_summary_flow.py` — per-vendor activity summaries
- `persistent_state_flow.py` — load/save `order_rules.json`, `vendor_codes.txt`, etc.

**3. UI Modules** — all `ui_*.py` + `bulk_sheet.py`, built on tkinter + ttkbootstrap + tksheet:
- `ui_bulk.py` — bulk grid tab: vendor worksheet dropdown, two-tier action bar, quick filter pills, filter state, bucket index, render cache, row builder, dynamic dropdown refresh
- `bulk_sheet.py` — tksheet wrapper, Delete key interceptor, context menu, row coloring, cell hover tooltips, column visibility toggle
- `ui_bulk_dialogs.py` — Remove-not-needed, stock warnings, finish_bulk_final, buy rule editor, **custom Toplevels with `_force_dialog_foreground` for Windows z-order fix**
- `ui_review.py` — exception review before export
- `ui_help.py` — Help tab with live search, tagged rendering, contextual-help API, Shortcuts page
- `ui_shortcut_overlay.py` — keyboard shortcut overlay (press ? on bulk grid)
- `ui_load.py` — Load tab with Quick Start card
- `ui_session_diff.py`, `ui_vendor_review.py`, `ui_supplier_map.py`, `ui_qoh_review.py`, `ui_skip_actions.py` — feature dialogs

**4. App Package + Entry Point:**
- `app/bootstrap.py` — `apply_dark_theme` (ttkbootstrap detection + fallback)
- `app/session_controller.py` — non-Tk `SessionController` with `_recalculate_item`, `_suggest_min_max`
- `po_builder.py` — `POBuilderApp` class, tab layout, workflow stepper, loading overlay with progress text. Uses ttkbootstrap `Window` with darkly theme.

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
2. **Memoize anything deterministic that's called per-item.** See `POBuilderApp._suggest_min_max` and `_resolve_pack_size_with_source` — both are per-session dict caches, invalidated on cycle change / data reload.
3. **Don't let bulk grid caches recompute signatures on every hit.** The row render cache is generation-keyed as of v0.8.10; don't regress by reintroducing per-cell signature comparison.
4. **Run the harness on the biggest real dataset**, not a synthetic 8K fixture. The v0.8.2 → v0.8.12 arc proved that small-dataset measurements give wrong answers — what felt "fine on the dev box" took 35+ seconds on the operator's 63K workload.
5. **Instrument before optimizing.** The perf harness's `span_start` breadcrumbs (v0.8.5) + per-loop breakdown stamps (v0.8.11) are what made every subsequent fix possible. Don't rip them out.

**Perf harness output files** (when enabled):
- `perf_trace.jsonl` — one JSON row per span/stamp event (also writes `span_start` breadcrumbs on entry so mid-function crashes leave a trail)
- `perf_summary.txt` — aggregate count/total/avg/min/max/p50/p95/p99 table written on clean shutdown via `atexit`
- `debug_trace.log` — append-only trace of business events (removal counts, delete keystrokes, dialog visibility, etc.)

## Testing Notes

- ~40 test files under `tests/`, one per major module
- Tests are plain `unittest` — no pytest required
- The build script (`build.bat`) runs the full suite and aborts on failure
- Parse caching uses pickle; if tests touch cached state, the cache file (`parse_result_cache.pkl`) may need deletion between runs
- **Headless tk tests** (`tests/test_ui_help.py`, some UI tests) skip gracefully when `tk.Tk()` can't instantiate
- **Perf baseline test** in `tests/test_bulk_perf_baseline.py` uses an 8K synthetic fixture to catch catastrophic regressions in the bulk grid hot paths — budgets are deliberately loose (5-10× measured time)

## v0.10.x — PySide6 migration (in progress)

The app is migrating from tkinter + ttkbootstrap + tksheet to PySide6.  The
migration uses a strangler pattern: both UI stacks coexist until the Qt
surfaces reach parity, then tkinter gets deleted.

- `po_builder.py` + `ui_*.py` + `bulk_sheet.py` — **tkinter stack** (primary,
  weekly-run target until Qt parity)
- `po_builder_qt.py` + `ui_qt/` — **Qt stack** (alpha, grows each release)
- `theme.py` — framework-independent design tokens (5 bg × 5 text × 5 accent
  palette ported from the Tuner app's `theme.hpp`)
- `theme_qt.py` — Qt stylesheet helpers consuming `theme.py` tokens
- Flow modules (`load_flow`, `assignment_flow`, `export_flow`,
  `draft_report_flow`, `schema_drift`, `reorder_flow`, `rules/`, `parsers/`,
  `models/`, `storage.py`) are **UI-agnostic** and called from both stacks.

Build targets:
- `build.bat` → `dist/POBuilder.exe` (tkinter, 30 MB)
- `build.bat qt` → `dist/POBuilder_Qt.exe` (Qt, ~90 MB)
- `build.bat debug` → `dist/PO Builder Debug.exe` (tkinter with console)

Migration phases (each is a release):

| Phase | Surfaces | Status |
|-------|----------|--------|
| alpha1 | Shell, sidebar, theme | done |
| alpha2 | Load tab + Help tab | **current** |
| alpha3 | Bulk grid (QTableView + model + delegate) | pending |
| alpha4 | Review, Export, dialogs | pending |
| beta1 | Command palette, shortcuts, polish | pending |
| release | Delete tk, rename `po_builder_qt.py` → `po_builder.py` | pending |

**Discipline rules** (every alpha commit must satisfy):
1. Both tkinter and Qt builds succeed.
2. Full test suite passes.
3. No feature additions in either stack during migration — parity first.
4. Flow modules stay UI-agnostic (no tkinter or Qt imports).

## Recent History (v0.8.x — perf + UX modernization)

Notable releases in chronological order — see corresponding `RELEASE_v0.8.*.md` files for details:

- **v0.8.0** — Help tab rebuild: live search, tagged rendering, contextual help API
- **v0.8.1** — Delete key lives on bulk grid + dark-themed right-click menu
- **v0.8.2** — Perf instrumentation harness (`perf_trace.py`)
- **v0.8.3–v0.8.8** — "Remove Unassigned → Review" lock-up saga (5 releases chasing a moving target); see the release history table in `RELEASE_v0.8.9.md`
- **v0.8.9** — Dialog lock-up fixed: short-circuit for >50 flagged items (was building 12,000 Tk widgets)
- **v0.8.10** — `normalize_items_to_cycle` eliminated as redundant pass (−23 s); generation-counter row render cache; memoized `_suggest_min_max`
- **v0.8.11** — Crunching-numbers instrumentation release: full span coverage of `_do_load` / `_proceed_to_assign` / `populate_bulk_tree` with per-loop breakdown stamps
- **v0.8.12** — **Eliminated O(n²) linear scan** in `_description_for_key`: `prepare_assignment_session` 34.5 s → 5.6 s (6.2× faster); `sales_history_for_key` also indexed; short-circuit in `receipt_pack_size_for_key`
- **v0.8.13** — **Fixed cell editing regression** (tksheet binding name change broke all grid edits); 5 bug fixes, 6 UX features, bulk edit 7.5×, `rules/` + `parsers/` + `models/` package split
- **v0.8.14** — ttkbootstrap darkly theme, row coloring, workflow stepper, column visibility toggle, TypedDict schemas, `parsers/` split complete
- **v0.9.0** — **ADHD-friendly workflow overhaul**: auto-assign vendors, quick load, vendor worksheet dropdown, two-tier action bar, quick filter pills, simplified why text, stale demand threshold (<1/yr skips ordering), pack rounding fix, dynamic dropdowns, shortcut overlay
- **v0.9.1** — **Draft PO filter fix**: X4 "auto max quantity PO" draft lines are no longer counted as already-committed; PO Builder's reorder trigger now correctly re-evaluates items that X4 drafted. Adds load-time "Draft PO Detected" warning. Setting `exclude_draft_pos_from_committed` (default true) in `po_builder_settings.json` controls behavior.
- **v0.9.2** — **Draft Review printout**: new per-vendor print-formatted xlsx export (`draft_report_flow.py`) triggered from the bulk grid's More Actions row. Landscape letter, fit-to-width, header repeats, bold yellow Draft Qty column, totals row with units + extended cost, cost coverage note. One file per vendor for physical verification.
- **v0.9.3** — **Ctrl+K command palette** (`ui_command_palette.py`) for keystroke-first navigation: type to jump to any item, vendor, or action across the whole app. **CSV schema drift detection** (`schema_drift.py`): hashes the header row of each source CSV on load and warns if any differs from last run, catching silent ERP export template changes before they corrupt output.
- **v0.10.0-alpha1** — **PySide6 migration kickoff**. New `po_builder_qt.py` entry point, `ui_qt/` package, `theme.py` (framework-independent tokens) + `theme_qt.py` (Qt stylesheet helpers) ported line-for-line from the Tuner app's `theme.hpp`. Empty shell with sidebar (Load/Filter/Bulk/Review/Help) + stacked pages; placeholders on every surface until subsequent alphas port each one. Tkinter build remains the weekly-run primary until parity.
- **v0.10.0-alpha2** — **Load tab + Help tab in Qt**. `ui_qt/load_tab.py` with hero banner, folder scan, per-file pickers (reuses tkinter's `LOAD_FILE_SECTIONS` data structure so both tabs stay in sync), `QThread`-based parse worker wrapping `load_flow.parse_all_files`, quick-start card when `last_scan_folder` is set, busy progress bar, schema drift hashes persisted via `app_settings`. `ui_qt/help_tab.py` with `QListWidget` section list + `QTextBrowser` body rendering the same `ui_help.HELP_SECTIONS` data through a markdown→HTML translator that respects theme tokens.

## Lessons from the v0.8.x debugging arc (for future sessions)

1. **The harness is the most important piece of code in this repo.** Every speculative fix from v0.8.3 onward missed the real cause until the trace data told us what was actually happening.
2. **Dialog visibility on Windows Tk is a real problem.** `messagebox` without explicit parent + geometry frequently lands at (0,0) or behind the main window. Use `_force_dialog_foreground` or the custom Toplevel pattern in `ui_bulk_dialogs.py`.
3. **tksheet's bindings consume events before widget-level bindings fire.** To intercept keys on the sheet, prepend a custom bindtag to each sub-widget via `bind_class` — see `BulkSheetView._bind_row_delete_keys`.
4. **The operator workflow is exception-heavy.** `check_stock_warnings` was designed for "5-10 exceptions"; on the real data it had to handle 1,099. Always consider "what if this has 1000× the expected input?"
5. **Match the operator's mental model over Excel convention.** Delete key = remove row (not clear cell) on this app. Audit: whose workflow are you optimizing for?
6. **O(n²) hides in innocent-looking helpers.** `_description_for_key` looked like a one-off fallback lookup. It was the single biggest perf bug in the entire codebase. Always ask "is this O(1)?" when it's called per-item in a 60K-item loop.
7. **Design for the operator, not the developer.** The ADHD-friendly v0.9.0 redesign reduced the operator's work from 4,000+ manual assignments to ~150 exceptions. Auto-assign, quick filters, and reduced columns matter more than code elegance.
8. **Render caches need aggressive eviction.** Three separate caches (render, visible-rows, filter-result) caused stale display bugs. Evict all caches at the edit site, not just in the refresh path.
9. **Demand normalization over long windows needs an annualized floor.** Items with <1 sale/year over 8 years should skip ordering. The MIN_ANNUALIZED_DEMAND_FOR_AUTO_ORDER threshold (1.0/yr) prevents stale one-off sales from generating POs.
10. **Near-pack tolerance must be directional.** Round UP for the first pack, tolerance only for multi-pack boundaries. `need=1, pack=40` → must order 40, not 1.

## Known Open Items (see ROADMAP_v0.8.md for full plan)

- Phase 4 native acceleration — deferred pending operator field time
- `SessionController` delegation from `POBuilderApp` — final separation step
- `test_parse_golden.py` — needs real 293 MB dataset
- Shift+click secondary sort — optional
- `items_by_status` collapse — speculative Phase 5
