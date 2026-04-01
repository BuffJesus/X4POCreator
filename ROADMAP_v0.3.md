# PO Builder Roadmap — v0.3.x

Status: v0.3.0 released — Phases 2–6 complete

Current app version: `0.3.0`

---

## What v0.3.x is about

v0.2.x got the fundamentals right: explainable reorder logic, detailed-sales evidence, shipping-aware release, a hardened bulk editor, and a self-updating packaged app. v0.3.x is about making the app smarter over time and easier to operate every run:

- **Session learning** — use what was ordered before to inform what to order next
- **Reel and large-pack graduation** — items trapped in permanent manual review should have a path to auto-order when evidence is strong enough
- **Operational diagnostics** — surface data-quality gaps before assignment, not after
- **Persistence** — filter state, sort preferences, and operator choices should survive restarts

---

## Phase 1. Packaged-App Confidence (carry-over from v0.2.x)

These two items were deferred from Phase 1 of the v0.2.x roadmap. They require manual QA with real-world CSV files and cannot be covered by unit tests alone.

- [ ] Run full load → assign → review → export workflow against representative real-world CSVs in the packaged exe.
- [ ] Confirm that detailed sales / received parts parsing, vendor resolution, and export formatting all behave correctly with live data shapes not covered by synthetic tests.
- [ ] Add any targeted regression tests discovered during live testing.

---

## Phase 2. Reel and Large-Pack Graduation

The `reel_review` and `large_pack_review` policies currently have no path to auto-order. Items reach these states once and stay there even when protecting evidence (recent receipts, active sales, explicit rules) is strong. This blocks routine replenishment for valid stocking items.

- [x] Define evidence thresholds that allow a `reel_review` item to graduate to auto-order:
  - explicit `policy_locked` rule set to a specific qty / pack policy
  - recent receipt within the reorder cycle with matching qty
  - `recency_confidence == "high"` and `sales_health_signal == "active"`
- [x] Define the same thresholds for `large_pack_review`.
- [x] Add a `reel_auto` policy that represents a confirmed reel/spool item with enough evidence to order without human review each cycle.
- [x] Ensure graduated items remain in review-first mode when evidence weakens (recency drops, no recent receipts).
- [x] Add tests covering each graduation and regression path.
- [x] Surface the graduation evidence in the buy-rule editor and item details so operators understand why an item changed policy.

---

## Phase 3. Missing-Recency Lifecycle

Items classified as `missing_recency_*` currently stay in review indefinitely with no mechanism to graduate to a lower-friction state. Operators have to re-review the same items every session.

- [x] Add a "confirmed stocking" flag that operators can set on a missing-recency item after manual review. This flag persists in `order_rules.json` and routes the item to auto-order (with a reduced-confidence cap) in future sessions.
- [x] Distinguish items that have been operator-confirmed at least once from items that are genuinely new or newly-missing.
- [x] Allow the confirmed stocking flag to expire when a configurable number of sessions pass without any new sale or receipt evidence, reverting to review.
- [x] Surface confirmation age and evidence status in item details.
- [x] Add tests for confirmation, expiry, and reversion.

---

## Phase 4. Session Learning and Order History

Session snapshots are written but never read. The `recent_orders` field is populated but only used for protective-evidence flags, not for suggestion improvement.

- [x] Load the most recent session snapshot on startup and extract per-item historical order quantities.
- [x] Add a `historical_order_qty` field to enriched items: the median or mode of order quantities from recent sessions.
- [x] Surface `historical_order_qty` in item details and the bulk editor as a reference column (non-editable).
- [x] When `historical_order_qty` exists and the current computed suggestion diverges by more than a configurable threshold, flag it as `suggestion_vs_history_gap` and route to review.
- [ ] Use `recent_local_order_qty` (already populated per-item) in the same comparison when no snapshot history is available.
- [x] Add tests covering history loading, gap detection, and review routing.
- [x] Decide how many sessions to retain for history averaging (default: last 3).

