# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

**PO Builder** is a Windows desktop application (**v0.8.13**) that converts X4 ERP report exports (CSV) into vendor-specific purchase order Excel files. It merges sales, receipts, inventory, open PO, and suspended-item reports, calculates order quantities, and lets the user assign vendors before exporting per-vendor `.xlsx` files in X4 import format.

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
As of v0.8.13: **1,140 tests**.

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
- `rules.py` (~1,670 lines) — ordering logic, quantity calculations, pack/trigger evaluation, the `enrich_item` orchestrator
- `parsers.py` (~1,220 lines) — CSV parsing, X4 report auto-detection, header normalization, per-row builders, streamed aggregation
- `reorder_flow.py` — reorder trigger evaluation, cached description/sales indexes, `suggest_min_max`
- `models.py` — data classes: `ItemKey`, `SourceItemState`, `SessionItemState`, `SuggestedItemState`, `AppSessionState`, `SessionSnapshot`
- `storage.py` — atomic JSON/text file I/O, lock handling, shared-folder merge logic
- `perf_trace.py` — opt-in timing harness (see Performance Notes)

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

**3. UI Modules** — all `ui_*.py` + `bulk_sheet.py`, built on tkinter + tksheet:
- `ui_bulk.py` (~1,600 lines) — bulk grid tab: filter state, bucket index, render cache, row builder
- `bulk_sheet.py` (~1,100 lines) — tksheet wrapper, Delete key interceptor via bindtag manipulation, context menu
- `ui_bulk_dialogs.py` (~1,330 lines) — Remove-not-needed, stock warnings, finish_bulk_final, buy rule editor, **custom Toplevels with `_force_dialog_foreground` for Windows z-order fix**
- `ui_review.py` — exception review before export
- `ui_help.py` — Help tab with live search, tagged rendering, contextual-help API (`open_help_for`, `focus_help_section`)
- `ui_session_diff.py`, `ui_vendor_review.py`, `ui_supplier_map.py`, `ui_qoh_review.py`, `ui_skip_actions.py` — feature dialogs

**4. Entry Point:**
- `po_builder.py` (~2,100 lines) — `POBuilderApp` class, tab layout, delegates to flow/UI modules. Exposes session fields via property accessors that delegate to `AppSessionState`. Hosts the cached `_suggest_min_max`, `_resolve_pack_size_with_source`, and other memoized helpers.

### Session Lifecycle (Data Flow)

```
Load CSVs → Parse & cache → Build AppSessionState → Apply rules → Filter by line code/customer
→ Bulk/Individual assignment → Review exceptions → Export per-vendor .xlsx → Save session snapshot
```

### Key Data Structures (`models.py`)

- `ItemKey`: `(line_code, item_code)` tuple — primary key throughout
- `AppSessionState`: central mutable state passed through all flows; holds all lookups and assigned items. ~30 fields spanning raw loads, derived lookups, user decisions, and session metadata. **Known god-object**; planned for sub-state split in a future release (see `ROADMAP_v0.8.md` Phase 3.3).
- `SessionSnapshot`: written to `sessions/` on export — full audit record

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
- **v0.8.13** — **Fixed cell editing regression** (tksheet binding name change broke all grid edits); Ctrl+F global shortcut; perf substep stamps on `bulk_remove_flow` and `finish_bulk_final`

## Lessons from the v0.8.x debugging arc (for future sessions)

1. **The harness is the most important piece of code in this repo.** Every speculative fix from v0.8.3 onward missed the real cause until the trace data told us what was actually happening.
2. **Dialog visibility on Windows Tk is a real problem.** `messagebox` without explicit parent + geometry frequently lands at (0,0) or behind the main window. Use `_force_dialog_foreground` or the custom Toplevel pattern in `ui_bulk_dialogs.py`.
3. **tksheet's bindings consume events before widget-level bindings fire.** To intercept keys on the sheet, prepend a custom bindtag to each sub-widget via `bind_class` — see `BulkSheetView._bind_row_delete_keys`.
4. **The operator workflow is exception-heavy.** `check_stock_warnings` was designed for "5-10 exceptions"; on the real data it had to handle 1,099. Always consider "what if this has 1000× the expected input?"
5. **Match the operator's mental model over Excel convention.** Delete key = remove row (not clear cell) on this app. Audit: whose workflow are you optimizing for?
6. **O(n²) hides in innocent-looking helpers.** `_description_for_key` looked like a one-off fallback lookup. It was the single biggest perf bug in the entire codebase. Always ask "is this O(1)?" when it's called per-item in a 60K-item loop.

## Known Open Items (see ROADMAP_v0.8.md for full plan)

- `build_bulk_sheet_rows` still takes ~8.9 s on first paint — next perf target after v0.8.12
- `rules.py` / `parsers.py` structural refactors from the audit are still open (Phase 3)
- `AppSessionState` sub-state split is still open (Phase 3.3)
- Phase 5 manual QA pass against real data
