import json
import os
import tempfile
import unittest

import item_notes_flow


class LoadNotesTests(unittest.TestCase):
    def test_load_missing_file(self):
        self.assertEqual(item_notes_flow.load_notes("/nonexistent/path.json"), {})

    def test_load_valid_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"010-:ITEM1": "reorder weekly", "GDY-:BELT5": "check price"}, f)
            path = f.name
        try:
            notes = item_notes_flow.load_notes(path)
            self.assertEqual(notes, {"010-:ITEM1": "reorder weekly", "GDY-:BELT5": "check price"})
        finally:
            os.unlink(path)

    def test_load_corrupt_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not json")
            path = f.name
        try:
            self.assertEqual(item_notes_flow.load_notes(path), {})
        finally:
            os.unlink(path)

    def test_load_strips_empty_values(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"A": "keep", "B": "", "C": None}, f)
            path = f.name
        try:
            notes = item_notes_flow.load_notes(path)
            self.assertEqual(notes, {"A": "keep"})
        finally:
            os.unlink(path)


class SaveNotesTests(unittest.TestCase):
    def test_save_and_reload(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            path = f.name
        try:
            notes = {"010-:A": "note one", "GDY-:B": "note two"}
            result = item_notes_flow.save_notes(path, notes)
            self.assertEqual(result, notes)
            reloaded = item_notes_flow.load_notes(path)
            self.assertEqual(reloaded, notes)
        finally:
            os.unlink(path)

    def test_save_strips_empty(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            path = f.name
        try:
            result = item_notes_flow.save_notes(path, {"A": "keep", "B": "", "C": "  "})
            self.assertEqual(result, {"A": "keep"})
        finally:
            os.unlink(path)


class ApplyNotesTests(unittest.TestCase):
    def test_apply_notes_to_items(self):
        items = [
            {"line_code": "010-", "item_code": "ITEM1"},
            {"line_code": "GDY-", "item_code": "BELT5"},
            {"line_code": "010-", "item_code": "ITEM2"},
        ]
        notes = {"010-:ITEM1": "reorder weekly", "010-:ITEM2": "discontinue soon"}
        item_notes_flow.apply_notes_to_items(items, notes)
        self.assertEqual(items[0]["notes"], "reorder weekly")
        self.assertNotIn("notes", items[1])
        self.assertEqual(items[2]["notes"], "discontinue soon")

    def test_apply_empty_notes(self):
        items = [{"line_code": "A", "item_code": "B"}]
        item_notes_flow.apply_notes_to_items(items, {})
        self.assertNotIn("notes", items[0])


class ClearNotesTests(unittest.TestCase):
    def test_clear_notes_for_keys(self):
        notes = {"010-:A": "one", "010-:B": "two", "GDY-:C": "three"}
        removed = item_notes_flow.clear_notes_for_keys(notes, [("010-", "A"), ("GDY-", "C")])
        self.assertEqual(removed, 2)
        self.assertEqual(notes, {"010-:B": "two"})

    def test_clear_nonexistent_key(self):
        notes = {"010-:A": "one"}
        removed = item_notes_flow.clear_notes_for_keys(notes, [("X", "Y")])
        self.assertEqual(removed, 0)
        self.assertEqual(notes, {"010-:A": "one"})


if __name__ == "__main__":
    unittest.main()
