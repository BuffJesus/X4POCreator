import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance import build_maintenance_report, build_dead_stock_report_rows
from models import (
    ItemKey,
    MaintenanceCandidate,
    SessionItemState,
    SourceItemState,
    SuggestedItemState,
)


class MaintenanceReportTests(unittest.TestCase):
    def test_supplier_and_pack_changes_are_reported(self):
        issues = build_maintenance_report([
            MaintenanceCandidate(
                key=ItemKey("AER-", "GH781-4"),
                source=SourceItemState(supplier="", order_multiple=None, min_qty=22, max_qty=67),
                session=SessionItemState(
                    description="1/4 2 WIRE AEROQUIP HOSE",
                    vendor="GREGDIST",
                    pack_size=500,
                    target_min=22,
                    target_max=67,
                ),
                suggested=SuggestedItemState(min_qty=22, max_qty=67),
            )
        ])
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertIn("Set supplier to GREGDIST", issue.issue)
        self.assertIn("Set order multiple to 500", issue.issue)
        self.assertEqual(issue.pack_size, "500")
        self.assertEqual(issue.x4_order_multiple, "")

    def test_app_min_max_override_takes_precedence_over_suggestion(self):
        issues = build_maintenance_report([
            MaintenanceCandidate(
                key=ItemKey("AMS-", "TCC-BE"),
                source=SourceItemState(supplier="AMSOIL", order_multiple=6, min_qty=1, max_qty=2),
                session=SessionItemState(
                    description="SYNTH CHAINCASE OIL",
                    vendor="AMSOIL",
                    pack_size=6,
                    target_min=3,
                    target_max=8,
                ),
                suggested=SuggestedItemState(min_qty=1, max_qty=4),
            )
        ])
        self.assertEqual(len(issues), 1)
        self.assertIn("App min/max 1/2 -> 3/8", issues[0].issue)
        self.assertNotIn("Suggested min/max", issues[0].issue)

    def test_suggested_min_max_difference_is_reported_when_app_values_match_source(self):
        issues = build_maintenance_report([
            MaintenanceCandidate(
                key=ItemKey("ACK-", "6035060T"),
                source=SourceItemState(supplier="GREGDIST", order_multiple=None, min_qty=1, max_qty=3),
                session=SessionItemState(
                    description="GORILLA TAPE",
                    vendor="GREGDIST",
                    target_min=1,
                    target_max=3,
                ),
                suggested=SuggestedItemState(min_qty=1, max_qty=2),
            )
        ])
        self.assertEqual(len(issues), 1)
        self.assertIn("Suggested min/max 1/2 differs from X4 1/3", issues[0].issue)

    def test_qoh_only_adjustment_creates_issue(self):
        issues = build_maintenance_report([
            MaintenanceCandidate(
                key=ItemKey("BAT-", "CR2032"),
                source=SourceItemState(supplier="UNISELE", order_multiple=None, min_qty=None, max_qty=None),
                session=SessionItemState(
                    description="BATTERY",
                    qoh_old=2.0,
                    qoh_new=5.0,
                ),
                suggested=SuggestedItemState(),
            )
        ])
        self.assertEqual(len(issues), 1)
        self.assertIn("QOH adjusted: 2 -> 5", issues[0].issue)


class DeadStockReportTests(unittest.TestCase):
    def _item(self, line_code="AER-", item_code="X1", dead_stock=True, days=400, on_po=0, qoh=5):
        return {
            "line_code": line_code,
            "item_code": item_code,
            "description": "Test Part",
            "dead_stock": dead_stock,
            "days_since_last_sale": days,
            "qty_on_po": on_po,
            "inventory": {"qoh": qoh},
        }

    def test_dead_stock_items_appear_in_report(self):
        items = [self._item()]
        rows = build_dead_stock_report_rows(items)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Line Code"], "AER-")
        self.assertEqual(rows[0]["Item Code"], "X1")
        self.assertEqual(rows[0]["Days Since Last Sale"], 400)

    def test_non_dead_stock_items_excluded(self):
        items = [self._item(dead_stock=False)]
        rows = build_dead_stock_report_rows(items)
        self.assertEqual(rows, [])

    def test_discontinue_flagged_shows_yes_when_rule_set(self):
        items = [self._item()]
        order_rules = {"AER-:X1": {"discontinue_candidate": True}}
        rows = build_dead_stock_report_rows(items, order_rules=order_rules)
        self.assertEqual(rows[0]["Discontinue Flagged"], "Yes")

    def test_discontinue_flagged_blank_when_not_set(self):
        items = [self._item()]
        rows = build_dead_stock_report_rows(items)
        self.assertEqual(rows[0]["Discontinue Flagged"], "")

    def test_rows_sorted_by_line_code_then_item_code(self):
        items = [
            self._item(line_code="ZZZ-", item_code="A"),
            self._item(line_code="AAA-", item_code="B"),
        ]
        rows = build_dead_stock_report_rows(items)
        self.assertEqual(rows[0]["Line Code"], "AAA-")
        self.assertEqual(rows[1]["Line Code"], "ZZZ-")

    def test_empty_items_returns_empty(self):
        self.assertEqual(build_dead_stock_report_rows([]), [])


if __name__ == "__main__":
    unittest.main()
