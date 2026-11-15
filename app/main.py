# app/main.py

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, JSONResponse

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.middlewares.auth import AuthRedirectMiddleware
from app.middlewares.ui_language import UILanguageMiddleware
from app.routers.web.ui_language import router as ui_language_router
from app.routers import router as root_router
from app.modules.reports.utils.report_verify_setup import (
    setup_report_verify_registry,
)

# -------------------------------
# Settings & Logging
# -------------------------------

settings = get_settings()
setup_logging(debug=settings.is_debug)

logger = logging.getLogger(__name__)


# -------------------------------
# Lifespan (startup logic)
# -------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Application startup...")

    yield

    logger.info("Application shutdown...")


# -------------------------------
# FastAPI App
# -------------------------------

app = FastAPI(lifespan=lifespan)

setup_report_verify_registry()

app.add_middleware(AuthRedirectMiddleware)
app.add_middleware(UILanguageMiddleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,  # ← обязательно из .env
)

BASE_DIR = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "web" / "static"),
    name="static",
)


if settings.use_local_storage:
    app.mount(
        settings.storage_public_base_url,
        StaticFiles(directory=settings.STORAGE_LOCAL_ROOT),
        name="storage",
    )

app.include_router(ui_language_router)
app.include_router(root_router)


# -------------------------------
# Routes
# -------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login", status_code=303)


# -------------------------------
# Exception handlers
# -------------------------------

from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.question_bank_i18n import (
    is_question_bank_request,
    question_bank_validation_response,
)
from app.core.assessment_i18n import (
    is_assessment_request, assessment_validation_response,
)
from app.core.staff_i18n import is_staff_request, staff_validation_response
from app.core.planning_i18n import is_planning_request, planning_validation_response
from app.core.execution_i18n import is_execution_request, execution_validation_response
from app.core.reports_i18n import reports_http_exception_handler, is_reports_request, reports_validation_response
app.add_exception_handler(StarletteHTTPException, reports_http_exception_handler)

uvicorn_logger = logging.getLogger("uvicorn.error")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    uvicorn_logger.error(
        "422 VALIDATION ERROR on %s: %s",
        request.url.path,
        exc.errors(),
    )
    if is_reports_request(request):
        return reports_validation_response(request, exc.errors())
    if is_execution_request(request):
        return execution_validation_response(request, exc.errors())
    if is_planning_request(request):
        return planning_validation_response(request, exc.errors())
    if is_staff_request(request):
        return staff_validation_response(request, exc.errors())
    if is_question_bank_request(request):
        return question_bank_validation_response(request, exc.errors())
    if is_assessment_request(request):
        return assessment_validation_response(request, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# Validate flags at startup and retain localized feature errors outside legacy handlers.
from app.core.feature_flags import get_features
from app.core.feature_access import FeatureUnavailable, unavailable_response
get_features()
app.add_exception_handler(FeatureUnavailable, unavailable_response)

# Opt-in local navigation profiling; disabled unless explicitly enabled.
from app.core.planning_profile import install_planning_profile
install_planning_profile(app)
