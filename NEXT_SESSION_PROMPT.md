# Next session — kick-off prompt

Paste this into the next Claude Code session:

---

We're continuing PO Builder development. **Active work: PySide6 migration (v0.10.0).**

## Current state

- **Version:** v0.10.0-alpha3
- **Tests:** 1,308 passing (tkinter + Qt combined)
- **Two builds coexist:**
  - `build.bat` → `dist/POBuilder.exe` (30 MB, tkinter, weekly-run primary)
  - `build.bat qt` → `dist/POBuilder_Qt.exe` (~90 MB, PySide6, alpha)
- **Tkinter build is unchanged and ships every Monday.** Qt build is additive until parity.

## Read first (in this order)

1. `CLAUDE.md` — architecture + invariants + migration phase table + discipline rules
2. `theme.py` — framework-independent design tokens (5×5×5 palette from Tuner's `theme.hpp`)
3. `theme_qt.py` — Qt stylesheet helpers (card_style, sidebar_style, app_stylesheet, etc.)
4. `ui_qt/shell.py` — POBuilderShell (QMainWindow + sidebar + QStackedWidget)
5. `ui_qt/load_tab.py` — Qt Load tab (folder scan, file pickers, QThread parse worker)
6. `ui_qt/help_tab.py` — Qt Help tab (section list + QTextBrowser body renderer)
7. `ui_qt/bulk_model.py` — BulkTableModel + BulkFilterProxyModel + row value builder
8. `ui_qt/bulk_delegate.py` — BulkDelegate (row tinting + cell editors)
9. `ui_qt/bulk_tab.py` — BulkTab (QTableView + toolbar + filters + summary)

## What shipped this session (v0.10.0-alpha3)

| Component | What |
|-----------|------|
| `ui_qt/bulk_model.py` | `BulkTableModel` with `setData` edit callbacks, generation cache, `BulkFilterProxyModel` (6 filter axes) |
| `ui_qt/bulk_delegate.py` | Row tinting via `ROW_TINT_ROLE` + `theme.zone_fill()`, combo/spinbox editors |
| `ui_qt/bulk_tab.py` | QTableView, vendor worksheet, quick filter pills, action bar, filter row, summary strip, column visibility, Delete key, context menu |
| `ui_qt/session_controller.py` | Non-UI controller: full load→assign→enrich→auto-assign pipeline without tkinter dependency |
| `ui_qt/shell.py` | BulkTab wired; load_finished runs full pipeline; cell edits persist; vendor apply + row removal functional |
| `tests/test_qt_bulk_model.py` | 22 tests (model, proxy, row helpers) |
| `tests/test_qt_session_controller.py` | 18 tests (controller, setData, shell integration) |

## Migration phase table

| Phase | Surfaces | Status |
|-------|----------|--------|
| alpha1 | Shell, sidebar, theme | done |
| alpha2 | Load tab + Help tab | done |
| alpha3 | Bulk grid (QTableView + model + delegate) | **done** |
| **alpha4** | **Review, Export, dialogs, session controller** | **next** |
| beta1 | Command palette, shortcuts, polish | pending |
| release | Delete tk, rename `po_builder_qt.py` → `po_builder.py` | pending |

## What to build next: v0.10.0-alpha4 (Review + Export + Controller)

### Plan

1. **Session controller (`ui_qt/session_controller.py`)** — non-UI controller that wires `load_flow.apply_load_result` → `assignment_flow.prepare_assignment_session` → `auto_assign_flow` → bulk grid population.  Currently `_on_load_finished` in shell.py just dumps raw sales items into the grid; alpha4 runs the full pipeline so enrich_item, reorder triggers, suggested qty, and auto-assign all fire.

2. **Wire bulk grid editing** — connect `BulkTab.edit_committed` signal through `bulk_edit_flow.apply_editor_value` so vendor/qty/pack/notes edits actually mutate `filtered_items` and recalculate.  The delegate already creates the right editors; alpha4 hooks up `setData()` on the model to call the flow module.

3. **Wire vendor apply + row removal** — connect `BulkTab.vendor_applied` and `BulkTab.rows_removed` signals to `assignment_flow` and `bulk_remove_flow`.

4. **Review tab (`ui_qt/review_tab.py`)** — exception review before export.  Port `ui_review.py` surface: list of items with review flags, resolve/skip/override actions, "Finish & Export" button.

5. **Export flow wiring** — connect the Review tab's export button to `export_flow.export_vendor_files`.

6. **Dialogs** — port the key dialogs to Qt: stock warnings, remove-not-needed confirmation, buy rule editor, vendor manager, item details.

7. **Undo/redo** — wire `BulkTab._on_undo` / `_on_redo` to either `QUndoStack` or the existing `session_state_flow` history mechanism.

### Key files to study

- `app/session_controller.py` — non-Tk SessionController with `_recalculate_item`, `_suggest_min_max`
- `po_builder.py` — `POBuilderApp` class, especially `_proceed_to_assign_inner`, `_do_load`, `_finish_bulk`
- `ui_review.py` — tkinter review tab
- `export_flow.py` — export grouping, per-vendor xlsx writing
- `ui_bulk_dialogs.py` — stock warnings, finish_bulk_final, buy rule editor

### Discipline rules (must hold for every commit)

1. Both tkinter and Qt builds succeed
2. Full test suite passes (1,308+ tests)
3. No feature additions in either stack — parity first
4. Flow modules stay UI-agnostic (no tkinter or Qt imports)
5. Theme tokens from `theme.py` for all colors; `theme_qt.py` helpers for all stylesheets

## Architecture reminders

- **Flow modules are UI-agnostic:** `load_flow`, `assignment_flow`, `export_flow`, `draft_report_flow`, `schema_drift`, `reorder_flow`, `rules/`, `parsers/`, `models/`, `storage.py` — call from either UI stack
- **Pure-data modules:** `ui_load_data.py`, `ui_help_data.py` — shared between tkinter and Qt without tkinter import
- **Session state:** `AppSessionState` in `models/__init__.py` holds everything; `session.filtered_items` is the bulk grid data source
- **Row ID format:** `json.dumps([line_code, item_code], separators=(",", ":"))` — used for lookup/selection
- **Performance invariant:** never put O(n) scans inside per-item hot loops; use lazy per-session indexes
- **Bulk model cache:** generation-keyed (same pattern as tkinter `_bulk_row_render_cache`); bump via `model.bump_generation()` after edits
- **Filter proxy:** `BulkFilterProxyModel.filterAcceptsRow` reads item dicts directly — O(1) per row, uses pre-built `_text_haystack`

## Deferred from this session

- Undo/redo stack — alpha4
- Cost-coverage badge on summary strip — alpha4
- Attention filter ("High Risk" quick pill) — not yet wired to a field
- Review tab + Export flow — alpha4
- Dialogs (buy rule editor, stock warnings, vendor manager) — alpha4

## Key invariants to preserve (from previous sessions)

- Auto-assign runs after prepare_assignment_session, before bulk tree populate
- Stale demand threshold: MIN_ANNUALIZED_DEMAND_FOR_AUTO_ORDER = 1.0
- Draft PO exclusion: `exclude_draft_pos_from_committed` default True
- Schema drift hashes persist in `po_builder_settings.json` under `csv_schema_hashes`
- Render cache eviction: must evict in apply_editor_value AND refresh_bulk_view_after_edit
- _hide_loading() must be called on ALL exit paths from _proceed_to_assign_inner
- 1,308+ tests must pass. Build script runs them before bundling.
