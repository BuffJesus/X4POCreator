# PO Builder Consolidated Roadmap to `v0.2.x`

Status: reconciled against the current workspace and test-covered behavior

Current app version: `0.1.18`

This file consolidates:

- [`ROADMAP_v0.2.0.md`](C:\Users\Cornelio\Desktop\POCreator\ROADMAP_v0.2.0.md)
- [`ROADMAP_v0.2.5.md`](C:\Users\Cornelio\Desktop\POCreator\ROADMAP_v0.2.5.md)

The goal is to keep one phased checklist that reflects what is actually done in the codebase now, instead of leaving completed work mixed in with older proposed work.

## Status Summary

### Foundation and stability

- `v0.2.0` foundation work is mostly complete.
- Shared/local data flow, release discipline basics, and controller decomposition all have strong evidence in the current codebase.
- The main remaining `v0.2.0` gap is packaged-app workflow confidence rather than core app structure.

### Reorder core and pack-driven logic

- The reorder core refactor is materially in place.
- Trigger-based ordering, effective reorder floors, pack-trigger behavior, hardware heuristics, recency-confidence gating, and acceptable-overstock handling are all implemented.
- The biggest remaining reorder-core gaps are deeper low-confidence classification, stricter separation between explicit-rule-protected and uncertain missing-recency items, additional reel/generalized replenishment policy cleanup, stronger candidate-preservation safeguards, and more dynamic hardware buffering tied to real usage history.

### Shipping-aware release logic

- A first vendor shipping policy model now exists.
- Vendor policies persist on disk, load with session state, and annotate items with release decisions and reasons.
- Export now respects held-vs-release-ready items, but the remaining shipping work is deeper operational planning: vendor-level consolidation, threshold forecasting, and date-aware release workflow.

### Bulk editor hardening

- A large amount of bulk editor safety work is complete.
- The remaining work is the final rapid-edit race elimination and further large-session performance separation.

### Workflow simplicity

- The app is becoming more powerful, but some newer shipping/release choices risk adding operator friction.
- The product direction should stay biased toward "good automatic default, explicit exception handling" rather than asking the user to make repeated policy or export-scope decisions.
- The remaining UX work is to collapse routine decisions into defaults, surface only the exceptions that need attention, and make advanced controls available without being mandatory.

## Phase 1. Foundation, Shared Data, and Release Discipline

- [x] Keep local/shared data switching explicit and visible in the UI.
- [x] Refresh active data from disk across rules, vendor codes, ignore state, history, suspense carry, and related saved state.
- [x] Keep shared-folder writes atomic and lock-protected for persistent JSON/text files.
- [x] Handle shared-data merge/conflict cases for concurrency-sensitive saved state such as `suspense_carry`.
- [x] Cover active-folder refresh and shared/local switching with regression tests.
- [x] Continue moving workflow logic out of `po_builder.py` into focused helper modules.
- [x] Keep UI event handlers thin and delegate logic into testable helpers.
- [x] Maintain a release checklist document.
- [x] Keep the internal app version as the primary version source used by the startup update check.
- [x] Keep startup update-check prompt behavior covered.
- [ ] Add stronger packaged `.exe` smoke-test evidence for the full user workflow using representative real-world CSVs.
- [ ] Confirm release-candidate workflow coverage from load through export at the packaged-app level, not only unit-test level.

## Phase 2. Reorder Core Refactor

- [x] Separate reorder trigger, target stock, quantity suggestion, and review gating in the ordering logic.
- [x] Stop relying only on `raw_need > 0` as the implicit reorder decision.
- [x] Track inventory position explicitly as `QOH + on PO`.
- [x] Track effective reorder floor separately from operational target stock.
- [x] Support trigger-based reordering below or above the ordinary operational max as needed.
- [x] Cover full-pack / small-operational-max edge cases with rule tests.
- [x] Thread clearer `why` / reason-code explanations through the enriched item model.
- [x] Extend cadence-aware reorder logic beyond pack floors into explicit cover-days / cover-cycles rules.

## Phase 2A. Detailed Sales and Receiving Evidence

- [x] Add first-class support for:
  - `DETAILEDPARTSALES.csv`
  - `ReceivedPartsDetail.csv`
