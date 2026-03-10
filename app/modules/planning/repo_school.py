# app/modules/planning/repo_school.py
from __future__ import annotations

from typing import cast, Type

from sqlalchemy import exists, update, select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import PlanStatus, PlanPeriodType, DocumentType, ReviewPlace
from app.modules.planning.models import (
    PlanTemplate,
    PlanTemplateDirection,
    PlanTemplateRow4,
    PlanTemplateRow11,
)
from app.modules.planning.models_school import (
    SchoolPlan,
    SchoolPlanRow4,
    SchoolPlanRow11, SchoolPlanRow11RequiredDocument, SchoolPlanRow11ReviewPlace,
)


class SchoolPlanningRepo:
    # =========================================================
    # Helpers (убираем дублирование)
    # =========================================================
    @staticmethod
    async def _scalar_int(db: AsyncSession, stmt) -> int:
        v = await db.scalar(stmt)
        return int(v or 0)

    @staticmethod
    def _model_for_kind(kind: str) -> Type[SchoolPlanRow4] | Type[SchoolPlanRow11]:
        if kind == "row4":
            return SchoolPlanRow4
        if kind == "row11":
            return SchoolPlanRow11
        raise ValueError("Unknown kind")

    @staticmethod
    async def _next_row_order(
            db: AsyncSession,
            *,
            model: Type[SchoolPlanRow4] | Type[SchoolPlanRow11],
            school_plan_id: int,
            direction_id: int,
    ) -> int:
        res = await db.execute(
            select(func.coalesce(func.max(model.row_order), 0)).where(
                model.school_plan_id == school_plan_id,
                model.direction_id == direction_id,
            )
        )
        return int(res.scalar_one()) + 1

    # =========================================================
    # Template -> School (безопаснее + меньше дубликатов)
    # =========================================================
    @staticmethod
    async def ensure_direction_rows_from_template(
            db: AsyncSession,
            *,
            school_plan_id: int,
            template_id: int,
            direction_id: int,
    ) -> None:
        """
        Создаёт строки для направления из шаблона ОДИН РАЗ.
        Безопасность:
        - проверяем, что план действительно относится к этому template_id (иначе не копируем)
        - копируем только если rows4 и rows11 отсутствуют
        """

        # ✅ 0) Проверяем план и соответствие template_id (защита от подмены template_id)
        plan = await db.get(SchoolPlan, school_plan_id)
        if not plan:
            return
        if plan.template_id != template_id:
            # не копируем, т.к. это потенциальная попытка скопировать чужой шаблон в план
            return

        # ✅ 1) Есть ли уже строки (если есть хоть какие-то — выходим)
        count4 = await SchoolPlanningRepo._scalar_int(
            db,
            select(func.count(SchoolPlanRow4.id)).where(
                SchoolPlanRow4.school_plan_id == school_plan_id,
                SchoolPlanRow4.direction_id == direction_id,
            ),
        )
        count11 = await SchoolPlanningRepo._scalar_int(
            db,
            select(func.count(SchoolPlanRow11.id)).where(
                SchoolPlanRow11.school_plan_id == school_plan_id,
                SchoolPlanRow11.direction_id == direction_id,
            ),
        )
        if count4 > 0 or count11 > 0:
            return

        # ✅ 2) Найти template_direction.id
        td_id = await db.scalar(
            select(PlanTemplateDirection.id).where(
                PlanTemplateDirection.template_id == template_id,
                PlanTemplateDirection.direction_id == direction_id,
            )
        )
        if not td_id:
            return  # в шаблоне нет такого направления

        # ✅ 3) Копируем rows4 пачкой
        t_rows4 = (
            await db.execute(
                select(PlanTemplateRow4)
                .where(PlanTemplateRow4.template_direction_id == td_id)
                .order_by(PlanTemplateRow4.row_order.asc(), PlanTemplateRow4.id.asc())
            )
        ).scalars().all()

        if t_rows4:
            db.add_all(
                [
                    SchoolPlanRow4(
                        school_plan_id=school_plan_id,
                        direction_id=direction_id,
                        row_order=tr.row_order,
                        no=tr.no,
                        control_object=tr.control_object or "",
                        risk_text=tr.risk_text,
                        decision_text=tr.decision_text,
                    )
                    for tr in t_rows4
                ]
            )

        # ✅ 4) Копируем rows11 пачкой
        t_rows11 = (
            await db.execute(
                select(PlanTemplateRow11)
                .where(PlanTemplateRow11.template_direction_id == td_id)
                .order_by(PlanTemplateRow11.row_order.asc(), PlanTemplateRow11.id.asc())
            )
        ).scalars().all()

        if t_rows11:
            db.add_all(
                [
                    SchoolPlanRow11(
                        school_plan_id=school_plan_id,
                        direction_id=direction_id,
                        row_order=tr.row_order,
                        topic=tr.topic,
                        goal=tr.goal,
                        control_object=tr.control_object,
                        control_type=tr.control_type,
                        methods=tr.methods,
                        deadlines=tr.deadlines,
                        responsibles=tr.responsibles,
                        review_place=tr.review_place,
                        management_decision=tr.management_decision,
                        second_control=tr.second_control,
                        # ✅ важно
                        is_custom=False,

                    )
                    for tr in t_rows11
                ]
            )

    # =========================================================
    # Templates
    # =========================================================
    @staticmethod
    async def list_active_templates(db: AsyncSession) -> list[PlanTemplate]:
        res = await db.execute(
            select(PlanTemplate)
            .where(PlanTemplate.is_active.is_(True))
            .order_by(PlanTemplate.id.desc())
        )
        return cast(list[PlanTemplate], res.scalars().all())

    @staticmethod
    async def get_template(db: AsyncSession, template_id: int) -> PlanTemplate | None:
        return await db.get(PlanTemplate, template_id)

    @staticmethod
    async def list_template_directions(
            db: AsyncSession, *, template_id: int
    ) -> list[PlanTemplateDirection]:
        res = await db.execute(
            select(PlanTemplateDirection)
            .where(PlanTemplateDirection.template_id == template_id)
            .order_by(PlanTemplateDirection.sort_order.asc(), PlanTemplateDirection.id.asc())
        )
        return cast(list[PlanTemplateDirection], res.scalars().all())

    @staticmethod
    async def list_template_rows4_by_td_ids(
            db: AsyncSession, *, td_ids: list[int]
    ) -> list[PlanTemplateRow4]:
        if not td_ids:
            return []
        res = await db.execute(
            select(PlanTemplateRow4)
            .where(PlanTemplateRow4.template_direction_id.in_(td_ids))
            .order_by(
                PlanTemplateRow4.template_direction_id.asc(),
                PlanTemplateRow4.row_order.asc(),
                PlanTemplateRow4.id.asc(),
            )
        )
        return cast(list[PlanTemplateRow4], res.scalars().all())

    @staticmethod
    async def list_template_rows11_by_td_ids(
            db: AsyncSession, *, td_ids: list[int]
    ) -> list[PlanTemplateRow11]:
        if not td_ids:
            return []
        res = await db.execute(
            select(PlanTemplateRow11)
            .where(PlanTemplateRow11.template_direction_id.in_(td_ids))
            .order_by(
                PlanTemplateRow11.template_direction_id.asc(),
                PlanTemplateRow11.row_order.asc(),
                PlanTemplateRow11.id.asc(),
            )
        )
        return cast(list[PlanTemplateRow11], res.scalars().all())

    # =========================================================
    # School plans
    # =========================================================
    @staticmethod
    async def school_plan_exists(db: AsyncSession, *, school_id: int, academic_year: str) -> bool:
        q = select(
            exists().where(
                SchoolPlan.school_id == school_id,
                SchoolPlan.academic_year == academic_year,
            )
        )
        res = await db.execute(q)
        return bool(res.scalar())

    @staticmethod
    async def create_school_plan(
            db: AsyncSession,
            *,
            school_id: int,
            template_id: int,
            academic_year: str,
    ) -> SchoolPlan:
        plan = SchoolPlan(
            school_id=school_id,
            template_id=template_id,
            academic_year=academic_year,
            status="draft",
        )
        db.add(plan)
        await db.flush()
        return plan

    @staticmethod
    async def get_school_plan(db: AsyncSession, *, plan_id: int, school_id: int) -> SchoolPlan | None:
        res = await db.execute(
            select(SchoolPlan).where(
                SchoolPlan.id == plan_id,
                SchoolPlan.school_id == school_id,
            )
        )
        return res.scalar_one_or_none()

    # alias для совместимости (если уже где-то используется старое имя)
    @staticmethod
    async def get_school_plan_for_school(
            db: AsyncSession,
            *,
            school_plan_id: int,
            school_id: int,
    ) -> SchoolPlan | None:
        return await SchoolPlanningRepo.get_school_plan(db, plan_id=school_plan_id, school_id=school_id)

    @staticmethod
    async def list_plan_directions(db: AsyncSession, *, template_id: int) -> list[PlanTemplateDirection]:
        # это дублирует list_template_directions, но пусть останется как semantic alias
        return await SchoolPlanningRepo.list_template_directions(db, template_id=template_id)

    @staticmethod
    async def list_school_plans(
            db: AsyncSession, *, school_id: int, academic_year: str | None = None
    ) -> list[SchoolPlan]:
        stmt = select(SchoolPlan).where(SchoolPlan.school_id == school_id)
        if academic_year:
            stmt = stmt.where(SchoolPlan.academic_year == academic_year)
        stmt = stmt.order_by(SchoolPlan.created_at.desc(), SchoolPlan.id.desc())
        res = await db.execute(stmt)
        return cast(list[SchoolPlan], res.scalars().all())

    # =========================================================
    # Insert rows (bulk)
    # =========================================================
    @staticmethod
    async def bulk_add_school_rows4(db: AsyncSession, rows: list[SchoolPlanRow4]) -> None:
        if rows:
            db.add_all(rows)

    @staticmethod
    async def bulk_add_school_rows11(db: AsyncSession, rows: list[SchoolPlanRow11]) -> None:
        if rows:
            db.add_all(rows)

    # =========================================================
    # Read rows
    # =========================================================
    @staticmethod
    async def list_rows4_by_direction(
            db: AsyncSession, *, plan_id: int, direction_id: int
    ) -> list[SchoolPlanRow4]:
        res = await db.execute(
            select(SchoolPlanRow4)
            .execution_options(populate_existing=True)
            .where(
                SchoolPlanRow4.school_plan_id == plan_id,
                SchoolPlanRow4.direction_id == direction_id,
            )
            .order_by(SchoolPlanRow4.row_order.asc(), SchoolPlanRow4.id.asc())
        )
        return cast(list[SchoolPlanRow4], res.scalars().all())

    @staticmethod
    async def list_rows11_by_direction(
            db: AsyncSession, *, plan_id: int, direction_id: int
    ) -> list[SchoolPlanRow11]:
        res = await db.execute(
            select(SchoolPlanRow11)
            .execution_options(populate_existing=True)
            .options(selectinload(SchoolPlanRow11.role_assignments))  # ✅ ВАЖНО
            .where(
                SchoolPlanRow11.school_plan_id == plan_id,
                SchoolPlanRow11.direction_id == direction_id,
            )
            .order_by(SchoolPlanRow11.row_order.asc(), SchoolPlanRow11.id.asc())
        )
        return cast(list[SchoolPlanRow11], res.scalars().all())

    # =========================================================
    # Row order (next_row_order4/11 -> через kind)
    # =========================================================
    @staticmethod
    async def next_row_order4(db: AsyncSession, *, plan_id: int, direction_id: int) -> int:
        return await SchoolPlanningRepo._next_row_order(
            db, model=SchoolPlanRow4, school_plan_id=plan_id, direction_id=direction_id
        )

    @staticmethod
    async def next_row_order11(db: AsyncSession, *, plan_id: int, direction_id: int) -> int:
        return await SchoolPlanningRepo._next_row_order(
            db, model=SchoolPlanRow11, school_plan_id=plan_id, direction_id=direction_id
        )

    @staticmethod
    async def next_row_order_for(
            db: AsyncSession,
            *,
            kind: str,
            school_plan_id: int,
            direction_id: int,
    ) -> int:
        model = SchoolPlanningRepo._model_for_kind(kind)
        return await SchoolPlanningRepo._next_row_order(
            db, model=model, school_plan_id=school_plan_id, direction_id=direction_id
        )

    # =========================================================
    # Single row getters (select)
    # =========================================================
    @staticmethod
    async def get_row4(db: AsyncSession, *, row_id: int) -> SchoolPlanRow4 | None:
        return await db.get(SchoolPlanRow4, row_id)

    @staticmethod
    async def get_row11(db: AsyncSession, *, row_id: int) -> SchoolPlanRow11 | None:
        return await db.scalar(
            select(SchoolPlanRow11)
            .options(
                selectinload(SchoolPlanRow11.role_assignments),
                selectinload(SchoolPlanRow11.required_documents),
                selectinload(SchoolPlanRow11.review_places),
            )
            .where(SchoolPlanRow11.id == row_id)
        )

    # =========================================================
    # Add row
    # =========================================================
    @staticmethod
    async def add_row4(
            db: AsyncSession,
            *,
            school_plan_id: int,
            direction_id: int,
            row_order: int,
    ) -> SchoolPlanRow4:
        row = SchoolPlanRow4(
            school_plan_id=school_plan_id,
            direction_id=direction_id,
            row_order=row_order,
            no=None,
            control_object="",
            risk_text=None,
            decision_text=None,
            is_custom=True,
        )
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def add_row11(
            db: AsyncSession,
            *,
            school_plan_id: int,
            direction_id: int,
            row_order: int,
    ) -> SchoolPlanRow11:

        row = SchoolPlanRow11(
            school_plan_id=school_plan_id,
            direction_id=direction_id,
            row_order=row_order,
            topic="",  # nullable=False

            # 👇 ОБЯЗАТЕЛЬНО
            period_type=PlanPeriodType.ALL_YEAR,
            is_custom=True,

            goal=None,
            control_object=None,
            control_type=None,
            methods=None,
            deadlines=None,
            responsibles=None,
            review_place=None,
            management_decision=None,
            second_control=None,
            period_value_int=None,
            period_values=None,
        )

        db.add(row)
        await db.flush()
        return row

    # =========================================================
    # Tx
    # =========================================================
    @staticmethod
    async def commit(db: AsyncSession) -> None:
        await db.commit()

    @staticmethod
    async def rollback(db: AsyncSession) -> None:
        await db.rollback()

    # =========================================================
    # Activate plan
    # =========================================================
    @staticmethod
    async def activate_plan(db: AsyncSession, *, plan_id: int, school_id: int) -> None:
        # 1) Архивируем все планы этой школы
        await db.execute(
            update(SchoolPlan)
            .where(
                SchoolPlan.school_id == school_id,
                SchoolPlan.status == PlanStatus.ACTIVE,
            )
            .values(status=PlanStatus.ARCHIVED)
        )

        # 2) Активируем выбранный план (только план этой школы)
        await db.execute(
            update(SchoolPlan)
            .where(
                SchoolPlan.id == plan_id,
                SchoolPlan.school_id == school_id,
            )
            .values(status=PlanStatus.ACTIVE)
        )

        await db.commit()

    # выбор документа на задачу
    @staticmethod
    async def list_required_documents(
            db: AsyncSession,
            *,
            row11_id: int,
    ) -> list[SchoolPlanRow11RequiredDocument]:
        res = await db.execute(
            select(SchoolPlanRow11RequiredDocument)
            .where(SchoolPlanRow11RequiredDocument.row11_id == row11_id)
            .order_by(SchoolPlanRow11RequiredDocument.id.asc())
        )
        return list(res.scalars().all())

    # место рассмотрение задачи
    @staticmethod
    async def list_review_places(
            db: AsyncSession,
            *,
            row11_id: int,
    ) -> list[SchoolPlanRow11ReviewPlace]:
        res = await db.execute(
            select(SchoolPlanRow11ReviewPlace)
            .where(SchoolPlanRow11ReviewPlace.row11_id == row11_id)
            .order_by(SchoolPlanRow11ReviewPlace.id.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def replace_required_documents(
            db: AsyncSession,
            *,
            row11_id: int,
            document_types: list[DocumentType],
    ) -> None:
        await db.execute(
            delete(SchoolPlanRow11RequiredDocument)
            .where(SchoolPlanRow11RequiredDocument.row11_id == row11_id)
        )

        for doc_type in document_types:
            db.add(
                SchoolPlanRow11RequiredDocument(
                    row11_id=row11_id,
                    document_type=doc_type,
                )
            )

        await db.flush()

    @staticmethod
    async def replace_review_places(
            db: AsyncSession,
            *,
            row11_id: int,
            review_places: list[ReviewPlace],
    ) -> None:
        await db.execute(
            delete(SchoolPlanRow11ReviewPlace)
            .where(SchoolPlanRow11ReviewPlace.row11_id == row11_id)
        )

        for place in review_places:
            db.add(
                SchoolPlanRow11ReviewPlace(
                    row11_id=row11_id,
                    review_place=place,
                )
            )

        await db.flush()

    # сохранение данных из модального окна: место рассмотрения
    @staticmethod
    async def replace_row11_review_places(
            db: AsyncSession,
            *,
            row11_id: int,
            review_places: list[str],
    ) -> None:

        await db.execute(
            delete(SchoolPlanRow11ReviewPlace)
            .where(SchoolPlanRow11ReviewPlace.row11_id == row11_id)
        )

        for rp in review_places:
            val = (rp or "").strip()
            if not val:
                continue

            db.add(
                SchoolPlanRow11ReviewPlace(
                    row11_id=row11_id,
                    review_place=ReviewPlace(val),
                )
            )

        await db.flush()

    # сохранение данных из модального окна: тип документа
    @staticmethod
    async def replace_row11_documents(
            db: AsyncSession,
            *,
            row11_id: int,
            document_types: list[str],
    ) -> None:

        await db.execute(
            delete(SchoolPlanRow11RequiredDocument)
            .where(SchoolPlanRow11RequiredDocument.row11_id == row11_id)
        )

        for dt in document_types:
            val = (dt or "").strip()
            if not val:
                continue

            db.add(
                SchoolPlanRow11RequiredDocument(
                    row11_id=row11_id,
                    document_type=DocumentType(val),
                )
            )

        await db.flush()
