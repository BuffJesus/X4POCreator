# PO Builder v0.10.5 — Analysis Reports

**Know what you're sitting on, not just what you're ordering.**

PO files tell you what to buy.  These reports tell you what to stop
buying, what got deferred, and where the money is going.  Three new
CSV exports live under **More > Export Reports** on the bulk toolbar.

872 tests pass.

---

## Dead Stock Report

One CSV with every item flagged as dead stock — grouped by vendor
(unassigned items grouped separately).

Each row includes QOH, unit cost, **on-hand value** (what you're
holding in dead inventory), last sale date, days since last sale,
and average days between sales.  The summary at the top of the
export dialog shows total dead-stock value across all vendors.

Use it to:
- Hand a vendor their dead-stock list and negotiate returns
- Identify which product lines are accumulating dormant inventory
- Prioritize cleanup by dollar value, not just item count

---

## Deferred Items Report

Every item where the pack-overshoot defer logic (v0.10.1) decided
to skip this cycle — with the data to decide whether that was right.

Each row shows QOH, max, **stock percentage**, pack size, raw need,
unit cost, and the full "why" explanation.  Sorted by vendor.

Use it to:
- Review what the system decided not to order and why
- Override specific items if the deferral doesn't make sense
- Track deferred items across sessions to catch items that keep
  getting pushed

---

## Session Summary

A single-page overview of the entire ordering session:

- Total items, assigned, unassigned
- Counts for review, warnings, skip, dead stock, deferred
- Estimated total order value
- Per-vendor breakdown: item count and estimated order value

Use it to:
- Attach to internal approval workflows ("this week's run is $47K
  across 12 vendors")
- Compare week-over-week ordering patterns
- Spot vendors with unusually high or low activity

---

## How to Export

1. Load data and assign vendors as usual
2. On the Bulk grid toolbar, click **More**
3. Hover over **Export Reports**
4. Choose the report — a folder picker opens
5. The CSV is written with a datestamp in the filename

Reports can be exported at any point during the session — before or
after the PO export.  They reflect the current state of the grid.

---

## Stats

| Metric | Count |
|--------|-------|
| Tests passing | 872 |
| New exportable reports | 3 |
| New module | `analysis_reports.py` |
