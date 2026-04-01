# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

**PO Builder** is a Windows desktop application (v0.1.23) that converts X4 ERP report exports (CSV) into vendor-specific purchase order Excel files. It merges sales, receipts, inventory, open PO, and suspended-item reports, calculates order quantities, and lets the user assign vendors before exporting per-vendor `.xlsx` files in X4 import format.

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
- `rules.py` — ordering logic, quantity calculations, pack/trigger evaluation
- `parsers.py` — CSV parsing, X4 report auto-detection, header normalization
- `models.py` — data classes: `ItemKey`, `SourceItemState`, `SessionItemState`, `SuggestedItemState`, `AppSessionState`, `SessionSnapshot`
- `storage.py` — atomic JSON/text file I/O, lock handling, shared-folder merge logic

**2. Flow Modules** — discrete, testable workflow controllers (no direct UI):
- `load_flow.py` — CSV loading, pickle-based parse caching (invalidated by file signature), line-code resolution
- `session_state_flow.py` — session initialization, data merging into `AppSessionState`
- `reorder_flow.py` — reorder trigger evaluation
- `shipping_flow.py` — vendor release/hold policies
- `export_flow.py` — export grouping, vendor scoping
- `assignment_flow.py` — vendor/qty assignment business logic
- `bulk_sheet_actions_flow.py` — undo/redo stack (25-item) for bulk edits
- `persistent_state_flow.py` — load/save `order_rules.json`, `vendor_codes.txt`
- Other `*_flow.py` files handle specific sub-workflows

**3. UI Modules** — all `ui_*.py` + `bulk_sheet.py`, built on tkinter + tksheet:
- `ui_bulk.py` + `bulk_sheet.py` — spreadsheet-style bulk assignment grid
- `ui_review.py` — exception review before export
- `ui_bulk_dialogs.py` — pack rules, vendor policy dialogs

**4. Entry Point:**
- `po_builder.py` (~2,000 lines) — `POBuilderApp` class, tab layout, delegates to flow/UI modules. Exposes session fields via property accessors that delegate to `AppSessionState`.

### Session Lifecycle (Data Flow)

```
Load CSVs → Parse & cache → Build AppSessionState → Apply rules → Filter by line code/customer
→ Bulk/Individual assignment → Review exceptions → Export per-vendor .xlsx → Save session snapshot
```

### Key Data Structures (`models.py`)

- `ItemKey`: `(line_code, item_code)` tuple — primary key throughout
- `AppSessionState`: central mutable state passed through all flows; holds all lookups and assigned items
- `SessionSnapshot`: written to `sessions/` on export — full audit record

### Persistence

- **Local**: JSON/text files next to the executable (or script directory)
- **Shared**: Optional network/OneDrive folder configured in `po_builder_settings.json` → `shared_data_dir`
- Shared-folder writes use atomic rename + lock files + merge logic for concurrency
- Parse results cached as `parse_result_cache.pkl`, invalidated when source file signatures change

### Key Config Files (not committed, user-managed)

| File | Purpose |
|------|---------|
| `po_builder_settings.json` | UI settings, shared data folder path |
| `order_rules.json` | Per-item buy rules (pack size, triggers, cover days) |
| `vendor_codes.txt` | Known vendor codes |
| `vendor_policies.json` | Per-vendor shipping/release hold policies |
| `ignored_items.txt` | `line_code:item_code` pairs to skip |
| `suspense_carry.json` | Suspense items carried between sessions |
| `sessions/` | Timestamped JSON snapshots for audit trail |

### Rule Key Format

Order rules in `order_rules.json` are keyed as `"LINE-:ITEMCODE"` (line code + colon + item code). The slash-bearing X4 line codes require careful handling — see parsers.py and tests for edge cases (fixed in v0.1.23).

## Testing Notes

- 39 test files under `tests/`, one per major module
- Tests are plain `unittest` — no pytest required
- The build script (`build.bat`) runs the full suite and aborts on failure
- Parse caching uses pickle; if tests touch cached state, the cache file (`parse_result_cache.pkl`) may need deletion between runs
