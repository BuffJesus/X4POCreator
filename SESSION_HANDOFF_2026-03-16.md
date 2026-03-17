POCreator session handoff for Monday, March 16, 2026.

Current version
- App version is now `0.1.18`.
- Canonical version sources:
  [app_version.py](C:/Users/Cornelio/Desktop/POCreator/app_version.py)
  [VERSION](C:/Users/Cornelio/Desktop/POCreator/VERSION)

Build status
- Release build completed successfully on Monday, March 16, 2026.
- Output executable:
  [dist/POBuilder.exe](C:/Users/Cornelio/Desktop/POCreator/dist/POBuilder.exe)
- Executable timestamp:
  `2026-03-16 9:06:37 PM`
- Build command:
  `cmd /c "build.bat < nul"`

Verification baseline
- `python -m unittest discover -s tests -q`
- Result after this checkpoint: `593` tests passed

Release notes for current build
- [RELEASE_v0.1.18.md](C:/Users/Cornelio/Desktop/POCreator/RELEASE_v0.1.18.md)

Major work completed in this stretch
- The detailed sales + receiving pair is now the real primary workflow rather than a sidecar.
- Live detailed-file parsing was corrected against the actual X4 exports:
  - [parsers.py](C:/Users/Cornelio/Desktop/POCreator/parsers.py)
  - [load_flow.py](C:/Users/Cornelio/Desktop/POCreator/load_flow.py)
- Real-file handling now includes:
  - parsing live `DETAILED PART SALES.csv`
  - parsing live `ReceivedPartsDetail.csv`
  - explicit diagnostics for unresolved detailed-sales rows
  - explicit diagnostics for suspicious parsed line-code conflicts
  - safe auto-correction when a conflicting parsed line code has one uniquely supported known candidate
  - hardened combined-token parsing so only 3-character X4-style PG prefixes are trusted
  - ambiguous oddball tokens like `K-D-1708` now stay unresolved instead of manufacturing bad line codes
- Load workflow simplification moved forward materially:
  - legacy combined `Part Sales & Receipts` is compatibility-only
  - [ui_load.py](C:/Users/Cornelio/Desktop/POCreator/ui_load.py) now hides legacy input by default behind an explicit toggle
  - [po_builder.py](C:/Users/Cornelio/Desktop/POCreator/po_builder.py) folder scan now respects that policy:
    - if the detailed pair is present, legacy sales stays hidden
    - if combined sales is the only sales source found, legacy compatibility input is auto-revealed
- Receiving-detail evidence is now integrated broadly:
  - receipt-first vendor defaulting
  - explicit receipt vendor confidence / ambiguity
  - receipt cadence / lot-size stats in item details
  - receipt-derived potential vendor and potential pack evidence
  - receipt-pack fallback only for appropriate families like hoses / hardware packs
  - receipt-pack mismatch review surfacing
  - receipt-vs-sales balance guardrails so overstock-heavy receiving does not quietly legitimize demand
- Detailed sales evidence is now integrated broadly:
  - detailed transaction-shape stats and classification
  - lumpy-demand review surfacing
  - detailed fallback min/max suggestions
  - detailed-vs-active suggestion comparison fields
  - `Detailed Only` review escalation where the active suggestion is blank but detailed sales suggests stocking
- The active suggestion path is now more explicit:
  - [reorder_flow.py](C:/Users/Cornelio/Desktop/POCreator/reorder_flow.py) now tracks `suggested_source` / `suggested_source_label`
  - source distinguishes:
    - `X4 12-month sales`
    - `Detailed sales fallback`
    - `No suggestion`
    - `Provided`
  - the source is carried through:
    - assignment-session preparation
    - session recalculation
    - review sync
    - bulk finalization
  - the source is visible in:
    - [ui_individual.py](C:/Users/Cornelio/Desktop/POCreator/ui_individual.py)
    - [ui_bulk_dialogs.py](C:/Users/Cornelio/Desktop/POCreator/ui_bulk_dialogs.py)
  - [ui_review.py](C:/Users/Cornelio/Desktop/POCreator/ui_review.py) now supports:
    - filtering by active suggestion source
    - review summary counts for detailed-fallback vs X4-driven suggestions
- Review & Export workflow issue fixed:
  - review focus now defaults to `All Items`
  - repaints no longer snap back to `Exceptions Only`

Most important files touched recently
- [parsers.py](C:/Users/Cornelio/Desktop/POCreator/parsers.py)
- [load_flow.py](C:/Users/Cornelio/Desktop/POCreator/load_flow.py)
- [reorder_flow.py](C:/Users/Cornelio/Desktop/POCreator/reorder_flow.py)
- [assignment_flow.py](C:/Users/Cornelio/Desktop/POCreator/assignment_flow.py)
- [item_workflow.py](C:/Users/Cornelio/Desktop/POCreator/item_workflow.py)
- [ui_load.py](C:/Users/Cornelio/Desktop/POCreator/ui_load.py)
- [ui_review.py](C:/Users/Cornelio/Desktop/POCreator/ui_review.py)
- [ui_individual.py](C:/Users/Cornelio/Desktop/POCreator/ui_individual.py)
- [ui_bulk_dialogs.py](C:/Users/Cornelio/Desktop/POCreator/ui_bulk_dialogs.py)
- [po_builder.py](C:/Users/Cornelio/Desktop/POCreator/po_builder.py)
- [ROADMAP_v0.2_CONSOLIDATED.md](C:/Users/Cornelio/Desktop/POCreator/ROADMAP_v0.2_CONSOLIDATED.md)

