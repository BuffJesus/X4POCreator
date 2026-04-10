# Release Notes — v0.9.0

**Date:** 2026-04-09

---

## Summary

**Major release: visual modernization, ADHD-friendly workflow,
algorithm overhaul, and complete structural refactor.**

The bulk assignment workflow goes from "stare at 59K rows and assign
vendors one by one" to "auto-assigned 4,200 items, review 150
exceptions, done." The UI is modernized with ttkbootstrap, the
codebase is split into clean packages, and the ordering algorithms
now handle 8-year datasets correctly.

1,149 tests pass. 39 commits since v0.8.13.

---

## Visual Modernization

- **ttkbootstrap darkly theme** — modern flat buttons, styled
  scrollbars, professional dark mode throughout
- **Row coloring** — subtle green (assigned), amber (review), red
  (warning), gray (skip) tints on the bulk grid
- **Workflow progress stepper** — `1. Load Files › 2. Filter ›
  3. Assign Vendors › 4. Review & Export` at top of window
- **Assignment progress bar** — percentage + visual bar next to
  summary
- **Filter badge** — "Filters (3)" on the filter panel header
- **Landing page redesign** — hero section with Quick Start card
- **Loading progress** — text updates during pipeline: "Preparing
  session..." → "Auto-assigning vendors..." → "Building grid..."

---

## ADHD-Friendly Workflow

### Auto-assign vendors from receipt history

After loading, the app auto-assigns vendors to items with
high-confidence receipt history. Green banner shows:
"Auto-assigned 4,200 items · 150 need manual assignment."
Reduces manual work from thousands of items to just exceptions.

### Quick Load

Remembers the last scan folder. On the Load tab, a prominent
"Quick Start" card offers one-click "Scan & Load Now."

### Vendor worksheet dropdown

Combobox at the top of the bulk grid: All Items, Overview (vendor
summary cards), per-vendor filters (with counts), Unassigned,
Exceptions. Click a vendor to see only their items.

### Two-tier action bar

Primary bar: Vendor + Apply + Remove Not Needed + Undo (always
visible). "▸ More Actions" collapses 20+ advanced buttons.

### Quick filter pills

One-click buttons above the filter panel: All, Unassigned, Needs
Review, Warnings, High Risk. No dropdown navigation needed.

### Simplified "Why" column

| Before | After |
|---|---|
| Stock after open POs: 2 \| Target stock: 10 \| Package profile: Hardware pack \| ... | Low stock: have 2, need 10 → ordering 12 (pack of 12) |
| Manual review required | Needs review — may be dead stock |
| No order needed | Stock OK (20 on hand, target 10) |

Full detail still available via hover tooltip.

### Reduced default columns

11 columns visible (down from 19). Right-click any header to
show/hide columns. Hidden by default: raw_need, sug_min, sug_max,
source, supplier, risk, buy_rule, cur_min, cur_max.

### Dynamic filter dropdowns

Dropdowns only show options that have matching items. If there are
no "Warning" items, "Warning" disappears from the dropdown.

### Help & discoverability

- Press `?` for keyboard shortcut overlay
- Inline tips bar on first session (dismissible)
- New "Shortcuts" help tab page
- Hover tooltips on Why/Notes/Description columns

---

## Algorithm Fixes

### Stale demand threshold

Items with less than 1 unit/year annualized demand (and no explicit
trigger rule) now skip ordering instead of ordering to max. Prevents
items sold once in 2018 from generating POs in 2026. On the 8-year
dataset: **58,199 skip, 632 ordering** (was 58K ordering before).

### Pack rounding fix

Near-pack-boundary tolerance was inverted — `need=1, pack=40` was
returning 1 instead of 40. Fixed: first pack always rounds up;
tolerance only applies at multi-pack boundaries.

### Remove Not Needed fix

"Remove Not Needed" now correctly removes vendor-assigned items
that have `status=skip` and `final_qty=0`. Auto-assigned vendors
no longer protect zero-demand items from removal.

### Other algorithm improvements

- **Trigger threshold warning** — flags triggers 5× above max
- **Zero-demand min-protection** — surfaces "ordering to min
  despite zero demand" in the why text
- **Hysteresis decay** — 25% decay per session prevents stale
  high targets from accumulating indefinitely
- **`math` import crash** — `not_needed_reason` was missing import

---

## Performance

- **Bulk edit batching** — 8-row pack_size: 5.6s → 750ms (7.5×)
- **Mass removal** — skips undo snapshot for >10K items (~3.6s saved)
- **Text filter** — precomputed haystack ~8× faster
- **Overview cards** — O(n) instead of O(n × vendors)
- **Vendor tab refresh** — deferred to after UI paint

---

## Structural Refactors

### rules/ package (7 modules)

| Module | Contents |
|---|---|
| `__init__.py` | `enrich_item` orchestrator (110 lines, was 380) |
| `calc.py` | 9 pure calculation functions |
| `policy.py` | 16 policy/classification functions |
| `explanation.py` | `build_reason_codes` + `build_detail_parts` |
| `status.py` | `evaluate_item_status` |
| `not_needed.py` | `not_needed_reason` (moved from UI) |
| `_constants.py` / `_helpers.py` | Shared constants + rule accessors |

### parsers/ package (5 modules)

`csv_io.py`, `x4_dialect.py`, `aggregators.py`, `dates.py`,
`normalize.py`. Fixed pre-existing HEADER_ALIASES bug.

### models/ package

`session_bundle.py` with `LoadedData`, `DerivedAnalysis`,
`UserDecisions`, `SessionMetadata`. `AppSessionState` uses
forwarding properties for backward compat. `schemas.py` with
TypedDict definitions.

### app/ package

`bootstrap.py` (theme), `session_controller.py` (non-Tk
calculation helpers). `BulkCacheState` consolidation.

### Tests

1,149 tests (49 new): 20 enrich golden, 9 prepare_assignment
golden, 10 item_notes, 10 existing test updates.

---

## Smart vendor features

- **Vendor suggestion label** — shows receipt-history-based vendor
  recommendation when rows are selected
- **Batch Edit Rules** button promoted to primary action bar
- **Overview cards** — per-vendor summary: item count, est. value,
  ready / needs attention status

---

## Release history

| Release | Headline |
|---|---|
| v0.8.9 | Dialog lock-up fix |
| v0.8.10 | normalize_items_to_cycle eliminated (−23 s) |
| v0.8.11 | Full span instrumentation |
| v0.8.12 | O(n²) description scan eliminated (−29 s) |
| v0.8.13 | 5 bug fixes + 6 UX features + bulk edit 7.5× + rules/parsers/models refactor |
| v0.8.14 | Visual modernization + structural extractions + text filter perf |
| **v0.9.0** | **ADHD-friendly workflow + algorithm overhaul + 8-year dataset support** |
