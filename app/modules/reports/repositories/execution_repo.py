# app/modules/reports/repositories/execution_repo.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update, insert, exists, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload

from app.modules.planning.enums import PlanItemStatus
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
)
from app.modules.planning.models_school import (
    SchoolPlan,
    SchoolPlanRow11,
    SchoolPlanRow11RequiredDocument,
)
from app.modules.reports.enums import DocumentType, TaskDocumentStatus
from app.modules.reports.models_documents import (
    ReportTypeModel,
    SchoolReportAreaScheme,
    TaskExecutionData,
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)
from app.modules.reports.models_report_assignments import TaskSelectedReportAssignment
from app.modules.reports.models_template_reports import CheckingNotebooksReport
from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole
from app.modules.users.models import User
from app.modules.education.models import Subject, SchoolClass, SchoolClassSubject, SchoolClassSubjectTeacher, SchoolSubjectSubgroup, CurriculumSubjectRule, SubjectMethodProfile
from app.modules.reports.report_schemas import ExecutionPageBundle


class ExecutionRepo:
    """
    Repository жизненного цикла выполнения задачи.

    Отвечает за:
    - TaskExecutionData;
    - выбранные системные отчеты;
    - обязательные документы;
    - проверку доступа исполнителя;
    - проверку готовности системных отчетов к завершению задачи.

    Не отвечает за файловый lifecycle итоговых документов.
    Для него используется ExecutionDocumentRepo.
    """

    @classmethod
    async def get_execution_data_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionData | None:
        """
        Получить execution_data для задачи.

        Что подгружаем:
        - report_type_links
        - report_type для каждого link

        Почему нужен selectinload:
        - чтобы service мог безопасно собрать report_types
          без дополнительных lazy-запросов
        """
        stmt = (
            select(TaskExecutionData).options(raiseload("*"))
            .where(TaskExecutionData.month_item_id == month_item_id)
            .options(
                selectinload(TaskExecutionData.selected_reports).selectinload(
                    TaskExecutionSelectedReport.report_type
                ),
            )
        )
        return await db.scalar(stmt)

    @classmethod
    async def get_executor_month_item_for_execution(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> SchoolMonthPlanItem | None:
        stmt = (
            select(SchoolMonthPlanItem).options(raiseload("*"))
            .where(SchoolMonthPlanItem.id == month_item_id)
            .where(
                SchoolMonthPlanItem.status.in_(
                    [PlanItemStatus.TODO, PlanItemStatus.IN_PROGRESS, PlanItemStatus.DONE]
                )
            )
            .options(
                selectinload(SchoolMonthPlanItem.review_places),
                selectinload(SchoolMonthPlanItem.source_row11),
            )
        )

        stmt = cls._apply_executor_user_filter(stmt, user_id=user_id)

        return await db.scalar(stmt)

    @classmethod
    async def get_or_create_execution_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionData:
        execution_data = await cls.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )
        if execution_data:
            return execution_data

        execution_data = TaskExecutionData(
            month_item_id=month_item_id,
        )
        db.add(execution_data)
        await db.flush()
        return execution_data

    @classmethod
    async def replace_selected_reports(
            cls,
            db: AsyncSession,
            *,
            execution_data_id: int,
            selected_reports: list[dict],
            algorithm_parameters: dict | None = None,
            expected_revision: int | None = None,
    ) -> None:
        """Synchronize the natural keys; preserve selected IDs and their dependent data.

        Call within the algorithm transaction. SQL is batched; no lazy loads.
        The task lock matches document save order, then selected rows are locked
        to serialize changes and protect concurrent FK-based document inserts.
        """
        requested = {}
        for item in selected_reports:
            report_type_id = int(item.get("report_type_id") or 0)
            if report_type_id <= 0:
                raise ValueError("Некорректный тип отчёта. / Есеп түрі дұрыс емес.")
            for target in item.get("targets") or []:
                kind = str(target.get("target_kind") or "").strip()
                value = str(target.get("target_value") or "").strip()
                if not kind or not value:
                    raise ValueError("Не указан объект отчёта. / Есеп нысаны көрсетілмеген.")
                requested[(report_type_id, kind, value)] = str(target.get("target_label") or "").strip() or None

        E, I = TaskExecutionData.__table__, SchoolMonthPlanItem.__table__
        S, D = TaskExecutionSelectedReport.__table__, TaskExecutionDocument.__table__
        A, C = TaskSelectedReportAssignment.__table__, CheckingNotebooksReport.__table__
        task_id = (await db.execute(select(E.c.month_item_id).where(E.c.id == execution_data_id))).scalar_one()
        task = (await db.execute(select(I.c.id, I.c.status, I.c.completed_at).where(I.c.id == task_id).with_for_update())).mappings().one()
        if task['completed_at'] or str(getattr(task['status'], 'value', task['status'])) in ('done', 'reviewed'):
            raise ValueError("Завершённую задачу нельзя изменять через алгоритм. / Аяқталған тапсырманың алгоритмін өзгертуге болмайды.")
        stored_parameters = (await db.execute(select(E.c.algorithm_parameters).where(E.c.id == execution_data_id).with_for_update())).scalar_one() or {}
        if algorithm_parameters is None and stored_parameters.get('version')==2:
            raise ValueError('Сохраните алгоритм через актуальную форму параметров. / Алгоритмді параметрлердің қолданыстағы нысаны арқылы сақтаңыз.')
        if algorithm_parameters is not None:
            revision = int(stored_parameters.get('revision') or 0)
            if expected_revision != revision:
                raise ValueError('Алгоритм изменён в другом окне. Обновите страницу. / Алгоритм басқа терезеде өзгертілген. Бетті жаңартыңыз.')
            from app.modules.reports.rules.control_flow import area_scope, is_scope_extension
            if stored_parameters.get('report_areas_mode') and 'report_areas_mode' not in algorithm_parameters:
                raise ValueError('Обновите форму алгоритма: в ней отсутствуют сохранённые области. / Алгоритм нысанын жаңартыңыз: сақталған ауқымдар жоқ.')
            dimension_keys = ('scope', 'year_start', 'subject_ids', 'class_ids', 'subject_class_pairs')
            dimensions_changed = any(stored_parameters.get(key) != algorithm_parameters.get(key) for key in dimension_keys) or area_scope(stored_parameters) != area_scope(algorithm_parameters)
            if dimensions_changed and not is_scope_extension(stored_parameters, algorithm_parameters):
                protected_scope = (await db.execute(select(S.c.id).where(S.c.execution_data_id == execution_data_id, or_(
                    exists(select(D.c.id).where(D.c.selected_report_id == S.c.id)),
                    exists(select(C.c.id).where(C.c.selected_report_id == S.c.id)),
                    exists(select(A.c.id).where(A.c.selected_report_id == S.c.id, A.c.status.in_(['completed', 'waived']))))).limit(1))).first()
                if protected_scope:
                    raise ValueError('Нельзя менять область проверки: уже есть сохранённые документы или завершения. / Тексеру ауқымын өзгертуге болмайды: сақталған құжаттар немесе аяқталу белгілері бар.')
            algorithm_parameters = dict(algorithm_parameters, revision=revision + 1)

        rows = (await db.execute(select(S).where(S.c.execution_data_id == execution_data_id).with_for_update())).mappings().all()
        existing = {(row['report_type_id'], row['target_kind'], row['target_value']): row for row in rows}
        removed = [row['id'] for key, row in existing.items() if key not in requested]
        if removed:
            protected = (await db.execute(select(S.c.id).where(S.c.id.in_(removed), or_(
                exists(select(D.c.id).where(D.c.selected_report_id == S.c.id)),
                exists(select(C.c.id).where(C.c.selected_report_id == S.c.id)),
                exists(select(A.c.id).where(A.c.selected_report_id == S.c.id, A.c.status.in_(['completed', 'waived']))),
            )).order_by(S.c.id))).scalars().all()
            if protected:
                ids = ', '.join(map(str, protected))
                raise ValueError(f"Нельзя убрать отчёты №{ids}: уже есть черновик, документ или зафиксированное завершение. Состав алгоритма не изменён. / Есептерді алып тастауға болмайды: жоба, құжат немесе аяқталу белгісі бар. Алгоритм құрамы өзгерген жоқ.")

        # Validate the full diff before the first mutation.
        if removed:
            await db.execute(delete(A).where(A.c.selected_report_id.in_(removed)))
            await db.execute(delete(S).where(S.c.id.in_(removed)))
        additions = [dict(execution_data_id=execution_data_id, report_type_id=key[0], target_kind=key[1],
                          target_value=key[2], target_label=label)
                     for key, label in requested.items() if key not in existing]
        if additions:
            await db.execute(insert(S), additions)
        # Labels do not define identity and may change without replacing the row.
        from sqlalchemy import bindparam
        labels = [dict(selected_id=existing[key]['id'], new_label=label)
                  for key, label in requested.items() if key in existing and existing[key]['target_label'] != label]
        if labels:
            await db.execute(update(S).where(S.c.id == bindparam('selected_id')).values(target_label=bindparam('new_label')), labels)
        if algorithm_parameters is not None:
            await db.execute(update(E).where(E.c.id == execution_data_id).values(algorithm_parameters=algorithm_parameters))
        await db.flush()

    @classmethod
    async def get_required_documents_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[SchoolPlanRow11RequiredDocument]:
        """
        Получить список обязательных документов для задачи.

        Что грузим:
        - только одну month-plan задачу
        - source_row11
        - required_documents у source_row11

        Почему так:
        - не делаем join на все подряд
        - selectinload хорошо масштабируется для 1 -> many
        - не тянем ненужные связи required_document дальше
        """
        stmt = (
            select(SchoolMonthPlanItem).options(raiseload("*"))
            .where(SchoolMonthPlanItem.id == month_item_id)
            .options(
                selectinload(SchoolMonthPlanItem.source_row11).selectinload(
                    SchoolPlanRow11.required_documents
                )
            )
        )

        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        if not task or not task.source_row11:
            return []

        required_documents = getattr(task.source_row11, "required_documents", None) or []
        return list(required_documents)

    @staticmethod
    def _apply_executor_user_filter(stmt, *, user_id: int):
        school_id = select(User.school_id).where(User.id == user_id, User.is_active.is_(True)).scalar_subquery()
        return stmt.where(
            SchoolMonthPlanItem.is_included.is_(True),
            SchoolMonthPlanItem.month_plan.has(
                SchoolMonthPlan.school_plan.has(SchoolPlan.school_id == school_id)
            ),
            SchoolMonthPlanItem.assignees.any(
                SchoolMonthPlanItemAssignee.staff_role.has(
                    (SchoolStaffRole.is_active.is_(True)) &
                    SchoolStaffRole.staff_member.has(
                        SchoolStaffMember.is_active.is_(True) &
                        (SchoolStaffMember.school_id == school_id) &
                        SchoolStaffMember.user_account.has(User.id == user_id)
                    )
                )
            )
        )

    @classmethod
    async def user_has_access_to_month_item(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> bool:
        """
        Проверить, имеет ли пользователь доступ к задаче.
        """
        stmt = (
            select(SchoolMonthPlanItem.id)
            .where(SchoolMonthPlanItem.id == month_item_id)
        )
        stmt = cls._apply_executor_user_filter(stmt, user_id=user_id)

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_algorithm_catalog(db: AsyncSession, *, month_item_id: int, school_id: int | None = None, user_id: int | None = None) -> dict:
        """Five bounded queries for one school's plan year; never a query per teacher."""
        I, M, P = SchoolMonthPlanItem.__table__, SchoolMonthPlan.__table__, SchoolPlan.__table__
        L = SchoolReportAreaScheme.__table__
        statement = (select(P.c.school_id, P.c.academic_year, P.c.status.label('plan_status'), M.c.status.label('month_status'), L.c.configuration.label('area_scheme'), L.c.revision.label('area_scheme_revision'))
                     .select_from(I.join(M, M.c.id == I.c.month_plan_id).join(P, P.c.id == M.c.school_plan_id).outerjoin(L,L.c.school_id == P.c.school_id))
                     .where(I.c.id == month_item_id))
        if school_id is not None:
            statement = statement.where(P.c.school_id == school_id)
        if user_id is not None:
            U = User.__table__
            statement = statement.join(U, U.c.school_id == P.c.school_id).where(U.c.id == user_id)
        context = (await db.execute(statement)).mappings().one_or_none()
        if context is None:
            raise ValueError('Задача не найдена в школе пользователя. / Тапсырма пайдаланушының мектебінен табылмады.')
        try:
            year = int(str(context['academic_year']).replace('–', '-').replace('—', '-').replace('/', '-').split('-')[0])
        except (TypeError, ValueError):
            raise ValueError('Проверьте учебный год плана. / Жоспардың оқу жылын тексеріңіз.')
        C, S, CS = SchoolClass.__table__, Subject.__table__, SchoolClassSubject.__table__
        CR, MP = CurriculumSubjectRule.__table__, SubjectMethodProfile.__table__
        A, F, G = SchoolClassSubjectTeacher.__table__, SchoolStaffMember.__table__, SchoolSubjectSubgroup.__table__
        classes = (await db.execute(select(C.c.id, C.c.grade_level, C.c.letter, C.c.instruction_language, C.c.education_track)
                   .where(C.c.school_id == context['school_id'], C.c.academic_year_start == year, C.c.is_active.is_(True))
                   .order_by(C.c.grade_level, C.c.letter, C.c.id))).mappings().all()
        class_ids = [row['id'] for row in classes]
        if not class_ids:
            return dict(school_id=context['school_id'], year_start=year, plan_status=context['plan_status'], month_status=context['month_status'], classes=[], subjects=[], teaching=[], subject_classes=[])
        curricular = exists(select(CS.c.id).where(CS.c.subject_id == S.c.id, CS.c.school_id == context['school_id'], CS.c.school_class_id.in_(class_ids), CS.c.is_active.is_(True)))
        assigned = exists(select(A.c.id).where(A.c.subject_id == S.c.id, A.c.school_id == context['school_id'], A.c.school_class_id.in_(class_ids), A.c.is_active.is_(True)))
        subjects = (await db.execute(select(S.c.id, S.c.code, S.c.name_ru, S.c.name_kz).where(S.c.is_active.is_(True), or_(curricular, assigned))
                    .order_by(S.c.sort_order, S.c.id))).mappings().all()
        live_subgroup = exists(select(G.c.id).where(G.c.id == A.c.subgroup_id, G.c.school_id == context['school_id'], G.c.school_class_id == A.c.school_class_id,
                                                   G.c.subject_id == A.c.subject_id, G.c.is_active.is_(True)))
        teaching = (await db.execute(select(A.c.staff_member_id.label('teacher_id'), F.c.full_name, A.c.subject_id, A.c.school_class_id.label('class_id'))
                    .select_from(A.join(F, F.c.id == A.c.staff_member_id).join(S, S.c.id == A.c.subject_id))
                    .where(A.c.school_id == context['school_id'], F.c.school_id == context['school_id'], A.c.school_class_id.in_(class_ids),
                           A.c.is_active.is_(True), A.c.unassigned_at.is_(None), S.c.is_active.is_(True), F.c.is_active.is_(True),
                           or_(A.c.subgroup_id.is_(None), live_subgroup)).distinct()
                    .order_by(F.c.full_name, A.c.staff_member_id, A.c.school_class_id, A.c.subject_id))).mappings().all()
        curriculum_pairs = (await db.execute(select(CS.c.subject_id, CS.c.school_class_id.label('class_id'),CR.c.method_profile_id,MP.c.code.label('profile_code'),MP.c.name.label('profile_name'))
            .select_from(CS.outerjoin(CR,CR.c.id==CS.c.rule_id).outerjoin(MP,MP.c.id==CR.c.method_profile_id))
            .where(CS.c.school_id == context['school_id'], CS.c.school_class_id.in_(class_ids), CS.c.is_active.is_(True)).distinct())).mappings().all()
        subject_set = {row['id'] for row in subjects}
        pairs = sorted({(row['subject_id'],row['class_id']) for row in list(curriculum_pairs)+list(teaching) if row['subject_id'] in subject_set})
        pair_set = set(pairs)
        profiles = {}
        for row in curriculum_pairs:
            if row['method_profile_id'] is not None and (row['subject_id'],row['class_id']) in pair_set:
                entry=profiles.setdefault(row['method_profile_id'],dict(id=row['method_profile_id'],name=row['profile_name'],code=row['profile_code'],pairs=[]))
                entry['pairs'].append(dict(subject_id=row['subject_id'],class_id=row['class_id']))
        paired_subjects = {sid for sid,cid in pairs}
        result = dict(school_id=context['school_id'], year_start=year, plan_status=context['plan_status'], month_status=context['month_status'],
                    classes=[dict(row, name=str(row['grade_level']) + str(row['letter'] or '')) for row in classes],
                    subjects=[dict(row) for row in subjects if row['id'] in paired_subjects], teaching=[dict(row) for row in teaching],
                    subject_classes=[dict(subject_id=sid,class_id=cid) for sid,cid in pairs],method_profiles=list(profiles.values()))
        from app.modules.reports.rules.report_area_scheme import suggestions
        result['area_scheme'] = context.get('area_scheme') or {}
        result['area_scheme_revision'] = context.get('area_scheme_revision') or 0
        result['area_suggestions'] = suggestions(result,result['area_scheme'])
        result['area_defaults'] = suggestions(result)
        return result


    @staticmethod
    async def get_teacher_labels_by_ids(
            db: AsyncSession,
            *,
            teacher_ids: list[str],
    ) -> dict[str, str]:
        """
        возвращает ФИО учителя из SchoolStaffMember
        "target_kind": "teacher",
        "target_value": str(tid),
        "target_label": "Фамилия имя отчество"
        """
        if not teacher_ids:
            return {}

        teacher_ids_int = []
        for value in teacher_ids:
            try:
                teacher_ids_int.append(int(value))
            except (TypeError, ValueError):
                continue

        if not teacher_ids_int:
            return {}

        stmt = (
            select(SchoolStaffMember.id, SchoolStaffMember.full_name)
            .where(SchoolStaffMember.id.in_(teacher_ids_int))
        )

        rows = (await db.execute(stmt)).all()

        result: dict[str, str] = {}
        for teacher_id, full_name in rows:
            result[str(teacher_id)] = (full_name or str(teacher_id)).strip()

        return result

    @classmethod
    async def get_missing_selected_reports(cls, db: AsyncSession, *, month_item_id: int) -> list[str]:
        """A completed document resolves its own selected position, not its type."""
        selected = TaskExecutionSelectedReport.__table__
        execution = TaskExecutionData.__table__
        types = ReportTypeModel.__table__
        documents = TaskExecutionDocument.__table__
        assignments = TaskSelectedReportAssignment.__table__
        completed = exists(select(documents.c.id).where(
            documents.c.selected_report_id == selected.c.id,
            documents.c.month_item_id == month_item_id,
            documents.c.is_current.is_(True), documents.c.is_final.is_(False),
            documents.c.document_type == DocumentType.REPORT,
            documents.c.status.in_([TaskDocumentStatus.SUBMITTED, TaskDocumentStatus.ACCEPTED])))
        waived = exists(select(assignments.c.id).where(
            assignments.c.selected_report_id == selected.c.id,
            assignments.c.status == 'waived'))
        statement = (select(types.c.name_kz, types.c.name_ru, types.c.code, selected.c.target_label, selected.c.target_value)
                     .select_from(selected.join(execution, execution.c.id == selected.c.execution_data_id)
                                  .join(types, types.c.id == selected.c.report_type_id))
                     .where(execution.c.month_item_id == month_item_id, types.c.code != 'analytical_reference',
                            ~completed, ~waived).order_by(selected.c.id))
        return [str(row.name_kz or row.name_ru or row.code) + ' · ' + str(row.target_label or row.target_value)
                for row in (await db.execute(statement)).all()]

    @classmethod
    async def mark_current_system_reports_submitted(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> None:
        """
        Отметить все текущие системные отчеты как отправленные.

        Используется при завершении задачи (вариант с системными отчетами).

        Что делает:
        - находит все НЕ итоговые документы (is_final=False)
        - только актуальные (is_current=True)
        - только системные отчеты (report_code != None)
        - переводит их в статус SUBMITTED
        - фиксирует кто и когда отправил

        Важно:
        - итоговый документ НЕ трогает
        - не создает новые записи
        - работает одним UPDATE (без N+1)
        """

        now = datetime.now(timezone.utc)

        stmt = (
            update(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.is_final.is_(False),
                TaskExecutionDocument.report_code.is_not(None),
            )
            .values(
                status=TaskDocumentStatus.SUBMITTED,
                submitted_by_user_id=user_id,
                submitted_at=now,
            )
        )

        await db.execute(stmt)


    @classmethod
    async def get_execution_page_bundle(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> ExecutionPageBundle:
        """
        Получить bundle данных execution-страницы.

        Зачем нужен:
        - сервису удобно получать execution_data и current_draft
          одной repo-точкой
        - сервис остается чище
        - внутреннюю реализацию можно позже оптимизировать
          без изменения сервисного слоя
        """
        current_draft = await cls.get_current_draft(
            db,
            month_item_id=month_item_id,
        )
        execution_data = await cls.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        return ExecutionPageBundle(
            current_draft=current_draft,
            execution_data=execution_data,
        )

    @classmethod
    async def get_current_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionDocument | None:
        """
        Получить текущий черновик по задаче.

        Логика:
        - только current
        - только не final
        - если черновиков несколько, берем самый свежий
          по version desc, id desc
        """
        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.is_final.is_(False),
            )
            .order_by(
                TaskExecutionDocument.version.desc(),
                TaskExecutionDocument.id.desc(),
            ).limit(1)
        )

        result = await db.execute(stmt)
        return result.scalars().first()
