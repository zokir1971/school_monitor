# app/modules/reviews/services/review_result_service.py

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import ReviewPlace
from app.modules.planning.models_month_plan import SchoolMonthPlanItem
from app.modules.reports.enums import DocumentType
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reviews.review_result_dto import (
    ReviewResultAccessDTO,
    ReviewResultHistoryItemDTO,
    ReviewResultListItemDTO,
    ReviewResultListPageDTO,
    ReviewResultTaskDetailDTO, ReviewResultDocumentDTO,
)
from app.modules.reviews.repositories.review_result_repository import (
    ReviewResultRepository,
)
from app.modules.reviews.models_task_review import (
    SchoolMonthPlanItemReviewResult,
)
from app.modules.staff.models_staff_school import SchoolStaffMember
from app.modules.users.enums import UserRole
from app.modules.users.models import User


MONTH_LABELS = {
    8: "Тамыз (Август)",
    9: "Қыркүйек (Сентябрь)",
    10: "Қазан (Октябрь)",
    11: "Қараша (Ноябрь)",
    12: "Желтоқсан (Декабрь)",
    1: "Қаңтар (Январь)",
    2: "Ақпан (Февраль)",
    3: "Наурыз (Март)",
    4: "Сәуір (Апрель)",
    5: "Мамыр (Май)",
    6: "Маусым (Июнь)",
}


