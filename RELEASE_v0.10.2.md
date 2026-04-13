# PO Builder v0.10.2 — Cost Columns + Secondary Sort

**See the money before you commit.  Sort by two columns at once.**

872 tests pass.

---

## New: Unit Cost and Extended Cost Columns

The bulk grid now shows two new columns after Pack Size:

- **Unit Cost** — replacement cost per unit from inventory (`$X.XX`)
- **Ext Cost** — unit cost multiplied by Final Qty (`$X.XX`)

Both columns are right-aligned, sortable, and available in the
column visibility context menu (right-click any header).  Extended
cost updates live as you change Final Qty.

Use Ext Cost to spot high-dollar orders at a glance, sort by it to
prioritize vendor review by spend, or hide both columns if you don't
need them.

---

## New: Shift+Click Secondary Sort

Click a column header to sort by it.  **Hold Shift and click another
header** to add a secondary sort (up to 3 levels).

Examples:
- Sort by Vendor, then Shift+click Ext Cost — see each vendor's
  items ordered by dollar value
- Sort by Status, then Shift+click Line Code — group exceptions
  by product line
- Sort by Risk, then Shift+click QOH — highest risk items with
  lowest stock first

Numeric columns (cost, qty, percentages) sort numerically, not
alphabetically.  Click without Shift to reset to a single sort.

---

## Stats

- **872 tests pass**
- **2 new columns** (Unit Cost, Ext Cost)
- **Multi-column sort** (up to 3 levels via Shift+click)
