# Release Notes — v0.5.0

**Date:** 2026-04-02

---

## Summary

v0.5.0 — **Configuration & Control**. Three gaps that forced operators to edit
files by hand are now handled from within the app:

- The ignore list can be viewed and reversed from a dedicated dialog.
- Buy rules can be applied to multiple selected items at once.
- Order rules can be exported to CSV, edited in Excel, and re-imported with a
  diff preview.

916 tests pass. Phase 4 (manual QA) remains open.

---

## What changed since v0.4.3

### Phase 1 — Ignored Items Manager (`ui_ignored_items.py`, `session_state_flow.py`)

The ignore list was write-only from the UI. Restoring a mistakenly ignored item
required editing `ignored_items.txt` by hand.

- **"Manage Ignored Items" button** added to the bulk tab toolbar (next to
  "Add to Ignore List").
- **Dialog** lists every ignored item in a two-column tree (Line Code, Item
  Code) with a live filter bar.
- **Remove from Ignore List** — select any rows, click Remove. The items are
  saved immediately and reappear on the next file load.
- **Remove All** — removes all items from the ignore list with a confirmation
  prompt.
- **`un_ignore_item_keys(app, keys)`** added to `session_state_flow.py` — the
  reverse of `ignore_items_by_keys`. Strips keys, saves, returns count removed.
  No-ops when a key is not in the list (safe to call with stale data).

---

### Phase 2 — Bulk Rule Edit (`bulk_rule_flow.py`, `ui_bulk_rule_edit.py`)

Applying the same pack size or policy to multiple items required opening the
buy-rule dialog once per item.

- **"Edit Rule for Selection"** added to the bulk grid context menu.
- **Dialog** exposes four fields: Order Policy, Pack Qty, Min Order Qty, Cover
  Days. Any field left blank is not written — existing rule values are
  preserved.
- **`apply_bulk_rule_edit(app, keys, changes)`** in `bulk_rule_flow.py`:
  - Applies only explicitly set, valid fields to each rule.
  - Policy changes are locked (same as the single-item editor).
  - Zero or negative numeric values are ignored.
  - Saves once via `_save_order_rules()` after all keys are updated.
  - Returns the count of rules modified.

---

### Phase 3 — Order Rules CSV Round-trip (`rules_csv_flow.py`)

`order_rules.json` was opaque — no way to audit its full contents or do mass
edits without a text editor.

- **"Export Rules CSV"** button on the bulk toolbar — opens a Save dialog and
  writes a CSV with columns: Line Code, Item Code, Order Policy, Pack Qty, Min
  Order Qty, Cover Days, Cover Cycles, Trigger Qty, Trigger %, Notes.
- **"Import Rules CSV"** button — opens an Open dialog, parses the file,
  shows a diff preview (X added, Y updated, Z deleted, N skipped), and applies
  on confirmation.
- **Import semantics:**
  - Additive/override: rules absent from the CSV are not touched.
  - A row with a recognised key but all-blank rule fields deletes that entry.
  - Invalid numeric values are skipped with a warning shown in the preview.
  - Unknown CSV columns are silently ignored (forward-compatible).
- **`rules_csv_flow.py`** — three pure functions, no UI, no file I/O:
  - `export_rules_csv(order_rules)` → CSV string
  - `import_rules_csv(csv_text, existing_rules)` → diff dict
  - `apply_import_diff(existing_rules, diff)` → count affected

---

## New files

| File | Purpose |
|------|---------|
| `ui_ignored_items.py` | Ignored Items Manager dialog |
| `bulk_rule_flow.py` | `apply_bulk_rule_edit` — pure bulk rule logic |
| `ui_bulk_rule_edit.py` | Bulk Rule Edit dialog |
| `rules_csv_flow.py` | Order rules CSV export / import / diff |
| `tests/test_ignored_items.py` | 21 tests |
| `tests/test_bulk_rule_flow.py` | 16 tests |
| `tests/test_rules_csv_flow.py` | 22 tests |

---

## Test count

| Release | Tests |
|---------|-------|
| v0.3.0  |   756 |
| v0.4.0  |   830 |
| v0.4.1  |   854 |
| v0.4.2  |   857 |
| v0.4.3  |   857 |
| v0.5.0  |   916 |

59 new tests across the three new feature modules.
