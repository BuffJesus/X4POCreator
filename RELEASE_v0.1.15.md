# PO Builder `v0.1.15` Release Notes

Date: `2026-03-15`

This release is a bulk-editor performance and history-efficiency checkpoint. It reduces repeated rebuild work in the bulk assignment view, makes active filter paths more cache-aware for large sessions, and lightens the undo snapshot path for common bulk edits.

## Highlights

- Bulk filtering is materially faster on repeated and narrowed views:
  - stable filter dimensions now use cached bucket intersections instead of repeated full-list matcher scans
  - repeated `apply_bulk_filter()` calls can reuse both the visible item set and the already-built visible row payload
  - repeated full-session bulk populates now reuse cached row payloads when session state is unchanged

- Bulk view hot paths now do less unnecessary work:
  - stable bulk row ids and filtered-item lookup are cached
  - rendered row values are cached and pruned to the active session
  - full-sheet redraws and combobox value writes are skipped when nothing visible changed

- Bulk undo snapshots are lighter:
  - common edit paths now capture only the state they actually mutate
  - runtime-only item cache fields and legacy removal payload deep-copy pressure were removed from normal history capture
  - bulk undo/redo now preserves selective capture intent across round trips

## Functional Detail

- Filter and rebuild performance:
  - line code, source, assignment status, item status, performance, sales health, and attention filters now participate in cache-backed candidate narrowing
  - bucket-only filter combinations can bypass the matcher entirely
  - unchanged filter state can reuse cached visible rows without rebuilding row ids or rendered payloads

- Render and lookup performance:
  - row-id generation and row-id resolution now avoid repeated JSON serialization and parsing on common paths
  - filtered-item membership changes now flow through shared cache-aware helpers
  - full-session metadata such as summary counts and line-code lists are maintained at the filtered-item replacement boundary

- History efficiency:
  - bulk edit, fill, clear, paste, vendor assignment, and removal flows now use selective history capture specs
  - partial undo snapshots preserve omitted app state instead of overwriting it with defaults
  - persistence-baseline fields are no longer mixed into bulk undo state

## Verification

- `python -m unittest discover -s tests -q`
- result: all `492` tests passed
- `cmd /c "build.bat < nul"`
- result: release build created `dist\POBuilder.exe`

## Notes

This remains a stepping-stone release toward `v0.2.x`. The next likely roadmap areas are:

- deeper undo-state reduction through per-row or per-key deltas instead of selective whole-collection snapshots
- broader cache-lifecycle design beyond the current safe session/edit boundaries
- packaged self-update replacement flow
