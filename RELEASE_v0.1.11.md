# PO Builder v0.1.11

Release date: 2026-03-13

## Summary

This release continues the road to `v0.2.x` with the first real pack-trigger and cadence-aware ordering behavior. It improves how PO Builder handles reels, bag/box hardware, and low-max large-pack items while keeping the automation conservative and explainable.

## Highlights

- Added explicit trigger-style buy-rule fields:
  - `reorder_trigger_qty`
  - `reorder_trigger_pct`
  - `minimum_packs_on_hand`
  - `acceptable_overstock_qty`
  - `acceptable_overstock_pct`
- Refactored the reorder core into clearer stages so the app now tracks:
  - inventory position
  - target stock
  - reorder-needed gate
  - effective reorder floor
- Added `pack_trigger` policy support for full-pack replenishment when inventory crosses a configured trigger threshold.
- Added `large_pack_review` for stale/risky non-reel large-pack items so they route to review instead of ordinary pack automation.
- Added hardware-pack description detection from inventory/QOH descriptions for terms like:
  - bolt
  - nut
  - washer
  - screw
  - clamp
  - fitting
  - fastener
- Added conservative hardware automation:
  - active hardware pack/max mismatches now infer `pack_trigger`
  - active obvious hardware can infer a two-pack floor when a one-pack steady state is unlikely to be safe
  - stale hardware can still fall to `large_pack_review`
- Surfaced the new trigger and coverage fields in the buy-rule editor, item details, and buy-rule summary text.

## Algorithm Progress

- Trigger thresholds can now come from:
  - explicit quantity
  - percentage of replenishment unit
  - minimum packs on hand
- When the trigger floor exceeds the normal target stock, the app now uses that higher floor for raw-need calculation.
- This allows cases like:
  - hose ordered by reel with an early trigger below the reel max
  - bag-of-100 hardware where two packs on hand are safer than a single-pack steady state

## Concrete Scenarios Now Covered

- `300 ft` hose with `max 93` and `trigger 60`
- bag of `100` hardware with `max 20`
- active hardware terms inferring pack-trigger handling automatically
- stale non-reel large-pack items remaining review-only

## Verification

- `python -m unittest discover -s tests -q`
- Full suite result: `294` tests passed
- `cmd /c build.bat`
- Release artifact: `dist\POBuilder.exe`

## Notes

This is still a stepping-stone release, not a `v0.2.x` milestone release. The current algorithm work is intentionally conservative:

- explicit rule fields and obvious hardware heuristics can now reduce manual cleanup
- truly ambiguous or stale large-pack cases still stay review-oriented
- vendor shipping and release-timing logic remain future work on the `v0.2.5` roadmap
