"""SessionController — owns the session state bundle and the
memoized calculation helpers that flow modules call on ``app``.

This is a non-Tk class that can be composed into ``POBuilderApp``
or used standalone in tests.  Flow modules continue to call
``app._recalculate_item(item)`` etc. — the methods are defined
here and inherited by the app.

Phase 3.5 step: eventually ``POBuilderApp`` will hold a
``SessionController`` reference instead of inheriting from it,
completing the separation of Tk view layer from business logic.
"""

import reorder_flow
import item_workflow
import shipping_flow
from models import AppSessionState


# Minimum annualized sales to generate min/max suggestions.
MIN_ANNUAL_SALES_FOR_SUGGESTIONS = 4


class SessionController:
    """Non-Tk session state owner with memoized calculation helpers."""

    def __init__(self):
        self.session = AppSessionState()
        self._suggest_min_max_cache = None
        self._pack_size_resolution_cache = None
        self._suggest_min_max_source_cache = None

    def _get_cycle_weeks(self):
        """Return the current reorder cycle in weeks."""
        var = getattr(self, "var_reorder_cycle", None)
        if var and hasattr(var, "get"):
            label = var.get()
            return {"Weekly": 1, "Bi-Weekly": 2, "Monthly": 4}.get(label, 1)
        return 1

    def _suggest_min_max(self, key):
        cache = self._suggest_min_max_cache
        if cache is None:
            cache = {}
            self._suggest_min_max_cache = cache
        hit = cache.get(key)
        if hit is not None:
            return hit
        result = reorder_flow.suggest_min_max(self, key, MIN_ANNUAL_SALES_FOR_SUGGESTIONS)
        cache[key] = result
        return result

    def _invalidate_suggest_min_max_cache(self):
        self._suggest_min_max_cache = None

    def _recalculate_item(self, item, annotate_release=True):
        from rules import get_rule_key
        session = getattr(self, "session", self)
        item["reorder_cycle_weeks"] = self._get_cycle_weeks()
        item_workflow.recalculate_item_from_session(item, session, self._suggest_min_max, get_rule_key)
        if annotate_release:
            shipping_flow.annotate_release_decisions(session)
        return item
