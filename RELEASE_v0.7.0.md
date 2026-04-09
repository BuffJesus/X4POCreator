# Release Notes — v0.7.0

**Date:** 2026-04-08

---

## Summary

v0.7.0 opens the v0.7.x feature train with **Phase 1: Session Diff** —
a new dialog that compares the current in-progress session against the
most recent snapshot in `sessions/` and shows what changed.  Most
operators run on a weekly cadence; until now the only artifact of
"what was different this week" lived in their head.

1006 tests pass (21 new regression tests).

---

## What's new

### Session Diff dialog

A new **Session Diff...** button on the Load tab footer (below
**View Session History**) opens a dialog with a tab per change
category:

- **New**           — items in this session but not the prior one
- **Removed**       — items in the prior session but not this one
- **Qty Up**        — same item, current qty > previous qty
- **Qty Down**      — same item, current qty < previous qty
- **Vendor Changed**— same item, vendor differs (case-insensitive)

Each tab carries a count badge so the operator can see at a glance
where their attention should go.  The header shows the previous
snapshot's `created_at` so there's no ambiguity about what "previous"
means.  Empty state — no prior snapshots in `sessions/` — shows a
short explainer instead of a blank dialog.

An item that both moved qty and switched vendor appears in both
buckets, on purpose: those are independent decisions and the operator
should see both.

---

## Architecture

`session_diff_flow.py` (new) hosts five pure helpers, all unit-tested
without a UI:

- `load_previous_snapshot(sessions_dir, *, loader=None)` — returns
  the most recent snapshot or `None`.  Loader is injectable so tests
  don't need to fake the filesystem.
- `diff_sessions(previous, current)` — returns the five-bucket
  categorized diff.  Tolerates `None` on either side.  Prefers
  `exported_items` over `assigned_items` so an aborted-before-export
  current session can still be diffed against a clean prior snapshot.
- `format_diff_summary(diff)` — one-line human banner string,
  e.g. `"3 new, 1 qty up, 2 qty down, 1 vendor changed"`.  Returns
  `""` when nothing changed.
- `diff_total_count(diff)` — sum across all buckets.
- `snapshot_label(snapshot)` — short label for header text.

`ui_session_diff.py` (new) wires the helpers into the dialog.  It
builds a snapshot-shaped dict from `app.assigned_items` (preferred)
or `app.filtered_items` and feeds it through `diff_sessions` against
the most recent disk snapshot.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.6.7  |   985 |
| v0.7.0  |  1006 |

21 new tests in `tests/test_session_diff_flow.py` covering:

- Loader injection + the empty-disk path
- All five diff buckets, including the simultaneous qty + vendor
  change case
- Both snapshot-key fallbacks (`exported_items` preferred,
  `assigned_items` fallback)
- Case-insensitive vendor compare
- Items without `item_code` are skipped
- `order_qty` used when `final_qty` is missing
- Sort order across line codes and item codes
- `format_diff_summary` blank-input and full-input paths
- `diff_total_count` and `snapshot_label`

---

## Files changed / added

- `session_diff_flow.py` (new) — pure helpers
- `ui_session_diff.py` (new) — dialog
- `ui_load.py` — "Session Diff..." button on the Load tab footer
- `po_builder.py` — `_open_session_diff` hook + import
- `tests/test_session_diff_flow.py` (new) — 21 regression tests
- `app_version.py` — bumped to 0.7.0
- `ROADMAP_v0.7.md` — Phase 1 closed (one polish item deferred)

---

## Roadmap status after this release

| Phase | Status |
|---|---|
| Phase 1 — Session Diff | ✓ closed (auto-banner deferred to v0.7.1) |
| Phase 2 — Vendor-centric Workflows | open |
| Phase 3 — Skip Cleanup Tools | open |
| Phase 4 — Performance & Correctness Carry-over | open |

The auto-banner that surfaces a diff summary in the bulk grid header
on session load is deferred to a follow-up — the dialog covers the
on-demand case and the banner is polish.

---

## Why this was the right Phase 1

I drafted v0.7.x with three feature phases (Session Diff, Vendor
Workflows, Skip Cleanup) and called Session Diff the highest leverage
because:

1. It's a *new* capability, not a refinement of an existing flow.
2. It's the smallest scope of the three feature phases (one flow +
   one dialog + one button).
3. Operators see the value on the very first session after upgrade,
   without needing to configure anything.
4. The pure helpers were trivially testable, so the regression
   coverage is dense.

Phase 2 and Phase 3 both build on existing flows and are good
candidates for the next focused session.
