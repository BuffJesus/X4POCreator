"""
Self-update helpers for the POBuilder packaged executable.

These functions implement the download-and-replace path that lets the user
install a new release without visiting the browser.  The flow is:

  1. `find_exe_asset(release)` — locate the .exe download URL in a GitHub
     release payload.
  2. `download_update(url, staging_path, ...)` — stream the file to a staging
     location next to the current executable.
  3. `write_updater_script(staging_path, current_exe)` — write a .bat file
     that waits for the app to exit, moves the staged exe into place, and
     relaunches.
  4. `launch_updater_and_exit(app, updater_script_path)` — start the updater
     detached and ask the app to close.

Only works when running as a frozen PyInstaller bundle on Windows.
`can_self_update()` returns False in all other cases so callers can skip the
automatic path and fall back to the browser.
"""

import os
import sys
import subprocess
import tempfile
import urllib.request
import urllib.error


def can_self_update():
    """Return True when automatic download-and-replace is safe to attempt."""
    return bool(getattr(sys, "frozen", False) and os.name == "nt")


def find_exe_asset(release):
    """
    Return the browser_download_url of the first .exe asset in *release*, or
    None when no such asset is found.

    *release* is the dict returned by the GitHub releases API.
    """
    assets = release.get("assets") or []
    for asset in assets:
        name = str(asset.get("name", "") or "").lower()
        url = str(asset.get("browser_download_url", "") or "").strip()
        if name.endswith(".exe") and url:
            return url
    return None


def staging_path_for(current_exe):
    """
    Return the path where the downloaded exe should be staged.

    The staging file sits next to the current executable so that the updater
    batch script can move it into place without crossing drive boundaries.
    """
    dirname = os.path.dirname(current_exe)
    basename = os.path.splitext(os.path.basename(current_exe))[0]
    return os.path.join(dirname, f"{basename}_pending_update.exe")


def download_update(url, staging_path, *, progress_callback=None, chunk_size=65536):
    """
    Download *url* to *staging_path*.

    *progress_callback* is called with (bytes_downloaded, total_bytes_or_None)
    after each chunk so the caller can update a progress indicator.

    Returns True on success.  Raises on network or I/O error.  Any partially
    downloaded file is deleted on failure.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "POBuilder-self-update/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_length = resp.headers.get("Content-Length")
            total = int(content_length) if content_length else None
            downloaded = 0
            with open(staging_path, "wb") as out:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        try:
                            progress_callback(downloaded, total)
                        except Exception:
                            pass
    except Exception:
        try:
            if os.path.exists(staging_path):
                os.remove(staging_path)
        except OSError:
            pass
        raise
    return True


def write_updater_script(staging_path, current_exe):
    """
    Write a Windows batch file that replaces *current_exe* with *staging_path*
    after the main process exits, then relaunches the new executable.

    Returns the path to the written .bat file.
    """
    script_dir = os.path.dirname(current_exe)
    script_path = os.path.join(script_dir, "_pobuilder_updater.bat")

    staging_escaped = staging_path.replace('"', '""')
    current_escaped = current_exe.replace('"', '""')

    script = (
        "@echo off\n"
        "setlocal\n"
        "\n"
        "rem Wait for POBuilder.exe to release the file lock, then swap in the update.\n"
        "set MAX_RETRIES=20\n"
        "set RETRY=0\n"
        "\n"
        ":retry\n"
        "if %RETRY% geq %MAX_RETRIES% goto failed\n"
        "set /a RETRY=%RETRY%+1\n"
        "ping -n 2 127.0.0.1 >nul\n"
        "\n"
        f'move /y "{staging_escaped}" "{current_escaped}" >nul 2>&1\n'
        "if errorlevel 1 goto retry\n"
        "\n"
        ":success\n"
        f'start "" "{current_escaped}"\n'
        'del "%~f0" >nul 2>&1\n'
        "goto end\n"
        "\n"
        ":failed\n"
        "echo.\n"
        "echo Update could not replace the executable.\n"
        "echo Please close all instances of POBuilder and manually replace:\n"
        "echo.\n"
        f'echo   Staged update : "{staging_escaped}"\n'
        f'echo   Replace target: "{current_escaped}"\n'
        "echo.\n"
        "pause\n"
        "\n"
        ":end\n"
        "endlocal\n"
    )

    with open(script_path, "w", encoding="ascii", errors="replace") as f:
        f.write(script)
    return script_path


def launch_updater_and_exit(app, updater_script_path):
    """
    Launch the updater batch script as a detached process, then ask *app* to
    close cleanly.

    *app* is expected to have a `root` attribute (tkinter root window) or a
    `_on_close` / `destroy` callable.
    """
    subprocess.Popen(
        ["cmd.exe", "/c", updater_script_path],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    close_fn = getattr(app, "close", None) or getattr(app, "_on_close", None) or getattr(app, "destroy", None)
    if callable(close_fn):
        try:
            close_fn()
        except Exception:
            pass


def cleanup_staging(staging_path):
    """Remove a staged update file if it exists (called on cancellation or error)."""
    try:
        if staging_path and os.path.exists(staging_path):
            os.remove(staging_path)
    except OSError:
        pass
