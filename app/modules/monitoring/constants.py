# app/modules/monitoring/constants.py

from app.modules.reports.enums import TaskDocumentStatus


VALID_SCORE_DOCUMENT_STATUSES = (
    TaskDocumentStatus.SUBMITTED,
    TaskDocumentStatus.APPROVED,
    TaskDocumentStatus.ACCEPTED,
)

FINAL_DOCUMENT_SCORE = 1
REPORT_SCORE = 1
