# PO Builder Roadmap to v0.2.5

Status: proposed

Current version: `0.1.10`

Target line: `0.2.0` through `0.2.5`

## Why this roadmap exists

The current ordering logic is already better than the old raw-total approach, but there is still a structural gap around pack-driven edge cases:

- hose, cable, tube, rope, wire, and other reel/coil products
- bolts, nuts, washers, and other bag/box-pack items
- low-max items that can only be purchased in much larger replenishment units
- parts where reorder timing matters more than target-max math

The core issue is that the current algorithm mostly decides:

1. what the target stock should be
2. how much raw need exists below that target
3. how to round the order quantity to the pack

That works for ordinary items, but it is weaker for items where:

- the replenishment unit is much larger than the operational max
- the reorder trigger should happen before the target is breached badly
- the app must tolerate intentional overstock because buying smaller is impossible

## Current algorithm weakness

Today, large-pack items can still behave awkwardly because target stock and reorder timing are too tightly coupled.

Examples:

- Hose on a 300 ft reel with an operational max near 93 ft.
- Bolts in bags of 100 with an operational max near 20 pieces.

Current behavior tends to do one of these:

- wait until stock dips below the normal target and then order a full pack/reel
- mark the item as review-only when the pack is far larger than the max
- rely on manual buy rules to correct the timing

What is missing is an explicit concept of:

- reorder trigger
- replenishment unit
- acceptable intentional overstock
- low-stock reserve threshold
- order-cycle cover
- minimum practical packs on hand
- vendor shipping policy
- shipment release timing
- free-freight threshold consolidation

## Bulk editor correctness risk

The bulk editor now handles large datasets and incremental refreshes better than before, but there is still a workflow-level correctness risk around in-grid editing:

- a cell edit can occasionally apply to the previously edited row or column once before correcting on the next attempt
- this appears most likely when the user edits one cell, then quickly clicks a different cell and edits again before the first edit path has fully settled
- vendor edits are a particularly likely trigger because they cause downstream row recalculation and view refresh work
- the current sheet edit flow uses deferred post-edit processing, a single pending edit slot, and a selection clear at the end of the commit path

That means the app still needs a stronger concept of edit-target integrity:

- the committed edit must always apply to the row and column the user just finished editing
- the next click or active-cell change must not be wiped out by cleanup from the previous edit
- delayed refresh work must not reuse stale row, column, or selection state

## Bulk editor large-session performance risk

The bulk editor is now safer, but very large active sessions can still feel sluggish because some post-edit work still scales with the full active list instead of just the touched rows.

Current pressure points:

- bulk summary updates can still rescan the full active session after simple edits
- any fallback to full filter rebuild still walks all active items
- large sessions that have been visually narrowed down can still pay for hidden items if they remain in `filtered_items`

This matters most when:

- the active session still contains tens of thousands of items
- the user is editing a much smaller working subset
- edits are frequent enough that summary/filter work dominates the actual row mutation cost

## Likely failure modes to eliminate

These are the main edge cases the `0.2.5` line should explicitly harden.

### 1. Previous-cell commit bleed

Example:

- edit vendor on item A
- immediately click pack size on item B
- first pack-size edit lands on item A once
- second attempt lands correctly on item B

Likely cause:

- the sheet still has deferred commit/cleanup work from the first edit when the second target is selected
- previous-edit cleanup clears or overwrites the new active selection

### 2. Single pending-edit slot race

The current bulk-sheet edit flow keeps one `_pending_edit` structure and schedules a delayed post-edit commit.

Risks:

- a second edit can overwrite the first pending edit before it fully drains
- a first scheduled refresh can still clean up after the user has already moved to a second cell
- row and column targeting become timing-sensitive instead of deterministic

### 3. Selection cleanup clobbering the new target

The post-edit flow currently clears selection after applying the committed edit.

Risks:

