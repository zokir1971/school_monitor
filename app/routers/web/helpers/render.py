# app/web/helpers/render.py (Стандарт “рендер + ошибка”)

from __future__ import annotations

from starlette.responses import Response


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
    }


def render(templates, request, name: str, ctx: dict, status_code: int = 200):
    c = dict(ctx)
    c.setdefault("request", request)

    # ключевой фикс: user в шаблон — только примитивы
    if "user" in c:
        c["user"] = _normalize_user(c["user"])

    return templates.TemplateResponse(request, name, c, status_code=status_code)


def render_error(templates, request, name: str, ctx: dict, error: str, status_code: int = 400) -> Response:
    c = dict(ctx)
    c["error"] = error
    return render(templates, request, name, c, status_code=status_code)
