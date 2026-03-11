# app/modules/planning/services/school_service.py
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.datastructures import FormData

from app.modules.planning.enums import ResponsibleRole, PlanPeriodType, ReviewPlace, DocumentType
from app.modules.planning.models import PlanDirection, PlanTemplate
from app.modules.planning.models_school import SchoolPlanRow4, SchoolPlanRow11, SchoolPlan, SchoolPlanRow11Responsible
from app.modules.planning.repo_school import SchoolPlanningRepo
from app.modules.planning.validators import normalize_months_text_to_list, months_list_to_canonical_text
# проверка доступа к школе плана
from app.modules.users.permissions import assert_can_edit_school


# =========================================================
# Shared helpers (оптимизация без изменения логики)
# =========================================================

async def _get_plan_or_404(db: AsyncSession, *, plan_id: int) -> SchoolPlan:
    plan: SchoolPlan | None = await db.get(SchoolPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="План не найден")
    return plan


async def _guard_plan_edit(db: AsyncSession, *, plan_id: int, user) -> SchoolPlan:
    """
    Единая точка безопасности:
    - план существует
    - пользователь имеет право редактировать школу плана
    """
    plan = await _get_plan_or_404(db, plan_id=plan_id)
    assert_can_edit_school(user, school_id=plan.school_id)
    return plan


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _set_row_attr(row, *, field: str, value: str | None, not_null_empty_string: bool = False) -> None:
    """
    Унификация присваивания:
    - not_null_empty_string=True -> "" вместо None
    """
    if not_null_empty_string:
        setattr(row, field, value or "")
    else:
        setattr(row, field, value or None)


@dataclass
class CreateSchoolPlanResult:
    plan_id: int


class SchoolPlanningService:
    @staticmethod
    async def get_active_academic_year(db):
        result = await db.execute(
            select(PlanTemplate)
            .where(PlanTemplate.is_active.is_(True))
            .order_by(PlanTemplate.created_at.desc())
        )
        template = result.scalars().first()
        if not template:
            return None
        return template.academic_year

    @staticmethod
    async def create_plan_from_template(
            db: AsyncSession,
            *,
            school_id: int,
            template_id: int,
            academic_year: str,
            allow_multiple_per_year: bool = False,
    ) -> CreateSchoolPlanResult:
        # 1) шаблон должен существовать
        tpl = await SchoolPlanningRepo.get_template(db, template_id)
        if not tpl:
            raise ValueError("Шаблон не найден")

        # (опционально) только активные
        if not tpl.is_active:
            raise ValueError("Выбранный шаблон не активен")

        # 2) запрет дубликата на один год
        if not allow_multiple_per_year:
            exists_ = await SchoolPlanningRepo.school_plan_exists(
                db, school_id=school_id, academic_year=academic_year
            )
            if exists_:
                raise ValueError("План на выбранный учебный год уже существует")

        try:
            # 3) создаём план
            plan = await SchoolPlanningRepo.create_school_plan(
                db,
                school_id=school_id,
                template_id=template_id,
                academic_year=academic_year,
            )

            # 4) направления шаблона
            tds = await SchoolPlanningRepo.list_template_directions(db, template_id=template_id)
            td_ids = [td.id for td in tds]
            td_to_direction = {td.id: td.direction_id for td in tds}

            # 5) rows_4
            tpl_rows4 = await SchoolPlanningRepo.list_template_rows4_by_td_ids(db, td_ids=td_ids)
            school_rows4: list[SchoolPlanRow4] = [
                SchoolPlanRow4(
                    school_plan_id=plan.id,
                    direction_id=td_to_direction[r.template_direction_id],
                    row_order=r.row_order,
                    no=r.no,
                    control_object=r.control_object,
                    risk_text=r.risk_text,
                    decision_text=r.decision_text,
                )
                for r in tpl_rows4
            ]
            await SchoolPlanningRepo.bulk_add_school_rows4(db, school_rows4)

            # 6) rows_11
            tpl_rows11 = await SchoolPlanningRepo.list_template_rows11_by_td_ids(db, td_ids=td_ids)

            school_rows11: list[SchoolPlanRow11] = [
                SchoolPlanRow11(
                    school_plan_id=plan.id,
                    direction_id=td_to_direction[r.template_direction_id],
                    row_order=r.row_order,
                    topic=r.topic,
                    goal=r.goal,
                    control_object=r.control_object,
                    control_type=r.control_type,
                    methods=r.methods,
                    deadlines=r.deadlines,
                    responsibles=r.responsibles,
                    review_place=r.review_place,
                    management_decision=r.management_decision,
                    second_control=r.second_control,

                    # FIX: period_type NOT NULL
                    period_type=getattr(r, "period_type", None) or PlanPeriodType.ALL_YEAR,
                    # (если в шаблоне есть эти поля — копируются, если нет — будет None)
                    period_value_int=getattr(r, "period_value_int", None),
                    period_values=getattr(r, "period_values", None),
                )
                for r in tpl_rows11
            ]

            await SchoolPlanningRepo.bulk_add_school_rows11(db, school_rows11)
            await SchoolPlanningRepo.commit(db)
            return CreateSchoolPlanResult(plan_id=plan.id)

        except Exception:
            await SchoolPlanningRepo.rollback(db)
            raise


