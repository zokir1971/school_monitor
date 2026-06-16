# app/modules/reports/utils/report_verify_setup.py

from app.modules.reports.enums import ReportType
from app.modules.reports.utils.report_verify_registry import ReportVerifyRegistry
from app.modules.reports.utils.verify_handlers import LessonObservationVerifyHandler, CheckingNotebooksVerifyHandler


def setup_report_verify_registry():
    ReportVerifyRegistry.register(
        ReportType.LESSON_OBSERVATION.value,
        LessonObservationVerifyHandler,
    )

    ReportVerifyRegistry.register(
        ReportType.CHECKING_NOTEBOOKS_TABLE.value,
        CheckingNotebooksVerifyHandler,
    )
