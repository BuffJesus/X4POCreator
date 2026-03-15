import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import po_builder
from models import AppSessionState


class SessionStateTests(unittest.TestCase):
    def test_app_session_state_starts_with_independent_collections(self):
        first = AppSessionState()
        second = AppSessionState()

        first.filtered_items.append({"line_code": "AER-", "item_code": "GH781-4"})

        self.assertEqual(second.filtered_items, [])
        self.assertEqual(first.order_rules, {})

    def test_po_builder_properties_proxy_to_session_state(self):
        fake_app = SimpleNamespace(session=AppSessionState())

        po_builder.POBuilderApp.filtered_items.fset(fake_app, [{"item_code": "GH781-4"}])
        result = po_builder.POBuilderApp.filtered_items.fget(fake_app)

        self.assertEqual(result, [{"item_code": "GH781-4"}])
        self.assertIs(fake_app.session.filtered_items, result)

    def test_filtered_items_property_syncs_bulk_caches_on_assignment(self):
        keep_item = {"line_code": "AER-", "item_code": "GH781-4"}
        drop_item = {"line_code": "AMS-", "item_code": "DROP"}
        fake_app = SimpleNamespace(
            session=AppSessionState(),
            _bulk_row_index_generation=0,
            _bulk_row_index_cache={"generation": 0, "by_row_id": {}, "by_key": {}},
            _bulk_row_render_cache={
                po_builder.ui_bulk.bulk_row_id(keep_item): (("sig",), ("row",)),
                po_builder.ui_bulk.bulk_row_id(drop_item): (("sig",), ("row",)),
            },
        )

        po_builder.POBuilderApp.filtered_items.fset(fake_app, [keep_item])

        self.assertEqual(fake_app.session.filtered_items, [keep_item])
        self.assertIsNone(fake_app._bulk_row_index_cache)
        self.assertEqual(fake_app._bulk_row_index_generation, 1)
        self.assertEqual(list(fake_app._bulk_row_render_cache.keys()), [po_builder.ui_bulk.bulk_row_id(keep_item)])
        self.assertEqual(fake_app._bulk_summary_counts, {"total": 1, "assigned": 0, "review": 0, "warning": 0})
        self.assertEqual(fake_app._bulk_line_code_values, ["AER-"])

    def test_po_builder_mapping_properties_proxy_to_session_state(self):
        fake_app = SimpleNamespace(session=AppSessionState())

        po_builder.POBuilderApp.suspense_carry.fset(fake_app, {("AER-", "GH781-4"): {"qty": 2}})
        result = po_builder.POBuilderApp.suspense_carry.fget(fake_app)

        self.assertEqual(result, {("AER-", "GH781-4"): {"qty": 2}})
        self.assertIs(fake_app.session.suspense_carry, result)


if __name__ == "__main__":
    unittest.main()