- [x] Keep the downstream assignment/reorder session shape stable while building it from the two detailed files.
- [x] Derive the active sales window from detailed sales rows when the combined report is not used.
- [x] Carry receipt-history metadata into session state for vendor-ranking, review, and item-detail flows.
- [x] Use receiving detail as the primary vendor-evidence source ahead of stale X4 supplier defaults.
- [x] Add receipt-derived vendor confidence / ambiguity handling instead of blindly trusting one receipt row.
- [x] Factor loaded receipt activity into reorder-confidence handling so recent receipts protect items when open-PO evidence is missing.
- [x] Add receipt-vs-sales balance guardrails so receipt-heavy history does not automatically legitimize demand.
- [x] Add detailed-sales transaction-shape metrics:
  - units per transaction
  - sale-day frequency
  - inter-sale cadence
  - burstiness / lumpy-demand signals
- [x] Surface receipt-history and detailed-sales evidence in item detail and assignment UI before making it authoritative for automation.
- [x] Compare detailed-sales-driven min/max suggestions against current X4 / heuristic suggestions before changing default reorder behavior.
- [x] Surface meaningful detailed-sales / receipt exceptions in Review:
  - lumpy demand
  - suggestion gaps
  - receipt-heavy vs sales
- [x] Make the detailed file pair the default/required load path and move the legacy combined `Part Sales & Receipts` report to compatibility-only status in the UI and docs.
- [ ] Decide whether to fully remove the legacy combined `Part Sales & Receipts` path after live-file coverage is proven.
- [x] Tighten live `DETAILED PART SALES.csv` parsing for edge cases where the first hyphen in the combined code token may not be the true PG/item boundary.
- [x] Measure real-world line-code resolution coverage after live parsing and add diagnostics for unresolved detailed-sales rows.
- [x] Decide how receipt activity should influence target-stock / reorder suppression beyond review/confidence handling.
- [ ] Decide whether any detailed-sales suggestion cases should replace the active suggestion by default instead of remaining compare/review signals only.

## Phase 3. Rule Model Expansion and Pack-Trigger Behavior

- [x] Add `pack_trigger` policy support.
- [x] Add persisted rule fields for `reorder_trigger_qty`.
- [x] Add persisted rule fields for `reorder_trigger_pct`.
- [x] Add persisted rule fields for `acceptable_overstock_qty`.
- [x] Add persisted rule fields for `acceptable_overstock_pct`.
- [x] Add persisted rule fields for `minimum_packs_on_hand`.
- [x] Surface those fields in the buy-rule editor, details UI, and tests.
- [x] Allow full-pack replenishment without treating all post-receipt overstock as suspicious by default.
- [x] Compute effective acceptable overstock from qty or percent of pack.
- [x] Use acceptable-overstock tolerances in downstream review/removal coherence.
- [x] Use acceptable-overstock tolerances as an upstream auto-order guardrail.
- [x] Explain trigger-driven and tolerance-driven behavior in `why` text.
- [x] Add persisted rule fields for `minimum_cover_days`.
- [x] Add persisted rule fields for `minimum_cover_cycles`.
- [x] Decide whether inferred two-pack hardware floors should persist into saved rules after explicit confirmation.

## Phase 4. Review Coherence, Large-Pack Handling, and Confidence Gating

- [x] Add `large_pack_review` as a non-reel review path.
- [x] Keep real reel-like items on `reel_review`.
- [x] Improve reel-vs-non-reel detection with blocklists and stronger description checks.
- [x] Add direct hardware-term detection from descriptions.
- [x] Add explicit package-profile classification for reel stock, hardware packs, and large non-reel packs.
- [x] Add conservative active-hardware heuristics that infer `pack_trigger` when appropriate.
- [x] Add conservative active-hardware heuristics that infer `minimum_packs_on_hand = 2` when appropriate.
- [x] Route stale/risky large-pack non-reel items to review instead of auto-order.
- [x] Add `recency_confidence` and `data_completeness` signals to final item recommendations.
- [x] Require stronger evidence before auto-ordering when both `last_sale` and `last_receipt` are missing.
- [x] Allow explicit stocking-rule exceptions for missing-recency items.
- [x] Route suspense/open-PO protected missing-recency items to review instead of blind skip or blind auto-order.
- [x] Ensure missing-recency review items do not surface a non-zero default export qty unless explicitly protected by a stronger rule.
- [x] Treat plain X4 min/default stock as insufficient protection when both `last_sale` and `last_receipt` are missing.
- [x] Ensure "Remove Not Needed" respects trigger-based replenishment logic.
- [x] Ensure "Remove Not Needed" respects acceptable intentional overstock.
- [x] Surface minimum-pack source, confidence, completeness, and shipping/release annotations in item details.
- [x] Distinguish low-confidence reorder candidates more explicitly into:
  - stale / likely dead
  - new / not enough history
  - missing-data / uncertain
  - critical / rule-protected
