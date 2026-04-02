# PO Builder Roadmap — v0.4.x

Status: Planning

Current app version: `0.3.0`

---

## What v0.4.x is about

v0.3.x made the app smarter: graduated hardware policies, operator-confirmed stocking, session learning, data-quality visibility, and export preview. v0.4.x focuses on three themes:

- **Correctness** — fix known context-menu and snapshot bugs before building on top of them
- **Operational intelligence** — use accumulated session history to surface actionable signals (trends, risk, dead stock)
- **Usability at scale** — features that pay off when the item list is large and the operator is familiar with the data

---

## Phase 1. Context Menu Bug Fixes

These are known regressions that affect daily use and should ship first.

### 1a. Multi-row snapshot reads cells, not just row-headers

**Bug:** `BulkSheetView.snapshot_row_ids()` reads only `snapshot["rows"]`, which is populated by row-header (`get_selected_rows()`) clicks. Normal shift-click or drag selection across cells populates `snapshot["cells"]` but leaves `"rows"` empty. Result: any context-menu command that calls `snapshot_row_ids()` silently reduces to a single row.

**Fix in `bulk_sheet.py`:**
- `handle_right_click`: expand "is this row already selected?" check to include cell-selection rows (`{r for r, _c in self.sheet.get_selected_cells()}`), so `set_currently_selected` is only called when the right-clicked row is truly outside the current selection.
- `snapshot_row_ids()`: when `snapshot["rows"]` is empty, derive unique rows from `snapshot["cells"]`.

Affected commands: Remove Selected Rows, Bulk Edit Selection (partial), Ignore Item.

- [x] Fix `handle_right_click` to treat cell-selected rows as part of the current selection.
- [x] Fix `snapshot_row_ids()` to fall back to deriving rows from `snapshot["cells"]`.
- [x] Add regression tests for cell-based multi-row snapshot.

### 1b. `resolve_review_from_bulk` and `dismiss_duplicate_from_bulk` use stale legacy attribute

**Bug:** Both functions (in `ui_bulk_dialogs.py`) resolve `row_id` from `app._right_click_row_id` — a legacy attribute that is never set in the current code path. The correct attribute is `app._right_click_bulk_context["row_id"]`. Both commands silently do nothing when triggered via the context menu unless the legacy attr happens to be set from elsewhere.

**Fix:**
- Update both functions to read from `_right_click_bulk_context` first, then fall back to `bulk_sheet.current_row_id()`, matching the pattern used by every other context-menu command.
- Add snapshot/multi-select support to `resolve_review_from_bulk` (mark all selected review items resolved in one action).
- `dismiss_duplicate_from_bulk` is intentionally single-row (each duplicate warning is item-specific) — no multi-select needed, but the row-id lookup must be fixed.

- [x] Fix `resolve_review_from_bulk` row-id lookup to use `_right_click_bulk_context`.
- [x] Fix `dismiss_duplicate_from_bulk` row-id lookup to use `_right_click_bulk_context`.
- [x] Add snapshot multi-select support to `resolve_review_from_bulk`.
- [x] Add tests for both commands confirming correct row resolution.

---

## Phase 1c. Bulk Grid: Remove-Filtered-View Bugs

Issues found during investigation of a report that items removed while a filter is active reappear when switching back to "ALL".

### 1c-i. Undo restore bypasses property setter (`ui_assignment_actions.py`)

**Bug:** "Undo Last Remove" uses `app.filtered_items.insert(insert_at, item)` — direct list mutation that bypasses the `filtered_items` property setter. The setter is what triggers `sync_bulk_session_metadata`, which rebuilds the `_bulk_items_by_item_status`, `_bulk_items_by_line_code`, and all other bucket caches. After an undo restore, all non-ALL filter views show stale results: the restored item is in `filtered_items` but absent from every bucket.

**Fix:** Replace the direct `.insert()` calls with `replace_filtered_items(app, new_list)` so the property setter fires and buckets are rebuilt.

### 1c-ii. No "Select All Visible" shortcut in filtered view (`bulk_sheet.py`, `po_builder.py`)

**Issue:** There is no keyboard shortcut or context-menu entry that selects all rows currently visible in the filtered bulk view. tksheet's native Ctrl+A selects all cells, not row headers. The "Remove Selected Rows" path (`bulk_remove_selected_rows`) works correctly when all visible rows are selected, but reaching that state is unintuitive — users must either shift-click through every row or use the row-header click + shift-click pattern. The practical result: users filtering to a subset (e.g. "Skip") and wanting to delete all of them have no obvious way to do so.

**Fix:** Add a "Select All Rows" context-menu entry that calls `bulk_sheet.select_all_visible()`, and bind Ctrl+Shift+A to it so it doesn't conflict with tksheet's native Ctrl+A.

