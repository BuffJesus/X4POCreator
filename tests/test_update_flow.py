import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import update_flow


class FindExeAssetTests(unittest.TestCase):
    def test_returns_url_for_exe_asset(self):
        release = {
            "assets": [
                {"name": "POBuilder.exe", "browser_download_url": "https://example.com/POBuilder.exe"},
                {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
            ]
        }
        self.assertEqual(update_flow.find_exe_asset(release), "https://example.com/POBuilder.exe")

    def test_returns_none_when_no_exe_asset(self):
        release = {
            "assets": [
                {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
            ]
        }
        self.assertIsNone(update_flow.find_exe_asset(release))

    def test_returns_none_for_empty_assets(self):
        self.assertIsNone(update_flow.find_exe_asset({}))
        self.assertIsNone(update_flow.find_exe_asset({"assets": []}))

    def test_skips_asset_with_empty_url(self):
        release = {
            "assets": [
                {"name": "POBuilder.exe", "browser_download_url": ""},
            ]
        }
        self.assertIsNone(update_flow.find_exe_asset(release))


class StagingPathTests(unittest.TestCase):
    def test_staging_path_sits_next_to_exe(self):
        path = update_flow.staging_path_for("C:\\foo\\POBuilder.exe")
        self.assertEqual(os.path.dirname(path), "C:\\foo")
        self.assertTrue(os.path.basename(path).endswith(".exe"))
        self.assertNotEqual(os.path.basename(path), "POBuilder.exe")

    def test_staging_path_contains_pending_update(self):
        path = update_flow.staging_path_for("/app/POBuilder.exe")
        self.assertIn("pending_update", os.path.basename(path))


class DownloadUpdateTests(unittest.TestCase):
    def test_downloads_content_to_file(self):
        fake_content = b"fake exe content"

        class FakeResponse:
            headers = {"Content-Length": str(len(fake_content))}

            def read(self, size):
                if self._remaining:
                    chunk = self._remaining[:size]
                    self._remaining = self._remaining[size:]
                    return chunk
                return b""

            def __enter__(self):
                self._remaining = fake_content
                return self

            def __exit__(self, *_):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            staging = os.path.join(tmp, "update.exe")
            progress_calls = []

            with patch("urllib.request.urlopen", return_value=FakeResponse()):
                result = update_flow.download_update(
                    "https://example.com/POBuilder.exe",
                    staging,
                    progress_callback=lambda dl, total: progress_calls.append((dl, total)),
                )

            self.assertTrue(result)
            self.assertEqual(Path(staging).read_bytes(), fake_content)
            self.assertTrue(len(progress_calls) > 0)

    def test_cleans_up_staging_file_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            staging = os.path.join(tmp, "update.exe")

            with patch("urllib.request.urlopen", side_effect=OSError("network error")):
                with self.assertRaises(OSError):
                    update_flow.download_update("https://example.com/POBuilder.exe", staging)

            self.assertFalse(os.path.exists(staging))


class WriteUpdaterScriptTests(unittest.TestCase):
    def test_script_is_written_and_contains_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            current_exe = os.path.join(tmp, "POBuilder.exe")
            staging = os.path.join(tmp, "POBuilder_pending_update.exe")
            script_path = update_flow.write_updater_script(staging, current_exe)

            self.assertTrue(os.path.exists(script_path))
            content = Path(script_path).read_text(encoding="ascii", errors="replace")
            self.assertIn("move /y", content)
            self.assertIn(staging, content)
            self.assertIn(current_exe, content)
            self.assertIn("retry", content)
            self.assertIn("failed", content)

    def test_script_contains_relaunch_and_self_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            current_exe = os.path.join(tmp, "POBuilder.exe")
            staging = os.path.join(tmp, "POBuilder_pending_update.exe")
            script_path = update_flow.write_updater_script(staging, current_exe)
            content = Path(script_path).read_text(encoding="ascii", errors="replace")
            self.assertIn("start", content)
            self.assertIn('del "%~f0"', content)


class CleanupStagingTests(unittest.TestCase):
    def test_removes_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            staging = os.path.join(tmp, "pending.exe")
            Path(staging).write_bytes(b"data")
            update_flow.cleanup_staging(staging)
            self.assertFalse(os.path.exists(staging))

    def test_does_not_raise_when_file_missing(self):
        update_flow.cleanup_staging("/nonexistent/path/update.exe")

    def test_does_not_raise_when_path_is_none(self):
        update_flow.cleanup_staging(None)


if __name__ == "__main__":
    unittest.main()
