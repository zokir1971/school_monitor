# app/routers/web/helpers/render.py (Стандарт “рендер + ошибка”)

from __future__ import annotations

from starlette.responses import Response
from app.core.render_urls import indexed_render_urls


def _normalize_user(u):
    """Превращаем ORM User в безопасный для Jinja словарь (без IO)."""
    if u is None:
        return None
    if isinstance(u, dict):
        return u

    # важно: только простые поля, без relationship!
    role = getattr(u, "role", None)
    if hasattr(role, "value"):
        role = role.value

    return {
        "id": getattr(u, "id", None),
        "username": getattr(u, "username", None),
        "full_name": getattr(u, "full_name", None),  # ✅ добавить
        "role": role,
        "ui_language": getattr(u, "ui_language", None),
    }


def render(
        templates,
        request,
        name: str,
        ctx: dict,
        status_code: int = 200,
):
    c = dict(ctx)

    c.setdefault(
        "request",
        request,
    )

    # --------------------------------------------------------
    # REQUEST-SCOPED WORKSPACE CONTEXT
    # --------------------------------------------------------

    workspace_context = getattr(
        request.state,
        "workspace_context",
        None,
    )

    if workspace_context is not None:
        c.setdefault(
            "workspace_context",
            workspace_context,
        )

    # --------------------------------------------------------
    # USER NORMALIZATION
    # --------------------------------------------------------

    if "user" in c:
        c["user"] = _normalize_user(
            c["user"]
        )

    with indexed_render_urls(c["request"]):
        return templates.TemplateResponse(
            request,
            name,
            c,
            status_code=status_code,
        )


def render_error(templates, request, name: str, ctx: dict, error: str, status_code: int = 400) -> Response:
    c = dict(ctx)
    c["error"] = error
    return render(templates, request, name, c, status_code=status_code)