- the user clicks the next target cell before the previous post-edit callback runs
- the previous callback clears the new target selection or current cell
- keyboard edit and click edit paths drift apart

### 4. Filtered or sorted view row remap risk

If an edit changes a value that affects sorting or filtering:

- the visible row position can change
- a delayed refresh can remap row indices
- the next edit must still bind to the correct row id, not the old visual row index

This is especially sensitive for:

- vendor edits
- final qty edits
- fields that may affect review state or visibility

### 5. Multi-selection / single-cell ambiguity

The bulk editor supports:

- explicit row selection
- cell selection in a single editable column
- current-cell editing
- right-click snapshot selection

Risks:

- a single-cell edit accidentally reuses a prior multi-row target set
- a current-cell edit falls back to stale selected rows
- a right-click snapshot survives longer than it should and contaminates later edits

### 6. Commit-and-move timing drift

Keyboard flows like:

- Enter
- Tab / Shift+Tab
- arrow-key commit and move

need to guarantee:

- the old cell commit is finalized first
- the new current cell is authoritative immediately after the move
- the next edit opens on the moved-to cell, not the pre-move cell

### 7. Undo/history snapshot mismatch

If history capture happens before pending edits drain cleanly:

- undo can represent the wrong before/after state
- one visible edit can become two logical edits
- row removal or fill actions launched right after a cell edit can capture stale state

### 8. Context action crossover

If the user edits a cell and then immediately uses:

- Ignore
- Remove rows
- Fill selected cells
- Clear selected cells
- Bulk vendor assignment

the action must operate on the current intended target, not stale edit-selection state left over from the prior cell edit.

## Desired algorithm direction

For `v0.2.5`, the ordering model should separate these ideas:

1. operational target
- what we would ideally like to keep on hand during normal usage

2. reorder trigger
- the point where we should place an order, even if stock is still above the operational max or near it

3. replenishment unit
- the smallest realistic amount we can buy: pack, bag, case, reel, spool, coil, etc.

4. post-receipt tolerance
- how much over the operational target is acceptable because of pack constraints

5. review gate
- whether the app should auto-order, suggest, or require review

6. order-cycle cover
- whether the item will survive until the next normal vendor order window once routine demand continues

## Execution phases

The remaining road to `v0.2.5` should be executed in phases, not as one flat checklist.

### Phase 0. Reconcile roadmap and preserve current stability

Purpose:

- keep the roadmap truthful about what is already done
- avoid redoing completed bulk-editor and signal-visibility work
- keep packaged-app behavior stable while deeper algorithm changes are prepared

Scope:

- mark completed `0.2.0` / `0.2.1` foundation work
- keep long-window and performance signals conservative
- treat shipping as a later vendor-release layer, not part of the first reorder-core refactor

### Phase 1. Reorder core refactor

Purpose:

- separate reorder trigger, target stock, quantity rounding, and review gating

Why this comes first:

- pack-trigger logic depends on it
- shipping-aware release logic depends on it
- explainability gets much cleaner once the stages are explicit

Target result:

- the code can answer:
  - should this item reorder at all?
  - what target stock is it using?
  - how much would it suggest if it reorders?
  - does the item require review?

### Phase 2. Rule model expansion

Purpose:

- add explicit fields for trigger-driven replenishment and tolerable overstock

Initial fields:

- `reorder_trigger_qty`
- `reorder_trigger_pct`
- `acceptable_overstock_qty`
- `acceptable_overstock_pct`
- `minimum_packs_on_hand`
- `minimum_cover_days`
- `minimum_cover_cycles`

### Phase 3. Pack-trigger behavior

Purpose:

- implement the first real behavior change for hose, bags, boxes, and reels

Target result:

- low-max / large-pack items can trigger early without being treated like suspicious over-orders

### Phase 4. Review and removal coherence

Purpose:

- make downstream review and “not needed” logic respect the smarter trigger model

Target result:

