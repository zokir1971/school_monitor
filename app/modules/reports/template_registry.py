# app/modules/reports/template_registry.py
from app.modules.reports.enums import ReportType
from app.modules.reports.services.system_lesson_observation_service import SystemLessonObservationService
from app.modules.reports.services.system_checking_notebooks_service import SystemCheckingNotebooksService

SYSTEM_REPORT_CONFIG = {
    ReportType.LESSON_OBSERVATION.value: {
        "template": "staff/reports/template_map/_lesson_observation.html",
        "service": SystemLessonObservationService,
        "pdf_route": "lesson_observation_pdf_view",
    },
    ReportType.CHECKING_NOTEBOOKS_TABLE.value: {
        "template": "staff/reports/user_templates/_checking_notebooks_table.html",
        "service": SystemCheckingNotebooksService,
        "pdf_route": "checking_notebooks_pdf_view",
    },
}