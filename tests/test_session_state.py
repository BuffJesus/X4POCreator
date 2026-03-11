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


if __name__ == "__main__":
    unittest.main()