- items no longer get good reorder logic upstream and contradictory review logic downstream

### Phase 5. Vendor shipping policy model

Purpose:

- define vendor-level free-shipping days and freight-threshold rules

Target result:

- the app can reason about when a needed item should be released, not just whether it is needed

### Phase 6. Shipping-aware release logic

Purpose:

- apply vendor shipping policy to actual order release recommendations

Target result:

- release now
- hold for free-shipping day
- hold for freight threshold
- bypass the hold if the shortage is urgent

### Phase 7. Remaining bulk-performance cleanup

Purpose:

- keep very large sessions responsive even when rebuilds are still required

Target result:

- separate full-session, active-filtered, and visible-row performance paths more aggressively

## Proposed policy expansions

### 1. Add explicit pack-aware reorder timing

For large-pack items, do not use only `target_stock - inventory_position > 0` as the reorder trigger.

Instead compute a trigger threshold such as:

- percentage of replenishment unit remaining
- weeks of cover remaining
- safety stock plus lead-time demand
- explicit user-configured reorder floor

Examples:

- 300 ft hose reel:
  - operational max may still be 93
  - reorder trigger might be 60 ft remaining
  - reorder qty is still 300 ft

- bag of 100 bolts:
  - operational max may still be 20
  - reorder trigger may be 20 or 30 remaining depending on movement and lead time
  - reorder qty is still 100

### 2. Introduce a new policy family for large-pack replenishment

Current policies:

- `standard`
- `soft_pack`
- `exact_qty`
- `reel_review`
- `manual_only`

Recommended additions:

- `pack_trigger`
  - buy full pack when inventory falls below a trigger threshold
- `reel_auto`
  - auto-order full reel at a conservative threshold for reliable reel items
- `large_pack_review`
  - similar to current `reel_review`, but generalized beyond hose-like items

These policies should separate:

- how reorder timing works
- whether full-pack auto-order is acceptable
- whether manual review is still required

### 3. Store replenishment rules explicitly

The buy-rule model should eventually support fields such as:

- `pack_size`
- `order_policy`
- `reorder_trigger_qty`
- `reorder_trigger_pct`
- `acceptable_overstock_qty`
- `acceptable_overstock_pct`
- `minimum_packs_on_hand`
- `minimum_cover_days`
- `minimum_cover_cycles`
- `lead_time_days`
- `safety_stock_qty`
- `manual_review_reason`

Not every field must ship at once, but `reorder_trigger_qty` and/or `reorder_trigger_pct` are high-value for these edge cases.

### 4. Add vendor shipping and consolidation policy

The app also needs a vendor-level shipping layer so it can help decide when an item should be released into an order, not just whether demand exists.

Examples:

- vendor ships free on a specific weekday
- vendor ships free above a threshold such as `$2000`
- urgent shortages should still release immediately even if the preferred free-shipping day has not arrived

The algorithm should eventually separate:

- item demand and reorder need
- vendor shipment policy
- order release urgency
- order consolidation opportunity
- freight-threshold progress

Recommended future vendor-policy fields:

- `preferred_free_ship_weekdays`
- `free_freight_threshold`
- `target_consolidation_order_value`
- `ship_hold_days`
- `urgent_release_floor`
- `shipping_policy`

Candidate shipping policies:

- `release_immediately`
  - order as soon as the item qualifies
- `hold_for_free_day`
  - hold non-urgent items until the vendor's free-shipping weekday
- `hold_for_threshold`
  - hold non-urgent items until the order reaches a minimum dollar threshold
- `hybrid_free_day_threshold`
  - prefer a free-shipping day, but also release once a threshold is reached

## Edge cases to support explicitly

### Reel / spool / coil materials

Examples:

- hose
- cable
- tubing
- rope
- wire
- chain in coil/roll form

Requirements:

- detect real reel-style items reliably
- avoid waiting too long to reorder when usage is meaningful
- allow full-reel ordering even when the reel exceeds operational max
- show the user why the item triggered early

