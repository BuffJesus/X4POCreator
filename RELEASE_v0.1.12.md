# PO Builder `v0.1.12` Release Notes

Date: `2026-03-14`

This release is a substantial workflow and algorithm checkpoint on the road to `v0.2.x`. It tightens reorder safety for low-confidence items, expands cadence-aware hardware behavior, and turns the shipping/release model into a more usable day-to-day operational workflow.

## Highlights

- Missing-recency items are now safer and more explainable:
  - items with no `last_sale` / `last_receipt` no longer ride through with an implicit default order qty
  - low-confidence recency is now split into actionable subtypes such as stale, sparse/new, recent-local-PO-protected, explicit-min-rule-protected, and other protected cases
  - Review & Export can filter directly by those recency subtypes

- Cadence-aware ordering is materially stronger:
  - `minimum_cover_days` and `minimum_cover_cycles` are active reorder triggers, not just stored rule fields
  - active weekly-order hardware can now infer a conservative two-cycle trigger floor even for smaller pack sizes
  - inferred cadence floors are labeled clearly in explanations and item details

- Shipping-aware release workflow is now more operational:
  - vendor policies persist and can be edited in Vendor Manager
  - release planning uses order value plus current date to compute threshold progress, next free-ship day, and planned export timing
  - held items now carry explicit `target order date` / `target release date`
  - export behavior respects immediate vs planned vs held items and explains what was held back

- Workflow friction is lower:
  - mixed export behavior can default automatically instead of prompting every time
  - Review & Export can default to `Exceptions Only`
  - the Release Plan dialog can drive review filters and direct vendor-scope exports
  - vendor shipping-policy presets are now available for common setups

## Functional Detail

- Reorder / confidence:
  - missing-recency review items stay visible but default to zero qty unless protected by a stronger explicit rule
  - recent local PO history is now treated as meaningful protective evidence for review bucketing
  - explicit critical min rules are distinguished from broader rule-protected cases

- Hardware / cadence:
  - trigger logic now supports saved or inferred pack floors, cover days, and cover cycles
  - high-velocity weekly hardware can trigger replenishment based on inferred two-cycle cover instead of only current max or large-pack heuristics

- Shipping / review / export:
  - Review shows release state and recency subtype more clearly
  - planned free-freight exports can be included intentionally
  - held items remain visible with concrete timing targets instead of only abstract hold reasons

## Verification

- `python -m unittest discover -s tests -q`
- result: all `361` tests passed
- `cmd /c build.bat`
- result: release build created `dist\POBuilder.exe`

## Notes

This is still a stepping-stone release rather than a final `v0.2.x` milestone. The biggest remaining roadmap areas are:

- broader vendor-policy defaulting beyond explicit presets
- stronger vendor-group shipping consolidation and urgent override workflow
- packaged self-update replacement flow
- final bulk edit integrity hardening under rapid interaction
