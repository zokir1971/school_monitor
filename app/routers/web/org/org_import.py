# app/routers/web/org/org_import>py

from __future__ import annotations

from zipfile import BadZipFile
from openpyxl.utils.exceptions import InvalidFileException
from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.i18n import resolve_language
from app.core.schools_i18n import school_feedback
from app.db.session import get_db
from app.modules.org.utils import read_schools_from_xlsx
from app.modules.org.service import OrgImportService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole

router = APIRouter(prefix="/org-import", tags=["org-import"])


@router.post("/schools-xlsx", name="import_schools_xlsx")
async def import_schools_xlsx(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    language = resolve_language(request, _user)
    if not file.filename:
        raise HTTPException(
            status_code=400, detail=school_feedback("Файл не выбран", language)
        )

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail=school_feedback("Разрешен только .xlsx файл", language),
        )

    try:
        await file.seek(0)
        rows = await run_in_threadpool(read_schools_from_xlsx, file.file)

        if not rows:
            raise HTTPException(
                status_code=400,
                detail=school_feedback("Файл пустой или не содержит данных", language),
            )

        await OrgImportService.import_schools_from_rows(
            db,
            rows=rows,
        )

        return RedirectResponse(
            url="/schools/",
            status_code=303,
        )

    except IntegrityError as exc:
        raise HTTPException(409, school_feedback(None, language)) from exc
    except (ValueError, BadZipFile, InvalidFileException) as exc:
        raise HTTPException(
            status_code=400, detail=school_feedback(str(exc), language)
        ) from exc

    finally:
        await file.close()
