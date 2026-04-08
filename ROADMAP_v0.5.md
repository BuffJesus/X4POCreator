# PO Builder Roadmap — v0.5.x

Status: Phases 1–3 complete — Phase 4 (manual QA) remaining

Current app version: `0.5.0`

---

## What v0.5.x is about

v0.4.x added intelligence (risk scoring, trends, dead stock, session history)
and fixed the auto-update pipeline. v0.5.x focuses on **Configuration &
Control**: the three biggest gaps where operators must currently leave the app
and edit files by hand are all addressed here.

- **Ignored Items Manager** — operators can ignore items from the bulk grid but
  have no way to view or undo the ignore list without editing the text file.
- **Bulk Rule Edit** — the buy-rule editor works one item at a time; applying
  the same pack size or policy to a selection requires opening the dialog once
  per item.
- **Order Rules CSV Round-trip** — order_rules.json accumulates over time with
  no way to audit, bulk-edit in Excel, or clean up stale entries from within
  the app.

---

## Phase 1. Ignored Items Manager

Operators have no way to see what is on the ignore list, and no way to restore
an item without editing `ignored_items.txt` by hand.

- [x] Add an "Ignored Items" button to the bulk tab toolbar (next to "Add to
  Ignore List") that opens the Ignored Items Manager dialog.
- [x] Dialog lists all ignored items (Line Code, Item Code columns), most
  recently added first where possible.
- [x] Filter bar — partial match on item code or line code.
- [x] "Remove from Ignore List" action — removes selected items from
  `ignored_item_keys`, saves via existing `_save_ignored_item_keys()`.
  Restored items reappear on next file load.
- [x] "Remove All" button with confirmation.
- [x] Add `un_ignore_item_keys(app, keys)` to `session_state_flow.py`.
- [x] Add tests for `un_ignore_item_keys` and the pure helper functions in
  `ui_ignored_items.py`.

---

## Phase 2. Bulk Rule Edit

Each buy rule currently requires opening a separate dialog per item. Applying
the same change (e.g., pack size 12 for all MOTION items) to a multi-row
selection is tedious.

- [x] Add "Edit Rule for Selection" to the bulk grid context menu.
- [x] Dialog shows Order Policy, Pack Qty, Min Order Qty, Cover Days. Blank
  fields leave each item's existing value unchanged.
- [x] Applies the change to all selected items in one operation, saves via
  `_save_order_rules()`, and refreshes suggestions.
- [x] `apply_bulk_rule_edit(app, keys, changes)` in `bulk_rule_flow.py`.
- [x] Tests covering partial-field updates, multi-item application, invalid
  values, and no-op when all fields are blank.

---

## Phase 3. Order Rules CSV Round-trip

There is no way to audit `order_rules.json` contents or do mass edits without
a text editor or writing custom tooling.

- [x] "Export Rules CSV" button on bulk toolbar — writes Line Code, Item Code,
  Order Policy, Pack Qty, Min Order Qty, Cover Days, Cover Cycles, Trigger Qty,
  Trigger %, Notes. One row per item in `app.order_rules`.
- [x] "Import Rules CSV" button — validates, previews diff (added / changed /
  deleted / skipped), applies on confirmation.
- [x] Import is additive/override; all-blank rows delete the rule entry.
- [x] `export_rules_csv`, `import_rules_csv`, `apply_import_diff` in
  `rules_csv_flow.py`.
- [x] Tests covering round-trip fidelity, partial imports, delete-by-blank,
  invalid fields, and unchanged detection.

---

## Phase 4. Manual QA (carry-over)

- [ ] Run full load → assign → review → export workflow against representative
  real-world CSVs in the packaged exe.
- [ ] Confirm that detailed sales / received parts parsing, vendor resolution,
  and export formatting all behave correctly with live data shapes not covered
  by synthetic tests.
- [ ] Add any targeted regression tests discovered during live testing.

---

## Definition of "Done Enough" for v0.5.x

- Operators can view and un-ignore any item without leaving the app.
- A multi-row selection in the bulk grid can have its pack size, policy, or
  cover days changed in one dialog.
- Order rules can be exported to CSV, edited in Excel, and re-imported with a
  diff preview.
- Phase 4 manual QA has been completed against at least one real-world dataset.
