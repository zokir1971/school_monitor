# app/modules/reports/template_registry.py

from __future__ import annotations

from app.modules.reports.enums import ReportType


# Registry теперь хранит только метаданные маршрутизации.
#
# Он больше НЕ импортирует System*Service и не определяет,
# каким сервисом сохраняется отчет. System/User одного типа отчета
# используют один канонический fill-route и один сервис.
SYSTEM_REPORT_CONFIG = {
    ReportType.LESSON_OBSERVATION.value: {
        "fill_route": "staff_user_lesson_observation_fill_page",
        "pdf_route": "lesson_observation_pdf_view",
    },

    ReportType.CHECKING_NOTEBOOKS_TABLE.value: {
        "fill_route": "checking_notebooks_fill_page",
        "pdf_route": "checking_notebooks_pdf_view",
    },
}
