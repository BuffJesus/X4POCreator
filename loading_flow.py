import math
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


def load_gif_frames(
    gif_path,
    *,
    target_size,
    max_frames,
    has_pil,
    image_module,
    image_tk_module,
    tk_module,
):
    frames = []
    if not os.path.exists(gif_path):
        return frames

    if has_pil:
        try:
            img = image_module.open(gif_path)
            frame_count = max(1, int(getattr(img, "n_frames", 1)))
            step = max(1, math.ceil(frame_count / max_frames))
            for i in range(0, frame_count, step):
                img.seek(i)
                frame = img.copy().convert("RGBA").resize(target_size, image_module.LANCZOS)
                frames.append(image_tk_module.PhotoImage(frame))
            if frames:
                return frames
        except Exception:
            frames = []

    try:
        target_w, target_h = target_size
        i = 0
        while i < max_frames:
            frame = tk_module.PhotoImage(file=gif_path, format=f"gif -index {i}")
            fw = max(1, frame.width())
            fh = max(1, frame.height())
            sx = max(1, round(fw / target_w))
            sy = max(1, round(fh / target_h))
            if sx > 1 or sy > 1:
                frame = frame.subsample(sx, sy)
            frames.append(frame)
            i += 1
    except Exception:
        pass
    return frames


def animate_loading(app):
    if not app._loading_overlay or not app._loading_frames:
        return
    frame = app._loading_frames[app._loading_frame_idx % len(app._loading_frames)]
    app._loading_img_label.configure(image=frame)
    app._loading_frame_idx += 1
    app._loading_after_id = app.root.after(50, app._animate_loading)


def ensure_corner_loading_gif(app, label_factory):
    if getattr(app, "_corner_loading_label", None) is not None:
        return app._corner_loading_label
    if not getattr(app, "_corner_loading_frames", None):
        return None

    label = label_factory(app.notebook)
    label.place(relx=1.0, x=-12, y=6, anchor="ne")
    try:
        label.lift()
    except Exception:
        pass
    app._corner_loading_label = label
    app._corner_loading_frame_idx = 0
    return label


def animate_corner_loading(app):
    label = getattr(app, "_corner_loading_label", None)
    frames = getattr(app, "_corner_loading_frames", None)
    if label is None or not frames:
        return
    try:
        frame = frames[app._corner_loading_frame_idx % len(frames)]
        label.configure(image=frame)
    except Exception:
        app._corner_loading_after_id = None
        return
    app._corner_loading_frame_idx += 1
    app._corner_loading_after_id = app.root.after(50, app._animate_corner_loading)


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


def run_with_loading(app, text, func, *args, min_seconds=0):
    app._show_loading(text)
    app.root.update()
    result_holder = {"result": None, "error": None}
    start_time = time.monotonic()
    min_seconds = max(0.0, float(min_seconds or 0))

    def _worker():
        try:
            result_holder["result"] = func(*args)
        except Exception as exc:
            result_holder["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    while thread.is_alive() or (time.monotonic() - start_time) < min_seconds:
        try:
            if hasattr(app.root, "update_idletasks"):
                app.root.update_idletasks()
            app.root.update()
        except Exception:
            break
        if thread.is_alive():
            thread.join(0.016)
        else:
            remaining = min_seconds - (time.monotonic() - start_time)
            if remaining > 0:
                time.sleep(min(0.016, remaining))

    app._hide_loading()

    if result_holder["error"]:
        raise result_holder["error"]
    return result_holder["result"]
