## PO Builder `v0.1.19`

Release date: 2026-03-17

This release tightens the remaining detailed-sales fallback policy and substantially deepens shipping-planning visibility, date handling, and review signals.

### Highlights

- Receipt-heavy items no longer let detailed-sales fallback quietly strengthen the active suggestion beyond what the sales evidence supports.
- Shipping planning now carries explicit cost-confidence, threshold-progress, and planned-date signals through item details, Review, and vendor release planning.
- Release decisions now include a more precise decision-detail family so planned-release vs threshold vs urgent-release paths are explainable instead of lumped together.

### Reorder policy updates

- Detailed-sales fallback is now suppressed for items whose loaded receipt-vs-sales balance is clearly `receipt_heavy`.
- That keeps the item review-first:
  - active suggestion falls back to `No suggestion`
  - detailed suggestion still remains visible for comparison
  - the item surfaces through the existing detailed-only / receipt-heavy review paths instead of being silently strengthened

### Shipping planning improvements

- Shipping value handling now explicitly classifies the item cost source:
  - `Inventory repl_cost`
  - `Missing inventory repl_cost`
  - `Zero inventory repl_cost`
  - `Invalid inventory repl_cost`
- Vendor-level planning now carries:
  - current estimated vendor total
  - threshold shortfall
  - threshold progress percent
  - value coverage confidence
  - known-percent coverage
  - missing / zero / invalid cost counts
- Business-day-aware planning dates are now centralized and covered:
  - next preferred free-freight weekday
  - planned export / order date
  - release one business day early when policy requires it
  - Friday / Monday edge cases
- Vendor-level recommendations now flag value-coverage risk directly instead of treating those plans as clean export-ready cases.

### Review and item-detail workflow

- Review & Export now shows shipping planning columns directly in the main grid:
  - recommended action
  - release decision
  - release detail
  - threshold shortfall
  - next free-ship date
  - planned export date
- Vendor Release Plan now also shows:
  - value coverage confidence
  - known percent
  - cost issue counts
  - release detail
- Bulk item details now include:
  - release detail
  - estimated unit cost / value
  - estimated value confidence
  - vendor value coverage diagnostics

### Validation

- `python -m unittest discover -s tests -q`
- `cmd /c "build.bat < nul"`
