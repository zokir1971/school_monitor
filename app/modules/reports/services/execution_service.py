# app/modules/reports/services/execution_service.py
from __future__ import annotations
from app.modules.planning.content_i18n import content_text, language
import json

from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanItemStatus, ReviewPlace
from app.modules.reports.enums import TaskCompletionMode, TaskDocumentStatus
from app.modules.reports.models_documents import TaskExecutionData
from app.modules.reports.schemas.execution_dto import ExecutionFormDTO
from app.modules.reports.repositories.execution_document_repo import (
    ExecutionDocumentRepo,
)
from app.modules.reports.repositories.execution_repo import ExecutionRepo
from app.modules.reports.repositories.report_type_repo import ReportTypeRepo
from app.modules.reports.rules.control_flow import build_algorithm_plan


class ExecutionService:
    """
    Бизнес-логика выполнения задачи.

    Отвечает за:
    - построение execution DTO;
    - сохранение черновика выполнения;
    - подготовку данных страницы выполнения;
    - завершение задачи.

    Файловый lifecycle итоговых документов вынесен
    в ExecutionDocumentService.
    """


    build_execution_form_dto = ExecutionFormDTO.from_model

    @classmethod
    async def save_execution_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            control_scope: str,
            control_form: str,
            control_kind: str,
            review_result: str,
            report_types: list[str] | None = None,
            subjects: list[str] | None = None,
            class_groups: list[str] | None = None,
            parallel_classes: list[str] | None = None,
            teacher_ids: list[str] | None = None,
            teacher_id: str | None = None,
            report_teacher_ids: dict[str, list[str]] | None = None,
            school_class_ids: list[str] | None = None,
            algorithm_revision: int = 0,
            report_areas_json: str | None = None,
    ) -> TaskExecutionData:
        task = await ExecutionRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )
        if not task:
            raise ValueError("Задача недоступна для сохранения черновика.")

        catalog = await ExecutionRepo.get_algorithm_catalog(db, month_item_id=month_item_id, user_id=user_id)
        report_type_map = await ReportTypeRepo.get_code_id_map(db)
        areas = None
        if report_areas_json is not None:
            if len(report_areas_json)>524288:raise ValueError('Слишком много параметров областей. / Ауқым параметрлері тым көп.')
            try:areas=json.loads(report_areas_json)
            except (ValueError,TypeError):raise ValueError('Проверьте параметры областей. / Ауқым параметрлерін тексеріңіз.')
        plan = build_algorithm_plan(catalog, scope=control_scope, report_types=report_types or [],
                                    subject_ids=subjects or [], class_ids=school_class_ids or [],
                                    parallels=parallel_classes or [], class_groups=class_groups or [],
                                    teacher_ids=teacher_ids or ([teacher_id] if teacher_id else []),
                                    report_teacher_ids=report_teacher_ids or {},
                                    report_type_map=report_type_map, task_id=month_item_id, form=control_form, kind=control_kind,report_areas=areas)
        execution_data = await ExecutionRepo.get_or_create_execution_data(db, month_item_id=month_item_id)
        await ExecutionRepo.replace_selected_reports(db, execution_data_id=execution_data.id,
                                                    selected_reports=plan['selected_reports'],
                                                    algorithm_parameters=plan['parameters'], expected_revision=algorithm_revision)
        execution_data.completion_mode = TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS.value
        execution_data.control_scope = control_scope or None
        execution_data.control_form = control_form or None
        execution_data.control_kind = control_kind or None
        execution_data.review_result = review_result or None
        if areas and areas.get('save_school_scheme'):
            if not plan['parameters'].get('report_areas'):
                raise ValueError('Сначала подготовьте области отчётов. / Алдымен есеп ауқымдарын дайындаңыз.')
            if areas.get('coverage_exclusions'):
                raise ValueError('Сохраните алгоритм с исключениями отдельно от школьной схемы. / Ерекшеліктері бар алгоритмді мектеп сызбасынан бөлек сақтаңыз.')
            from app.modules.reports.rules.report_area_scheme import school_layout
            from app.modules.reports.repositories.report_area_scheme_repo import save as save_scheme
            revision=areas.get('scheme_revision')
            if type(revision) is not int or revision<0:
                raise ValueError('Обновите версию школьной схемы. / Мектеп сызбасының нұсқасын жаңартыңыз.')
            configuration=school_layout(plan['parameters']['report_areas'],catalog,catalog.get('area_scheme'))
            await save_scheme(db,school_id=catalog['school_id'],task_id=month_item_id,user_id=user_id,
                              expected_revision=revision,configuration=configuration)
        await db.commit()
        await db.refresh(execution_data)
        return execution_data

    @classmethod
    async def get_execution_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> dict:
        task = await ExecutionRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not task:
            raise ValueError("Задача не найдена или недоступна.")

        execution_data = await ExecutionRepo.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        execution_dto = cls.build_execution_form_dto(execution_data)

        required_documents = await ExecutionRepo.get_required_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

        final_documents = await ExecutionDocumentRepo.get_final_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

        current_final_document = await ExecutionDocumentRepo.get_current_final_document_for_task(
            db,
            month_item_id=month_item_id,
        )

        is_done = task.status == PlanItemStatus.DONE

        completion_ready = bool(execution_data) and len(required_documents) > 0

        review_place_text = "—"

        if getattr(task, "review_places", None):
            values = []

            for item in task.review_places:
                review_place = getattr(item, "review_place", None)

                if not review_place:
                    continue

                try:
                    enum_place = ReviewPlace(review_place)
                    values.append(enum_place.label_kz)

                except ValueError:
                    values.append(str(review_place))
            if values:
                review_place_text = ", ".join(values)

        task_topic = (
                content_text(getattr(task, "source_row11", None), 'topic')
                or "—"
        )

        task_goal = (
                content_text(getattr(task, "source_row11", None), 'goal')
                or "—"
        )

        return {
            "task": task,
            "task_topic": task_topic,
            "task_goal": task_goal,

            "review_place_text": review_place_text,

            "execution": execution_dto,

            "required_documents": required_documents,
            "final_documents": final_documents,
            "current_final_document": current_final_document,

            "has_final_document": current_final_document is not None,
            "final_document_status": (
                current_final_document.status
                if current_final_document
                else None
            ),

            "completion_ready": completion_ready,
            "is_done": is_done,
        }

    @classmethod
    async def complete_task_execution(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            completion_mode: TaskCompletionMode,
    ):
        locked_task = await ExecutionDocumentRepo.lock_task_row(db, month_item_id=month_item_id)
        if locked_task and any(str(getattr(locked_task[k], 'value', locked_task[k])) == 'archived' for k in ('month_status', 'annual_status')):
            raise ValueError("Архивную задачу изменять нельзя.")

        task = await ExecutionRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not task:
            raise ValueError("Задача не найдена или недоступна.")

        if task.status == PlanItemStatus.DONE:
            raise ValueError("Задача уже завершена.")

        execution = await ExecutionRepo.get_execution_data_for_task(db, month_item_id=month_item_id)
        saved_mode = cls.build_execution_form_dto(execution).completion_mode if execution else ""
        if completion_mode == TaskCompletionMode.SIMPLE_FINAL_DOCUMENT and (
            saved_mode == TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS.value
            or (execution is not None and execution.selected_reports)
        ):
            raise ValueError("Для этой задачи выбран вариант с системными отчётами. Завершите отчёты и отправьте итоговый документ.")

        final_document = await ExecutionDocumentRepo.get_current_final_document_for_task(
            db,
            month_item_id=month_item_id,
        )

        if not final_document:
            raise ValueError("Сначала загрузите итоговый документ.")

        snapshot = final_document.schema_json or {}
        assembled_reference = final_document.report_code == 'analytical_reference' and snapshot.get('assembly_version') == 1
        if assembled_reference:
            from app.modules.reports.services.final_reference_assembly import fingerprint
            from app.modules.reports.services.structured_report_service import source_snapshot
            from app.modules.reports.repositories.structured_report_repo import evidence
            from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo
            if final_document.status != TaskDocumentStatus.SUBMITTED:
                raise ValueError("Сначала подпишите итоговую справку и сформируйте PDF.")
            signature = await ReportVerifyRepo.get_active_signature_for_document(db, report_type='analytical_reference', document_id=final_document.id)
            if signature is None:
                raise ValueError("Подпись итоговой справки не найдена.")
            sources = await evidence(db, locked_task['school_id'], month_item_id)
            if len(sources) > 2000:
                raise ValueError("Слишком много исходных отчётов.")
            entries, _ = source_snapshot({'source_reports': sources}, True)
            if not entries or fingerprint(entries, snapshot.get('source_fingerprint_version', 1)) != snapshot.get('source_fingerprint'):
                raise ValueError("Исходные отчёты изменились после подписания. Создайте новую версию справки и обновите данные отчётов.")

        if execution is None:
            execution = await ExecutionRepo.get_or_create_execution_data(db, month_item_id=month_item_id)

        execution.completion_mode = completion_mode.value
        db.add(execution)

        if completion_mode == TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS and not assembled_reference:
            missing_reports = await ExecutionRepo.get_missing_selected_reports(
                db,
                month_item_id=month_item_id,
            )

            if missing_reports:
                raise ValueError(
                    "Не заполнены выбранные отчеты: "
                    + ", ".join(missing_reports)
                )

            await ExecutionRepo.mark_current_system_reports_submitted(
                db,
                month_item_id=month_item_id,
                user_id=user_id,
            )

        now = datetime.now(timezone.utc)

        task.status = PlanItemStatus.DONE
        task.executed_at = date.today()
        task.completed_at = now
        task.completed_by_user_id = user_id

        final_document.status = TaskDocumentStatus.SUBMITTED
        final_document.submitted_by_user_id = user_id
        final_document.submitted_at = now

        db.add(task)
        db.add(final_document)

        await db.commit()
