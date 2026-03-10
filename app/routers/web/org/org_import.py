# app/routers/web/org/org_import>py

from __future__ import annotations

import os
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.org.utils import read_schools_from_xlsx
from app.modules.org.service import OrgImportService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole

router = APIRouter(prefix="/org-import", tags=["org-import"])


@router.post("/schools-xlsx", name="import_schools_xlsx")
async def import_schools_xlsx(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Разрешен только .xlsx файл")

    tmp_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        rows = read_schools_from_xlsx(tmp_path)

        if not rows:
            raise HTTPException(status_code=400, detail="Файл пустой или не содержит данных")

        await OrgImportService.import_schools_from_rows(
            db,
            rows=rows,
        )

        await db.commit()

        return RedirectResponse(
            url="/schools/",
            status_code=303,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
