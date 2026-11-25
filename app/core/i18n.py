"""UI localization only. Assessment and instruction languages remain independent."""
from functools import lru_cache
import gettext
from pathlib import Path
from urllib.parse import unquote, urlsplit

DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES = (("kk", "Қазақша"), ("ru", "Русский"))
COOKIE_NAME = "ui_language"
LOCALE_DIR = Path(__file__).resolve().parents[1] / "locales"


def normalize_language(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower().replace("_", "-").split("-")[0]
    if value == "kz":
        value = "kk"
    return value if value in {"kk", "ru"} else None


def resolve_language(request, user=None):
    saved = (user.get("ui_language") if isinstance(user, dict)
             else getattr(user, "ui_language", None))
    return (normalize_language(saved)
            or normalize_language(getattr(request.state, "ui_language", None))
            or normalize_language(request.cookies.get(COOKIE_NAME))
            or DEFAULT_LANGUAGE)


@lru_cache(maxsize=2)
def catalog(language):
    # Catalogs are immutable shared objects; the selected language is request-local.
    return gettext.translation("messages", LOCALE_DIR,
                               languages=[normalize_language(language) or DEFAULT_LANGUAGE])


def translate(message, language=DEFAULT_LANGUAGE, **values):
    from app.modules.planning.review_places import label_for_message
    from app.core.system_message_pairs import paired_message
    selected_language = normalize_language(language) or DEFAULT_LANGUAGE
    selected = label_for_message(message, selected_language)
    if selected is None:
        selected = paired_message(message, selected_language)
    text = selected if selected is not None else catalog(language).gettext(message)
    return text % values if values else text


def gettext_for(request, message, **values):
    return translate(message, resolve_language(request), **values)


def safe_return_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return "/dashboards"
    decoded = value
    for _ in range(4):
        decoded = unquote(decoded)
    if (not decoded.startswith("/") or decoded.startswith("//")
            or "\\" in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded)):
        return "/dashboards"
    parts = urlsplit(decoded)
    if parts.scheme or parts.netloc or parts.path.rstrip("/") == "/ui/language":
        return "/dashboards"
    return value


def set_language_cookie(response, request, language):
    response.set_cookie(COOKIE_NAME, language, max_age=365 * 24 * 60 * 60,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https",
                        path="/")
