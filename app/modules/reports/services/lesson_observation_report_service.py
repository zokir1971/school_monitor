# app/modules/reports/services/lesson_observation_report_service.py

from __future__ import annotations

import base64
import mimetypes
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from typing import cast

from fastapi import Request
from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData

from app.modules.planning.models_month_plan import SchoolMonthPlanItem
from app.modules.reports.dtos_template import LessonObservationFillDTO, LessonObservationInfoDTO, \
    LessonObservationFormDTO
from app.modules.reports.enums import TaskDocumentStatus
from app.modules.reports.models_documents import TaskExecutionSelectedReport
from app.modules.reports.models_template_reports import LessonObservationReport
from app.modules.reports.repositories.lesson_observation_report_repo import LessonObservationReportRepo, \
    LessonObservationRepo
from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo
from app.modules.reports.repositories.template_repo import TemplateReportRepo
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.tasks.task_repo import StaffTasksRepo
from app.modules.users.models import User


class LessonObservationReportService:

    @staticmethod
    def filter_lesson_observation_info_fields(data: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {field.name for field in fields(LessonObservationInfoDTO)}

        return {
            key: value
            for key, value in data.items()
            if key in allowed_fields
        }

    @staticmethod
    def parse_optional_datetime(value: str | None) -> datetime | None:
        if not value or not value.strip():
            return None

        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            return None

    @staticmethod
    def _fill_if_empty(data: dict[str, Any], key: str, value: Any) -> None:
        if data.get(key) in (None, ""):
            data[key] = value or ""

    @staticmethod
    def _format_datetime_for_input(value: datetime | None) -> str:
        if not value:
            return ""

        return value.strftime("%Y-%m-%dT%H:%M")

    @classmethod
    def _build_info_from_report(
            cls,
            report: LessonObservationReport,
    ) -> tuple[dict, dict, int]:
        criteria_data = report.criteria_scores or {}

        # ВАЖНО: копия, чтобы не мутировать JSON из БД напрямую
        saved_info = dict(criteria_data.get("info") or {})

        cls._fill_if_empty(saved_info, "teacher_full_name", report.teacher_full_name)
        cls._fill_if_empty(saved_info, "teacher_position", report.teacher_position)
        cls._fill_if_empty(saved_info, "teacher_category", report.teacher_category)
        cls._fill_if_empty(saved_info, "teacher_subject", report.teacher_subject)

        cls._fill_if_empty(saved_info, "observer_full_name", report.observer_full_name)
        cls._fill_if_empty(saved_info, "observer_position", report.observer_position)

        cls._fill_if_empty(saved_info, "school_name", report.school_name)
        cls._fill_if_empty(saved_info, "class_name", report.class_name)
        cls._fill_if_empty(saved_info, "group_name", report.group_name)
        cls._fill_if_empty(
            saved_info,
            "lesson_datetime",
            cls._format_datetime_for_input(report.lesson_datetime),
        )

        cls._fill_if_empty(saved_info, "theme", report.theme)
        cls._fill_if_empty(saved_info, "learning_objectives", report.learning_objectives)

        cls._fill_if_empty(saved_info, "lesson_objectives_1", report.lesson_objectives_1)
        cls._fill_if_empty(saved_info, "lesson_objectives_2", report.lesson_objectives_2)
        cls._fill_if_empty(saved_info, "lesson_objectives_3", report.lesson_objectives_3)

        cls._fill_if_empty(saved_info, "feedback", report.feedback)
        cls._fill_if_empty(saved_info, "suggestion_control", report.suggestion_control)

        scores = criteria_data.get("scores") or {}
        total_score = criteria_data.get("total_score") or report.total or 0

        return saved_info, scores, total_score

    @classmethod
    async def _build_initial_info(
            cls,
            db: AsyncSession,
            *,
            task: SchoolMonthPlanItem,
            selected_report: TaskExecutionSelectedReport,
            user: User,
    ) -> tuple[dict, dict, int]:

        # --- школа ---
        try:
            school_name = task.month_plan.school_plan.school.name or ""
        except AttributeError:
            school_name = ""

        # --- типобезопасные значения ---
        school_id = cast(int, user.school_id)
        staff_member_id = cast(int | None, user.staff_member_id)

        # --- учитель ---
        teacher_name = selected_report.target_label or ""
        teacher_post = ""
        teacher_category = ""
        subject = ""

        target_value = cast(str | None, selected_report.target_value)
        teacher_staff_id = int(target_value) if target_value else None

        if teacher_staff_id:
            teacher = await LessonObservationReportRepo.get_staff_member_by_id(
                db,
                school_id=school_id,
                staff_member_id=teacher_staff_id,
            )

            if teacher:
                teacher_name = teacher.full_name or teacher_name
                teacher_post = teacher.position_text or ""
                teacher_category = teacher.qualification_category or ""
                subject = teacher.subject or ""

                if teacher_category:
                    teacher_post = (
                        f"{teacher_post}, {teacher_category}"
                        if teacher_post
                        else teacher_category
                    )
        # --- наблюдатель ---
        controller_post = ""

        if staff_member_id is not None:
            controller_post = await LessonObservationReportRepo.get_controller_post(
                db,
                school_id=school_id,
                staff_member_id=staff_member_id,
            )

        # --- итог ---
        saved_info = {
            "teacher_full_name": teacher_name,
            "teacher_position": teacher_post,
            "teacher_category": teacher_category,
            "teacher_subject": subject,

            "observer_full_name": user.full_name or "",
            "observer_position": controller_post,

            "school_name": school_name,
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

    @classmethod
    async def get_lesson_observation_fill_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
    ) -> LessonObservationFillDTO:

        document = await TemplateReportRepo.get_template_document(
            db,
            selected_report_id=selected_report_id,
            user_id=user.id,
        )

        if not document:
            raise ValueError("Документ отчета не найден или нет доступа")

        if document.month_item_id != month_item_id:
            raise ValueError("Документ не относится к выбранной задаче")

        selected_report = await LessonObservationReportRepo.get_selected_report_by_id(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Выбранный отчет не найден")

        if selected_report.target_kind != "teacher":
            raise ValueError("Для листа наблюдения должен быть выбран учитель")

        school_id = cast(int, user.school_id)
        staff_member_id = cast(int | None, user.staff_member_id)

        staff_role_ids = []

        if staff_member_id is not None:
            staff_role_ids = await LessonObservationReportRepo.get_active_staff_role_ids(
                db,
                school_id=school_id,
                staff_member_id=staff_member_id,
            )

        task = await StaffTasksRepo.get_task_for_execution(
            db,
            school_id=user.school_id,
            staff_role_ids=staff_role_ids,
            month_item_id=month_item_id,
        )

        if not task:
            raise ValueError("Задача не найдена или нет доступа")

        schema = document.schema_json or {}

        if not schema:
            raise ValueError("Для документа не найден пользовательский шаблон")

        report = await LessonObservationReportRepo.get_by_document_id(
            db,
            task_execution_document_id=document.id,
        )

        if report:
            saved_info, scores, total_score = cls._build_info_from_report(report)
        else:
            saved_info, scores, total_score = await cls._build_initial_info(
                db,
                task=task,
                selected_report=selected_report,
                user=user,
            )

        # ✅ Добавляем категорию учителя к должности
        teacher_category = (
                saved_info.get("teacher_category")
                or saved_info.get("qualification_category")
                or ""
        )

        teacher_position = saved_info.get("teacher_position") or ""

        if teacher_category and teacher_category not in teacher_position:
            saved_info["teacher_position"] = (
                f"{teacher_position}, {teacher_category}"
                if teacher_position
                else teacher_category
            )

        info = LessonObservationInfoDTO(
            **cls.filter_lesson_observation_info_fields(saved_info)
        )

        return LessonObservationFillDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            schema=schema,
            info=info,
            scores=scores,
            total_score=total_score,
            report=report,
            document=document,
        )

    @classmethod
    async def save_lesson_observation_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
            form: FormData,
    ) -> None:

        school_id = cast(int, user.school_id)
        staff_member_id = cast(int | None, user.staff_member_id)

        # 1. Документ отчета
        document = await TemplateReportRepo.get_template_document(
            db,
            selected_report_id=selected_report_id,
            user_id=user.id,
        )

        if not document:
            raise ValueError("Документ отчета не найден или нет доступа")

        if document.month_item_id != month_item_id:
            raise ValueError("Документ не относится к выбранной задаче")

        # 2. Выбранный отчет / учитель
        selected_report = await LessonObservationReportRepo.get_selected_report_by_id(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Выбранный отчет не найден")

        if selected_report.target_kind != "teacher":
            raise ValueError("Для листа наблюдения должен быть выбран учитель")

        # 3. Проверка доступа к задаче
        staff_role_ids = []

        if staff_member_id is not None:
            staff_role_ids = await LessonObservationReportRepo.get_active_staff_role_ids(
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
            raise ValueError("Задача не найдена или нет доступа")

        # 4. Собираем info из формы
        saved_info = {}

        for key, value in form.multi_items():
            if key.startswith("info_"):
                field_name = key.removeprefix("info_")
                saved_info[field_name] = str(value).strip()

        # 5. Собираем scores из формы
        scores: dict[str, int] = {}

        for key, value in form.multi_items():
            if key.startswith("score_"):
                try:
                    scores[key] = int(value)
                except (TypeError, ValueError):
                    scores[key] = 0

        # 6. Итоговый балл
        try:
            total_score = int(form.get("total_score") or 0)
        except (TypeError, ValueError):
            total_score = 0

        # страховка: если total_score не пришел из формы,
        # считаем на backend по выбранным radio
        if total_score == 0 and scores:
            total_score = sum(scores.values())

        criteria_scores = {
            "info": saved_info,
            "scores": scores,
            "total_score": total_score,
        }
        lesson_datetime_raw: str = saved_info.get("lesson_datetime", "")

        lesson_datetime_db = cls.parse_optional_datetime(lesson_datetime_raw)

        if lesson_datetime_db is None:
            raise ValueError("Укажите дату и время урока")

        await LessonObservationReportRepo.upsert_lesson_observation_report(
            db,
            task_execution_document_id=document.id,
            month_item_id=month_item_id,
            criteria_scores=criteria_scores,
            total_score=total_score,

            teacher_full_name=saved_info.get("teacher_full_name", ""),
            teacher_position=saved_info.get("teacher_position", ""),
            teacher_category=saved_info.get("teacher_category", ""),
            teacher_subject=saved_info.get("teacher_subject", ""),

            observer_full_name=saved_info.get("observer_full_name", ""),
            observer_position=saved_info.get("observer_position", ""),

            school_name=saved_info.get("school_name", ""),
            class_name=saved_info.get("class_name", ""),
            group_name=saved_info.get("group_name", ""),

            lesson_datetime=lesson_datetime_db,
            theme=saved_info.get("theme", ""),
            learning_objectives=saved_info.get("learning_objectives", ""),

            lesson_objectives_1=saved_info.get("lesson_objectives_1", ""),
            lesson_objectives_2=saved_info.get("lesson_objectives_2", ""),
            lesson_objectives_3=saved_info.get("lesson_objectives_3", ""),

            feedback=saved_info.get("feedback", ""),
            suggestion_control=saved_info.get("suggestion_control", ""),
        )

        await db.commit()

    @classmethod
    async def save_report(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user_id: int,
            form,
            complete: bool = False,
    ) -> LessonObservationReport:
        """
        Сохранить лист наблюдения (radio 0–3 + данные урока).

        Источник структуры:
        - TaskExecutionDocument.schema_json

        Сохраняет:
        - LessonObservationReport.criteria_scores
        - LessonObservationReport.total
        - LessonObservationReport.col_sum_0..3

        Обновляет:
        - TaskExecutionDocument.status
        """

        # 1. получить документ
        document = await TemplateReportRepo.get_template_document(
            db,
            selected_report_id=selected_report_id,
            user_id=user_id,
        )

        if not document:
            raise ValueError("Документ отчета не найден.")

        if document.month_item_id != month_item_id:
            raise ValueError("Документ не относится к задаче.")

        if not document.schema_json:
            raise ValueError("К документу не применен личный шаблон.")

        # 2. получить или создать LessonObservationReport
        stmt = select(LessonObservationReport).where(
            LessonObservationReport.task_execution_document_id == document.id
        )

        report = await db.scalar(stmt)

        if not report:
            report = LessonObservationReport(
                month_item_id=month_item_id,
                task_execution_document_id=document.id,
                observer_user_id=user_id,
            )
            db.add(report)
            await db.flush()

        # 3. разбор формы
        scores = {}
        info = {}

        total_score = 0
        col_sum = {0: 0, 1: 0, 2: 0, 3: 0}

        for key, value in form.items():

            # --- оценки ---
            if key.startswith("score_"):
                score = int(value)

                scores[key] = score
                total_score += score

                if score in col_sum:
                    col_sum[score] += 1

            # --- данные урока ---
            elif key.startswith("info_"):
                field_code = key.replace("info_", "", 1)
                info[field_code] = str(value).strip()

        # 4. сохранить оценки
        report.criteria_scores = {
            "info": info,
            "scores": scores,
            "total_score": total_score,
            "max_score": document.schema_json.get("max_score", 0),
        }

        # 5. сохранить агрегаты
        report.col_sum_0 = col_sum[0]
        report.col_sum_1 = col_sum[1]
        report.col_sum_2 = col_sum[2]
        report.col_sum_3 = col_sum[3]

        report.total = total_score

        # 6. сохранить основные поля
        report.teacher_full_name = info.get("teacher_full_name")
        report.teacher_position = info.get("teacher_position")
        report.teacher_category = info.get("teacher_category")
        report.teacher_subject = info.get("teacher_subject")

        report.observer_full_name = info.get("observer_full_name")
        report.observer_position = info.get("observer_position")

        report.school_name = info.get("school_name")
        report.class_name = info.get("class_name")
        report.group_name = info.get("group_name")

        report.theme = info.get("theme")
        lesson_datetime_raw = info.get("lesson_datetime")

        if lesson_datetime_raw:
            try:
                report.lesson_datetime = datetime.fromisoformat(lesson_datetime_raw)
            except ValueError:
                report.lesson_datetime = None
        else:
            report.lesson_datetime = None
        report.learning_objectives = info.get("learning_objectives")

        report.lesson_objectives_1 = info.get("lesson_objectives_1")
        report.lesson_objectives_2 = info.get("lesson_objectives_2")
        report.lesson_objectives_3 = info.get("lesson_objectives_3")

        report.suggestion_control = info.get("suggestion_control")
        report.feedback = info.get("feedback")

        # 7. статус документа
        document.status = (
            TaskDocumentStatus.SUBMITTED
            if complete
            else TaskDocumentStatus.DRAFT
        )

        await db.commit()
        return report

    @staticmethod
    async def complete_report(
            db: AsyncSession,
            *,
            selected_report_id: int,
            user: User,
    ):
        report = await LessonObservationReportRepo.get_selected_report_by_id(
            db,
            selected_report_id=selected_report_id,
        )

        if not report:
            raise ValueError("Отчет не найден")

        report.is_completed = True
        report.completed_by_user_id = user.id

        await db.commit()


class LessonObservationService:

    @staticmethod
    async def save_or_complete(
            db: AsyncSession,
            *,
            request: Request,
            form,
            month_item_id: int,
            selected_report_id: int,
            task_execution_document_id: int,
            user,
            templates,
    ):
        action = form.get("action") or "save"

        report = await LessonObservationRepo.get_by_document_id(
            db,
            task_execution_document_id,
        )

        if report and report.submitted_at is not None:
            raise ValueError("Отчет уже подписан. Редактирование запрещено.")

        document = await LessonObservationRepo.get_document_by_id(
            db,
            task_execution_document_id,
        )

        if not document:
            raise ValueError("Документ отчета не найден")

        dto = LessonObservationService._build_dto_from_form(
            form=form,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=task_execution_document_id,
            user=user,
        )

        report = await LessonObservationRepo.save_from_dto(
            db,
            dto=dto,
        )

        await db.flush()
        await db.refresh(report)

        if action == "complete":

            schema = document.schema_json or {}

            report.submitted_at = datetime.now(timezone.utc)

            # -----------------------------------
            # JWT
            # -----------------------------------

            token = ReportSignatureService.create_token(
                report_type="lesson_observation",
                report_id=report.id,
                document_id=report.task_execution_document_id,
                total=report.total,
            )

            # -----------------------------------
            # deactivate old QR
            # -----------------------------------

            await ReportVerifyRepo.deactivate_old_signatures(
                db,
                report_type="lesson_observation",
                report_id=report.id,
                document_id=report.task_execution_document_id,
            )

            # -----------------------------------
            # save token in DB
            # -----------------------------------

            signature = await ReportVerifyRepo.create_signature_token(
                db,
                token=token,
                report_type="lesson_observation",
                report_id=report.id,
                document_id=report.task_execution_document_id,
            )

            # -----------------------------------
            # SHORT QR URL
            # -----------------------------------

            verify_url = str(
                request.url_for(
                    "report_verify_by_code_page",
                    code=signature.code,
                )
            )

            # -----------------------------------
            # QR
            # -----------------------------------

            report.qr_file = ReportSignatureService.generate_qr_file(
                report_type="lesson_observation",
                report_id=report.id,
                verify_url=verify_url,
            )

            # -----------------------------------
            # PDF
            # -----------------------------------

            report.pdf_signed_file = (
                await LessonObservationService._generate_signed_pdf(
                    request=request,
                    templates=templates,
                    report=report,
                    schema=schema,
                )
            )

            document.status = TaskDocumentStatus.SUBMITTED

            db.add(report)
            db.add(document)

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
            month_item_id: int,
            task_execution_document_id: int,
            selected_report_id: int,
            user,
    ) -> LessonObservationFormDTO:
        scores = {}

        for key, value in form.multi_items():
            if key.startswith("score_"):
                criterion_key = key.removeprefix("score_")
                try:
                    scores[criterion_key] = int(value)
                except (TypeError, ValueError):
                    scores[criterion_key] = 0

        def text(name: str) -> str | None:
            raw_value = form.get(f"info_{name}")
            raw_value = str(raw_value).strip() if raw_value is not None else ""
            return raw_value or None

        def integer(name: str) -> int:
            try:
                return int(form.get(name) or 0)
            except (TypeError, ValueError):
                return 0

        return LessonObservationFormDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=task_execution_document_id,

            staff_member_id=integer("staff_member_id") or None,
            observer_user_id=user.id,

            teacher_full_name=text("teacher_full_name"),
            teacher_position=text("teacher_position"),
            teacher_category=text("teacher_category"),
            teacher_subject=text("teacher_subject"),

            observer_full_name=text("observer_full_name"),
            observer_position=text("observer_position"),

            school_name=text("school_name"),
            class_name=text("class_name"),
            group_name=text("group_name"),

            lesson_datetime=LessonObservationReportService.parse_optional_datetime(
                form.get("info_lesson_datetime")
            ),

            theme=text("theme"),
            learning_objectives=text("learning_objectives"),
            lesson_objectives_1=text("lesson_objectives_1"),
            lesson_objectives_2=text("lesson_objectives_2"),
            lesson_objectives_3=text("lesson_objectives_3"),

            lesson_plan_filename=text("lesson_plan_filename"),

            criteria_scores={
                "scores": scores,
                "total_score": integer("total_score"),
            },

            col_sum_0=integer("col_sum_0"),
            col_sum_1=integer("col_sum_1"),
            col_sum_2=integer("col_sum_2"),
            col_sum_3=integer("col_sum_3"),
            total=integer("total_score"),

            suggestion_control=text("suggestion_control"),
            feedback=text("feedback"),
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
        base_dir = Path("media/reports/lesson_observation/pdf")
        base_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = base_dir / f"lesson_observation_{report.id}_signed.pdf"

        qr_file = LessonObservationService._file_to_data_uri(report.qr_file)

        html = templates.get_template(
            "staff/reports/user_templates/lesson_observation_pdf.html"
        ).render(
            request=request,
            report=report,
            schema=schema,
            qr_file=qr_file,
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
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

            await browser.close()

        return str(pdf_path)