### Bag / case / box hardware

Examples:

- bolts
- nuts
- washers
- screws
- clamps

Requirements:

- do not over-review common bag-pack hardware unnecessarily
- allow simple full-bag replenishment when stock falls below practical thresholds
- distinguish “buy full pack because that is the selling unit” from “this is suspicious over-ordering”
- account for routine order cadence when one pack may not last until the next normal weekly order
- avoid recommending a single-pack steady state when fastener demand can exhaust that pack before the next planned vendor order

### Low-movement but mandatory-stock items

Requirements:

- do not suppress all reorder suggestions just because recent demand is sparse
- respect minimum service-level floors and current min values
- allow trigger-based replenishment for critical spares

### High-velocity small-pack items with weekly ordering cadence

Examples:

- common bolt sizes
- popular shop consumables
- fast-moving clamps, fittings, and hardware sold from bag stock

Requirements:

- detect when one replenishment unit is not enough cover until the next routine order cycle
- allow a rule to require more than one pack on hand even if operational max is near one pack
- distinguish “low max because of display/working target” from “safe weekly stock level”
- explain when the app recommends carrying two or more packs because of order cadence, not just immediate shortage

### Expensive / obsolete / risky overstock items

Requirements:

- avoid auto-ordering large packs just because pack rounding allows it
- combine pack logic with dormancy and historical strength
- prefer review when the item is stale or likely obsolete

### Shipping-aware vendor ordering

Requirements:

- support vendor-specific free-shipping weekdays
- support vendor-specific freight-free thresholds
- distinguish urgent replenishment from routine stock consolidation
- explain why an item was held, released, or split across shipment strategies
- avoid holding truly urgent shortages just to optimize freight

## Algorithm work by release

## `0.2.0`

Stabilize the app and keep algorithm changes conservative.

Checklist:

- [x] keep current long-window sales and performance signals stable
- [x] keep missed-reorder and dormant-performer logic review-only
- [x] do not ship aggressive new quantity logic before packaged-app validation is complete

## `0.2.1`

Expose the new signals so they can be used operationally.

Checklist:

- [x] add bulk/review filters for `performance_profile`
- [x] add bulk/review filters for `sales_health_signal`
- [x] add bulk/review filters for `reorder_attention_signal`
- [x] let users find likely missed-reorder items quickly in large datasets

## `0.2.2` - Phase 1: reorder core refactor

Refactor reorder logic so trigger decisions are separate from quantity rounding.

Checklist:

- [ ] split the algorithm into:
  - reorder trigger
  - target stock
  - quantity rounding
  - review gate
- [ ] stop relying only on `raw_need > 0` as the decision to place a replenishment order
- [ ] add tests for full-pack items with small operational max values
- [ ] sketch the vendor shipping-policy model so release timing can be layered on top of reorder need later

## `0.2.3` - Phases 2-3: rule model expansion and pack-trigger behavior

Introduce pack-aware trigger policies.

Checklist:

- [ ] add `pack_trigger` policy or equivalent
- [ ] add rule fields for `reorder_trigger_qty` and/or `reorder_trigger_pct`
- [ ] add rule fields for `acceptable_overstock_qty` and/or `acceptable_overstock_pct`
- [ ] add rule fields for cadence-aware coverage such as:
  - `minimum_packs_on_hand`
  - `minimum_cover_days`
  - `minimum_cover_cycles`
- [ ] allow full-pack replenishment without treating the post-receipt overstock as suspicious by default
- [ ] add explainable `why` text for trigger-driven reorders
- [ ] add vendor-level shipping rules for:
  - free-shipping weekdays
  - freight-free thresholds
- [ ] model "routine stock" vs "urgent shortage" release behavior at the vendor level
- [ ] store enough vendor-policy data to explain why an item was held for a later order

