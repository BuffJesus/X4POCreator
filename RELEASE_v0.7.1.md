# Release Notes — v0.7.1

**Date:** 2026-04-08

---

## Summary

v0.7.1 closes Phase 2 of the v0.7.x roadmap: **Vendor-centric
Workflows**.  Lead times and recent vendor activity have been
inferable from snapshot history since v0.4.x but nothing surfaced
them per-vendor at the moment of assignment — operators had to dig
through `sessions/*.json` by hand.

1026 tests pass (20 new regression tests).

---

## What's new

### Vendor Review dialog

A new **Vendor Review...** button on the bulk tab vendor row (next to
"Manage Vendors...") opens a dialog with two panels:

**Top — vendor table** (Vendor | Orders | Qty Ordered | Qty Received |
Last Session | Lead Time), sorted most-active first.  Lead times are
inferred from snapshot pairs where an item moved from On PO to
Received between sessions (the existing
`storage.infer_vendor_lead_times` helper).

**Bottom — top items panel.**  Click any vendor row in the top table
and the bottom panel updates to show that vendor's top items by total
qty ordered across the loaded snapshots (line code, item code,
description, qty).

The dialog scopes to the **25 most recent snapshots** and the vendors
in the current session (via `session.vendor_codes_used`) so it
focuses on what the operator is actually working with this session,
not the entire historical archive.

Empty-state message when `sessions/` is empty.

---

## Architecture

`vendor_summary_flow.py` (new) hosts three pure helpers, all
unit-tested without a UI:

- `summarize_vendor(vendor_code, snapshots, *, lead_times, top_n)` —
  per-vendor summary dict.  Tolerates blank vendor codes, normalizes
  to upper case, prefers `exported_items` over `assigned_items`, and
  picks `last_session_date` as the most recent snapshot that
  actually contained the vendor.
- `summarize_all_vendors(snapshots, *, vendor_codes, lead_times,
  top_n)` — fans out the per-vendor summary across every vendor that
  appears in the snapshots, optionally restricted to a supplied
  vendor list.  Sorted by `(-order_count, vendor_code)`.
- `format_lead_time_label(lead_days)` — short renderer (`~7d`,
  `""` for unknown).  Designed for inline combobox hints in the
  v0.7.2 follow-up.

`ui_vendor_review.py` (new) wires the helpers into the dialog with a
ttk PanedWindow so the operator can resize the vendor table vs the
top-items panel.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.7.0  |  1006 |
| v0.7.1  |  1026 |

20 new tests in `tests/test_vendor_summary_flow.py` covering:

- Blank vendor / no snapshots → empty summary
- Vendor-code normalization (case + whitespace)
- `session_count` only counts snapshots that actually contained the
  vendor
- `last_session_date` picks the most recent of the matching
  snapshots
- `total_qty_received` sums correctly across snapshots
- `top_items` sorted by qty descending and aggregated across
  snapshots
- `lead_times` lookup propagated; missing vendor returns None
- `exported_items` vs `assigned_items` fallback
- `summarize_all_vendors` discovery, vendor_codes filter, sort order
- `format_lead_time_label` for None / positive / zero / non-numeric

---

## Files changed / added

- `vendor_summary_flow.py` (new) — pure helpers
- `ui_vendor_review.py` (new) — dialog
- `ui_bulk.py` — "Vendor Review..." button on the vendor row
- `po_builder.py` — `_open_vendor_review` hook + import
- `tests/test_vendor_summary_flow.py` (new) — 20 regression tests
- `app_version.py` — bumped to 0.7.1
- `ROADMAP_v0.7.md` — Phase 2 closed (combobox hint deferred to v0.7.2)

---

## What's deferred to v0.7.2

Two small Phase 2 polish items deferred to keep this release tight:

- **Inline lead-time hint on the vendor combobox autocomplete** (e.g.
  `GRELIN (lead ~7d)`).  Touches `_bulk_vendor_autocomplete` and the
  vendor list rendering — more invasive than the rest of Phase 2.
  The Vendor Review dialog already exposes the same data.
- **Right-click "Show vendor summary..." menu entry** on the bulk
  grid.  Same logic as the dialog but scoped to the row's vendor.

Both are small wins and good first work for v0.7.2.

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed (v0.7.0) |
| Phase 2 — Vendor-centric Workflows | ✓ closed (v0.7.1, two polish items deferred) |
| Phase 3 — Skip Cleanup Tools | open |
| Phase 4 — Performance & Correctness Carry-over | open |

Phase 3 (Skip Cleanup Tools) is the natural next session — it builds
on the v0.5.4 → v0.6.5 skip-filter fixes and unblocks bulk action on
the 5,317 logically-skip items the operator can now see.
