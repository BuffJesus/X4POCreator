import os
import webbrowser
from tkinter import messagebox

import storage


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
