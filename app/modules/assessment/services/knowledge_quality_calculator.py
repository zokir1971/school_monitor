# app/modules/assessment/services/knowledge_quality_calculator.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


# =========================================================
# RESULT
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityMetrics:
    """
    Результат расчёта показателей качества знаний.

    Класс не зависит от SQLAlchemy и может использоваться:
        - для одного класса;
        - для Assessment целиком;
        - при создании AssessmentQualitySummary;
        - для агрегированной аналитики.
    """

    average_score: Decimal | None
    average_percent: Decimal | None

    achievement_percent: Decimal | None
    quality_percent: Decimal | None


# =========================================================
# CALCULATOR
# =========================================================


class KnowledgeQualityCalculator:
    """
    Единый калькулятор качества знаний.

    Не работает с БД.
    Не знает ничего об ORM.
    Не выполняет SQL.

    Все значения должны быть уже агрегированы вызывающим
    сервисом или repository.
    """

    PERCENT_QUANT = Decimal("0.01")
    SCORE_QUANT = Decimal("0.01")

    HUNDRED = Decimal("100")

    # =====================================================
    # PUBLIC
    # =====================================================
    @classmethod
    def calculate(
        cls,
        *,
        total_students: int,
        participated_students: int,

        absent_students: int,
        excused_students: int,
        not_completed_students: int,

        grade_5_count: int,
        grade_4_count: int,
        grade_3_count: int,
        grade_2_count: int,

        score_sum: Decimal,
        percent_sum: Decimal,
    ) -> KnowledgeQualityMetrics:
        """
        Рассчитать показатели качества знаний.

        Формулы:

        Успеваемость:
            (5 + 4 + 3) / participated * 100

        Качество знаний:
            (5 + 4) / participated * 100

        Средний балл:
            score_sum / participated

        Средний процент:
            percent_sum / participated

        ABSENT / EXCUSED / NOT_COMPLETED
        не входят в participated_students.
        """

        cls._validate_counts(
            total_students=total_students,
            participated_students=participated_students,

            absent_students=absent_students,
            excused_students=excused_students,
            not_completed_students=not_completed_students,

            grade_5_count=grade_5_count,
            grade_4_count=grade_4_count,
            grade_3_count=grade_3_count,
            grade_2_count=grade_2_count,
        )

        cls._validate_sums(
            score_sum=score_sum,
            percent_sum=percent_sum,
            participated_students=participated_students,
        )

        # -------------------------------------------------
        # Нет фактических результатов
        # -------------------------------------------------

        if participated_students == 0:
            return KnowledgeQualityMetrics(
                average_score=None,
                average_percent=None,
                achievement_percent=None,
                quality_percent=None,
            )

        divisor = Decimal(
            participated_students
        )

        # -------------------------------------------------
        # AVERAGES
        # -------------------------------------------------

        average_score = (
            score_sum
            / divisor
        ).quantize(
            cls.SCORE_QUANT,
            rounding=ROUND_HALF_UP,
        )

        average_percent = (
            percent_sum
            / divisor
        ).quantize(
            cls.PERCENT_QUANT,
            rounding=ROUND_HALF_UP,
        )

        # -------------------------------------------------
        # ACHIEVEMENT
        # -------------------------------------------------

        successful_count = (
            grade_5_count
            + grade_4_count
            + grade_3_count
        )

        achievement_percent = (
            Decimal(successful_count)
            * cls.HUNDRED
            / divisor
        ).quantize(
            cls.PERCENT_QUANT,
            rounding=ROUND_HALF_UP,
        )

        # -------------------------------------------------
        # KNOWLEDGE QUALITY
        # -------------------------------------------------

        quality_count = (
            grade_5_count
            + grade_4_count
        )

        quality_percent = (
            Decimal(quality_count)
            * cls.HUNDRED
            / divisor
        ).quantize(
            cls.PERCENT_QUANT,
            rounding=ROUND_HALF_UP,
        )

        return KnowledgeQualityMetrics(
            average_score=average_score,
            average_percent=average_percent,
            achievement_percent=achievement_percent,
            quality_percent=quality_percent,
        )

    # =====================================================
    # VALIDATION
    # =====================================================

    @staticmethod
    def _validate_counts(
        *,
        total_students: int,
        participated_students: int,

        absent_students: int,
        excused_students: int,
        not_completed_students: int,

        grade_5_count: int,
        grade_4_count: int,
        grade_3_count: int,
        grade_2_count: int,
    ) -> None:
        """
        Проверить целостность агрегированных счётчиков.
        """

        values = {
            "total_students": total_students,
            "participated_students": (
                participated_students
            ),
            "absent_students": absent_students,
            "excused_students": excused_students,
            "not_completed_students": (
                not_completed_students
            ),
            "grade_5_count": grade_5_count,
            "grade_4_count": grade_4_count,
            "grade_3_count": grade_3_count,
            "grade_2_count": grade_2_count,
        }

        for name, value in values.items():
            if value < 0:
                raise ValueError(
                    f"{name} не может быть отрицательным."
                )

        if participated_students > total_students:
            raise ValueError(
                "Количество участников не может быть "
                "больше общего количества учащихся."
            )

        graded_students = (
            grade_5_count
            + grade_4_count
            + grade_3_count
            + grade_2_count
        )

        if graded_students != participated_students:
            raise ValueError(
                "Количество оценок 5/4/3/2 должно быть "
                "равно количеству участников, "
                "получивших результат."
            )

        processed_students = (
            participated_students
            + absent_students
            + excused_students
            + not_completed_students
        )

        if processed_students > total_students:
            raise ValueError(
                "Количество обработанных учащихся "
                "не может быть больше общего количества."
            )

    @staticmethod
    def _validate_sums(
        *,
        score_sum: Decimal,
        percent_sum: Decimal,
        participated_students: int,
    ) -> None:
        """
        Проверить агрегированные суммы.
        """

        if not score_sum.is_finite():
            raise ValueError(
                "score_sum должен быть конечным числом."
            )

        if not percent_sum.is_finite():
            raise ValueError(
                "percent_sum должен быть конечным числом."
            )

        if score_sum < 0:
            raise ValueError(
                "score_sum не может быть отрицательным."
            )

        if percent_sum < 0:
            raise ValueError(
                "percent_sum не может быть отрицательным."
            )

        if participated_students == 0:
            if score_sum != 0:
                raise ValueError(
                    "При отсутствии участников "
                    "score_sum должен быть равен 0."
                )

            if percent_sum != 0:
                raise ValueError(
                    "При отсутствии участников "
                    "percent_sum должен быть равен 0."
                )
