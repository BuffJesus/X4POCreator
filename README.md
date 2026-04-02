# PO Builder

PO Builder is a Windows desktop tool for turning X4 report exports into vendor-specific purchase order files. Current version: **v0.3.0**

It is designed for a practical workflow:
- load current X4 CSV reports
- review the data quality summary before proceeding
- filter out line codes or suspended customers you do not want in the run
- review suggested quantities and assign vendors in bulk
- review exceptions instead of rereading every routine row
- use `Export Recommended` for the normal export path
- review a maintenance report for X4 cleanup items afterward

## What It Does

PO Builder combines several X4 report inputs to help answer:
- what likely needs to be ordered
- how much to order
- which vendor to assign
- which X4 source values may need cleanup

Key behaviors:
- uses `QOH + On PO` as inventory position
- uses sales and suspended demand signals without double-subtracting suspense from QOH
- applies pack/order-multiple logic with trigger-based reorder thresholds
- supports pack-aware replenishment for reel, spool, coil, and large-pack hardware items
- supports manual overrides for qty, pack, min, max, and vendor
- gates low-confidence items (weak recency, missing sale/receipt history) to review instead of auto-ordering
- exports one `.xlsx` PO file per vendor
- generates maintenance output to help update X4 later
- saves a session snapshot for traceability at export time
- learns from previous sessions: surfaces historical order quantities alongside current suggestions

## Main Workflow

1. Load the required X4 CSV files.
2. Review the Data Quality card on the Load tab — acknowledge any coverage gaps before proceeding.
3. Exclude line codes you do not want in the run.
4. Optionally exclude suspended customers.
5. Use the bulk grid to review suggested quantities and assign vendors.
6. Use the individual assignment tab for leftovers.
7. Review exceptions first in `Review & Export`.
8. Use `Export Recommended` for the default export path, or choose an explicit immediate-only / planned-only export when needed.
9. Review the maintenance report and optional startup warnings CSV if needed.

## Input Files

Required pair:
- `Detailed Part Sales CSV` (`DETAILEDPARTSALES.csv`)
- `Received Parts Detail CSV` (`ReceivedPartsDetail.csv`)

Optional supplemental files:
- `On Hand Min/Max Sales CSV`
- `On Hand Report CSV`
- `Open PO Listing CSV`
- `Suspended Items CSV`
- `Order Multiples / Pack Sizes CSV`

The app can scan a folder and auto-detect supported report files, or you can browse to them manually.

## Output Files

Main outputs:
- one `.xlsx` PO import file per vendor
- optional startup warnings CSV
- optional maintenance CSV
- session snapshot JSON

## Vendor Management

The app includes a vendor manager so users can:
- add vendor codes
- rename vendor codes
- remove vendor codes from the saved list

Vendor codes are persisted locally in `vendor_codes.txt`.

## Local Persistent Files

These files are created and used locally beside the script or beside the built `.exe`:
- `duplicate_whitelist.txt`
- `order_history.json`
- `order_rules.json`
- `po_builder_settings.json`
- `suspense_carry.json`
- `vendor_codes.txt`
- `vendor_policies.json`
- `sessions/`

These are operational/user data files and should generally stay out of public version control.

## Optional Shared Data Folder

The app can be pointed at a shared OneDrive or network folder for shared operational data.

- Configure it from the `Load Files` tab with `Set Shared Folder...`
- Use `Use Local Data` to switch back to the default local storage beside the app
- The active data source is shown in the UI so users can confirm whether they are on local or shared data

Shared-folder safeguards:

- JSON writes are atomic to reduce corruption risk
- lock files are used during writes to reduce simultaneous-save collisions
- shared rule/vendor/whitelist saves merge against the latest on-disk version where possible
- session snapshots get unique filenames so multiple users can save into the same shared `sessions/` folder

Practical guidance:

- A shared network folder is more predictable than OneDrive for active multi-user editing
- `sessions/` is safe to share because snapshots are append-only
- `suspense_carry.json` is shared too, but it is still the most concurrency-sensitive file

## Startup Update Check

The app can check GitHub for a newer release when it starts.

- The startup check is controlled from the `Load Files` tab with `Check GitHub for new releases on startup`
- It uses the latest GitHub release for `BuffJesus/X4POCreator`
- If a newer release is found, the app prompts the user and can download and install the update automatically
- When the user accepts: the new executable is downloaded to a staging location, a small updater script is written, the app exits, the updater replaces the old executable, and the new version relaunches
- Network failures or missing connectivity do not block startup

## UX Rule

Default-first workflow is intentional:
- no new required field unless the app cannot infer or default it safely
- no new prompt unless different user choices materially change the outcome
- advanced controls should not slow down the routine path

Versioning note:

- The current app version is read from [`VERSION`](/C:/Users/Cornelio/Desktop/POCreator/VERSION)
- Update that file and `app_version.py` when cutting a new release so the startup check compares correctly

## Repository Layout

Entry point:
- [`po_builder.py`](/C:/Users/Cornelio/Desktop/POCreator/po_builder.py) — app controller, tab layout, delegates to flow and UI modules

