# PO Builder v0.10.0-beta1 Release Notes

**Date:** 2026-04-12
**Build:** `dist/POBuilder.exe` (30 MB, tkinter) + `dist/POBuilder_Qt.exe` (61 MB, Qt)
**Tests:** 1,379 passing

## What's New

### All 12 Workflow Dialogs Ported to Qt

Every tkinter dialog now has a Qt equivalent in `ui_qt/workflow_dialogs.py`, using the Tuner visual grammar (theme.py tokens, card_style accents, number cards, generous spacing).

| Dialog | Purpose |
|--------|---------|
| Remove Not Needed | Interactive checkbox table with summary cards |
| Stock Warnings | Pre-export review of flagged items |
| Too Many Flagged | Summary confirm for >50 flagged items |
| Vendor Review | Per-vendor activity from session snapshots |
| Session Diff | Tabbed comparison against previous snapshot |
| Supplier Map | Supplier-to-vendor auto-mapping editor |
| QOH Adjustments | Review and revert QOH edits |
| Skip Cleanup | Bulk ignore / discontinue / export CSV |
| Bulk Rule Edit | Apply partial buy-rule changes to multiple items |
| Ignored Items | View, filter, and restore ignored items |
| Vendor Policy | Per-vendor shipping/release configuration |
| Vendor Manager | Add, rename, remove vendor codes |
| Session History | Browse past snapshots with item-level detail |

### "More" Menu on Bulk Tab

All workflow dialogs accessible from a single **More** dropdown on the bulk tab toolbar. Clean, non-intimidating, discoverable.

### Stock Warnings Wired into Export

The Qt export path now runs the same stock warnings gate as tkinter before writing PO files. Items flagged as not-needed show a review dialog; unchecked items have their vendor cleared.

### Performance: Remove Not Needed on 56K Items

- **Scan:** 730ms (synchronous with status bar progress)
- **Dialog build:** ~2.5s for 55K rows using `QTableWidgetItem` check states
- **Previous:** 90s (was creating 55K QCheckBox + QWidget + QHBoxLayout widgets)
- **Fix:** Replaced per-row widget allocation with native item check states

### Perf Trace Wired into Qt Entry Point

`po_builder_qt.py` now calls `perf_trace.maybe_auto_enable()` on startup, so `DEBUG_PERF=1` or the `perf_trace.enabled` flag file work for the Qt build.

## Design Philosophy

All new dialogs follow the stated design principles:

- **Intuitive** — lead with the action, not the data
- **Non-intimidating** — summary cards instead of dense tables; 5 columns max on review dialogs
- **Beautiful** — Tuner palette (theme.py tokens), 3px accent bars, card grammar
- **Modern** — generous spacing, clear primary/secondary/danger button hierarchy

## Files Changed

- `app_version.py` — bumped to 0.10.0-beta1
- `po_builder_qt.py` — added `perf_trace.maybe_auto_enable()` call
- `ui_qt/workflow_dialogs.py` — **new**, 12 dialog classes + shared helpers
- `ui_qt/shell.py` — Remove Not Needed dialog integration, stock warnings gate, 8 dialog launcher methods, 8 new signal connections
- `ui_qt/bulk_tab.py` — 8 workflow signals + "More" dropdown menu
- `tests/test_qt_workflow_dialogs.py` — **new**, 30 headless tests

## Migration Status

| Phase | Surfaces | Status |
|-------|----------|--------|
| alpha1 | Shell, sidebar, theme | done |
| alpha2 | Load tab + Help tab | done |
| alpha3 | Bulk grid, session controller, undo/redo, review/export | done |
| **beta1** | **QThread pipeline, number cards, session snapshots, editor styling, data labels, all dialogs** | **done** |
| release | Delete tk, rename `po_builder_qt.py` to `po_builder.py` | pending |

## How to Run

No installation needed. Single-file executables:

- **Tkinter (primary):** `dist/POBuilder.exe` (30 MB)
- **Qt (beta):** `dist/POBuilder_Qt.exe` (61 MB)

Both read the same config files (`po_builder_settings.json`, `order_rules.json`, etc.) and write to the same `sessions/` directory.
