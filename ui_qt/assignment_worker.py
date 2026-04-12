"""QThread worker for the assignment pipeline.

Runs ``QtSessionController.prepare_assignment`` off the main thread
so the UI stays responsive during the 5–30 second enrichment pass
on a 63K-item dataset.  Progress messages are streamed back to the
main thread via a Qt signal.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal


class AssignmentWorker(QObject):
    """Runs prepare_assignment in a background thread."""

    progress = Signal(str)
    finished = Signal(bool)   # True if items available
    failed = Signal(str)

    def __init__(self, controller):
        super().__init__()
        self._controller = controller

    def run(self):
        try:
            def _progress_cb(msg: str):
                self.progress.emit(msg)

            has_items = self._controller.prepare_assignment(
                progress_cb=_progress_cb,
            )
            self.finished.emit(has_items)
        except Exception as exc:
            self.failed.emit(str(exc))
