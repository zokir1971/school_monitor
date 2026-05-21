# app/modules/reports/repositories/user_template_repo.py

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.reports.models_documents import ReportTypeModel
from app.modules.reports.models_template_reports import UserReportTemplate


class UserReportTemplateRepo:
    """
    Репозиторий личных шаблонов исполнителя.

    Здесь только работа с БД:
    - создать личный шаблон;
    - получить шаблон;
    - получить список шаблонов пользователя;
    - обновить шаблон;
    - отключить шаблон.
    """

    @classmethod
    async def get_report_type_by_code(
            cls,
            db: AsyncSession,
            *,
            report_code: str,
    ) -> ReportTypeModel | None:
        """
        Найти тип отчета в report_types по code.

        report_type_id используем как удобную связь,
        но главный стабильный ключ всё равно report_code.
        """

        stmt = (
            select(ReportTypeModel)
            .where(
                ReportTypeModel.code == report_code,
                ReportTypeModel.is_active.is_(True),
            )
        )

        return await db.scalar(stmt)

    @classmethod
    async def list_user_templates(
            cls,
            db: AsyncSession,
            *,
            owner_user_id: int,
            report_code: str | None = None,
    ) -> list[UserReportTemplate]:
        """
        Получить активные личные шаблоны пользователя.

        Если report_code передан — вернет шаблоны только для этого типа отчета.
        """

        stmt = (
            select(UserReportTemplate)
            .where(
                UserReportTemplate.owner_user_id == owner_user_id,
                UserReportTemplate.is_active.is_(True),
            )
            .options(selectinload(UserReportTemplate.report_type))
            .order_by(UserReportTemplate.updated_at.desc(), UserReportTemplate.id.desc())
        )

        if report_code:
            stmt = stmt.where(UserReportTemplate.report_code == report_code)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_user_template(
            cls,
            db: AsyncSession,
            *,
            template_id: int,
            owner_user_id: int,
    ) -> UserReportTemplate | None:
        """
        Получить личный шаблон пользователя по id.

        owner_user_id обязателен, чтобы пользователь не мог открыть чужой шаблон.
        """

        stmt = (
            select(UserReportTemplate)
            .where(
                UserReportTemplate.id == template_id,
                UserReportTemplate.owner_user_id == owner_user_id,
                UserReportTemplate.is_active.is_(True),
            )
            .options(selectinload(UserReportTemplate.report_type))
        )

        return await db.scalar(stmt)

    @staticmethod
    async def create_user_template(
            db: AsyncSession,
            *,
            owner_user_id: int,
            report_type_id: int | None,
            report_code: str,
            report_label: str,
            title: str,
            description: str | None,
            schema_json: dict | None,
    ) -> UserReportTemplate:
        """
        Создать личный шаблон исполнителя.

        schema_json должен быть dict, потому что в БД поле JSONB.
        """

        template = UserReportTemplate(
            owner_user_id=owner_user_id,
            report_type_id=report_type_id,
            report_code=report_code,
            report_label=report_label,
            title=title,
            description=description,
            schema_json=schema_json,
        )

        db.add(template)
        await db.flush()
        return template

    @classmethod
    async def update_user_template(
            cls,
            db: AsyncSession,
            *,
            template: UserReportTemplate,
            title: str,
            description: str | None,
            schema_json: dict | None,
    ) -> UserReportTemplate:
        """
        Обновить личный шаблон.

        Уже примененные к задачам документы не меняются,
        потому что в TaskExecutionDocument хранится snapshot-копия.
        """

        template.title = title
        template.description = description
        template.schema_json = schema_json

        await db.flush()
        return template

    @classmethod
    async def deactivate_user_template(
            cls,
            db: AsyncSession,
            *,
            template: UserReportTemplate,
    ) -> None:
        """
        Мягко удалить личный шаблон.

        Физически строку не удаляем, чтобы не ломать историю.
        """

        template.is_active = False
        await db.flush()

    @classmethod
    async def get_user_template_by_id(
            cls,
            db: AsyncSession,
            *,
            template_id: int,
    ) -> UserReportTemplate | None:
        """
        Получить активный личный шаблон по id.

        Проверку owner_user_id делаем в сервисе,
        потому что там бизнес-логика доступа.
        """

        stmt = (
            select(UserReportTemplate)
            .where(
                UserReportTemplate.id == template_id,
                UserReportTemplate.is_active.is_(True),
            )
            .options(selectinload(UserReportTemplate.report_type))
        )

        return await db.scalar(stmt)
