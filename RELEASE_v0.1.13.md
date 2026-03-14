# PO Builder `v0.1.13` Release Notes

Date: `2026-03-14`

This release is a workflow-simplification and shipping-operations checkpoint. It makes planned-release export more intentional, improves export traceability, reduces vendor-policy setup friction, and gives operators a single recommended action at both item and vendor level.

## Highlights

- Planned-release export is now intentional at the main Review & Export screen:
  - export immediate items only
  - export planned-today items only
  - keep the existing default export path for all exportable items

- Export traceability is stronger:
  - order history now records whether an export was immediate or planned-release
  - session snapshots retain exported item scope and timing metadata
  - planned free-freight exports are easier to audit after the fact

- Vendor shipping-policy setup is lower friction:
  - a saved default vendor shipping preset can apply to vendors that do not yet have explicit saved policies
  - Vendor Manager now pre-fills unconfigured vendors from that default preset
  - item details and `why` text explain whether shipping behavior came from a saved vendor rule or the default preset

- Review and release planning are simpler to follow:
  - items now expose a single `Recommended Action`
  - vendor release-plan rows now expose a single recommended action as well
  - critical-held logic is shared consistently across shipping, review, and export

## Functional Detail

- Shipping / export:
  - planned batches can be exported globally from Review, not only through vendor-scoped plan actions
  - explicit planned/immediate exports skip unnecessary mixed-scope prompting
  - release history and session snapshots now preserve export batch type and intended order/release dates

- Vendor policy defaults:
  - saved vendor-specific policy still wins
  - user-selected default preset applies only when a vendor has no explicit saved policy
  - no vendor-specific threshold or ship-day guessing was introduced

- Recommended actions:
  - item-level examples include `Export Now`, `Review Before Export`, `Export Planned Today`, `Hold Until ...`, and `Review Critical Hold`
  - vendor-level examples include `Export Now`, `Export All Due`, `Export Planned Today`, `Wait for Threshold`, and `Review Critical Holds`

## Verification

- `python -m unittest discover -s tests -q`
- result: all `396` tests passed
- `cmd /c "build.bat < nul"`
- result: release build created `dist\POBuilder.exe`

## Notes

This is still a stepping-stone release toward `v0.2.x`. The biggest remaining roadmap areas are:

- packaged self-update replacement flow
- final bulk edit-target integrity hardening under rapid interaction
- additional dialog simplification through `Advanced` affordances where the common path still shows too many fields
