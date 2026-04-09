"""Consolidated bulk-grid cache state.

Replaces the three independent cache attributes
(``_bulk_row_index_cache``, ``_bulk_filter_result_cache``,
``_bulk_visible_rows_cache``) with a single object that makes
invalidation explicit and atomic.

Usage::

    cache = BulkCacheState.get(app)
    cache.invalidate_row_index()
    cache.invalidate_filter_result()
    cache.invalidate_visible_rows()
    cache.invalidate_all()  # atomic clear
"""


class BulkCacheState:
    """Manages the three bulk-grid caches on a single object."""

    __slots__ = (
        "row_index", "row_index_generation",
        "filter_result", "filter_result_generation",
        "visible_rows", "visible_rows_generation",
        "row_render", "row_render_generation",
    )

    def __init__(self):
        self.row_index = None
        self.row_index_generation = 0
        self.filter_result = None
        self.filter_result_generation = 0
        self.visible_rows = None
        self.visible_rows_generation = 0
        self.row_render = {}
        self.row_render_generation = 0

    def invalidate_row_index(self):
        self.row_index = None
        self.row_index_generation += 1

    def invalidate_filter_result(self):
        self.filter_result = None
        self.filter_result_generation += 1

    def invalidate_visible_rows(self):
        self.visible_rows = None
        self.visible_rows_generation += 1

    def bump_row_render_generation(self):
        self.row_render_generation += 1

    def invalidate_all(self):
        self.invalidate_row_index()
        self.invalidate_filter_result()
        self.invalidate_visible_rows()
        self.bump_row_render_generation()

    @staticmethod
    def get(app):
        """Get or create the BulkCacheState on *app*."""
        cache = getattr(app, "_bulk_cache", None)
        if not isinstance(cache, BulkCacheState):
            cache = BulkCacheState()
            app._bulk_cache = cache
        return cache
