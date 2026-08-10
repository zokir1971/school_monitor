# app/modules/monitoring/monitoring_service.py

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.constants import (
    FINAL_DOCUMENT_SCORE,
    REPORT_SCORE,
)
from app.modules.monitoring.monitoring_dto import (
    StaffMonitoringPageDTO,
    StaffMonitoringRatingDTO,
    StaffMonitoringTotalsDTO,
    StaffTaskScoreDTO,
)
from app.modules.monitoring.monitoring_repo import (
    StaffMonitoringRepository,
)


class StaffMonitoringService:
    """
    Бизнес-логика мониторинга и рейтинга исполнителей.

    Главное правило новой архитектуры:

        личный результат сотрудника не зависит от того,
        завершена ли задача целиком.

    Это особенно важно для соисполнителя:

        - сотруднику назначены конкретные отчёты;
        - он отвечает только за свои назначения;
        - выполненный им отчёт засчитывается сразу после
          перехода TaskSelectedReportAssignment в COMPLETED;
        - отсутствие итогового документа и незавершённость
          всей задачи относятся к ответственности PRIMARY.

    Правила начисления баллов:

        COMPLETED assignment:
            REPORT_SCORE за каждый лично выполненный отчёт;

        PENDING assignment:
            0 баллов;

        WAIVED assignment:
            0 баллов;

        итоговый документ:
            FINAL_DOCUMENT_SCORE только PRIMARY.

    Статус SchoolMonthPlanItem.DONE сохраняется как отдельный
    показатель состояния всей задачи, но не обнуляет и не
    блокирует персональные баллы за уже выполненные отчёты.
    """

    repository = StaffMonitoringRepository

    # =========================================================
    # ОБЩИЕ ВЫЧИСЛЕНИЯ
    # =========================================================

    @staticmethod
    def _calculate_percent(
        numerator: int,
        denominator: int,
    ) -> float:
        """
        Рассчитать процент с округлением до одного знака.
        """

        if denominator <= 0:
            return 0.0

        return round(
            numerator / denominator * 100,
            1,
        )

    @staticmethod
    def _calculate_average(
        numerator: int | float,
        denominator: int,
    ) -> float:
        """
        Рассчитать среднее значение
        с округлением до двух знаков.
        """

        if denominator <= 0:
            return 0.0

        return round(
            numerator / denominator,
            2,
        )

    @staticmethod
    def _get_assignment_kind(
        value: Any,
    ) -> str:
        """
        Нормализовать вид участия сотрудника в задаче.

        Поддерживаются:
            - строка;
            - Python Enum;
            - Enum со значением-кортежем.
        """

        if value is None:
            return "primary"

        enum_value = getattr(
            value,
            "value",
            value,
        )

        if isinstance(enum_value, tuple):
            enum_value = enum_value[0]

        return str(enum_value)

    @staticmethod
    def _normalize_count(
        value: Any,
    ) -> int:
        """
        Привести числовой показатель к безопасному int >= 0.
        """

        try:
            return max(
                int(value or 0),
                0,
            )
        except (TypeError, ValueError):
            return 0

    # =========================================================
    # РАСЧЁТ ОДНОЙ ЗАДАЧИ СОТРУДНИКА
    # =========================================================

    @classmethod
    def _build_task_score(
        cls,
        row,
    ) -> StaffTaskScoreDTO:
        """
        Преобразовать строку репозитория в персональный
        результат сотрудника по одной задаче.

        Важно:

        is_completed:
            состояние всей задачи;

        assigned/completed/pending/waived_report_count:
            личные обязательства конкретного сотрудника;

        has_final_document:
            учитывается только для PRIMARY.

        Персональные выполненные отчёты НЕ обнуляются,
        если вся задача ещё не имеет статус DONE.
        """

        assignment_kind = cls._get_assignment_kind(
            row.assignment_kind
        )

        is_co_executor = (
            assignment_kind == "co_executor"
        )
        is_primary = not is_co_executor

        # -----------------------------------------------------
        # Состояние всей задачи
        # -----------------------------------------------------

        is_completed = bool(
            row.is_completed
        )

        # -----------------------------------------------------
        # Итоговый документ
        # -----------------------------------------------------
        #
        # Итоговый документ является ответственностью PRIMARY.
        # Для соисполнителя он никогда не начисляет балл.
        #
        # Здесь намеренно нет проверки is_completed:
        # наличие валидного итогового документа является
        # самостоятельным фактом выполненной работы PRIMARY.
        # -----------------------------------------------------

        has_final_document = bool(
            is_primary
            and row.has_final_document
        )

        # -----------------------------------------------------
        # Персональные назначения отчётов
        # -----------------------------------------------------

        assigned_report_count = cls._normalize_count(
            row.assigned_report_count
        )

        completed_report_count = cls._normalize_count(
            row.completed_report_count
        )

        pending_report_count = cls._normalize_count(
            row.pending_report_count
        )

        waived_report_count = cls._normalize_count(
            row.waived_report_count
        )

        # Защита от неконсистентных агрегатов.
        #
        # Источником истины остаётся assigned_report_count,
        # но completed не должен визуально превышать количество
        # назначенных отчётов.
        if assigned_report_count > 0:
            completed_report_count = min(
                completed_report_count,
                assigned_report_count,
            )

            pending_report_count = min(
                pending_report_count,
                assigned_report_count,
            )

            waived_report_count = min(
                waived_report_count,
                assigned_report_count,
            )

        report_completion_percent = (
            cls._calculate_percent(
                completed_report_count,
                assigned_report_count,
            )
        )

        # -----------------------------------------------------
        # Баллы
        # -----------------------------------------------------

        final_document_score = (
            FINAL_DOCUMENT_SCORE
            if has_final_document
            else 0
        )

        completed_reports_score = (
            completed_report_count
            * REPORT_SCORE
        )

        total_score = (
            final_document_score
            + completed_reports_score
        )

        return StaffTaskScoreDTO(
            # Сотрудник
            user_id=row.user_id,
            staff_member_id=row.staff_member_id,

            full_name=(
                row.full_name
                or f"Сотрудник {row.staff_member_id}"
            ),
            position_text=row.position_text,

            # Задача
            month_item_id=row.month_item_id,
            month_plan_id=row.month_plan_id,
            source_row11_id=row.source_row11_id,

            year=row.year,
            month=row.month,
            direction_id=row.direction_id,

            # Роль
            assignment_kind=assignment_kind,
            is_primary=is_primary,
            is_co_executor=is_co_executor,

            # Состояние задачи
            is_completed=is_completed,
            has_final_document=has_final_document,

            # Персональные отчёты
            assigned_report_count=(
                assigned_report_count
            ),
            completed_report_count=(
                completed_report_count
            ),
            pending_report_count=(
                pending_report_count
            ),
            waived_report_count=(
                waived_report_count
            ),

            report_completion_percent=(
                report_completion_percent
            ),

            # Баллы
            final_document_score=(
                final_document_score
            ),
            completed_reports_score=(
                completed_reports_score
            ),

            total_score=total_score,
        )

    # =========================================================
    # ПОЛУЧЕНИЕ ОЦЕНЁННЫХ ЗАДАЧ
    # =========================================================

    @classmethod
    async def get_task_scores(
        cls,
        db: AsyncSession,
        *,
        school_plan_id: int,
        month_plan_id: int | None = None,
        direction_id: int | None = None,
    ) -> list[StaffTaskScoreDTO]:
        """
        Получить персональные результаты сотрудников
        по задачам выбранного плана.

        month_plan_id и direction_id являются
        необязательными фильтрами.
        """

        rows = await (
            cls.repository
            .get_staff_task_scoring_rows(
                db,
                school_plan_id=school_plan_id,
                month_plan_id=month_plan_id,
                direction_id=direction_id,
            )
        )

        return [
            cls._build_task_score(row)
            for row in rows
        ]

    # =========================================================
    # РЕЙТИНГ СОТРУДНИКОВ
    # =========================================================

    @classmethod
    def build_rating(
        cls,
        task_scores: list[StaffTaskScoreDTO],
    ) -> list[StaffMonitoringRatingDTO]:
        """
        Сгруппировать персональные результаты по сотрудникам
        и сформировать итоговый рейтинг.

        Основой рейтинга являются реальные личные результаты:

            1. общий балл;
            2. процент выполнения персонально
               назначенных отчётов;
            3. средний балл за участие в задаче;
            4. процент задач со статусом DONE;
            5. ФИО.

        Статус всей задачи используется только как
        дополнительный показатель и не отменяет уже
        заработанные сотрудником баллы.
        """

        grouped: dict[
            int,
            list[StaffTaskScoreDTO],
        ] = defaultdict(list)

        for task in task_scores:
            grouped[
                task.staff_member_id
            ].append(task)

        prepared_rows: list[
            dict[str, Any]
        ] = []

        for staff_member_id, tasks in grouped.items():
            first_task = tasks[0]

            # -------------------------------------------------
            # Участие в задачах
            # -------------------------------------------------

            assigned_count = len(tasks)

            primary_assignment_count = sum(
                1
                for task in tasks
                if task.is_primary
            )

            co_executor_assignment_count = sum(
                1
                for task in tasks
                if task.is_co_executor
            )

            # -------------------------------------------------
            # Состояние всей задачи
            # -------------------------------------------------

            completed_count = sum(
                1
                for task in tasks
                if task.is_completed
            )

            not_completed_count = max(
                assigned_count
                - completed_count,
                0,
            )

            completed_primary_count = sum(
                1
                for task in tasks
                if (
                    task.is_primary
                    and task.is_completed
                )
            )

            completed_co_executor_count = sum(
                1
                for task in tasks
                if (
                    task.is_co_executor
                    and task.is_completed
                )
            )

            # -------------------------------------------------
            # Ответственность PRIMARY
            # -------------------------------------------------

            final_document_count = sum(
                1
                for task in tasks
                if task.has_final_document
            )

            # -------------------------------------------------
            # Персональные отчёты
            # -------------------------------------------------

            assigned_report_count = sum(
                task.assigned_report_count
                for task in tasks
            )

            completed_report_count = sum(
                task.completed_report_count
                for task in tasks
            )

            pending_report_count = sum(
                task.pending_report_count
                for task in tasks
            )

            waived_report_count = sum(
                task.waived_report_count
                for task in tasks
            )

            report_completion_percent = (
                cls._calculate_percent(
                    completed_report_count,
                    assigned_report_count,
                )
            )

            # -------------------------------------------------
            # Баллы
            # -------------------------------------------------

            total_score = sum(
                task.total_score
                for task in tasks
            )

            # -------------------------------------------------
            # Дополнительные показатели
            # -------------------------------------------------

            completion_percent = (
                cls._calculate_percent(
                    completed_count,
                    assigned_count,
                )
            )

            average_score_per_task = (
                cls._calculate_average(
                    total_score,
                    assigned_count,
                )
            )

            # Для среднего по завершённым задачам используем
            # только баллы тех задач, которые действительно DONE.
            completed_task_score = sum(
                task.total_score
                for task in tasks
                if task.is_completed
            )

            average_score_per_completed_task = (
                cls._calculate_average(
                    completed_task_score,
                    completed_count,
                )
            )

            prepared_rows.append(
                {
                    # Сотрудник
                    "user_id": first_task.user_id,
                    "staff_member_id": (
                        staff_member_id
                    ),
                    "full_name": first_task.full_name,
                    "position_text": (
                        first_task.position_text
                    ),

                    # Участие
                    "assigned_count": (
                        assigned_count
                    ),
                    "primary_assignment_count": (
                        primary_assignment_count
                    ),
                    "co_executor_assignment_count": (
                        co_executor_assignment_count
                    ),

                    # Состояние задач
                    "completed_count": (
                        completed_count
                    ),
                    "not_completed_count": (
                        not_completed_count
                    ),
                    "completed_primary_count": (
                        completed_primary_count
                    ),
                    "completed_co_executor_count": (
                        completed_co_executor_count
                    ),

                    # PRIMARY
                    "final_document_count": (
                        final_document_count
                    ),

                    # Отчёты
                    "assigned_report_count": (
                        assigned_report_count
                    ),
                    "completed_report_count": (
                        completed_report_count
                    ),
                    "pending_report_count": (
                        pending_report_count
                    ),
                    "waived_report_count": (
                        waived_report_count
                    ),
                    "report_completion_percent": (
                        report_completion_percent
                    ),

                    # Итоги
                    "total_score": total_score,
                    "completion_percent": (
                        completion_percent
                    ),
                    "average_score_per_task": (
                        average_score_per_task
                    ),
                    "average_score_per_completed_task": (
                        average_score_per_completed_task
                    ),
                }
            )

        # -----------------------------------------------------
        # Сортировка рейтинга
        # -----------------------------------------------------

        prepared_rows.sort(
            key=lambda row: (
                -row["total_score"],
                -row["report_completion_percent"],
                -row["average_score_per_task"],
                -row["completion_percent"],
                row["full_name"].lower(),
            )
        )

        # -----------------------------------------------------
        # Формирование мест
        # -----------------------------------------------------

        rating_rows: list[
            StaffMonitoringRatingDTO
        ] = []

        previous_rating_key: tuple[
            int | float,
            float,
            float,
            float,
        ] | None = None

        current_rank = 0

        for index, rating_data in enumerate(
            prepared_rows,
            start=1,
        ):
            rating_key = (
                rating_data["total_score"],
                rating_data[
                    "report_completion_percent"
                ],
                rating_data[
                    "average_score_per_task"
                ],
                rating_data[
                    "completion_percent"
                ],
            )

            # При одинаковых показателях сотрудники
            # получают одинаковое место.
            if rating_key != previous_rating_key:
                current_rank = index
                previous_rating_key = rating_key

            rating_rows.append(
                StaffMonitoringRatingDTO(
                    rank=current_rank,

                    # Сотрудник
                    user_id=(
                        rating_data["user_id"]
                    ),
                    staff_member_id=(
                        rating_data[
                            "staff_member_id"
                        ]
                    ),

                    full_name=(
                        rating_data["full_name"]
                    ),
                    position_text=(
                        rating_data[
                            "position_text"
                        ]
                    ),

                    # Участие
                    assigned_count=(
                        rating_data[
                            "assigned_count"
                        ]
                    ),
                    primary_assignment_count=(
                        rating_data[
                            "primary_assignment_count"
                        ]
                    ),
                    co_executor_assignment_count=(
                        rating_data[
                            "co_executor_assignment_count"
                        ]
                    ),

                    # Состояние задач
                    completed_count=(
                        rating_data[
                            "completed_count"
                        ]
                    ),
                    not_completed_count=(
                        rating_data[
                            "not_completed_count"
                        ]
                    ),
                    completed_primary_count=(
                        rating_data[
                            "completed_primary_count"
                        ]
                    ),
                    completed_co_executor_count=(
                        rating_data[
                            "completed_co_executor_count"
                        ]
                    ),

                    # PRIMARY
                    final_document_count=(
                        rating_data[
                            "final_document_count"
                        ]
                    ),

                    # Персональные отчёты
                    assigned_report_count=(
                        rating_data[
                            "assigned_report_count"
                        ]
                    ),
                    completed_report_count=(
                        rating_data[
                            "completed_report_count"
                        ]
                    ),
                    pending_report_count=(
                        rating_data[
                            "pending_report_count"
                        ]
                    ),
                    waived_report_count=(
                        rating_data[
                            "waived_report_count"
                        ]
                    ),
                    report_completion_percent=(
                        rating_data[
                            "report_completion_percent"
                        ]
                    ),

                    # Итоги
                    total_score=(
                        rating_data[
                            "total_score"
                        ]
                    ),
                    completion_percent=(
                        rating_data[
                            "completion_percent"
                        ]
                    ),
                    average_score_per_task=(
                        rating_data[
                            "average_score_per_task"
                        ]
                    ),
                    average_score_per_completed_task=(
                        rating_data[
                            "average_score_per_completed_task"
                        ]
                    ),
                )
            )

        return rating_rows

    # =========================================================
    # ОБЩИЕ ИТОГИ РЕЙТИНГА
    # =========================================================

    @classmethod
    def build_totals(
        cls,
        rating_rows: list[StaffMonitoringRatingDTO],
        task_scores: list[StaffTaskScoreDTO],
    ) -> StaffMonitoringTotalsDTO:
        """
        Сформировать общие показатели рейтинга.

        unique_task_count:
            число уникальных задач месячных планов;

        assignment_count:
            число персональных участий
            вида «задача + сотрудник»;

        report_*:
            реальные персональные назначения отчётов.
        """

        staff_count = len(
            rating_rows
        )

        unique_task_count = len(
            {
                task.month_item_id
                for task in task_scores
            }
        )

        tasks_with_coexecutors_ids = {
            task.month_item_id
            for task in task_scores
            if task.is_co_executor
        }

        tasks_with_coexecutors_count = len(
            tasks_with_coexecutors_ids
        )

        completed_tasks_with_coexecutors_count = len(
            {
                task.month_item_id
                for task in task_scores
                if (
                    task.is_co_executor
                    and task.is_completed
                )
            }
        )

        assignment_count = len(
            task_scores
        )

        # -----------------------------------------------------
        # Участие
        # -----------------------------------------------------

        primary_assignment_count = sum(
            row.primary_assignment_count
            for row in rating_rows
        )

        co_executor_assignment_count = sum(
            row.co_executor_assignment_count
            for row in rating_rows
        )

        # -----------------------------------------------------
        # Состояние задач
        # -----------------------------------------------------

        completed_count = sum(
            row.completed_count
            for row in rating_rows
        )

        not_completed_count = sum(
            row.not_completed_count
            for row in rating_rows
        )

        completed_primary_count = sum(
            row.completed_primary_count
            for row in rating_rows
        )

        completed_co_executor_count = sum(
            row.completed_co_executor_count
            for row in rating_rows
        )

        # -----------------------------------------------------
        # PRIMARY
        # -----------------------------------------------------

        final_document_count = sum(
            row.final_document_count
            for row in rating_rows
        )

        # -----------------------------------------------------
        # Персональные отчёты
        # -----------------------------------------------------

        assigned_report_count = sum(
            row.assigned_report_count
            for row in rating_rows
        )

        completed_report_count = sum(
            row.completed_report_count
            for row in rating_rows
        )

        pending_report_count = sum(
            row.pending_report_count
            for row in rating_rows
        )

        waived_report_count = sum(
            row.waived_report_count
            for row in rating_rows
        )

        report_completion_percent = (
            cls._calculate_percent(
                completed_report_count,
                assigned_report_count,
            )
        )

        # -----------------------------------------------------
        # Итоги
        # -----------------------------------------------------

        total_score = sum(
            row.total_score
            for row in rating_rows
        )

        return StaffMonitoringTotalsDTO(
            # Сотрудники / задачи
            staff_count=staff_count,
            unique_task_count=(
                unique_task_count
            ),
            tasks_with_coexecutors_count=(
                tasks_with_coexecutors_count
            ),
            completed_tasks_with_coexecutors_count=(
                completed_tasks_with_coexecutors_count
            ),

            # Участия
            assignment_count=(
                assignment_count
            ),
            assigned_count=(
                assignment_count
            ),
            primary_assignment_count=(
                primary_assignment_count
            ),
            co_executor_assignment_count=(
                co_executor_assignment_count
            ),

            # Состояние задач
            completed_count=(
                completed_count
            ),
            not_completed_count=(
                not_completed_count
            ),
            completed_primary_count=(
                completed_primary_count
            ),
            completed_co_executor_count=(
                completed_co_executor_count
            ),

            # PRIMARY
            final_document_count=(
                final_document_count
            ),

            # Персональные отчёты
            assigned_report_count=(
                assigned_report_count
            ),
            completed_report_count=(
                completed_report_count
            ),
            pending_report_count=(
                pending_report_count
            ),
            waived_report_count=(
                waived_report_count
            ),
            report_completion_percent=(
                report_completion_percent
            ),

            # Итоги
            total_score=total_score,

            completion_percent=(
                cls._calculate_percent(
                    completed_count,
                    assignment_count,
                )
            ),

            average_score_per_staff=(
                cls._calculate_average(
                    total_score,
                    staff_count,
                )
            ),
        )

    # =========================================================
    # ДАННЫЕ СТРАНИЦЫ
    # =========================================================

    @classmethod
    async def get_page_data(
        cls,
        db: AsyncSession,
        *,
        school_plan_id: int,
        academic_year: str,
        month_plan_id: int | None = None,
        direction_id: int | None = None,
    ) -> StaffMonitoringPageDTO:
        """
        Собрать полный набор данных страницы
        мониторинга исполнителей.
        """

        task_scores = await cls.get_task_scores(
            db,
            school_plan_id=school_plan_id,
            month_plan_id=month_plan_id,
            direction_id=direction_id,
        )

        rating_rows = cls.build_rating(
            task_scores
        )

        totals = cls.build_totals(
            rating_rows,
            task_scores,
        )

        return StaffMonitoringPageDTO(
            school_plan_id=(
                school_plan_id
            ),
            academic_year=str(
                academic_year
            ),

            selected_month_plan_id=(
                month_plan_id
            ),
            selected_direction_id=(
                direction_id
            ),

            rating_rows=(
                rating_rows
            ),
            totals=totals,
        )
