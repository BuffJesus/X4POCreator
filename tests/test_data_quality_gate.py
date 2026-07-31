"""Tests for the data-quality gate: broadened scoring, storage on the session
after load, and the overridable prepare_assignment gate seam."""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import load_flow

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False


class DataQualitySummaryTests(unittest.TestCase):
    def _session(self, *, total, unresolved=0, conflicting=0):
        return SimpleNamespace(
            sales_items=[{"i": n} for n in range(total)],
            inventory_lookup={},
            unresolved_detailed_item_codes={f"u{n}" for n in range(unresolved)},
            detailed_sales_conflict_keys={("L", f"c{n}") for n in range(conflicting)},
        )

    def test_clean_load_does_not_gate(self):
        s = self._session(total=100)
        summary = load_flow.compute_data_quality_summary(s)
        self.assertFalse(summary["gate_required"])
        self.assertEqual(summary["quality_score"], 1.0)

    def test_conflicts_count_toward_gate(self):
        # 15 conflicts out of 100 -> 15% > 10% threshold, even with 0 unresolved.
        s = self._session(total=100, conflicting=15)
        summary = load_flow.compute_data_quality_summary(s)
        self.assertTrue(summary["gate_required"])
        self.assertAlmostEqual(summary["quality_score"], 0.85)

    def test_unresolved_and_conflicts_combine(self):
        s = self._session(total=100, unresolved=6, conflicting=6)
        summary = load_flow.compute_data_quality_summary(s)
        self.assertTrue(summary["gate_required"])  # 12% > 10%
        self.assertEqual(summary["unresolved_item_codes"], 6)
        self.assertEqual(summary["conflicting_items"], 6)

    def test_small_gap_below_threshold_does_not_gate(self):
        s = self._session(total=100, unresolved=5)  # 5% < 10%
        summary = load_flow.compute_data_quality_summary(s)
        self.assertFalse(summary["gate_required"])


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class PrepareAssignmentGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls._app = QApplication(sys.argv)

    def test_confirm_cb_abort_stops_assignment(self):
        from ui_qt.session_controller import QtSessionController

        ctrl = QtSessionController()
        ctrl.session.data_quality_summary = {
            "gate_required": True, "quality_score": 0.5,
            "unresolved_item_codes": 40, "conflicting_items": 10, "total_items": 100,
        }
        calls = []

        def deny(summary):
            calls.append(summary)
            return False

        # Gate declines -> prepare_assignment returns False without running the
        # pipeline (no exception even though no real data is loaded).
        result = ctrl.prepare_assignment(confirm_cb=deny)
        self.assertFalse(result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["unresolved_item_codes"], 40)

    def test_no_confirm_cb_does_not_block(self):
        from ui_qt.session_controller import QtSessionController

        ctrl = QtSessionController()
        ctrl.session.data_quality_summary = {"gate_required": True}
        # With no confirm_cb the gate is skipped; prepare_assignment proceeds to
        # the pipeline. With no loaded items it simply returns a falsey/empty
        # result rather than aborting at the gate — assert it did not raise and
        # did not consult a gate.
        try:
            ctrl.prepare_assignment()
        except Exception as exc:  # pragma: no cover - defensive
            self.fail(f"prepare_assignment raised without confirm_cb: {exc}")


if __name__ == "__main__":
    unittest.main()
