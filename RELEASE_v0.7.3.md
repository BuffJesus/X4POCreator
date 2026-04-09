# Release Notes — v0.7.3

**Date:** 2026-04-08

---

## Summary

v0.7.3 closes the two Phase 2 polish items deferred from v0.7.1 and
brings vendor lead-time visibility into the moment of assignment.
Operators picking a vendor in the bulk grid now see the inferred
lead time inline; right-clicking a row jumps straight to the Vendor
Review dialog pre-selected to that row's vendor.

1058 tests pass (8 new regression tests).

---

## What's new

### Inline lead-time hint on the vendor combobox

The vendor autocomplete dropdown on the bulk tab now renders entries
as `GRELIN (lead ~7d)` for every vendor with an inferred lead time
in the snapshot history.  Vendors without history stay as plain
codes.

Inferred lead times come from the existing
`storage.infer_vendor_lead_times` helper — snapshot pairs where an
item moved from On PO to Received between sessions.  The lookup is
cached on the app on first autocomplete keystroke so the snapshot
walk doesn't re-run on every key event.

The apply path strips the hint via the new
`vendor_summary_flow.strip_vendor_hint` helper before reading the
vendor, so picking a hinted entry still assigns the bare code.

### Right-click "Show Vendor Summary..."

A new entry on the bulk grid context menu (next to "Flag for
Discontinue Review") opens the Vendor Review dialog pre-selected to
the right-clicked row's vendor.  Operators can drill into a vendor
without leaving the row they're working on.

`open_vendor_review_dialog` gained an optional `focus_vendor` keyword
arg for this — the existing call from the toolbar button passes
nothing and gets the default first-row selection.

---

## Architecture

Two new helpers in `vendor_summary_flow.py`:

- `strip_vendor_hint(value)` — pulls the bare vendor code out of a
  hinted combobox label.  Tolerates `None`, blank, and bare codes.
- `format_vendor_combo_value(vendor_code, lead_days)` — renders the
  combo display string.  Returns the bare code when *lead_days* is
  None / zero so the dropdown stays clean for vendors with no
  history.

`ui_assignment_actions.py` got two new private helpers:

- `_vendor_lead_time_lookup(app)` — lazy + cached snapshot walk;
  failure-tolerant (returns `{}` on any exception so the autocomplete
  never crashes).
- `_hinted_vendor_values(app, codes)` — maps a list of vendor codes
  to their hinted display values for the combobox.

`bulk_vendor_autocomplete` now strips hints from the typed value
before filtering, and feeds the filtered codes through
`_hinted_vendor_values` before assigning to the combobox.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.7.2  |  1050 |
| v0.7.3  |  1058 |

8 new tests in `tests/test_vendor_summary_flow.py`:

- `StripVendorHintTests` — parenthetical suffix stripping, bare-code
  pass-through, None / blank tolerance, whitespace handling
- `FormatVendorComboValueTests` — known lead time, unknown lead time,
  zero lead time, blank vendor

---

## Files changed

- `vendor_summary_flow.py` — `strip_vendor_hint` + `format_vendor_combo_value`
- `ui_assignment_actions.py` — lazy lead-time cache, hinted values,
  hint-stripped reads at the apply sites
- `ui_vendor_review.py` — `open_vendor_review_dialog` accepts
  `focus_vendor`
- `bulk_sheet.py` — "Show Vendor Summary..." context-menu entry
- `po_builder.py` — `_show_vendor_summary_from_bulk` hook
- `tests/test_vendor_summary_flow.py` — 8 new regression tests
- `app_version.py` — bumped to 0.7.3
- `ROADMAP_v0.7.md` — Phase 2 deferred items closed

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed (v0.7.0) |
| Phase 2 — Vendor-centric Workflows | ✓ fully closed (v0.7.1 + v0.7.3) |
| Phase 3 — Skip Cleanup Tools | ✓ closed (v0.7.2) |
| Phase 4 — Performance & Correctness Carry-over | open |

Phase 4 remains: pack-rounding overshoot defer (behind a feature
flag), bulk grid render perf audit on the 8,409-item dataset, the
Phase 5 manual QA pass, and a `recent_orders` / suggestion-history
cache invalidation audit (same shape as the v0.6.6 fix).
