POCreator session handoff for Saturday, March 14, 2026.

Current version
- App version is now `0.1.11`.
- Canonical version source remains internal:
  [`app_version.py`](C:\Users\Cornelio\Desktop\POCreator\app_version.py)

Build status
- Release build completed successfully on Friday, March 13, 2026.
- Output executable:
  [`dist\POBuilder.exe`](C:\Users\Cornelio\Desktop\POCreator\dist\POBuilder.exe)
- Build command:
  `cmd /c build.bat`

Verification baseline
- `python -m unittest discover -s tests -q`
- Result after this checkpoint: `294` tests passed

Major work completed in this stretch
- Roadmap reconciliation:
  - [`ROADMAP_v0.2.5.md`](C:\Users\Cornelio\Desktop\POCreator\ROADMAP_v0.2.5.md) now reflects actual completed work and phased execution order.
- Reorder-core refactor:
  - [`rules.py`](C:\Users\Cornelio\Desktop\POCreator\rules.py) now separates:
    - inventory position
    - target stock
    - reorder-needed gate
    - effective reorder floor
- Trigger-style buy-rule fields added and threaded through UI/details:
  - `reorder_trigger_qty`
  - `reorder_trigger_pct`
  - `minimum_packs_on_hand`
  - `acceptable_overstock_qty`
  - `acceptable_overstock_pct`
- Buy-rule UI and details updated:
  - [`ui_bulk_dialogs.py`](C:\Users\Cornelio\Desktop\POCreator\ui_bulk_dialogs.py)
- Added `pack_trigger` explicit policy support.
- Added `large_pack_review` inferred review path for stale/risky non-reel large-pack items.
- Added hardware description detection using inventory/QOH descriptions for:
  - bolt
  - nut
  - washer
  - screw
  - clamp
  - fitting
  - fastener
- Added conservative active-hardware automation:
  - obvious active hardware pack/max mismatches infer `pack_trigger`
  - obvious active hardware can infer `minimum_packs_on_hand = 2`
  - stale hardware still routes to `large_pack_review`

Important current behavior
- Reels:
  - true reel-like items still infer `reel_review`
- Stale non-reel large packs:
  - can infer `large_pack_review`
- Active hardware:
  - can infer `pack_trigger`
  - can infer a two-pack floor when the mismatch is extreme and the recency/performance signals are active enough
- Trigger thresholds can now come from:
  - fixed trigger qty
  - trigger percent of pack
  - minimum packs on hand

Most important files touched
- [`rules.py`](C:\Users\Cornelio\Desktop\POCreator\rules.py)
- [`ui_bulk_dialogs.py`](C:\Users\Cornelio\Desktop\POCreator\ui_bulk_dialogs.py)
- [`tests/test_rules.py`](C:\Users\Cornelio\Desktop\POCreator\tests\test_rules.py)
- [`tests/test_ui_bulk_dialogs.py`](C:\Users\Cornelio\Desktop\POCreator\tests\test_ui_bulk_dialogs.py)
- [`tests/test_po_builder.py`](C:\Users\Cornelio\Desktop\POCreator\tests\test_po_builder.py)
- [`ROADMAP_v0.2.5.md`](C:\Users\Cornelio\Desktop\POCreator\ROADMAP_v0.2.5.md)

Best next steps
1. Improve explainability for inferred cadence coverage.
   - Surface `minimum_packs_on_hand_source` in item details and review text.
   - Make it obvious when the app inferred a two-pack floor versus when a human set it.
2. Decide whether inferred two-pack hardware floors should also persist into saved rules after explicit confirmation.
3. Add more real-world hardware-term coverage if your QOH descriptions show common patterns the current term list misses.
4. Continue `v0.2.5` roadmap work on:
   - review/removal coherence with the new effective reorder floor
   - shipping-aware release timing later, after the ordering core settles

Risks / open questions
- The new hardware heuristic is intentionally conservative, but it is still heuristic.
- The current active-hardware two-pack inference is not yet surfaced clearly enough in the UI for user trust.
- Description-based detection may need expansion after reviewing more live QOH descriptions.

Notes
- If tests dirty [`debug_trace.log`](C:\Users\Cornelio\Desktop\POCreator\debug_trace.log), restore it non-destructively if needed.
- Current release note for this checkpoint:
  [`RELEASE_v0.1.11.md`](C:\Users\Cornelio\Desktop\POCreator\RELEASE_v0.1.11.md)
