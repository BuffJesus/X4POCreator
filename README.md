# PO Builder

Windows desktop app that turns X4 ERP report exports into
vendor-specific purchase order files.  Built on PySide6.

Load CSVs, auto-assign vendors from receipt history, review
exceptions, export per-vendor `.xlsx` POs.  Weekly workflow on a
63K-item / 8-year dataset completes in under a minute.

---

## Quick Start

```
python -m pip install -r requirements.txt
python po_builder.py
```

Or use the packaged executable: `dist/POBuilder.exe`

---

## What It Does

PO Builder combines X4 report inputs to answer four questions:

1. **What needs ordering?** Inventory position vs target stock,
   with reorder triggers and demand signals.
2. **How much?** Pack-aware rounding, reel/hose handling,
   overshoot deferral, min/max credibility checks.
3. **Which vendor?** Auto-assigned from receipt history, with
   mismatch detection when you override.
4. **What needs cleanup?** Maintenance report surfaces X4 source
   values that should be updated.

### Key Behaviors

- Inventory position = QOH + On PO (no double-subtraction of suspense)
- Pack-aware ordering: standard rounding, reel auto, pack triggers,
  overshoot deferral when stock is comfortable
- Max credibility: detects auto-calculated nonsense (max=10 for bolts
  in packs of 100) and adjusts target
- Vendor mismatch: amber warning when assigned vendor contradicts
  receipt history
- Dead stock: velocity-aware detection (2x normal cycle, not just
  365-day cliff)
- Auto-assign: high-confidence receipt history fills vendor
  automatically, reducing manual work to exceptions
- Per-item notes, buy rules, and order history persist across sessions

---

## Workflow

1. **Load** — scan a folder or browse to CSV files
2. **Filter** — exclude line codes or suspended customers
3. **Bulk Assign** — review the grid, assign vendors, adjust quantities
4. **Review & Export** — check exceptions, add PO memo, export

### Bulk Grid Features

- Summary cards: total items, assigned, unassigned, order value
- Quick filter pills: All, Unassigned, Review, Warnings, High Risk,
  Dead Stock, Deferred, Vendor Mismatch
- Shift+click headers for secondary sort (up to 3 levels)
- Apply by Supplier: assign a vendor to all items from a supplier
- Right-click column headers to show/hide columns
- Ctrl+K command palette for keyboard-first navigation
- Unit Cost, Ext Cost, Last Sale, Last Receipt columns
- Inline editing: Vendor, Final Qty, QOH, Min, Max, Pack, Notes

### Export Reports (More > Export Reports)

- **Dead Stock** — print-ready xlsx grouped by vendor with on-hand values
- **Deferred Items** — items where pack overshoot was deferred
- **Session Summary** — overall stats + per-vendor breakdown

---

## Input Files

**Required pair:**
- Detailed Part Sales CSV
- Received Parts Detail CSV

**Optional:**
- On Hand Min/Max Sales CSV
- On Hand Report CSV
- Open PO Listing CSV
- Suspended Items CSV
- Order Multiples / Pack Sizes CSV

The app can scan a folder and auto-detect supported report files.

---

## Output Files

- Per-vendor `.xlsx` PO import files
- Draft Review print sheets (per-vendor, landscape-formatted)
- Dead stock xlsx report
- Deferred items CSV
- Session summary CSV
- Maintenance CSV (X4 cleanup items)
- Session snapshot JSON (audit trail)

---

## Building

```
build.bat          # Release: dist/POBuilder.exe
build.bat debug    # Debug build with console window
```

The build script installs dependencies, runs the full test suite
(872 tests, must pass), and bundles via PyInstaller.

---

## Testing

```
python -m unittest discover -s tests -q
```

---

## Architecture

```
po_builder.py              Entry point (PySide6 bootstrap)
ui_qt/                     Qt UI package
  shell.py                 Main window, sidebar, tab lifecycle
  bulk_tab.py              Bulk assignment grid
  bulk_model.py            Table model + proxy filters
  review_tab.py            Review & export surface
  load_tab.py              File loading with QThread parser
  session_controller.py    Non-UI pipeline controller
  workflow_dialogs.py      12 workflow modals
  settings_dialog.py       Preferences dialog
  ...
rules/                     Ordering logic (no UI deps)
  calc.py                  Inventory position, target stock, suggested qty
  policy.py                Order policy determination
  explanation.py           Reason codes, why text
  status.py                Item status evaluation
  ...
parsers/                   CSV parsing (no UI deps)
models/                    Data structures
*_flow.py                  Workflow controllers (no UI deps)
theme.py                   Framework-independent design tokens
theme_qt.py                Qt stylesheet helpers
```

Flow modules are UI-agnostic.  All business logic is testable
without Qt.

---

## Requirements

- Windows
- Python 3.10+
- PySide6, openpyxl, Pillow (see `requirements.txt`)

---

## Persistent Files

Created beside the executable (or script directory):

| File | Purpose |
|------|---------|
| `order_rules.json` | Per-item buy rules |
| `vendor_codes.txt` | Known vendor codes |
| `vendor_policies.json` | Per-vendor shipping policies |
| `po_builder_settings.json` | UI settings and preferences |
| `order_history.json` | Export history |
| `ignored_items.txt` | Items to skip |
| `item_notes.json` | Per-item notes |
| `suspense_carry.json` | Suspense carry-forward tracking |
| `sessions/` | Export-time session snapshots |

Optional shared folder support for multi-user setups (atomic writes,
lock files, merge logic).