---

## Phase 5. Data Quality Dashboard

Data quality warnings are collected during load but only surfaced in the review tab. Operators can reach the assignment step without knowing that a large fraction of their items are unresolved or have coverage gaps.

- [x] Add a "Data Quality" summary card on the load tab that appears after a successful parse. Show:
  - total items loaded vs items with inventory coverage
  - unresolved detailed-sales line codes (count and sample)
  - items with missing `last_sale` and `last_receipt`
  - items where detailed-sales and X4 min/max materially disagree
- [x] Gate the assignment tab activation on a user acknowledgment if the data quality score is below a configurable threshold (e.g. >10% unresolved items).
- [ ] Add an "Export Data Quality Report" button that writes a CSV of all flagged items with their flag reasons, for sharing with the data-source owner.
- [x] Keep the existing startup warning rows behavior intact — the new dashboard is additive.
- [x] Add tests for the quality scoring and gate logic.

---

## Phase 6. Filter and Sort Persistence

Bulk-editor filter state and sort order reset on every app restart. Operators who run the app daily with the same filter (e.g., "show only review-status items for AER-") must reconfigure it each session.

- [x] Save the active bulk filter state (line-code filter, status filter, vendor filter, search text) to `po_builder_settings.json` on change.
- [x] Restore the saved filter state on startup when a session is active.
- [ ] Allow operators to save named filter presets ("My review items", "All AER- unassigned") and switch between them.
- [x] Persist the active sort column and direction.
- [x] Add tests for save/restore round-trips.

---

## Phase 7. Dynamic Hardware Heuristic Calibration

Several hardware-buffer heuristics use fixed multipliers that were chosen conservatively. As more session history accumulates, these can be evidence-weighted rather than static.

Key fixed constants currently in `rules.py`:
- `REEL_REVIEW_MIN_PACK_QTY = 250`
- `LARGE_PACK_REVIEW_MIN_PACK_QTY = 25`
- Pack-trigger infer thresholds (e.g. `pack_qty * 0.75`, `mx * 1.5`)
- Cover-cycle inference multipliers

Items:
- [ ] Move all heuristic thresholds into a named-constant block at the top of `rules.py` with comments explaining each value's intent and the evidence that would justify raising or lowering it.
- [ ] Add a `heuristic_confidence` score to enriched items that reflects how much loaded evidence supports the inferred hardware policy, distinct from `recency_confidence`.
- [ ] When `heuristic_confidence` is high and recent history supports a higher buffer, allow the inferred `minimum_packs_on_hand` to exceed 2 without requiring an explicit rule.
- [ ] When history is short or demand is volatile, cap inferred buffers conservatively.
- [ ] Add tests for evidence-weighted buffer adjustment.

---

## Phase 8. Export and PO Formatting Options

The current export writes fixed-column X4 import files. Operators have requested column selection, vendor grouping control, and export preview.

- [ ] Add an export preview dialog that shows the row count, vendor list, and total estimated order value before writing files.
- [ ] Add a "Column notes" or "PO memo" field that operators can fill in once per export session; it is written to a notes column in each exported file.
- [ ] Add a per-vendor export scope override: include this vendor in the current export, defer to next session, or skip permanently.
- [ ] Keep the default export behavior (immediate-release items only) unchanged; scope overrides are opt-in.
- [ ] Add tests for preview data and scope override logic.

---

## Definition of "Done Enough" for v0.3.x

The v0.3.x line is ready when:

- Items with strong protective evidence are not permanently trapped in `reel_review` or `large_pack_review`.
- Operators who review an item and confirm it for stocking do not have to re-review the same item next session.
- Historical order quantities are visible alongside the current suggestion.
- Data quality gaps are visible before the assignment step, not buried in the review tab.
- Bulk-editor filter and sort state persist across restarts.
- The packaged exe has been smoke-tested against real-world CSVs and any gaps discovered are covered.
