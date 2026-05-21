# app/modules/reports/services/user_template_service.py

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.enums import ReportType, TaskDocumentSource, DocumentType
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.models_template_reports import UserReportTemplate
from app.modules.reports.repositories.template_repo import TemplateReportRepo
from app.modules.reports.repositories.user_template_repo import UserReportTemplateRepo
from app.modules.reports.utils.checking_notebooks_defaults import CHECKING_NOTEBOOKS_INFO_FIELDS, \
    CHECKING_NOTEBOOKS_DEFAULT_CRITERIA, CHECKING_NOTEBOOKS_RATING


class UserReportTemplateService:
    """
    Сервис личных шаблонов исполнителя.

    Здесь бизнес-логика:
    - проверка report_code;
    - нормализация текста;
    - создание/редактирование личных шаблонов;
    - защита от чужих шаблонов.
    """

    @staticmethod
    def get_constructor_page_context(
            *,
            report_code: str | None,
            month_item_id: str | None = None,
            selected_report_id: str | None = None,
    ) -> dict:
        report_code = report_code or ReportType.LESSON_OBSERVATION.value

        if report_code == ReportType.CHECKING_NOTEBOOKS_TABLE.value:
            return {
                "template_name": "staff/reports/user_templates/constructors/checking_notebooks_table.html",
                "report_code": report_code,
                "report_label": "Дәптер тексеру кестесі",
                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,
                "info_fields": CHECKING_NOTEBOOKS_INFO_FIELDS,
                "default_criteria": CHECKING_NOTEBOOKS_DEFAULT_CRITERIA,
                "rating": CHECKING_NOTEBOOKS_RATING,
            }

        return {
            "template_name": "staff/reports/user_templates/constructors/lesson_observation.html",
            "report_code": ReportType.LESSON_OBSERVATION.value,
            "report_label": "Сабақты бақылау парағы",
            "month_item_id": month_item_id,
            "selected_report_id": selected_report_id,
        }

    @classmethod
    async def list_my_templates(
            cls,
            db: AsyncSession,
            *,
            owner_user_id: int,
            report_code: str | None = None,
    ) -> list[UserReportTemplate]:
        """
        Получить личные шаблоны текущего пользователя.

        Можно фильтровать по типу отчета.
        """

        if report_code:
            cls._validate_report_code(report_code)

        return await UserReportTemplateRepo.list_user_templates(
            db,
            owner_user_id=owner_user_id,
            report_code=report_code,
        )

    @classmethod
    async def create_my_template(
            cls,
            db: AsyncSession,
            *,
            owner_user_id: int,
            report_code: str,
            title: str,
            description: str | None,
            schema_json: str | None,
    ) -> UserReportTemplate:
        """
        Создать личный шаблон пользователя.

        schema_json приходит из формы как JSON-строка.
        В БД сохраняем dict, потому что поле JSONB.
        """

        import json

        report_code = cls._validate_report_code(report_code)
        title = cls._require_text(title, "Укажите название шаблона.")
        description = cls._clean(description)
        schema_json = cls._clean(schema_json)

        if not schema_json:
            raise ValueError("Добавьте хотя бы один раздел и критерий.")

        try:
            schema_data = json.loads(schema_json)

            # очистка schema
            info_fields = schema_data.get("info_fields") or []

            schema_data["info_fields"] = [
                f for f in info_fields
                if f not in ["feedback", "suggestion_control"]
            ]
        except json.JSONDecodeError:
            raise ValueError("Некорректная структура шаблона.")

        if not isinstance(schema_data, dict):
            raise ValueError("Структура шаблона должна быть объектом.")

        # Проверка структуры зависит от типа отчета
        if report_code == ReportType.CHECKING_NOTEBOOKS_TABLE.value:
            columns = (
                    schema_data.get("columns")
                    or schema_data.get("fields")
                    or schema_data.get("notebook_fields")
                    or schema_data.get("info_fields")
                    or []
            )

            columns = [
                column for column in columns
                if isinstance(column, str) and column.strip()
            ]

            if not columns:
                raise ValueError("Добавьте хотя бы одну колонку или поле.")

            schema_data["columns"] = columns

        else:
            sections = schema_data.get("sections") or []

            if not sections:
                raise ValueError("Добавьте хотя бы один раздел.")

            has_criteria = any(
                section.get("criteria")
                for section in sections
                if isinstance(section, dict)
            )

            if not has_criteria:
                raise ValueError("Добавьте хотя бы один критерий.")

        report_type = await UserReportTemplateRepo.get_report_type_by_code(
            db,
            report_code=report_code,
        )

        report_type_id = report_type.id if report_type else None

        report_label = (
            report_type.name_kz or report_type.name_ru or report_type.code
            if report_type
            else cls._get_enum_label(report_code)
        )

        try:
            template = await UserReportTemplateRepo.create_user_template(
                db,
                owner_user_id=owner_user_id,
                report_type_id=report_type_id,
                report_code=report_code,
                report_label=report_label,
                title=title,
                description=description,
                schema_json=schema_data,  # dict, не строка
            )

            await db.commit()
            return template

        except IntegrityError:
            await db.rollback()
            raise ValueError("Шаблон с таким названием уже существует.")

    @classmethod
    async def update_my_template(
            cls,
            db: AsyncSession,
            *,
            template_id: int,
            owner_user_id: int,
            title: str,
            description: str | None,
            schema_json: str | None,
    ) -> UserReportTemplate:
        """
        Обновить личный шаблон исполнителя.

        schema_json приходит из формы как JSON-строка.
        В БД сохраняем dict, потому что поле JSONB.
        """

        import json

        template = await UserReportTemplateRepo.get_user_template(
            db,
            template_id=template_id,
            owner_user_id=owner_user_id,
        )

        if not template:
            raise ValueError("Шаблон не найден или недоступен.")

        title = cls._require_text(title, "Укажите название шаблона.")
        description = cls._clean(description)
        schema_json = cls._clean(schema_json)

        if not schema_json:
            raise ValueError("Добавьте хотя бы один раздел и критерий.")

        try:
            schema_data = json.loads(schema_json)

            # очистка schema
            info_fields = schema_data.get("info_fields") or []

            schema_data["info_fields"] = [
                f for f in info_fields
                if f not in ["feedback", "suggestion_control"]
            ]
        except json.JSONDecodeError:
            raise ValueError("Некорректная структура шаблона.")

        if not isinstance(schema_data, dict):
            raise ValueError("Структура шаблона должна быть объектом.")

        if template.report_code == ReportType.CHECKING_NOTEBOOKS_TABLE.value:
            columns = (
                    schema_data.get("columns")
                    or schema_data.get("fields")
                    or schema_data.get("notebook_fields")
                    or schema_data.get("info_fields")
                    or []
            )

            columns = [
                column.strip()
                for column in columns
                if isinstance(column, str) and column.strip()
            ]

            if not columns:
                raise ValueError("Добавьте хотя бы одну колонку или поле.")

            schema_data["columns"] = columns

        else:
            sections = schema_data.get("sections") or []

            if not sections:
                raise ValueError("Добавьте хотя бы один раздел.")

            has_criteria = any(
                section.get("criteria")
                for section in sections
                if isinstance(section, dict)
            )

            if not has_criteria:
                raise ValueError("Добавьте хотя бы один критерий.")

        try:
            template = await UserReportTemplateRepo.update_user_template(
                db,
                template=template,
                title=title,
                description=description,
                schema_json=schema_data,
            )

            await db.commit()
            return template

        except IntegrityError:
            await db.rollback()
            raise ValueError("Шаблон с таким названием уже существует.")

    @classmethod
    async def delete_my_template(
            cls,
            db: AsyncSession,
            *,
            template_id: int,
            owner_user_id: int,
    ) -> None:
        """
        Отключить личный шаблон пользователя.
        """

        template = await UserReportTemplateRepo.get_user_template(
            db,
            template_id=template_id,
            owner_user_id=owner_user_id,
        )

        if not template:
            raise ValueError("Шаблон не найден или недоступен.")

        await UserReportTemplateRepo.deactivate_user_template(
            db,
            template=template,
        )
        await db.commit()

    @classmethod
    async def get_my_template(
            cls,
            db: AsyncSession,
            *,
            template_id: int,
            owner_user_id: int,
    ) -> UserReportTemplate:
        """
        Получить один шаблон для редактирования/просмотра.
        """

        template = await UserReportTemplateRepo.get_user_template(
            db,
            template_id=template_id,
            owner_user_id=owner_user_id,
        )

        if not template:
            raise ValueError("Шаблон не найден или недоступен.")

        return template

    @classmethod
    async def get_my_template_edit_page_data(
            cls,
            db: AsyncSession,
            *,
            template_id: int,
            owner_user_id: int,
    ) -> dict:
        """
        Универсальный метод для редактирования/просмотра пользовательских шаблонов.
        """

        template = await cls.get_my_template(
            db,
            template_id=template_id,
            owner_user_id=owner_user_id,
        )

        schema = template.schema_json or {}

        if not template.report_type:
            raise ValueError("У шаблона не задан тип отчета")

        report_type_code = template.report_type.code

        template_path = (
            "staff/reports/user_templates/constructors/"
            f"{report_type_code}.html"
        )

        return {
            "template": template,
            "schema": schema,
            "report_type_code": report_type_code,
            "template_path": template_path,

            # универсальные данные (работают для всех типов)
            "rating": schema.get("rating") or {},
            "criteria": schema.get("criteria") or [],
            "sections": schema.get("sections") or [],
            "info_fields": schema.get("info_fields") or schema.get("columns") or [],
        }

    @classmethod
    async def apply_my_template(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user_id: int,
            template_id: int,
    ) -> TaskExecutionDocument:

        # 1. Получаем только шаблон текущего пользователя
        template = await UserReportTemplateRepo.get_user_template(
            db,
            template_id=template_id,
            owner_user_id=user_id,
        )

        if not template:
            raise ValueError("Шаблон не найден или недоступен.")

        # 2. Ищем документ отчета
        document = await TemplateReportRepo.get_template_document(
            db,
            selected_report_id=selected_report_id,
            user_id=user_id,
        )

        # 3. Если документа нет — создаем
        if not document:
            document = TaskExecutionDocument(
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                report_type_id=template.report_type_id,
                report_code=template.report_code,
                report_label=template.report_label,
                document_type=DocumentType.REPORT,
                source=TaskDocumentSource.TEMPLATE,
                schema_json=template.schema_json or {},
            )

            db.add(document)
            await db.flush()

        # 4. Проверяем, что документ относится к выбранной задаче
        if document.month_item_id != month_item_id:
            raise ValueError("Документ не относится к выбранной задаче.")

        # 5. Главная проверка типа отчета
        if document.report_type_id and template.report_type_id:
            if document.report_type_id != template.report_type_id:
                raise ValueError(
                    "Шаблон не соответствует типу отчета. "
                    f"document.report_type_id={document.report_type_id}, "
                    f"template.report_type_id={template.report_type_id}"
                )

        # 6. Дополнительная проверка по report_code, если оба заполнены
        document_report_code = (document.report_code or "").strip()
        template_report_code = (template.report_code or "").strip()

        if document_report_code and template_report_code:
            if document_report_code != template_report_code:
                raise ValueError(
                    "Шаблон не соответствует типу отчета. "
                    f"document.report_code={document_report_code}, "
                    f"template.report_code={template_report_code}"
                )

        # 7. Если у документа пустые служебные поля — заполняем из шаблона
        if not document.report_type_id:
            document.report_type_id = template.report_type_id

        if not document.report_code:
            document.report_code = template.report_code

        if not document.report_label:
            document.report_label = template.report_label

        document.source = TaskDocumentSource.TEMPLATE
        document.document_type = DocumentType.REPORT

        # 8. Применяем шаблон к документу
        document = await TemplateReportRepo.apply_custom_template_to_document(
            db,
            document=document,
            user_template=template,
        )

        await db.commit()
        await db.refresh(document)

        return document

    @staticmethod
    def _clean(value) -> str | None:
        if value is None:
            return None

        value = str(value).strip()
        return value or None

    @classmethod
    def _require_text(cls, value, error_message: str) -> str:
        value = cls._clean(value)
        if not value:
            raise ValueError(error_message)
        return value

    @staticmethod
    def _validate_report_code(report_code: str) -> str:
        report_code = str(report_code or "").strip()

        valid_codes = {item.value for item in ReportType.__members__.values()}
        if report_code not in valid_codes:
            raise ValueError("Недопустимый тип отчета.")

        return report_code

    @staticmethod
    def _get_enum_label(report_code: str) -> str:
        for item in ReportType.__members__.values():
            if item.value == report_code:
                return item.label_kz
        return report_code
