# app/modules/reports/services/system_lesson_observation_service.py
from datetime import datetime, timezone
from pathlib import Path
import base64
import mimetypes

from fastapi import Request
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.enums import ReportType, TaskDocumentStatus
from app.modules.reports.models_template_reports import LessonObservationReport
from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo
from app.modules.reports.repositories.system_lesson_observation_repo import (
    SystemLessonObservationRepo,
)
from app.modules.reports.system_report_dto.system_lesson_observation_dto import (
    SystemLessonObservationFillDTO,
)
from app.modules.reports.system_schemas.lesson_observation_schema import (
    LESSON_OBSERVATION_SCHEMA,
)
from app.modules.reports.utils.report_signature import ReportSignatureService


class SystemLessonObservationService:
    TEMPLATE_MAP = {
        ReportType.LESSON_OBSERVATION.value:
            "staff/reports/template_map/_lesson_observation.html",
    }

    # =========================================================
    # HELPERS
    # =========================================================
    @staticmethod
    def parse_optional_datetime(value: str | None):
        if not value or not str(value).strip():
            return None

        try:
            return datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None

    @staticmethod
    def _normalize_report_code(selected_report) -> str:
        report_code = getattr(selected_report, "report_code", None)

        if hasattr(report_code, "value"):
            report_code = report_code.value

        if not report_code and getattr(selected_report, "report_type", None):
            report_type = selected_report.report_type

            report_code = (
                    getattr(report_type, "code", None)
                    or getattr(report_type, "value", None)
            )

            if hasattr(report_code, "value"):
                report_code = report_code.value

        return report_code or ReportType.LESSON_OBSERVATION.value

    @staticmethod
    def _collect_info(form_data: dict) -> dict:
        result = {}

        for key, value in form_data.items():
            if key.startswith("info_"):
                clean_key = key.removeprefix("info_")
                result[clean_key] = (
                    str(value).strip()
                    if value is not None
                    else ""
                )

        return result

    @staticmethod
    def _collect_scores(form_data: dict) -> dict:
        scores = {}

        for key, value in form_data.items():
            if key.startswith("score_"):
                score_key = key.removeprefix("score_")

                try:
                    scores[score_key] = int(value)
                except (TypeError, ValueError):
                    scores[score_key] = 0

        return scores

    @staticmethod
    def _collect_col_sums(form_data: dict) -> dict:
        col_sums = {}

        for index in range(4):
            raw_value = form_data.get(f"col_sum_{index}")

            try:
                col_sums[str(index)] = int(raw_value or 0)
            except (TypeError, ValueError):
                col_sums[str(index)] = 0

        return col_sums

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    # =========================================================
    # DEFAULT INFO
    # =========================================================

    @classmethod
    async def _build_default_info(
            cls,
            db: AsyncSession,
            *,
            selected_report,
            user,
    ) -> dict:

        observer_staff = getattr(user, "staff_member", None)

        school_id = (
            getattr(observer_staff, "school_id", None)
            if observer_staff
            else None
        )

        observer_staff_id = (
            getattr(observer_staff, "id", None)
            if observer_staff
            else None
        )

        # =====================================================
        # DEFAULTS
        # =====================================================

        teacher_name = (
                getattr(selected_report, "target_label", None)
                or ""
        )

        teacher_position = ""
        teacher_category = ""
        teacher_subject = ""

        target_kind = str(
            getattr(selected_report, "target_kind", "") or ""
        ).lower()

        target_value = getattr(selected_report, "target_value", None)

        # =====================================================
        # TEACHER
        # =====================================================

        if (
                target_value
                and target_kind in {"teacher", "staff_member", "teacher_staff"}
        ):

            try:
                teacher_id = int(target_value)
            except (TypeError, ValueError):
                teacher_id = None

            if teacher_id:
                teacher_info = (
                    await SystemLessonObservationRepo.get_teacher_info(
                        db,
                        teacher_id=teacher_id,
                    )
                )

                if teacher_info:
                    teacher_name = teacher_info.full_name or teacher_name

                    position_text = teacher_info.position_text or ""
                    qualification_category = teacher_info.qualification_category or ""

                    teacher_position = position_text

                    if qualification_category:
                        teacher_position = (
                            f"{position_text}, {qualification_category}"
                            if position_text
                            else qualification_category
                        )

                    teacher_category = qualification_category
                    teacher_subject = teacher_info.subject or ""

        # =====================================================
        # OBSERVER
        # =====================================================

        observer_name = (
                getattr(user, "full_name", None)
                or getattr(user, "name", None)
                or ""
        )

        observer_position = ""

        if school_id and observer_staff_id:
            observer_position = (
                await SystemLessonObservationRepo.get_controller_post(
                    db,
                    school_id=school_id,
                    staff_member_id=observer_staff_id,
                )
            )

        # =====================================================
        # SCHOOL
        # =====================================================

        school_name = ""

        school = (
            getattr(observer_staff, "school", None)
            if observer_staff
            else None
        )

        if school:
            school_name = (
                    getattr(school, "name", None)
                    or getattr(school, "name_kz", None)
                    or getattr(school, "title", None)
                    or ""
            )

        # =====================================================
        # RESULT
        # =====================================================

        return {
            "teacher_name": teacher_name,
            "teacher_position": teacher_position,
            "teacher_category": teacher_category,
            "subject": teacher_subject,

            "observer_name": observer_name,
            "observer_position": observer_position,

            "school_name": school_name,
        }

    # =========================================================
    # GET PAGE
    # =========================================================

    @classmethod
    async def get_fill_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user,
    ) -> SystemLessonObservationFillDTO:

        selected_report = (
            await SystemLessonObservationRepo.get_selected_report(
                db,
                selected_report_id=selected_report_id,
            )
        )

        if not selected_report:
            raise ValueError("Системный отчет не найден")

        report_code = cls._normalize_report_code(selected_report)

        if report_code != ReportType.LESSON_OBSERVATION.value:
            raise ValueError(
                "Для этого типа системного отчета форма пока не реализована"
            )

        schema = LESSON_OBSERVATION_SCHEMA

        document = (
            await SystemLessonObservationRepo.get_or_create_document(
                db,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                user_id=user.id,
                report_code=report_code,
                report_label="Лист наблюдения урока",
                schema_json=schema,
            )
        )

        lesson_report = (
            await SystemLessonObservationRepo
            .get_or_create_lesson_observation_report(
                db,
                month_item_id=month_item_id,
                document_id=document.id,
                observer_user_id=user.id,
            )
        )

        criteria_scores = (
            lesson_report.criteria_scores
            if lesson_report.criteria_scores
            else {}
        )

        saved_info = dict(criteria_scores.get("info") or {})

        default_info = await cls._build_default_info(
            db,
            selected_report=selected_report,
            user=user,
        )

        for key, value in default_info.items():
            if not saved_info.get(key):
                saved_info[key] = value

        scores = criteria_scores.get("scores") or {}
        col_sums = criteria_scores.get("col_sums") or {}

        total_score = cls._safe_int(
            criteria_scores.get("total_score")
            or lesson_report.total
        )

        readonly = bool(
            document.status == TaskDocumentStatus.SUBMITTED
        )

        return SystemLessonObservationFillDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,

            selected_report=selected_report,

            report_type=report_code,
            report_code=report_code,

            document=document,

            is_completed=readonly,
            readonly=readonly,

            lesson_report=lesson_report,

            schema=schema,

            criteria=schema.get("criteria", []),
            score_scale=schema.get("score_scale", [0, 1, 2, 3]),

            max_score=schema.get("max_score", 102),

            template_partial=cls.TEMPLATE_MAP[report_code],

            criteria_scores=criteria_scores,

            saved_info=saved_info,
            scores=scores,
            col_sums=col_sums,

            teacher_name=saved_info.get("teacher_name", ""),
            teacher_position=saved_info.get("teacher_position", ""),
            teacher_category=saved_info.get("teacher_category", ""),
            subject=saved_info.get("subject", ""),

            observer_name=saved_info.get("observer_name", ""),
            observer_position=saved_info.get("observer_position", ""),

            school_name=saved_info.get("school_name", ""),

            class_name=saved_info.get("class_name", ""),
            group_name=saved_info.get("group_name", ""),

            lesson_datetime=saved_info.get("lesson_datetime"),

            theme=saved_info.get("theme", ""),
            learning_objectives=saved_info.get(
                "learning_objectives",
                "",
            ),

            lesson_objectives_1=saved_info.get(
                "lesson_objectives_1",
                "",
            ),
            lesson_objectives_2=saved_info.get(
                "lesson_objectives_2",
                "",
            ),
            lesson_objectives_3=saved_info.get(
                "lesson_objectives_3",
                "",
            ),

            total_score=total_score,

            feedback=criteria_scores.get("feedback", ""),
            suggestion_control=criteria_scores.get(
                "suggestion",
                "",
            ),
        )

    # =========================================================
    # SAVE
    # =========================================================

    @classmethod
    async def save_lesson_observation(
            cls,
            db: AsyncSession,
            *,
            request: Request,
            templates,
            month_item_id: int,
            selected_report_id: int,
            user,
            form_data: dict,
    ) -> LessonObservationReport:

        selected_report = await SystemLessonObservationRepo.get_selected_report(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Системный отчет не найден")

        report_code = cls._normalize_report_code(selected_report)

        document = await SystemLessonObservationRepo.get_or_create_document(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user_id=user.id,
            report_code=report_code,
            report_label="Лист наблюдения урока",
            schema_json=LESSON_OBSERVATION_SCHEMA,
        )

        if document.status == TaskDocumentStatus.SUBMITTED:
            raise ValueError("Отчет уже подписан. Редактирование запрещено.")

        lesson_report = await SystemLessonObservationRepo.get_or_create_lesson_observation_report(
            db,
            month_item_id=month_item_id,
            document_id=document.id,
            observer_user_id=user.id,
        )

        info = cls._collect_info(form_data)
        required_fields = {
            "teacher_name": "Педагогтің ТАӘ",
            "observer_name": "Бақылаушының ТАӘ",
            "teacher_position": "Лауазымы",
            "observer_position": "Бақылаушы лауазымы",
            "subject": "Пән",
            "school_name": "Мектеп",
            "class_name": "Сынып",
            "group_name": "Топ",
            "lesson_datetime": "Бақылау күні",
        }

        for field_key, field_label in required_fields.items():

            value = str(info.get(field_key) or "").strip()

            if not value:
                raise ValueError(
                    f"Міндетті өріс толтырылмаған: {field_label}"
                )

        default_info = await cls._build_default_info(
            db,
            selected_report=selected_report,
            user=user,
        )

        for key, value in default_info.items():
            if not info.get(key):
                info[key] = value

        scores = cls._collect_scores(form_data)
        if not scores:
            raise ValueError(
                "Не выбраны критерии оценивания."
            )

        if all(int(v or 0) == 0 for v in scores.values()):
            raise ValueError(
                "Необходимо заполнить оценивание."
            )

        # ВАЖНО: пересчитываем на сервере, а не берем из JS
        col_sums = {
            "0": 0,
            "1": 0,
            "2": 0,
            "3": 0,
        }

        total_score = 0

        for score_value in scores.values():
            score = cls._safe_int(score_value)

            if score < 0:
                score = 0

            if score > 3:
                score = 3

            key = str(score)
            col_sums[key] += 1

            total_score += score

        feedback = str(form_data.get("feedback") or "").strip()
        suggestion = str(form_data.get("suggestion") or "").strip()

        criteria_scores = {
            "info": info,
            "scores": scores,
            "col_sums": col_sums,
            "total_score": total_score,
            "feedback": feedback,
            "suggestion": suggestion,
        }

        lesson_report.col_sum_0 = col_sums.get("0", 0)
        lesson_report.col_sum_1 = col_sums.get("1", 0)
        lesson_report.col_sum_2 = col_sums.get("2", 0)
        lesson_report.col_sum_3 = col_sums.get("3", 0)

        lesson_report.total = total_score
        lesson_report.criteria_scores = criteria_scores

        lesson_report.teacher_full_name = info.get("teacher_name", "")
        lesson_report.teacher_position = info.get("teacher_position", "")
        lesson_report.teacher_category = info.get("teacher_category", "")
        lesson_report.teacher_subject = info.get("subject", "")

        lesson_report.observer_full_name = info.get("observer_name", "")
        lesson_report.observer_position = info.get("observer_position", "")

        lesson_report.school_name = info.get("school_name", "")
        lesson_report.class_name = info.get("class_name", "")
        lesson_report.group_name = info.get("group_name", "")
        lesson_report.lesson_datetime = cls.parse_optional_datetime(info.get("lesson_datetime"))

        lesson_report.theme = info.get("theme", "")
        lesson_report.learning_objectives = info.get("learning_objectives", "")
        lesson_report.lesson_objectives_1 = info.get("lesson_objectives_1", "")
        lesson_report.lesson_objectives_2 = info.get("lesson_objectives_2", "")
        lesson_report.lesson_objectives_3 = info.get("lesson_objectives_3", "")

        lesson_report.feedback = feedback
        lesson_report.suggestion_control = suggestion

        action = form_data.get("action")

        if action == "complete":
            schema = document.schema_json or LESSON_OBSERVATION_SCHEMA

            db.add(lesson_report)
            await db.flush()
            await db.refresh(lesson_report)

            lesson_report.submitted_at = datetime.now(timezone.utc)

            token = ReportSignatureService.create_token(
                report_type="lesson_observation",
                report_id=lesson_report.id,
                document_id=document.id,
                total=lesson_report.total,
            )

            await ReportVerifyRepo.deactivate_old_signatures(
                db,
                report_type="lesson_observation",
                report_id=lesson_report.id,
                document_id=document.id,
            )

            signature = await ReportVerifyRepo.create_signature_token(
                db,
                token=token,
                report_type="lesson_observation",
                report_id=lesson_report.id,
                document_id=document.id,
            )

            verify_url = str(
                request.url_for(
                    "report_verify_by_code_page",
                    code=signature.code,
                )
            )

            lesson_report.qr_file = ReportSignatureService.generate_qr_file(
                report_type="lesson_observation",
                report_id=lesson_report.id,
                verify_url=verify_url,
            )

            if not lesson_report.qr_file:
                raise ValueError("QR файл не создан.")

            lesson_report.pdf_signed_file = await cls._generate_signed_pdf(
                request=request,
                templates=templates,
                report=lesson_report,
                schema=schema,
            )

            if not lesson_report.pdf_signed_file:
                raise ValueError("PDF файл не создан.")

            document.status = TaskDocumentStatus.SUBMITTED
        else:
            document.status = TaskDocumentStatus.DRAFT

        db.add(lesson_report)
        db.add(document)

        await db.commit()

        await db.refresh(lesson_report)
        await db.refresh(document)

        return lesson_report

    @classmethod
    async def _generate_signed_pdf(
            cls,
            *,
            request: Request,
            templates,
            report,
            schema: dict | None = None,
    ) -> str:

        if not report.qr_file:
            raise ValueError(
                "QR файл отсутствует."
            )

        base_dir = Path(
            "media/reports/lesson_observation/pdf"
        )

        base_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        pdf_path = (
                base_dir /
                f"lesson_observation_{report.id}_signed.pdf"
        )

        qr_file = cls._file_to_data_uri(report.qr_file)

        criteria_scores = report.criteria_scores or {}

        html = templates.get_template(
            "staff/reports/user_templates/lesson_observation_pdf.html"
        ).render(
            request=request,
            report=report,
            schema=schema or {},

            info=criteria_scores.get("info", {}),  # добавь это
            saved_info=criteria_scores.get("info", {}),

            scores=criteria_scores.get("scores", {}),
            col_sums=criteria_scores.get("col_sums", {}),
            total_score=criteria_scores.get(
                "total_score",
                report.total or 0,
            ),

            feedback=criteria_scores.get("feedback", ""),
            suggestion=criteria_scores.get("suggestion", ""),

            qr_file=qr_file,
        )

        try:
            async with async_playwright() as p:

                browser = await p.chromium.launch(
                    headless=True
                )

                page = await browser.new_page()

                await page.set_content(
                    html,
                    wait_until="networkidle",
                )

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

        except Exception as e:
            raise ValueError(
                f"Ошибка генерации PDF: {str(e)}"
            )

        # проверка что файл реально создался
        if not pdf_path.exists():
            raise ValueError(
                "PDF файл не был создан."
            )

        return str(pdf_path)

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
