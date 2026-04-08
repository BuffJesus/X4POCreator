import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui_ignored_items import _filter_keys, _parse_ignore_key
import session_state_flow


class TestParseIgnoreKey(unittest.TestCase):
    def test_splits_on_first_colon(self):
        self.assertEqual(_parse_ignore_key("AER-:GH781-4"), ("AER-", "GH781-4"))

    def test_no_colon_returns_empty_line_code(self):
        self.assertEqual(_parse_ignore_key("GH781-4"), ("", "GH781-4"))

    def test_multiple_colons_splits_on_first(self):
        self.assertEqual(_parse_ignore_key("A:B:C"), ("A", "B:C"))

    def test_empty_string(self):
        self.assertEqual(_parse_ignore_key(""), ("", ""))

    def test_colon_at_start(self):
        self.assertEqual(_parse_ignore_key(":ITEM"), ("", "ITEM"))

    def test_colon_at_end(self):
        self.assertEqual(_parse_ignore_key("LINE:"), ("LINE", ""))


class TestFilterKeys(unittest.TestCase):
    _KEYS = ["AER-:GH781-4", "AER-:XY999", "MOT-:GH781-4", "MOT-:WIDGET"]

    def test_empty_filter_returns_all(self):
        self.assertEqual(_filter_keys(self._KEYS, ""), self._KEYS)

    def test_whitespace_only_filter_returns_all(self):
        self.assertEqual(_filter_keys(self._KEYS, "   "), self._KEYS)

    def test_filter_by_item_code(self):
        result = _filter_keys(self._KEYS, "gh781")
        self.assertEqual(result, ["AER-:GH781-4", "MOT-:GH781-4"])

    def test_filter_by_line_code(self):
        result = _filter_keys(self._KEYS, "aer-")
        self.assertEqual(result, ["AER-:GH781-4", "AER-:XY999"])

    def test_filter_case_insensitive(self):
        result = _filter_keys(self._KEYS, "WIDGET")
        self.assertEqual(result, ["MOT-:WIDGET"])

    def test_filter_no_match(self):
        self.assertEqual(_filter_keys(self._KEYS, "ZZZZZ"), [])

    def test_empty_keys(self):
        self.assertEqual(_filter_keys([], "gh781"), [])


class TestUnIgnoreItemKeys(unittest.TestCase):
    def _make_app(self, ignored=None):
        saved = []
        app = SimpleNamespace(
            ignored_item_keys=set(ignored or []),
            _loaded_ignored_item_keys=set(ignored or []),
            _save_ignored_item_keys=lambda: saved.append(1),
        )
        app._saved = saved
        return app

    def test_removes_keys_from_ignored_set(self):
        app = self._make_app({"AER-:GH781-4", "MOT-:XY999"})
        count = session_state_flow.un_ignore_item_keys(app, {"AER-:GH781-4"})
        self.assertEqual(count, 1)
        self.assertNotIn("AER-:GH781-4", app.ignored_item_keys)
        self.assertIn("MOT-:XY999", app.ignored_item_keys)

    def test_returns_zero_for_empty_keys(self):
        app = self._make_app({"AER-:GH781-4"})
        count = session_state_flow.un_ignore_item_keys(app, set())
        self.assertEqual(count, 0)
        self.assertIn("AER-:GH781-4", app.ignored_item_keys)

    def test_returns_zero_when_key_not_in_ignored(self):
        app = self._make_app({"AER-:GH781-4"})
        count = session_state_flow.un_ignore_item_keys(app, {"MOT-:NOPE"})
        self.assertEqual(count, 0)

    def test_saves_after_removal(self):
        app = self._make_app({"AER-:GH781-4"})
        session_state_flow.un_ignore_item_keys(app, {"AER-:GH781-4"})
        self.assertEqual(len(app._saved), 1)

    def test_no_save_when_nothing_removed(self):
        app = self._make_app({"AER-:GH781-4"})
        session_state_flow.un_ignore_item_keys(app, {"NOT-:THERE"})
        self.assertEqual(len(app._saved), 0)

    def test_removes_multiple_keys(self):
        app = self._make_app({"A:1", "B:2", "C:3"})
        count = session_state_flow.un_ignore_item_keys(app, {"A:1", "C:3"})
        self.assertEqual(count, 2)
        self.assertEqual(app.ignored_item_keys, {"B:2"})

    def test_strips_whitespace_from_keys(self):
        app = self._make_app({"AER-:GH781-4"})
        count = session_state_flow.un_ignore_item_keys(app, {" AER-:GH781-4 "})
        self.assertEqual(count, 1)
        self.assertNotIn("AER-:GH781-4", app.ignored_item_keys)

    def test_ignores_empty_string_keys(self):
        app = self._make_app({"AER-:GH781-4"})
        count = session_state_flow.un_ignore_item_keys(app, {"", "  "})
        self.assertEqual(count, 0)
