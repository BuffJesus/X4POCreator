# PO Builder v0.10.6 — Review Tab Editing + Analysis Reports

**Edit quantities and remove items right on the Review tab.  Export
dead stock, deferred, and session summary reports.**

Two features the operator has been working around: the Review tab
was read-only (had to go back to Bulk to fix anything), and there
was no way to export analysis data beyond the PO files themselves.
Both are fixed.

872 tests pass.

---

## Review Tab: Now Editable

The Review & Export tab was previously read-only — you could look at
items but had to navigate back to the Bulk grid to change anything.

Now you can:

- **Double-click Vendor or Final Qty** to edit inline (or press F2)
- **Delete / Backspace** removes selected rows from the export
- **Right-click** for a context menu with Remove Selected Rows
- **Multi-select** with Ctrl+click or Shift+click, then delete in
  bulk

Edits propagate back to the underlying item data and sync to the
Bulk grid, so the summary cards and Order Value stay accurate.

---

## Analysis Reports: More > Export Reports

Three new CSV exports accessible from **More > Export Reports** on
the Bulk toolbar:

### Dead Stock Report
Per-vendor breakdown of all dead stock items with QOH, unit cost,
**on-hand value**, last sale date, days since last sale, and sales
velocity.  Summary dialog shows total dead-stock value.

Use it to negotiate vendor returns or prioritize inventory cleanup
by dollar value.

### Deferred Items Report
Every item where pack-overshoot defer skipped ordering this cycle.
Shows stock percentage, pack size, raw need, and why it was
deferred.

Use it to review system deferrals and override where needed.

### Session Summary
One-page overview: total items, assigned/unassigned counts,
review/warning/skip/dead stock/deferred counts, estimated order
value, and per-vendor breakdown with item counts and values.

Use it for approval workflows or week-over-week comparison.

---

## Stats

| Metric | Count |
|--------|-------|
| Tests passing | 872 |
| Review tab capabilities added | 3 (edit, delete, context menu) |
| New exportable reports | 3 (dead stock, deferred, session summary) |
