# app/modules/reports/schemas/report_template_dto.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.reports.enums import ReportTemplateMode


@dataclass(slots=True)
class ResolvedReportTemplateDTO:
    """
    Нормализованное описание шаблона отчета.

    DTO не представляет TaskExecutionDocument и ничего не сохраняет в БД.
    Он используется как результат разрешения источника шаблона перед
    открытием формы или созданием snapshot документа.

    Соответствие режимов:
    - ReportTemplateMode.STANDARD -> системный шаблон;
    - ReportTemplateMode.CUSTOM   -> пользовательский шаблон.
    """

    report_code: str
    report_label: str

    template_mode: ReportTemplateMode

    schema: dict[str, Any] = field(default_factory=dict)

    # Заполняется только для пользовательского шаблона.
    user_template_id: int | None = None
    template_title: str | None = None

    @property
    def is_system(self) -> bool:
        return self.template_mode == ReportTemplateMode.STANDARD

    @property
    def is_user(self) -> bool:
        return self.template_mode == ReportTemplateMode.CUSTOM
