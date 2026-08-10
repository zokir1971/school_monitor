# app/modules/reports/services/task_reports_service.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import ReviewPlace
from app.modules.reports.enums import (
    ReportType,
    TaskCompletionMode,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import (
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)
from app.modules.reports.models_template_reports import (
    CheckingNotebooksReport,
    LessonObservationReport,
)
from app.modules.reports.repositories.checking_notebooks_repo import (
    CheckingNotebooksRepo,
)
from app.modules.reports.repositories.execution_document_repo import (
    ExecutionDocumentRepo,
)
from app.modules.reports.repositories.lesson_observation_repo import (
    LessonObservationRepo,
)
from app.modules.reports.repositories.report_assignment_repo import (
    ReportAssignmentRepo,
)
from app.modules.reports.repositories.task_reports_repo import TaskReportsRepo
from app.modules.reports.rules.control_flow import validate_report_target
from app.modules.reports.schemas.task_reports_dto import (
    ExecutionFinalDocumentDTO,
    TaskReportListItemDTO,
    TaskReportsPageDTO,
)


class TaskReportsService:
    """
    Формирует рабочую страницу отчетов конкретной задачи.

    Сервис только читает и собирает состояние страницы:
    - задачу и роль текущего исполнителя;
    - выбранные отчеты;
    - текущие документы отчетов;
    - назначения исполнителям;
    - общий прогресс;
    - итоговые документы.
    """

    USER_REPORT_ROUTES = {
        ReportType.LESSON_OBSERVATION.value: {
            "fill": "staff_user_lesson_observation_fill_page",
            "pdf": "lesson_observation_pdf_view",
        },
        ReportType.CHECKING_NOTEBOOKS_TABLE.value: {
            "fill": "checking_notebooks_fill_page",
            "pdf": "checking_notebooks_pdf_view",
        },
    }

    SYSTEM_REPORT_ROUTES = {
        ReportType.LESSON_OBSERVATION.value: {
            "fill": "staff_user_lesson_observation_fill_page",
            "pdf": "lesson_observation_pdf_view",
        },
        ReportType.CHECKING_NOTEBOOKS_TABLE.value: {
            "fill": "checking_notebooks_fill_page",
            "pdf": "checking_notebooks_pdf_view",
        },
    }

    @classmethod
    async def get_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> TaskReportsPageDTO:
        """
        Сформировать рабочую страницу отчетов задачи.
        """

        # =========================================================
        # TASK
        # =========================================================

        task = await TaskReportsRepo.get_task_for_reports_page(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if task is None:
            raise ValueError(
                "Задача не найдена или недоступна."
            )

        # =========================================================
        # CURRENT STAFF MEMBER
        # =========================================================

        current_staff_member_id = (
            await TaskReportsRepo
            .get_current_staff_member_id(
                db,
                user_id=user_id,
            )
        )

        if current_staff_member_id is None:
            raise ValueError(
                "Сотрудник школы не найден."
            )

        # =========================================================
        # EXECUTOR CONTEXT
        # =========================================================

        (
            is_primary_executor,
            is_co_executor,
            executor_role_label,
        ) = cls._resolve_executor_context(
            task=task,
            current_staff_member_id=current_staff_member_id,
        )

        # =========================================================
        # TASK INFO
        # =========================================================

        (
            task_title,
            task_topic,
            task_month,
            planned_start,
            planned_end,
            period_text,
        ) = cls._build_task_info(
            task
        )

        # =========================================================
        # EXECUTION DATA
        # =========================================================

        execution_data = (
            await TaskReportsRepo
            .get_execution_data_with_selected_reports(
                db,
                month_item_id=month_item_id,
            )
        )

        # =========================================================
        # COMPLETION CONTEXT
        # =========================================================

        (
            completion_mode_value,
            is_simple_final_document,
            is_final_with_system_reports,
        ) = cls._resolve_completion_context(
            execution_data
        )

        # =========================================================
        # FINAL DOCUMENTS
        # =========================================================

        (
            final_documents,
            current_final_document,
            has_final_document,
            final_document_status,
        ) = await cls._build_final_documents_context(
            db,
            month_item_id=month_item_id,
        )

        # =========================================================
        # REVIEW PLACE
        # =========================================================

        review_place_text = (
            await cls._build_review_place_text(
                db,
                month_item_id=month_item_id,
            )
        )

        # =========================================================
        # REVIEW REPORTS TEXT
        # =========================================================

        review_reports_text = (
            cls._get_review_reports_text(
                execution_data
            )
        )

        # =========================================================
        # NO EXECUTION DATA
        # =========================================================

        if execution_data is None:
            result = cls._build_page_dto(
                month_item_id=month_item_id,
                task=task,

                task_title=task_title,
                task_topic=task_topic,
                task_month=task_month,

                planned_start=planned_start,
                planned_end=planned_end,
                period_text=period_text,

                current_staff_member_id=(
                    current_staff_member_id
                ),

                is_primary_executor=(
                    is_primary_executor
                ),
                is_co_executor=(
                    is_co_executor
                ),
                executor_role_label=(
                    executor_role_label
                ),

                completion_mode_value=(
                    completion_mode_value
                ),

                is_simple_final_document=(
                    is_simple_final_document
                ),

                is_final_with_system_reports=(
                    is_final_with_system_reports
                ),

                pending_reports_count=0,
                waived_reports_count=0,
                all_reports_resolved=False,
                can_manage_report_assignments=False,

                final_documents=final_documents,
                current_final_document=(
                    current_final_document
                ),
                has_final_document=(
                    has_final_document
                ),
                final_document_status=(
                    final_document_status
                ),

                review_reports_text=(
                    review_reports_text
                ),
                review_place_text=(
                    review_place_text
                ),
            )

            return result

        # =========================================================
        # BUILD REPORT ITEMS
        # =========================================================

        result_reports = (
            await cls._build_report_items(
                db,
                execution_data=execution_data,
                is_simple_final_document=(
                    is_simple_final_document
                ),
            )
        )

        # =========================================================
        # APPLY ASSIGNMENTS
        # =========================================================

        await cls._apply_assignments(
            db,
            reports=result_reports,
            current_staff_member_id=(
                current_staff_member_id
            ),
            is_simple_final_document=(
                is_simple_final_document
            ),
        )

        # =========================================================
        # REPORT ASSIGNMENT RESOLUTION
        # =========================================================

        assignment_rows = (
            await ReportAssignmentRepo.list_report_rows(
                db,
                month_item_id=month_item_id,
            )
        )

        (
            pending_reports_count,
            waived_reports_count,
            all_reports_resolved,
        ) = cls._calculate_resolution(
            reports=result_reports,
            assignment_rows=assignment_rows,
            is_simple_final_document=(
                is_simple_final_document
            ),
        )

        can_manage_report_assignments = bool(
            is_primary_executor
            and result_reports
        )

        # =========================================================
        # MY REPORTS
        # =========================================================

        my_reports = [
            report
            for report in result_reports
            if report.is_my_report
        ]

        # =========================================================
        # ALL REPORTS FOR PRIMARY
        # =========================================================

        all_reports = (
            list(result_reports)
            if is_primary_executor
            else []
        )

        # =========================================================
        # PROGRESS
        # =========================================================

        (
            required_reports_count,
            completed_reports_count,
            signed_reports_count,
            all_reports_completed,
            all_reports_signed,
        ) = cls._calculate_progress(
            reports=result_reports,
            is_simple_final_document=(
                is_simple_final_document
            ),
        )

        # =========================================================
        # PAGE DTO
        # =========================================================

        result = cls._build_page_dto(
            month_item_id=month_item_id,
            task=task,

            task_title=task_title,
            task_topic=task_topic,
            task_month=task_month,

            planned_start=planned_start,
            planned_end=planned_end,
            period_text=period_text,

            current_staff_member_id=(
                current_staff_member_id
            ),

            is_primary_executor=(
                is_primary_executor
            ),
            is_co_executor=(
                is_co_executor
            ),
            executor_role_label=(
                executor_role_label
            ),

            # Текущему исполнителю показываем
            # только назначенные ему отчёты.
            my_reports=my_reports,

            # PRIMARY при необходимости имеет
            # полный список для контроля.
            all_reports=all_reports,

            # Совместимое рабочее поле:
            # только отчёты текущего сотрудника.
            reports=my_reports,

            completion_mode_value=(
                completion_mode_value
            ),

            is_simple_final_document=(
                is_simple_final_document
            ),

            is_final_with_system_reports=(
                is_final_with_system_reports
            ),

            required_reports_count=(
                required_reports_count
            ),

            completed_reports_count=(
                completed_reports_count
            ),

            signed_reports_count=(
                signed_reports_count
            ),

            all_reports_completed=(
                all_reports_completed
            ),

            all_reports_signed=(
                all_reports_signed
            ),

            pending_reports_count=(
                pending_reports_count
            ),

            waived_reports_count=(
                waived_reports_count
            ),

            all_reports_resolved=(
                all_reports_resolved
            ),

            can_manage_report_assignments=(
                can_manage_report_assignments
            ),

            final_documents=final_documents,

            current_final_document=(
                current_final_document
            ),

            has_final_document=(
                has_final_document
            ),

            final_document_status=(
                final_document_status
            ),

            review_reports_text=(
                review_reports_text
            ),

            review_place_text=(
                review_place_text
            ),
        )

        # =========================================================
        # TOTAL
        # =========================================================

        return result

    @staticmethod
    def _resolve_executor_context(
            *,
            task,
            current_staff_member_id: int,
    ) -> tuple[bool, bool, str]:
        is_primary_executor = False
        is_co_executor = False

        for assignee in task.assignees or []:
            staff_role = getattr(
                assignee,
                "staff_role",
                None,
            )

            staff_member = (
                getattr(
                    staff_role,
                    "staff_member",
                    None,
                )
                if staff_role
                else None
            )

            if staff_member is None:
                continue

            if (
                    int(staff_member.id)
                    != int(current_staff_member_id)
            ):
                continue

            assignment_kind = getattr(
                assignee,
                "assignment_kind",
                None,
            )

            assignment_kind_value = getattr(
                assignment_kind,
                "value",
                assignment_kind,
            )

            if assignment_kind_value == "primary":
                is_primary_executor = True

            elif assignment_kind_value == "co_executor":
                is_co_executor = True

        if is_primary_executor:
            executor_role_label = (
                "Ответственный исполнитель"
            )

        elif is_co_executor:
            executor_role_label = "Соисполнитель"

        else:
            executor_role_label = "—"

        return (
            is_primary_executor,
            is_co_executor,
            executor_role_label,
        )

    @staticmethod
    def _build_task_info(task):
        task_topic = "—"

        source_row11 = getattr(
            task,
            "source_row11",
            None,
        )

        if source_row11 is not None:
            task_topic = (
                    getattr(
                        source_row11,
                        "topic",
                        None,
                    )
                    or "—"
            )

        task_title = task_topic

        task_month = None

        month_plan = getattr(
            task,
            "month_plan",
            None,
        )

        if month_plan is not None:
            task_month = getattr(
                month_plan,
                "month",
                None,
            )

        planned_start = getattr(
            task,
            "planned_start",
            None,
        )

        planned_end = getattr(
            task,
            "planned_end",
            None,
        )

        period_text = (
            TaskReportsService
            ._build_period_text(
                planned_start=planned_start,
                planned_end=planned_end,
            )
        )

        return (
            task_title,
            task_topic,
            task_month,
            planned_start,
            planned_end,
            period_text,
        )

    @staticmethod
    def _build_period_text(
            *,
            planned_start,
            planned_end,
    ) -> str:
        if planned_start and planned_end:
            return (
                f"{planned_start.strftime('%d.%m.%Y')}"
                f" – "
                f"{planned_end.strftime('%d.%m.%Y')}"
            )

        if planned_start:
            return planned_start.strftime(
                "%d.%m.%Y"
            )

        if planned_end:
            return planned_end.strftime(
                "%d.%m.%Y"
            )

        return "—"

    @staticmethod
    def _resolve_completion_context(
            execution_data,
    ) -> tuple[str | None, bool, bool]:
        completion_mode = (
            getattr(
                execution_data,
                "completion_mode",
                None,
            )
            if execution_data
            else None
        )

        completion_mode_value = getattr(
            completion_mode,
            "value",
            completion_mode,
        )

        is_simple_final_document = (
                completion_mode_value
                == TaskCompletionMode
                .SIMPLE_FINAL_DOCUMENT
                .value
        )

        is_final_with_system_reports = (
                completion_mode_value
                == TaskCompletionMode
                .FINAL_WITH_SYSTEM_REPORTS
                .value
        )

        return (
            completion_mode_value,
            is_simple_final_document,
            is_final_with_system_reports,
        )

    @classmethod
    async def _build_final_documents_context(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> tuple[
        list[ExecutionFinalDocumentDTO],
        ExecutionFinalDocumentDTO | None,
        bool,
        TaskDocumentStatus | None,
    ]:
        final_document_models = (
            await ExecutionDocumentRepo
            .get_final_documents_for_task(
                db,
                month_item_id=month_item_id,
            )
        )

        current_final_document_model = (
            await ExecutionDocumentRepo
            .get_current_final_document_for_task(
                db,
                month_item_id=month_item_id,
            )
        )

        final_documents = [
            cls._build_final_document_dto(
                document
            )
            for document in final_document_models
        ]

        current_final_document = (
            cls._build_final_document_dto(
                current_final_document_model
            )
            if current_final_document_model
            else None
        )

        has_final_document = (
                current_final_document is not None
        )

        final_document_status = (
            current_final_document.status
            if current_final_document
            else None
        )

        return (
            final_documents,
            current_final_document,
            has_final_document,
            final_document_status,
        )

    @staticmethod
    async def _build_review_place_text(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> str:
        review_places = (
            await TaskReportsRepo
            .list_review_places(
                db,
                month_item_id=month_item_id,
            )
        )

        review_place_labels: list[str] = []

        for place in review_places:
            try:
                enum_place = ReviewPlace(place)
                review_place_labels.append(
                    enum_place.label_kz
                )

            except ValueError:
                review_place_labels.append(
                    str(place)
                )

        return ", ".join(
            review_place_labels
        )

    @staticmethod
    def _get_review_reports_text(
            execution_data,
    ) -> str | None:
        if execution_data is None:
            return None

        return (getattr(execution_data, "review_result", None) or
                getattr(execution_data, "review_reports_text", None))

    @classmethod
    async def _build_report_items(
            cls,
            db: AsyncSession,
            *,
            execution_data,
            is_simple_final_document: bool,
    ) -> list[TaskReportListItemDTO]:
        """
        Пакетно сформировать строки отчетов задачи.

        SQL внутри цикла отсутствует:
        - один запрос для документов;
        - один запрос для lesson observation;
        - один запрос для checking notebooks;
        - затем DTO собираются в памяти.
        """

        selected_reports = list(
            execution_data.selected_reports
            or []
        )

        if not selected_reports:
            return []

        # =========================================================
        # SELECTED REPORT IDS
        # =========================================================

        selected_report_ids = [
            int(item.id)
            for item in selected_reports
            if getattr(item, "id", None) is not None
        ]

        if not selected_report_ids:
            return []

        # =========================================================
        # DOCUMENTS — ОДИН ВЫЗОВ
        # =========================================================

        documents_map = (
            await ExecutionDocumentRepo
            .get_current_report_documents_map(
                db,
                selected_report_ids=selected_report_ids,
            )
        )

        # =========================================================
        # DOCUMENT IDS BY REPORT TYPE
        # =========================================================

        lesson_document_ids: list[int] = []
        notebooks_document_ids: list[int] = []

        for item in selected_reports:
            report_type = getattr(
                item,
                "report_type",
                None,
            )

            if report_type is None:
                continue

            raw_code = getattr(
                report_type,
                "code",
                None,
            )

            report_code = (
                raw_code.value
                if hasattr(raw_code, "value")
                else str(raw_code)
            )

            document = documents_map.get(
                int(item.id)
            )

            if document is None:
                continue

            document_id = int(
                document.id
            )

            if (
                    report_code
                    == ReportType.LESSON_OBSERVATION.value
            ):
                lesson_document_ids.append(
                    document_id
                )

            elif (
                    report_code
                    == ReportType.CHECKING_NOTEBOOKS_TABLE.value
            ):
                notebooks_document_ids.append(
                    document_id
                )

        # =========================================================
        # LESSON REPORTS
        # =========================================================

        lesson_reports_map = (
            await LessonObservationRepo
            .get_by_document_ids(
                db,
                document_ids=lesson_document_ids,
            )
        )

        # =========================================================
        # CHECKING NOTEBOOKS REPORTS
        # =========================================================

        notebooks_reports_map = (
            await CheckingNotebooksRepo
            .get_by_document_ids(
                db,
                document_ids=notebooks_document_ids,
            )
        )

        # =========================================================
        # BUILD DTOs — БЕЗ SQL
        # =========================================================

        result_reports: list[
            TaskReportListItemDTO
        ] = []

        for item in selected_reports:
            report = cls._build_report_item(
                item=item,
                documents_map=documents_map,
                lesson_reports_map=lesson_reports_map,
                notebooks_reports_map=notebooks_reports_map,
                is_simple_final_document=(
                    is_simple_final_document
                ),
            )

            if report is not None:
                result_reports.append(
                    report
                )

        return result_reports

    @classmethod
    def _build_report_item(
            cls,
            *,
            item: TaskExecutionSelectedReport,
            documents_map: dict[int, TaskExecutionDocument],
            lesson_reports_map: dict[int, LessonObservationReport],
            notebooks_reports_map: dict[int, CheckingNotebooksReport],
            is_simple_final_document: bool,
    ) -> TaskReportListItemDTO | None:
        """
        Сформировать DTO одного selected_report.

        Метод не выполняет SQL и работает только
        с уже загруженными пакетными словарями.
        """

        report_type = item.report_type

        if report_type is None:
            return None

        raw_code = report_type.code

        report_code = (
            raw_code.value
            if hasattr(
                raw_code,
                "value",
            )
            else str(raw_code)
        )

        if (
                report_code
                == ReportType
                .ANALYTICAL_REFERENCE
                .value
        ):
            return None

        user_routes = (
            cls.USER_REPORT_ROUTES.get(
                report_code,
                {},
            )
        )

        system_routes = (
            cls.SYSTEM_REPORT_ROUTES.get(
                report_code,
                {},
            )
        )

        target_valid, target_error = (
            validate_report_target(
                report_code=report_code,
                target_kind=item.target_kind,
            )
        )

        # =========================================================
        # DOCUMENT FROM MEMORY
        # =========================================================

        document = documents_map.get(
            int(item.id)
        )

        source = (
            document.source
            if document
            else None
        )

        source_value = getattr(
            source,
            "value",
            source,
        )

        is_system_used = bool(
            document
            and source_value
            == TaskDocumentSource
            .GENERATED
            .value
        )

        is_user_template_used = bool(
            document
            and source_value
            == TaskDocumentSource
            .TEMPLATE
            .value
        )

        # =========================================================
        # REPORT MODEL FROM MEMORY
        # =========================================================

        user_report: (
                LessonObservationReport
                | CheckingNotebooksReport
                | None
        ) = None

        if document is not None:
            document_id = int(
                document.id
            )

            if (
                    report_code
                    == ReportType
                    .LESSON_OBSERVATION
                    .value
            ):
                user_report = (
                    lesson_reports_map.get(
                        document_id
                    )
                )

            elif (
                    report_code
                    == ReportType.CHECKING_NOTEBOOKS_TABLE.value
            ):
                user_report = (
                    notebooks_reports_map.get(
                        document_id
                    )
                )

        # =========================================================
        # STATUS
        # =========================================================

        user_report_is_signed = bool(
            user_report
            and getattr(
                user_report,
                "pdf_signed_file",
                None,
            )
        )

        is_completed = bool(
            document
            and (
                    document.status
                    == TaskDocumentStatus.SUBMITTED
                    or user_report_is_signed
            )
        )

        has_draft = bool(
            document
            and not is_completed
            and document.status
            == TaskDocumentStatus.DRAFT
        )

        can_view_system_report = bool(
            is_system_used
            and user_report
            and user_report_is_signed
        )

        can_view_user_report = bool(
            is_user_template_used
            and user_report
            and user_report_is_signed
        )

        display_status = (
            TaskDocumentStatus.SUBMITTED
            if is_completed
            else (
                document.status
                if document
                else None
            )
        )

        # =========================================================
        # DTO
        # =========================================================

        return TaskReportListItemDTO(
            selected_report_id=item.id,

            report_type_id=report_type.id,

            report_code=report_code,

            report_label=(
                    report_type.name_kz
                    or report_type.name_ru
                    or report_code
            ),

            target_kind=item.target_kind,
            target_value=item.target_value,
            target_label=(
                    item.target_label
                    or "—"
            ),

            target_valid=target_valid,
            target_error=target_error,

            document_id=(
                document.id
                if document
                else None
            ),

            document_status=display_status,

            is_filled=(
                    document is not None
            ),

            is_completed=is_completed,
            has_draft=has_draft,

            source=source,

            is_system_used=is_system_used,
            is_user_template_used=(
                is_user_template_used
            ),

            has_system_template=(
                is_system_used
            ),

            has_user_template=(
                is_user_template_used
            ),

            can_view_system_report=(
                can_view_system_report
            ),

            system_fill_route=(
                system_routes.get(
                    "fill"
                )
            ),

            system_pdf_view_route=(
                system_routes.get(
                    "pdf"
                )
                if can_view_system_report
                else None
            ),

            system_report_id=(
                getattr(
                    user_report,
                    "id",
                    None,
                )
                if can_view_system_report
                else None
            ),

            system_pdf_signed_file=(
                getattr(
                    user_report,
                    "pdf_signed_file",
                    None,
                )
                if can_view_system_report
                else None
            ),

            can_view_user_report=(
                can_view_user_report
            ),

            user_fill_route=(
                user_routes.get(
                    "fill"
                )
                if (
                        target_valid
                        and not is_simple_final_document
                )
                else None
            ),

            user_pdf_view_route=(
                user_routes.get(
                    "pdf"
                )
                if target_valid
                else None
            ),

            user_report_id=(
                getattr(
                    user_report,
                    "id",
                    None,
                )
                if user_report
                else None
            ),

            user_pdf_signed_file=(
                getattr(
                    user_report,
                    "pdf_signed_file",
                    None,
                )
                if user_report
                else None
            ),

            custom_template_id=(
                document.custom_template_id
                if document
                else None
            ),

            template_mode=(
                document.template_mode
                if document
                else None
            ),
        )

    @staticmethod
    async def _apply_assignments(
            db: AsyncSession,
            *,
            reports: list[TaskReportListItemDTO],
            current_staff_member_id: int,
            is_simple_final_document: bool,
    ) -> None:
        selected_report_ids = [
            report.selected_report_id
            for report in reports
        ]

        assignments_map = (
            await TaskReportsRepo
            .get_assignment_map(
                db,
                selected_report_ids=(
                    selected_report_ids
                ),
            )
        )

        for report in reports:
            assigned_staff_member_id = (
                assignments_map.get(
                    report.selected_report_id
                )
            )

            report.assigned_staff_member_id = (
                assigned_staff_member_id
            )

            report.is_my_report = (
                    assigned_staff_member_id
                    == current_staff_member_id
            )

            report.can_fill_system_report = bool(
                report.is_my_report
                and report.target_valid
                and report.system_fill_route
                and not is_simple_final_document
                and not report.is_completed
            )

            report.can_fill_user_report = bool(
                report.is_my_report
                and report.target_valid
                and report.user_fill_route
                and not is_simple_final_document
                and not report.is_completed
            )

    @staticmethod
    def _calculate_resolution(
            *,
            reports: list[TaskReportListItemDTO],
            assignment_rows,
            is_simple_final_document: bool,
    ) -> tuple[int, int, bool]:
        """
        Определить состояние обязательств по системным отчётам.

        Для сценария FINAL_WITH_SYSTEM_REPORTS отчёт считается
        закрытым, если:

        - он реально выполнен;
        - либо назначение имеет статус WAIVED.

        PENDING, отсутствие назначения и неизвестный статус
        блокируют завершение задачи.

        Для SIMPLE_FINAL_DOCUMENT системные отчёты не требуются,
        поэтому состояние считается разрешённым.
        """

        if is_simple_final_document:
            return (
                0,
                0,
                True,
            )

        required_reports = [
            report
            for report in reports
            if (
                report.target_valid
                and (
                    report.system_fill_route
                    or report.user_fill_route
                )
            )
        ]

        if not required_reports:
            return (
                0,
                0,
                False,
            )

        assignment_by_report_id = {
            int(row.selected_report_id): row
            for row in assignment_rows
        }

        pending_count = 0
        waived_count = 0

        for report in required_reports:
            # Фактически завершённый отчёт закрывает обязательство
            # независимо от текущего assignment.status.
            #
            # Это важно для старых данных: после миграции их
            # assignment мог остаться PENDING, хотя документ уже
            # был завершён ранее.
            if report.is_completed:
                continue

            assignment = assignment_by_report_id.get(
                int(report.selected_report_id)
            )

            if assignment is None:
                pending_count += 1
                continue

            assignment_status = str(
                getattr(
                    assignment,
                    "assignment_status",
                    "",
                )
                or ""
            ).strip()

            if assignment_status == "waived":
                waived_count += 1
                continue

            # PENDING, пустой или неизвестный статус
            # безопасно считаем незакрытым.
            pending_count += 1

        all_reports_resolved = (
            pending_count == 0
        )

        return (
            pending_count,
            waived_count,
            all_reports_resolved,
        )

    @staticmethod
    def _calculate_progress(
            *,
            reports: list[TaskReportListItemDTO],
            is_simple_final_document: bool,
    ) -> tuple[int, int, int, bool, bool]:
        if is_simple_final_document:
            return (
                0,
                0,
                0,
                True,
                True,
            )

        required_reports = [
            report
            for report in reports
            if (
                    report.target_valid
                    and (
                            report.system_fill_route
                            or report.user_fill_route
                    )
            )
        ]

        completed_reports = [
            report
            for report in required_reports
            if report.is_completed
        ]

        signed_reports = [
            report
            for report in required_reports
            if (
                    report.can_view_system_report
                    or report.can_view_user_report
                    or report.is_completed
            )
        ]

        all_reports_completed = bool(
            required_reports
        ) and (
                                        len(completed_reports)
                                        == len(required_reports)
                                )

        all_reports_signed = bool(
            required_reports
        ) and (
                                     len(signed_reports)
                                     == len(required_reports)
                             )

        return (
            len(required_reports),
            len(completed_reports),
            len(signed_reports),
            all_reports_completed,
            all_reports_signed,
        )

    @staticmethod
    def _build_page_dto(
            *,
            month_item_id: int,
            task,
            task_title,
            task_topic,
            task_month,
            planned_start,
            planned_end,
            period_text,
            current_staff_member_id,
            is_primary_executor,
            is_co_executor,
            executor_role_label,
            completion_mode_value,
            is_simple_final_document,
            is_final_with_system_reports,
            final_documents,
            current_final_document,
            has_final_document,
            final_document_status,
            review_reports_text,
            review_place_text,
            my_reports=None,
            all_reports=None,
            reports=None,
            required_reports_count: int = 0,
            completed_reports_count: int = 0,
            signed_reports_count: int = 0,
            all_reports_completed: bool = False,
            all_reports_signed: bool = False,
            pending_reports_count: int = 0,
            waived_reports_count: int = 0,
            all_reports_resolved: bool = False,
            can_manage_report_assignments: bool = False,
    ) -> TaskReportsPageDTO:
        return TaskReportsPageDTO(
            month_item_id=month_item_id,

            task_title=task_title,
            task_topic=task_topic,
            task_month=task_month,

            planned_start=planned_start,
            planned_end=planned_end,
            period_text=period_text,

            task_status=getattr(
                task,
                "status",
                None,
            ),

            current_staff_member_id=(
                current_staff_member_id
            ),

            is_primary_executor=(
                is_primary_executor
            ),

            is_co_executor=(
                is_co_executor
            ),

            executor_role_label=(
                executor_role_label
            ),

            my_reports=(
                my_reports
                if my_reports is not None
                else []
            ),

            all_reports=(
                all_reports
                if all_reports is not None
                else []
            ),

            reports=(
                list(reports)
                if reports is not None
                else []
            ),

            completion_mode=(
                completion_mode_value
            ),

            is_simple_final_document=(
                is_simple_final_document
            ),

            is_final_with_system_reports=(
                is_final_with_system_reports
            ),

            required_reports_count=(
                required_reports_count
            ),

            completed_reports_count=(
                completed_reports_count
            ),

            signed_reports_count=(
                signed_reports_count
            ),

            all_reports_completed=(
                all_reports_completed
            ),

            all_reports_signed=(
                all_reports_signed
            ),

            pending_reports_count=(
                pending_reports_count
            ),

            waived_reports_count=(
                waived_reports_count
            ),

            all_reports_resolved=(
                all_reports_resolved
            ),

            can_manage_report_assignments=(
                can_manage_report_assignments
            ),

            final_documents=(
                final_documents
            ),

            current_final_document=(
                current_final_document
            ),

            has_final_document=(
                has_final_document
            ),

            final_document_status=(
                final_document_status
            ),

            review_reports_text=(
                review_reports_text
            ),

            review_place_text=(
                review_place_text
            ),
        )

    @staticmethod
    def _build_final_document_dto(
            document,
    ) -> ExecutionFinalDocumentDTO:
        return ExecutionFinalDocumentDTO(
            id=int(document.id),
            status=getattr(
                document,
                "status",
                None,
            ),
            document_type=getattr(
                document,
                "document_type",
                None,
            ),
            original_file_name=getattr(
                document,
                "original_file_name",
                None,
            ),
            file_path=getattr(
                document,
                "file_path",
                None,
            ),
            is_final=bool(
                getattr(
                    document,
                    "is_final",
                    False,
                )
            ),
        )
