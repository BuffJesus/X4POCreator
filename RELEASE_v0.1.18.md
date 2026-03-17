## PO Builder `v0.1.18`

Release date: 2026-03-16

This release continues the detailed-report transition with safer live parsing, clearer workflow defaults, and better visibility into where active reorder suggestions are coming from.

### Highlights

- The load workflow now hides the legacy combined `Part Sales & Receipts` input by default.
- Folder scan now respects that policy:
  - if the detailed pair is present, the legacy combined report stays hidden
  - if the combined report is the only sales source found, the compatibility input is revealed automatically
- Live `DETAILED PART SALES.csv` parsing is safer:
  - valid three-character product-group prefixes still parse normally
  - whitespace around the separator is tolerated
  - ambiguous oddball tokens no longer manufacture bad line codes and instead flow into the existing unresolved diagnostics path

### Detailed-report workflow improvements

- The app now tracks and shows the source of the active suggestion:
  - `X4 12-month sales`
  - `Detailed sales fallback`
  - `No suggestion`
- Suggestion source is now visible in:
  - Individual assignment details
  - Bulk item details
- Review now makes that signal operational too:
  - active suggestion source can be filtered directly
  - review summary now shows detailed-fallback vs X4-sourced suggestion counts
- Suggestion source also survives assignment/review handoff and session recalculation, so the active suggestion path is explainable instead of implicit.

### Validation

- `python -m unittest discover -s tests -q`
- Result: `593` tests passed
