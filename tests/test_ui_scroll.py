import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_scroll


class FakeCanvas:
    def __init__(self, width=1234, bbox=(0, 0, 1234, 567)):
        self._width = width
        self._bbox = bbox
        self.itemconfigure_calls = []
        self.coords_calls = []
        self.configure_calls = []

    def winfo_width(self):
        return self._width

    def itemconfigure(self, item, **kwargs):
        self.itemconfigure_calls.append((item, kwargs))

    def coords(self, item, x, y):
        self.coords_calls.append((item, x, y))

    def bbox(self, tag):
        return self._bbox

    def configure(self, **kwargs):
        self.configure_calls.append(kwargs)


class FakeScrollable:
    def __init__(self, first, last):
        self._first = first
        self._last = last

    def yview(self):
        return (self._first, self._last)


class UiScrollTests(unittest.TestCase):
    def test_sync_canvas_window_sets_width_origin_and_scrollregion(self):
        canvas = FakeCanvas()

        ui_scroll.sync_canvas_window(canvas, "content_window")

        self.assertEqual(canvas.itemconfigure_calls, [("content_window", {"width": 1234})])
        self.assertEqual(canvas.coords_calls, [("content_window", 0, 0)])
        self.assertEqual(canvas.configure_calls, [{"scrollregion": (0, 0, 1234, 567)}])

    def test_sync_canvas_window_skips_width_update_until_canvas_is_sized(self):
        canvas = FakeCanvas(width=1, bbox=None)

        ui_scroll.sync_canvas_window(canvas, "content_window")

        self.assertEqual(canvas.itemconfigure_calls, [])
        self.assertEqual(canvas.coords_calls, [("content_window", 0, 0)])
        self.assertEqual(canvas.configure_calls, [])

    def test_can_scroll_vertically_false_when_content_fits(self):
        self.assertFalse(ui_scroll.can_scroll_vertically(FakeScrollable(0.0, 1.0)))

    def test_can_scroll_vertically_true_when_content_overflows(self):
        self.assertTrue(ui_scroll.can_scroll_vertically(FakeScrollable(0.0, 0.72)))


if __name__ == "__main__":
    unittest.main()
