# Release Notes — v0.6.3

**Date:** 2026-04-08

---

## Summary

v0.6.3 fixes the **second** half of the "Skip filter is missing items"
report.  v0.5.4 fixed the underlying status classification (860 items
hidden under "Review"), but a separate bug in the bulk grid's bucket
index meant the Skip filter was *still* invisibly losing items — this
time to the No Pack bucket.

976 tests pass (6 new regression tests).

---

## The bug

`bulk_item_status` (`ui_bulk.py:699`) is the helper that decides which
Item Status filter bucket an item belongs to.  It used to return a
single label, with `missing_pack` and `dead_stock` taking priority over
the actual status:

```python
if "missing_pack" in item.get("data_flags", []):
    return "No Pack"
if item.get("dead_stock"):
    return "Dead Stock"
status = item.get("status", "ok").lower()
return {"ok": "OK", "review": "Review", "warning": "Warning", "skip": "Skip"}.get(status)
```

So an item with `status="skip"` *and* `missing_pack` got bucketed under
**No Pack** and never appeared in the Skip filter.

Meanwhile, `item_matches_bulk_filter` (line 1098) treats No Pack and
Dead Stock as **additive tags**, not exclusive statuses — its Skip
check is just `status == "skip"`, with no mention of `missing_pack`.
The matcher and the bucket disagreed, and the bucket fast path
(line 1351) wins when only bucket-resolvable filters are active.

**Measured on the user's real `Order/` dataset** (8,409 candidates):

| | Before v0.6.3 | After v0.6.3 |
|---|---:|---:|
| `status == "skip"` total                       | 5,317 |  5,317 |
| Skip bucket size                               |     0 |  5,317 |
| Skip items also tagged `missing_pack`          | 5,317 |  5,317 |

Every single skip item in the dataset also carries the `missing_pack`
flag (the user's items don't have pack-size data), so under the old
code the Skip filter was effectively empty.

---

## The fix

`bulk_item_status` now returns a **tuple of all applicable bucket
labels** instead of a single label.  An item with `status="skip"` and
`missing_pack` returns `("Skip", "No Pack")`; both buckets receive the
item.  The OK bucket still excludes `missing_pack` because the
matcher's OK rule does too.

Supporting changes:

- **`_append_bucket_item`** now accepts a single key or an iterable of
  keys and routes the item to every key.
- **`_replace_bucket_membership`** now operates on the symmetric
  difference of `(old_keys, new_keys)` so an item that already lives in
  multiple buckets doesn't get spuriously dropped or duplicated when
  one tag changes.

---

## Tests

| Release | Tests |
|---------|-------|
| v0.6.2  |   970 |
| v0.6.3  |   976 |

Six new regression tests in `tests/test_ui_bulk.py` (`BulkItemStatusBucketTests`)
covering:

- skip + missing_pack → both buckets
- skip + dead_stock → both buckets
- review + missing_pack → both buckets
- ok + missing_pack → No Pack only (matcher's OK rule excludes missing_pack)
- ok + dead_stock → both buckets
- ok + no flags → OK only

The existing `test_adjust_bulk_summary_for_item_change_updates_cached_counts`
test was updated to reflect the new (correct) multi-bucket membership.

---

## Files changed

- `ui_bulk.py` — `bulk_item_status` returns a tuple; `_append_bucket_item`
  and `_replace_bucket_membership` handle multi-bucket membership
- `tests/test_ui_bulk.py` — new `BulkItemStatusBucketTests` class +
  updated cache-adjustment expectation
- `app_version.py` — bumped to 0.6.3

---

## Related

- v0.5.4 fixed `rules.py:1159` — the *classification* bug that
  promoted zero-need items to "review" instead of "skip".
- v0.6.3 fixes the *bucket index* bug — the same items would have
  matched the Skip filter via `item_matches_bulk_filter` but the bulk
  grid's bucket fast path was bypassing the matcher.

Both fixes are needed.  v0.5.4 made the underlying data correct;
v0.6.3 makes the UI honor it.
