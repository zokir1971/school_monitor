# app/modules/reports/services/checking_notebooks_service.py
from __future__ import annotations

from app.core.i18n import resolve_language
from app.core.report_pdf_i18n import select_document_language, saved_report_language, report_pdf_context

from datetime import datetime, timezone
from typing import Any
import logging

from fastapi import Request
from playwright.async_api import async_playwright
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData

from app.core.storage.factory import get_storage
from app.core.storage.school_storage import SchoolStorageService
from app.modules.reports.enums import (
    DocumentType,
    ReportTemplateMode,
    ReportType,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_template_reports import CheckingNotebooksReport
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.repositories.checking_notebooks_repo import CheckingNotebooksRepo
from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo
from app.modules.reports.repositories.execution_document_repo import ExecutionDocumentRepo
from app.modules.reports.repositories.report_assignment_repo import (
    ReportAssignmentRepo,
)
from app.modules.reports.schemas.checking_notebooks_dto import (
    CheckingNotebooksDTO,
    CheckingNotebooksFillDTO,
)
from app.modules.reports.utils.parsing import parse_optional_datetime
from app.modules.reports.rules.checking_notebooks import calculate_max_score
from app.modules.reports.services.report_template_resolver import (
    ReportTemplateResolver,
)
from app.modules.reports.services.base_report_service import (
    BaseReportService,
)
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.users.models import User

logger = logging.getLogger(__name__)


class CheckingNotebooksService(BaseReportService):

    @classmethod
    async def save_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            _user: User,
            form: FormData,
    ) -> CheckingNotebooksReport:

        document = await ExecutionDocumentRepo.get_current_report_document(
            db,
            selected_report_id=selected_report_id,
        )

        if not document:
            raise ValueError("Документ отчета не найден")

        # INFO
        saved_info = {
            key.removeprefix("info_"): str(value).strip()
            for key, value in form.multi_items()
            if key.startswith("info_")
        }

        # SCORES
        scores = {}
        for key, value in form.multi_items():
            if key.startswith("score_"):
                k = key.removeprefix("score_")
                try:
                    scores[k] = int(value or 0)
                except (TypeError, ValueError):
                    scores[k] = 0

        # TOTAL
        total_score = int(form.get("total_score") or 0)
        max_score = int(form.get("max_score") or 0)
        percent = int(form.get("percent") or 0)
        level = str(form.get("info_level") or "—").strip()

        if total_score == 0 and scores:
            total_score = sum(scores.values())

        if percent == 0 and max_score:
            percent = round(total_score * 100 / max_score)

        rows_json = {
            "info": saved_info,
            "scores": scores,
            "total_score": total_score,
            "max_score": max_score,
            "percent": percent,
            "level": level,
        }

        report = await CheckingNotebooksRepo.upsert_checking_notebooks_report(
            db,
            task_execution_document_id=document.id,
            month_item_id=month_item_id,

            rows_json=rows_json,

            total_score=total_score,
            max_score=max_score,
            percent=percent,
            level=level,

            school_name=saved_info.get("school_name", ""),
            checker_name=saved_info.get("checker_name", ""),
            checker_post=saved_info.get("checker_post", ""),

            teacher_name=saved_info.get("teacher_name", ""),
            class_name=saved_info.get("class_name", ""),
            subject_name=saved_info.get("subject_name", ""),

            check_date=parse_optional_datetime(
                saved_info.get("check_date")
            ),

            conclusion=saved_info.get("conclusion", ""),
            recommendations=saved_info.get("recommendations", ""),
        )

        await db.commit()
        await db.refresh(report)

        return report

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
    ) -> CheckingNotebooksReport:
        """
        Сохранить черновик или подписать отчет проверки тетрадей.

        Новая архитектура:
        - TaskExecutionDocument НЕ обязан существовать до POST;
        - при первом Save/Complete документ создается здесь;
        - schema_json сохраняется как snapshot выбранного шаблона;
        - системный и пользовательский шаблоны используют один flow;
        - повторное открытие использует snapshot документа.
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

        # =========================================================
        # READ CONTEXT
        # =========================================================

        context = await CheckingNotebooksRepo.get_fill_context(
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
                != ReportType.CHECKING_NOTEBOOKS_TABLE.value
        ):
            raise ValueError(
                "Выбранный отчет не является отчетом проверки тетрадей."
            )

        document = context.document
        report = context.report

        if report is not None and report.submitted_at is not None:
            raise ValueError(
                "Отчет уже подписан. Редактирование запрещено."
            )

        document_language = select_document_language(
            form.get("document_language"), saved_report_language(report), resolve_language(request, user)
        )

        # =========================================================
        # RESOLVE TEMPLATE / SNAPSHOT
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
                    selected_report_id=selected_report_id,
                    uploaded_by_user_id=user.id,

                    document_type=DocumentType.REPORT,
                    report_code=context.report_code,
                    report_label=(
                        resolved.report_label
                        or context.report_label
                    ),

                    source=TaskDocumentSource.GENERATED,
                    template_mode=resolved.template_mode.value,
                    custom_template_id=resolved.user_template_id,

                    status=TaskDocumentStatus.DRAFT,
                    version=1,
                    is_current=True,
                    is_final=False,

                    title=(
                        resolved.template_title
                        or resolved.report_label
                        or context.report_label
                    ),

                    schema_json=resolved.schema,
                )

                db.add(document)
                await db.flush()

            else:
                # Legacy document without schema snapshot:
                # normalize it only during explicit Save/Complete.
                document.schema_json = resolved.schema
                document.template_mode = resolved.template_mode.value
                document.custom_template_id = resolved.user_template_id

        if not schema:
            raise ValueError(
                "Для отчета не найдена структура шаблона."
            )

        # =========================================================
        # FORM DATA
        # =========================================================

        saved_info: dict[str, str] = {}

        for key, field_value in form.multi_items():
            if not key.startswith("info_"):
                continue

            cleaned_value = cls.clean_text(
                field_value
            )

            saved_info[
                key.removeprefix("info_")
            ] = cleaned_value or ""

        scores: dict[str, int] = {}

        for key, field_value in form.multi_items():
            if not key.startswith("score_"):
                continue

            criterion_key = key.removeprefix("score_")

            score_value = cls.parse_int(
                field_value
            )

            # Сохраняем обе формы ключа для совместимости
            # с текущими Jinja/PDF шаблонами.
            scores[criterion_key] = score_value
            scores[key] = score_value

        total_score = cls.parse_int(
            form.get("total_score")
        )

        max_score = cls.parse_int(
            form.get("max_score")
        )

        percent = cls.parse_int(
            form.get("percent")
        )

        level = str(
            form.get("level")
            or form.get("info_level")
            or saved_info.get("level")
            or "—"
        ).strip()

        if total_score == 0 and scores:
            total_score = sum(
                value
                for key, value in scores.items()
                if not key.startswith("score_")
            )

        if max_score == 0:
            criteria = schema.get("criteria") or []
            score_scale = schema.get("score_scale") or [0, 1, 2]

            if criteria:
                max_score = calculate_max_score(
                    criteria=criteria,
                    score_scale=score_scale,
                )

        if percent == 0 and max_score:
            percent = round(
                total_score * 100 / max_score
            )

        rows_json = {
            "document_language": document_language,
            "info": saved_info,
            "scores": scores,
            "total_score": total_score,
            "max_score": max_score,
            "percent": percent,
            "level": level,
        }

        # =========================================================
        # REPORT UPSERT
        # =========================================================

        report = (
            await CheckingNotebooksRepo
            .upsert_checking_notebooks_report(
                db,
                task_execution_document_id=document.id,
                month_item_id=month_item_id,

                rows_json=rows_json,

                total_score=total_score,
                max_score=max_score,
                percent=percent,
                level=level,

                school_name=saved_info.get(
                    "school_name",
                    "",
                ),
                checker_name=saved_info.get(
                    "checker_name",
                    "",
                ),
                checker_post=saved_info.get(
                    "checker_post",
                    "",
                ),

                teacher_name=saved_info.get(
                    "teacher_name",
                    "",
                ),
                class_name=saved_info.get(
                    "class_name",
                    "",
                ),
                subject_name=saved_info.get(
                    "subject_name",
                    "",
                ),

                check_date=parse_optional_datetime(
                    saved_info.get("check_date")
                ),

                conclusion=saved_info.get(
                    "conclusion",
                    "",
                ),
                recommendations=saved_info.get(
                    "recommendations",
                    "",
                ),
            )
        )

        report.criteria_scores = rows_json
        report.rows_json = rows_json

        await db.flush()
        await db.refresh(report)

        # =========================================================
        # STORAGE / COMPLETE
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
                report_type="checking_notebooks",
                report_id=report.id,
                document_id=report.task_execution_document_id,
                total=report.total_score,
            )

            await ReportVerifyRepo.deactivate_old_signatures(
                db,
                report_type="checking_notebooks",
                report_id=report.id,
                document_id=report.task_execution_document_id,
            )

            signature = await ReportVerifyRepo.create_signature_token(
                db,
                token=token,
                report_type="checking_notebooks",
                report_id=report.id,
                document_id=report.task_execution_document_id,
            )

            verify_url = str(
                request.url_for(
                    "report_verify_by_code_page",
                    code=signature.code,
                )
            )

            qr_data_uri = ReportSignatureService.generate_qr_data_uri(
                verify_url=verify_url,
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
                f"checking_notebooks_{report.id}_signed.pdf"
            )

            stored_file = await storage_service.save_task_report(
                context=storage_context,
                document_id=document.id,
                report_code="checking_notebooks",
                content=pdf_content,
                original_file_name=original_file_name,
                content_type="application/pdf",
            )

            new_object_key = stored_file.object_key

            report.qr_file = None
            report.pdf_signed_file = stored_file.object_key

            document.title = original_file_name
            document.original_file_name = stored_file.original_file_name
            document.stored_file_name = stored_file.stored_file_name
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
                "Не удалось сохранить отчет проверки тетрадей: "
                "month_item_id=%s, selected_report_id=%s, document_id=%s",
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

    @staticmethod
    async def _safe_delete_storage_object(
            *,
            storage_service: SchoolStorageService,
            object_key: str | None,
    ) -> None:
        """
        Удалить объект без прерывания основной операции.

        Используется при компенсационном удалении:
        например, когда файл записался, но транзакция БД завершилась ошибкой.
        """
        if not object_key:
            return

        try:
            await storage_service.delete(
                object_key=object_key,
            )
        except (OSError, RuntimeError) as exc:
            logger.warning(
                "Не удалось удалить объект из хранилища: "
                "object_key=%s, error=%s",
                object_key,
                exc,
                exc_info=True,
            )

    @staticmethod
    def _build_dto_from_form(
            *,
            form,
            schema: dict[str, Any],
            document,
            month_item_id: int,
            selected_report_id: int,
            task_execution_document_id: int,
            user,
    ) -> CheckingNotebooksDTO:
        def text(name: str) -> str | None:
            raw = form.get(f"info_{name}")
            cleaned = str(raw).strip() if raw is not None else ""
            return cleaned or None

        def integer(name: str) -> int:
            try:
                return int(form.get(name) or 0)
            except (TypeError, ValueError):
                return 0

        columns = schema.get("columns") or []
        rows_json: list[dict[str, Any]] = []

        for row_index in range(1, 101):
            row_data: dict[str, Any] = {}
            has_value = False

            for column in columns:
                field_name = f"row_{row_index}_{column}"
                raw_value = form.get(field_name)
                value = str(raw_value).strip() if raw_value is not None else ""

                if value:
                    has_value = True

                row_data[column] = value

            if has_value:
                rows_json.append(row_data)

        return CheckingNotebooksDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=task_execution_document_id,
            observer_user_id=user.id,

            user_template_id=getattr(document, "user_template_id", None),

            school_name=text("school_name"),
            checker_name=text("checker_name"),
            checker_post=text("checker_post"),

            teacher_name=text("teacher_name"),
            class_name=text("class_name"),
            subject_name=text("subject_name"),

            check_date=parse_optional_datetime(
                form.get("info_check_date")
            ),

            rows_json=rows_json,

            total_score=integer("total_score"),
            max_score=integer("max_score"),
            percent=integer("percent"),
            level=text("level") or "—",

            conclusion=text("conclusion"),
            recommendations=text("recommendations"),
        )

    '''
    @staticmethod
    def _file_to_data_uri(file_path: str | None) -> str | None:
        if not file_path:
            return None

        path = Path(file_path)

        if not path.exists():
            return None

        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("utf-8")

        return f"data:{mime_type};base64,{data}"
    '''

    @staticmethod
    async def _generate_signed_pdf(
            *,
            request: Request,
            templates,
            report,
            schema: dict | None = None,
            qr_data_uri: str,
            document=None,
    ) -> bytes:
        html = templates.get_template(
            "staff/reports/user_templates/checking_notebooks_pdf.html"
        ).render(
            request=request,
            report=report,
            schema=schema or {},
            qr_file=qr_data_uri,
            **report_pdf_context(request, report, document),
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            try:
                page = await browser.new_page()

                await page.set_content(html, wait_until="networkidle")

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

    @classmethod
    async def get_checking_notebooks_fill_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            template_id: int | None,
            user: User,
    ) -> CheckingNotebooksFillDTO:
        """
        Сформировать страницу заполнения проверки тетрадей.

        Новая архитектура:
        - GET является read-only;
        - отсутствие TaskExecutionDocument допустимо;
        - существующий document.schema_json имеет приоритет как snapshot;
        - если документа еще нет, schema разрешается через
          ReportTemplateResolver только в памяти;
        - системный шаблон не требует SQL-запроса к библиотеке шаблонов;
        - пользовательский шаблон требует максимум один дополнительный SELECT.

        template_id:
        - None -> системный preview, если документа еще нет;
        - int  -> пользовательский preview, если документа еще нет.

        Если черновик уже существует, template_id игнорируется:
        источник истины — snapshot самого TaskExecutionDocument.
        """

        # =========================================================
        # USER CONTEXT
        # =========================================================

        school_id, staff_member_id = (
            cls.require_user_context(user)
        )

        # =========================================================
        # ONE-SQL FILL CONTEXT
        # =========================================================

        context = await CheckingNotebooksRepo.get_fill_context(
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
                != ReportType.CHECKING_NOTEBOOKS_TABLE.value
        ):
            raise ValueError(
                "Выбранный отчет не является отчетом проверки тетрадей."
            )

        selected_report = context.selected_report
        document = context.document
        report = context.report

        # =========================================================
        # TEMPLATE / SCHEMA
        # =========================================================

        template = None

        if document is not None and document.schema_json:
            # Уже сохраненный черновик/документ.
            # Snapshot документа неизменяем и не обращаемся к resolver.
            schema = document.schema_json or {}

        else:
            # Preview без создания TaskExecutionDocument.
            #
            # Если существует legacy document без schema_json,
            # пытаемся восстановить режим по его метаданным.
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
                "Для отчета не найдена структура шаблона."
            )

        # =========================================================
        # SCHEMA PREPARATION
        # =========================================================

        criteria = schema.get("criteria") or []
        score_scale = schema.get("score_scale") or [0, 1, 2]

        if not criteria:
            raise ValueError(
                "В шаблоне отсутствуют критерии проверки."
            )

        max_score = calculate_max_score(
            criteria=criteria,
            score_scale=score_scale,
        )

        # =========================================================
        # SAVED / INITIAL FORM DATA
        # =========================================================

        scores: dict[str, int] = {}
        total_score = 0
        percent = 0
        level = "—"

        if report is not None:
            saved_info = {
                "school_name": report.school_name or context.school_name,
                "checker_name": (
                    report.checker_name
                    or user.full_name
                    or ""
                ),
                "checker_post": (
                    report.checker_post
                    or context.checker_post
                    or ""
                ),
                "teacher_name": (
                    report.teacher_name
                    or context.teacher_name
                    or selected_report.target_label
                    or ""
                ),
                "class_name": report.class_name or "",
                "subject_name": (
                    report.subject_name
                    or context.teacher_subject
                    or ""
                ),
                "check_date": (
                    report.check_date.strftime(
                        "%Y-%m-%dT%H:%M"
                    )
                    if report.check_date
                    else ""
                ),
                "conclusion": report.conclusion or "",
                "recommendations": report.recommendations or "",
                "level": report.level or "",
            }

            raw_rows_data = report.rows_json

            if isinstance(raw_rows_data, dict):
                raw_info = raw_rows_data.get("info")

                if isinstance(raw_info, dict):
                    saved_info.update(raw_info)

                raw_scores = raw_rows_data.get("scores")

                if isinstance(raw_scores, dict):
                    for key, value in raw_scores.items():
                        clean_key = str(key).removeprefix(
                            "score_"
                        )

                        try:
                            score_value = int(value or 0)
                        except (TypeError, ValueError):
                            score_value = 0

                        # Оставляем обе формы ключа, потому что
                        # существующие Jinja-шаблоны поддерживают обе.
                        scores[clean_key] = score_value
                        scores[
                            f"score_{clean_key}"
                        ] = score_value

            elif isinstance(raw_rows_data, list):
                # Совместимость со старыми сохраненными данными.
                for index, row in enumerate(raw_rows_data):
                    if not isinstance(row, dict):
                        continue

                    try:
                        score_value = int(
                            row.get("score") or 0
                        )
                    except (TypeError, ValueError):
                        score_value = 0

                    key = f"criterion_{index}"

                    scores[key] = score_value
                    scores[f"score_{key}"] = score_value

            total_score = (
                report.total_score
                if report.total_score is not None
                else sum(
                    value
                    for key, value in scores.items()
                    if not key.startswith("score_")
                )
            )

            max_score = (
                report.max_score
                if report.max_score is not None
                else max_score
            )

            percent = (
                report.percent
                if report.percent is not None
                else (
                    round(
                        total_score * 100 / max_score
                    )
                    if max_score
                    else 0
                )
            )

            level = report.level or "—"

        else:
            saved_info = {
                "school_name": context.school_name,
                "checker_name": user.full_name or "",
                "checker_post": context.checker_post,

                "teacher_name": (
                    context.teacher_name
                    or selected_report.target_label
                    or ""
                ),

                "class_name": "",
                "subject_name": context.teacher_subject,

                "check_date": "",
                "conclusion": "",
                "recommendations": "",
            }

        # =========================================================
        # DTO
        # =========================================================

        return CheckingNotebooksFillDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,

            # None до первого Save/Complete — это нормальное
            # состояние preview в новой архитектуре.
            task_execution_document_id=(
                document.id
                if document is not None
                else None
            ),

            schema=schema,
            criteria=criteria,
            score_scale=score_scale,

            scores=scores,
            saved_info=saved_info,
            rows=[],

            total_score=total_score,
            max_score=max_score,
            percent=percent,
            level=level,

            report=report,
            document=document,
            template=template,
        )
