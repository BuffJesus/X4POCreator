# PO Builder Roadmap — v0.7.x

Status: Planning

Current app version: `0.6.7`

---

## What v0.7.x is about

v0.5.x addressed configuration pain points.  v0.6.x added Find &
Configure features (search, supplier map, QOH review) and squashed the
four-bug skip-filter saga that was hiding items from the bulk grid.
v0.7.x focuses on **Session Intelligence**: turning every run from a
fresh-start exercise into one informed by what changed since last
time.

Three themes drive the phases below.  Each is grounded in something
the v0.6.x bug hunt surfaced as friction:

- **Session Diff** — operators run weekly against the same item list.
  After a session they want to know "what changed since last time?"
  but the only artifact is the per-vendor PO file.  No high-level
  view of which items appeared, disappeared, or shifted.
- **Vendor-centric workflows** — the supplier map (v0.6.1) gave us
  the vendor↔supplier relationship.  Lead times, recent receipts,
  and cycle-over-cycle vendor performance are sitting in the
  snapshots already; nothing surfaces them.
- **Skip cleanup** — fixing the skip filter (v0.5.4 / v0.6.3 / v0.6.4
  / v0.6.5) made 5,317 items visible on the user's real dataset.
  Operators now need bulk tooling to actually do something with them
  beyond Remove Not Needed.

A fourth phase covers performance and correctness work that's been
sitting in the backlog.

---

## Phase 1. Session Diff

Compare the current session against the most recent snapshot in
`sessions/` and surface what changed.  This is the highest-leverage
addition because most operators run on a weekly cadence — knowing
"these 12 items are new since last week" or "this item's order qty
doubled" is exactly the context they currently keep in their heads.

- [x] Added `session_diff_flow.py` with pure helpers:
  - `load_previous_snapshot(sessions_dir)` — most recent snapshot or
    `None`.  Loader is injectable for tests.
  - `diff_sessions(previous, current)` — five-bucket categorized
    diff (`new_items`, `removed_items`, `qty_increased`,
    `qty_decreased`, `vendor_changed`).  Prefers `exported_items`
    over `assigned_items`.
  - `format_diff_summary(diff)` — one-line human banner string;
    returns `""` when nothing changed so callers can use it as a
    truthiness check.
  - Bonus: `diff_total_count(diff)` and `snapshot_label(snapshot)`.
- [x] Added `ui_session_diff.py` — "Session Diff" dialog with a tab
  per category (New / Removed / Qty Up / Qty Down / Vendor Changed),
  count badges on each tab, and a header banner showing the previous
  snapshot's `created_at`.  Empty-state message when no prior
  snapshots exist.
- [x] Added "Session Diff..." button to the Load tab footer below
  "View Session History".
- [ ] Auto-show the diff banner in the bulk grid header when a new
  session loads against an existing snapshot history.  Deferred —
  the dialog covers the on-demand case; auto-banner is a polish
  step that can wait for v0.7.1.
- [x] 21 new tests in `tests/test_session_diff_flow.py` covering
  every helper, all five buckets, both snapshot-key fallbacks,
  case-insensitive vendor compare, item-without-item-code skip,
  `order_qty` qty fallback, sort order, and the empty-input path.

---

## Phase 2. Vendor-centric Workflows

Build on the v0.6.1 supplier map.  Lead times are already inferred
from snapshot history (`storage.infer_vendor_lead_times`) but nothing
displays them per-vendor before assignment.

- [x] Added `vendor_summary_flow.py` with three pure helpers:
  - `summarize_vendor(vendor_code, snapshots, *, lead_times, top_n)`
    — per-vendor summary dict (session_count, order_count,
    total_qty_ordered/received, last_session_date, inferred_lead_days,
    top_items).
  - `summarize_all_vendors(snapshots, *, vendor_codes, lead_times,
    top_n)` — fans out across every vendor that appears in the
    snapshots, sorted by `(-order_count, vendor_code)`.
  - `format_lead_time_label(lead_days)` — short renderer for combobox
    hints / table cells (`~7d`, `""` when unknown).
- [x] Added `ui_vendor_review.py` — "Vendor Review" dialog with a top
  table (Vendor / Orders / Qty Ordered / Qty Received / Last Session
  / Lead Time) and a bottom panel showing the selected vendor's
  top items.  Empty-state message when `sessions/` is empty.
- [x] Added "Vendor Review..." button to the bulk tab vendor row
  next to "Manage Vendors...".
