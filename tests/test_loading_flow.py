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

    def test_ensure_corner_loading_gif_places_label_on_notebook(self):
        events = []

        class Label:
            def place(self, **kwargs):
                events.append(("place", kwargs))
            def lift(self):
                events.append("lift")

        fake_app = SimpleNamespace(
            notebook="notebook",
            _corner_loading_label=None,
            _corner_loading_frames=["frame-1"],
            _corner_loading_frame_idx=99,
        )

        label = loading_flow.ensure_corner_loading_gif(
            fake_app,
            lambda parent: events.append(("factory", parent)) or Label(),
        )

        self.assertIsNotNone(label)
        self.assertEqual(fake_app._corner_loading_label, label)
        self.assertEqual(fake_app._corner_loading_frame_idx, 0)
        self.assertIn(("factory", "notebook"), events)
        self.assertIn(("place", {"relx": 1.0, "x": -12, "y": 6, "anchor": "ne"}), events)
        self.assertIn("lift", events)

    def test_animate_corner_loading_updates_label_and_schedules_next_frame(self):
        events = []

        class Label:
            def configure(self, **kwargs):
                events.append(("configure", kwargs))

        fake_app = SimpleNamespace(
            _corner_loading_label=Label(),
            _corner_loading_frames=["frame-1", "frame-2"],
            _corner_loading_frame_idx=0,
            _corner_loading_after_id=None,
            _animate_corner_loading=lambda: None,
            root=SimpleNamespace(after=lambda delay, callback: events.append(("after", delay, callback)) or "after-2"),
        )

        loading_flow.animate_corner_loading(fake_app)

        self.assertEqual(events[0], ("configure", {"image": "frame-1"}))
        self.assertEqual(fake_app._corner_loading_frame_idx, 1)
        self.assertEqual(fake_app._corner_loading_after_id, "after-2")

    def test_animate_corner_loading_stops_cleanly_when_label_errors(self):
        class BrokenLabel:
            def configure(self, **kwargs):
                raise RuntimeError("gone")

        fake_app = SimpleNamespace(
            _corner_loading_label=BrokenLabel(),
            _corner_loading_frames=["frame-1"],
            _corner_loading_frame_idx=0,
            _corner_loading_after_id="after-1",
            _animate_corner_loading=lambda: None,
            root=SimpleNamespace(after=lambda delay, callback: "after-2"),
        )

        loading_flow.animate_corner_loading(fake_app)

        self.assertIsNone(fake_app._corner_loading_after_id)

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
