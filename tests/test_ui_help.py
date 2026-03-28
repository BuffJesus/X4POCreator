import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_help


class UIHelpTests(unittest.TestCase):
    def test_overview_help_documents_exception_first_export_recommended_workflow(self):
        overview = next(section for section in ui_help.HELP_SECTIONS if section[0] == "Overview")
        body = overview[2]

        self.assertIn("Review exceptions first", body)
        self.assertIn("Export Recommended", body)
        self.assertIn("exception-first screen", body)

    def test_review_and_export_help_documents_default_review_fallback_and_recommended_export(self):
        section = next(section for section in ui_help.HELP_SECTIONS if section[0] == "Review And Export")
        body = section[2]

        self.assertIn("Exceptions Only", body)
        self.assertIn("falls back to All Items", body)
        self.assertIn("Export Recommended is the normal path", body)

    def test_shipping_help_documents_urgent_overrides_as_review_first(self):
        section = next(section for section in ui_help.HELP_SECTIONS if section[0] == "Shipping And Release")
        body = section[2]

        self.assertIn("urgent overrides", body.lower())
        self.assertIn("review-first exceptions", body)


if __name__ == "__main__":
    unittest.main()
