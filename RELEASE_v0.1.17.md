## PO Builder `v0.1.17`

Release date: 2026-03-16

This release tightens the Review & Export workflow and continues the transition away from the old combined sales/receipts report.

### Highlights

- Review & Export now defaults to `All Items` instead of `Exceptions Only`.
- Review repaints no longer reset the user back to the exception-only focus.
- The detailed sales + receiving pair is now more explicitly the primary workflow:
  - the legacy combined `Part Sales & Receipts` report remains supported only as compatibility fallback
  - using the legacy combined source now raises an explicit compatibility warning
  - load status now shows whether the run used the detailed pair or the legacy combined source

### Additional detailed-report work included

- High-confidence receipt-history pack sizes can already fill missing pack-size data conservatively.
- High-confidence receipt-pack mismatches now surface as review exceptions instead of staying hidden in item details.
- Receipt-derived vendor and pack evidence continues to be surfaced in assignment and detail views without silently overriding saved/X4 data.

### Validation

- `python -m unittest discover -s tests -q`
- Result: `577` tests passed