Most important tests touched recently
- [tests/test_parsers.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_parsers.py)
- [tests/test_load_flow.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_load_flow.py)
- [tests/test_reorder_flow.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_reorder_flow.py)
- [tests/test_assignment_flow.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_assignment_flow.py)
- [tests/test_item_workflow.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_item_workflow.py)
- [tests/test_ui_load.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_ui_load.py)
- [tests/test_ui_review.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_ui_review.py)
- [tests/test_ui_individual.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_ui_individual.py)
- [tests/test_ui_bulk_dialogs.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_ui_bulk_dialogs.py)
- [tests/test_po_builder.py](C:/Users/Cornelio/Desktop/POCreator/tests/test_po_builder.py)

Roadmap state
- The current planning source of truth remains:
  [ROADMAP_v0.2_CONSOLIDATED.md](C:/Users/Cornelio/Desktop/POCreator/ROADMAP_v0.2_CONSOLIDATED.md)
- Phase 2A is now much further along than the roadmap originally implied.
- Newly completed `2A` items now reflected in the roadmap:
  - live detailed-sales parsing hardening
  - real replacement of the combined sales/receipts path with the detailed pair
- The main remaining `2A` decisions are now policy questions, not plumbing gaps:
  - whether to fully remove legacy combined sales support after enough live-file confidence
  - how receipt activity should affect target-stock / reorder suppression beyond review/confidence handling
  - whether any detailed-sales suggestion cases should replace the active suggestion more aggressively by default

Best next steps
1. Continue the remaining Phase 2A policy work, not more low-level parser plumbing.
   - The next safest high-value slice is:
     - make active suggestion source easier to act on in Review & Export, or
     - use receipt-vs-sales balance to gate one narrow additional reorder behavior beyond review-only surfacing
2. If staying in `2A`, avoid broad behavior drift.
   - Good candidates:
     - a review filter / summary emphasis around detailed-fallback-driven suggestions already landed
     - next, decide whether receipt-heavy items should suppress or downgrade target-stock suggestions in a narrow, explicit way
3. If `2A` starts requiring too many product assumptions, pivot to the next major roadmap area.
   - Most likely:
     - Phase 6A shipping planning
     - or packaged `.exe` smoke-test evidence from real workflows

Recommended next implementation slice
- Start with the remaining `2A` item:
  [ROADMAP_v0.2_CONSOLIDATED.md](C:/Users/Cornelio/Desktop/POCreator/ROADMAP_v0.2_CONSOLIDATED.md)
  - `Decide how receipt activity should influence target-stock / reorder suppression beyond review/confidence handling.`
- Candidate direction:
  - only in clearly `receipt_heavy` cases, prevent receipt-driven fallback logic from encouraging a stronger suggestion than the sales-side evidence supports
  - keep it narrow and review-first
  - do not change X4 `mo12_sales`-driven suggestions broadly
- Regression coverage to add if taking that route:
  - receipt-heavy detailed fallback does not inflate the active suggestion
  - balanced receipt-vs-sales cases still allow current fallback behavior
  - review summary / details remain coherent with the adjusted behavior

Open risks / remaining gaps
- Legacy combined sales support still exists as compatibility fallback.
- The live detailed-sales parser is much safer now, but unresolved/suspicious rows still exist and are only diagnosed, not automatically repaired beyond uniquely supported cases.
- Suggestion source is now visible and filterable, but the broader product policy for when detailed sales should actually override more active-suggestion cases is still open.
- No packaged `.exe` smoke test through a full real user workflow was run after the latest `0.1.18` changes.

Notes
- Release artifacts are already updated for `0.1.18`.
- If touching release artifacts again, keep:
  - [app_version.py](C:/Users/Cornelio/Desktop/POCreator/app_version.py)
  - [VERSION](C:/Users/Cornelio/Desktop/POCreator/VERSION)
  - matching `RELEASE_v...md`
  in sync.
- Current working tree after the release build:
  - [debug_trace.log](C:/Users/Cornelio/Desktop/POCreator/debug_trace.log) is modified by runtime/build activity
  - release artifacts changed this session:
    - [app_version.py](C:/Users/Cornelio/Desktop/POCreator/app_version.py)
    - [VERSION](C:/Users/Cornelio/Desktop/POCreator/VERSION)
    - [RELEASE_v0.1.18.md](C:/Users/Cornelio/Desktop/POCreator/RELEASE_v0.1.18.md)
    - [ROADMAP_v0.2_CONSOLIDATED.md](C:/Users/Cornelio/Desktop/POCreator/ROADMAP_v0.2_CONSOLIDATED.md)
