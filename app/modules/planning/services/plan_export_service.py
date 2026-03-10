# app/modules/planning/services/plan_export_service.py (Экпортирием план школы в PDF)

from __future__ import annotations
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow4, SchoolPlanRow11
from app.modules.planning.models import PlanDirection

from app.modules.org.models import School, District
from app.modules.users.models import User


@dataclass
class PlanMeta:
    school_name: str
    director_fio: str
    district_name: str | None = None


@dataclass
class DirectionBlock:
    direction: PlanDirection
    rows4: list[SchoolPlanRow4]
    rows11: list[SchoolPlanRow11]


@dataclass
class FullPlanDTO:
    plan: SchoolPlan
    directions: list[DirectionBlock]
    meta: PlanMeta


class SchoolPlanExportService:

    @staticmethod
    async def get_full_plan(
            db: AsyncSession,
            *,
            school_plan_id: int,
            user: User,
    ) -> FullPlanDTO | None:

        # 0) админ школы обязан иметь school_id
        if user.school_id is None:
            return None

        # 1) план должен принадлежать этой школе
        plan: SchoolPlan | None = await db.get(SchoolPlan, school_plan_id)
        if plan is None or plan.school_id != user.school_id:
            return None

        # 2) школа
        school: School | None = await db.get(School, user.school_id)
        if school is None:
            return None

        # 3) район
        district: District | None = None
        if school.district_id:
            district = await db.get(District, school.district_id)

        meta = PlanMeta(
            school_name=(school.name or "").strip() or f"Школа #{school.id}",
            director_fio=(user.full_name or "").strip() or "________________________",
            district_name=(district.name if district else None),  # ✅ добавили район
        )
        # 3) направления
        directions: list[PlanDirection] = list(
            (await db.scalars(
                select(PlanDirection)
                .order_by(PlanDirection.sort_order.asc(), PlanDirection.id.asc())
            )).all()
        )

        blocks: list[DirectionBlock] = []

        for d in directions:
            rows4: list[SchoolPlanRow4] = list(
                (await db.scalars(
                    select(SchoolPlanRow4)
                    .where(
                        SchoolPlanRow4.school_plan_id == school_plan_id,
                        SchoolPlanRow4.direction_id == d.id,
                    )
                    .order_by(SchoolPlanRow4.row_order.asc(), SchoolPlanRow4.id.asc())
                )).all()
            )

            rows11: list[SchoolPlanRow11] = list(
                (await db.scalars(
                    select(SchoolPlanRow11)  # ✅ было SchoolPlanRow4
                    .where(
                        SchoolPlanRow11.school_plan_id == school_plan_id,  # ✅ было Row4
                        SchoolPlanRow11.direction_id == d.id,              # ✅ было Row4
                    )
                    .order_by(SchoolPlanRow11.row_order.asc(), SchoolPlanRow11.id.asc())
                )).all()
            )

            if not rows4 and not rows11:
                continue

            blocks.append(DirectionBlock(direction=d, rows4=rows4, rows11=rows11))

        return FullPlanDTO(plan=plan, directions=blocks, meta=meta)
