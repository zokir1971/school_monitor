# app/modules/reports/services/lesson_observation_service.py

from __future__ import annotations

from app.core.i18n import resolve_language
from app.core.report_pdf_i18n import select_document_language, saved_report_language, report_pdf_context

import logging
from dataclasses import fields
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from playwright.async_api import async_playwright
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.factory import get_storage
from app.core.storage.school_storage import SchoolStorageService
from app.modules.reports.enums import (
    DocumentType,
    ReportTemplateMode,
    ReportType,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.models_template_reports import LessonObservationReport
from app.modules.reports.repositories.execution_document_repo import (
    ExecutionDocumentRepo,
)
from app.modules.reports.repositories.lesson_observation_repo import (
    LessonObservationRepo,
)
from app.modules.reports.repositories.report_verify_repo import (
    ReportVerifyRepo,
)
from app.modules.reports.repositories.report_assignment_repo import (
    ReportAssignmentRepo,
)
from app.modules.reports.schemas.lesson_observation_dto import (
    LessonObservationFillDTO,
    LessonObservationFormDTO,
    LessonObservationInfoDTO,
)
from app.modules.reports.services.base_report_service import (
    BaseReportService,
)
from app.modules.reports.services.report_template_resolver import (
    ReportTemplateResolver,
)
from app.modules.reports.utils.parsing import parse_optional_datetime
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.users.models import User

logger = logging.getLogger(__name__)


class LessonObservationService(BaseReportService):
    """
    Единый сервис листа наблюдения новой архитектуры.

    Один flow обслуживает системный и пользовательский шаблоны.

    Основные правила:
    - GET /fill является read-only;
    - TaskExecutionDocument может отсутствовать до первого Save/Complete;
    - существующий document.schema_json является неизменяемым snapshot;
    - новый документ создается только при Save/Complete;
    - system/user отличаются только источником schema.
    """

    # =========================================================
    # COMMON INFO HELPERS
    # =========================================================

    @staticmethod
    def filter_lesson_observation_info_fields(
            data: dict[str, Any],
    ) -> dict[str, Any]:
        allowed_fields = {
            field.name
            for field in fields(LessonObservationInfoDTO)
        }

        return {
            key: value
            for key, value in data.items()
            if key in allowed_fields
        }

    @staticmethod
    def _fill_if_empty(
            data: dict[str, Any],
            key: str,
            value: Any,
    ) -> None:
        if data.get(key) in (None, ""):
            data[key] = value or ""

    @staticmethod
    def _format_datetime_for_input(
            value: datetime | None,
    ) -> str:
        if value is None:
            return ""

        return value.strftime("%Y-%m-%dT%H:%M")

    @classmethod
    def _build_info_from_report(
            cls,
            report: LessonObservationReport,
    ) -> tuple[dict[str, Any], dict[str, Any], int]:
        criteria_data = report.criteria_scores or {}

        # Копия нужна, чтобы не мутировать JSON ORM-объекта.
        saved_info = dict(
            criteria_data.get("info") or {}
        )

        cls._fill_if_empty(
            saved_info,
            "teacher_full_name",
            report.teacher_full_name,
        )
        cls._fill_if_empty(
            saved_info,
            "teacher_position",
            report.teacher_position,
        )
        cls._fill_if_empty(
            saved_info,
            "teacher_category",
            report.teacher_category,
        )
        cls._fill_if_empty(
            saved_info,
            "teacher_subject",
            report.teacher_subject,
        )

        cls._fill_if_empty(
            saved_info,
            "observer_full_name",
            report.observer_full_name,
        )
        cls._fill_if_empty(
            saved_info,
            "observer_position",
            report.observer_position,
        )

        cls._fill_if_empty(
            saved_info,
            "school_name",
            report.school_name,
        )
        cls._fill_if_empty(
            saved_info,
            "class_name",
            report.class_name,
        )
        cls._fill_if_empty(
            saved_info,
            "group_name",
            report.group_name,
        )
        cls._fill_if_empty(
            saved_info,
            "lesson_datetime",
            cls._format_datetime_for_input(
                report.lesson_datetime
            ),
        )

        cls._fill_if_empty(
            saved_info,
            "theme",
            report.theme,
        )
        cls._fill_if_empty(
            saved_info,
            "learning_objectives",
            report.learning_objectives,
        )
        cls._fill_if_empty(
            saved_info,
            "lesson_objectives_1",
            report.lesson_objectives_1,
        )
        cls._fill_if_empty(
            saved_info,
            "lesson_objectives_2",
            report.lesson_objectives_2,
        )
        cls._fill_if_empty(
            saved_info,
            "lesson_objectives_3",
            report.lesson_objectives_3,
        )

        cls._fill_if_empty(
            saved_info,
            "feedback",
            report.feedback,
        )
        cls._fill_if_empty(
            saved_info,
            "suggestion_control",
            report.suggestion_control,
        )

        scores = criteria_data.get("scores") or {}

        total_score = (
            criteria_data.get("total_score")
            or report.total
            or 0
        )

        return (
            saved_info,
            scores,
            cls.parse_int(total_score),
        )

    @staticmethod
    def _build_initial_info_from_context(
            *,
            context,
            user: User,
    ) -> tuple[dict[str, Any], dict[str, Any], int]:
        saved_info = {
            "teacher_full_name": context.teacher_full_name,
            "teacher_position": context.teacher_position,
            "teacher_category": context.teacher_category,
            "teacher_subject": context.teacher_subject,

            "observer_full_name": user.full_name or "",
            "observer_position": context.observer_position,

            "school_name": context.school_name,

            # Заполняются пользователем.
            "class_name": "",
            "group_name": "",
            "lesson_datetime": "",

            "theme": "",
            "learning_objectives": "",
            "lesson_objectives_1": "",
            "lesson_objectives_2": "",
            "lesson_objectives_3": "",

            "feedback": "",
            "suggestion_control": "",
        }

        return saved_info, {}, 0

    # =========================================================
    # GET / FILL
    # =========================================================

    @classmethod
    async def get_lesson_observation_fill_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
            template_id: int | None = None,
    ) -> LessonObservationFillDTO:
        """
        Подготовить страницу листа наблюдения.

        Производительность:
        - основной контекст получаем одним SQL через get_fill_context();
        - существующий document -> resolver не вызывается;
        - system preview -> resolver работает из памяти, без SQL;
        - user preview -> максимум один дополнительный SELECT шаблона.
        """

        school_id, staff_member_id = (
            cls.require_user_context(user)
        )

        context = await LessonObservationRepo.get_fill_context(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
        )

        if context is None:
            raise ValueError(
                "Отчет не найден, не относится к выбранной задаче "
                "или не назначен текущему сотруднику."
            )

        if (
                context.report_code
                != ReportType.LESSON_OBSERVATION.value
        ):
            raise ValueError(
                "Выбранный отчет не является листом наблюдения."
            )

        selected_report = context.selected_report

        if selected_report.target_kind != "teacher":
            raise ValueError(
                "Для листа наблюдения должен быть выбран учитель."
            )

        document = context.document
        report = context.report

        # =========================================================
        # TEMPLATE / SCHEMA
        # =========================================================

        if document is not None and document.schema_json:
            # Snapshot документа — источник истины после первого save.
            schema = document.schema_json or {}

        else:
            if document is not None:
                raw_mode = (
                    document.template_mode
                    or (
                        ReportTemplateMode.CUSTOM.value
                        if document.custom_template_id is not None
                        else ReportTemplateMode.STANDARD.value
                    )
                )

                resolved_template_id = (
                    document.custom_template_id
                    if document.custom_template_id is not None
                    else template_id
                )

            elif template_id is not None:
                raw_mode = ReportTemplateMode.CUSTOM
                resolved_template_id = template_id

            else:
                raw_mode = ReportTemplateMode.STANDARD
                resolved_template_id = None

            resolved = await ReportTemplateResolver.resolve(
                db,
                report_code=context.report_code,
                template_mode=raw_mode,
                owner_user_id=user.id,
                template_id=resolved_template_id,
            )

            schema = resolved.schema

        if not schema:
            raise ValueError(
                "Для листа наблюдения не найдена структура шаблона."
            )

        # =========================================================
        # FORM DATA
        # =========================================================

        if report is not None:
            saved_info, scores, total_score = (
                cls._build_info_from_report(report)
            )

            # Если старый отчет не содержит части шапки,
            # заполняем ее актуальным серверным контекстом.
            cls._fill_if_empty(
                saved_info,
                "teacher_full_name",
                context.teacher_full_name,
            )
            cls._fill_if_empty(
                saved_info,
                "teacher_position",
                context.teacher_position,
            )
            cls._fill_if_empty(
                saved_info,
                "teacher_category",
                context.teacher_category,
            )
            cls._fill_if_empty(
                saved_info,
                "teacher_subject",
                context.teacher_subject,
            )
            cls._fill_if_empty(
                saved_info,
                "observer_full_name",
                user.full_name,
            )
            cls._fill_if_empty(
                saved_info,
                "observer_position",
                context.observer_position,
            )
            cls._fill_if_empty(
                saved_info,
                "school_name",
                context.school_name,
            )

        else:
            saved_info, scores, total_score = (
                cls._build_initial_info_from_context(
                    context=context,
                    user=user,
                )
            )

        info = LessonObservationInfoDTO(
            **cls.filter_lesson_observation_info_fields(
                saved_info
            )
        )

        return LessonObservationFillDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,

            schema=schema,
            report_code=context.report_code,
            report_label=context.report_label,

            info=info,
            scores=scores,
            total_score=total_score,

            report=report,
            document=document,
        )

    # =========================================================
    # SAVE / COMPLETE
    # =========================================================

    @classmethod
    async def save_or_complete(
            cls,
            db: AsyncSession,
            *,
            request: Request,
            form,
            month_item_id: int,
            selected_report_id: int,
            user: User,
            templates,
            template_id: int | None = None,
    ) -> LessonObservationReport:
        """
        Сохранить черновик или подписать лист наблюдения.

        TaskExecutionDocument создается только здесь, то есть
        только после явного Save/Complete.
        """

        action = str(
            form.get("action") or "save"
        ).strip()

        if action not in {"save", "complete"}:
            raise ValueError(
                "Неподдерживаемое действие."
            )

        school_id, staff_member_id = (
            cls.require_user_context(user)
        )

        context = await LessonObservationRepo.get_fill_context(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
        )

        if context is None:
            raise ValueError(
                "Отчет не найден, не относится к выбранной задаче "
                "или не назначен текущему сотруднику."
            )

        if (
                context.report_code
                != ReportType.LESSON_OBSERVATION.value
        ):
            raise ValueError(
                "Выбранный отчет не является листом наблюдения."
            )

        selected_report = context.selected_report

        if selected_report.target_kind != "teacher":
            raise ValueError(
                "Для листа наблюдения должен быть выбран учитель."
            )

        document = context.document
        report = context.report

        if (
                report is not None
                and report.submitted_at is not None
        ):
            raise ValueError(
                "Отчет уже подписан. Редактирование запрещено."
            )

        document_language = select_document_language(
            form.get("document_language"), saved_report_language(report), resolve_language(request, user)
        )

        # =========================================================
        # TEMPLATE / DOCUMENT SNAPSHOT
        # =========================================================

        if document is not None and document.schema_json:
            schema = document.schema_json or {}

        else:
            if document is not None:
                raw_mode = (
                    document.template_mode
                    or (
                        ReportTemplateMode.CUSTOM.value
                        if document.custom_template_id is not None
                        else ReportTemplateMode.STANDARD.value
                    )
                )

                resolved_template_id = (
                    document.custom_template_id
                    if document.custom_template_id is not None
                    else template_id
                )

            elif template_id is not None:
                raw_mode = ReportTemplateMode.CUSTOM
                resolved_template_id = template_id

            else:
                raw_mode = ReportTemplateMode.STANDARD
                resolved_template_id = None

            resolved = await ReportTemplateResolver.resolve(
                db,
                report_code=context.report_code,
                template_mode=raw_mode,
                owner_user_id=user.id,
                template_id=resolved_template_id,
            )

            schema = resolved.schema

            if document is None:
                document = TaskExecutionDocument(
                    month_item_id=month_item_id,
                    report_type_id=selected_report.report_type_id,
                    selected_report_id=selected_report_id,

                    report_code=context.report_code,
                    report_label=(
                        resolved.report_label
                        or context.report_label
                    ),

                    document_type=DocumentType.REPORT,
                    status=TaskDocumentStatus.DRAFT,
                    source=TaskDocumentSource.GENERATED,

                    version=1,
                    is_current=True,
                    is_final=False,

                    title=(
                        resolved.template_title
                        or resolved.report_label
                        or context.report_label
                    ),

                    uploaded_by_user_id=user.id,

                    custom_template_id=resolved.user_template_id,
                    template_mode=resolved.template_mode.value,
                    schema_json=resolved.schema,
                )

                db.add(document)
                await db.flush()

            else:
                # Legacy document без snapshot нормализуем только
                # при явном Save/Complete.
                document.schema_json = resolved.schema
                document.template_mode = (
                    resolved.template_mode.value
                )
                document.custom_template_id = (
                    resolved.user_template_id
                )

        if not schema:
            raise ValueError(
                "Для листа наблюдения не найдена структура шаблона."
            )

        # =========================================================
        # DTO
        # =========================================================

        dto = cls._build_dto_from_form(
            form=form,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=document.id,
            user=user,
        )

        # Шапочные данные не доверяем форме:
        # они всегда берутся из серверного контекста.
        dto.staff_member_id = context.teacher_staff_id
        dto.observer_user_id = user.id

        dto.teacher_full_name = context.teacher_full_name
        dto.teacher_position = context.teacher_position
        dto.teacher_category = context.teacher_category
        dto.teacher_subject = context.teacher_subject

        dto.observer_full_name = user.full_name or ""
        dto.observer_position = context.observer_position
        dto.school_name = context.school_name

        report = await LessonObservationRepo.save_from_dto(
            db,
            dto=dto,
        )
        report.criteria_scores = {**(report.criteria_scores or {}), "document_language": document_language}


        await db.flush()
        await db.refresh(report)

        # =========================================================
        # STORAGE / SIGN
        # =========================================================

        storage_service = SchoolStorageService(
            storage=get_storage(),
        )

        new_object_key: str | None = None
        old_object_key: str | None = report.pdf_signed_file

        if action == "complete":
            report.submitted_at = datetime.now(
                timezone.utc
            )

            token = ReportSignatureService.create_token(
                report_type="lesson_observation",
                report_id=report.id,
                document_id=report.task_execution_document_id,
                total=report.total,
            )

            await ReportVerifyRepo.deactivate_old_signatures(
                db,
                report_type="lesson_observation",
                report_id=report.id,
                document_id=report.task_execution_document_id,
            )

            signature = await ReportVerifyRepo.create_signature_token(
                db,
                token=token,
                report_type="lesson_observation",
                report_id=report.id,
                document_id=report.task_execution_document_id,
            )

            verify_url = str(
                request.url_for(
                    "report_verify_by_code_page",
                    code=signature.code,
                )
            )

            qr_data_uri = (
                ReportSignatureService
                .generate_qr_data_uri(
                    verify_url=verify_url,
                )
            )

            pdf_content = await cls._generate_signed_pdf(
                request=request,
                templates=templates,
                report=report,
                schema=schema,
                qr_data_uri=qr_data_uri,
                document=document,
            )

            storage_context = (
                await ExecutionDocumentRepo
                .get_storage_context_for_month_item(
                    db,
                    month_item_id=month_item_id,
                )
            )

            original_file_name = (
                f"lesson_observation_{report.id}_signed.pdf"
            )

            stored_file = await storage_service.save_task_report(
                context=storage_context,
                document_id=document.id,
                report_code="lesson_observation",
                content=pdf_content,
                original_file_name=original_file_name,
                content_type="application/pdf",
            )

            new_object_key = stored_file.object_key

            report.qr_file = None
            report.pdf_signed_file = stored_file.object_key

            document.title = original_file_name
            document.original_file_name = (
                stored_file.original_file_name
            )
            document.stored_file_name = (
                stored_file.stored_file_name
            )
            document.file_path = stored_file.object_key
            document.mime_type = stored_file.content_type
            document.file_size = stored_file.file_size

            document.status = TaskDocumentStatus.SUBMITTED
            document.submitted_by_user_id = user.id
            document.submitted_at = datetime.now(
                timezone.utc
            )

        else:
            if document.status != TaskDocumentStatus.SUBMITTED:
                document.status = TaskDocumentStatus.DRAFT

        db.add(report)
        db.add(document)

        try:
            if action == "complete":
                assignment = (
                    await ReportAssignmentRepo
                    .get_assignment_for_update(
                        db,
                        selected_report_id=selected_report_id,
                    )
                )

                if assignment is None:
                    raise RuntimeError(
                        "Назначение исполнителя отчёта не найдено."
                    )

                await ReportAssignmentRepo.mark_completed(
                    db,
                    assignment=assignment,
                )

            await db.commit()

        except (SQLAlchemyError, RuntimeError):
            await db.rollback()

            logger.exception(
                "Не удалось сохранить лист наблюдения: "
                "month_item_id=%s, selected_report_id=%s, "
                "document_id=%s",
                month_item_id,
                selected_report_id,
                document.id,
            )

            if new_object_key:
                await cls._safe_delete_storage_object(
                    storage_service=storage_service,
                    object_key=new_object_key,
                )

            raise

        await db.refresh(report)

        # Старый объект удаляем только после успешного commit.
        if (
                action == "complete"
                and old_object_key
                and new_object_key
                and old_object_key != new_object_key
                and old_object_key.startswith("schools/")
        ):
            await cls._safe_delete_storage_object(
                storage_service=storage_service,
                object_key=old_object_key,
            )

        return report

    # =========================================================
    # FORM -> DTO
    # =========================================================

    @classmethod
    def _build_dto_from_form(
            cls,
            *,
            form,
            month_item_id: int,
            task_execution_document_id: int,
            selected_report_id: int,
            user: User,
    ) -> LessonObservationFormDTO:
        scores: dict[str, int] = {}

        for key, raw_value in form.multi_items():
            if not key.startswith("score_"):
                continue

            criterion_key = key.removeprefix(
                "score_"
            )

            scores[criterion_key] = cls.parse_int(
                raw_value
            )

        def text(name: str) -> str | None:
            return cls.clean_text(
                form.get(
                    f"info_{name}"
                )
            )

        total_score = cls.parse_int(
            form.get("total_score")
        )

        return LessonObservationFormDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=(
                task_execution_document_id
            ),

            # Эти значения дополнительно перезаписываются
            # серверным контекстом в save_or_complete().
            staff_member_id=(
                cls.parse_int(
                    form.get("staff_member_id")
                )
                or None
            ),
            observer_user_id=user.id,

            teacher_full_name=text(
                "teacher_full_name"
            ),
            teacher_position=text(
                "teacher_position"
            ),
            teacher_category=text(
                "teacher_category"
            ),
            teacher_subject=text(
                "teacher_subject"
            ),

            observer_full_name=text(
                "observer_full_name"
            ),
            observer_position=text(
                "observer_position"
            ),

            school_name=text("school_name"),
            class_name=text("class_name"),
            group_name=text("group_name"),

            lesson_datetime=parse_optional_datetime(
                form.get("info_lesson_datetime")
            ),

            theme=text("theme"),
            learning_objectives=text(
                "learning_objectives"
            ),
            lesson_objectives_1=text(
                "lesson_objectives_1"
            ),
            lesson_objectives_2=text(
                "lesson_objectives_2"
            ),
            lesson_objectives_3=text(
                "lesson_objectives_3"
            ),

            lesson_plan_filename=text(
                "lesson_plan_filename"
            ),

            criteria_scores={
                "scores": scores,
                "total_score": total_score,
            },

            col_sum_0=cls.parse_int(
                form.get("col_sum_0")
            ),
            col_sum_1=cls.parse_int(
                form.get("col_sum_1")
            ),
            col_sum_2=cls.parse_int(
                form.get("col_sum_2")
            ),
            col_sum_3=cls.parse_int(
                form.get("col_sum_3")
            ),

            total=total_score,

            suggestion_control=text(
                "suggestion_control"
            ),
            feedback=text("feedback"),
        )

    # =========================================================
    # STORAGE
    # =========================================================

    @staticmethod
    async def _safe_delete_storage_object(
            *,
            storage_service: SchoolStorageService,
            object_key: str | None,
    ) -> None:
        if not object_key:
            return

        try:
            await storage_service.delete(
                object_key=object_key,
            )

        except (OSError, RuntimeError) as exc:
            logger.warning(
                "Не удалось удалить объект листа наблюдения "
                "из хранилища: object_key=%s, error=%s",
                object_key,
                exc,
                exc_info=True,
            )

    # =========================================================
    # PDF
    # =========================================================

    @staticmethod
    async def _generate_signed_pdf(
            *,
            request: Request,
            templates,
            report: LessonObservationReport,
            schema: dict | None = None,
            qr_data_uri: str,
            document=None,
    ) -> bytes:
        html = templates.get_template(
            "staff/reports/user_templates/"
            "lesson_observation_pdf.html"
        ).render(
            request=request,
            report=report,
            schema=schema or {},
            qr_file=qr_data_uri,
            **report_pdf_context(request, report, document),
        )

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
            )

            try:
                page = await browser.new_page()

                await page.set_content(
                    html,
                    wait_until="networkidle",
                )

                pdf_content = await page.pdf(
                    format="A4",
                    print_background=True,
                    margin={
                        "top": "15mm",
                        "right": "15mm",
                        "bottom": "15mm",
                        "left": "15mm",
                    },
                )

            finally:
                await browser.close()

        return pdf_content
