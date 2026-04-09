# Release Notes — v0.8.13

**Date:** 2026-04-09

---

## Summary

Largest single release in the v0.8.x train: **5 bug fixes, 3 perf
wins, 6 new UX features, and the Phase 3 structural refactor** that
splits `rules.py` (1,670 lines) into a 6-module package, adds
sub-state dataclasses to `AppSessionState`, and begins the `parsers.py`
split.

1140 tests pass (30 new).

---

## Bug fixes

### 1. Cell edits not displaying on the bulk grid

Edits applied to the data model but the grid showed stale values.
Three caches (render, visible-rows, filter-result) were not evicted
for edited rows.  Fixed by evicting all three at the top of
`refresh_bulk_view_after_edit` before any refresh path runs.

### 2. Inline cell editor race condition

tksheet's inline text editor opened alongside the dialog prompt on
double-click.  When the dialog stole focus, `close_text_editor`
wrote the old value back.  Fixed: `begin_edit_cell` returns `None`
to suppress the inline editor entirely.

### 3. Multi-row drag-select + F2 only editing one row

`selected_target_row_ids` checked the snapshot (overwritten by
intermediate events) before the live selection.  Fixed to check
`get_selected_cells()` first.

### 4. Invalid tksheet binding name

`"end_edit_table"` → `"end_edit_cell"` (not a valid name in
tksheet 7.5.19).

### 5. HEADER_ALIASES missing underscore forms

Pre-existing bug: `qty_sold`, `sale_date`, `qty_received`,
`receipt_date` were missing from alias sets, breaking generic CSV
header detection for files with those header labels.

---

## Performance

### Bulk edit batching (7.5× faster)

8-row pack_size edit: **~5.6 s → ~750 ms**.  `_save_order_rules`
(disk write) and `annotate_release_decisions` (59K-item loop) are
now deferred to one call after the multi-row loop via
`_bulk_apply_and_flush`.

### Per-row-id undo snapshot

`bulk_remove_flow` now passes removal indices to the history capture
spec, deepcopying only affected rows instead of all 59K.  Expected:
**~6.5 s → < 50 ms**.

### Sort + parse instrumentation

New perf spans: `header_click_sort`, `sort_bulk_tree.sort`,
`sort_bulk_tree.apply_filter`, `parse_detailed_pair_aggregates`
sales/receipts substep stamps.

---

## New features (Phase 1b + 1c)

| Feature | Key |
|---|---|
| Click column header to sort + ▲/▼ arrows | Header click |
| Double-click column header to auto-size | Header double-click |
| Enter on selected row → View Item Details | Enter |
| Ctrl+F focuses bulk search box | Ctrl+F |
| Ctrl+D fill-down (pre-existing, now documented) | Ctrl+D |
| Per-item Notes column (editable, persisted, exported) | Phase 1c |

Notes are stored in `item_notes.json` keyed by `LC:IC`, loaded on
startup via `item_notes_flow.py`, and included in vendor xlsx exports.

---

## Structural refactors (Phase 3)

### 3.1 — Golden characterization tests

20 `test_enrich_golden.py` fixtures pinning `enrich_item` output
across all major policy/status/attention paths.

### 3.2 — `rules.py` → `rules/` package (complete)

| Module | Contents |
|---|---|
| `rules/__init__.py` | `enrich_item` orchestrator (~177 lines, down from ~380) + re-exports |
| `rules/_constants.py` | All shared constants and term lists |
| `rules/_helpers.py` | Rule field accessors (`get_rule_int`, `has_pack_trigger_fields`, etc.) |
| `rules/calc.py` | 9 pure calculation functions |
| `rules/policy.py` | 16 policy/classification functions + 3 label helpers |
| `rules/explanation.py` | `build_reason_codes` + `build_detail_parts` |
| `rules/status.py` | `evaluate_item_status` |

All existing `from rules import X` statements continue working.

### 3.3 — `AppSessionState` sub-states (partial)

`models/session_bundle.py` with four dataclasses: `LoadedData`,
`DerivedAnalysis`, `UserDecisions`, `SessionMetadata`.
`AppSessionState` uses `__getattr__`/`__setattr__` forwarding so
`state.sales_items` → `state.loaded.sales_items` transparently.

### 3.4 — `parsers.py` → `parsers/` package (partial)

`parsers/dates.py` (parse_x4_date + cache) and
`parsers/normalize.py` (_safe_cell, _coerce_int, etc.) extracted.
HEADER_ALIASES bug fixed.

---

## Other changes

- `requirements.txt` — pin `tksheet>=7.5.19`
- `VERSION` synced to 0.8.13
- `CLAUDE.md` updated

---

## Release history

| Release | Headline |
|---|---|
| v0.8.9 | Dialog lock-up fix |
| v0.8.10 | normalize_items_to_cycle eliminated (−23 s) |
| v0.8.11 | Full span instrumentation |
| v0.8.12 | O(n²) description scan eliminated (−29 s) |
| **v0.8.13** | **5 bug fixes + 6 UX features + bulk edit 7.5× + rules/parsers/models refactor** |
