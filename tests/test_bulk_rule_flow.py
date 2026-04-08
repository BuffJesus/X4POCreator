import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bulk_rule_flow


def _make_app(order_rules=None):
    saved = []
    app = SimpleNamespace(
        order_rules=dict(order_rules or {}),
        _save_order_rules=lambda: saved.append(1),
    )
    app._saved = saved
    return app


class TestApplyBulkRuleEdit(unittest.TestCase):

    def test_sets_pack_size(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["AER-:GH781"], {"pack_size": "10"})
        self.assertEqual(app.order_rules["AER-:GH781"]["pack_size"], 10)

    def test_sets_min_order_qty(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["AER-:GH781"], {"min_order_qty": "5"})
        self.assertEqual(app.order_rules["AER-:GH781"]["min_order_qty"], 5)

    def test_sets_cover_days(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["AER-:GH781"], {"cover_days": "14"})
        self.assertEqual(app.order_rules["AER-:GH781"]["minimum_cover_days"], 14.0)

    def test_sets_order_policy_and_locks(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["AER-:GH781"], {"order_policy": "pack_trigger"})
        rule = app.order_rules["AER-:GH781"]
        self.assertEqual(rule["order_policy"], "pack_trigger")
        self.assertTrue(rule["policy_locked"])

    def test_blank_policy_not_applied(self):
        app = _make_app({"AER-:GH781": {"order_policy": "standard"}})
        bulk_rule_flow.apply_bulk_rule_edit(app, ["AER-:GH781"], {"order_policy": "", "pack_size": "12"})
        self.assertNotIn("policy_locked", app.order_rules["AER-:GH781"])
        self.assertEqual(app.order_rules["AER-:GH781"]["order_policy"], "standard")

    def test_invalid_policy_not_applied(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["AER-:GH781"], {"order_policy": "bogus_policy", "pack_size": "10"})
        self.assertNotIn("order_policy", app.order_rules["AER-:GH781"])

    def test_preserves_existing_rule_fields(self):
        app = _make_app({"AER-:GH781": {"pack_size": 50, "minimum_cover_days": 30.0}})
        bulk_rule_flow.apply_bulk_rule_edit(app, ["AER-:GH781"], {"min_order_qty": "5"})
        rule = app.order_rules["AER-:GH781"]
        self.assertEqual(rule["pack_size"], 50)
        self.assertEqual(rule["minimum_cover_days"], 30.0)
        self.assertEqual(rule["min_order_qty"], 5)

    def test_applies_to_multiple_keys(self):
        app = _make_app()
        keys = ["AER-:GH781", "MOT-:XY999", "BLT-:AB100"]
        bulk_rule_flow.apply_bulk_rule_edit(app, keys, {"pack_size": "24"})
        for key in keys:
            self.assertEqual(app.order_rules[key]["pack_size"], 24)

    def test_returns_count_of_modified_rules(self):
        app = _make_app()
        count = bulk_rule_flow.apply_bulk_rule_edit(app, ["A:1", "B:2"], {"pack_size": "6"})
        self.assertEqual(count, 2)

    def test_returns_zero_when_no_valid_changes(self):
        app = _make_app()
        count = bulk_rule_flow.apply_bulk_rule_edit(app, ["A:1"], {"pack_size": "", "cover_days": ""})
        self.assertEqual(count, 0)

    def test_saves_after_modification(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["A:1"], {"pack_size": "10"})
        self.assertEqual(len(app._saved), 1)

    def test_no_save_when_no_changes(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["A:1"], {})
        self.assertEqual(len(app._saved), 0)

    def test_zero_pack_not_applied(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["A:1"], {"pack_size": "0"})
        self.assertNotIn("A:1", app.order_rules)

    def test_negative_cover_days_not_applied(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["A:1"], {"cover_days": "-5"})
        self.assertNotIn("A:1", app.order_rules)

    def test_empty_keys_returns_zero(self):
        app = _make_app()
        count = bulk_rule_flow.apply_bulk_rule_edit(app, [], {"pack_size": "10"})
        self.assertEqual(count, 0)

    def test_float_pack_size_truncated_to_int(self):
        app = _make_app()
        bulk_rule_flow.apply_bulk_rule_edit(app, ["A:1"], {"pack_size": "12.7"})
        self.assertEqual(app.order_rules["A:1"]["pack_size"], 12)
