"""A locale snapshot for one synchronous, audited planning-page render.

These templates render one authenticated user and never switch locale inside
the render. The snapshot and bounded translation memo are discarded afterwards;
no user, school, authored text or final HTML is cached across requests.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from app.core.i18n import catalog, resolve_language


PLANNING_READ_TEMPLATES = frozenset({
    "planning/school/monthly_tasks.html",
    "planning/school/plan_preview.html",
})

_active_locale = ContextVar("planning_render_locale", default=None)
_missing = object()


class _RenderLocale:
    __slots__ = ("request", "user", "language", "_translate", "_messages")

    def __init__(self, request, user):
        self.request = request
        self.user = user
        self.language = resolve_language(request, user)
        self._translate = catalog(self.language).gettext
        self._messages = {}

    def matches(self, context):
        return (context.get("request") is self.request
                and context.get("user") is self.user)

    def gettext(self, message):
        # Preserve handling of Markup, string subclasses and unusual arguments.
        # Cache only raw translations, before per-call %-formatting.
        if type(message) is not str:
            return self._translate(message)
        translated = self._messages.get(message, _missing)
        if translated is _missing:
            translated = self._translate(message)
            if len(self._messages) < 256:
                self._messages[message] = translated
        return translated


def matching_render_locale(context):
    snapshot = _active_locale.get()
    if snapshot is not None and snapshot.matches(context):
        return snapshot
    return None


@contextmanager
def planning_render_locale(template_name, context):
    # Never let an outer planning render optimize an unrelated nested page.
    snapshot = (_RenderLocale(context["request"], context.get("user"))
                if template_name in PLANNING_READ_TEMPLATES else None)
    token = _active_locale.set(snapshot)
    try:
        if snapshot is not None:
            snapshot.request.state.ui_language = snapshot.language
        yield
    finally:
        _active_locale.reset(token)
        parent = _active_locale.get()
        if parent is not None:
            parent.request.state.ui_language = parent.language
        elif snapshot is not None:
            snapshot.request.state.ui_language = snapshot.language
