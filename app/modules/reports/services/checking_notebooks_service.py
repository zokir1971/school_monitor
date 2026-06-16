from __future__ import annotations

import base64
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from fastapi import Request
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData

from app.modules.reports.enums import TaskDocumentStatus
from app.modules.reports.models_template_reports import CheckingNotebooksReport
from app.modules.reports.repositories.checking_notebooks_repo import CheckingNotebooksRepo
from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo
from app.modules.reports.repositories.template_repo import TemplateReportRepo
from app.modules.reports.repositories.user_template_repo import UserReportTemplateRepo
from app.modules.reports.schemas.checking_notebooks_dto import CheckingNotebooksDTO, CheckingNotebooksFillDTO
from app.modules.reports.services.lesson_observation_report_service import LessonObservationReportService
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.tasks.task_repo import StaffTasksRepo
from app.modules.users.models import User


class CheckingNotebooksService:

    @staticmethod
    def parse_optional_datetime(value: str | None) -> datetime | None:
        if not value or not value.strip():
            return None

        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            return None

    @classmethod
    async def save_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
            form: FormData,
    ) -> CheckingNotebooksReport:

        document = await TemplateReportRepo.get_template_document(
            db,
            selected_report_id=selected_report_id,
            user_id=user.id,
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

            check_date=CheckingNotebooksService.parse_optional_datetime(
                saved_info.get("check_date")
            ),

            conclusion=saved_info.get("conclusion", ""),
            recommendations=saved_info.get("recommendations", ""),
        )

        await db.commit()
        await db.refresh(report)

        return report

    @staticmethod
    async def save_or_complete(
            db: AsyncSession,
            *,
            request: Request,
            form,
            month_item_id: int,
            selected_report_id: int,
            task_execution_document_id: int,
            _user,
            templates,
    ):
        action = form.get("action") or "save"

        report = await CheckingNotebooksRepo.get_by_document_id(
            db,
            document_id=task_execution_document_id,
        )

        if report and report.submitted_at is not None:
            raise ValueError("Отчет уже подписан. Редактирование запрещено.")

        document = await CheckingNotebooksRepo.get_document_by_id(
            db,
            task_execution_document_id,
        )

        if not document:
            raise ValueError("Документ отчета не найден")

        if document.month_item_id != month_item_id:
            raise ValueError("Документ не относится к выбранной задаче.")

        if document.selected_report_id != selected_report_id:
            raise ValueError("Документ не относится к выбранному отчету.")

        schema = document.schema_json or {}

        if not schema:
            raise ValueError("К документу не применен личный шаблон.")

        saved_info: dict[str, str] = {}

        for key, value in form.multi_items():
            if key.startswith("info_"):
                saved_info[key.removeprefix("info_")] = str(value).strip()

        scores: dict[str, int] = {}

        for key, value in form.multi_items():
            if key.startswith("score_"):
                criterion_key = key.removeprefix("score_")

                try:
                    score_value = int(value or 0)
                except (TypeError, ValueError):
                    score_value = 0

                scores[criterion_key] = score_value
                scores[key] = score_value

        try:
            total_score = int(form.get("total_score") or 0)
        except (TypeError, ValueError):
            total_score = 0

        try:
            max_score = int(form.get("max_score") or 0)
        except (TypeError, ValueError):
            max_score = 0

        try:
            percent = int(form.get("percent") or 0)
        except (TypeError, ValueError):
            percent = 0

        level = str(
            form.get("level")
            or form.get("info_level")
            or saved_info.get("level")
            or "—"
        ).strip()

        if total_score == 0 and scores:
            total_score = sum(
                value for key, value in scores.items()
                if not key.startswith("score_")
            )

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

            check_date=CheckingNotebooksService.parse_optional_datetime(
                saved_info.get("check_date")
            ),

            conclusion=saved_info.get("conclusion", ""),
            recommendations=saved_info.get("recommendations", ""),
        )
        report.criteria_scores = rows_json
        report.rows_json = rows_json

        await db.flush()
        await db.refresh(report)

        if action == "complete":

            report.submitted_at = datetime.now(timezone.utc)

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

            report.qr_file = ReportSignatureService.generate_qr_file(
                report_type="checking_notebooks",
                report_id=report.id,
                verify_url=verify_url,
            )

            report.pdf_signed_file = (
                await CheckingNotebooksService._generate_signed_pdf(
                    request=request,
                    templates=templates,
                    report=report,
                    schema=schema,
                )
            )

            document.status = TaskDocumentStatus.SUBMITTED

        else:

            if document.status != TaskDocumentStatus.SUBMITTED:
                document.status = TaskDocumentStatus.DRAFT

        db.add(report)
        db.add(document)

        await db.commit()
        await db.refresh(report)

        return report

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

            check_date=LessonObservationReportService.parse_optional_datetime(
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

    @staticmethod
    async def _generate_signed_pdf(
            *,
            request: Request,
            templates,
            report,
            schema: dict | None = None,
    ) -> str:
        base_dir = Path("media/reports/checking_notebooks/pdf")
        base_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = base_dir / f"checking_notebooks_{report.id}_signed.pdf"

        qr_file = CheckingNotebooksService._file_to_data_uri(report.qr_file)

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

        document = await TemplateReportRepo.get_template_document(
            db,
            selected_report_id=selected_report_id,
            user_id=user.id,
        )

        if not document:
            raise ValueError("Документ отчета не найден")

        if document.month_item_id != month_item_id:
            raise ValueError("Документ не относится к выбранной задаче")

        selected_report = await CheckingNotebooksRepo.get_selected_report_by_id(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Выбранный отчет не найден")

        school_id = cast(int, user.school_id)
        staff_member_id = cast(int | None, user.staff_member_id)

        staff_role_ids: list[int] = []

        if staff_member_id is not None:
            staff_role_ids = await CheckingNotebooksRepo.get_active_staff_role_ids(
                db,
                school_id=school_id,
                staff_member_id=staff_member_id,
            )

        task = await StaffTasksRepo.get_task_for_execution(
            db,
            school_id=school_id,
            staff_role_ids=staff_role_ids,
            month_item_id=month_item_id,
        )

        if not task:
            raise ValueError("Задача не найдена")

        school_name = await CheckingNotebooksRepo.get_school_name_by_id(
            db,
            school_id=school_id,
        )

        checker_post = ""
        if staff_member_id is not None:
            checker_post = await CheckingNotebooksRepo.get_controller_post(
                db,
                school_id=school_id,
                staff_member_id=staff_member_id,
            )

        schema = document.schema_json or {}
        template = None

        if not schema and template_id:
            template = await UserReportTemplateRepo.get_user_template(
                db,
                template_id=template_id,
                owner_user_id=user.id,
            )

            if not template:
                raise ValueError("Шаблон не найден")

            schema = template.schema_json or {}

        if not schema:
            raise ValueError("Для документа не найден шаблон")

        criteria = schema.get("criteria") or []
        score_scale = schema.get("score_scale") or [0, 1, 2]

        if not criteria:
            raise ValueError("В шаблоне нет критериев")

        max_score = len(criteria) * max(score_scale)

        report = await CheckingNotebooksRepo.get_by_document_id(
            db,
            document_id=document.id,
        )

        # =========================================================
        # Teacher subject fallback
        # =========================================================

        teacher_subject = ""

        if selected_report.target_kind == "teacher":
            try:
                teacher_id = int(selected_report.target_value)
            except (TypeError, ValueError):
                teacher_id = None

            if teacher_id:
                teacher_info = await CheckingNotebooksRepo.get_teacher_info(
                    db,
                    teacher_id=teacher_id,
                )

                if teacher_info:
                    teacher_subject = (
                            getattr(teacher_info, "subject", "")
                            or getattr(teacher_info, "subject_name", "")
                            or ""
                    )

        scores: dict[str, int] = {}
        total_score = 0
        percent = 0
        level = "—"

        if report:
            saved_info = {
                "school_name": report.school_name or "",
                "checker_name": report.checker_name or user.full_name or "",
                "checker_post": report.checker_post or checker_post,
                "teacher_name": report.teacher_name or "",
                "class_name": report.class_name or "",
                "subject_name": report.subject_name or teacher_subject or "",
                "check_date": (
                    report.check_date.strftime("%Y-%m-%dT%H:%M")
                    if report.check_date else ""
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
                        clean_key = str(key).removeprefix("score_")

                        try:
                            scores[clean_key] = int(value or 0)
                            scores[f"score_{clean_key}"] = int(value or 0)
                        except (TypeError, ValueError):
                            scores[clean_key] = 0
                            scores[f"score_{clean_key}"] = 0

            elif isinstance(raw_rows_data, list):
                for i, row in enumerate(raw_rows_data):
                    if isinstance(row, dict):
                        try:
                            score_value = int(row.get("score") or 0)
                        except (TypeError, ValueError):
                            score_value = 0

                        scores[f"criterion_{i}"] = score_value
                        scores[f"score_criterion_{i}"] = score_value

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
                else round(total_score * 100 / max_score) if max_score else 0
            )

            level = report.level or "—"

        else:
            saved_info = {
                "school_name": school_name,
                "checker_name": user.full_name or "",
                "checker_post": checker_post,
                "teacher_name": getattr(selected_report, "target_label", "") or "",
                "class_name": getattr(selected_report, "class_name", "") or "",
                "subject_name": teacher_subject,
                "check_date": "",
                "conclusion": "",
                "recommendations": "",
            }

        return CheckingNotebooksFillDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=document.id,

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

    @staticmethod
    def calculate_max_score(
            *,
            sections: list[dict[str, Any]],
            score_scale: list[int],
    ) -> int:
        max_value = max(score_scale) if score_scale else 0
        total = 0

        for section in sections:
            criteria = section.get("criteria") or []
            total += len(criteria) * max_value

        return total
