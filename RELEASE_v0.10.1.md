# PO Builder v0.10.1 — Pack Quantity Fixes + Auto-Update

**Three ordering algorithm fixes and automatic update checking.**

This release fixes a family of pack-quantity bugs where the system
either ordered too much (2 rolls of hose instead of 1), ordered
when it shouldn't have (stock was already comfortable), or used a
nonsensical max as the target (bolts with max=10 that come in boxes
of 100).  It also wires up automatic update checking so the operator
gets notified when a new release is available on GitHub.

872 tests pass (881 in rules suite, including 8 new credibility tests).

---

## Pack Quantity Ordering Fixes

### 1. Suggested max no longer overrides operator-set max

**Before:** The system took `max(current_max, suggested_max)` as the
target stock level.  When annual sales were high, the formula-driven
`suggested_max` could far exceed the operator's intentional limit.

**Example:** Hose 114-08 had max=420 (set by the operator based on
storage capacity), but `suggested_max=769` from high annual sales.
The system targeted 769, computed `raw_need=497`, and rounded up to
2 full rolls (600 ft) — when 1 roll would have been plenty.

**After:** `current_max` is authoritative when set.  `suggested_max`
only fills the gap when no explicit max exists.  The hose now targets
420, needs 148, orders 1 roll (300).

### 2. Pack-overshoot defer for comfortable stock

**Before:** When a full pack would overshoot max, the system either
ordered the pack anyway or routed to manual review.

**After:** When ALL of these are true, the system suggests deferring
to the next cycle (order 0):
- `raw_need < pack_qty` (the order is purely pack-rounding waste)
- `pack_qty <= max` (if pack > max, overshoot is inherent to the item)
- `QOH >= 50% of max` (stock is comfortable)
- Overshoot would exceed 25% of a pack (small overshoots near pack
  multiples are acceptable)

**Example:** Hose at 272/420 ft (65% stocked), pack=300.  One roll
would push stock to 572 (152 over max, 51% of a pack).  System
defers — stock is comfortable, order next cycle when it drops.

But: hose at 168/420 ft (40%) still orders.  And hose with max=93,
pack=300 (pack > max, inherent overshoot) still orders — the
deferral only triggers when the overshoot is avoidable.

### 3. Max credibility check for auto-calculated nonsense

**Before:** X4 auto-calculates min/max without considering pack sizes.
Bolts with annual sales of 8 get max=10 — but they come in boxes of
100.  With the target_stock fix (#1), we'd now target 10, get
`raw_need=7`, and the pack-rounding logic would try to order 100.
The overstock check would then force manual review for what should be
a routine hardware restock.

**After:** When `pack_qty > current_max * 5`, the max is treated as
auto-noise and the target is adjusted up to at least one full pack.
Tagged `"pack_adjusted_max"` in the why text so the operator can see
the adjustment.

| Item | max | pack | Ratio | Credible? | Target |
|------|-----|------|-------|-----------|--------|
| 1/4" bolt | 10 | 100 | 10x | No | **100** (adjusted) |
| 1/4" nut | 5 | 100 | 20x | No | **100** (adjusted) |
| Hyd hose | 93 | 300 | 3.2x | Yes | 93 (trusted) |
| Hyd hose | 420 | 300 | 0.7x | Yes | 420 (trusted) |
| Screws | 500 | 100 | 0.2x | Yes | 500 (trusted) |

The 5x threshold separates hardware items with auto-noise (bolt/nut
at 10-20x) from reel stock with intentional small-max settings
(hose at 3.2x).

---

## Automatic Update Checking

The app now checks GitHub releases in the background on startup.
When a newer version is found:

- Status bar shows **"Update available: vX.Y.Z"** in accent color
- Click the label to open the update dialog
- If running as a packaged .exe: offers one-click download + restart
- If running from source: opens the release page in the browser
- Controlled by `check_for_updates_on_startup` in settings (default: on)

---

## Cleanup

- Deleted `loading_flow.py` + test — orphaned tkinter animation code
  that survived the v0.10.0 migration
- `update_flow.py` — `launch_updater_and_exit` now uses `app.close()`
  (Qt) instead of the old `root.destroy()` (tkinter)

---

## Stats

- **872 tests pass** (8 new for max credibility)
- **3 ordering algorithm fixes** (target_stock, defer, credibility)
- **1 new module** (`update_check.py` — GitHub API + version comparison)
- **1 deleted module** (`loading_flow.py` — dead code)