class ReviewResultService:
    """
    Сервис просмотра результатов рассмотрения задач.

    Сервис:

    - определяет школу пользователя;
    - определяет режим администратора или сотрудника;
    - проверяет и нормализует фильтры;
    - вызывает ReviewResultRepository;
    - преобразует ORM-модели в DTO.

    SQL-запросы в сервисе отсутствуют.
    """

    # ==========================================================
    # 1. Страница списка
    # ==========================================================

    @classmethod
    async def get_list_page_data(
            cls,
            db: AsyncSession,
            *,
            user: User,
            year: int | None = None,
            month: int | None = None,
            review_place: ReviewPlace | str | None = None,
            reviewed: bool | str | None = None,
            task_review_id: int | None = None,
            selected_school_id: int | None = None,
    ) -> ReviewResultListPageDTO:
        """
        Формирует данные страницы списка результатов.

        SCHOOL_ADMIN:
            видит все подходящие задачи школы.

        SCHOOL_STAFF:
            видит задачи, где он является ответственным,
            основным исполнителем или соисполнителем.

        SUPERUSER:
            должен передать selected_school_id.
        """

        access = cls._build_access_context(
            user,
            selected_school_id=selected_school_id,
        )

        active_plan = (
            await ReviewResultRepository.get_active_school_plan(
                db,
                school_id=access.school_id,
            )
        )

        if active_plan is None:
            raise ValueError(
                "У выбранной школы отсутствует активный годовой план."
            )

        academic_year = str(
            active_plan.academic_year or ""
        ).strip()

        academic_year_label = (
            academic_year
            if academic_year
            else "Не указан"
        )

        # ----------------------------------------------------------
        # Выбранные фильтры
        # ----------------------------------------------------------

        selected_review_place = cls._parse_review_place(
            review_place
        )

        selected_reviewed = cls._parse_reviewed_filter(
            reviewed
        )

        # ----------------------------------------------------------
        # Все места рассмотрения
        # ----------------------------------------------------------

        review_places: list[dict[str, str]] = [
            {
                "value": str(
                    getattr(place, "value")
                ),
                "label": str(
                    getattr(place, "label_kz")
                ),
            }
            for place in ReviewPlace
        ]

        # ----------------------------------------------------------
        # Доступные годы
        # ----------------------------------------------------------

        available_years = (
            await ReviewResultRepository.get_available_years(
                db,
                school_plan_id=active_plan.id,
            )
        )

        selected_year = cls._resolve_selected_year(
            requested_year=year,
            available_years=available_years,
        )

        # ----------------------------------------------------------
        # Доступные месяцы
        # ----------------------------------------------------------

        available_months: list[int] = []

        if selected_year is not None:
            available_months = (
                await ReviewResultRepository.get_available_months(
                    db,
                    school_plan_id=active_plan.id,
                    year=selected_year,
                )
            )

        available_month_options = [
            {
                "num": month_number,
                "label": MONTH_LABELS.get(
                    month_number,
                    str(month_number),
                ),
            }
            for month_number in available_months
        ]

        selected_month = cls._resolve_selected_month(
            requested_month=month,
            available_months=available_months,
        )

        # ----------------------------------------------------------
        # Доступные протоколы
        # ----------------------------------------------------------

        available_protocol_models = []

        if (
                selected_year is not None
                and selected_review_place is not None
        ):
            available_protocol_models = (
                await ReviewResultRepository.get_available_protocols(
                    db,
                    school_plan_id=active_plan.id,
                    year=selected_year,
                    month=selected_month,
                    review_place=selected_review_place,
                    participant_user_id=access.participant_user_id,
                    participant_staff_id=access.participant_staff_id,
                )
            )

        available_protocols: list[
            dict[str, int | str]
        ] = []

        for protocol in available_protocol_models:
            protocol_number = cls._normalize_text(
                protocol.protocol_number
            )

            protocol_date = protocol.protocol_date

            label_parts = ["Протокол"]

            if protocol_number:
                label_parts.append(
                    f"№{protocol_number}"
                )

            if protocol_date is not None:
                label_parts.append(
                    "от "
                    f"{protocol_date.strftime('%d.%m.%Y')}"
                )

            available_protocols.append(
                {
                    "id": protocol.id,
                    "label": " ".join(label_parts),
                }
            )

        available_protocol_ids = {
            int(protocol["id"])
            for protocol in available_protocols
        }

        selected_task_review_id = (
            task_review_id
            if (
                    task_review_id is not None
                    and task_review_id in available_protocol_ids
            )
            else None
        )

        # Выбранный протокол всегда означает,
        # что задача уже рассмотрена.
        if selected_task_review_id is not None:
            selected_reviewed = True

        # ----------------------------------------------------------
        # Получение задач
        # ----------------------------------------------------------

        items: list[SchoolMonthPlanItem] = []

        if (
                selected_year is not None
                and selected_review_place is not None
        ):
            items = (
                await ReviewResultRepository.get_available_tasks(
                    db,
                    school_plan_id=active_plan.id,
                    year=selected_year,
                    month=selected_month,
                    review_place=selected_review_place,
                    reviewed=selected_reviewed,
                    task_review_id=selected_task_review_id,
                    participant_user_id=(
                        access.participant_user_id
                    ),
                    participant_staff_id=(
                        access.participant_staff_id
                    ),
                )
            )

        item_dtos = [
            cls._build_list_item_dto(
                item,
                review_place=selected_review_place,
                current_user_id=(
                    access.participant_user_id
                ),
                current_staff_member_id=(
                    access.participant_staff_id
                ),
            )
            for item in items
        ]

        reviewed_count = sum(
            1
            for item in item_dtos
            if item.is_reviewed
        )

        total_count = len(item_dtos)

        return ReviewResultListPageDTO(
            school_plan_id=active_plan.id,
            school_id=access.school_id,

            academic_year_label=academic_year_label,

            is_admin=access.is_admin,

            selected_year=selected_year,
            selected_month=selected_month,
            selected_review_place=selected_review_place,
            selected_reviewed=selected_reviewed,
            selected_task_review_id=selected_task_review_id,

            available_years=available_years,
            available_months=available_month_options,
            review_places=review_places,
            available_protocols=available_protocols,

            items=item_dtos,

            total_count=total_count,
            reviewed_count=reviewed_count,
            not_reviewed_count=(
                    total_count - reviewed_count
            ),
        )

    # ==========================================================
    # 2. Детальная страница задачи
    # ==========================================================

    @classmethod
    async def get_task_detail_page_data(
            cls,
            db: AsyncSession,
            *,
            user: User,
            month_item_id: int,
            review_place: ReviewPlace | str | None = None,
            selected_school_id: int | None = None,
    ) -> ReviewResultTaskDetailDTO:
        """
        Формирует детальную страницу задачи с историей рассмотрений.

        Задача ищется в пределах доступной пользователю школы,
        независимо от статуса годового плана.
        """

        access = cls._build_access_context(
            user,
            selected_school_id=selected_school_id,
        )

        selected_review_place = cls._parse_review_place(
            review_place
        )

        item = await ReviewResultRepository.get_task_with_review_history(
            db,
            month_item_id=month_item_id,
            school_id=access.school_id,
            review_place=selected_review_place,
            participant_user_id=access.participant_user_id,
            participant_staff_id=access.participant_staff_id,
        )

        if item is None:
            raise ValueError(
                "Задача не найдена или у пользователя нет доступа."
            )

        # ----------------------------------------------------------
        # Документы выполнения задачи
        # ----------------------------------------------------------

        documents = (
            await ReviewResultRepository.get_current_task_documents(
                db,
                month_item_id=item.id,
            )
        )

        final_document = cls._build_final_document_dto(
            documents
        )

        execution_reports = cls._build_execution_report_dtos(
            documents
        )

        # ----------------------------------------------------------
        # История рассмотрений
        # ----------------------------------------------------------

        relevant_results = cls._get_relevant_review_results(
            item,
            review_place=selected_review_place,
        )

        protocol_document_ids: list[int] = [
            cast(int, result.protocol_document_id)
            for result in relevant_results
            if result.protocol_document_id is not None
        ]

        protocol_documents: dict[int, TaskExecutionDocument] = (
            await ReviewResultRepository.get_protocol_documents_by_ids(
                db,
                document_ids=protocol_document_ids,
            )
        )

        history: list[ReviewResultHistoryItemDTO] = []

        for result in cls._sort_review_results(
                relevant_results
        ):
            protocol_document_id = (
                cast(int, result.protocol_document_id)
                if result.protocol_document_id is not None
                else None
            )

            protocol_document = (
                protocol_documents.get(protocol_document_id)
                if protocol_document_id is not None
                else None
            )

            history.append(
                cls._build_history_item_dto(
                    result,
                    protocol_document=protocol_document,
                )
            )

        month_plan = item.month_plan

        return ReviewResultTaskDetailDTO(
            month_item_id=item.id,

            task_name=cls._get_task_name(item),
            task_goal=cls._get_task_goal(item),
            responsibles_text=cls._get_responsibles_text(item),

            responsible_name=cls._get_responsible_name(item),

            participation_label=cls._build_participation_label(
                item,
                current_user_id=access.participant_user_id,
                current_staff_member_id=access.participant_staff_id,
            ),

            year=month_plan.year,
            month=month_plan.month,
            week_of_month=item.week_of_month,

            planned_start=item.planned_start,
            planned_end=item.planned_end,

            planned_period_text=cls._build_planned_period_text(
                item.planned_start,
                item.planned_end,
            ),

            executed_at=item.executed_at,

            task_status=cls._get_enum_value(
                item.status
            ),

            task_status_label=cls._get_enum_label(
                item.status
            ),

            notes=cls._normalize_text(
                item.notes
            ),

            review_place=selected_review_place,

            review_place_label=(
                cls._get_enum_label(selected_review_place)
                if selected_review_place is not None
                else None
            ),

            history=history,
            review_count=len(history),

            final_document=final_document,
            execution_reports=execution_reports,
        )

    # ==========================================================
    # 3. Получение конкретного результата
    # ==========================================================

    @classmethod
    async def get_result_detail(
            cls,
            db: AsyncSession,
            *,
            user: User,
            review_result_id: int,
            selected_school_id: int | None = None,
    ) -> ReviewResultHistoryItemDTO:
        """
        Получает конкретный результат рассмотрения с проверкой доступа.
        """

        access = cls._build_access_context(
            user,
            selected_school_id=selected_school_id,
        )

        result = await ReviewResultRepository.get_result_by_id(
            db,
            review_result_id=review_result_id,
            school_id=access.school_id,
            participant_user_id=access.participant_user_id,
            participant_staff_id=access.participant_staff_id,
        )

        if result is None:
            raise ValueError(
                "Результат рассмотрения не найден "
                "или у пользователя нет доступа."
            )

        protocol_document_id = (
            cast(int, result.protocol_document_id)
            if result.protocol_document_id is not None
            else None
        )

        protocol_document: TaskExecutionDocument | None = None

        if protocol_document_id is not None:
            protocol_documents = (
                await ReviewResultRepository.get_protocol_documents_by_ids(
                    db,
                    document_ids=[protocol_document_id],
                )
            )

            protocol_document = protocol_documents.get(
                protocol_document_id
            )

        return cls._build_history_item_dto(
            result,
            protocol_document=protocol_document,
        )

    # ==========================================================
    # 4. Контекст доступа
    # ==========================================================

    @staticmethod
    def _build_access_context(
            user: User,
            *,
            selected_school_id: int | None,
    ) -> ReviewResultAccessDTO:
        """
        Преобразует текущего пользователя в параметры доступа
        для репозитория.
        """

        if user.role == UserRole.SUPERUSER:
            school_id_value = (
                selected_school_id
                if selected_school_id is not None
                else user.school_id
            )

            if school_id_value is None:
                raise ValueError(
                    "Для суперпользователя необходимо выбрать школу."
                )

            return ReviewResultAccessDTO(
                school_id=cast(int, school_id_value),
                is_admin=True,
                participant_user_id=None,
                participant_staff_id=None,
            )

        if user.school_id is None:
            raise ValueError(
                "У пользователя не определена школа."
            )

        school_id = cast(
            int,
            user.school_id,
        )

        if user.role == UserRole.SCHOOL_ADMIN:
            return ReviewResultAccessDTO(
                school_id=school_id,
                is_admin=True,
                participant_user_id=None,
                participant_staff_id=None,
            )

        if user.role == UserRole.SCHOOL_STAFF:
            if user.staff_member_id is None:
                raise ValueError(
                    "Для пользователя не найден профиль сотрудника."
                )

            return ReviewResultAccessDTO(
                school_id=school_id,
                is_admin=False,
                participant_user_id=cast(
                    int,
                    user.id,
                ),
                participant_staff_id=cast(
                    int,
                    user.staff_member_id,
                ),
            )

        raise PermissionError(
            "У пользователя нет доступа к результатам рассмотрения."
        )

    # ==========================================================
    # 5. Построение строки списка
    # ==========================================================

    @classmethod
    def _build_list_item_dto(
        cls,
        item: SchoolMonthPlanItem,
        *,
        review_place: ReviewPlace,
        current_user_id: int | None,
        current_staff_member_id: int | None,
    ) -> ReviewResultListItemDTO:
        month_plan = item.month_plan

        relevant_results = cls._get_relevant_review_results(
            item,
            review_place=review_place,
        )

        latest_result = cls._get_latest_review_result(
            relevant_results
        )

        latest_task_review = (
            latest_result.task_review
            if latest_result is not None
            else None
        )

        return ReviewResultListItemDTO(
            month_item_id=item.id,

            task_name=cls._get_task_name(item),
            task_goal=cls._get_task_goal(item),

            responsible_name=cls._get_responsible_name(item),

            participation_label=cls._build_participation_label(
                item,
                current_user_id=current_user_id,
                current_staff_member_id=current_staff_member_id,
            ),

            year=month_plan.year,
            month=month_plan.month,
            week_of_month=item.week_of_month,

            planned_start=item.planned_start,
            planned_end=item.planned_end,

            planned_period_text=cls._build_planned_period_text(
                item.planned_start,
                item.planned_end,
            ),

            task_status=cls._get_enum_value(
                item.status
            ),

            task_status_label=cls._get_enum_label(
                item.status
            ),

            review_place=cls._get_enum_value(
                review_place
            ),

            review_place_label=cls._get_enum_label(
                review_place
            ),

            is_reviewed=bool(relevant_results),
            review_count=len(relevant_results),

            latest_review_result_id=(
                latest_result.id
                if latest_result is not None
                else None
            ),

            latest_review_status=(
                cls._get_enum_value(
                    latest_result.status
                )
                if latest_result is not None
                else None
            ),

            latest_review_status_label=(
                cls._get_enum_label(
                    latest_result.status
                )
                if latest_result is not None
                else None
            ),

            latest_reviewed_at=(
                latest_result.reviewed_at
                if latest_result is not None
                else None
            ),

            latest_review_comment=(
                cls._normalize_text(
                    latest_result.comment
                )
                if latest_result is not None
                else None
            ),

            latest_protocol_number=(
                cls._normalize_text(
                    latest_task_review.protocol_number
                )
                if latest_task_review is not None
                else None
            ),

            latest_protocol_date=(
                latest_task_review.protocol_date
                if latest_task_review is not None
                else None
            ),
        )

    @classmethod
    def _build_document_dto(
            cls,
            document: TaskExecutionDocument,
    ) -> ReviewResultDocumentDTO | None:
        """
        Преобразует документ выполнения задачи в DTO.
        """

        file_path = cls._normalize_text(
            document.file_path
        )

        if file_path is None:
            return None

        file_name = (
                cls._normalize_text(document.original_file_name)
                or cls._normalize_text(document.stored_file_name)
                or Path(file_path).name
        )

        title = (
                cls._normalize_text(document.title)
                or cls._normalize_text(document.report_label)
                or cls._get_enum_label(document.document_type)
                or file_name
                or "Документ"
        )

        return ReviewResultDocumentDTO(
            document_id=document.id,
            title=title,
            file_name=file_name,
            file_path=file_path,

            view_url=(
                f"/staff/reviews/documents/{document.id}/view"
            ),

            download_url=(
                f"/staff/reviews/documents/{document.id}/download"
            ),
        )

    @classmethod
    def _build_final_document_dto(
            cls,
            documents: list[TaskExecutionDocument],
    ) -> ReviewResultDocumentDTO | None:
        """
        Возвращает актуальный итоговый документ выполнения задачи.

        Протокол рассмотрения не является итоговым документом задачи,
        даже если у него установлен is_final=True.
        """

        final_document = next(
            (
                document
                for document in documents
                if (
                    document.is_current
                    and document.is_final
                    and document.document_type
                    != DocumentType.PROTOCOL
                    and document.file_path
                )
            ),
            None,
        )

        if final_document is None:
            return None

        return cls._build_document_dto(
            final_document
        )

    @classmethod
    def _build_execution_report_dtos(
            cls,
            documents: list[TaskExecutionDocument],
    ) -> list[ReviewResultDocumentDTO]:
        """
        Возвращает актуальные отчеты исполнителей.

        Итоговый документ в список отчетов не включается.
        """

        result: list[ReviewResultDocumentDTO] = []

        for document in documents:
            if not document.is_current:
                continue

            if document.is_final:
                continue

            if document.document_type != DocumentType.REPORT:
                continue

            if not document.file_path:
                continue

            document_dto = cls._build_document_dto(
                document
            )

            if document_dto is not None:
                result.append(document_dto)

        return result

    # ==========================================================
    # 6. Построение истории
    # ==========================================================

    @classmethod
    def _build_history_item_dto(
            cls,
            result: SchoolMonthPlanItemReviewResult,
            *,
            protocol_document: TaskExecutionDocument | None,
    ) -> ReviewResultHistoryItemDTO:
        protocol_document_dto = (
            cls._build_document_dto(protocol_document)
            if protocol_document is not None
            else None
        )

        task_review = result.task_review

        return ReviewResultHistoryItemDTO(
            review_result_id=result.id,
            month_item_id=result.month_item_id,

            review_place=cls._get_enum_value(
                result.review_place
            ),

            review_place_label=cls._get_enum_label(
                result.review_place
            ),

            status=cls._get_enum_value(
                result.status
            ),

            status_label=cls._get_enum_label(
                result.status
            ),

            reviewed_at=result.reviewed_at,
            created_at=result.created_at,

            reviewed_by_name=cls._get_user_name(
                result.reviewed_by_user
            ),

            comment=cls._normalize_text(
                result.comment
            ),

            protocol_document_id=result.protocol_document_id,

            has_protocol_document=(
                    protocol_document_dto is not None
            ),

            protocol_document=protocol_document_dto,

            protocol_number=(
                cls._normalize_text(
                    task_review.protocol_number
                )
                if task_review is not None
                else None
            ),

            protocol_date=(
                task_review.protocol_date
                if task_review is not None
                else None
            ),
        )

    # ==========================================================
    # 7. Фильтрация результатов по инстанции
    # ==========================================================

    @staticmethod
    def _get_relevant_review_results(
        item: SchoolMonthPlanItem,
        *,
        review_place: ReviewPlace | None,
    ) -> list[SchoolMonthPlanItemReviewResult]:
        """
        Возвращает результаты нужной инстанции.

        Если review_place=None, возвращается вся история задачи.
        """

        if review_place is None:
            return list(item.review_results)

        return [
            result
            for result in item.review_results
            if result.review_place == review_place
        ]

    @staticmethod
    def _sort_review_results(
        results: list[SchoolMonthPlanItemReviewResult],
    ) -> list[SchoolMonthPlanItemReviewResult]:
        """
        Сортирует результаты от нового к старому.
        """

        return sorted(
            results,
            key=lambda result: (
                result.reviewed_at is not None,
                result.reviewed_at or result.created_at,
                result.id,
            ),
            reverse=True,
        )

    @classmethod
    def _get_latest_review_result(
        cls,
        results: list[SchoolMonthPlanItemReviewResult],
    ) -> SchoolMonthPlanItemReviewResult | None:
        sorted_results = cls._sort_review_results(
            results
        )

        if not sorted_results:
            return None

        return sorted_results[0]

    # ==========================================================
    # 8. Участие сотрудника
    # ==========================================================

    @classmethod
    def _build_participation_label(
        cls,
        item: SchoolMonthPlanItem,
        *,
        current_user_id: int | None,
        current_staff_member_id: int | None,
    ) -> str | None:
        labels: list[str] = []

        if (
            current_user_id is not None
            and item.responsible_user_id == current_user_id
        ):
            labels.append("Жауапты")

        if current_staff_member_id is not None:
            for assignee in item.assignees:
                staff_role = assignee.staff_role

                if (
                    staff_role.staff_member_id
                    != current_staff_member_id
                ):
                    continue

                label = assignee.assignment_kind.label_kz

                if label not in labels:
                    labels.append(label)

        return (
            ", ".join(labels)
            if labels
            else None
        )

    # ==========================================================
    # 9. Данные задачи
    # ==========================================================

    @staticmethod
    def _get_task_name(
        item: SchoolMonthPlanItem,
    ) -> str:
        source_row = item.source_row11

        if source_row is None:
            return f"Задача №{item.id}"

        topic = source_row.topic.strip()

        return topic or f"Задача №{item.id}"

    @classmethod
    def _get_task_goal(
        cls,
        item: SchoolMonthPlanItem,
    ) -> str | None:
        source_row = item.source_row11

        if source_row is None:
            return None

        return cls._normalize_text(
            source_row.goal
        )

    @classmethod
    def _get_responsibles_text(
        cls,
        item: SchoolMonthPlanItem,
    ) -> str | None:
        source_row = item.source_row11

        if source_row is None:
            return None

        return cls._normalize_text(
            source_row.responsibles
        )

    @classmethod
    def _get_responsible_name(
            cls,
            item: SchoolMonthPlanItem,
    ) -> str | None:
        """
        Возвращает ответственного по приоритету:

        1. Назначенные сотрудники из item.assignees.
        2. item.responsible_user.
        3. Текст ответственного из годового плана.
        """

        assignee_names: list[str] = []

        for assignee in item.assignees or []:
            staff_role = assignee.staff_role

            if staff_role is None:
                continue

            staff_member_name = cls._get_staff_member_name(
                staff_role.staff_member
            )

            if staff_member_name:
                assignee_names.append(
                    staff_member_name
                )

        unique_names = list(
            dict.fromkeys(assignee_names)
        )

        if unique_names:
            return ", ".join(unique_names)

        responsible_user = cast(
            User | None,
            item.responsible_user,
        )

        user_name = cls._get_user_name(
            responsible_user
        )

        if user_name:
            return user_name

        return cls._get_responsibles_text(
            item
        )

    @classmethod
    def _get_staff_member_name(
            cls,
            staff_member: SchoolStaffMember | None,
    ) -> str | None:
        """
        Возвращает ФИО сотрудника.

        Приоритет:
        1. user_account.full_name;
        2. staff_member.full_name;
        3. user_account.username;
        4. идентификатор пользователя.
        """

        if staff_member is None:
            return None

        user_account = cast(
            User | None,
            staff_member.user_account,
        )

        if user_account is not None:
            user_full_name = cls._normalize_text(
                user_account.full_name
            )

            if user_full_name:
                return user_full_name

        staff_full_name = cls._normalize_text(
            staff_member.full_name
        )

        if staff_full_name:
            return staff_full_name

        if user_account is not None:
            username = cls._normalize_text(
                user_account.username
            )

            if username:
                return username

            return f"Пользователь №{user_account.id}"

        return None

    # ==========================================================
    # 10. Пользователь
    # ==========================================================

    @classmethod
    def _get_user_name(
        cls,
        user: User | None,
    ) -> str | None:
        if user is None:
            return None

        full_name = getattr(
            user,
            "full_name",
            None,
        )

        normalized_full_name = cls._normalize_text(
            full_name
        )

        if normalized_full_name:
            return normalized_full_name

        staff_member = getattr(
            user,
            "staff_member",
            None,
        )

        if staff_member is not None:
            staff_full_name = getattr(
                staff_member,
                "full_name",
                None,
            )

            normalized_staff_name = cls._normalize_text(
                staff_full_name
            )

            if normalized_staff_name:
                return normalized_staff_name

        username = getattr(
            user,
            "username",
            None,
        )

        normalized_username = cls._normalize_text(
            username
        )

        if normalized_username:
            return normalized_username

        return f"Пользователь №{user.id}"

    # ==========================================================
    # 11. Фильтры
    # ==========================================================

    @staticmethod
    def _parse_review_place(
        value: ReviewPlace | str | None,
    ) -> ReviewPlace | None:
        if value is None:
            return None

        if isinstance(value, ReviewPlace):
            return value

        normalized = value.strip()

        if not normalized:
            return None

        try:
            return ReviewPlace(normalized)
        except ValueError as exc:
            raise ValueError(
                "Передана неизвестная инстанция рассмотрения."
            ) from exc

    @staticmethod
    def _parse_reviewed_filter(
        value: bool | str | None,
    ) -> bool | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        normalized = value.strip().lower()

        if normalized in {
            "",
            "all",
        }:
            return None

        if normalized in {
            "1",
            "true",
            "yes",
            "reviewed",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "no",
            "not_reviewed",
        }:
            return False

        raise ValueError(
            "Передан некорректный фильтр результатов."
        )

    @staticmethod
    def _resolve_selected_year(
        *,
        requested_year: int | None,
        available_years: list[int],
    ) -> int | None:
        if not available_years:
            return None

        if requested_year is None:
            current_year = date.today().year
            return current_year if current_year in available_years else available_years[0]

        if requested_year not in available_years:
            raise ValueError(
                "Для выбранного года месячные планы не найдены."
            )

        return requested_year

    @staticmethod
    def _resolve_selected_month(
        *,
        requested_month: int | None,
        available_months: list[int],
    ) -> int | None:
        if requested_month is None:
            return None

        if requested_month < 1 or requested_month > 12:
            raise ValueError(
                "Номер месяца должен находиться "
                "в диапазоне от 1 до 12."
            )

        if requested_month not in available_months:
            raise ValueError(
                "Для выбранного месяца план не найден."
            )

        return requested_month

    # ==========================================================
    # 12. Форматирование
    # ==========================================================

    @staticmethod
    def _build_planned_period_text(
        planned_start: date | None,
        planned_end: date | None,
    ) -> str:
        if planned_start and planned_end:
            if planned_start == planned_end:
                return planned_start.strftime(
                    "%d.%m.%Y"
                )

            return (
                f"{planned_start:%d.%m.%Y} — "
                f"{planned_end:%d.%m.%Y}"
            )

        if planned_start:
            return f"с {planned_start:%d.%m.%Y}"

        if planned_end:
            return f"до {planned_end:%d.%m.%Y}"

        return "Не указан"

    @staticmethod
    def _normalize_text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()

        return normalized or None

    @staticmethod
    def _get_enum_value(
        value: Any,
    ) -> str:
        """
        Возвращает техническое значение enum.

        Поддерживает обычные str Enum и enum,
        созданные через __new__.
        """

        enum_value = getattr(
            value,
            "value",
            value,
        )

        return str(enum_value)

    @staticmethod
    def _get_enum_label(
        value: Any,
    ) -> str:
        """
        Возвращает человекочитаемую подпись enum.

        Приоритет:

        1. label_kz;
        2. label_ru;
        3. label;
        4. title;
        5. value.
        """

        if value is None:
            return ""

        for attribute_name in (
            "label_kz",
            "label_ru",
            "label",
            "title",
        ):
            label = getattr(
                value,
                attribute_name,
                None,
            )

            if isinstance(label, str) and label.strip():
                return label.strip()

        enum_value = getattr(
            value,
            "value",
            value,
        )

        return str(enum_value)

    @classmethod
    async def get_document_for_access(
            cls,
            db: AsyncSession,
            *,
            user: User,
            document_id: int,
            selected_school_id: int | None = None,
    ) -> ReviewResultDocumentDTO:
        """
        Получает документ с проверкой школы и прав пользователя.
        """

        access = cls._build_access_context(
            user,
            selected_school_id=selected_school_id,
        )

        document = (
            await ReviewResultRepository.get_document_for_access(
                db,
                document_id=document_id,
                school_id=access.school_id,
                participant_user_id=access.participant_user_id,
                participant_staff_id=access.participant_staff_id,
            )
        )

        if document is None:
            raise ValueError(
                "Документ не найден или у пользователя нет доступа."
            )

        document_dto = cls._build_document_dto(
            document
        )

        if document_dto is None:
            raise ValueError(
                "У документа отсутствует файл."
            )

        return document_dto
