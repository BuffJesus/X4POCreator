# Release v0.1.1

Tag: `v0.1.1`

Release title: `PO Builder v0.1.1`

## Summary

This patch release fixes recommendation recalculation and review persistence issues, while preserving the duplicate-row protection needed for X4 sales imports.

## Highlights

- fixed reorder-cycle changes so suggested qty, final qty, status, and explanation recalculate immediately
- fixed review-tab pack-size edits so they persist into saved order rules
- refined part-sales deduplication to drop only exact duplicate CSV rows, preventing repeated X4 rows from inflating demand
- added regression coverage for the recalculation, persistence, and parsing fixes

## Notes

- `VERSION` is now `0.1.1`
- recommended git tag: `v0.1.1`
- recommended release target: the commit that contains the fixes for review pack persistence, reorder-cycle recalculation, and exact-row sales deduplication

## Suggested Git Commands

```powershell
git add VERSION RELEASE_v0.1.1.md po_builder.py parsers.py tests\test_po_builder.py tests\test_parsers.py
git commit -m "Prepare v0.1.1 release"
git tag -a v0.1.1 -m "PO Builder v0.1.1"
git push origin master
git push origin v0.1.1
```
