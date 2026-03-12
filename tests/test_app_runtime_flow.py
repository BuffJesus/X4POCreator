import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app_runtime_flow
import po_builder


class AppRuntimeFlowTests(unittest.TestCase):
    def test_save_app_settings_logs_failure(self):
        fake_app = SimpleNamespace(app_settings={"a": 1})

        with patch("app_runtime_flow.storage.save_json_file", side_effect=OSError("nope")), \
             patch("app_runtime_flow.messagebox.showerror") as mocked_error:
            write_events = []
            app_runtime_flow.save_app_settings(
                fake_app,
                str(ROOT / "settings.json"),
                lambda event, **kwargs: write_events.append((event, kwargs)),
            )

        self.assertEqual(write_events[0][0], "app_settings.save_failed")
        mocked_error.assert_not_called()

    def test_check_for_updates_worker_schedules_prompt_for_newer_release(self):
        scheduled = []
        release = {"tag_name": "v0.2.0"}
        fake_app = SimpleNamespace(
            root=SimpleNamespace(after=lambda delay, callback: scheduled.append((delay, callback))),
            _prompt_for_update=lambda rel: scheduled.append(("prompt", rel)),
        )

        app_runtime_flow.check_for_updates_worker(
            fake_app,
            app_version="0.1.7",
            fetch_latest_release=lambda: release,
            is_newer_version=po_builder.is_newer_version,
            url_error_types=(OSError, json.JSONDecodeError),
        )

        self.assertEqual(scheduled[0][0], 0)
        scheduled[0][1]()
        self.assertEqual(scheduled[1], ("prompt", release))

    def test_prompt_for_update_shows_fallback_page_when_browser_open_fails(self):
        fake_app = SimpleNamespace()
        release = {
            "tag_name": "v0.2.0",
            "name": "PO Builder 0.2.0",
            "published_at": "2026-03-12T12:00:00Z",
            "html_url": "https://example.com/release",
        }

        with patch("app_runtime_flow.messagebox.askyesno", return_value=True), \
             patch("app_runtime_flow.webbrowser.open", side_effect=RuntimeError("blocked")), \
             patch("app_runtime_flow.messagebox.showinfo") as mocked_info:
            app_runtime_flow.prompt_for_update(
                fake_app,
                release,
                app_version="0.1.7",
                releases_page_url="https://example.com/latest",
            )

        mocked_info.assert_called_once()
        self.assertIn("https://example.com/release", mocked_info.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
