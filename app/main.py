# app/main.py

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
from app.routers import router as root_router

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

app.add_middleware(AuthRedirectMiddleware)

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

app.include_router(root_router)
for r in app.router.routes:
    if getattr(r, "name", "") == "school_staff_dismiss_member":
        print("FOUND:", r.path, r.methods)


# -------------------------------
# Routes
# -------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login", status_code=303)


# -------------------------------
# Exception handlers
# -------------------------------

uvicorn_logger = logging.getLogger("uvicorn.error")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    uvicorn_logger.error(
        "422 VALIDATION ERROR on %s: %s",
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
