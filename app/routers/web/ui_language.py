"""Switch interface language for guests and authenticated users."""
from urllib.parse import urlsplit
from time import perf_counter
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.i18n import normalize_language, set_language_cookie
from app.core.ui_language_return import language_read_url
from app.db.session import get_db
from app.modules.users.deps import _get_session_user_id
from app.modules.users.repo import UserRepo

router = APIRouter()


@router.post("/ui/language", name="ui_language_switch")
async def switch_ui_language(request: Request, language: str = Form(...),
                             next: str = Form("/dashboards"),
                             db: AsyncSession = Depends(get_db)):
    started=perf_counter()
    locale = normalize_language(language)
    if locale is None:
        raise HTTPException(400, "Unsupported interface language")
    origin = request.headers.get("origin")
    expected = urlsplit(str(request.base_url))
    if origin:
        actual = urlsplit(origin)
        if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
            raise HTTPException(403, "Cross-origin language switch is not allowed")
    user_id = _get_session_user_id(request)
    write_started=perf_counter()
    if user_id and await UserRepo.set_ui_language(db,user_id,locale):
        await db.commit()
    written=perf_counter()
    response = RedirectResponse(language_read_url(request,next), status_code=303)
    routed=perf_counter()
    response.headers['Server-Timing']=f'language_write;dur={(written-write_started)*1000:.2f}, return_route;dur={(routed-written)*1000:.2f}, language_total;dur={(routed-started)*1000:.2f}'
    set_language_cookie(response, request, locale)
    return response
