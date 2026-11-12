"""Register typed lesson/notebook handlers and the shared snapshot handler."""
from app.modules.reports.enums import ReportType
from app.modules.reports.utils.report_verify_registry import ReportVerifyRegistry
from app.modules.reports.utils.verify_handlers import LessonObservationVerifyHandler, CheckingNotebooksVerifyHandler
from app.modules.reports.utils.assessment_report_verify import QualityVerifyHandler
from app.modules.reports.assessment_report_types import REPORT_TYPES


def setup_report_verify_registry():
    ReportVerifyRegistry.register(ReportType.LESSON_OBSERVATION.value,LessonObservationVerifyHandler)
    ReportVerifyRegistry.register(ReportType.CHECKING_NOTEBOOKS_TABLE.value,CheckingNotebooksVerifyHandler)
    for code in REPORT_TYPES:
        ReportVerifyRegistry.register(code,type('SystemReportVerifyHandler',(QualityVerifyHandler,),{'CODE':code}))