- [x] Make low-confidence recency buckets actionable in Review filters and summary text.
- [x] Add cadence-aware heuristics for high-velocity small-pack items beyond the current two-pack hardware floor.
- [x] Decide whether `reel_review` should remain distinct or split into `reel_auto` plus generalized replenishment-unit policies.
- [ ] Keep negative QOH clamped to zero for ordering quantities while continuing to surface negative-balance data-quality warnings.
- [x] Add explicit candidate-preservation rules so items can enter the assignment session from inventory/min-max protection signals even when loaded sales rows are weak or absent.
- [x] Add stronger source-confidence handling when X4 min/max, X4 12-month sales, and detailed-sales annualization materially disagree.
- [x] Add min/max sanity normalization and review flags for invalid or suspicious source pairs such as `max < min`, negative values, or extreme jumps.
- [ ] Add churn-damping / hysteresis so small source-data changes do not unnecessarily flip reorder decisions or target-stock outcomes between runs.
- [ ] Clarify and deepen the split between hard reorder floors and preferred operational targets so protected reorder timing can stay stable without permanently inflating routine targets.
- [x] Replace the static hardware two-pack bias with a more dynamic hardware buffer based on available evidence such as sales window length, annualized demand, receipt cadence, and pack size.
- [ ] Make hardware buffer heuristics get more permissive only when the loaded history window is long enough and the demand shape is stable enough to justify it.
- [ ] Clean up pack semantics so "unknown pack", "no pack data", and explicit operator intent to order exact quantities are represented distinctly instead of overloading zero-like values.

## Phase 5. Vendor Shipping Policy Model

- [x] Add persistent vendor shipping policy storage.
- [x] Add vendor-policy session loading.
- [x] Support shipping policies:
  - `release_immediately`
  - `hold_for_free_day`
  - `hold_for_threshold`
  - `hybrid_free_day_threshold`
- [x] Support policy inputs for:
  - preferred free-shipping weekdays
  - freight-free threshold
  - urgent release floor
- [x] Compute vendor-level order-value totals for release decisions.
- [x] Annotate items with:
  - shipping policy
  - release decision
  - release reason
  - vendor order value total
- [x] Append release reasoning to the item `why` text.
- [x] Add a real editing/configuration surface for vendor policies.
- [x] Decide where vendor policy should live operationally in the UI: settings, vendor manager, dedicated dialog, or data file only.
- [x] Add broader validation and normalization for user-entered vendor policy values.
- [x] Add explicit vendor-policy fields for release lead time / order-ahead behavior.
- [x] Decide whether release timing should be modeled as:
  - same-day release only
  - release on target ship day
  - release one business day before target ship day
  - vendor-specific lead days

## Phase 6. Shipping-Aware Release Logic

- [x] Release immediately when urgent floor is breached.
- [x] Hold for preferred free-shipping day when configured and not urgent.
- [x] Hold for freight threshold when configured and not urgent.
- [x] Release once threshold is reached.
- [x] Surface release reasoning in item details and `why` text.
- [x] Make review/export workflows act on release decisions, not just display them.
- [x] Support "held but still visible for review" as an explicit operational workflow, not only as explanatory text.
- [x] Add stronger vendor-group consolidation behavior across multiple candidate items and mixed urgency.
- [x] Treat "paid urgent truck" or equivalent override as an explicit release path in the model and UI.
- [x] Prevent hold logic from hiding critical shortages operationally during export/review, not only in reasoning text.
- [x] Add vendor-level release planning that distinguishes:
  - release now
  - hold and keep accumulating toward threshold
  - release on next preferred free-freight day
  - release one business day before the preferred free-freight day so the PO lands on time
- [x] Add explicit "target release date" / "target order date" annotations to held items, not only abstract hold reasons.
- [x] Add export support for planned-release batches so users can intentionally export tomorrow's free-freight POs one day early when policy requires it.

## Phase 6A. Cost- and Date-Aware Shipping Planning

This is the next high-value shipping slice. The current model already uses `repl_cost` from inventory data and the current weekday to decide `release_decision`, but it does not yet reason about expected future threshold reach or order-ahead timing.

- [x] Confirm and document the cost source used for shipping decisions:
  - inventory `repl_cost`
  - report-provided extended/value fields if available
  - fallback behavior when cost is missing or zero
- [ ] Add data-quality handling for shipping-value calculations:
  - missing cost
  - zero cost
  - obviously stale or malformed cost
  - vendor totals with mixed known/unknown value coverage
- [x] Add vendor-level threshold progress signals:
  - current estimated vendor total
  - amount short of threshold
  - percentage of threshold reached
  - value coverage confidence