- [x] Fix undo restore (`ui_assignment_actions.py`) to use `replace_filtered_items` so buckets are rebuilt.
- [x] Add "Select All Rows" to the context menu and bind Ctrl+Shift+A to `select_all_visible()`.
- [x] Add tests for undo restore bucket correctness.

---

## Phase 2. Stockout Risk Scoring

Items are currently sorted by line code / item code. Operators who want to prioritize their review pass have no signal-based ordering — they cannot tell at a glance which items are most likely to stock out before the next cycle.

- [x] Add a `stockout_risk_score` (0–1 float) to enriched items based on:
  - days of cover remaining: `inventory_position / daily_demand` vs `lead_time_estimate`
  - recency confidence (low confidence → higher risk weight)
- [x] Surface `stockout_risk_score` as a sortable `Risk` column in the bulk grid.
- [x] Add a "High Risk" filter option in the Attention combobox (score ≥ 0.60).
- [x] Add tests for score calculation with edge cases (zero demand, zero QOH, full cover, clamping).

---

## Phase 3. Trend and Variance Reporting

Session snapshots accumulate historical data that is currently only used for the `suggestion_vs_history_gap` flag. A trend report would let operators see whether suggestions are improving or drifting over time.

- [x] Add a `Trend Report` export (CSV) available from the review tab:
  - one row per item that appears in at least 2 session snapshots
  - columns: line code, item code, last 3 suggested qtys, last 3 ordered qtys, trend direction, current suggestion
- [x] Flag items where the operator consistently overrides the suggestion in the same direction (always increasing, always decreasing) — these are candidates for rule adjustment.
- [x] Add a `suggestion_override_pattern` field (`"always_up"`, `"always_down"`, `"mixed"`, `None`) to enriched items and surface it in item details.
- [x] Add tests for trend extraction and override pattern detection.

---

## Phase 4. Dead Stock and Discontinue Candidates

Items with no sales movement over several sessions are candidates for discontinuation, but they still appear in every run and consume review attention.

- [x] Add a `dead_stock` classification: item has no sale in the configured window (default: 12 months) and no pending demand (suspense or open PO).
- [x] Surface dead-stock items in a separate filter bucket ("Dead Stock") in the bulk grid.
- [x] Add a bulk action to "Flag for discontinue review" — sets a persistent `discontinue_candidate` flag in `order_rules.json` and adds to the Dead Stock report.
- [x] Add a Dead Stock section to the maintenance report via `build_dead_stock_report_rows`.
- [x] Add tests for dead-stock classification and maintenance report output.

---

## Phase 5. Vendor Lead Time Inference

Vendor lead time is not currently modeled. The stockout risk score (Phase 2) needs a lead-time estimate; right now it would use a flat default. Session history contains enough data to infer per-vendor lead times from receipt gaps.

- [x] Infer per-vendor `estimated_lead_days` from session snapshots: median elapsed days between an item appearing on an open PO and its next receipt in a subsequent session.
- [x] Store inferred lead times in `vendor_policies.json` alongside shipping/release policies.
- [x] Surface inferred lead time in the vendor policy editor.
- [x] Use inferred lead time in the stockout risk score (Phase 2) instead of the flat default.
- [x] Add tests for lead time inference with synthetic multi-session history.

---

## Phase 6. Session History Viewer

Past sessions are stored as JSON snapshots but are inaccessible from the UI. Operators who want to audit a past export or check what was ordered for a specific item must open JSON files manually.

- [ ] Add a `Session History` tab (or dialog accessible from the Load tab) that lists recent session snapshots with date, item count, and vendor count.
- [ ] Allow expanding a session to see its items: line code, item code, vendor, final qty, suggested qty, policy at time of export.
- [ ] Allow filtering the history view by item code or vendor.
- [ ] Add a "Copy item history" button that copies the selected item's order history rows as tab-separated text for pasting into other tools.
- [ ] No new file I/O beyond what `storage.py` already supports for snapshot loading.

---

## Phase 7. Manual QA (carry-over from v0.3.x Phase 1)

These require a human with real-world CSV files and cannot be covered by unit tests alone.

- [ ] Run full load → assign → review → export workflow against representative real-world CSVs in the packaged exe.
- [ ] Confirm that detailed sales / received parts parsing, vendor resolution, and export formatting all behave correctly with live data shapes not covered by synthetic tests.
- [ ] Add any targeted regression tests discovered during live testing.

---

## Definition of "Done Enough" for v0.4.x

- All Phase 1 bug fixes shipped and covered by regression tests.
- Operators can sort and filter by stockout risk in the bulk grid.
- Dead-stock candidates appear in the maintenance report and can be flagged for discontinue review.
- A trend report export is available showing suggestion vs. ordered-qty history per item.
- Session history is browsable from the UI without opening JSON files manually.
- Phase 7 manual QA has been completed against at least one real-world dataset.
