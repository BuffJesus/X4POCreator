"""Pure-data definitions for the Help tab.

Separated from ``ui_help.py`` so the Qt Help tab can load the same
content without pulling in tkinter.  See ``ui_load_data.py`` for the
rationale — same story: the Qt PyInstaller spec excludes tkinter, and
``ui_help.py`` imports tk at module level for its rendering code, so
the Qt build crashes if anything reaches through to it.

This module is framework-independent: plain strings and a plain dict.
"""


# Maps a contextual-help key (the string the caller passes to
# ``open_help_for(app, key)``) to the HELP_SECTIONS tab title the
# operator should land on.  Keep in sync with _section_titles() in
# ``ui_help.py``; the test in tests/test_ui_help.py asserts every
# mapped section exists.
CONTEXTUAL_HELP_MAP = {
    "reorder_cycle":          "Ordering Logic",
    "history_days":           "Ordering Logic",
    "skip_filter":            "Bulk Assign",
    "no_pack_filter":         "Bulk Assign",
    "acceptable_overstock":   "Ordering Logic",
    "confirmed_stocking":     "Ordering Logic",
    "vendor_review":          "Bulk Assign",
    "supplier_map":           "Bulk Assign",
    "session_diff":           "Overview",
    "session_history":        "Overview",
    "bulk_remove_not_needed": "Bulk Assign",
    "shared_data_folder":     "Data And Sharing",
    "shortcuts":              "Shortcuts",
    "maintenance":            "Maintenance",
    "shipping_release":       "Shipping And Release",
    "review_export":          "Review And Export",
    "reports":                "Reports",
    "troubleshooting":        "Troubleshooting",
}


