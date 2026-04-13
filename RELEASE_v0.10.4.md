# PO Builder v0.10.4 — Help Refresh

**The Help tab now matches the app.**

All help content updated to reflect the v0.10.x feature set.  Stale
tkinter references removed, new features documented, ordering logic
explanations rewritten to match current behavior.

872 tests pass.

---

## What Changed

### Overview
- Sidebar tab names replace old tkinter tab layout
- Order Value summary card documented
- Individual Assign references removed (workflow consolidated into
  Bulk grid with auto-assign)

### Ordering Logic
- Target stock: explains that operator-set max is now authoritative
- Pack-adjusted max: documents the credibility check for auto-noise
  (bolts with max=10, pack=100)
- Pack-overshoot defer: explains the 50% stock / 25% pack tolerance
  logic and when items get deferred vs ordered
- Dead stock: documents velocity-aware detection (2x normal cycle)

### Bulk Assign
- New columns documented: Unit Cost, Ext Cost, Last Sale, Last Receipt
- Shift+click secondary sort (up to 3 levels)
- Column visibility via right-click header

### Shortcuts
- Shift+click column header for secondary sort
- Ctrl+K command palette
- Updated quick filter pill list: Dead Stock, Deferred

### Troubleshooting
- Removed tksheet installation reference (no longer relevant)
- Added tip: press Enter on any warning item to see Activity & Risk
- Updated warning explanation to include deferred and dead stock
