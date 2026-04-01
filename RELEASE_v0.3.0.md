# Release Notes — v0.3.0

**Date:** 2026-04-01

---

## Summary

v0.3.0 is the first stable release of the v0.3.x line. All five code-deliverable "Definition of Done Enough" criteria are satisfied:

- Items with strong protective evidence are no longer permanently trapped in `reel_review` or `large_pack_review`.
- Operators who confirm a missing-recency item for stocking do not have to re-review it next session.
- Historical order quantities from recent sessions are visible alongside the current suggestion.
- Data quality gaps are surfaced on the load tab before the assignment step.
- Bulk-editor filter and sort state survive restarts.

The two manual QA steps (packaged-exe smoke test with real-world CSVs) remain open from Phase 1 but do not block this release.

---

## What changed since v0.2.0

### Phase 2 — Reel and Large-Pack Graduation (`rules.py`)

`reel_review` and `large_pack_review` items previously had no path to auto-order. They now graduate based on evidence:

- **New `reel_auto` policy.** A reel/spool item graduates from `reel_review` to `reel_auto` when `recency_confidence == "high"` AND (`sales_health_signal == "active"` OR `has_recent_local_order == True`). `reel_auto` computes quantities like `pack_trigger` — rounding to the replenishment unit without human review.
- **Large-pack graduation.** A `large_pack_review` item graduates to `pack_trigger` under the same evidence conditions.
- **`policy_locked` blocks graduation.** When the operator sets `policy_locked: true` on a rule, the item is never promoted out of review.
- **Regression is automatic.** Evidence is re-evaluated each session; if recency drops to medium or low, the item returns to `reel_review` / `large_pack_review`.
- **`policy_graduated_from` field.** Set on graduated items so downstream code and the UI can explain why the policy changed.
- **`reel_auto` added to the buy-rule editor combobox.**
- **18 new tests** covering graduation, non-graduation, expiry, quantity calculation, replenishment mode, and `evaluate_item_status` behavior.

### Phase 3 — Missing-Recency Lifecycle (`rules.py`)

Items classified as `missing_recency_*` previously re-entered review every session indefinitely.

- **`confirmed_stocking` rule flag.** Operators set `confirmed_stocking: true` in `order_rules.json` to bypass the recency-review gate for that item. The item auto-orders in future sessions.
- **Session counter.** Each session without new sale or receipt evidence increments `confirmed_stocking_sessions_without_evidence` on the rule. After `CONFIRMED_STOCKING_MAX_SESSIONS_WITHOUT_EVIDENCE` (default 3) such sessions, the flag expires and the item reverts to manual review.
- **Evidence resets the counter.** When both `last_sale` and `last_receipt` are present, the counter resets to 0 and is written back to the rule so `order_rules.json` stays current.
- **Quantity suppression bypass.** `should_suppress_manual_only_qty()` now checks the confirmed flag before zeroing the suggestion.
- **Surfaces in `why` and `reason_codes`.** Items show "Confirmed stocking: operator-confirmed" in the detail view, including how many sessions remain before expiry.
- **7 new tests** covering bypass, expiry, counter increment/reset, and why-text appearance.

### Phase 4 — Session Learning and Order History (`storage.py`, `load_flow.py`, `assignment_flow.py`, `rules.py`)

Session snapshots were written but never read back.

- **`load_session_snapshots(directory, max_count=3)`** in `storage.py` reads the most recent N session snapshot files.
- **`extract_order_history(snapshots)`** in `storage.py` builds a per-item dict of historical order quantities from `assigned_items.final_qty`.
- **`session_history` field** added to `AppSessionState`; populated on every load from the `sessions/` directory.
- **`historical_order_qty`** stamped on items in `assignment_flow.prepare_assignment_session()` using the median of recent quantities.
- **`suggestion_vs_history_gap` flag and review routing.** In `enrich_item()`, when the current suggestion deviates from `historical_order_qty` by more than `SUGGESTION_VS_HISTORY_GAP_THRESHOLD` (default 50%), the item is flagged and routed to review. The gap detail appears in the `why` text.
- **9 new tests** covering snapshot loading, history extraction, gap detection, and review routing.

### Phase 5 — Data Quality Dashboard (`load_flow.py`, `ui_load.py`, `po_builder.py`)

Data quality warnings were buried in the review tab and not visible before assignment.

- **`compute_data_quality_summary(session)`** in `load_flow.py` computes: total items loaded, inventory coverage count, items with missing last-sale / last-receipt, unresolved detailed-sales item codes, conflicting items, and an overall quality score.
- **Data Quality card on the Load tab.** Appears immediately after a successful parse. Shows all quality metrics in a labeled frame.
- **Acknowledgment gate.** When more than 10% of items are unresolved (`gate_required == True`), a warning dialog is shown before the assignment tab is enabled. The operator can proceed after reading the warning.
- **Existing startup warning rows behavior unchanged** — the new card is additive.
- **5 new tests** covering quality scoring, gate threshold, missing-recency counts, and empty session handling.

