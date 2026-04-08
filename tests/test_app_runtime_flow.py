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

    def test_prompt_for_update_takes_self_update_path_when_exe_asset_present(self):
        """When can_self_update() is True and an exe asset exists, the download
        dialog should be shown rather than the browser fallback."""
        fake_app = SimpleNamespace()
        release = {
            "tag_name": "v0.5.0",
            "name": "PO Builder 0.5.0",
            "published_at": "2026-04-01T00:00:00Z",
            "html_url": "https://example.com/release",
            "assets": [
                {"name": "POBuilder.exe", "browser_download_url": "https://example.com/POBuilder.exe"},
            ],
        }

        download_offered = []
        with patch("app_runtime_flow.update_flow.can_self_update", return_value=True), \
             patch("app_runtime_flow._prompt_for_update_with_download",
                   side_effect=lambda *a, **kw: download_offered.append(kw.get("exe_url"))), \
             patch("app_runtime_flow.messagebox.askyesno") as mocked_browser_dialog:
            app_runtime_flow.prompt_for_update(
                fake_app,
                release,
                app_version="0.4.1",
                releases_page_url="https://example.com/latest",
            )

        self.assertEqual(download_offered, ["https://example.com/POBuilder.exe"])
        mocked_browser_dialog.assert_not_called()

    def test_prompt_for_update_falls_back_to_browser_when_no_exe_asset(self):
        """When can_self_update() is True but the release has no exe asset,
        the browser fallback dialog should be shown."""
        fake_app = SimpleNamespace()
        release = {
            "tag_name": "v0.5.0",
            "name": "PO Builder 0.5.0",
            "published_at": "2026-04-01T00:00:00Z",
            "html_url": "https://example.com/release",
            "assets": [],
        }

        with patch("app_runtime_flow.update_flow.can_self_update", return_value=True), \
             patch("app_runtime_flow.messagebox.askyesno", return_value=False) as mocked_browser_dialog:
            app_runtime_flow.prompt_for_update(
                fake_app,
                release,
                app_version="0.4.1",
                releases_page_url="https://example.com/latest",
            )

        mocked_browser_dialog.assert_called_once()


class CheckForUpdatesNowTests(unittest.TestCase):
    _URL_ERRORS = (OSError, json.JSONDecodeError)
    _RELEASES_URL = "https://example.com/latest"

    def _run(self, fetch_fn, app_version="0.4.1", is_newer=None):
        if is_newer is None:
            is_newer = po_builder.is_newer_version
        fake_app = SimpleNamespace(
            _prompt_for_update=lambda r: None,
        )
        shown = []
        with patch("app_runtime_flow.messagebox.showinfo",
                   side_effect=lambda t, m: shown.append(("info", t, m))), \
             patch("app_runtime_flow.messagebox.askyesno",
                   side_effect=lambda t, m: shown.append(("yesno", t, m)) or False):
            app_runtime_flow.check_for_updates_now(
                fake_app,
                app_version=app_version,
                fetch_latest_release=fetch_fn,
                is_newer_version=is_newer,
                releases_page_url=self._RELEASES_URL,
                url_error_types=self._URL_ERRORS,
            )
        return fake_app, shown

    def test_network_error_shows_info(self):
        _, shown = self._run(lambda: (_ for _ in ()).throw(OSError("no route")))
        self.assertEqual(len(shown), 1)
        self.assertIn("Could not reach", shown[0][2])

    def test_up_to_date_shows_info(self):
        _, shown = self._run(lambda: {"tag_name": "v0.4.1", "assets": []})
        self.assertEqual(len(shown), 1)
        self.assertIn("up to date", shown[0][2])

    def test_update_with_exe_asset_and_frozen_delegates_to_prompt(self):
        prompted = []
        fake_app = SimpleNamespace(_prompt_for_update=lambda r: prompted.append(r))
        release = {
            "tag_name": "v0.5.0", "name": "PO Builder 0.5.0",
            "assets": [{"name": "POBuilder.exe",
                        "browser_download_url": "https://example.com/POBuilder.exe"}],
        }
        with patch("app_runtime_flow.update_flow.can_self_update", return_value=True), \
             patch("app_runtime_flow.messagebox.showinfo"), \
             patch("app_runtime_flow.messagebox.askyesno", return_value=False):
            app_runtime_flow.check_for_updates_now(
                fake_app,
                app_version="0.4.1",
                fetch_latest_release=lambda: release,
                is_newer_version=po_builder.is_newer_version,
                releases_page_url=self._RELEASES_URL,
                url_error_types=self._URL_ERRORS,
            )
        self.assertEqual(len(prompted), 1)

    def test_update_no_exe_asset_explains_missing_asset(self):
        release = {"tag_name": "v0.5.0", "name": "PO Builder 0.5.0",
                   "html_url": "https://example.com/rel", "assets": []}
        with patch("app_runtime_flow.update_flow.can_self_update", return_value=True):
            _, shown = self._run(lambda: release)
        self.assertEqual(len(shown), 1)
        kind, _, msg = shown[0]
        self.assertEqual(kind, "yesno")
        self.assertIn("No release assets", msg)

    def test_update_not_frozen_explains_source_mode(self):
        release = {
            "tag_name": "v0.5.0", "name": "PO Builder 0.5.0",
            "html_url": "https://example.com/rel",
            "assets": [{"name": "POBuilder.exe",
                        "browser_download_url": "https://example.com/POBuilder.exe"}],
        }
        with patch("app_runtime_flow.update_flow.can_self_update", return_value=False):
            _, shown = self._run(lambda: release)
        self.assertEqual(len(shown), 1)
        kind, _, msg = shown[0]
        self.assertEqual(kind, "yesno")
        self.assertIn("packaged .exe", msg)

    def test_asset_with_wrong_extension_explains_naming(self):
        release = {
            "tag_name": "v0.5.0", "name": "PO Builder 0.5.0",
            "html_url": "https://example.com/rel",
            "assets": [{"name": "POBuilder.zip",
                        "browser_download_url": "https://example.com/POBuilder.zip"}],
        }
        with patch("app_runtime_flow.update_flow.can_self_update", return_value=True):
            _, shown = self._run(lambda: release)
        kind, _, msg = shown[0]
        self.assertIn("none end in .exe", msg)


if __name__ == "__main__":
    unittest.main()
