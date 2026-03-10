# app/planning/repo.py
from __future__ import annotations

from sqlalchemy import update, desc, select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.models import (
    PlanDirection,
    PlanTemplate,
    PlanTemplateRow11, )
from app.modules.planning.models import PlanTemplateRow4, PlanTemplateDirection


# =========================================================
# Directions (Направления ВШК)
# =========================================================
class PlanDirectionRepo:
    @staticmethod
    async def list_active(db: AsyncSession) -> list[PlanDirection]:
        """
        Активные направления.
        У тебя нет sort_order в модели -> сортируем по short_title/id.
        """
        res = await db.execute(
            select(PlanDirection)
            .where(PlanDirection.is_active.is_(True))
            .order_by(PlanDirection.short_title.asc(), PlanDirection.id.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def list_all(db: AsyncSession) -> list[PlanDirection]:
        res = await db.execute(
            select(PlanDirection).order_by(
                PlanDirection.is_active.desc(),
                PlanDirection.created_at.asc(),
                PlanDirection.id.asc(),
            )
        )
        return list(res.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, direction_id: int) -> PlanDirection | None:
        return await db.get(PlanDirection, direction_id)

    @staticmethod
    async def create(
            db: AsyncSession,
            *,
            short_title: str,
            full_title: str | None,
            is_active: bool,
            created_by_user_id: int | None,
            # name: str | None = None,
    ) -> PlanDirection:
        short_title = (short_title or "").strip()
        if not short_title:
            raise ValueError("short_title обязателен")

        full_title = (full_title or "").strip() or None
        # name_val = short_title

        obj = PlanDirection(
            # name=name_val,
            short_title=short_title,
            full_title=full_title,
            is_active=bool(is_active),
            created_by_user_id=created_by_user_id,
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def set_active(
            db: AsyncSession,
            *,
            direction_id: int,
            is_active: bool,
    ) -> bool:
        res = await db.execute(
            update(PlanDirection)
            .where(PlanDirection.id == direction_id)
            .values(is_active=bool(is_active))
        )
        return (res.rowcount or 0) > 0

    @staticmethod
    async def delete(db: AsyncSession, *, direction_id: int) -> bool:
        res = await db.execute(
            delete(PlanDirection).where(PlanDirection.id == direction_id)
        )
        return (res.rowcount or 0) > 0


# =========================================================
# Templates (Образцы планов)
# =========================================================
class PlanTemplateRepo:
    @staticmethod
    async def list_all(db: AsyncSession) -> list[PlanTemplate]:
        res = await db.execute(
            select(PlanTemplate).order_by(
                PlanTemplate.is_active.desc(),
                PlanTemplate.created_at.desc(),
                PlanTemplate.id.desc(),
            )
        )
        return list(res.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, template_id: int) -> PlanTemplate | None:
        return await db.get(PlanTemplate, template_id)

    @staticmethod
    async def get_active(db: AsyncSession) -> PlanTemplate | None:
        res = await db.execute(
            select(PlanTemplate)
            .where(PlanTemplate.is_active.is_(True))
            .order_by(desc(PlanTemplate.created_at), desc(PlanTemplate.id))
            .limit(1)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def create(
            db: AsyncSession,
            *,
            name: str,
            academic_year: str | None,
            created_by_user_id: int | None,
            is_active: bool = False,
    ) -> PlanTemplate:
        name_val = (name or "").strip()
        if not name_val:
            raise ValueError("name обязателен")

        obj = PlanTemplate(
            name=name_val,
            academic_year=(academic_year or "").strip() or None,
            is_active=bool(is_active),
            created_by_user_id=created_by_user_id,
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def set_active(db: AsyncSession, *, template_id: int) -> bool:
        """
        Делает активным один шаблон (глобально).
        """
        await db.execute(update(PlanTemplate).values(is_active=False))
        res = await db.execute(
            update(PlanTemplate)
            .where(PlanTemplate.id == template_id)
            .values(is_active=True)
        )
        return (res.rowcount or 0) > 0

    @staticmethod
    async def delete_template(db: AsyncSession, *, template_id: int) -> bool:
        res = await db.execute(delete(PlanTemplate).where(PlanTemplate.id == template_id))
        return (res.rowcount or 0) > 0

    @staticmethod
    async def get_active_or_latest(db: AsyncSession) -> PlanTemplate | None:
        # активный
        res = await db.execute(
            select(PlanTemplate)
            .where(PlanTemplate.is_active.is_(True))
            .order_by(desc(PlanTemplate.created_at), desc(PlanTemplate.id))
            .limit(1)
        )
        tpl = res.scalar_one_or_none()
        if tpl is not None:
            return tpl

        # иначе — последний созданный
        res = await db.execute(
            select(PlanTemplate)
            .order_by(desc(PlanTemplate.created_at), desc(PlanTemplate.id))
            .limit(1)
        )
        return res.scalar_one_or_none()


# =========================================================
# Template Rows 4 (таблица на 4 колонки в твоём шаблоне)
# control_object / risk_text / decision_text (+ row_order)
# =========================================================
class PlanTemplateRow4Repo:
    @staticmethod
    async def _get_tpl_dir_id(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
            create_if_missing: bool = False,
    ) -> int | None:
        tpl_dir_id = await db.scalar(
            select(PlanTemplateDirection.id).where(
                PlanTemplateDirection.template_id == template_id,
                PlanTemplateDirection.direction_id == direction_id,
            )
        )
        if tpl_dir_id:
            return int(tpl_dir_id)

        if not create_if_missing:
            return None

        td = PlanTemplateDirection(
            template_id=template_id,
            direction_id=direction_id,
            sort_order=1,  # можно потом выставить правильно
        )
        db.add(td)
        await db.flush()
        return int(td.id)

    @staticmethod
    async def list_rows(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
    ) -> list[PlanTemplateRow4]:
        tpl_dir_id = await PlanTemplateRow4Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id
        )
        if not tpl_dir_id:
            return []

        res = await db.execute(
            select(PlanTemplateRow4)
            .where(PlanTemplateRow4.template_direction_id == tpl_dir_id)
            .order_by(PlanTemplateRow4.row_order.asc(), PlanTemplateRow4.id.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, row_id: int) -> PlanTemplateRow4 | None:
        return await db.get(PlanTemplateRow4, row_id)

    @staticmethod
    async def max_row_order(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
    ) -> int:
        tpl_dir_id = await PlanTemplateRow4Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id
        )
        if not tpl_dir_id:
            return 0

        val = await db.scalar(
            select(func.max(PlanTemplateRow4.row_order))
            .where(PlanTemplateRow4.template_direction_id == tpl_dir_id)
        )
        return int(val or 0)

    @staticmethod
    async def create(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
            row_order: int,
            control_object: str,
            risk_text: str | None,
            decision_text: str | None,
            no: str | None = None,
    ) -> PlanTemplateRow4:
        # важно: если направления в шаблоне ещё нет — создаём
        tpl_dir_id = await PlanTemplateRow4Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id, create_if_missing=True
        )
        assert tpl_dir_id is not None

        obj = PlanTemplateRow4(
            template_direction_id=tpl_dir_id,
            row_order=int(row_order),
            no=(no or "").strip() or None,
            control_object=(control_object or "").strip(),
            risk_text=(risk_text or "").strip() or None,
            decision_text=(decision_text or "").strip() or None,
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def delete_row(db: AsyncSession, *, row_id: int) -> bool:
        res = await db.execute(delete(PlanTemplateRow4).where(PlanTemplateRow4.id == row_id))
        return (res.rowcount or 0) > 0

    @staticmethod
    async def delete_all_for_template_direction(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
    ) -> int:
        tpl_dir_id = await PlanTemplateRow4Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id
        )
        if not tpl_dir_id:
            return 0

        res = await db.execute(
            delete(PlanTemplateRow4).where(PlanTemplateRow4.template_direction_id == tpl_dir_id)
        )
        return int(res.rowcount or 0)


# =========================================================
# Template Rows 11 (на будущее, если нужно)
# =========================================================
class PlanTemplateRow11Repo:
    @staticmethod
    async def _get_tpl_dir_id(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
            create_if_missing: bool = False,
    ) -> int | None:
        tpl_dir_id = await db.scalar(
            select(PlanTemplateDirection.id).where(
                PlanTemplateDirection.template_id == template_id,
                PlanTemplateDirection.direction_id == direction_id,
            )
        )
        if tpl_dir_id:
            return int(tpl_dir_id)

        if not create_if_missing:
            return None

        td = PlanTemplateDirection(
            template_id=template_id,
            direction_id=direction_id,
            sort_order=1,
        )
        db.add(td)
        await db.flush()
        return int(td.id)

    @staticmethod
    async def list_rows(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
    ) -> list[PlanTemplateRow11]:
        tpl_dir_id = await PlanTemplateRow11Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id
        )
        if not tpl_dir_id:
            return []

        res = await db.execute(
            select(PlanTemplateRow11)
            .where(PlanTemplateRow11.template_direction_id == tpl_dir_id)
            .order_by(PlanTemplateRow11.row_order.asc(), PlanTemplateRow11.id.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def max_row_order(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
    ) -> int:
        tpl_dir_id = await PlanTemplateRow11Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id
        )
        if not tpl_dir_id:
            return 0

        val = await db.scalar(
            select(func.max(PlanTemplateRow11.row_order))
            .where(PlanTemplateRow11.template_direction_id == tpl_dir_id)
        )
        return int(val or 0)

    @staticmethod
    async def create(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
            row_order: int,
            topic: str,
            goal: str | None,
            control_object: str | None,
            control_type: str | None,
            methods: str | None,
            deadlines: str | None,
            responsibles: str | None,
            review_place: str | None,
            management_decision: str | None,
            second_control: str | None,
    ) -> PlanTemplateRow11:
        tpl_dir_id = await PlanTemplateRow11Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id, create_if_missing=True
        )
        assert tpl_dir_id is not None

        obj = PlanTemplateRow11(
            template_direction_id=tpl_dir_id,
            row_order=int(row_order),

            topic=(topic or "").strip(),
            goal=(goal or "").strip() or None,
            control_object=(control_object or "").strip() or None,
            control_type=(control_type or "").strip() or None,
            methods=(methods or "").strip() or None,
            deadlines=(deadlines or "").strip() or None,
            responsibles=(responsibles or "").strip() or None,
            review_place=(review_place or "").strip() or None,
            management_decision=(management_decision or "").strip() or None,
            second_control=(second_control or "").strip() or None,
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def delete_row(db: AsyncSession, *, row_id: int) -> bool:
        res = await db.execute(delete(PlanTemplateRow11).where(PlanTemplateRow11.id == row_id))
        return (res.rowcount or 0) > 0

    @staticmethod
    async def delete_all_for_template_direction(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
    ) -> int:
        tpl_dir_id = await PlanTemplateRow11Repo._get_tpl_dir_id(
            db, template_id=template_id, direction_id=direction_id
        )
        if not tpl_dir_id:
            return 0

        res = await db.execute(
            delete(PlanTemplateRow11).where(PlanTemplateRow11.template_direction_id == tpl_dir_id)
        )
        return int(res.rowcount or 0)


class PlanTemplateDirectionRepo:
    @staticmethod
    async def get_or_create(
            db: AsyncSession,
            *,
            template_id: int,
            direction_id: int,
    ) -> PlanTemplateDirection:
        td = await db.scalar(
            select(PlanTemplateDirection).where(
                PlanTemplateDirection.template_id == template_id,
                PlanTemplateDirection.direction_id == direction_id,
            )
        )
        if td:
            return td

        td = PlanTemplateDirection(
            template_id=template_id,
            direction_id=direction_id,
            sort_order=1,
        )
        db.add(td)
        await db.flush()  # получаем td.id
        return td


class PlanTemplateReplaceRepo:
    @staticmethod
    async def replace_rows4(
            db: AsyncSession,
            *,
            template_direction_id: int,
            rows: list[dict],
    ) -> int:
        # удалить старые
        await db.execute(
            delete(PlanTemplateRow4).where(
                PlanTemplateRow4.template_direction_id == template_direction_id
            )
        )

        # вставить новые
        for r in rows:
            db.add(PlanTemplateRow4(
                template_direction_id=template_direction_id,
                row_order=r["row_order"],
                control_object=r.get("control_object", "") or "",
                risk_text=r.get("risk_text"),
                decision_text=r.get("decision_text"),
            ))
        await db.flush()
        return len(rows)

    @staticmethod
    async def replace_rows11(
            db: AsyncSession,
            *,
            template_direction_id: int,
            rows: list[dict],
    ) -> int:
        await db.execute(
            delete(PlanTemplateRow11).where(
                PlanTemplateRow11.template_direction_id == template_direction_id
            )
        )

        for r in rows:
            db.add(PlanTemplateRow11(
                template_direction_id=template_direction_id,
                row_order=r["row_order"],
                topic=r.get("topic", "") or "",
                goal=r.get("goal"),
                control_object=r.get("control_object"),
                control_type=r.get("control_type"),
                methods=r.get("methods"),
                deadlines=r.get("deadlines"),
                responsibles=r.get("responsibles"),
                review_place=r.get("review_place"),
                management_decision=r.get("management_decision"),
                second_control=r.get("second_control"),
            ))
        await db.flush()
        return len(rows)
