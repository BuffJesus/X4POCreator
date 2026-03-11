import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import maintenance_flow
from models import AppSessionState


class MaintenanceFlowTests(unittest.TestCase):
    def test_build_maintenance_candidates_merges_filtered_and_assigned_items(self):
        session = AppSessionState(
            filtered_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "vendor": "MOTION",
                "pack_size": 6,
                "data_flags": ["missing_pack"],
                "order_policy": "standard",
            }],
            assigned_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "vendor": "SOURCE",
            }],
            inventory_source_lookup={("AER-", "GH781-4"): {"supplier": "MOTION", "min": 1, "max": 3}},
            inventory_lookup={("AER-", "GH781-4"): {"min": 2, "max": 4}},
            duplicate_ic_lookup={"GH781-4": {"AER-", "ALT-"}},
            qoh_adjustments={("AER-", "GH781-4"): {"old": 1, "new": 5}},
        )

        candidates = maintenance_flow.build_maintenance_candidates(
            session,
            suggest_min_max=lambda key: (2, 4),
            get_x4_pack_size=lambda key: 6,
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.session.vendor, "SOURCE")
        self.assertEqual(candidate.session.pack_size, 6)
        self.assertEqual(candidate.session.duplicate_line_codes, ("ALT-",))
        self.assertEqual(candidate.session.qoh_new, 5)
        self.assertEqual(candidate.suggested.max_qty, 4)

    def test_build_maintenance_candidates_adds_qoh_only_entries(self):
        session = AppSessionState(
            inventory_source_lookup={("BAT-", "CR2032"): {"supplier": "UNISELE"}},
            inventory_lookup={("BAT-", "CR2032"): {"min": None, "max": None}},
            qoh_adjustments={("BAT-", "CR2032"): {"old": 2.0, "new": 5.0}},
        )

        candidates = maintenance_flow.build_maintenance_candidates(
            session,
            suggest_min_max=lambda key: (None, None),
            get_x4_pack_size=lambda key: None,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].key.item_code, "CR2032")
        self.assertEqual(candidates[0].session.qoh_old, 2.0)
        self.assertEqual(candidates[0].session.qoh_new, 5.0)


if __name__ == "__main__":
    unittest.main()
