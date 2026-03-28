# PO Builder

PO Builder is a Windows desktop tool for turning X4 report exports into vendor-specific purchase order files.

It is designed for a practical workflow:
- load current X4 CSV reports
- filter out line codes or suspended customers you do not want in the run
- review suggested quantities
- assign vendors in bulk or one item at a time
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
- applies pack/order-multiple logic
- supports manual overrides for qty, pack, min, max, and vendor
- exports one `.xlsx` PO file per vendor
- generates maintenance output to help update X4 later
- saves a session snapshot for traceability at export time

## Main Workflow

1. Load the required X4 CSV files.
2. Exclude line codes you do not want in the run.
3. Optionally exclude suspended customers.
4. Use the bulk grid to review suggested quantities and assign vendors.
5. Use the individual assignment tab for leftovers.
6. Review exceptions first in `Review & Export`.
7. Use `Export Recommended` for the default export path, or choose an explicit immediate-only / planned-only export when needed.
8. Review the maintenance report and optional startup warnings CSV if needed.

## Input Files

Typical inputs:
- `Detailed Part Sales CSV` (required with `Received Parts Detail CSV`)
- `Received Parts Detail CSV` (required with `Detailed Part Sales CSV`)
- `On Hand Min/Max Sales CSV`
- `On Hand Report CSV`
- `Open PO Listing CSV`
- `Suspended Items CSV`
- `Order Multiples / Pack Sizes CSV`

Legacy compatibility:
- `Part Sales & Receipts CSV` is still supported as a fallback when the detailed pair is unavailable, but it is no longer the preferred daily workflow.

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
- `suspense_carry.json`
- `vendor_codes.txt`
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
- If a newer release is found, the app prompts the user and can open the release page
- Network failures or missing connectivity do not block startup

## UX Rule

Default-first workflow is intentional:
- no new required field unless the app cannot infer or default it safely
- no new prompt unless different user choices materially change the outcome
- advanced controls should not slow down the routine path

Versioning note:

- The current app version is read from [`VERSION`](/C:/Users/Cornelio/Desktop/POCreator/VERSION)
- Update that file when cutting a new release so the startup check compares correctly

## Repository Layout

Main application modules:
- [`po_builder.py`](/C:/Users/Cornelio/Desktop/POCreator/po_builder.py): main application entry point and app controller
- [`rules.py`](/C:/Users/Cornelio/Desktop/POCreator/rules.py): ordering logic and recommendation calculations
- [`parsers.py`](/C:/Users/Cornelio/Desktop/POCreator/parsers.py): CSV parsing and report detection
- [`storage.py`](/C:/Users/Cornelio/Desktop/POCreator/storage.py): persistence helpers
- [`export_flow.py`](/C:/Users/Cornelio/Desktop/POCreator/export_flow.py): export/session-save flow
- [`maintenance.py`](/C:/Users/Cornelio/Desktop/POCreator/maintenance.py): maintenance report generation

UI modules:
- [`ui_load.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_load.py)
- [`ui_filters.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_filters.py)
- [`ui_bulk.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_bulk.py)
- [`ui_bulk_dialogs.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_bulk_dialogs.py)
- [`ui_individual.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_individual.py)
- [`ui_review.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_review.py)
- [`ui_assignment_actions.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_assignment_actions.py)
- [`ui_vendor_manager.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_vendor_manager.py)
- [`ui_help.py`](/C:/Users/Cornelio/Desktop/POCreator/ui_help.py)

Tests:
- [`tests/`](/C:/Users/Cornelio/Desktop/POCreator/tests)

Build files:
- [`build.bat`](/C:/Users/Cornelio/Desktop/POCreator/build.bat)
- [`requirements.txt`](/C:/Users/Cornelio/Desktop/POCreator/requirements.txt)
- [`PO Builder.spec`](/C:/Users/Cornelio/Desktop/POCreator/PO%20Builder.spec)

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

Use:

```powershell
python -m unittest discover -s tests -q
```

## Building the Executable

Use:

```powershell
build.bat
```

The build script:
- installs missing dependencies
- runs the unit test suite
- bundles optional local assets if present
- creates `dist\POBuilder.exe`

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

This repo now tracks `loading.gif` and `loading.wav` directly so builds can bundle them without extra manual setup.

The app will still run and build without them, but those optional presentation features will be missing.
