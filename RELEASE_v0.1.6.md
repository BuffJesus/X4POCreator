# PO Builder v0.1.6

Release date: 2026-03-11

## Summary

This release improves shared-folder usability and continues the recent reliability work around parsing, persistence, and bulk assignment behavior.

## Highlights

- Added a persistent ignore list so items can be excluded from future ordering runs and ignored directly from the bulk assignment screen.
- Added `Refresh Active Data` so the app can reload shared/local rules, history, vendor codes, ignore list, and related saved state from disk without restarting.
- Made the active data source more visible across the main working tabs, not just on the load screen.
- Added `Open Active Folder` for quicker inspection and support of the current shared/local data location.
- Fixed vendor assignment and bulk removal paths that could fail when inventory `QOH` was missing in source data.
- Tightened parser and persistence reliability around blank-row CSVs, stale suspense carry, order history cleanup, and shared JSON loads.

## Shared Data Workflow

- The active data source now stays visible on the bulk assignment, individual assignment, and review/export tabs.
- `Refresh Active Data` reloads the current folder’s persisted files and updates the current session where it is safe to do so.
- `Open Active Folder` opens the exact local/shared folder the app is currently using.

## Functional Detail

- New persistent `ignored_items.txt` store for ignored `line_code:item_code` keys.
- Bulk right-click menu now includes `Ignore Item`.
- Assignment prep now skips ignored items on future runs.
- Blank min/max `QOH` values no longer break vendor assignment or `Remove Not Needed`.
- Bulk UI now treats missing `QOH` as blank instead of crashing on numeric formatting.
- Shared/local JSON-backed state now refreshes more explicitly from disk when requested.

## Verification

- `python -m unittest discover -s tests -q`