HELP_SECTIONS = [
    (
        "Overview",
        "Start here for the main purpose of each tab and the normal end-to-end flow.",
        """Quick Start

PO Builder turns X4 report exports into vendor-ready PO import files while also surfacing X4 cleanup work.

Normal flow
- Load the current X4 CSV exports.
- Exclude line codes or suspended customers you do not want in this run.
- Review the Bulk Assign grid, assign vendors, and adjust quantities only where needed.
- Review exceptions first instead of rereading every routine item.
- Use Export Recommended for the normal export path.
- Use the maintenance report afterward to clean up X4 source values when needed.

What each sidebar tab is for
- Load: choose reports, scan a folder, and manage shared/local data.
- Filter: exclude line codes and suspended customers from the run.
- Bulk: spreadsheet-style review, filtering, vendor assignment, and bulk editing.
- Review: final cleanup and export of per-vendor PO files.
- Help: reference for reports, controls, and troubleshooting.

Summary cards at the top of the Bulk grid
- Total items, Assigned, Unassigned, and estimated Order Value are shown at a glance.
- Order Value sums Final Qty x Unit Cost for all assigned items, updated live.

Best practice
- Use the latest reports from the same general time window.
- Treat Bulk as the main working screen; most items auto-assign from receipt history.
- Treat Review & Export as an exception-first screen, not a touch-every-row screen.
- Use Export Recommended unless you intentionally want immediate-only or planned-only scope.
- Review warnings and deferred items instead of exporting blindly.
- Prefer fixing repeated pack, vendor, min, and max issues at the source when possible.
""",
    ),
    (
        "Reports",
        "What each report means and how the app uses it.",
        """Detailed Part Sales (preferred sales source)
- Transaction-level sales report: one row per invoice line.
- Provides per-customer, per-date, and margin data not available in the legacy combined report.
- The app aggregates across all transactions to produce total qty sold per item.
- Use together with Received Parts Detail for the preferred daily workflow.

Received Parts Detail (preferred receiving source)
- Transaction-level receiving report: one row per receipt line.
- Stock-return rows (RR) are excluded automatically; only inbound receipts (RC) are counted.
- Provides vendor codes per receipt, which the app uses for vendor suggestions.
- Use together with Detailed Part Sales for the preferred daily workflow.

Part Sales & Receipts (legacy / compatibility)
- Closed, printed invoice sales plus receipts during the selected period.
- This is your confirmed movement history.
- The app uses it for demand history and suggested replenishment when the detailed pair is unavailable.
- Exact duplicate report rows are ignored so duplicated X4 rows do not inflate demand.
- Use only when the Detailed Part Sales + Received Parts Detail pair is not available.

POs by PG
- Items currently on purchase orders.
- These quantities are treated as already on order.
- They reduce duplicate ordering by contributing to inventory position.

Suspended Items
- Items on running invoices that have likely already left the shelf.
- X4 already removes suspended quantities from QOH, so the app does not subtract suspense from QOH again.
- Suspense is treated as a temporary demand signal.
- Suspense carry tracking helps avoid ordering the same demand again once it later appears in Part Sales.

On Hand Report / Min-Max source data
- QOH, min, max, supplier, sales history, and receipt/sale dates come from the source CSVs.
- These values are used for suggestion logic, warnings, and maintenance reporting.
- Bulk QOH, min, and max edits affect this session's calculations and can appear in maintenance follow-up.

Order multiples / pack quantities
- Pack sizes come from the order-multiples source and saved item rules.
- Manual pack edits can be saved and surfaced again in the maintenance report.

Maintenance report purpose
- The maintenance report is meant to show differences between X4 values and the app's current target values.
- It is a cleanup aid for X4, not just a copy of whatever the app currently holds.
- It does not change X4 automatically.
""",
    ),
    (
        "Ordering Logic",
        "How suggested quantities are calculated in plain language.",
        """Base recommendation
- Inventory position = QOH + On PO.
- The app does not subtract suspense from QOH because X4 already has.
- Recommended order = target stock - inventory position, never below zero.
- Reorder-cycle changes recalculate suggested min/max and suggested qty for the current session.

Target stock
- When a current max is set in X4, it is treated as authoritative (the operator knows their business).
- Suggested max only fills the gap when no explicit max exists.
- If the max looks like auto-calculated noise (pack size is more than 5x the max), the target is adjusted up to at least one full pack and tagged "pack_adjusted_max".
- If no useful max exists, the app falls back to min guidance or the current demand signal.
- Very sparse 12-month sales history does not create a suggested min/max by itself.

Demand signals
- Part Sales is the confirmed demand signal.
- Suspense is a short-term demand signal for likely off-shelf items that are not yet closed/invoiced.
- Suspense carry helps prevent double-ordering when suspense later turns into printed sales.

Pack handling
- Standard pack items round up to the next pack.
- Soft-pack rules can allow smaller increments when configured.
- Exact-qty items use the exact result.
- Reel-review and manual-only items stay flagged for human review.
- Trigger-style rules can hold a reorder floor above the ordinary max when coverage or pack logic requires it.
- Acceptable overstock rules can allow intentional post-receipt overstock without treating it as an error automatically.

Pack-overshoot defer
- When stock is already comfortable (QOH >= 50% of max) and a full pack would significantly overshoot max (by more than 25% of a pack), the app suggests deferring to the next cycle.
- Deferred items show as Warnings with a "deferred_pack_overshoot" flag so you can review them.
- The defer does NOT apply when pack > max (overshoot is inherent to the item, like hose reels) or when you genuinely need a full pack to restock.

Coverage-aware rules
- Saved item rules can define trigger qty, trigger %, minimum packs, cover days, and cover cycles.
- These rules can make an item reorder earlier than its normal operational max would suggest.
- Hardware-style large-pack items may also infer conservative pack-trigger behavior when the data strongly suggests it.

Confidence and caution
- Missing sale/receipt recency can reduce recommendation confidence.
- Low-confidence items may route to review/manual handling instead of auto-order.
- Why text and item details now surface confidence, completeness, and trigger/tolerance signals directly.

Why text
- Stock after open POs: inventory position used for the calculation.
- Target stock: stock level the app is trying to restore.
- Based on ... : what drove the target, such as current max, suggested max, or demand signal.
- Suspended demand included: effective suspense demand included for this run.
- Already on PO: quantity already on order.

Common statuses
- ok: ready to export.
- review: needs a manual decision.
- warning: data is incomplete, risky, or a pack overshoot was deferred.
- skip: no order needed.

Dead stock detection
- Items with no sale in 365+ days are flagged as dead stock.
- Items that haven't sold in 2x their normal sales cycle (minimum 90 days) are also flagged, even if under 365 days.
- Dead stock items can be isolated with the Dead Stock quick filter pill.

What overrides what
- Manual Final Qty edits override the app suggestion for that session.
- Manual Pack edits can change both the suggestion and the saved per-item rule.
- Vendor changes do not change the recommendation math; they only affect grouping and export.

Plain-language field names
- Qty Needed Before Pack: what the item would need before pack rounding or special buy rules.
- Suggested Qty: the app's recommendation after pack and buy-rule logic.
- Final Qty: the quantity that will actually export.
- Why This Qty: a readable explanation of the recommendation.
""",
    ),
    (
        "Bulk Assign",
        "Spreadsheet-style controls, bulk actions, and selection behavior on the Assign Vendors tab.",
        """Grid columns
- Editable columns: Vendor, Final Qty, QOH, Min, Max, Pack, and Notes.
- Informational columns: Unit Cost, Ext Cost, Last Sale, Last Receipt, Risk, and more.
- Right-click any column header to show/hide columns.
- Shift+click a column header to add a secondary sort (up to 3 levels).

Basic editing
- Click a cell to make it active.
- Double-click, F2, or Enter to edit the active editable cell or selection.
- When editing directly in a cell, movement keys commit the current change before moving.

Selection
- Ctrl+click adds cells or rows to the selection.
- Shift+click extends the current cell or row range.
- Shift+Arrow extends the current selection range from the anchor cell.
- Shift+Space selects the current row.
- Ctrl+Space selects the current column.
- Ctrl+A selects all visible rows.
- Fit Columns To Window resizes the bulk grid columns to fit within the visible area as well as possible.

Bulk editing
- Fill Selected Cells applies one entered value across the selected editable cells in one column.
- If rows are selected, Fill Selected Cells uses the active editable column across those rows.
- Editing one selected cell in a single editable column applies that edited value across the whole selected range in that column.
- Clear Selected Cells clears the selected editable cells in the active editable column.
- Ctrl+D, Ctrl+R, and Ctrl+Enter reuse the current cell value across the selected rows in the active editable column.
- Undo and Redo reverse recent bulk edits and row removals.

Clipboard
- Ctrl+C copies the current selected cells or rows.
- Ctrl+V pastes one value down the active editable column, or pastes a rectangular block starting at the active cell.
- Rectangular pastes only affect editable columns.

Delete behavior
- Delete or Backspace clears selected editable cells.
- If rows are selected, Delete removes those rows from the current session instead.
- The context menu also includes Remove Selected Rows.

Useful bulk actions
- Apply to Selected: sets the vendor for the selected rows.
- Apply to All Visible: sets the vendor for the currently filtered list.
- Remove Not Needed (On Screen): review likely-unnecessary rows currently visible.
- Remove Not Needed (Filtered): review likely-unnecessary rows from the full filtered set.
- Undo Last Remove: restores the most recent bulk-removal action.
- Undo / Redo: reverses or reapplies broader bulk edit actions such as fill, paste, and row removal.

Context menu
- Remove Selected Rows
- Bulk Edit Selection
- Select Current Row
- Select Current Column
- View Item Details
- Edit Buy Rule
- Mark Review Resolved
- Dismiss duplicate warning

Status line
- Shows the active editable column plus selected-cell or selected-row count.
- If the sheet feels unfamiliar, open Bulk Shortcuts from the Bulk tab for a quick reference.
""",
    ),
    (
        "Shortcuts",
        "Keyboard reference for the bulk editor and review grid.",
        """Bulk grid essentials
- Ctrl+C: copy selected cells or rows
- Ctrl+V: paste into the active editable area
- Ctrl+A: select all visible rows
- Ctrl+Z / Ctrl+Y: undo and redo bulk actions
- Ctrl+D / Ctrl+R: fill the selected rows from the current cell value
- Ctrl+Enter: apply the current cell value to the selected rows in the active editable column
- Delete / Backspace: clear selected cells, or remove rows if whole rows are selected
- F2 or Enter: edit the current editable selection
- Esc: clear the current selection

Bulk navigation
- Tab / Shift+Tab: move across editable bulk columns
- Shift+Arrow: extend the current selection range
- Home / End: jump to first or last editable column on the current row
- Ctrl+Arrow: jump to the edge in the pressed direction
- Shift+Space: select current row
- Ctrl+Space: select current column

Editing behavior
- If an in-cell editor is open, arrow keys, Tab, and Shift+Tab commit the edit first and then move.
- Bulk editing remains column-oriented on purpose. The app does not try to behave like a full spreadsheet across arbitrary multi-column edits.

Review grid essentials
- Double-click, F2, or Enter edits the active editable column
- Left / Right changes the active editable column
- Delete removes selected rows from the review list

If something feels off
- First check whether you selected rows or cells.
- Then check the active editable column shown in the bulk status line.
- For predictable bulk edits, work in one editable column at a time.
""",
    ),
    (
        "Review And Export",
        "What to do after bulk assignment and how export works.",
"""Individual Assign
- Use this when bulk assignment is not enough.
- Assign & Next saves the vendor and advances.
- Skip Item leaves the item unassigned and moves on.
- Back returns to the previous item.
- Vendor entry now auto-fills when the app has strong evidence from the current report supplier or a single-vendor recent local order history.

Review table
- Double-click Vendor, Final Qty, or Pack to edit.
- Final Qty is what will export.
- Why This Qty explains the recommendation in plain language.
- Review & Export can default to Exceptions Only so routine items do not crowd the screen.
- If no exceptions are present, Review automatically falls back to All Items so the screen stays usable.
- The Focus filter switches between All Items and Exceptions Only.
- The Release filter separates Release Now, Planned Today, and Held items.
- If multiple rows are selected, editing one editable cell in that column applies that value across the selected rows.
- Enter or F2 starts editing the active editable column.
- Left and Right change the active editable column.
- Up and Down move while editing.
- Delete removes selected rows from the review list.
- Pack edits from Review can persist into saved order rules.

Release planning
- Vendor shipping policies can mark items as Release Now, Planned Today, or Held.
- Planned Today usually means the PO should be exported now so it is ready for an upcoming free-freight day.
- Held means the vendor policy wants more time, a threshold, or a specific future day before release.
- Use Release Plan to see the vendor-level picture instead of reading item rows one by one.

Release Plan dialog
- Summarizes each vendor's immediate, planned, and held items.
- Shows vendor value, threshold shortfall/progress, coverage confidence, next free-ship day, and planned export date.
- You can jump directly into Review for one vendor from this dialog.
- You can also export a selected vendor's immediate batch or planned batch directly from the dialog.

Export
- Export writes one PO file per vendor.
- The export step also saves a session snapshot for traceability.
- Maintenance output reflects X4 source values, target values, and suggested values where appropriate.
- Export Recommended is the normal path from Review & Export.
- Mixed immediate/planned export behavior can be saved as a workflow default.
- The default can be Export All Exportable, Immediate Only, or Ask When Mixed.
- Scoped exports from Release Plan still use the normal export pipeline, history, and session snapshot behavior.

Before exporting
- Check the exception list first rather than rereading every routine item.
- Review held vendors, planned-today vendors, low-confidence items, and warnings.
- Confirm pack sizes and manual quantity overrides on unusual items.
- Remove anything that was only included temporarily for review.
""",
    ),
    (
        "Shipping And Release",
        "How vendor shipping policy affects timing, visibility, and export decisions.",
        """Core idea
- Shipping policy is vendor-level release planning layered on top of item-level reorder logic.
- The app can recommend ordering an item while still holding or scheduling the vendor PO release.

Current policy model
- release_immediately
- hold_for_free_day
- hold_for_threshold
- hybrid_free_day_threshold

Inputs used today
- preferred free-shipping weekdays
- freight-free threshold
- urgent release floor
- inventory replacement cost from the loaded inventory data
- current day/date

What the planner computes
- estimated item order value
- vendor order value total
- value coverage confidence
- threshold shortfall and progress
- next preferred free-ship date
- planned export date for free-day ordering

Release states
- Release Now: export now with the routine batch.
- Planned Today: export now so the PO is ready for the upcoming free-freight day.
- Held: keep visible for review, but do not export yet.

Important behavior
- Urgent floor can override hold logic.
- Planned Today is exportable.
- Held items stay visible in Review & Export and are excluded from export.
- Vendor value coverage can be partial or missing when cost data is incomplete, so threshold math should be read accordingly.

How to work with it
- Use Review & Export in Exceptions Only mode for the fastest path.
- Treat urgent overrides as review-first exceptions even when they are exportable now.
- Use Release Plan when you want to think by vendor instead of by item.
- If a vendor is Planned Today, export its planned batch directly from Release Plan or include planned items in the normal export batch depending on your saved default.
""",
    ),
    (
        "Maintenance",
        "How maintenance reporting and source cleanup fit into the workflow.",
        """Purpose
- The maintenance report helps clean up item data in X4.
- It is meant to surface differences between X4 and the app's current targets or suggestions.
- It is a follow-up checklist, not a required export step.
- It does not change X4 automatically.

What it can show
- Supplier/vendor differences
- Pack quantity differences
- Current min/max versus target min/max
- Suggested min/max differences even when you did not manually change min/max
- QOH adjustments made during the session

How to use it
- Export or inspect the maintenance report after reviewing the PO session.
- Use it as a future reference to update the actual X4 source values more quickly.
- Repeated issues usually mean the source CSVs or saved item rules should be cleaned up.

Persistence
- Pack overrides and buy-rule changes can persist through saved rules.
- Session snapshots capture what was loaded, what was assigned, and what maintenance issues were present at export time.
- Shared-folder users should remember that the maintenance report reflects the current session state, not live changes already made in X4 afterward.
""",
    ),
    (
        "Data And Sharing",
        "How local data, shared data, and saved rules behave.",
        """Local vs shared data
- By default, the app stores operational files beside the script or beside the built EXE.
- You can point the app at a shared folder from Load Files when multiple users need the same rules, vendor list, and history.
- The active data source is shown in the UI so users can confirm whether they are working locally or against shared data.

Files the app saves
- vendor_codes.txt: saved vendor list
- order_rules.json: per-item pack and buy-rule settings
- duplicate_whitelist.txt: accepted duplicate item-code exceptions
- order_history.json: recent export history
- suspense_carry.json: carry-forward suspense tracking
- sessions/: export-time session snapshots

What to expect
- Shared saves attempt to merge cleanly where possible.
- Session snapshots are append-only and are the safest files to share.
- suspense_carry.json is more sensitive because multiple users may affect the same demand carry logic.
- Reload files if you changed shared rules or vendor data elsewhere and want the current session to reflect it.
""",
    ),
    (
        "Troubleshooting",
        "Common issues and what to check first.",
        """Suggestion looks wrong
- Check QOH, On PO, Suspense, current max, and pack size.
- Look at the Why text for Pos, Target, Basis, Susp, and OnPO.
- Sparse annual sales may suppress suggested min/max.
- If you changed reorder cycle, the session should recalculate immediately. If it still looks wrong, verify the underlying source values.

Item marked review or warning
- Review often means reel/manual-only handling or another rule requiring a human decision.
- Warning usually means missing or inconsistent data, a pack overshoot deferral, or dead stock detection.
- Press Enter on any item to open the details dialog and see the full Activity & Risk breakdown.

Delete did not do what you expected
- If rows are selected, Delete removes rows.
- If cells are selected, Delete clears editable cells.
- Use Shift+Space first if you want to force row selection.

Paste did not do what you expected
- Single-column paste follows the active editable column.
- Rectangular paste starts at the active cell.
- Read-only columns are skipped.

I edited a cell and moving with the keyboard felt wrong
- In the bulk grid, arrow keys, Tab, and Shift+Tab now commit the current edit before moving.
- If movement still seems wrong, check whether focus moved out of the editor or whether the selected area spans multiple rows.
- For the cleanest behavior, keep bulk edits to one editable column at a time.

Vendor is blank
- Supplier data can prefill vendor automatically, but users can still overwrite it.
- If supplier is missing in source data, vendor may need manual entry.

Undo or redo did not restore what you expected
- Undo / Redo is aimed at recent bulk actions on the Bulk Assign tab.
- Undo Last Remove is still available for the older remove flow.
- If the current filter hides restored rows, switch filters back to ALL before assuming data was lost.
""",
    ),
    (
        "Shortcuts",
        "Every keyboard shortcut on the bulk assignment grid. Press ? on the grid for a quick overlay.",
        """Navigation
- `Enter` — View item details for the selected row
- `F2` or `Double-click` — Edit the selected cell
- `Tab` / `Shift+Tab` — Move to the next / previous editable column
- `Home` / `End` — Jump to the first / last column
- `Ctrl+Arrow` — Jump to the edge of the data in that direction
- `Shift+Arrow` — Extend the current selection

Editing
- `Ctrl+Z` — Undo the last edit or removal
- `Ctrl+Y` — Redo
- `Ctrl+D` — Fill down: copy the top cell's value to all selected cells in the column
- `Ctrl+R` — Fill right
- `Ctrl+Enter` — Apply the current cell's value to the entire selection
- `Delete` or `Backspace` — Remove the selected rows

Selection
- `Ctrl+A` — Select all visible cells
- `Ctrl+Shift+A` — Select all rows (for row-header operations)
- `Shift+Space` — Select the current row
- `Ctrl+Space` — Select the current column
- `Escape` — Clear the selection

Grid & Columns
- `Click column header` — Sort by that column (click again to reverse)
- `Shift+Click column header` — Add a secondary sort (up to 3 levels)
- `Right-click column header` — Show/hide columns
- `Ctrl+K` — Open the command palette (jump to any item, vendor, or action)
- `Ctrl+F` — Focus the text search box
- `Ctrl+C` / `Ctrl+V` — Copy / Paste cell data
- `?` — Show the keyboard shortcut overlay

Quick Filters
- Use the pill buttons above the filter panel for one-click presets: All, Unassigned, Needs Review, Warnings, High Risk, Dead Stock, Deferred.
- Combine with the detailed filter dropdowns below for precise filtering.
""",
    ),
]