- [x] Inline lead-time hint on the vendor combobox autocomplete
  dropdown.  Vendors with inferred lead times now render as
  `GRELIN (lead ~7d)`.  The lead-time lookup is cached on the app
  on first autocomplete keystroke; the apply path strips the
  hint via the new `vendor_summary_flow.strip_vendor_hint`
  helper before reading the vendor.
- [x] Right-click "Show Vendor Summary..." menu entry on the bulk
  grid.  Opens the Vendor Review dialog pre-selected to the
  right-clicked row's vendor (via the new `focus_vendor` arg on
  `open_vendor_review_dialog`).
- [x] 20 new tests in `tests/test_vendor_summary_flow.py` covering
  the empty/no-snapshots paths, vendor-code normalization, session
  count, last-session-date selection, qty aggregation, top-items
  ordering and aggregation across snapshots, lead-times lookup,
  exported_items vs assigned_items fallback, and the
  summarize_all_vendors filter / sort behavior.

---

## Phase 3. Skip Cleanup Tools

The v0.5.4 → v0.6.5 skip-filter fixes made 5,317 logically-skip items
visible on the user's real dataset.  Today the only thing the operator
can do with them is "Remove Not Needed" one filter scope at a time.
Bulk tooling for the Skip filter is the obvious next step.

- [x] Added a "Skip Cleanup..." button on the bulk tab removal row
  (always visible — operators don't need to set the Skip filter
  first).  Opens a dialog with a per-line-code cluster table and
  three action buttons:
  - **Add to Ignore List** — pipes through `_ignore_items_by_keys`.
  - **Flag Discontinue** — sets `discontinue_candidate = True` on
    each item's order rule and saves `order_rules.json`.
  - **Export CSV** — `skip_actions_flow.render_skip_csv` writes
    line code, item code, description, qoh, current/suggested
    min/max, supplier, last sale date, last receipt date.
- [x] Added `count_skip_clusters_by_line_code(items)` and the rest of
  `skip_actions_flow.py` (5 pure helpers in total).  The dialog
  header shows "N skip items across M line codes" so operators see
  the cluster shape immediately.
- [x] Per-line-code grouped view (as a dialog rather than an
  in-grid tree mode).  Selecting one or more line codes scopes
  every action; leaving the selection empty applies to every skip
  item.
- [x] 24 new tests in `tests/test_skip_actions_flow.py` covering
  every helper: `is_skip_item` predicate, `filter_skip_items`,
  cluster counting + tie-break + non-skip filtering, key
  collection, the export-row builder (inventory lookup vs
  inventory-on-item fallback, last-sale-date precedence, suggested
  min/max), and the CSV renderer (header order, empty rows,
  extras-ignored).

---

## Phase 4. Performance & Correctness Carry-over

Smaller items that have been deferred from prior phases.

- [ ] **Pack-rounding overshoot defer** in `calculate_suggested_qty`
  (`rules.py:1069`).  v0.5.5 added the `would_overshoot_max` data
  flag but the suggestion still goes through to manual review at
  full pack qty.  Operators with reels at 60%+ on hand probably
  want a "defer this cycle" suggestion instead of a manual-only
  pack order.  Behind a feature flag in `app_settings` so the
  default doesn't change for existing users.
- [ ] **Bulk grid render perf audit on 8,409 items** — measure first
  paint time and filter-change time on the user's real dataset.
  The bucket fast path now handles the common case but a tksheet
  set_rows of 8K rows is still the dominant cost.  Likely
  improvements: lazy row rendering, viewport-only signature
  computation, or a column subset for the initial paint.
- [ ] **Phase 5 manual QA carry-over** — full load → assign → review
  → export workflow against the user's real `Order/` files in the
  packaged exe.  Add any targeted regression tests discovered
  during the pass.
- [ ] **Audit `suggestion_history_lookup` and `recent_orders` cache
  invalidation** — same kind of staleness check I did on
  `bulk_row_render_signature` in v0.6.6.

---

## Definition of "Done Enough" for v0.7.x

- Operators see what changed since their last session at a glance.
- Vendor lead times and recent activity are visible at the moment of
  vendor assignment, not buried in snapshot files.
- The Skip filter has bulk tooling that matches the scale of what
  v0.6.5 made visible.
- One end-to-end manual QA pass against the real `Order/` dataset.

---

## Out of scope (deferred to v0.8.x or later)

- Multi-branch / multi-warehouse support.
- Direct X4 API integration (still CSV in / Excel out).
- Web / cloud version.
- Configurable Excel templates (currently the X4 import format is
  hard-coded).
- Email / Slack notifications on session completion.
