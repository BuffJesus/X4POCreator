import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui_session_history import (
    _format_tsv,
    _item_history_rows,
    _snapshot_items,
    _snapshot_summary,
)


def _make_snap(created_at, items, scope="all items"):
    return {
        "created_at": created_at,
        "export_scope_label": scope,
        "assigned_items": items,
    }


def _make_item(line_code="AER-", item_code="ABC123", vendor="ACME",
               suggested_qty=10, final_qty=12, description="Widget"):
    return {
        "line_code": line_code,
        "item_code": item_code,
        "description": description,
        "vendor": vendor,
        "suggested_qty": suggested_qty,
        "final_qty": final_qty,
    }


class TestSnapshotSummary(unittest.TestCase):
    def test_basic(self):
        snap = _make_snap(
            "2026-03-15T10:30:00",
            [
                _make_item(vendor="ACME"),
                _make_item(item_code="DEF456", vendor="BOLT"),
                _make_item(item_code="GHI789", vendor="ACME"),
            ],
        )
        s = _snapshot_summary(snap)
        self.assertEqual(s["date_str"], "2026-03-15 10:30:00")
        self.assertEqual(s["item_count"], 3)
        self.assertEqual(s["vendor_count"], 2)
        self.assertEqual(s["scope"], "all items")

    def test_empty_snapshot(self):
        snap = _make_snap("2026-01-01T00:00:00", [])
        s = _snapshot_summary(snap)
        self.assertEqual(s["item_count"], 0)
        self.assertEqual(s["vendor_count"], 0)

    def test_missing_created_at(self):
        snap = {"assigned_items": []}
        s = _snapshot_summary(snap)
        self.assertEqual(s["date_str"], "—")

    def test_vendor_normalization_deduplicates_case(self):
        snap = _make_snap(
            "2026-02-01T00:00:00",
            [_make_item(vendor="acme"), _make_item(vendor="ACME")],
        )
        s = _snapshot_summary(snap)
        self.assertEqual(s["vendor_count"], 1)

    def test_blank_vendor_not_counted(self):
        snap = _make_snap(
            "2026-02-01T00:00:00",
            [_make_item(vendor=""), _make_item(vendor="BOLT")],
        )
        s = _snapshot_summary(snap)
        self.assertEqual(s["vendor_count"], 1)


class TestSnapshotItems(unittest.TestCase):
    def _snap(self):
        return _make_snap(
            "2026-03-01T08:00:00",
            [
                _make_item(item_code="ABC123", vendor="ACME", final_qty=5, suggested_qty=4),
                _make_item(item_code="DEF456", vendor="BOLT", final_qty=0, suggested_qty=0),
                _make_item(item_code="GHI789", vendor="ACME", final_qty=10, suggested_qty=8),
            ],
        )

    def test_no_filter_returns_all(self):
        rows = _snapshot_items(self._snap())
        self.assertEqual(len(rows), 3)

    def test_filter_by_item_code(self):
        rows = _snapshot_items(self._snap(), "abc123")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_code"], "ABC123")

    def test_filter_by_vendor(self):
        rows = _snapshot_items(self._snap(), "acme")
        self.assertEqual(len(rows), 2)

    def test_filter_partial_match(self):
        rows = _snapshot_items(self._snap(), "ghi")
        self.assertEqual(len(rows), 1)

    def test_zero_qty_rendered_as_empty_string(self):
        rows = _snapshot_items(self._snap())
        row = next(r for r in rows if r["item_code"] == "DEF456")
        self.assertEqual(row["final_qty"], "")
        self.assertEqual(row["suggested_qty"], "")

    def test_positive_qty_rendered_as_int(self):
        rows = _snapshot_items(self._snap())
        row = next(r for r in rows if r["item_code"] == "ABC123")
        self.assertEqual(row["final_qty"], 5)
        self.assertEqual(row["suggested_qty"], 4)

    def test_empty_snap_returns_empty(self):
        snap = _make_snap("2026-01-01T00:00:00", [])
        self.assertEqual(_snapshot_items(snap), [])

    def test_filter_no_match_returns_empty(self):
        rows = _snapshot_items(self._snap(), "ZZZZZ")
        self.assertEqual(rows, [])


class TestItemHistoryRows(unittest.TestCase):
    def _snapshots(self):
        # most-recent first
        return [
            _make_snap("2026-03-15T00:00:00", [_make_item(final_qty=14, suggested_qty=12)]),
            _make_snap("2026-02-01T00:00:00", [_make_item(final_qty=10, suggested_qty=10)]),
            _make_snap("2026-01-01T00:00:00", [_make_item(item_code="OTHER", final_qty=5)]),
        ]

    def test_collects_across_snapshots_where_item_present(self):
        rows = _item_history_rows(self._snapshots(), "AER-", "ABC123")
        self.assertEqual(len(rows), 2)

    def test_most_recent_first(self):
        rows = _item_history_rows(self._snapshots(), "AER-", "ABC123")
        self.assertEqual(rows[0]["final_qty"], 14)
        self.assertEqual(rows[1]["final_qty"], 10)

    def test_date_formatted(self):
        rows = _item_history_rows(self._snapshots(), "AER-", "ABC123")
        self.assertEqual(rows[0]["date_str"], "2026-03-15 00:00:00")

    def test_item_not_in_any_snapshot_returns_empty(self):
        rows = _item_history_rows(self._snapshots(), "AER-", "NOPE99")
        self.assertEqual(rows, [])

    def test_empty_snapshots_returns_empty(self):
        rows = _item_history_rows([], "AER-", "ABC123")
        self.assertEqual(rows, [])

    def test_one_entry_per_snapshot(self):
        # Snapshot with duplicate item entries — only first match used
        snap = _make_snap("2026-03-01T00:00:00", [
            _make_item(final_qty=5),
            _make_item(final_qty=99),  # duplicate item_code in same snapshot
        ])
        rows = _item_history_rows([snap], "AER-", "ABC123")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["final_qty"], 5)


class TestFormatTsv(unittest.TestCase):
    _COLS = [("a", "Col A"), ("b", "Col B"), ("c", "Col C")]

    def test_header_row(self):
        result = _format_tsv([], self._COLS)
        self.assertEqual(result, "Col A\tCol B\tCol C")

    def test_data_rows(self):
        rows = [{"a": 1, "b": "x", "c": ""}, {"a": 2, "b": "y", "c": 3}]
        lines = _format_tsv(rows, self._COLS).split("\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1], "1\tx\t")
        self.assertEqual(lines[2], "2\ty\t3")

    def test_missing_key_renders_empty(self):
        rows = [{"a": 1}]  # b and c missing
        line = _format_tsv(rows, self._COLS).split("\n")[1]
        self.assertEqual(line, "1\t\t")