@dataclass
class DirectionEditDTO:
    direction: PlanDirection
    rows4: list[SchoolPlanRow4]
    rows11: list[SchoolPlanRow11]


class SchoolPlanEditService:
    @staticmethod
    async def get_direction_data(
            db: AsyncSession,
            *,
            plan_id: int,
            direction_id: int,
            user,
    ) -> DirectionEditDTO:

        # 1) Проверяем направление
        direction: PlanDirection | None = await db.get(PlanDirection, direction_id)
        if direction is None:
            raise HTTPException(status_code=404, detail="Направление не найдено")

        # 2) Проверяем план + доступ
        plan = await _guard_plan_edit(db, plan_id=plan_id, user=user)

        # 3) Лениво создаём строки из шаблона, если их ещё нет
        await SchoolPlanningRepo.ensure_direction_rows_from_template(
            db,
            school_plan_id=plan_id,
            template_id=plan.template_id,
            direction_id=direction_id,
        )

        await db.commit()

        # 4) Читаем строки после возможного создания
        rows4 = await SchoolPlanningRepo.list_rows4_by_direction(db, plan_id=plan_id, direction_id=direction_id)
        rows11 = await SchoolPlanningRepo.list_rows11_by_direction(db, plan_id=plan_id, direction_id=direction_id)
        # ===== DEBUG ПРОВЕРКА =====
        print("====== DEBUG ROWS11 ======")
        for r in rows11:
            print(
                "ROW ID:", r.id,
                "PERIOD:", r.period_type, r.period_value_int, r.period_values,
                "ROLES:", [a.role.value for a in getattr(r, "role_assignments", [])]
            )
        print("====== END DEBUG ======")
        # ==========================

        return DirectionEditDTO(direction=direction, rows4=rows4, rows11=rows11)

    # ---------- rows4 ----------
    @staticmethod
    async def add_row4(
            db: AsyncSession,
            *,
            plan_id: int,
            direction_id: int,
            user,
    ) -> None:
        await _guard_plan_edit(db, plan_id=plan_id, user=user)

        try:
            order_ = await SchoolPlanningRepo.next_row_order4(db, plan_id=plan_id, direction_id=direction_id)
            await SchoolPlanningRepo.add_row4(db, school_plan_id=plan_id, direction_id=direction_id, row_order=order_)
            await SchoolPlanningRepo.commit(db)
        except Exception:
            await SchoolPlanningRepo.rollback(db)
            raise

    @staticmethod
    async def add_row11(
            db: AsyncSession,
            *,
            plan_id: int,
            direction_id: int,
            user,
    ) -> None:
        await _guard_plan_edit(db, plan_id=plan_id, user=user)

        row_order = await SchoolPlanningRepo.next_row_order11(db, plan_id=plan_id, direction_id=direction_id)
        await SchoolPlanningRepo.add_row11(db, school_plan_id=plan_id, direction_id=direction_id, row_order=row_order)
        await db.commit()

    @staticmethod
    async def save_rows4(
            db: AsyncSession,
            *,
            plan_id: int,
            direction_id: int,
            form: FormData,
            user,
    ) -> None:
        await _guard_plan_edit(db, plan_id=plan_id, user=user)

        rows4 = await SchoolPlanningRepo.list_rows4_by_direction(db, plan_id=plan_id, direction_id=direction_id)

        try:
            for r in rows4:
                for field in SchoolRowsService.ROW4_ALLOWED:
                    key = f"{field}_{r.id}"
                    if key not in form:
                        continue
                    val_s = _clean_str(form.get(key))
                    _set_row_attr(
                        r,
                        field=field,
                        value=val_s,
                        not_null_empty_string=(field == "control_object"),
                    )

            await SchoolPlanningRepo.commit(db)
        except Exception:
            await SchoolPlanningRepo.rollback(db)
            raise

    @staticmethod
    async def save_rows11(
            db: AsyncSession,
            *,
            plan_id: int,
            direction_id: int,
            form: FormData,
            user,
    ) -> None:
        if not SchoolRowsService.ROW11_ALLOWED:
            raise ValueError("ROW11_ALLOWED пустой")

        await _guard_plan_edit(db, plan_id=plan_id, user=user)

        rows11 = await SchoolPlanningRepo.list_rows11_by_direction(db, plan_id=plan_id, direction_id=direction_id)

        try:
            for r in rows11:
                for field in SchoolRowsService.ROW11_ALLOWED:
                    key = f"{field}_{r.id}"
                    if key not in form:
                        continue
                    val_s = _clean_str(form.get(key))
                    _set_row_attr(r, field=field, value=val_s, not_null_empty_string=False)

            await SchoolPlanningRepo.commit(db)
        except Exception:
            await SchoolPlanningRepo.rollback(db)
            raise

    @staticmethod
    def _normalize_document_types(values: list[str] | None) -> list[DocumentType]:
        if not values:
            return []

        result: list[DocumentType] = []
        seen: set[str] = set()

        for raw in values:
            val = (raw or "").strip()
            if not val or val in seen:
                continue
            seen.add(val)
            result.append(DocumentType(val))

        return result

    @staticmethod
    def _normalize_review_places(values: list[str] | None) -> list[ReviewPlace]:
        if not values:
            return []

        result: list[ReviewPlace] = []
        seen: set[str] = set()

        for raw in values:
            val = (raw or "").strip()
            if not val or val in seen:
                continue
            seen.add(val)
            result.append(ReviewPlace(val))

        return result

    @staticmethod
    async def save_row11_required_documents(
            db: AsyncSession,
            *,
            row11_id: int,
            document_type_values: list[str] | None,
    ) -> None:
        doc_types = SchoolPlanEditService._normalize_document_types(document_type_values)

        await SchoolPlanningRepo.replace_required_documents(
            db,
            row11_id=row11_id,
            document_types=doc_types,
        )

    @staticmethod
    async def save_row11_review_places(
            db: AsyncSession,
            *,
            row11_id: int,
            review_place_values: list[str] | None,
    ) -> None:
        places = SchoolPlanEditService._normalize_review_places(review_place_values)

        await SchoolPlanningRepo.replace_review_places(
            db,
            row11_id=row11_id,
            review_places=places,
        )

    @staticmethod
    async def save_row11_documents_and_review_places(
            db: AsyncSession,
            *,
            row11_id: int,
            document_type_values: list[str] | None,
            review_place_values: list[str] | None,
    ) -> None:
        doc_types = SchoolPlanEditService._normalize_document_types(document_type_values)
        places = SchoolPlanEditService._normalize_review_places(review_place_values)

        await SchoolPlanningRepo.replace_required_documents(
            db,
            row11_id=row11_id,
            document_types=doc_types,
        )
        await SchoolPlanningRepo.replace_review_places(
            db,
            row11_id=row11_id,
            review_places=places,
        )


