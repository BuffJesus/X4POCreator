# Next session — kick-off prompt

Paste this into the next Claude Code session:

---

We're continuing PO Builder development. Current state:

- **Version:** v0.9.0
- **Tests:** 1,149 passing
- **Theme:** ttkbootstrap darkly + ADHD-friendly workflow
- **Big picture:** Major release shipped with auto-assign vendors, visual modernization, algorithm overhaul for 8-year datasets, and full structural refactor (rules/, parsers/, models/, app/ packages).

**Read first** (in this order):
1. `CLAUDE.md` — current architecture + invariants + lessons
2. `ROADMAP_v0.8.md` — v0.8.x scoreboard (89% complete, 8 items remain)
3. `RELEASE_v0.9.0.md` — full release notes for the latest version
4. `dist/perf_summary.txt` — latest live trace

**What shipped in v0.9.0:**
- Auto-assign vendors from receipt history (reduces manual work 95%)
- Quick Load (one-click from remembered folder)
- Vendor worksheet dropdown (filter by vendor/unassigned/exceptions)
- Two-tier action bar (5 primary buttons, rest collapsed)
- Quick filter pills (All, Unassigned, Review, Warnings, High Risk)
- Simplified why text ("Low stock: have 2, need 10 → ordering 12 (pack of 12)")
- Row coloring, workflow stepper, progress bar, column toggle
- Stale demand threshold (<1/yr annualized skips ordering)
- Pack rounding fix, trigger warnings, hysteresis decay
- rules/ (7 modules), parsers/ (5), models/ (3), app/ (2)

**Remaining roadmap items (low priority):**
- Phase 4 native acceleration (roadmap says wait for field time)
- SessionController delegation from POBuilderApp
- test_parse_golden.py (needs 293 MB dataset)
- Shift+click secondary sort (optional)
- items_by_status collapse (speculative)

**Key invariants to preserve:**
- Auto-assign runs after prepare_assignment_session, before bulk tree
- Stale demand threshold: MIN_ANNUALIZED_DEMAND_FOR_AUTO_ORDER = 1.0
- Render cache eviction: must evict in apply_editor_value AND refresh_bulk_view_after_edit
- ttkbootstrap detection in app/bootstrap.py — falls back to manual theme
- Dynamic dropdown refresh in apply_bulk_filter
- uses_only_bucket_filters returns False for vendor_tab and text filters
- _hide_loading() must be called on ALL exit paths from _proceed_to_assign_inner
- 1,149 tests must pass. Build script runs them before bundling.
