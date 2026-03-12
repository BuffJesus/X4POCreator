import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import loading_flow


class LoadingFlowTests(unittest.TestCase):
    def test_autosize_dialog_clamps_to_screen_and_sets_minimum(self):
        events = []

        class Dialog:
            def update_idletasks(self):
                events.append("update")
            def winfo_screenwidth(self):
                return 1000
            def winfo_screenheight(self):
                return 800
            def winfo_reqwidth(self):
                return 1200
            def winfo_reqheight(self):
                return 900
            def geometry(self, value):
                events.append(("geometry", value))
            def minsize(self, width, height):
                events.append(("minsize", width, height))

        loading_flow.autosize_dialog(Dialog(), min_w=420, min_h=280)

        self.assertEqual(events[0], "update")
        self.assertIn(("geometry", "900x720+50+26"), events)
        self.assertIn(("minsize", 420, 280), events)

    def test_hide_loading_cancels_animation_and_destroys_overlay(self):
        events = []

        class Overlay:
            def destroy(self):
                events.append("destroy")

        fake_app = SimpleNamespace(
            _loading_after_id="after-1",
            _loading_overlay=Overlay(),
            root=SimpleNamespace(after_cancel=lambda after_id: events.append(("cancel", after_id))),
            _stop_loading_audio=lambda: events.append("audio"),
        )

        loading_flow.hide_loading(fake_app)

        self.assertEqual(fake_app._loading_after_id, None)
        self.assertEqual(fake_app._loading_overlay, None)
        self.assertEqual(events, [("cancel", "after-1"), "audio", "destroy"])

    def test_run_with_loading_returns_result_and_hides_overlay(self):
        events = []
        fake_app = SimpleNamespace(
            _show_loading=lambda text: events.append(("show", text)),
            _hide_loading=lambda: events.append(("hide", None)),
            root=SimpleNamespace(update=lambda: events.append(("update", None)), after=lambda delay: events.append(("after", delay))),
        )

        result = loading_flow.run_with_loading(fake_app, "Working", lambda a, b: a + b, 2, 3, min_seconds=0)

        self.assertEqual(result, 5)
        self.assertIn(("show", "Working"), events)
        self.assertEqual(events[-1], ("hide", None))

    def test_run_with_loading_reraises_worker_error(self):
        events = []
        fake_app = SimpleNamespace(
            _show_loading=lambda text: events.append(("show", text)),
            _hide_loading=lambda: events.append(("hide", None)),
            root=SimpleNamespace(update=lambda: events.append(("update", None)), after=lambda delay: events.append(("after", delay))),
        )

        with self.assertRaisesRegex(RuntimeError, "boom"):
            loading_flow.run_with_loading(fake_app, "Working", lambda: (_ for _ in ()).throw(RuntimeError("boom")), min_seconds=0)

        self.assertEqual(events[-1], ("hide", None))


if __name__ == "__main__":
    unittest.main()
