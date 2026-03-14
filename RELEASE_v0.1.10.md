# PO Builder v0.1.10

Release date: 2026-03-13

## Summary

This release is the current finalized checkpoint on the road to `v0.2.x`. It focuses on bulk-editor correctness and large-session performance, especially for users working inside very large active sessions and making rapid edits across different cells, filters, and workflow stages.

## Highlights

- hardened bulk-sheet edit targeting so rapid consecutive edits no longer apply to the previously edited cell
- flushed pending bulk edits before context actions, dialogs, tab handoffs, filtering, sorting, paste, and review transitions
- cleared stale right-click context on selection changes and bulk-sheet rebuilds
- improved bulk-editor performance for large sessions:
  - cached bulk summary counts instead of rescanning the whole active session after common edits
  - kept more filtered and sorted edits incremental when the changed column cannot affect membership or ordering
- kept behavior explainable while strengthening regression coverage around bulk-sheet correctness and workflow transitions
- renamed the release executable to `POBuilder.exe`

## Functional Detail

Bulk-editor hardening in this release covers:

- vendor -> pack-size and similar cross-row consecutive edits
- pending edit drain before Ignore / Remove / Fill / Clear / dialog actions
- safe handoff from bulk editing into review and assignment workflows
- safer filtered/sorted refresh behavior during edits
- clipboard paste using the same pending-edit and incremental-refresh rules as other bulk edit paths

Large-session performance work in this release covers:

- cached bulk summary counts
- incremental summary updates for common per-item edits
- more selective fallback to full bulk rebuilds

## Verification

- `python -m unittest discover -s tests -q`
- result: `257` tests passed
- `cmd /c build.bat`
- result: build succeeded and created `dist\POBuilder.exe`

## Notes

This is still a stepping-stone release rather than the final `v0.2.0` milestone. The biggest remaining performance work is reducing full active-session rebuild cost when a rebuild truly is required on very large datasets.
