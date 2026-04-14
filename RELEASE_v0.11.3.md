# PO Builder v0.11.3 - Suspect ORG/FLU Inventory Count Review

Patch release focused on a Fluidseal-style edge case where `ORG-` and
`FLU-` inventory counts can be overstated in X4 and suppress reorder
review.

---

## What Changed

- Added a narrow `ORG-` / `FLU-` safeguard in the assignment flow.
- When an item has recent demand, no real min/max anchor, and reported
  stock is the only thing suppressing reorder, it is now flagged as a
  manual review candidate instead of quietly disappearing behind a zero
  suggestion.
- Added a dedicated review reason explaining that the reported count may
  be overstated.
- Protected these suspect-count items from the `Remove Not Needed` bulk
  cleanup flow.

---

## Why

Some `ORG-` / `FLU-` items have active or recent demand, but unreliable
QOH values can make them look fully covered. Before this patch, those
rows could be treated as satisfied and never get surfaced for manual
check.

This release does not globally loosen reorder logic. It only promotes
the suspicious subset into review so the operator can validate the shelf
count before export.

---

## Dataset Validation

Validated against the Fluidseal dataset from `2026-04-14`.

Examples now flagged for review:

- `FLU-/25002000375B`
- `FLU-/BAK-10-FH`
- `FLU-/D-01750/4615`
- `ORG-/7012`
- `ORG-/7108`
- `ORG-/9914`
- `ORG-/NB115`

---

## Verification

- Added unit coverage for the suspect-count heuristic.
- Added unit coverage to ensure `Remove Not Needed` does not auto-remove
  flagged suspect-count items.
- Verified with:

```powershell
python -m unittest tests.test_assignment_flow tests.test_not_needed
```
