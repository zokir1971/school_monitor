# app/modules/reports/services/checking_notebooks_system_service.py

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.enums import (
    DocumentType,
    ReportType,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import TaskExecutionDocument, TaskExecutionSelectedReport
from app.modules.reports.repositories.checking_notebooks_repo import CheckingNotebooksRepo
from app.modules.reports.repositories.system_checking_notebooks_repo import CheckingNotebooksSystemRepo
from app.modules.reports.system_report_dto.system_checking_notebooks_dto import CheckingNotebooksFillPageDTO
from app.modules.reports.system_schemas.checking_notebooks_schemas import CHECKING_NOTEBOOKS_SYSTEM_SCHEMA
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.users.models import User


class SystemCheckingNotebooksService:

    @classmethod
    async def get_fill_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
    ) -> CheckingNotebooksFillPageDTO:

        document = await cls.get_or_create_document(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
        )

        selected_report = await CheckingNotebooksSystemRepo.get_selected_report_by_id(
            db,
            selected_report_id=selected_report_id,
        )

        await cls.upgrade_schema_if_needed(
            db,
            document=document,
        )

        return await cls.build_page_data(
            db=db,
            document=document,
            selected_report=selected_report,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
        )

    @classmethod
    async def get_or_create_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
    ) -> TaskExecutionDocument:

        document = await CheckingNotebooksSystemRepo.get_document_by_selected_report(
            db,
            selected_report_id=selected_report_id,
            user_id=user.id,
        )

        if document:
            return document

        document = TaskExecutionDocument(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,

            uploaded_by_user_id=user.id,

            document_type=DocumentType.REPORT,

            report_code=ReportType.CHECKING_NOTEBOOKS_TABLE.value,
            report_label="Дәптер тексеру кестесі",

            source=TaskDocumentSource.GENERATED,
            template_mode="system",

            status=TaskDocumentStatus.DRAFT,

            version=1,
            is_current=True,
            is_final=False,

            title="Дәптер тексеру кестесі",

            schema_json=CHECKING_NOTEBOOKS_SYSTEM_SCHEMA,
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        return document

    @classmethod
    async def upgrade_schema_if_needed(
            cls,
            db: AsyncSession,
            *,
            document: TaskExecutionDocument,
    ) -> None:

        if document.source != TaskDocumentSource.GENERATED:
            return

        current_schema = document.schema_json or {}

        current_version = current_schema.get("version", 1)
        actual_version = CHECKING_NOTEBOOKS_SYSTEM_SCHEMA["version"]

        if current_version >= actual_version:
            return

        document.schema_json = {
            **CHECKING_NOTEBOOKS_SYSTEM_SCHEMA,

            "scores": current_schema.get("scores", {}),
            "saved_info": current_schema.get("saved_info", {}),
            "total_score": current_schema.get("total_score", 0),
        }

        db.add(document)
        await db.commit()
        await db.refresh(document)

    @classmethod
    async def build_page_data(
            cls,
            db: AsyncSession,
            *,
            document: TaskExecutionDocument,
            selected_report: TaskExecutionSelectedReport | None,
            month_item_id: int,
            selected_report_id: int,
            user: User,
    ) -> CheckingNotebooksFillPageDTO:

        schema = document.schema_json or CHECKING_NOTEBOOKS_SYSTEM_SCHEMA

        report = await CheckingNotebooksRepo.get_by_document_id(
            db,
            document_id=document.id,
        )

        criteria = schema.get("criteria") or []
        score_scale = schema.get("score_scale") or [0, 1, 2]

        target_kind = selected_report.target_kind if selected_report else None
        target_label = selected_report.target_label if selected_report else ""

        # =========================================================
        # School info
        # =========================================================

        school_info = await CheckingNotebooksSystemRepo.get_school_name_by_month_item_id(
            db,
            month_item_id=month_item_id,
        )

        # =========================================================
        # Checker info
        # =========================================================

        checker_info = None

        if school_info:
            checker_info = await CheckingNotebooksSystemRepo.get_checker_info(
                db,
                user_id=user.id,
                school_id=school_info.id,
            )

        # =========================================================
        # Teacher info
        # =========================================================

        teacher_info = None

        if target_kind == "teacher":
            try:
                teacher_id = int(selected_report.target_value)
            except (TypeError, ValueError):
                teacher_id = None

            if teacher_id:
                teacher_info = await CheckingNotebooksSystemRepo.get_teacher_info(
                    db,
                    teacher_id=teacher_id,
                )

        # =========================================================
        # Saved data
        # =========================================================

        saved_info = schema.get("saved_info") or {}

        saved_info = {
            **saved_info,

            "school_name": (
                    saved_info.get("school_name")
                    or (school_info.name if school_info else "")
                    or ""
            ),

            "checker_name": (
                    saved_info.get("checker_name")
                    or (checker_info.full_name if checker_info else "")
                    or getattr(user, "full_name", "")
                    or ""
            ),

            "checker_post": (
                    saved_info.get("checker_post")
                    or (checker_info.post if checker_info else "")
                    or ""
            ),

            "teacher_name": (
                    saved_info.get("teacher_name")
                    or (teacher_info.full_name if teacher_info else "")
                    or (target_label if target_kind == "teacher" else "")
                    or ""
            ),

            "subject_name": (
                    saved_info.get("subject_name")
                    or (teacher_info.subject if teacher_info else "")
                    or (target_label if target_kind == "subject" else "")
                    or ""
            ),

            "class_name": (
                    saved_info.get("class_name")
                    or (target_label if target_kind == "parallel_class" else "")
                    or ""
            ),
        }

        rows = schema.get("rows") or []

        # =========================================================
        # Scores
        # =========================================================

        scores = schema.get("scores") or {}

        try:
            total_score = int(schema.get("total_score") or 0)
        except (TypeError, ValueError):
            total_score = 0

        max_score = cls.calculate_max_score(
            criteria=criteria,
            score_scale=score_scale,
        )

        percent = cls.calculate_percent(
            total_score=total_score,
            max_score=max_score,
        )

        level = cls.calculate_level(percent)

        return CheckingNotebooksFillPageDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=document.id,

            document=document,
            selected_report=selected_report,

            template=None,
            schema=schema,

            rows=rows,
            saved_info=saved_info,

            criteria=criteria,
            score_scale=score_scale,

            scores=scores,
            total_score=total_score,
            max_score=max_score,
            percent=percent,
            level=level,

            report=report,
            readonly=bool(report and report.submitted_at),
            error=None,
        )

    @staticmethod
    def calculate_max_score(
            *,
            criteria: list,
            score_scale: list[int],
    ) -> int:
        if not criteria or not score_scale:
            return 0

        return len(criteria) * max(score_scale)

    @staticmethod
    def calculate_percent(
            *,
            total_score: int,
            max_score: int,
    ) -> int:
        if max_score <= 0:
            return 0

        return round(total_score * 100 / max_score)

    @staticmethod
    def calculate_level(percent: int) -> str:
        if percent >= 85:
            return "Жоғары"

        if percent >= 60:
            return "Орта"

        if percent > 0:
            return "Төмен"

        return "—"

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
    ):
        action = form.get("action")

        if action not in {"save", "complete"}:
            raise ValueError("Некорректное действие формы")

        document = await cls.get_or_create_document(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
        )

        if document.month_item_id != month_item_id:
            raise ValueError("Документ не относится к выбранной задаче")

        report = await CheckingNotebooksRepo.get_by_document_id(
            db,
            document_id=document.id,
        )

        if report and report.submitted_at is not None:
            raise ValueError("Подписанный отчет нельзя редактировать")

        if not report:
            report = await CheckingNotebooksSystemRepo.create(
                db,
                document_id=document.id,
                selected_report_id=selected_report_id,
                month_item_id=month_item_id,
                created_by_user_id=user.id,
            )

        # =========================================================
        # INFO
        # =========================================================

        saved_info = {}

        for key, value in form.multi_items():
            if key.startswith("info_"):
                info_key = key.removeprefix("info_")
                saved_info[info_key] = str(value).strip()

        # =========================================================
        # ROWS
        # =========================================================

        rows = []

        row_indexes = set()

        for key, value in form.multi_items():
            if key.startswith("rows["):
                index = key.split("[")[1].split("]")[0]
                row_indexes.add(index)

        for index in sorted(row_indexes, key=lambda x: int(x)):
            row = {}

            prefix = f"rows[{index}]"

            for key, value in form.multi_items():
                if key.startswith(prefix):
                    field_name = key.replace(prefix, "").strip("[]")
                    row[field_name] = str(value).strip()

            rows.append(row)

        # =========================================================
        # SAVE REPORT
        # =========================================================

        report.info_json = saved_info
        report.rows_json = rows
        report.updated_by_user_id = user.id

        schema = document.schema_json or CHECKING_NOTEBOOKS_SYSTEM_SCHEMA

        document.schema_json = {
            **schema,
            "saved_info": saved_info,
            "rows": rows,
        }

        # =========================================================
        # DRAFT
        # =========================================================

        if action == "save":
            document.status = TaskDocumentStatus.DRAFT

            await db.flush()

            await db.refresh(report)
            await db.refresh(document)

            return report

        # =========================================================
        # COMPLETE
        # =========================================================

        report.submitted_at = datetime.now(timezone.utc)

        token = ReportSignatureService.create_token(
            report_type="checking_notebooks",
            report_id=report.id,
            document_id=document.id,
        )

        verify_url = str(
            request.url_for("report_signature_verify")
        ) + f"?token={token}"

        report.qr_file = ReportSignatureService.generate_qr_file(
            report_type="checking_notebooks",
            report_id=report.id,
            verify_url=verify_url,
        )

        report.pdf_signed_file = await cls._generate_signed_pdf(
            request=request,
            templates=templates,
            report=report,
            schema=document.schema_json or {},
        )

        document.status = TaskDocumentStatus.SUBMITTED
        document.file_path = report.pdf_signed_file
        document.mime_type = "application/pdf"

        await db.flush()

        await db.refresh(report)
        await db.refresh(document)

        return report

    @classmethod
    async def _generate_signed_pdf(
            cls,
            *,
            request: Request,
            templates,
            report,
            schema: dict | None = None,
    ) -> str:
        base_dir = Path("media/reports/checking_notebooks/pdf")
        base_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = base_dir / f"checking_notebooks_{report.id}_signed.pdf"

        qr_file = cls._file_to_data_uri(report.qr_file)

        html = templates.get_template(
            "staff/reports/user_templates/checking_notebooks_pdf.html"
        ).render(
            request=request,
            report=report,
            schema=schema or {},
            qr_file=qr_file,
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            try:
                page = await browser.new_page()
                await page.set_content(html, wait_until="networkidle")

                await page.pdf(
                    path=str(pdf_path),
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

        return str(pdf_path)

    @staticmethod
    def _file_to_data_uri(file_path: str | None) -> str | None:
        if not file_path:
            return None

        path = Path(file_path)

        if not path.exists():
            return None

        mime_type = "image/png"

        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")

        return f"data:{mime_type};base64,{encoded}"
