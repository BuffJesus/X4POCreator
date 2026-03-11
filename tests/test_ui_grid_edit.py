import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui_grid_edit import TreeGridEditor


class FakeTree:
    def __init__(self):
        self._selection = ("1", "3")
        self.focused = ""

    def selection(self):
        return self._selection

    def selection_set(self, rows):
        self._selection = tuple(rows)

    def focus(self, row_id):
        self.focused = row_id

    def get_children(self, _parent=""):
        return ["1", "2", "3"]


class TreeGridEditorTests(unittest.TestCase):
    def test_target_row_ids_uses_selected_rows_for_multi_fill(self):
        tree = FakeTree()
        editor = TreeGridEditor(None, tree, ("pack_size",), None, None, None, None)

        self.assertEqual(editor.target_row_ids("1"), ["1", "3"])
        self.assertEqual(editor.target_row_ids("2"), ["2"])

    def test_apply_to_targets_updates_all_selected_rows(self):
        tree = FakeTree()
        applied = []
        refreshed = []
        editor = TreeGridEditor(
            None,
            tree,
            ("pack_size",),
            None,
            None,
            lambda row_id, col_name, raw: applied.append((row_id, col_name, raw)),
            lambda row_id: refreshed.append(row_id),
        )

        editor.apply_to_targets("1", "pack_size", "500")

        self.assertEqual(
            applied,
            [("1", "pack_size", "500"), ("3", "pack_size", "500")],
        )
        self.assertEqual(refreshed, ["1", "3"])
        self.assertEqual(tree.focused, "1")


if __name__ == "__main__":
    unittest.main()