- [x] Add shipping-planning dates:
  - next preferred free-freight weekday
  - recommended order/export date
  - business-day-aware "release one day early" date when appropriate
- [x] Decide and encode the operational rule for "day before" export:
  - calendar day
  - business day
  - vendor-configurable lead days
- [x] Add a release decision family for planned future release, for example:
  - `hold_for_threshold`
  - `hold_until_free_day`
  - `export_next_business_day_for_free_day`
  - `release_now_threshold_reached`
- [x] Show planning outputs in Review & Export:
  - threshold shortfall
  - next free-freight day
  - planned export date
  - why this date was chosen
- [x] Add an export mode that can include:
  - release-ready POs only
  - release-ready plus due-soon planned POs
  - a filtered "planned for tomorrow" batch
- [x] Keep order history and session snapshots clear about whether a PO was:
  - exported now for immediate ordering
  - exported early for a scheduled free-freight release
  - still held and not exported
- [x] Add tests for:
  - threshold shortfall math from report cost
  - mixed known/unknown cost coverage
  - next-free-day calculation
  - Friday/Monday business-day edge cases
  - export-on-previous-business-day behavior
  - urgent override beating planned free-day logic

## Phase 7. Packaged-App Self-Update Flow

- [x] Check GitHub for updates on startup.
- [x] Prompt the user when a newer release exists.
- [x] Keep the startup update prompt covered by tests.
- [ ] Download accepted updates to a staging location.
- [ ] Hand off replacement to an updater helper or script after shutdown.
- [ ] Replace the running executable safely after exit.
- [ ] Relaunch automatically after successful replacement.
- [ ] Keep failed download / failed swap paths recoverable and clearly explained.

## Phase 8. Bulk Editor Integrity and Large-Session Performance

- [x] Flush pending bulk-sheet edits before many downstream actions.
- [x] Invalidate stale right-click context and selection snapshots more safely.
- [x] Add undo/redo support for bulk edits and removals.
- [x] Add selection snapshot handling and smarter post-edit selection preservation.
- [x] Add broad shortcut and bulk-sheet editing coverage around common editing flows.
- [x] Improve bulk summary caching and safer incremental refresh paths for common edits.
- [x] Move bulk row identity from positional indices to stable item keys so filtered/sorted refreshes, context actions, and row removals keep hitting the intended item.
- [x] Treat in-sheet navigation and selection changes as edit boundaries so queued cell commits drain before focus moves.
- [x] Carry stable bulk row-id resolution through vendor assignment actions so selected/visible sheet updates keep targeting the correct items.
- [x] Route bulk removal operations through the same undo/redo history capture path as other bulk actions.
- [x] Make the dedicated remove-undo path respect the real bulk history stack before falling back to legacy payload restore.
- [x] Flush queued edits before mouse-driven selection and right-click context changes so click-away paths respect the same edit boundary model.
- [ ] Eliminate remaining previous-cell / rapid-click commit bleed under real timing pressure.
- [ ] Guarantee edit-target integrity under rapid click-edit, keyboard-edit, filtered, sorted, and multi-selection workflows.
- [x] Document and centralize final precedence between current cell, selected cells, selected rows, and right-click snapshot state.
- [ ] Tighten undo/history boundaries so they always match the user's perceived edit unit.
- [ ] Separate full-session, active-filtered, and visible-row performance paths more aggressively for very large sessions.
- [ ] Require removal actions to verify stable row id plus current item identity before mutating the session, so stale UI state cannot remove the wrong candidate.
- [ ] Add a protected removal path for items that still meet reorder-worthiness signals from inventory floors, trigger rules, suspense demand, or other protected evidence, routing them to review before deletion instead of silently dropping them.
- [ ] Add explicit "why this item survived removal" reasoning for protected candidates so operators can distinguish true false-positives from protected-but-uncertain reorder rows.
- [ ] Add audit visibility for session removals so a removed row can be traced back as intentional operator action rather than upstream candidate loss.
- [ ] Promote unresolved source-mapping and high inventory-coverage-gap cases into an explicit review workflow so weak upstream joins do not quietly degrade ordering correctness.

## Phase 9. Workflow Simplification and Default-First UX

This phase is about reducing required operator input. Humans will consistently choose the path of least resistance, so the app should make the safest routine path the easiest one.

- [x] Treat the common path as:
  - load reports
  - review exceptions
  - export the default recommended batch
  rather than requiring users to decide policy details every run
- [x] Establish a single default export behavior that works without prompts in the common case.
- [x] Reserve extra prompts for meaningful branch points only, such as:
  - all items are held
  - only planned-release items are exportable
  - mixed immediate vs planned export where timing genuinely matters
