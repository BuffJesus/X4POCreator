def _iter_widget_tree(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _iter_widget_tree(child)


def attach_vertical_mousewheel(scroll_widget, *event_widgets):
    """Bind mouse-wheel scrolling to the given widget tree."""
    targets = event_widgets or (scroll_widget,)

    def _on_mousewheel(event):
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
