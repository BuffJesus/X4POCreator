# PO Builder v0.10.0 — PySide6 Migration Complete

**The tkinter era is over. PO Builder now runs entirely on PySide6.**

This release deletes the tkinter UI stack and promotes the Qt build
to the sole entry point. Same workflow, same data files, same
operator experience — but on a modern widget toolkit that matches
the Tuner app's visual system and unlocks capabilities tkinter
couldn't deliver (per-side borders, true border-radius, native
HiDPI, stylesheet-driven theming).

873 tests pass. 61 MB single-file exe (was 30 MB tkinter + 61 MB Qt
side-by-side — net savings since the operator no longer needs both).

---

## What Changed

### Deleted: entire tkinter stack (~30,000 lines)

- **37 source files removed**: `po_builder.py` (tkinter entry point),
  all `ui_*.py` modules, `bulk_sheet.py`, `app/` directory,
  `review_flow.py`, `app_runtime_flow.py`, `data_folder_flow.py`,
  and 6 tkinter-coupled flow modules
- **24 test files removed**: all tkinter UI tests and tests for
  deleted flow modules
- **Dependencies dropped**: `tksheet`, `ttkbootstrap` no longer
  required

### Promoted: Qt stack is now primary

- `po_builder_qt.py` renamed to `po_builder.py`
- `PO_Builder_Qt.spec` renamed to `PO_Builder.spec`
- `build.bat` simplified: `build.bat` → release, `build.bat debug`
  → debug with console
- Single output: `dist/POBuilder.exe`

### Refactored for UI independence

- `export_flow.py` — removed tkinter fallbacks; dialog calls now go
  through app handler methods (`_show_info`, `_ask_yes_no`, etc.)
- `assignment_flow.py` — removed `ui_bulk` dependency; sets
  `session.filtered_items` directly
- `reorder_flow.py` — `_rebuild_bulk_metadata_after_inplace_recalc`
  is now a no-op (Qt model handles refresh via signals)

### Extracted shared data modules

- `command_palette_data.py` — UI-agnostic indexing/ranking for Ctrl+K
- `shortcut_data.py` — keyboard shortcut group definitions

---

## What Didn't Change

- **All flow modules** — `load_flow`, `assignment_flow`,
  `export_flow`, `shipping_flow`, `reorder_flow`, etc.
- **All business logic** — `rules/`, `parsers/`, `models/`
- **All data files** — same `po_builder_settings.json`,
  `order_rules.json`, `vendor_codes.txt`, `sessions/`, etc.
- **The operator workflow** — load, filter, assign, review, export
- **Performance profile** — same ~32 s pre-UI pipeline on 63K items
- **Session snapshots** — fully compatible with prior sessions

---

## Upgrade Path

Drop the new `POBuilder.exe` in place of the old one. No config
changes needed — all settings, rules, vendor codes, and session
history carry over unchanged. The app reads the same
`po_builder_settings.json` and data files it always has.

---

## Build Targets

| Command | Output | Notes |
|---------|--------|-------|
| `build.bat` | `dist/POBuilder.exe` (61 MB) | Release build |
| `build.bat debug` | `dist/PO Builder Debug.exe` | Console visible |

---

## Migration Timeline

| Phase | Version | What |
|-------|---------|------|
| alpha1 | 0.10.0-alpha1 | Shell, sidebar, theme tokens |
| alpha2 | 0.10.0-alpha2 | Load tab, Help tab |
| alpha3 | 0.10.0-alpha3 | Bulk grid, session controller, undo/redo, review/export |
| beta1 | 0.10.0-beta1 | QThread pipeline, workflow dialogs, number cards |
| **release** | **0.10.0** | **Delete tkinter, Qt is sole stack** |

---

## Stats

- **30,000 lines deleted** (tkinter UI + coupled flow modules)
- **480 lines added** (refactors, extracted data modules, test fixes)
- **873 tests pass** (was 1,379 with both stacks — 506 were tkinter-only)
- **61 MB exe** (single build, down from 30 + 61 = 91 MB combined)
- **3 dependencies** (openpyxl, Pillow, PySide6) — was 5