@dataclass
class RowAddResult:
    id: int


class SchoolRowsService:
    ROW4_ALLOWED = {"no", "control_object", "risk_text", "decision_text"}
    ROW11_ALLOWED = {
        "topic",
        "goal",
        "control_object",
        "control_type",
        "methods",
        "deadlines",
        "responsibles",
        "review_place",
        "management_decision",
        "second_control",
    }

    @staticmethod
    async def add_row(
            db: AsyncSession,
            *,
            school_plan_id: int,
            direction_id: int,
            kind: str,  # "row4" | "row11"
            school_id: int,
    ) -> RowAddResult:
        # логика прежняя: доступ проверяется через связку plan_id + school_id
        plan = await SchoolPlanningRepo.get_school_plan_for_school(
            db, school_plan_id=school_plan_id, school_id=school_id
        )
        if not plan:
            raise HTTPException(status_code=404, detail="План не найден")

        row_order = await SchoolPlanningRepo.next_row_order_for(
            db, kind=kind, school_plan_id=school_plan_id, direction_id=direction_id
        )

        if kind == "row4":
            row = await SchoolPlanningRepo.add_row4(
                db, school_plan_id=school_plan_id, direction_id=direction_id, row_order=row_order
            )
        elif kind == "row11":
            row = await SchoolPlanningRepo.add_row11(
                db, school_plan_id=school_plan_id, direction_id=direction_id, row_order=row_order
            )
        else:
            raise HTTPException(status_code=400, detail="Неверный kind")

        await db.commit()
        return RowAddResult(id=row.id)

    @staticmethod
    async def update_cell(
            db: AsyncSession,
            *,
            user,
            kind: str,
            row_id: int,
            field: str,
            value: str | None,
            school_plan_id: int | None = None,
            direction_id: int | None = None,
    ) -> None:
        # 1) выбрать модель и allowed
        if kind == "row4":
            model = SchoolPlanRow4
            allowed = SchoolRowsService.ROW4_ALLOWED
        elif kind == "row11":
            model = SchoolPlanRow11
            allowed = SchoolRowsService.ROW11_ALLOWED
        else:
            raise HTTPException(status_code=400, detail="Unknown kind")

        if field not in allowed:
            raise HTTPException(status_code=400, detail=f"Field '{field}' not allowed")

        # 2) загрузить строку
        row = await db.get(model, row_id)
        if not row:
            raise HTTPException(status_code=404, detail="Row not found")

        # 3) загрузить план и проверить доступ
        await _guard_plan_edit(db, plan_id=row.school_plan_id, user=user)

        # 4) дополнительные сверки
        if school_plan_id is not None and school_plan_id != row.school_plan_id:
            raise HTTPException(status_code=400, detail="school_plan_id mismatch")
        if direction_id is not None and direction_id != row.direction_id:
            raise HTTPException(status_code=400, detail="direction_id mismatch")

        # 5) обновить
        val_s = _clean_str(value)
        _set_row_attr(
            row,
            field=field,
            value=val_s,
            not_null_empty_string=(kind == "row4" and field == "control_object"),
        )

        await db.commit()

    @staticmethod
    async def update_row11_meta(
            db: AsyncSession,
            *,
            row_id: int,
            period_type: str,
            month: int | None,
            period_values: str | None,
            responsible_roles: list[str],
            user,
    ) -> SchoolPlanRow11:

        row = await SchoolPlanningRepo.get_row11(db, row_id=row_id)
        if not row:
            raise HTTPException(status_code=404, detail="Строка не найдена")

        await _guard_plan_edit(db, plan_id=row.school_plan_id, user=user)

        # ---------- PERIOD (НЕ ТРОГАЮ) ----------
        try:
            pt = PlanPeriodType(period_type)
        except Exception:
            raise HTTPException(status_code=400, detail="Некорректный period_type")

        row.period_type = pt

        if pt in (PlanPeriodType.ALL_YEAR, PlanPeriodType.MONTHLY):
            row.period_value_int = None
            row.period_values = None

        elif pt == PlanPeriodType.QUARTER:
            # QUARTER = "каждую четверть"
            row.period_value_int = None
            row.period_values = None

        elif pt == PlanPeriodType.MONTH:
            if month is None or not (1 <= month <= 12):
                raise HTTPException(status_code=400, detail="Для month нужен месяц 1..12")
            row.period_value_int = month
            row.period_values = None

        elif pt == PlanPeriodType.MONTHS:
            months = normalize_months_text_to_list(period_values or "")
            if not months:
                raise HTTPException(status_code=400, detail="Для months укажи месяцы (например: 10,1,5)")
            row.period_value_int = None
            row.period_values = months_list_to_canonical_text(months)

        else:
            # на всякий случай
            row.period_value_int = None
            row.period_values = None

        # -------- responsible roles (MULTI) ----------
        # 1) валидируем роли и приводим к enum
        enum_roles = []
        for rv in responsible_roles or []:
            try:
                enum_roles.append(ResponsibleRole(rv))
            except Exception:
                pass

        if responsible_roles and not enum_roles:
            # пришёл список, но ничего невалидно — не трогаем БД
            raise HTTPException(status_code=400, detail="Не удалось распознать выбранные роли")

        # 2) очистить старые назначения
        await db.execute(
            delete(SchoolPlanRow11Responsible)
            .where(SchoolPlanRow11Responsible.row11_id == row_id)
        )

        # 3) добавить новые
        if enum_roles:
            db.add_all(
                [SchoolPlanRow11Responsible(row11_id=row_id, role=r, is_primary=False) for r in enum_roles]
            )

        # flush, commit
        await db.flush()
        await db.commit()

        # вернуть свежий row вместе с role_assignments
        row2 = await db.scalar(
            select(SchoolPlanRow11)
            .options(selectinload(SchoolPlanRow11.role_assignments))
            .where(SchoolPlanRow11.id == row_id)
        )
        if not row2:
            raise HTTPException(status_code=404, detail="Строка не найдена после сохранения")

        return row2

    # сохранение данных из модальных окон:
    # - место рассмотрения
    # - тип документа
    @staticmethod
    async def save_row11_requirements(
            db: AsyncSession,
            *,
            row11_id: int,
            document_types: list[str] | None = None,
            review_places: list[str] | None = None,
    ) -> None:

        if document_types is not None:
            await SchoolPlanningRepo.replace_row11_documents(
                db,
                row11_id=row11_id,
                document_types=document_types,
            )

        if review_places is not None:
            await SchoolPlanningRepo.replace_row11_review_places(
                db,
                row11_id=row11_id,
                review_places=review_places,
            )
