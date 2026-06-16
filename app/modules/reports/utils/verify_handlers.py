# app/modules/reports/utils/verify_handlers.py

from app.modules.reports.system_report_dto.report_verify_dto import ReportVerifyViewDTO
from app.modules.reports.utils.report_verify_registry import ReportVerifyRegistry
from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo


class LessonObservationVerifyHandler:

    @staticmethod
    async def build(
            db,
            *,
            report_id: int,
            document_id: int | None,
            total: int | None,
    ) -> ReportVerifyViewDTO:

        report = await ReportVerifyRepo.get_lesson_observation_by_id(
            db,
            report_id,
        )

        if not report:
            raise ValueError("Отчет не найден")

        return ReportVerifyViewDTO(
            valid=True,
            report_type="lesson_observation",
            report_label="Сабақты бақылау парағы",
            report_id=report.id,
            document_id=document_id,
            signed_at=report.submitted_at,
            total=total,
            details=[
                {"label": "Білім беру ұйымы", "value": getattr(report, "school_name", None)},
                {"label": "Педагог", "value": getattr(report, "teacher_full_name", None) or getattr(report, "teacher_name", None)},
                {"label": "Пән", "value": getattr(report, "teacher_subject", None) or getattr(report, "subject", None)},
                {"label": "Бақылаушы", "value": getattr(report, "observer_full_name", None)},
            ],
        )


class CheckingNotebooksVerifyHandler:

    @staticmethod
    async def build(
            db,
            *,
            report_id: int,
            document_id: int | None,
            total: int | None,
    ) -> ReportVerifyViewDTO:

        report = await ReportVerifyRepo.get_checking_notebooks_by_id(
            db,
            report_id,
        )

        if not report:
            raise ValueError("Отчет не найден")

        return ReportVerifyViewDTO(
            valid=True,
            report_type="checking_notebooks",
            report_label="Дәптер тексеру кестесі",
            report_id=report.id,
            document_id=document_id,
            signed_at=report.submitted_at,
            total=total,
            details=[
                {"label": "Білім беру ұйымы", "value": getattr(report, "school_name", None)},
                {"label": "Мұғалім", "value": getattr(report, "teacher_name", None)},
                {"label": "Сынып", "value": getattr(report, "class_name", None)},
                {"label": "Пән", "value": getattr(report, "subject_name", None)},
            ],
        )


ReportVerifyRegistry.register(
    "lesson_observation",
    LessonObservationVerifyHandler,
)

ReportVerifyRegistry.register(
    "checking_notebooks",
    CheckingNotebooksVerifyHandler,
)
