# PO Builder `v0.1.14` Release Notes

Date: `2026-03-14`

This release is a bulk-editor integrity checkpoint. It tightens row targeting under filtered and sorted views, makes in-sheet navigation behave as a safer edit boundary, and brings bulk removal recovery into the same history model as other bulk actions.

## Highlights

- Bulk row targeting is more reliable:
  - the sheet now uses stable row identity derived from the item key instead of depending on visible position
  - filtered, sorted, and rebuilt bulk views keep edits, context actions, and removals pointed at the intended item
  - vendor assignment bulk actions now use the same stable row-id model

- In-sheet editing is safer under movement:
  - queued cell edits now drain before navigation or selection changes move focus
  - arrow-key, tab, and in-sheet selection transitions are less likely to let a previous cell commit after focus has already moved

- Bulk removal recovery is more coherent:
  - selected-row removals and remove-not-needed removals now create real bulk history entries
  - `Undo Last Remove` now respects the actual bulk undo stack first
  - stale legacy remove payloads no longer override newer bulk actions silently

## Functional Detail

- Bulk row identity:
  - stable row ids are now carried through bulk edit, refresh, context-menu actions, details, ignore, duplicate dismiss, and buy-rule entry points
  - right-click and selection-driven bulk actions now share one explicit target-precedence model

- Navigation and edit boundaries:
  - pending edits are flushed before moving the active cell, extending selection, or switching current row/column focus inside the sheet
  - keyboard navigation now reuses more shared cell-targeting paths instead of splitting movement behavior across multiple flows

- Removal history:
  - bulk removals now route through a shared removal helper
  - removal actions participate in the same bulk undo/redo capture path as other bulk mutations
  - the dedicated remove-undo action now defers to structured history when available

## Verification

- `python -m unittest discover -s tests -q`
- result: all `430` tests passed
- `cmd /c "build.bat < nul"`
- result: release build created `dist\POBuilder.exe`

## Notes

This is still a stepping-stone release toward `v0.2.x`. The biggest remaining roadmap areas are:

- final rapid-click / previous-cell bulk edit bleed under real timing pressure
- broader bulk history boundary tightening for complex multi-step edit sequences
- packaged self-update replacement flow
