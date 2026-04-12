# Next session — kick-off prompt

Paste this into the next Claude Code session:

---

We're continuing PO Builder development. **Active work: PySide6 migration (v0.10.0).**

## Current state

- **Version:** v0.10.0-alpha2
- **Tests:** 1,252 passing (tkinter + Qt combined)
- **Two builds coexist:**
  - `build.bat` → `dist/POBuilder.exe` (30 MB, tkinter, weekly-run primary)
  - `build.bat qt` → `dist/POBuilder_Qt.exe` (61 MB, PySide6, alpha)
- **Tkinter build is unchanged and ships every Monday.** Qt build is additive until parity.

## Read first (in this order)

1. `CLAUDE.md` — architecture + invariants + migration phase table + discipline rules
2. `theme.py` — framework-independent design tokens (5×5×5 palette from Tuner's `theme.hpp`)
3. `theme_qt.py` — Qt stylesheet helpers (card_style, sidebar_style, app_stylesheet, etc.)
4. `ui_qt/shell.py` — POBuilderShell (QMainWindow + sidebar + QStackedWidget)
5. `ui_qt/load_tab.py` — Qt Load tab (folder scan, file pickers, QThread parse worker)
6. `ui_qt/help_tab.py` — Qt Help tab (section list + QTextBrowser body renderer)

## What shipped this session (v0.9.1 through v0.10.0-alpha2)

| Release | Feature |
|---------|---------|
| v0.9.1 | **Draft PO filter fix** — X4 "Draft PO" lines excluded from committed qty; load-time warning; `exclude_draft_pos_from_committed` setting |
| v0.9.2 | **Draft Review (Print)** — per-vendor print-formatted xlsx; `draft_report_flow.py`; landscape letter, bold yellow Draft Qty column, totals row |
| v0.9.3 | **Ctrl+K command palette** (`ui_command_palette.py`) — type to jump to items/vendors/actions; **CSV schema drift detection** (`schema_drift.py`) |
| v0.10.0-alpha1 | **PySide6 migration kickoff** — shell, sidebar, `theme.py`, `theme_qt.py`, `po_builder_qt.py` entry point, `PO_Builder_Qt.spec`, `build.bat qt` |
| v0.10.0-alpha2 | **Load tab + Help tab in Qt** — file pickers, QThread parse worker, Quick Start card, schema drift baseline, Help section browser with markdown→HTML |
| (bugfix) | Extract `ui_load_data.py` / `ui_help_data.py` to break tkinter transitive import in Qt build |

## Migration phase table

| Phase | Surfaces | Status |
|-------|----------|--------|
| alpha1 | Shell, sidebar, theme | done |
| alpha2 | Load tab + Help tab | **done** |
| **alpha3** | **Bulk grid (QTableView + model + delegate)** | **next** |
| alpha4 | Review, Export, dialogs | pending |
| beta1 | Command palette, shortcuts, polish | pending |
| release | Delete tk, rename `po_builder_qt.py` → `po_builder.py` | pending |

## What to build next: v0.10.0-alpha3 (Bulk grid)

This is the hardest and most important phase. The bulk grid is PO Builder's primary working surface — 63K items, vendor assignment, qty editing, pack rounding, row coloring, context menus, filtering, undo/redo.

### Plan

1. **`ui_qt/bulk_tab.py`** — `QTableView` + custom `QAbstractTableModel` backed by `session.filtered_items`
2. **`QSortFilterProxyModel`** for vendor/status/text filtering (replaces the tkinter filter chain)
3. **Custom `QStyledItemDelegate`** for row tints using `theme.zone_fill()` and bold yellow Draft Qty column
4. **Cell editing** — `QComboBox` delegate for vendor column (populated from KNOWN_VENDORS), `QSpinBox` or direct text for qty/pack/min/max, plain text for notes
5. **Delete key dispatch** via `keyPressEvent` on the table view (rows selected → remove, cells selected → clear)
6. **Right-click context menu** via `contextMenuEvent` (Remove Selected, View Details, Edit Buy Rule, etc.)
7. **Column visibility** toggle via header context menu
8. **Quick filter pills** — row of `QPushButton` above the table (All, Unassigned, Review, Warnings, High Risk)
9. **Vendor worksheet dropdown** — `QComboBox` in the toolbar switching `var_bulk_vendor_filter_internal`
10. **Undo/redo** plumbing via `QUndoStack` (or manual stack mirroring the tkinter approach)
11. **Wire `assignment_flow.prepare_assignment_session`** and `load_flow.apply_load_result` so Load → Bulk flow works end-to-end in the Qt build
12. **Performance target:** 63K items must load in <10s and scroll at 60fps on the operator's machine

### Key files to study

- `bulk_sheet.py` — tkinter BulkSheetView wrapper; column definitions, row_ids, render cache, row coloring, edit dispatch
- `ui_bulk.py` — tkinter bulk tab builder; action bars, filter dropdowns, vendor worksheet, quick filter pills
- `assignment_flow.py:prepare_assignment_session` — the core per-item loop that builds `session.filtered_items`
- `bulk_edit_flow.py` — per-cell editor handling (vendor, qty, pack, min, max, qoh, notes)
- `bulk_sheet_actions_flow.py` — Delete-key dispatch, undo/redo plumbing
- `bulk_remove_flow.py` — bulk row removal with per-row diagnostic logging
- `rules/__init__.py:enrich_item` — called per-item to stamp order_qty, why, status

### Discipline rules (must hold for every commit)

1. Both tkinter and Qt builds succeed
2. Full test suite passes (1,252+ tests)
3. No feature additions in either stack — parity first
4. Flow modules stay UI-agnostic (no tkinter or Qt imports)
5. Theme tokens from `theme.py` for all colors; `theme_qt.py` helpers for all stylesheets

## Architecture reminders

- **Flow modules are UI-agnostic:** `load_flow`, `assignment_flow`, `export_flow`, `draft_report_flow`, `schema_drift`, `reorder_flow`, `rules/`, `parsers/`, `models/`, `storage.py` — call from either UI stack
- **Pure-data modules:** `ui_load_data.py`, `ui_help_data.py` — shared between tkinter and Qt without tkinter import
- **Session state:** `AppSessionState` in `models/__init__.py` holds everything; `session.filtered_items` is the bulk grid data source
- **Row ID format:** `json.dumps([line_code, item_code], separators=(",", ":"))` — used for lookup/selection
- **Performance invariant:** never put O(n) scans inside per-item hot loops; use lazy per-session indexes

## Also deferred from this session

- Tuner visual style port to tkinter (abandoned in favor of PySide6 migration)
- `theme.py` was written but never applied to the tkinter build; it's used only by the Qt build now
- Cost-coverage badge on the bulk grid status line (can wire during alpha3)

## Key invariants to preserve (from previous sessions)

- Auto-assign runs after prepare_assignment_session, before bulk tree populate
- Stale demand threshold: MIN_ANNUALIZED_DEMAND_FOR_AUTO_ORDER = 1.0
- Draft PO exclusion: `exclude_draft_pos_from_committed` default True
- Schema drift hashes persist in `po_builder_settings.json` under `csv_schema_hashes`
- Render cache eviction: must evict in apply_editor_value AND refresh_bulk_view_after_edit
- _hide_loading() must be called on ALL exit paths from _proceed_to_assign_inner
- 1,252+ tests must pass. Build script runs them before bundling.
