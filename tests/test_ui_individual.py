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

    def test_suggested_vendor_for_item_prefers_current_then_receipt_then_supplier_then_unique_history(self):
        app = SimpleNamespace(
            receipt_history_lookup={
                ("AER-", "GH781-4"): {"vendor_candidates": ["source"], "primary_vendor": "source", "vendor_confidence": "high"}
            },
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
            ("SOURCE", "receipt history"),
        )
        self.assertEqual(
            ui_individual.suggested_vendor_for_item(
                SimpleNamespace(receipt_history_lookup={}, recent_orders=app.recent_orders),
                {"line_code": "AER-", "item_code": "GH781-4", "vendor": ""},
                {"supplier": "gregdist"},
            ),
            ("GREGDIST", "report supplier"),
        )
        self.assertEqual(
            ui_individual.suggested_vendor_for_item(
                SimpleNamespace(receipt_history_lookup={}, recent_orders=app.recent_orders),
                {"line_code": "AER-", "item_code": "GH781-4", "vendor": ""},
                {},
            ),
            ("MOTION", "recent local order history"),
        )

    def test_suggested_vendor_for_item_prefers_top_receipt_vendor_when_history_is_mixed(self):
        app = SimpleNamespace(
            receipt_history_lookup={
                ("AER-", "GH781-4"): {"vendor_candidates": ["source", "motion"], "primary_vendor": "source", "vendor_confidence": "medium"}
            },
            recent_orders={},
        )

        result = ui_individual.suggested_vendor_for_item(
            app,
            {"line_code": "AER-", "item_code": "GH781-4", "vendor": ""},
            {"supplier": "gregdist"},
        )

        self.assertEqual(result, ("SOURCE", "receipt history"))

    def test_populate_assign_item_autofills_receipt_vendor_and_prioritizes_choices(self):
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
                "potential_vendor": "GREGDIST",
                "receipt_primary_vendor": "GREGDIST",
                "receipt_vendor_confidence": "high",
                "receipt_count": 3,
                "receipt_sales_balance": "balanced",
                "pack_size_source": "receipt_history",
                "potential_pack_size": 25,
                "potential_pack_confidence": "high",
                "avg_units_per_receipt": 7.5,
                "median_units_per_receipt": 6,
                "avg_days_between_receipts": 9.0,
                "detailed_sales_shape": "steady_repeat",
                "detailed_sales_shape_confidence": "high",
                "suggested_source_label": "Detailed sales fallback",
                "detailed_suggested_min": 3,
                "detailed_suggested_max": 6,
                "detailed_suggestion_compare_label": "Detailed only",
            }],
            lbl_assign_progress=SimpleNamespace(config=lambda **kwargs: None),
            assign_progress={},
            assign_detail_vars={label: DummyVar() for label in (
                "Line Code:", "Item Code:", "Description:", "Source:", "Qty Sold:", "Qty Suspended:",
                "Qty Received:", "Order Qty:", "Pack Size:", "QOH:", "On PO:", "Min:", "Max:",
                "Sug Min:", "Sug Max:", "Sug Source:", "Dtl Sug Min:", "Dtl Sug Max:", "Sug Compare:", "YTD Sales:", "12 Mo Sales:", "Supplier:", "Receipt Vendor:",
                "Potential Vendor:", "Receipt Confidence:", "Receipt Count:", "Receipt vs Sales:", "Pack Source:", "Potential Pack:", "Pack Confidence:", "Avg Units / Receipt:", "Median Units / Receipt:", "Avg Days Between Receipts:", "Demand Shape:", "Shape Confidence:", "Last Receipt:", "Last Sale:"
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
            receipt_history_lookup={("AER-", "GH781-4"): {"vendor_candidates": ["gregdist"], "primary_vendor": "gregdist", "vendor_confidence": "high"}},
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
        self.assertIn("receipt history", app._vendor_hint)
        self.assertEqual(app._combo_values[:3], ["GREGDIST", "MOTION", "SOURCE"])
        self.assertEqual(app.assign_detail_vars["Potential Vendor:"].get(), "GREGDIST")
        self.assertEqual(app.assign_detail_vars["Receipt Vendor:"].get(), "GREGDIST")
        self.assertEqual(app.assign_detail_vars["Receipt Confidence:"].get(), "high")
        self.assertEqual(app.assign_detail_vars["Receipt Count:"].get(), "3")
        self.assertEqual(app.assign_detail_vars["Receipt vs Sales:"].get(), "balanced")
        self.assertEqual(app.assign_detail_vars["Pack Source:"].get(), "Receipt History")
        self.assertEqual(app.assign_detail_vars["Potential Pack:"].get(), "25")
        self.assertEqual(app.assign_detail_vars["Pack Confidence:"].get(), "high")
        self.assertEqual(app.assign_detail_vars["Avg Units / Receipt:"].get(), "7.50")
        self.assertEqual(app.assign_detail_vars["Median Units / Receipt:"].get(), "6.00")
        self.assertEqual(app.assign_detail_vars["Avg Days Between Receipts:"].get(), "9.00")
        self.assertEqual(app.assign_detail_vars["Sug Source:"].get(), "Detailed sales fallback")
        self.assertEqual(app.assign_detail_vars["Dtl Sug Min:"].get(), "3")
        self.assertEqual(app.assign_detail_vars["Dtl Sug Max:"].get(), "6")
        self.assertEqual(app.assign_detail_vars["Sug Compare:"].get(), "Detailed only")
        self.assertEqual(app.assign_detail_vars["Demand Shape:"].get(), "steady_repeat")
        self.assertEqual(app.assign_detail_vars["Shape Confidence:"].get(), "high")
        self.assertTrue(app._focused)

    def test_populate_assign_item_autofills_dominant_high_confidence_receipt_vendor(self):
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
                "receipt_primary_vendor": "MOTION",
                "receipt_vendor_confidence": "high",
            }],
            lbl_assign_progress=SimpleNamespace(config=lambda **kwargs: None),
            assign_progress={},
            assign_detail_vars={label: DummyVar() for label in (
                "Line Code:", "Item Code:", "Description:", "Source:", "Qty Sold:", "Qty Suspended:",
                "Qty Received:", "Order Qty:", "Pack Size:", "QOH:", "On PO:", "Min:", "Max:",
                "Sug Min:", "Sug Max:", "Sug Source:", "Dtl Sug Min:", "Dtl Sug Max:", "Sug Compare:", "YTD Sales:", "12 Mo Sales:", "Supplier:", "Receipt Vendor:",
                "Potential Vendor:", "Receipt Confidence:", "Receipt Count:", "Receipt vs Sales:", "Pack Source:", "Potential Pack:", "Pack Confidence:", "Avg Units / Receipt:", "Median Units / Receipt:", "Avg Days Between Receipts:", "Demand Shape:", "Shape Confidence:", "Last Receipt:", "Last Sale:"
            )},
            inventory_lookup={("AER-", "GH781-4"): {"supplier": "source", "qoh": 2, "min": 1, "max": 4}},
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
            receipt_history_lookup={("AER-", "GH781-4"): {
                "vendor_candidates": ["motion", "source"],
                "primary_vendor": "motion",
                "vendor_confidence": "high",
                "vendor_confidence_reason": "dominant_recent_vendor",
                "primary_vendor_qty_share": 0.83,
                "primary_vendor_receipt_share": 0.67,
            }},            
            recent_orders={},
            vendor_codes_used=["MOTION", "SOURCE"],
            combo_vendor={"values": ()},
            var_vendor_input=DummyVar(),
        )
        app.combo_vendor = type("Combo", (), {
            "__setitem__": lambda self, key, value: setattr(app, "_combo_values", value),
            "focus_set": lambda self: setattr(app, "_focused", True),
        })()

        ui_individual.populate_assign_item(app)

        self.assertEqual(app.var_vendor_input.get(), "MOTION")
        self.assertIn("receipt history", app._vendor_hint)
        self.assertEqual(app._combo_values[:2], ["MOTION", "SOURCE"])
        self.assertEqual(app.assign_detail_vars["Receipt Vendor:"].get(), "MOTION")
        self.assertEqual(app.assign_detail_vars["Receipt Confidence:"].get(), "high")
        self.assertTrue(app._focused)

    def test_populate_assign_item_autofills_top_receipt_vendor_when_history_is_mixed(self):
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
                "receipt_primary_vendor": "MOTION",
                "receipt_vendor_confidence": "medium",
            }],
            lbl_assign_progress=SimpleNamespace(config=lambda **kwargs: None),
            assign_progress={},
            assign_detail_vars={label: DummyVar() for label in (
                "Line Code:", "Item Code:", "Description:", "Source:", "Qty Sold:", "Qty Suspended:",
                "Qty Received:", "Order Qty:", "Pack Size:", "QOH:", "On PO:", "Min:", "Max:",
                "Sug Min:", "Sug Max:", "Sug Source:", "Dtl Sug Min:", "Dtl Sug Max:", "Sug Compare:", "YTD Sales:", "12 Mo Sales:", "Supplier:", "Receipt Vendor:",
                "Potential Vendor:", "Receipt Confidence:", "Receipt Count:", "Receipt vs Sales:", "Pack Source:", "Potential Pack:", "Pack Confidence:", "Avg Units / Receipt:", "Median Units / Receipt:", "Avg Days Between Receipts:", "Demand Shape:", "Shape Confidence:", "Last Receipt:", "Last Sale:"
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
            receipt_history_lookup={("AER-", "GH781-4"): {"vendor_candidates": ["motion", "source"], "primary_vendor": "motion", "vendor_confidence": "medium"}},
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

        self.assertEqual(app.var_vendor_input.get(), "MOTION")
        self.assertIn("receipt history", app._vendor_hint.lower())
        self.assertEqual(app._combo_values[:2], ["MOTION", "SOURCE"])
        self.assertEqual(app.assign_detail_vars["Receipt Vendor:"].get(), "MOTION")
        self.assertEqual(app.assign_detail_vars["Receipt Confidence:"].get(), "medium")


if __name__ == "__main__":
    unittest.main()
