import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import item_workflow


class ItemWorkflowTests(unittest.TestCase):
    def test_set_effective_order_qty_keeps_fields_aligned(self):
        item = {"order_qty": 7}

        item_workflow.set_effective_order_qty(item, 3, manual_override=True)

        self.assertEqual(item["final_qty"], 3)
        self.assertEqual(item["order_qty"], 3)
        self.assertTrue(item["manual_override"])

    def test_set_effective_order_qty_clamps_negative_qty_to_zero(self):
        item = {"order_qty": 7}

        item_workflow.set_effective_order_qty(item, -12, manual_override=True)

        self.assertEqual(item["final_qty"], 0)
        self.assertEqual(item["order_qty"], 0)
        self.assertTrue(item["manual_override"])

    def test_find_filtered_item_returns_matching_item(self):
        items = [
            {"line_code": "AER-", "item_code": "GH781-4"},
            {"line_code": "AMS-", "item_code": "XLF-1G"},
        ]

        result = item_workflow.find_filtered_item(items, ("AMS-", "XLF-1G"))

        self.assertIs(result, items[1])

    def test_apply_pack_size_edit_updates_item_and_rule(self):
        item = {"line_code": "AER-", "item_code": "GH781-4", "pack_size": 5}
        order_rules = {"AER-:GH781-4": {"order_policy": "standard"}}

        rule_key, rule = item_workflow.apply_pack_size_edit(
            item,
            "12",
            order_rules,
            lambda line_code, item_code: f"{line_code}:{item_code}",
        )

        self.assertEqual(rule_key, "AER-:GH781-4")
        self.assertEqual(item["pack_size"], 12)
        self.assertEqual(rule["pack_size"], 12)
        self.assertNotIn("order_policy", rule)


if __name__ == "__main__":
    unittest.main()
