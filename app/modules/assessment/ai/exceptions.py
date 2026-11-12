# app/modules/assessment/ai/exceptions.py
from __future__ import annotations


class AIProviderError(RuntimeError):
    """
    Ошибка внешнего AI-провайдера.

    Изолирует application/service слои School Monitor
    от исключений конкретного SDK.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
    ) -> None:
        super().__init__(message)
        self.code = code
