# PO Builder v0.11 — Vendor Intelligence + Operator Tools

**Know who you're buying from, catch mismatches before export, and
assign vendors in bulk by supplier name.**

This release adds vendor mismatch detection, a settings dialog, PO
memo support, a supplier-based bulk assignment tool, a formatted
dead stock report you can hand to vendors, and a proper post-load
summary.  It also fixes the progress bar freeze on large datasets
and cleans up 87 stale files from the repo.

872 tests pass.

---

## Vendor Mismatch Detection

When you assign a vendor that contradicts receipt history, the
vendor cell turns **amber** with a tooltip:

> Vendor mismatch: assigned SOURCE, but receipt history suggests
> MOTION (high confidence)

The **Vendor &ne;** quick filter pill isolates all mismatched items
so you can review them before export.  The item details dialog
shows the full mismatch with vendor confidence level.

---

## Apply by Supplier

Enter a vendor code, click **Apply by Supplier**, and a checklist
shows every supplier in the current view with item counts:

```
MOTION INDUSTRIES    (142 items)
APPLIED INDUSTRIAL    (87 items)
FASTENAL              (23 items)
```

Check the suppliers you want, click OK — all their unassigned items
get the vendor in one action.  Replaces the old workflow of
filtering by supplier and applying vendor to visible rows.

---

## Settings Dialog

**More > Settings** opens a proper dialog instead of hand-editing
JSON.  Current settings:

- Check for updates on startup (toggle)
- Mixed export behavior (all exportable / immediate only / ask)
- Shared data folder (browse)
- Default scan folder (browse)

---

## PO Memo

A text field on the Review tab lets you attach a note to every
exported PO row.  The memo appears as a Notes column in the xlsx
file.  Per-item notes take priority when both exist.

---

## Assignment Summary

After the auto-assign pipeline runs, a dialog shows the full
breakdown instead of a one-line status message:

- Total items loaded
- Auto-assigned from receipt history
- Needing manual vendor assignment
- Review / Warning / Dead stock counts

---

## Dead Stock Report (xlsx)

**More > Export Reports > Dead Stock** now writes a print-ready xlsx
instead of a basic CSV.  Grouped by vendor with:

- Red headers, vendor subtotals with dollar values
- Money-formatted unit cost and on-hand value columns
- Landscape layout, fit-to-width for printing

Hand it to a vendor to negotiate returns.

---

## Progress Bar Fix

The load progress bar was stuck on "Starting file load" for the
entire 30+ second parse on large datasets.  Root cause: Python's
GIL — the CPU-bound CSV parser held the lock and starved the UI
thread.  Fixed with GIL yield points between parse phases.  Progress
now updates live throughout the load.

---

## Repo Cleanup

- Deleted 71 patch-level release notes (v0.1.x through v0.10.x)
- Deleted 6 old roadmap files, stale VERSION, handoff docs
- Removed runtime artifacts from git (cache, trace logs)
- Updated .gitignore to prevent re-tracking
- Total: 87 files removed, ~15,000 lines deleted

---

## Stats

| Metric | Count |
|--------|-------|
| Tests passing | 872 |
| New features | 6 (mismatch, supplier apply, settings, memo, summary, xlsx report) |
| Bug fixes | 1 (GIL progress freeze) |
| Files cleaned | 87 |
