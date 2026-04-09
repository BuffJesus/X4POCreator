# Next session — kick-off prompt

Paste this into the next Claude Code session:

---

We're continuing PO Builder perf work. Current state:

- **Version:** v0.8.12
- **Tests:** 1110 passing
- **Goal (operator's words):** "Make it as fast as you can. I wanna put X4 to shame."
- **Big picture:** Session load on the 63K-item production dataset has gone from ~85 s (v0.8.9) to **~32 s pre-UI** (v0.8.12). Live operator trace at `dist/perf_summary.txt` confirms `prepare_assignment_session` is 5.6 s (was 34.5 s) and `populate_bulk_tree` is 1.5 s (was 8.9 s). The v0.8.12 O(n²) fix in `_description_for_key` indirectly warmed the description index in time for the bulk paint, so we got two wins for one fix.

**Read first** (in this order):
1. `CLAUDE.md` — current architecture + invariants + lessons from v0.8.x
2. `ROADMAP_v0.8.md` — full v0.8.x scoreboard, the "Live confirmation" table at the top, and the "New top targets" list
3. `RELEASE_v0.8.12.md` — the most recent shipped fix as a worked example
4. `dist/perf_summary.txt` — the freshest live trace

**Next targets, ranked by expected payoff:**

1. **`parse_detailed_pair_aggregates` — 15.8 s, 88 % of parse.** Three-pass loop in `parsers.py`. Fuse into one pass. Already on the v0.8.x roadmap (2.1, "still open"). Likely v0.8.13 headline.
2. **`export_flow.do_export` — 8.4 s.** Not instrumented at substep level yet. Add breakdown stamps inside `do_export` (group, build_session_snapshot, write_vendor_files, save_session_snapshot, append_order_history) before optimizing — same playbook that worked for `prepare_assignment_session`.
3. **`bulk_remove_flow.remove_filtered_rows` — 6.5 s.** Suspect the per-action `deepcopy(filtered_items)` for the undo snapshot. Replace with row-id snapshot. Listed as open in roadmap 2.1.
4. **`finish_bulk` / `finish_bulk_final` — 3.9 s / 2.8 s.** Need substep stamps to know which child loop dominates.

**Invariants to preserve** (do not regress these):

- Perf harness: `perf_trace.span_start` breadcrumbs are crash-survivable; keep `fsync` on entry. Aggregate summary writes via `atexit`.
- Lazy per-session indexes pattern: `_description_index_cache`, `_sales_history_index_cache`, `_pack_size_resolution_cache`, `_suggest_min_max_source_cache`. Invalidate from `_refresh_suggestions` and `_proceed_to_assign`.
- Generation-counter cache for `bulk_row_values` (int compare, not signature recompute).
- Bindtag-interception Delete handler on bulk sheet (`POBuilderSheetDelete` tag prepended to Sheet/MT/RI/CH/TL).
- `_force_dialog_foreground` helper for any new modal — Windows z-order bug bites whenever we forget.
- `check_stock_warnings` short-circuit at 50 flagged rows (lock-up regression guard).
- `1110 tests must still pass`. Build script (`build.bat`) runs them before bundling — never `--no-verify` or skip.

**How to enable a fresh perf trace on the next operator run:**

The `dist/perf_trace.enabled` sentinel file is already in place, so the packaged exe auto-instruments. After the operator runs a session, look at:
- `dist/perf_summary.txt` (aggregate)
- `dist/perf_trace.jsonl` (raw spans for drill-down)
- `dist/debug_trace.log` (crash breadcrumbs)

**Workflow that's been working:**

1. Pick the top item from the live perf summary
2. Add substep stamps if it isn't broken down yet
3. Ship instrumentation as one release, get a real trace
4. Find the actual bottleneck (it's almost never what I guessed)
5. Fix with measured before/after, ship as the next release, update the roadmap and CLAUDE.md

Start by reading the four files above, then pitch a plan for v0.8.13.