- [x] Add a user preference for export behavior defaults, for example:
  - export immediate only
  - export all exportable
  - ask when mixed
- [x] Reduce repeated vendor-policy setup by preferring inherited or inferred defaults where safe.
- [x] Add policy templates / presets for common vendor behaviors so shipping rules can be configured with one click instead of field-by-field entry.
- [x] Make missing policy data fail soft with safe defaults instead of forcing immediate user intervention.
- [x] Prefer auto-filled values from current reports and saved history before asking for manual entry.
- [x] Collapse low-value fields behind an "Advanced" affordance in dialogs where the common workflow only needs one or two inputs.
- [x] Shift review emphasis from "touch every item" to "touch only exceptions":
  - held vendors with meaningful shortfall
  - urgent overrides
  - low-confidence recommendations
  - policy/data conflicts
- [x] Add a compact review mode centered on:
  - vendors ready to export
  - vendors planned today
  - vendors blocked and why
- [x] Add a single "Recommended Action" concept at both item and vendor level, so the operator can mostly follow one instruction instead of interpreting several fields.
- [x] Prefer persistent user choices over repeated prompts when the same decision recurs often.
- [x] Audit current prompts and dialogs for removal, consolidation, or safe defaulting.
- [x] Document a UX rule for future features:
  - no new required field unless the app cannot infer or default it safely
  - no new prompt unless different user choices create materially different outcomes
  - advanced controls should not slow down the routine path

## High-Value Remaining Checklist

These are the best next steps after reconciliation.

- [x] Define the default export behavior for mixed immediate/planned batches so routine users do not need to choose every time.
- [x] Add saved user preferences for export-scope prompting vs auto-selection.
- [x] Add broader vendor-policy defaulting beyond explicit presets to reduce setup friction without guessing unsafe values.
- [x] Add a compact exception-first review workflow that highlights only the items/vendors needing human judgment.
- [x] Add cost-confidence and threshold-progress signals to vendor shipping decisions.
- [x] Add planned release dates and "export the day before free-freight day" workflow for vendor policies.
- [x] Add stronger vendor-group release consolidation and explicit urgent paid-freight override workflow.
- [x] Replace the combined sales/receipts input path with `DETAILEDPARTSALES.csv` + `ReceivedPartsDetail.csv`, including receipt-derived vendor evidence and receipt-aware reorder protection.
- [x] Deepen shipping review/export options so users can export immediate, planned-tomorrow, or all-due batches intentionally.
- [x] Deepen recency-confidence classification for new-item / stale-item / critical-item distinctions.
- [x] Keep missing-recency activity-protected items visible with zero default qty instead of letting them ride through as implicitly orderable rows.
- [x] Treat recent local PO history as protective recency evidence for review bucketing, while still keeping missing-recency items review-first by default.
- [x] Distinguish explicit critical min-rule protection from other rule-protected missing-recency cases.
- [x] Cover weekly-order hardware cadence cases with inferred trigger-floor behavior for active small-pack hardware.
- [x] Preserve reorder-worthy candidates that are below protected inventory floors even when they have little or no loaded sales history.
- [ ] Replace the fixed hardware floor with evidence-weighted hardware buffer rules that improve as the loaded history window becomes longer and more stable.
- [ ] Keep negative QOH from inflating order quantities beyond the zero-on-hand interpretation while still flagging the underlying source issue for review.
- [ ] Add removal-protection tests for rows that still qualify through trigger rules, inventory-floor protection, suspense demand, or other protected reorder evidence.
- [ ] Add tests covering churn-control behavior so tiny source-data changes do not reorder or suppress items needlessly.
- [ ] Add tests covering explicit pack-state distinctions between unknown pack data, no-pack items, and deliberate exact-quantity overrides.
- [ ] Add tests covering unresolved source-mapping / inventory-coverage review routing so weak joins fail visible rather than silent.
- [ ] Add remaining edge-case tests called out in the original `0.2.5` roadmap, especially:
- [ ] Complete packaged-app self-update replacement flow.
- [ ] Finish bulk edit-target integrity hardening under rapid interactions.

## Definition of "Done Enough" for `v0.2.x`

The `v0.2.x` line is in good shape when all of the following are true:

- reorder behavior is explainable for pack, reel, hardware, confidence, and shipping cases
- reorder-worthy items are not silently lost because of source gaps, stale row state, or over-aggressive removal paths
- shared/local persistence behavior is operationally trustworthy
- shipping policy affects release workflow, not just display text
- bulk editor rapid-edit correctness is no longer a known risk
- packaged update flow is safe enough for end users to rely on
