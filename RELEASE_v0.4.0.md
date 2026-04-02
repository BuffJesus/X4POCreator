# Release Notes — v0.4.0

**Date:** 2026-04-01

---

## Summary

v0.4.0 delivers all five code-deliverable phases of the v0.4.x roadmap:

- Two silent context-menu regressions fixed (multi-row selection and stale row-id lookup).
- Stockout risk scoring surfaces the items most likely to run out before the next order cycle.
- A Trend Report CSV export shows whether suggestions are improving or drifting over time.
- Dead-stock classification routes slow-moving items to their own filter bucket and the maintenance report.
- Vendor lead times are now inferred automatically from session history and feed back into risk scoring.

830 tests pass. Phase 7 (manual QA with real-world CSVs) and Phase 6 (Session History Viewer) remain open.

---

## What changed since v0.3.0

### Phase 1 — Context Menu Bug Fixes

#### 1a. Multi-row context menu silently collapsed to one row (`bulk_sheet.py`)

Shift-click and drag selection populate `snapshot["cells"]` rather than `snapshot["rows"]`. Any context-menu command that called `snapshot_row_ids()` would silently act on a single row.

- `handle_right_click` now includes cell-selection rows in the "is this row already selected?" check, so right-clicking inside a cell-selection no longer replaces it.
- `snapshot_row_ids()` falls back to deriving unique rows from `snapshot["cells"]` when `snapshot["rows"]` is empty.

Affected commands: Remove Selected Rows, Bulk Edit Selection, Ignore Item.

#### 1b. Resolve Review and Dismiss Duplicate used a stale attribute (`ui_bulk_dialogs.py`)

Both functions read `app._right_click_row_id`, a legacy attribute never set in the current code path. Both commands silently did nothing from the context menu.

- Both now read from `app._right_click_bulk_context["row_id"]`, then fall back to `bulk_sheet.current_row_id()`.
- `resolve_review_from_bulk` gains multi-select support: all selected review items are resolved in one action.

---

### Phase 2 — Stockout Risk Scoring (`rules.py`)

Items are now scored 0–1 for stockout risk each session.

- **`compute_stockout_risk_score(item, lead_time_days)`** — score is based on days of inventory cover vs vendor lead time, with a recency-confidence penalty (high = 0, medium = +10%, low = +20%). Score is 0.0 when demand is zero or cover ≥ 2× lead time; 1.0 at zero cover with active demand.
- **`DEFAULT_LEAD_TIME_DAYS = 14`** — flat fallback used when no vendor-specific lead time has been inferred yet.
- **`Risk` column** added to the bulk grid — sortable float, two decimal places.
- **"High Risk" filter** added to the Attention combobox — shows items with score ≥ 0.60.

---

### Phase 3 — Trend and Variance Reporting (`trend_flow.py`, `po_builder.py`)

Session snapshots now drive a user-facing trend report.

- **Trend Report CSV** — available from the review tab. One row per item appearing in ≥ 2 snapshots. Columns: Line Code, Item Code, last 3 suggested qtys, last 3 ordered qtys, trend direction, current suggestion.
- **`suggestion_override_pattern`** — stamped on each enriched item: `"always_up"`, `"always_down"`, `"mixed"`, or `None`. Surfaced in item details as "Override pattern: always ordering above suggestion" etc.
- Items with a consistent override pattern in the same direction are flagged as candidates for rule adjustment.

---

### Phase 4 — Dead Stock and Discontinue Candidates (`rules.py`, `maintenance.py`)

Slow-moving items now have a dedicated classification and workflow.

- **`classify_dead_stock(item)`** — returns `True` when `days_since_last_sale ≥ DEAD_STOCK_MIN_DAYS_SINCE_SALE` (default 365) and no pending demand (`qty_on_po`, `qty_suspended`, `effective_qty_suspended` all zero). `dead_stock` is stamped by `enrich_item`.
- **"Dead Stock" filter bucket** in the bulk grid — shows only dead-stock items for focused review.
- **"Flag for Discontinue Review" bulk action** — sets `discontinue_candidate: true` in `order_rules.json` for each selected item.
- **`build_dead_stock_report_rows(items, order_rules)`** in `maintenance.py` — returns rows for a Dead Stock section of the maintenance report, sorted by line code then item code, with a "Discontinue Flagged" column.

---

### Phase 5 — Vendor Lead Time Inference (`storage.py`, `shipping_flow.py`, `rules.py`, `load_flow.py`, `assignment_flow.py`, `item_workflow.py`, `ui_vendor_manager.py`)

The flat 14-day lead time default in stockout risk scoring is now replaced by per-vendor estimates derived from session history.

- **`infer_vendor_lead_times(snapshots)`** in `storage.py` — scans consecutive snapshot pairs (chronological order). Finds items with `qty_on_po > 0` in the earlier session and `qty_received > 0` in the later session. The elapsed calendar days between the two sessions is one observation. Returns `{vendor_code: median_lead_days}` for vendors with ≥ 1 observation.
- **Stored in `vendor_policies.json`** — after each CSV load, inferred lead times are merged into `session.vendor_policies[vendor]["estimated_lead_days"]` and persist through the normal save flow.
- **`normalize_vendor_policy`** preserves `estimated_lead_days` (integer ≥ 1) when present; omits it otherwise so existing policy round-trips are unaffected.
- **Stockout risk scoring uses vendor lead time** — `enrich_item` accepts `lead_time_days=None`; `assignment_flow` and `item_workflow` look up the vendor's `estimated_lead_days` and pass it through. Falls back to `DEFAULT_LEAD_TIME_DAYS` when no inference is available.
- **Vendor policy editor** shows a read-only "Inferred Lead Time" row (e.g. "21 days (from session history)" or "— (no history yet)"). Saving manual policy fields preserves the inferred value.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.3.0  | 756   |
| v0.4.0  | 830   |

74 new tests across `test_bulk_sheet.py`, `test_ui_bulk_dialogs.py`, `test_rules.py`, `test_maintenance.py`, and `test_storage.py`.