## `0.2.4` - Phases 4-5: review coherence and vendor shipping policy

Generalize reel and large-pack handling.

Checklist:

- [ ] review whether `reel_review` should split into:
  - `reel_auto`
  - `large_pack_review`
  - or a more general replenishment-unit policy model
- [ ] improve detection for real reel items vs ordinary packaged parts
- [ ] add bag/box hardware heuristics so hardware packs do not fall into the wrong review path
- [ ] add cadence-aware heuristics for high-velocity small-pack items so one-pack stock levels are not treated as sufficient by default
- [ ] add regression tests for:
  - 300 ft hose / 93 ft max / early reorder trigger
  - bag of 100 / 20 max
  - stale reel item that should still be review-only
  - active large-pack item that should auto-trigger safely
  - weekly-order bolt item where one bag is not enough cover until the next normal order
- [ ] introduce shipping-aware consolidation logic:
  - hold non-urgent items for free-shipping weekdays
  - hold non-urgent items for freight thresholds
  - release immediately once threshold is reached
  - let urgent shortages bypass holding logic when needed
- [ ] add explainable shipping/release reason text such as:
  - held for Friday free-shipping order
  - released now because vendor threshold was reached
  - released now because the shortage was urgent

## `0.2.5` - Phases 6-7: shipping-aware release and remaining performance cleanup

Use the new pack-aware trigger system in the final recommendation flow.

Checklist:

- [ ] integrate pack-aware trigger logic into the main reorder algorithm
- [ ] support acceptable intentional overstock explicitly
- [ ] let cadence-aware coverage rules increase the effective reorder floor when one pack is not enough to survive until the next routine order
- [ ] ensure “not needed” review respects trigger-based replenishment logic
- [ ] surface trigger reason, replenishment unit, and confidence in item details / review
- [ ] verify that edge-case rules remain explainable to the user
- [ ] integrate shipping-aware release timing into the final recommendation flow
- [ ] let vendor shipping policy influence whether an item is:
  - release now
  - hold for vendor free-shipping day
  - hold for freight threshold
- [ ] treat the paid urgent truck as an override path, not the main consolidation target
- [ ] ensure threshold/free-day holding does not hide urgent shortages or critical service items
- [ ] surface shipping policy, hold reason, and release reason in item details / review

- [ ] guarantee bulk-editor edit-target integrity under rapid click-edit, keyboard-edit, filtered, sorted, and multi-selection workflows
- [ ] document the expected precedence between current cell, selected cells, selected rows, and right-click snapshot state
- [ ] ensure undo/history boundaries still match what the user perceives as one edit
- [ ] separate full-session, active-filtered, and visible-row performance paths so very large sessions do not penalize small working subsets unnecessarily

## Already completed before the remaining phases

These items should be treated as baseline, not future work.

- bulk/review visibility for:
  - `performance_profile`
  - `sales_health_signal`
  - `reorder_attention_signal`
- item-details visibility for long-window sales and performance signals
- conservative missed-reorder and dormant-performer review handling
- major bulk-editor hardening for:
  - pending edit flush before actions
  - filter/sort flush behavior
  - paste flush behavior
  - stale right-click context invalidation
  - bulk-to-dialog and bulk-to-review transition safety
- bulk summary caching and safer incremental refreshes for many common edit paths

## Concrete algorithm ideas to test

These should be tested before final adoption.

### Trigger by percentage of replenishment unit

Example:

- reorder a 300 ft reel when remaining stock drops below 20% of the reel

Pros:

- easy to understand
- matches how many buyers think about reels and packs

Cons:

- too simplistic by itself for slow or seasonal items

### Trigger by weeks of cover remaining

Example:

- if estimated weekly usage is 12 ft and only 4 weeks of cover remain, reorder full reel

Pros:

- demand-aware
- better than pure percentage for uneven pack sizes

Cons:

- only as good as the demand estimate

### Trigger by next-order-cycle survival

