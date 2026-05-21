# app/modules/reports/repositories/template_service.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import ReviewPlace
from app.modules.reports.control_flow import validate_report_target
from app.modules.reports.enums import ReportType, TaskDocumentStatus, TaskDocumentSource, TaskCompletionMode
from app.modules.reports.report_repo import ReportRepo
from app.modules.reports.repositories.checking_notebooks_repo import CheckingNotebooksRepo
from app.modules.reports.repositories.lesson_observation_report_repo import LessonObservationRepo
from app.modules.reports.repositories.template_repo import TemplateReportRepo
from app.modules.reports.dtos_template import LessonObservationFormDTO
from app.modules.reports.repositories.user_template_repo import UserReportTemplateRepo
from app.modules.users.models import User


class TemplateReportService:
    """
    Сервис системных шаблонов отчетов.

    Отвечает за бизнес-логику:
    - открыть выбранный шаблон;
    - создать/обновить TaskExecutionDocument;
    - сохранить данные конкретной формы;
    - проверить соответствие report_code нужному шаблону.

    SQL-запросы здесь не пишем — только через TemplateReportRepo.
    """

    @classmethod
    async def get_templates_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> dict:
        USER_REPORT_ROUTES = {
            "lesson_observation": {
                "fill": "staff_user_lesson_observation_fill_page",
                "pdf": "lesson_observation_pdf_view",
            },
            "checking_notebooks_table": {
                "fill": "checking_notebooks_fill_page",
                "pdf": "checking_notebooks_pdf_view",
            },
        }

        task = await TemplateReportRepo.get_task_for_templates_page(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not task:
            raise ValueError("Задача не найдена или недоступна.")

        task_topic = "—"
        if getattr(task, "source_row11", None):
            task_topic = task.source_row11.topic or "—"

        task_month = None
        if getattr(task, "month_plan", None):
            task_month = getattr(task.month_plan, "month", None)

        execution_data = await TemplateReportRepo.get_execution_data_for_templates(
            db,
            month_item_id=month_item_id,
        )

        completion_mode = (
            getattr(execution_data, "completion_mode", None)
            if execution_data
            else None
        )

        completion_mode_value = (
            completion_mode.value
            if hasattr(completion_mode, "value")
            else completion_mode
        )

        is_simple_final_document = (
                completion_mode_value
                == TaskCompletionMode.SIMPLE_FINAL_DOCUMENT.value
        )

        is_final_with_system_reports = (
                completion_mode_value
                == TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS.value
        )

        final_documents = await ReportRepo.get_final_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

        current_final_document = await ReportRepo.get_current_final_document_for_task(
            db,
            month_item_id=month_item_id,
        )

        review_places = await TemplateReportRepo.get_review_places_for_month_item(
            db,
            month_item_id=month_item_id,
        )

        review_place_labels = []

        for place in review_places:
            try:
                enum_place = ReviewPlace(place)
                review_place_labels.append(enum_place.label_kz)
            except ValueError:
                review_place_labels.append(str(place))

        review_place_text = ", ".join(review_place_labels)

        review_reports_text = None

        if execution_data:
            review_reports_text = (
                    getattr(execution_data, "review_result", None)
                    or getattr(execution_data, "review_reports_text", None)
            )

        has_final_document = current_final_document is not None

        final_document_status = (
            current_final_document.status
            if current_final_document
            else None
        )

        if not execution_data:
            return {
                "task": task,
                "task_topic": task_topic,
                "task_month": task_month,
                "reports": [],

                "completion_mode": completion_mode_value,
                "is_simple_final_document": False,
                "is_final_with_system_reports": False,

                "final_documents": final_documents,
                "current_final_document": current_final_document,

                "review_reports_text": review_reports_text,
                "review_place_text": review_place_text,

                "has_final_document": has_final_document,
                "final_document_status": final_document_status,

                "all_reports_signed": False,
                "required_reports_count": 0,
                "signed_reports_count": 0,
            }

        result_reports = []

        for item in execution_data.selected_reports or []:
            report_type = item.report_type

            if not report_type:
                continue

            report_code = (
                report_type.code.value
                if hasattr(report_type.code, "value")
                else str(report_type.code)
            )

            if report_code == ReportType.ANALYTICAL_REFERENCE.value:
                continue

            routes = USER_REPORT_ROUTES.get(report_code, {})

            target_valid, target_error = validate_report_target(
                report_code=report_code,
                target_kind=item.target_kind,
            )

            document = await TemplateReportRepo.get_template_document(
                db,
                selected_report_id=item.id,
                user_id=user_id,
            )

            source = document.source if document else None

            is_system_used = bool(
                document and source == TaskDocumentSource.GENERATED
            )

            is_user_template_used = bool(
                document and source == TaskDocumentSource.TEMPLATE
            )

            has_system_template = is_system_used
            has_user_template = is_user_template_used

            user_report = None

            if document and report_code == ReportType.LESSON_OBSERVATION.value:
                user_report = await LessonObservationRepo.get_by_document_id(
                    db,
                    document.id,
                )

            elif document and report_code == ReportType.CHECKING_NOTEBOOKS_TABLE.value:
                user_report = await CheckingNotebooksRepo.get_by_document_id(
                    db,
                    document_id=document.id,
                )

            user_report_is_signed = bool(
                user_report and user_report.pdf_signed_file
            )

            is_completed = bool(
                document
                and (
                        document.status == TaskDocumentStatus.SUBMITTED
                        or user_report_is_signed
                )
            )

            has_draft = bool(
                document
                and not is_completed
                and document.status == TaskDocumentStatus.DRAFT
            )

            can_view_system_report = bool(
                is_system_used
                and user_report
                and user_report.pdf_signed_file
            )

            can_view_user_report = bool(
                is_user_template_used
                and user_report
                and user_report.pdf_signed_file
            )

            display_status = (
                TaskDocumentStatus.SUBMITTED
                if is_completed
                else document.status if document else None
            )

            if (
                    document
                    and user_report_is_signed
                    and document.status != TaskDocumentStatus.SUBMITTED
            ):
                document.status = TaskDocumentStatus.SUBMITTED
                db.add(document)

            result_reports.append({
                "selected_report_id": item.id,
                "report_type_id": report_type.id,
                "report_code": report_code,
                "report_type": report_code,
                "report_label": (
                        report_type.name_kz
                        or report_type.name_ru
                        or report_code
                ),

                "target_kind": item.target_kind,
                "target_value": item.target_value,
                "target_label": item.target_label,

                "target_valid": target_valid,
                "target_error": target_error,

                "completion_mode": completion_mode_value,
                "is_simple_final_document": is_simple_final_document,
                "is_final_with_system_reports": is_final_with_system_reports,

                "can_prepare_user_report": bool(
                    target_valid
                    and routes.get("fill")
                    and not is_simple_final_document
                ),

                "document": document,
                "document_id": document.id if document else None,
                "document_status": display_status,

                "source": source,

                "is_filled": document is not None,
                "is_completed": is_completed,

                "is_system_used": is_system_used,
                "is_user_template_used": is_user_template_used,

                "has_system_template": has_system_template,
                "has_user_template": has_user_template,
                "has_draft": has_draft,

                "can_view_user_report": can_view_user_report,

                "can_view_system_report": can_view_system_report,
                "system_report": user_report if is_system_used else None,
                "system_report_id": (
                    user_report.id
                    if can_view_system_report
                    else None
                ),
                "system_pdf_view_route": (
                    routes.get("pdf")
                    if can_view_system_report
                    else None
                ),
                "system_pdf_signed_file": (
                    user_report.pdf_signed_file
                    if can_view_system_report
                    else None
                ),

                "user_report": user_report,
                "user_report_id": user_report.id if user_report else None,
                "pdf_signed_file": (
                    user_report.pdf_signed_file
                    if user_report
                    else None
                ),

                "user_fill_route": (
                    routes.get("fill")
                    if target_valid and not is_simple_final_document
                    else None
                ),
                "user_pdf_view_route": (
                    routes.get("pdf")
                    if target_valid
                    else None
                ),

                "lesson_report": (
                    user_report
                    if report_code == ReportType.LESSON_OBSERVATION.value
                    else None
                ),
                "lesson_report_id": (
                    user_report.id
                    if user_report and report_code == ReportType.LESSON_OBSERVATION.value
                    else None
                ),

                "checking_notebooks_report": (
                    user_report
                    if report_code == ReportType.CHECKING_NOTEBOOKS_TABLE.value
                    else None
                ),
                "checking_notebooks_report_id": (
                    user_report.id
                    if user_report and report_code == ReportType.CHECKING_NOTEBOOKS_TABLE.value
                    else None
                ),

                "is_user_template": has_user_template,
                "custom_template_id": (
                    document.custom_template_id
                    if document
                    else None
                ),
                "template_mode": (
                    document.template_mode
                    if document
                    else None
                ),
            })

        if is_simple_final_document:
            required_reports = []
            signed_reports = []
            all_reports_signed = True
        else:
            required_reports = [
                item for item in result_reports
                if item.get("target_valid") and item.get("user_fill_route")
            ]

            signed_reports = [
                item for item in required_reports
                if item.get("can_view_user_report") or item.get("is_completed")
            ]

            all_reports_signed = (
                    bool(required_reports)
                    and len(signed_reports) == len(required_reports)
            )

        await db.commit()

        return {
            "task": task,
            "task_topic": task_topic,
            "task_month": task_month,
            "reports": result_reports,

            "completion_mode": completion_mode_value,
            "is_simple_final_document": is_simple_final_document,
            "is_final_with_system_reports": is_final_with_system_reports,

            "all_reports_signed": all_reports_signed,
            "required_reports_count": len(required_reports),
            "signed_reports_count": len(signed_reports),

            "final_documents": final_documents,
            "current_final_document": current_final_document,

            "review_reports_text": review_reports_text,
            "review_place_text": review_place_text,

            "has_final_document": has_final_document,
            "final_document_status": final_document_status,
        }

    @classmethod
    async def save_lesson_observation_report(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
            form_data: dict,
    ):
        """
        Сохранить форму "Сабақты бақылау парағы".

        Что делает:
        1. Получает выбранный отчет TaskExecutionSelectedReport.
        2. Проверяет, что это именно lesson_observation.
        3. Создает или обновляет TaskExecutionDocument.
        4. Собирает DTO из form_data.
        5. Сохраняет LessonObservationReport.
        6. commit делает здесь, потому что это завершенная операция сохранения.
        """

        selected_report = await TemplateReportRepo.get_selected_report(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Выбранный отчет не найден.")

        if not selected_report.report_type:
            raise ValueError("У выбранного отчета не указан тип.")

        report_code = selected_report.report_type.code

        if report_code != ReportType.LESSON_OBSERVATION.value:
            raise ValueError("Выбранный отчет не является листом наблюдения урока.")

        document = await TemplateReportRepo.create_or_update_template_document(
            db,
            month_item_id=month_item_id,
            selected_report=selected_report,
            user_id=user.id,
        )

        dto = cls._build_lesson_observation_dto(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            document_id=document.id,
            user_id=user.id,
            form_data=form_data,
        )

        report = await TemplateReportRepo.upsert_lesson_observation(
            db,
            document=document,
            data=dto,
        )

        await db.commit()
        return report

    @classmethod
    async def get_lesson_observation_form_data(
            cls,
            db: AsyncSession,
            *,
            selected_report_id: int,
            user: User,
    ) -> dict:
        """
        Получить данные для открытия формы наблюдения урока.

        Используется GET-роутом:
        - получает выбранный отчет;
        - получает связанный TaskExecutionDocument;
        - если документ есть, получает LessonObservationReport;
        - возвращает dict для шаблона.
        """

        selected_report = await TemplateReportRepo.get_selected_report(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Выбранный отчет не найден.")

        if not selected_report.report_type:
            raise ValueError("У выбранного отчета не указан тип.")

        if selected_report.report_type.code != ReportType.LESSON_OBSERVATION.value:
            raise ValueError("Это не шаблон наблюдения урока.")

        document = await TemplateReportRepo.get_template_document(
            db,
            selected_report_id=selected_report_id,
            user_id=user.id,

        )

        lesson_report = None
        if document:
            lesson_report = await TemplateReportRepo.get_lesson_observation(
                db,
                document_id=document.id,
            )

        return {
            "selected_report": selected_report,
            "report_type": selected_report.report_type,
            "document": document,
            "lesson_report": lesson_report,
        }

    @staticmethod
    def _build_lesson_observation_dto(
            *,
            month_item_id: int,
            selected_report_id: int,
            document_id: int,
            user_id: int,
            form_data: dict,
    ) -> LessonObservationFormDTO:
        """
        Собрать LessonObservationFormDTO из form_data.

        Здесь изолируем всю грязную работу с request.form:
        - str -> int;
        - str -> datetime;
        - пустые строки -> None.
        """

        return LessonObservationFormDTO(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=document_id,

            staff_member_id=_to_int(form_data.get("staff_member_id")),
            observer_user_id=user_id,

            teacher_full_name=_clean(form_data.get("teacher_full_name")),
            teacher_position=_clean(form_data.get("teacher_position")),
            teacher_category=_clean(form_data.get("teacher_category")),
            teacher_subject=_clean(form_data.get("teacher_subject")),

            observer_full_name=_clean(form_data.get("observer_full_name")),
            observer_position=_clean(form_data.get("observer_position")),

            school_name=_clean(form_data.get("school_name")),
            class_name=_clean(form_data.get("class_name")),
            group_name=_clean(form_data.get("group_name")),

            lesson_datetime=_to_datetime(form_data.get("lesson_datetime")),

            theme=_clean(form_data.get("theme")),
            learning_objectives=_clean(form_data.get("learning_objectives")),

            lesson_objectives_1=_clean(form_data.get("lesson_objectives_1")),
            lesson_objectives_2=_clean(form_data.get("lesson_objectives_2")),
            lesson_objectives_3=_clean(form_data.get("lesson_objectives_3")),

            lesson_plan_filename=_clean(form_data.get("lesson_plan_filename")),

            col_sum_0=_to_int(form_data.get("col_sum_0")),
            col_sum_1=_to_int(form_data.get("col_sum_1")),
            col_sum_2=_to_int(form_data.get("col_sum_2")),
            col_sum_3=_to_int(form_data.get("col_sum_3")),
            total=_to_int(form_data.get("total")),

            suggestion_control=_clean(form_data.get("suggestion_control")),
            feedback=_clean(form_data.get("feedback")),
        )

    @classmethod
    async def apply_my_template_to_selected_report(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            user: User,
            template_id: int,
    ):
        """
        Применить личный шаблон исполнителя к выбранному отчету задачи.

        Поток:
        1. Получаем selected_report.
        2. Получаем личный шаблон пользователя.
        3. Проверяем, что report_code совпадает.
        4. Создаем/обновляем TaskExecutionDocument.
        5. Копируем содержимое личного шаблона в документ задачи.
        """

        selected_report = await TemplateReportRepo.get_selected_report(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Выбранный отчет не найден.")

        if not selected_report.report_type:
            raise ValueError("У выбранного отчета не указан тип.")

        user_template = await UserReportTemplateRepo.get_user_template(
            db,
            template_id=template_id,
            owner_user_id=user.id,
        )

        if not user_template:
            raise ValueError("Личный шаблон не найден или недоступен.")

        selected_code = selected_report.report_type.code

        if user_template.report_code != selected_code:
            raise ValueError("Этот шаблон относится к другому типу отчета.")

        document = await TemplateReportRepo.create_or_update_template_document(
            db,
            month_item_id=month_item_id,
            selected_report=selected_report,
            user_id=user.id,
        )

        await TemplateReportRepo.apply_custom_template_to_document(
            db,
            document=document,
            user_template=user_template,
        )

        await db.commit()
        return document


def _clean(value) -> str | None:
    """
    Привести значение формы к нормальной строке.

    Пустые строки сохраняем как None,
    чтобы в БД не было мусора вида "".
    """
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _to_int(value) -> int | None:
    """
    Безопасно преобразовать значение формы в int.

    Если значение пустое или некорректное — вернет None.
    """
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value) -> datetime | None:
    """
    Безопасно преобразовать HTML datetime-local в datetime.

    Ожидаемый формат:
    2026-04-27T10:30
    """
    value = _clean(value)
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
