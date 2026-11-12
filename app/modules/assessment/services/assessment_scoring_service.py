# app/modules/assessment/services/assessment_scoring_service.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    Decimal,
    ROUND_CEILING,
    ROUND_HALF_UP,
)

from app.modules.assessment.enums import AssessmentGrade


# =========================================================
# DTO
# =========================================================


@dataclass(frozen=True, slots=True)
class AssessmentGradeScaleItem:
    """
    Один диапазон шкалы оценивания.
    """

    grade: AssessmentGrade

    min_percent: Decimal
    max_percent: Decimal

    min_score: Decimal
    max_score: Decimal

    @property
    def value(self) -> str:
        return self.grade.value

    @property
    def label_kz(self) -> str:
        return self.grade.label_kz


@dataclass(frozen=True, slots=True)
class AssessmentScoringResult:
    """
    Результат расчёта оценки ученика.
    """

    score: Decimal
    max_score: Decimal

    percent: Decimal
    grade: AssessmentGrade

    @property
    def grade_value(self) -> str:
        return self.grade.value

    @property
    def grade_label_kz(self) -> str:
        return self.grade.label_kz


# =========================================================
# SERVICE
# =========================================================


class AssessmentScoringService:
    """
    Единый сервис расчёта результатов Assessment.

    Сервис не работает с БД.

    Его используют:
        - ручной ввод результатов;
        - онлайн Assessment;
        - аналитика качества знаний;
        - DTO / интерфейс;
        - формирование отчётов.

    Бизнес-правила:

        85–100% -> 5 -> Үздік
        65–84%  -> 4 -> Жақсы
        40–64%  -> 3 -> Қанағаттанарлық
        0–39%   -> 2 -> Қанағаттанарлықсыз
    """

    EXCELLENT_MIN_PERCENT = Decimal("85")
    GOOD_MIN_PERCENT = Decimal("65")
    SATISFACTORY_MIN_PERCENT = Decimal("40")

    MIN_PERCENT = Decimal("0")
    MAX_PERCENT = Decimal("100")

    PERCENT_QUANT = Decimal("0.0001")

    # =====================================================
    # PUBLIC
    # =====================================================

    @classmethod
    def calculate(
        cls,
        *,
        score: Decimal | int | float | str,
        max_score: Decimal | int | float | str,
    ) -> AssessmentScoringResult:
        """
        Рассчитать полный результат ученика.

        Возвращает:
            score
            max_score
            percent
            grade
        """

        normalized_score = cls._to_decimal(
            score,
            field_name="score",
        )

        normalized_max_score = cls._to_decimal(
            max_score,
            field_name="max_score",
        )

        cls._validate_scores(
            score=normalized_score,
            max_score=normalized_max_score,
        )

        percent = cls.calculate_percent(
            score=normalized_score,
            max_score=normalized_max_score,
        )

        grade = cls.resolve_grade(
            percent=percent,
        )

        return AssessmentScoringResult(
            score=normalized_score,
            max_score=normalized_max_score,
            percent=percent,
            grade=grade,
        )

    # =====================================================
    # PERCENT
    # =====================================================

    @classmethod
    def calculate_percent(
        cls,
        *,
        score: Decimal | int | float | str,
        max_score: Decimal | int | float | str,
    ) -> Decimal:
        """
        Рассчитать процент выполнения.

        Например:

            23 / 30 -> 76.6667
        """

        normalized_score = cls._to_decimal(
            score,
            field_name="score",
        )

        normalized_max_score = cls._to_decimal(
            max_score,
            field_name="max_score",
        )

        cls._validate_scores(
            score=normalized_score,
            max_score=normalized_max_score,
        )

        percent = (
            normalized_score
            * cls.MAX_PERCENT
            / normalized_max_score
        )

        return percent.quantize(
            cls.PERCENT_QUANT,
            rounding=ROUND_HALF_UP,
        )

    # =====================================================
    # GRADE
    # =====================================================

    @classmethod
    def resolve_grade(
        cls,
        *,
        percent: Decimal | int | float | str,
    ) -> AssessmentGrade:
        """
        Определить школьную оценку по проценту.
        """

        normalized_percent = cls._to_decimal(
            percent,
            field_name="percent",
        )

        if not (
            cls.MIN_PERCENT
            <= normalized_percent
            <= cls.MAX_PERCENT
        ):
            raise ValueError(
                "percent должен находиться "
                "в диапазоне от 0 до 100"
            )

        if (
            normalized_percent
            >= cls.EXCELLENT_MIN_PERCENT
        ):
            return AssessmentGrade.EXCELLENT

        if (
            normalized_percent
            >= cls.GOOD_MIN_PERCENT
        ):
            return AssessmentGrade.GOOD

        if (
            normalized_percent
            >= cls.SATISFACTORY_MIN_PERCENT
        ):
            return AssessmentGrade.SATISFACTORY

        return AssessmentGrade.UNSATISFACTORY

    # =====================================================
    # SCALE
    # =====================================================

    @classmethod
    def build_scale(
        cls,
        *,
        max_score: Decimal | int | float | str,
        score_step: Decimal | int | float | str = 1,
    ) -> tuple[
        AssessmentGradeScaleItem,
        AssessmentGradeScaleItem,
        AssessmentGradeScaleItem,
        AssessmentGradeScaleItem,
    ]:
        """
        Построить шкалу оценивания по максимальному баллу.

        score_step определяет минимальный шаг балла.

        Например:

            max_score = 30
            score_step = 1

        получим:

            5 -> 26–30
            4 -> 20–25
            3 -> 12–19
            2 -> 0–11

        Если работа допускает половинные баллы:

            score_step = 0.5

        шкала будет рассчитана с шагом 0.5.
        """

        normalized_max_score = cls._to_decimal(
            max_score,
            field_name="max_score",
        )

        normalized_step = cls._to_decimal(
            score_step,
            field_name="score_step",
        )

        if normalized_max_score <= 0:
            raise ValueError(
                "max_score должен быть больше 0"
            )

        if normalized_step <= 0:
            raise ValueError(
                "score_step должен быть больше 0"
            )

        excellent_min = cls._ceil_to_step(
            normalized_max_score
            * Decimal("0.85"),
            normalized_step,
        )

        good_min = cls._ceil_to_step(
            normalized_max_score
            * Decimal("0.65"),
            normalized_step,
        )

        satisfactory_min = cls._ceil_to_step(
            normalized_max_score
            * Decimal("0.40"),
            normalized_step,
        )

        excellent = AssessmentGradeScaleItem(
            grade=AssessmentGrade.EXCELLENT,
            min_percent=Decimal("85"),
            max_percent=Decimal("100"),
            min_score=excellent_min,
            max_score=normalized_max_score,
        )

        good = AssessmentGradeScaleItem(
            grade=AssessmentGrade.GOOD,
            min_percent=Decimal("65"),
            max_percent=Decimal("84.9999"),
            min_score=good_min,
            max_score=excellent_min - normalized_step,
        )

        satisfactory = AssessmentGradeScaleItem(
            grade=AssessmentGrade.SATISFACTORY,
            min_percent=Decimal("40"),
            max_percent=Decimal("64.9999"),
            min_score=satisfactory_min,
            max_score=good_min - normalized_step,
        )

        unsatisfactory = AssessmentGradeScaleItem(
            grade=AssessmentGrade.UNSATISFACTORY,
            min_percent=Decimal("0"),
            max_percent=Decimal("39.9999"),
            min_score=Decimal("0"),
            max_score=(
                satisfactory_min
                - normalized_step
            ),
        )

        return (
            excellent,
            good,
            satisfactory,
            unsatisfactory,
        )

    # =====================================================
    # VALIDATION
    # =====================================================

    @classmethod
    def validate_score(
        cls,
        *,
        score: Decimal | int | float | str,
        max_score: Decimal | int | float | str,
    ) -> None:
        """
        Публичная проверка введённого балла.
        """

        normalized_score = cls._to_decimal(
            score,
            field_name="score",
        )

        normalized_max_score = cls._to_decimal(
            max_score,
            field_name="max_score",
        )

        cls._validate_scores(
            score=normalized_score,
            max_score=normalized_max_score,
        )

    @staticmethod
    def _validate_scores(
        *,
        score: Decimal,
        max_score: Decimal,
    ) -> None:
        if max_score <= 0:
            raise ValueError(
                "max_score должен быть больше 0"
            )

        if score < 0:
            raise ValueError(
                "score не может быть меньше 0"
            )

        if score > max_score:
            raise ValueError(
                "score не может превышать max_score"
            )

    # =====================================================
    # INTERNAL
    # =====================================================

    @staticmethod
    def _to_decimal(
        value: Decimal | int | float | str,
        *,
        field_name: str,
    ) -> Decimal:
        """
        Безопасно преобразовать значение в Decimal.

        float преобразуется через str, чтобы избежать
        двоичных погрешностей Float.
        """

        if isinstance(value, Decimal):
            result = value

        else:
            try:
                result = Decimal(str(value))
            except Exception as exc:
                raise ValueError(
                    f"{field_name} содержит "
                    f"некорректное числовое значение"
                ) from exc

        if not result.is_finite():
            raise ValueError(
                f"{field_name} должен быть "
                f"конечным числом"
            )

        return result

    @staticmethod
    def _ceil_to_step(
        value: Decimal,
        step: Decimal,
    ) -> Decimal:
        """
        Округлить вверх до ближайшего допустимого шага.

        Примеры:

            value=25.5, step=1
                -> 26

            value=25.5, step=0.5
                -> 25.5
        """

        units = (
            value / step
        ).to_integral_value(
            rounding=ROUND_CEILING
        )

        return units * step
