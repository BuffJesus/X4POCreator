# Release Notes — v0.4.1

**Date:** 2026-04-02

---

## Summary

v0.4.1 delivers Phase 6 of the v0.4.x roadmap: a Session History viewer that
lets operators browse past exports directly from the UI without opening JSON
files manually.

854 tests pass. Phase 7 (manual QA with real-world CSVs) remains open.

---

## What changed since v0.4.0

### Phase 6 — Session History Viewer (`ui_session_history.py`, `ui_load.py`, `po_builder.py`)

Past sessions are now accessible from the Load tab without leaving the app.

- **"View Session History" button** added to the Load tab footer — opens the
  Session History dialog at any time, before or after loading files.

- **Session list pane** — all saved session snapshots are listed most-recent
  first with: date/time, item count, unique vendor count, and export scope
  label. Selecting a row populates the item detail pane below.

- **Item detail pane** — shows every assigned item from the selected session:
  Line Code, Item Code, Description, Vendor, Suggested Qty, Final Qty. The
  pane updates live as the session selection changes.

- **Filter bar** — type any text to narrow the item detail pane by item code
  or vendor (case-insensitive, partial match). Useful for quickly locating a
  specific part or all items from one vendor in a past session.

- **Copy Item History button** — select any item in the detail pane and click
  "Copy Item History" to copy that item's order history across *all* sessions
  to the clipboard as tab-separated text (Session Date, Line Code, Item Code,
  Vendor, Suggested Qty, Final Qty). Ready to paste into Excel or any other
  tool without manual JSON inspection.

- **No new file I/O** — the dialog re-uses `storage.load_session_snapshots`
  with `max_count=None` to load all available snapshots from the existing
  `sessions/` directory.

---

## Test count

| Release | Tests |
|---------|-------|
| v0.3.0  |   756 |
| v0.4.0  |   830 |
| v0.4.1  |   854 |

24 new tests in `tests/test_session_history.py` covering `_snapshot_summary`,
`_snapshot_items`, `_item_history_rows`, and `_format_tsv`.
