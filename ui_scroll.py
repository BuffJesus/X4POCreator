def sync_canvas_window(canvas, content_window, width=None):
    target_width = width if width is not None else canvas.winfo_width()
    if target_width and target_width > 1:
        canvas.itemconfigure(content_window, width=target_width)
    canvas.coords(content_window, 0, 0)
    bbox = canvas.bbox("all")
    if bbox:
        canvas.configure(scrollregion=bbox)


def can_scroll_vertically(scroll_widget):
    yview = getattr(scroll_widget, "yview", None)
    if not callable(yview):
        return False
    first, last = yview()
    return (last - first) < 0.999999


def _iter_widget_tree(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _iter_widget_tree(child)


def attach_vertical_mousewheel(scroll_widget, *event_widgets):
    """Bind mouse-wheel scrolling to the given widget tree."""
    targets = event_widgets or (scroll_widget,)

    def _on_mousewheel(event):
        if not can_scroll_vertically(scroll_widget):
            return "break"
        if getattr(event, "delta", 0):
            step = -int(event.delta / 120) if event.delta else 0
            if step == 0:
                step = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = 0
        if step:
            scroll_widget.yview_scroll(step, "units")
            return "break"
        return None

    for target in targets:
        for widget in _iter_widget_tree(target):
            widget.bind("<MouseWheel>", _on_mousewheel, add="+")
            widget.bind("<Button-4>", _on_mousewheel, add="+")
            widget.bind("<Button-5>", _on_mousewheel, add="+")
