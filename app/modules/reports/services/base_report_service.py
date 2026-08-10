# app/modules/reports/services/base_report_service.py

from __future__ import annotations

from typing import Any, cast

from app.modules.users.models import User


class BaseReportService:
    """
    Общие helper-методы сервисов отчетов новой архитектуры.

    Здесь не должно быть бизнес-логики конкретного типа отчета.
    """

    @staticmethod
    def require_user_context(
            user: User,
    ) -> tuple[int, int]:
        """
        Вернуть school_id и staff_member_id текущего пользователя.

        Raises:
            ValueError:
                если пользователь не связан со школой или сотрудником школы.
        """

        if user.school_id is None:
            raise ValueError(
                "У пользователя не определена школа."
            )

        if user.staff_member_id is None:
            raise ValueError(
                "Для пользователя не найден сотрудник школы."
            )

        return (
            cast(int, user.school_id),
            cast(int, user.staff_member_id),
        )

    @staticmethod
    def parse_int(
            raw_value: Any,
            *,
            default: int = 0,
    ) -> int:
        """
        Безопасно преобразовать значение формы в int.

        Пустые/некорректные значения возвращают default.
        """

        try:
            if raw_value in (None, ""):
                return default

            return int(raw_value)

        except (TypeError, ValueError):
            return default

    @staticmethod
    def clean_text(
            raw_value: Any,
    ) -> str | None:
        """
        Нормализовать текстовое значение формы.

        Возвращает None для None, пустой строки
        или строки, состоящей только из пробелов.
        """

        if raw_value is None:
            return None

        cleaned = str(raw_value).strip()

        return cleaned or None
