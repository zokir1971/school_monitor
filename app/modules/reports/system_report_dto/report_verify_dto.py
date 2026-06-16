# app/modules/reports/system_report_dto/report_verify_dto.py
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ReportVerifyViewDTO:
    valid: bool

    report_type: str | None = None
    report_label: str | None = None

    report_id: int | None = None
    document_id: int | None = None

    signed_at: datetime | None = None
    total: int | None = None

    details: list[dict] = field(default_factory=list)

    error: str | None = None
