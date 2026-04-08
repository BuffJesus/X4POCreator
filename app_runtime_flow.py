import os
import sys
import threading
import webbrowser
from tkinter import messagebox

import storage
import update_flow


def save_app_settings(app, app_settings_file, write_debug):
    try:
        storage.save_json_file(app_settings_file, app.app_settings)
    except Exception as exc:
        write_debug("app_settings.save_failed", error=str(exc), path=app_settings_file)


def open_active_data_folder(app):
    try:
        if os.name == "nt":
            os.startfile(app.data_dir)
        else:
            webbrowser.open(f"file://{app.data_dir}")
    except Exception as exc:
        messagebox.showerror("Open Data Folder", f"Could not open the active data folder:\n{exc}")


def set_update_check_enabled(app):
    if hasattr(app, "var_check_updates"):
        app.update_check_enabled = bool(app.var_check_updates.get())
    else:
        app.update_check_enabled = True
    app.app_settings["check_for_updates_on_startup"] = app.update_check_enabled
    app._save_app_settings()


def start_update_check(app, app_version, is_release_version, thread_factory):
    if not app.update_check_enabled or not is_release_version(app_version):
        return
    worker = thread_factory(target=app._check_for_updates_worker, daemon=True)
    worker.start()


def check_for_updates_now(app, *, app_version, fetch_latest_release, is_newer_version,
                          releases_page_url, url_error_types):
    """Synchronous update check triggered manually by the user.

    Shows a result dialog regardless of outcome so the user can see exactly
    what was found (or why the download path is not available).
    """
    try:
        release = fetch_latest_release()
    except url_error_types as exc:
        messagebox.showinfo(
            "Check for Updates",
            f"Could not reach GitHub to check for updates.\n\nError: {exc}",
        )
        return

    latest_tag = release.get("tag_name", "")
    if not is_newer_version(latest_tag, app_version):
        messagebox.showinfo(
            "Check for Updates",
            f"You are up to date.\n\nCurrent version: {app_version}\nLatest release: {latest_tag or '(none found)'}",
        )
        return

    exe_url = update_flow.find_exe_asset(release)
    frozen = update_flow.can_self_update()

    if frozen and exe_url:
        # Full self-update path — hand off to the normal prompt
        app._prompt_for_update(release)
        return

    # Something is missing — explain clearly
    release_name = release.get("name") or latest_tag
    lines = [
        f"Update available: {release_name}",
        f"\nCurrent version : {app_version}",
        f"Latest release  : {latest_tag}",
        "",
    ]
    if not frozen:
        lines.append(
            "Auto-install is only available when running the packaged .exe.\n"
            "Running from source — manual download required."
        )
    if not exe_url:
        asset_count = len(release.get("assets") or [])
        if asset_count == 0:
            lines.append(
                "No release assets found on this GitHub release.\n"
                "Attach POBuilder.exe as a release asset to enable auto-install."
            )
        else:
            lines.append(
                f"{asset_count} asset(s) found on this release, but none end in .exe.\n"
                "Ensure the uploaded file is named POBuilder.exe."
            )

    lines += ["", "Open the release page to download manually?"]
    answer = messagebox.askyesno("Check for Updates", "\n".join(lines))
    if answer:
        target = release.get("html_url") or releases_page_url
        try:
            webbrowser.open(target)
        except Exception:
            messagebox.showinfo("Release Page", f"Open this page in your browser:\n{target}")


def check_for_updates_worker(app, *, app_version, fetch_latest_release, is_newer_version, url_error_types):
    try:
        release = fetch_latest_release()
    except url_error_types:
        return
    latest_tag = release.get("tag_name", "")
    if not is_newer_version(latest_tag, app_version):
        return
    app.root.after(0, lambda: app._prompt_for_update(release))


def prompt_for_update(app, release, *, app_version, releases_page_url):
    latest_tag = release.get("tag_name", "")
    release_name = release.get("name") or latest_tag
    published_at = release.get("published_at", "")
    details = f"Version {latest_tag}"
    if release_name and release_name != latest_tag:
        details = f"{release_name} ({latest_tag})"
    if published_at:
        details += f"\nPublished: {published_at[:10]}"

    exe_url = update_flow.find_exe_asset(release)
    if update_flow.can_self_update() and exe_url:
        _prompt_for_update_with_download(
            app,
            release,
            exe_url=exe_url,
            app_version=app_version,
            details=details,
            releases_page_url=releases_page_url,
        )
        return

    answer = messagebox.askyesno(
        "Update Available",
        f"A newer release is available on GitHub.\n\nCurrent version: {app_version}\nLatest release: {details}\n\nOpen the release page now?",
    )
    if answer:
        target = release.get("html_url") or releases_page_url
        try:
            webbrowser.open(target)
        except Exception:
            messagebox.showinfo(
                "Release Page",
                f"Open this page in your browser:\n{target}",
            )


def _prompt_for_update_with_download(app, release, *, exe_url, app_version, details, releases_page_url):
    """Offer automatic download-and-replace when running as a packaged .exe."""
    answer = messagebox.askyesnocancel(
        "Update Available",
        (
            f"A newer release is available on GitHub.\n\n"
            f"Current version: {app_version}\n"
            f"Latest release: {details}\n\n"
            f"Download and install now? (The app will restart.)\n\n"
            f"Yes = Download & install\n"
            f"No  = Open release page\n"
            f"Cancel = Remind me next time"
        ),
    )
    if answer is None:
        return
    if not answer:
        target = release.get("html_url") or releases_page_url
        try:
            webbrowser.open(target)
        except Exception:
            messagebox.showinfo("Release Page", f"Open this page in your browser:\n{target}")
        return

    current_exe = sys.executable
    staging = update_flow.staging_path_for(current_exe)
    _run_download_and_install(app, exe_url=exe_url, staging_path=staging, current_exe=current_exe)


def _run_download_and_install(app, *, exe_url, staging_path, current_exe):
    """Download the update in a background thread and offer to restart when done."""
    root = getattr(app, "root", None)

    def _worker():
        try:
            update_flow.download_update(exe_url, staging_path)
        except Exception as exc:
            update_flow.cleanup_staging(staging_path)
            if root is not None:
                root.after(0, lambda: messagebox.showerror(
                    "Update Failed",
                    f"The download could not complete:\n{exc}\n\n"
                    "Please download the update manually from the release page.",
                ))
            return
        if root is not None:
            root.after(0, _offer_restart)

    def _offer_restart():
        try:
            script = update_flow.write_updater_script(staging_path, current_exe)
        except Exception as exc:
            update_flow.cleanup_staging(staging_path)
            messagebox.showerror(
                "Update Failed",
                f"Could not write the updater script:\n{exc}\n\n"
                "The downloaded file has been removed.",
            )
            return
        ready = messagebox.askyesno(
            "Ready to Install",
            "The update has been downloaded.\n\n"
            "Click Yes to restart POBuilder and apply the update, "
            "or No to apply it the next time you close the app.",
        )
        if ready:
            update_flow.launch_updater_and_exit(app, script)

    thread = threading.Thread(target=_worker, daemon=True)
    if root is not None:
        root.after(0, lambda: messagebox.showinfo(
            "Downloading Update",
            "Downloading the update in the background.\n"
            "You will be notified when it is ready to install.",
        ))
    thread.start()
