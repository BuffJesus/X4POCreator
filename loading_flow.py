import os
import threading
import time


def start_loading_audio(*, has_winsound, loading_wav_file, winsound_module):
    if not has_winsound:
        return
    if not os.path.exists(loading_wav_file):
        return
    try:
        winsound_module.PlaySound(
            loading_wav_file,
            winsound_module.SND_FILENAME | winsound_module.SND_ASYNC | winsound_module.SND_LOOP,
        )
    except Exception:
        pass


def stop_loading_audio(*, has_winsound, winsound_module):
    if not has_winsound:
        return
    try:
        winsound_module.PlaySound(None, winsound_module.SND_PURGE)
    except Exception:
        pass


def animate_loading(app):
    if not app._loading_overlay or not app._loading_frames:
        return
    frame = app._loading_frames[app._loading_frame_idx % len(app._loading_frames)]
    app._loading_img_label.configure(image=frame)
    app._loading_frame_idx += 1
    app._loading_after_id = app.root.after(50, app._animate_loading)


def autosize_dialog(dlg, min_w=420, min_h=280, max_w_ratio=0.9, max_h_ratio=0.9):
    dlg.update_idletasks()
    screen_w = dlg.winfo_screenwidth()
    screen_h = dlg.winfo_screenheight()
    max_w = max(min_w, int(screen_w * max_w_ratio))
    max_h = max(min_h, int(screen_h * max_h_ratio))

    req_w = dlg.winfo_reqwidth() + 16
    req_h = dlg.winfo_reqheight() + 16
    width = max(min_w, min(req_w, max_w))
    height = max(min_h, min(req_h, max_h))

    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    dlg.geometry(f"{width}x{height}+{x}+{y}")
    dlg.minsize(min_w, min_h)


def hide_loading(app):
    if app._loading_after_id:
        app.root.after_cancel(app._loading_after_id)
        app._loading_after_id = None
    app._stop_loading_audio()
    if app._loading_overlay:
        app._loading_overlay.destroy()
        app._loading_overlay = None


def run_with_loading(app, text, func, *args, min_seconds=5):
    app._show_loading(text)
    app.root.update()
    result_holder = {"result": None, "error": None}
    start_time = time.time()

    def _worker():
        try:
            result_holder["result"] = func(*args)
        except Exception as exc:
            result_holder["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    while thread.is_alive() or (time.time() - start_time) < min_seconds:
        app.root.update()
        app.root.after(16)

    app._hide_loading()

    if result_holder["error"]:
        raise result_holder["error"]
    return result_holder["result"]