Example:

- if a bag of 100 bolts is selling fast enough that one bag on hand will not survive until next week's routine order, reorder before stock drops to a single bag

Pros:

- matches how consolidated weekly ordering actually works
- prevents “technically in stock” parts from running out before the next vendor cycle
- helps with bolts, clamps, fittings, and other small-pack fast movers

Cons:

- requires a trustworthy order-cycle assumption
- can overstock if cadence or demand assumptions are too aggressive

### Trigger by max of several thresholds

Recommended candidate model:

- reorder trigger = max(
  current_min,
  safety_stock_qty,
  reorder_trigger_qty,
  replenishment_unit * reorder_trigger_pct
)

Pros:

- flexible
- handles both operational floors and pack-driven timing

Cons:

- needs careful UI explanation

### Release by vendor shipping policy

Recommended candidate model:

- determine reorder need at the item level
- determine urgency at the item level
- group candidates by vendor
- apply vendor shipping policy:
  - free-shipping weekday
  - freight-free threshold
- decide per item:
  - release now
  - hold for next free shipment window
  - hold until threshold is reached
  - bypass the hold if the shortage is urgent

Pros:

- reflects real purchasing behavior better than item-only logic
- can reduce freight without hiding true shortages
- gives the app a path to smarter vendor-level consolidation

Cons:

- requires explainable vendor policy configuration
- can create confusing results if hold logic is too aggressive

## Testing scenarios that must exist by `0.2.5`

- [ ] 300 ft hose reel with max 93, trigger 60, reorder at 58
- [ ] 300 ft hose reel with max 93, stock 95, no reorder
- [ ] bag of 100 bolts with max 20, trigger 20, reorder at 18
- [ ] bag of 100 bolts on a weekly order cycle: one bag on hand but weekly demand implies stockout before next order, so reorder early
- [ ] bag of 100 bolts with two-bag minimum practical cover: reorder when projected cover falls below two bags even if current max is lower
- [ ] bag of 100 bolts with stale demand and high stock, no reorder
- [ ] reel item with dormant sales and no recency signal, review instead of auto-order
- [ ] manual override item preserves user quantity
- [ ] trigger-based item is not auto-removed by “Remove Not Needed”
- [ ] vendor ships free on Friday only: non-urgent items hold until Friday
- [ ] vendor reaches free-freight threshold at `$2000`: held items release once threshold is met
- [ ] vendor below threshold with no urgency: items stay held with an explainable reason
- [ ] urgent shortage overrides free-day or threshold hold
- [ ] held-for-shipping item is still visible in review with the release reason

- [ ] edit vendor on one row, then immediately edit pack size on a different row: second edit applies to the intended row on the first attempt
- [ ] commit with Tab or Enter, then immediately edit the newly focused cell: no previous-cell bleed
- [ ] edit while sorted or filtered: next edit still applies by row id, not stale visual row position
- [ ] perform a cell edit, then immediately run Ignore or Remove on selected rows: action uses current intended selection only

## Definition of success

By `v0.2.5`, PO Builder should be able to explain edge cases like these in plain language:

- “This hose is ordered by the reel, so the app triggered replenishment early at the configured low-stock threshold.”
- “This hardware item is bought by the bag, so the app recommends one bag even though operational max is lower.”
- “This bolt item is bought weekly, and one bag would not last until the next normal order cycle, so the app recommended ordering early.”
- “This item’s working max is low, but the app kept more than one pack because routine order cadence would otherwise create a stockout.”
- “This item used to sell well, but recency is weak, so it was flagged for review instead of automatic reorder.”
- “This item was held for the vendor's Friday free-shipping order because stock is routine, not urgent.”
- “This item was released immediately even though the vendor has a free-shipping stock order because the shortage was urgent.”
- “This vendor order was released because the free-freight threshold was reached.”

That is the bar: not just better numbers, but better reasoning users can trust.