### Phase 6 — Filter and Sort Persistence (`ui_bulk.py`, `po_builder.py`)

Bulk-editor filter state and sort order reset on every restart.

- **`save_bulk_filter_sort_state(app)`** writes the active filter state (all 7 filter vars) and sort column/direction to `app_settings` and calls `_save_app_settings()`. Called automatically at the end of `apply_bulk_filter()` and `sort_bulk_tree()`.
- **`restore_bulk_filter_sort_state(app)`** reads from settings and sets all filter vars + sort state before `_populate_bulk_tree()`. Called in `_proceed_to_assign()` so the saved state applies to the first render.
- **Safe to call before filter vars exist** — missing vars are silently skipped.
- **4 new tests** covering save, restore, empty-settings handling, and no-settings-attr guard.

---

## Test coverage

**730 tests, all passing.**

New tests added since v0.2.0:
- `test_reel_review_without_strong_evidence_stays_reel_review`
- `test_reel_item_graduates_to_reel_auto_with_high_recency_and_active_sales`
- `test_reel_item_graduates_to_reel_auto_with_high_recency_and_recent_local_order`
- `test_reel_item_does_not_graduate_with_low_recency`
- `test_reel_item_does_not_graduate_when_policy_locked`
- `test_large_pack_review_graduates_to_pack_trigger_with_high_recency_and_active_sales`
- `test_large_pack_review_stays_without_strong_evidence`
- `test_reel_auto_calculates_pack_trigger_quantity`
- `test_reel_auto_replenishment_unit_mode_is_pack_trigger`
- `test_reel_auto_does_not_trigger_review_in_evaluate_item_status`
- `test_enrich_item_reel_auto_graduation_appears_in_reason_codes_and_why`
- `test_reel_graduated_item_reverts_when_recency_drops`
- `test_confirmed_stocking_bypasses_recency_review_routes_to_auto_order`
- `test_confirmed_stocking_false_still_routes_to_review_without_evidence`
- `test_confirmed_stocking_expired_after_threshold_sessions_without_evidence`
- `test_confirmed_stocking_resets_counter_when_evidence_present`
- `test_confirmed_stocking_increments_counter_without_evidence`
- `test_confirmed_stocking_surfaces_in_why_detail`
- `test_confirmed_stocking_expiry_surfaces_in_why_detail`
- `test_no_history_no_gap_flag`
- `test_history_within_threshold_no_gap`
- `test_history_gap_beyond_threshold_flags_review`
- `test_history_gap_ignored_for_manual_only_policy`
- `test_load_session_snapshots_returns_empty_for_missing_directory`
- `test_load_session_snapshots_reads_recent_files_most_recent_first`
- `test_load_session_snapshots_respects_max_count`
- `test_extract_order_history_builds_per_item_dict`
- `test_extract_order_history_ignores_zero_and_missing_qty`
- `test_data_quality_summary_clean_session`
- `test_data_quality_summary_gate_required_when_unresolved_exceeds_threshold`
- `test_data_quality_summary_gate_not_required_when_unresolved_at_threshold`
- `test_data_quality_summary_counts_missing_recency`
- `test_data_quality_summary_handles_empty_session`
- `test_save_bulk_filter_sort_state_persists_to_app_settings`
- `test_restore_bulk_filter_sort_state_applies_saved_values`
- `test_restore_bulk_filter_sort_state_handles_missing_settings`
- `test_save_bulk_filter_sort_state_noop_when_no_app_settings`

---

## Open items (non-blocking)

- **Phase 1 (manual QA):** Run full load → assign → review → export against representative real-world CSVs in the packaged exe.
- **Phase 5:** "Export Data Quality Report" button deferred to a follow-on release.
- **Phase 6:** Named filter presets ("My review items") deferred to a follow-on release.
- **Phases 7–8:** Dynamic heuristic calibration and export formatting options remain open roadmap items.

---

## Upgrade

Replace `POBuilder.exe` with the new build. No data-file migration required. All existing `order_rules.json`, `vendor_codes.txt`, `vendor_policies.json`, and session snapshots are fully compatible.

**Behavioral changes visible to operators:**

1. Items that previously always entered `reel_review` or `large_pack_review` may now auto-order as `reel_auto` or `pack_trigger` when demand evidence is strong. The `why` text will indicate "Policy graduated from Reel review."
2. Missing-recency items with `confirmed_stocking: true` in their rule auto-order instead of going to review. A session counter in the rule tracks how long since evidence was last seen.
3. The load tab now shows a Data Quality card after each successful parse. If more than 10% of items are unresolved, a warning dialog appears before the assignment step.
4. Bulk-editor filter and sort state are saved on each change and restored automatically at the start of the next session.
