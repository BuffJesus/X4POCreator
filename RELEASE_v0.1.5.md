# PO Builder v0.1.5

Release date: 2026-03-11

## Summary

This release focuses on functional reliability. It hardens report parsing, inventory merging, suspense carry persistence, and order history handling so the app behaves more predictably with imperfect X4 exports and persisted JSON data.

## Highlights

- Made JSON-backed app data safer to load by rejecting wrong top-level payload shapes instead of accepting corrupted or mismatched content.
- Improved folder scan and parser tolerance for CSV files with leading blank rows across sales, suspended-items, and pack-size/order-multiple reports.
- Fixed old open PO warnings so they include PO references when the source report provides them.
- Prevented blank min/max QOH and replacement-cost fields from overwriting valid on-hand inventory values during load.
- Pruned stale suspense carry entries from the persisted file instead of only ignoring them in memory.
- Cleaned up order history persistence so zero-quantity and invalid rows are not saved as real orders, and recent-order lookups normalize vendor values.

## Functional Detail

- `order_rules.json`, `order_history.json`, `suspense_carry.json`, and settings loads now fall back safely when the file shape is invalid.
- `parse_suspended_csv(...)` and `parse_pack_sizes_csv(...)` now handle leading blank rows in both X4-style and generic CSV formats.
- `parse_po_listing_csv(...)` now captures `po_number` when present, improving open-PO review context.
- Min/max parsing now preserves blank `QOH` and cost fields as missing data instead of forcing `0.0`.
- Suspense carry saves now remove expired carry rows from disk.
- Order history saves now skip non-orders and keep vendor codes normalized for recent-order display.

## Verification

- `python -m unittest discover -s tests -q`
