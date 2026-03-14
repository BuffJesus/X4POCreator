import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_individual


class DummyVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class UIIndividualTests(unittest.TestCase):
    def test_vendor_history_suggestions_orders_by_total_qty_then_recency(self):
        app = SimpleNamespace(
            recent_orders={
                ("AER-", "GH781-4"): [
                    {"vendor": "source", "qty": 1, "date": "2026-03-10"},
                    {"vendor": "motion", "qty": 3, "date": "2026-03-08"},
                    {"vendor": "source", "qty": 4, "date": "2026-03-11"},
                ]
            }
        )

        suggestions = ui_individual.vendor_history_suggestions(app, ("AER-", "GH781-4"))

        self.assertEqual(suggestions, ["SOURCE", "MOTION"])

    def test_suggested_vendor_for_item_prefers_current_then_supplier_then_unique_history(self):
        app = SimpleNamespace(
            recent_orders={
                ("AER-", "GH781-4"): [{"vendor": "motion", "qty": 2, "date": "2026-03-10"}]
            }
        )
        item = {"line_code": "AER-", "item_code": "GH781-4", "vendor": "source"}

        self.assertEqual(
            ui_individual.suggested_vendor_for_item(app, item, {"supplier": "gregdist"}),
            ("SOURCE", "current assignment"),
        )
        self.assertEqual(
            ui_individual.suggested_vendor_for_item(
                app,
                {"line_code": "AER-", "item_code": "GH781-4", "vendor": ""},
                {"supplier": "gregdist"},
            ),
            ("GREGDIST", "report supplier"),
        )
        self.assertEqual(
            ui_individual.suggested_vendor_for_item(
                app,
                {"line_code": "AER-", "item_code": "GH781-4", "vendor": ""},
                {},
            ),
            ("MOTION", "recent local order history"),
        )

    def test_populate_assign_item_autofills_supplier_and_prioritizes_choices(self):
        app = SimpleNamespace(
            assign_index=0,
            individual_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 0,
                "qty_suspended": 0,
                "qty_received": 0,
                "order_qty": 1,
                "pack_size": 1,
                "vendor": "",
            }],
            lbl_assign_progress=SimpleNamespace(config=lambda **kwargs: None),
            assign_progress={},
            assign_detail_vars={label: DummyVar() for label in (
                "Line Code:", "Item Code:", "Description:", "Source:", "Qty Sold:", "Qty Suspended:",
                "Qty Received:", "Order Qty:", "Pack Size:", "QOH:", "On PO:", "Min:", "Max:",
                "Sug Min:", "Sug Max:", "YTD Sales:", "12 Mo Sales:", "Supplier:", "Last Receipt:", "Last Sale:"
            )},
            inventory_lookup={("AER-", "GH781-4"): {"supplier": "gregdist", "qoh": 2, "min": 1, "max": 4}},
            on_po_qty={("AER-", "GH781-4"): 0},
            _suggest_min_max=lambda key: (1, 4),
            open_po_lookup={},
            suspended_lookup={},
            suspended_set=set(),
            duplicate_ic_lookup={},
            lbl_po_warning=SimpleNamespace(config=lambda **kwargs: None),
            lbl_susp_warning=SimpleNamespace(config=lambda **kwargs: None),
            lbl_dup_warning=SimpleNamespace(config=lambda **kwargs: None),
            btn_dismiss_dup=SimpleNamespace(pack=lambda *args, **kwargs: None, pack_forget=lambda: None),
            lbl_recent_warning=SimpleNamespace(config=lambda **kwargs: None),
            lbl_vendor_suggestion=SimpleNamespace(config=lambda **kwargs: setattr(app, "_vendor_hint", kwargs.get("text", ""))),
            recent_orders={("AER-", "GH781-4"): [{"vendor": "motion", "qty": 2, "date": "2026-03-10"}]},
            vendor_codes_used=["MOTION", "SOURCE"],
            combo_vendor={"values": ()},
            var_vendor_input=DummyVar(),
        )
        app.combo_vendor = {
            "values": ()
        }
        app.combo_vendor = type("Combo", (), {
            "__setitem__": lambda self, key, value: setattr(app, "_combo_values", value),
            "focus_set": lambda self: setattr(app, "_focused", True),
        })()

        ui_individual.populate_assign_item(app)

        self.assertEqual(app.var_vendor_input.get(), "GREGDIST")
        self.assertIn("report supplier", app._vendor_hint)
        self.assertEqual(app._combo_values[:3], ["GREGDIST", "MOTION", "SOURCE"])
        self.assertTrue(app._focused)

    def test_populate_assign_item_leaves_blank_when_history_is_mixed(self):
        app = SimpleNamespace(
            assign_index=0,
            individual_items=[{
                "line_code": "AER-",
                "item_code": "GH781-4",
                "description": "HOSE",
                "qty_sold": 0,
                "qty_suspended": 0,
                "qty_received": 0,
                "order_qty": 1,
                "pack_size": 1,
                "vendor": "",
            }],
            lbl_assign_progress=SimpleNamespace(config=lambda **kwargs: None),
            assign_progress={},
            assign_detail_vars={label: DummyVar() for label in (
                "Line Code:", "Item Code:", "Description:", "Source:", "Qty Sold:", "Qty Suspended:",
                "Qty Received:", "Order Qty:", "Pack Size:", "QOH:", "On PO:", "Min:", "Max:",
                "Sug Min:", "Sug Max:", "YTD Sales:", "12 Mo Sales:", "Supplier:", "Last Receipt:", "Last Sale:"
            )},
            inventory_lookup={("AER-", "GH781-4"): {"qoh": 2, "min": 1, "max": 4}},
            on_po_qty={("AER-", "GH781-4"): 0},
            _suggest_min_max=lambda key: (1, 4),
            open_po_lookup={},
            suspended_lookup={},
            suspended_set=set(),
            duplicate_ic_lookup={},
            lbl_po_warning=SimpleNamespace(config=lambda **kwargs: None),
            lbl_susp_warning=SimpleNamespace(config=lambda **kwargs: None),
            lbl_dup_warning=SimpleNamespace(config=lambda **kwargs: None),
            btn_dismiss_dup=SimpleNamespace(pack=lambda *args, **kwargs: None, pack_forget=lambda: None),
            lbl_recent_warning=SimpleNamespace(config=lambda **kwargs: None),
            lbl_vendor_suggestion=SimpleNamespace(config=lambda **kwargs: setattr(app, "_vendor_hint", kwargs.get("text", ""))),
            recent_orders={("AER-", "GH781-4"): [
                {"vendor": "motion", "qty": 2, "date": "2026-03-10"},
                {"vendor": "source", "qty": 2, "date": "2026-03-11"},
            ]},
            vendor_codes_used=["MOTION", "SOURCE"],
            combo_vendor={"values": ()},
            var_vendor_input=DummyVar(),
        )
        app.combo_vendor = type("Combo", (), {
            "__setitem__": lambda self, key, value: setattr(app, "_combo_values", value),
            "focus_set": lambda self: None,
        })()

        ui_individual.populate_assign_item(app)

        self.assertEqual(app.var_vendor_input.get(), "")
        self.assertIn("Recent vendor history", app._vendor_hint)
        self.assertEqual(app._combo_values[:2], ["MOTION", "SOURCE"])


if __name__ == "__main__":
    unittest.main()
