# PO Builder `v0.1.16` Release Notes

Date: `2026-03-15`

This release is a bulk-history canonicalization and restore-efficiency checkpoint. It makes undo/redo history smaller, more consistent across coalesced and mixed-format states, and cheaper to replay when a restore is effectively a no-op.

## Highlights

- Bulk history is now more canonical:
  - row-scoped item snapshots are compacted to field patches
  - keyed side structures such as inventory, QOH adjustments, and order rules are compacted to per-entry field patches
  - mixed full-state and patch-state history pairs now normalize to the same canonical net-change form

- Bulk undo coalescing is smarter:
  - top-of-stack coalescing now uses semantic state equivalence instead of raw dict equality
  - merged entries are recompressed across the full coalesced span
  - coalesced edits that return to their original state now remove themselves from undo history entirely

- Bulk restore does less unnecessary work:
  - empty and no-op patch sections are treated as absent
  - no-op row restores, mapping restores, and full-state restores now return without UI churn
  - compact mapping patches can recreate missing keyed entries and remove empty ones safely

## Functional Detail

- History format and compaction:
  - row-scoped history now keeps only changed rows, then only changed fields within those rows
  - partial keyed history now keeps only changed keys, then only changed fields within those keyed dict entries
  - undo/redo inverse entry creation reuses the same canonical compaction path

- Coalescing behavior:
  - consecutive matching bulk edits coalesce even when one side is stored as full rows/entries and the other side is stored as patches
  - net-no-op coalesced sequences are dropped from the undo stack instead of leaving dead history entries

- Restore-path efficiency and robustness:
  - restore skips row cache invalidation, summary adjustment, and downstream bulk refresh work when a patch does not materially change the current object
  - omitted canonicalized state no longer falls through to empty-list replacement
  - compact mapping patches can now rebuild missing dict entries from their field data when needed

## Verification

- `python -m unittest discover -s tests -q`
- result: all `530` tests passed
- `cmd /c "build.bat < nul"`
- result: release build created `dist\POBuilder.exe`

## Notes

This remains a stepping-stone release toward `v0.2.x`. The next likely roadmap areas are:

- generating canonical compact row/key history directly at capture time instead of snapshot-then-compact
- broader undo-boundary policy beyond the current exact semantic coalescing model
- packaged self-update replacement flow