Core logic (no UI dependencies):
- [`rules.py`](/C:/Users/Cornelio/Desktop/POCreator/rules.py) — ordering logic, quantity calculations, pack/trigger evaluation, recency confidence, policy graduation
- [`parsers.py`](/C:/Users/Cornelio/Desktop/POCreator/parsers.py) — CSV parsing, X4 report auto-detection, header normalization
- [`models.py`](/C:/Users/Cornelio/Desktop/POCreator/models.py) — data classes: `ItemKey`, `SourceItemState`, `SessionItemState`, `AppSessionState`, `SessionSnapshot`
- [`storage.py`](/C:/Users/Cornelio/Desktop/POCreator/storage.py) — atomic JSON/text file I/O, session snapshot loading, order history extraction
- [`maintenance.py`](/C:/Users/Cornelio/Desktop/POCreator/maintenance.py) — maintenance report generation

Flow modules (discrete, testable workflow controllers):
- [`load_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/load_flow.py) — CSV loading, parse caching, data quality summary
- [`session_state_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/session_state_flow.py) — session initialization, data merging, bulk edit history
- [`reorder_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/reorder_flow.py) — reorder trigger evaluation, suggestion context, cycle normalization
- [`assignment_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/assignment_flow.py) — vendor/qty assignment, session preparation, historical order qty
- [`shipping_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/shipping_flow.py) — vendor release/hold policies, release decision annotation
- [`export_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/export_flow.py) — export grouping, vendor scoping, session snapshot save
- [`item_workflow.py`](/C:/Users/Cornelio/Desktop/POCreator/item_workflow.py) — per-item state synchronization between session and filtered views
- [`review_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/review_flow.py) — review tab state and exception routing
- [`performance_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/performance_flow.py) — performance profile and sales health signals
- [`sales_history_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/sales_history_flow.py) — detailed sales history processing and transaction shape metrics
- [`bulk_edit_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/bulk_edit_flow.py) — in-grid cell edit mutations
- [`bulk_remove_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/bulk_remove_flow.py) — row removal with protection checks and undo support
- [`bulk_context_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/bulk_context_flow.py) — bulk context menu actions (ignore, dismiss duplicate, resolve review)
- [`bulk_sheet_actions_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/bulk_sheet_actions_flow.py) — bulk edit/fill/clear/sort/remove actions, undo/redo stack
- [`persistent_state_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/persistent_state_flow.py) — load/save `order_rules.json`, `vendor_codes.txt`
- [`data_folder_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/data_folder_flow.py) — shared/local data folder switching and refresh
- [`app_runtime_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/app_runtime_flow.py) — app startup orchestration and runtime helpers
- [`loading_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/loading_flow.py) — loading animation and progress UI
- [`maintenance_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/maintenance_flow.py) — maintenance report UI flow
- [`update_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/update_flow.py) — GitHub release check, executable download, updater script handoff

UI modules:
- [`ui_load.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_load.py)
- [`ui_filters.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_filters.py)
- [`ui_bulk.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_bulk.py)
- [`bulk_sheet.py`](/C:/Users/Cornelio/Desktop/POCreator/bulk_sheet.py)
- [`ui_bulk_dialogs.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_bulk_dialogs.py)
- [`ui_individual.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_individual.py)
- [`ui_review.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_review.py)
- [`ui_assignment_actions.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_assignment_actions.py)
- [`ui_vendor_manager.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_vendor_manager.py)
- [`ui_help.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_help.py)
- [`ui_state_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_state_flow.py)
- [`ui_grid_edit.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_grid_edit.py)
- [`ui_scroll.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_scroll.py)

Support:
- [`app_version.py`](/C:/Users/Cornelio/Desktop/POCreator/app_version.py)
- [`debug_log.py`](/C:/Users/Cornelio/Desktop/POCreator/debug_log.py)

Tests:
- [`tests/`](/C:/Users/Cornelio/Desktop/POCreator/tests)

Build files:
- [`build.bat`](/C:/Users/Cornelio/Desktop/POCreator/build.bat)
- [`requirements.txt`](/C:/Users/Cornelio/Desktop/POCreator/requirements.txt)
- [`PO_Builder.spec`](/C:/Users/Cornelio/Desktop/POCreator/PO_Builder.spec)

## Running From Source

Requirements:
- Windows
- Python 3.14

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the app:

```powershell
python po_builder.py
```

## Running Tests

```powershell
python -m unittest discover -s tests -q
```

## Building the Executable

```powershell
build.bat
```

The build script:
- installs missing dependencies
- runs the unit test suite
- bundles optional local assets if present
- creates `dist\POBuilder.exe`

For a debug build with a visible console window:

```powershell
build.bat debug
```

## Notes About Public Repos

This repository is intentionally set up to keep private work data out of Git.

Ignored items include:
- `CSVs/`
- `.json` data files
- generated sessions
- build output
- local media/assets
- virtualenv and IDE folders

If you clone this repo elsewhere, you may need to supply local assets like:
- `loading.gif`
- `loading.wav`
- `icon.ico`

This repo tracks `loading.gif` and `loading.wav` directly so builds can bundle them without extra manual setup. The app will still run and build without them, but those optional presentation features will be missing.
