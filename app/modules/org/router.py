# modules/org/router.py — JSON маршруты
'''
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.org.repo import OrgRepo

router = APIRouter(prefix="/api/org", tags=["org-api"])


# ---------------------------------------------------
# API: список областей (Region)
# URL: /api/org/regions
# ---------------------------------------------------
@router.get("/regions")
async def api_regions(db: AsyncSession = Depends(get_db)):
    regions = await OrgRepo.list_regions(db)
    return [{"id": r.id, "name": r.name} for r in regions]


# ---------------------------------------------------
# API: список районов по области
# URL: /api/org/districts?region_id=1
# ---------------------------------------------------
@router.get("/districts")
async def api_districts(region_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    districts = await OrgRepo.list_districts_by_region(db, region_id=region_id)
    return [{"id": d.id, "name": d.name} for d in districts]


# ---------------------------------------------------
# API: список школ по району
# URL: /api/org/schools?district_id=10
# ---------------------------------------------------
@router.get("/schools")
async def api_schools(district_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    schools = await OrgRepo.list_schools_by_district(db, district_id=district_id)
    return [{"id": s.id, "name": s.name} for s in schools]
'''

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.org.repo import OrgRepo
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User

router = APIRouter(prefix="/api/orgs", tags=["orgs-api"])


@router.get("/districts", name="api_org_districts")
async def api_org_districts(
    region_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    districts = await OrgRepo.list_districts(db, region_id=region_id)

    return {
        "status": "ok",
        "items": [
            {"id": district.id, "name": district.name}
            for district in districts
        ],
    }


@router.get("/settlements", name="api_org_settlements")
async def api_org_settlements(
    district_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    settlements = await OrgRepo.list_settlements(db, district_id=district_id)

    return {
        "status": "ok",
        "items": [
            {"name": item}
            for item in settlements
        ],
    }

@router.get("/schools", name="api_schools_list")
async def api_schools_list(
        region_id: int | None = Query(default=None),
        district_id: int | None = Query(default=None),
        q: str | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    schools = await OrgRepo.list_schools(
        db,
        region_id=region_id,
        district_id=district_id,
        q=q,
    )

    return {
        "status": "ok",
        "items": [
            {
                "user": user,
                "id": school.id,
                "name": school.name,
                "address": school.address,
                "district_id": school.district_id,
                "district_name": school.district.name,
                "region_id": school.district.region_id,
                "region_name": school.district.region.name,
            }
            for school in schools
        ],
    }


@router.delete("/schools/{school_id}", name="api_school_delete")
async def api_school_delete(
        school_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    school = await OrgRepo.get_school(db, school_id=school_id)
    if not school:
        raise HTTPException(status_code=404, detail="Школа не найдена")

    await OrgRepo.delete_school(db, school)

    return {
        "user": user,
        "status": "ok",
        "message": "Школа удалена",
    }
