import tkinter as tk
from tkinter import ttk
import shipping_flow
from ui_scroll import attach_vertical_mousewheel


HELP_SECTIONS = [
    (
        "Overview",
        "Start here for the main purpose of each tab and the normal end-to-end flow.",
        """Quick Start

PO Builder turns X4 report exports into vendor-ready PO import files while also surfacing X4 cleanup work.

Normal flow
- Load the current X4 CSV exports.
- Exclude line codes or suspended customers you do not want in this run.
- Review the Bulk Assign list, assign vendors, and adjust quantities only where needed.
- Use Individual Assign for leftovers that need manual attention.
- Review the final vendor groups and export the PO files.
- Use the maintenance report afterward to clean up X4 source values when needed.

What each main tab is for
- Load Files: choose reports, scan a folder, manage shared/local data, and check for updates.
- Line Codes: exclude whole product groups from the run.
- Customers: exclude suspended customers from the Suspended Items report.
- Assign Vendors: spreadsheet-style review, filtering, vendor assignment, and bulk editing.
- Individual: one-item-at-a-time assignment for leftovers.
- Review & Export: final cleanup before writing PO files.
- Help: reference for reports, controls, and troubleshooting.

Best practice
- Use the latest reports from the same general time window.
- Treat Bulk Assign as the main working screen and Individual as the exception path.
- Review warnings instead of exporting blindly.
- Prefer fixing repeated pack, vendor, min, and max issues at the source when possible.
""",
    ),
    (
        "Reports",
        "What each report means and how the app uses it.",
        """Part Sales & Receipts
- Closed, printed invoice sales plus receipts during the selected period.
- This is your confirmed movement history.
- The app uses it for demand history and suggested replenishment.
- Exact duplicate report rows are ignored so duplicated X4 rows do not inflate demand.

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
- The app usually uses the stronger of current max and suggested max.
- If no useful max exists, it falls back to min guidance or the current demand signal.
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
- warning: data is incomplete or risky.
- skip: no order needed.

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
        """Basic editing
- Click a cell to make it active.
- Double-click, F2, or Enter to edit the active editable cell or selection.
- Editable bulk columns are Vendor, Final Qty, QOH, Min, Max, and Pack.
- When editing directly in a cell, movement keys now commit the current change before moving.

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

Review table
- Double-click Vendor, Final Qty, or Pack to edit.
- Final Qty is what will export.
- Why This Qty explains the recommendation in plain language.
- Review & Export can default to Exceptions Only so routine items do not crowd the screen.
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
        """Bulk sheet unavailable
- The bulk spreadsheet editor requires the tksheet package.
- Install it in the same Python interpreter your IDE or EXE build uses.
- For this repo, the local .venv is often the interpreter used by debug runs.

Suggestion looks wrong
- Check QOH, On PO, Suspense, current max, and pack size.
- Look at the Why text for Pos, Target, Basis, Susp, and OnPO.
- Sparse annual sales may suppress suggested min/max.
- If you changed reorder cycle, the session should recalculate immediately. If it still looks wrong, verify the underlying source values.

Item marked review or warning
- Review often means reel/manual-only handling or another rule requiring a human decision.
- Warning usually means missing or inconsistent data such as no pack on an item that needs one.

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
]


def _build_help_page(parent, intro, body_text):
    page = ttk.Frame(parent, padding=12)
    ttk.Label(page, text=intro, style="SubHeader.TLabel", wraplength=900, justify="left").pack(anchor="w", pady=(0, 8))

    body_frame = ttk.Frame(page)
    body_frame.pack(fill=tk.BOTH, expand=True)

    body = tk.Text(
        body_frame,
        wrap="word",
        height=28,
        padx=12,
        pady=12,
        relief="flat",
        borderwidth=0,
    )
    body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scroll = ttk.Scrollbar(body_frame, orient="vertical", command=body.yview)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    body.configure(yscrollcommand=scroll.set)
    attach_vertical_mousewheel(body)

    body.insert("1.0", body_text)
    body.configure(state="disabled")
    return page


def build_help_tab(app):
    frame = ttk.Frame(app.notebook, padding=16)
    app.notebook.add(frame, text="  Help  ")

    ttk.Label(frame, text="Help", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text="Reference for reports, calculations, controls, maintenance behavior, and common troubleshooting steps.",
        style="SubHeader.TLabel",
        wraplength=900,
    ).pack(anchor="w", pady=(2, 10))

    settings_frame = ttk.LabelFrame(frame, text="Workflow Defaults", padding=10)
    settings_frame.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(
        settings_frame,
        text="Mixed immediate/planned export behavior:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(0, 8))
    behavior_map = {
        "all_exportable": "Export All Exportable",
        "immediate_only": "Immediate Only",
        "ask_when_mixed": "Ask When Mixed",
    }
    reverse_behavior_map = {label: key for key, label in behavior_map.items()}
    var_mixed_export = tk.StringVar(value=behavior_map.get(app._get_mixed_export_behavior(), "Export All Exportable"))
    combo_mixed_export = ttk.Combobox(
        settings_frame,
        textvariable=var_mixed_export,
        state="readonly",
        width=24,
        values=list(behavior_map.values()),
    )
    combo_mixed_export.pack(side=tk.LEFT)
    combo_mixed_export.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_mixed_export_behavior(reverse_behavior_map.get(var_mixed_export.get(), "all_exportable")),
    )

    ttk.Label(
        settings_frame,
        text="Planned-only export behavior:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(18, 8))
    planned_only_map = {
        "export_automatically": "Export Automatically",
        "ask_before_export": "Ask Before Export",
    }
    reverse_planned_only_map = {label: key for key, label in planned_only_map.items()}
    var_planned_only = tk.StringVar(
        value=planned_only_map.get(app._get_planned_only_export_behavior(), "Export Automatically")
    )
    combo_planned_only = ttk.Combobox(
        settings_frame,
        textvariable=var_planned_only,
        state="readonly",
        width=22,
        values=list(planned_only_map.values()),
    )
    combo_planned_only.pack(side=tk.LEFT)
    combo_planned_only.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_planned_only_export_behavior(
            reverse_planned_only_map.get(var_planned_only.get(), "export_automatically")
        ),
    )

    ttk.Label(
        settings_frame,
        text="Review & Export default focus:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(18, 8))
    focus_map = {
        "all_items": "All Items",
        "exceptions_only": "Exceptions Only",
    }
    reverse_focus_map = {label: key for key, label in focus_map.items()}
    var_review_focus = tk.StringVar(value=focus_map.get(app._get_review_export_focus(), "Exceptions Only"))
    combo_review_focus = ttk.Combobox(
        settings_frame,
        textvariable=var_review_focus,
        state="readonly",
        width=18,
        values=list(focus_map.values()),
    )
    combo_review_focus.pack(side=tk.LEFT)
    combo_review_focus.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_review_export_focus(reverse_focus_map.get(var_review_focus.get(), "exceptions_only")),
    )

    ttk.Label(
        settings_frame,
        text="Default vendor shipping preset:",
        style="Info.TLabel",
    ).pack(side=tk.LEFT, padx=(18, 8))
    preset_options = shipping_flow.vendor_policy_preset_options()
    preset_map = {"": "No Default"}
    preset_map.update({key: label for key, label in preset_options})
    reverse_preset_map = {label: key for key, label in preset_map.items()}
    var_vendor_preset = tk.StringVar(value=preset_map.get(app._get_default_vendor_policy_preset(), "No Default"))
    combo_vendor_preset = ttk.Combobox(
        settings_frame,
        textvariable=var_vendor_preset,
        state="readonly",
        width=24,
        values=list(preset_map.values()),
    )
    combo_vendor_preset.pack(side=tk.LEFT)
    combo_vendor_preset.bind(
        "<<ComboboxSelected>>",
        lambda _e: app._set_default_vendor_policy_preset(reverse_preset_map.get(var_vendor_preset.get(), "")),
    )

    ttk.Label(
        frame,
        text=(
            "Recommended routine path: keep Review & Export on Exceptions Only, use Release Plan for vendor timing decisions, "
            "save export defaults so the common path stays one-click, and use a default vendor shipping preset only when "
            "most unconfigured vendors should follow the same rule."
        ),
        style="Info.TLabel",
        wraplength=920,
        justify="left",
    ).pack(anchor="w", pady=(0, 10))

    help_notebook = ttk.Notebook(frame)
    help_notebook.pack(fill=tk.BOTH, expand=True)

    for title, intro, body_text in HELP_SECTIONS:
        page = _build_help_page(help_notebook, intro, body_text)
        help_notebook.add(page, text=f"  {title}  ")
