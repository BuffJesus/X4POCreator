import csv
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import export_flow
from models import MaintenanceIssue


class ExportFlowTests(unittest.TestCase):
    def test_build_session_snapshot_captures_expected_fields(self):
        app = SimpleNamespace(
            var_sales_path=SimpleNamespace(get=lambda: "C:\\Reports\\sales.csv"),
            var_po_path=SimpleNamespace(get=lambda: "C:\\Reports\\po.csv"),
            var_susp_path=SimpleNamespace(get=lambda: "C:\\Reports\\susp.csv"),
            var_onhand_path=SimpleNamespace(get=lambda: "C:\\Reports\\onhand.csv"),
            var_minmax_path=SimpleNamespace(get=lambda: "C:\\Reports\\minmax.csv"),
            var_packsize_path=SimpleNamespace(get=lambda: "C:\\Reports\\packs.csv"),
            qoh_adjustments={("AER-", "GH781-4"): {"old": 2, "new": 5}},
            assigned_items=[{"line_code": "AER-", "item_code": "GH781-4", "order_qty": 250}],
            startup_warning_rows=[{"warning_type": "Pack Fallback Conflict"}],
            order_rules={"AER-:GH781-4": {"pack_size": 500}},
        )
        issues = (
            MaintenanceIssue(
                line_code="AER-",
                item_code="GH781-4",
                description="HOSE",
                issue="Set order multiple to 500",
                assigned_vendor="GREGDIST",
                x4_supplier="",
                pack_size="500",
                x4_order_multiple="",
                x4_min="22",
                x4_max="67",
                target_min="22",
                target_max="67",
                sug_min="22",
                sug_max="67",
                qoh_old="2",
                qoh_new="5",
            ),
        )

        snapshot = export_flow.build_session_snapshot(app, "C:\\Exports", ("C:\\Exports\\PO_A.xlsx",), issues)

        self.assertEqual(snapshot.output_dir, "C:\\Exports")
        self.assertEqual(snapshot.loaded_report_paths["sales"], "C:\\Reports\\sales.csv")
        self.assertEqual(snapshot.po_files, ("C:\\Exports\\PO_A.xlsx",))
        self.assertEqual(snapshot.qoh_adjustments[0]["new"], 5)
        self.assertEqual(snapshot.order_rules["AER-:GH781-4"]["pack_size"], 500)

    def test_export_maintenance_csv_writes_ascii_safe_rows(self):
        issues = [
            MaintenanceIssue(
                line_code="AER-",
                item_code="GH781-4",
                description='Bad â€” text "quote"',
                issue="Fix supplier â†’ pack",
                assigned_vendor="GREGDIST",
                x4_supplier="",
                pack_size="500",
                x4_order_multiple="",
                x4_min="22",
                x4_max="67",
                target_min="22",
                target_max="67",
                sug_min="22",
                sug_max="67",
                qoh_old="2",
                qoh_new="5",
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = export_flow.export_maintenance_csv(issues, tmp)
            with open(path, newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(rows[0][0], "Line Code")
        self.assertEqual(rows[1][0], "AER-")
        self.assertEqual(rows[1][2], 'Bad - text "quote"')
        self.assertEqual(rows[1][3], "Fix supplier -> pack")


if __name__ == "__main__":
    unittest.main()
