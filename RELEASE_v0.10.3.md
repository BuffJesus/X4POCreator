# PO Builder v0.10.3 — Data Visibility + Smarter Dead Stock

**The data was always there. Now you can see it.**

The parsers have been computing sales velocity, receipt frequency,
vendor confidence, and cost data since v0.9.0 — but most of it was
invisible to the operator, buried in internal logic.  This release
pulls it all to the surface: new grid columns, a richer item details
dialog, an order value summary card, and two new quick filters that
let you isolate dormant and deferred items in one click.

The dead stock algorithm also gets smarter.  Instead of waiting a
full year to flag an item, it now watches each item's normal sales
rhythm and flags it when it goes silent for twice its usual cycle.

872 tests pass.

---

## See the Money: Order Value Card

The summary bar at the top of the bulk grid now shows **estimated
total order value** for all assigned items — Final Qty multiplied by
unit replacement cost, summed across every vendor.

Updates live as you assign vendors, adjust quantities, or remove
items.  Answers the weekly question: *"How much are we committing
this run?"* — before you hit Export.

---

## New Columns: Last Sale & Last Receipt

Two new sortable columns show when each item last moved:

- **Last Sale** — date of the most recent sale from the X4 export
- **Last Receipt** — date of the most recent receipt

Sort by Last Sale descending to spot items going stale.  Both
columns are hidden by default — right-click any header to toggle
them on.

---

## Enriched Item Details

Press Enter on any row to open the item details dialog.  The new
**Activity & Risk** section surfaces everything the system knows
about the item beyond the grid columns:

| Field | What it tells you |
|-------|-------------------|
| Unit Cost | Replacement cost per unit |
| Last Sale / Last Receipt | Most recent activity dates |
| Days Since Last Sale | How long since this item moved |
| Stockout Risk | 0–100% risk score |
| Dead Stock | Whether the item is flagged dormant |
| Recency Confidence | How reliable the ordering recommendation is |
| Receipt Primary Vendor | Who you usually buy this from |
| Vendor Confidence | How consistent that vendor relationship is |
| Receipt Pack Candidate | What pack size receipt history suggests |
| Receipt Pack Confidence | How reliable that suggestion is |
| Target Basis | Why the system chose this target stock level |
| Deferred | Whether a pack overshoot caused the order to defer |

---

## Smarter Dead Stock: Velocity-Aware Detection

The old rule was simple: no sale in 365 days = dead stock.  That
missed items that were clearly going dormant but hadn't crossed the
one-year line.

**New rule:** an item also flags as dead stock when it hasn't sold
in **twice its normal sales cycle**, with a minimum floor of 90
days.

| Item | Normal cycle | Flagged after |
|------|-------------|---------------|
| Bolts (sells every 45 days) | 45 days | **90 days** (2x, hits floor) |
| Bearings (sells every 60 days) | 60 days | **120 days** (2x) |
| Seasonal filter (sells every 180 days) | 180 days | **360 days** (2x) |
| Unknown cycle (no data) | — | **365 days** (original rule) |

The original 365-day rule still applies as a backstop for items
without velocity data.

---

## Deferred Items Now Visible

When v0.10.1's pack-overshoot defer logic decides to skip an order
(stock is comfortable, pack would significantly overshoot max), the
item previously got a silent `suggested_qty = 0` with no visual
indicator.

Now these items get:
- A **`deferred_pack_overshoot`** flag in their reason codes
- **Warning** status in the grid (amber tint, visible in Warnings)
- A clear note in the item details dialog
- Their own **Deferred** quick filter pill

The operator can review all deferred items in one click and decide
whether to override or let them ride to next cycle.

---

## New Quick Filter Pills

Two new one-click filters on the bulk toolbar:

- **Dead Stock** — isolate all items flagged dormant by the
  velocity-aware or 365-day rule
- **Deferred** — isolate all items where a pack overshoot caused
  the system to suggest deferring

Click **All** to reset.

---

## Stats

| Metric | Count |
|--------|-------|
| Tests passing | 872 |
| New grid columns | 2 (Last Sale, Last Receipt) |
| New summary cards | 1 (Order Value) |
| New quick filter pills | 2 (Dead Stock, Deferred) |
| Enriched dialogs | 1 (Activity & Risk in item details) |
| Algorithm improvements | 1 (velocity-aware dead stock) |
| Warning upgrades | 1 (deferred items visible) |
