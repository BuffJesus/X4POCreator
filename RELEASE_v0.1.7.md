# PO Builder v0.1.7

Release date: 2026-03-11

## Summary

This release tightens the shared-data workflow, finishes the first pass of the persistent ignore-list feature, and fixes several bulk-assignment UI issues discovered during real use.

## Highlights

- Added `Refresh Active Data` so the app can reload shared/local saved data into the running session without restarting.
- Added a persistent ignore list and a working `Ignore Item` action in the bulk editor right-click menu.
- Made the active shared/local data source visible on the main working tabs and added `Open Active Folder`.
- Fixed bulk-assignment and bulk-removal failures caused by missing `QOH` values.
- Improved the bulk assignment header layout so maximized windows use horizontal space more effectively.

## Shared Data Workflow

- `Refresh Active Data` reloads rules, history, vendor codes, duplicate whitelist, ignored items, and related saved state from the active folder on disk.
- The current data source is now shown on Load, Assign Vendors, Individual, and Review & Export screens.
- `Open Active Folder` opens the exact local/shared data directory the app is using.

## Ignore List

- Ignored items are stored persistently as `line_code:item_code` keys.
- Assignment preparation skips ignored items on future runs.
- Bulk right-click now includes `Ignore Item`, and that action removes the item from the current session immediately.

## Reliability Fixes

- Missing inventory `QOH` values no longer break vendor assignment, bulk row rendering, or `Remove Not Needed`.
- Bulk-sheet context menu now shows the actual ignore action in the menu that is displayed at runtime.
- Recent parser and persistence hardening remains in place for blank-row CSVs, stale suspense carry cleanup, and history cleanup.

## Verification

- `python -m unittest discover -s tests -q`
