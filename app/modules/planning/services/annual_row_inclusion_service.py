"""Reversible annual exclusions; retain unused monthly records and task history."""
from fastapi import HTTPException
from sqlalchemy import delete, exists, or_, select, update

from app.core.ui_locale_context import ui_locale
from app.modules.planning.models_school import (
    SchoolPlan, SchoolPlanRow4, SchoolPlanRow11, SchoolPlanRow11RequiredDocument,
)
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemAssignee, SchoolMonthPlanItemExecution,
)
from app.modules.planning.repositories.review_place_sync_repo import ReviewPlaceSyncRepo
from app.modules.reports.models_documents import TaskExecutionData, TaskExecutionDocument
from app.modules.reviews.models_task_review import SchoolMonthPlanItemReviewResult
from app.modules.users.permissions import assert_can_edit_school
from app.utils.calendar_weeks import calc_year_from_academic
from app.modules.planning.services.annual_row_notices import AnnualRowConflict


def text(ru, kk):
    return kk if ui_locale.get() == 'kk' else ru


def code(value):
    return getattr(value, 'value', value)


async def _monthly_state(db, *, row_id):
    """Annual lock -> monthly locks -> item locks -> fresh protection read."""
    m, i = SchoolMonthPlan.__table__, SchoolMonthPlanItem.__table__
    # EXISTS avoids DISTINCT + FOR UPDATE, which PostgreSQL does not support.
    months = list((await db.execute(select(m).where(exists(
        select(i.c.id).where(i.c.month_plan_id == m.c.id, i.c.source_row11_id == row_id)
    )).order_by(m.c.id).with_for_update(of=m))).mappings())
    ids = list((await db.execute(select(i.c.id).where(i.c.source_row11_id == row_id)
                               .order_by(i.c.id).with_for_update(of=i))).scalars())
    if not ids:
        return months, []
    checks = [exists(select(t.c.id).where(t.c.month_item_id == i.c.id)).label(name) for name, t in (
        ('has_assignees', SchoolMonthPlanItemAssignee.__table__),
        ('has_execution', SchoolMonthPlanItemExecution.__table__),
        ('has_execution_data', TaskExecutionData.__table__),
        ('has_documents', TaskExecutionDocument.__table__),
        ('has_review', SchoolMonthPlanItemReviewResult.__table__),
    )]
    protected = or_(
        i.c.status != 'todo', i.c.executed_at.is_not(None), i.c.completed_at.is_not(None),
        i.c.completed_by_user_id.is_not(None), i.c.responsible_user_id.is_not(None), *checks,
    ).label('protected')
    tasks = list((await db.execute(select(i, protected, *checks).where(i.c.id.in_(ids)).order_by(i.c.id))).mappings())
    return months, tasks


def _block_reason(task, month):
    """Return a language-neutral reason; the GET reader chooses its language."""
    if code(task['status']) != 'todo':
        return 'status'
    if task['executed_at'] is not None or task['completed_at'] is not None or task['completed_by_user_id'] is not None:
        return 'completed'
    if task['responsible_user_id'] is not None or task['has_assignees']:
        return 'assigned'
    for field, reason in (('has_execution','execution'), ('has_execution_data','execution_data'),
                          ('has_documents','documents'), ('has_review','review')):
        if task[field]:
            return reason
    if code(month['status']) != 'draft' and task['is_included']:
        return 'published_included'
    return None


async def set_excluded(db, *, plan_id, direction_id, row_id, kind, excluded, user):
    """Caller owns commit. No rows, assignments, reports or documents are deleted."""
    models = {'rows4': SchoolPlanRow4, 'rows11': SchoolPlanRow11}
    model = models.get(kind)
    if model is None:
        raise HTTPException(400, text('Некорректный вид строки', 'Жол түрі дұрыс емес'))
    p = SchoolPlan.__table__
    plan = (await db.execute(select(p.c.school_id, p.c.academic_year).where(p.c.id == plan_id))).mappings().first()
    if plan is None:
        raise HTTPException(404, text('План не найден', 'Жоспар табылмады'))
    assert_can_edit_school(user, school_id=plan['school_id'])
    locked = await ReviewPlaceSyncRepo.lock_plan(db, school_plan_id=plan_id)
    if locked is None:
        raise HTTPException(404, text('План не найден', 'Жоспар табылмады'))
    if code(locked['status']) == 'archived':
        raise AnnualRowConflict('archived_plan')
    row = model.__table__
    state = await db.scalar(select(row.c.is_excluded).where(
        row.c.id == row_id, row.c.school_plan_id == plan_id, row.c.direction_id == direction_id,
    ))
    if state is None:
        raise HTTPException(404, text('Строка не найдена', 'Жол табылмады'))
    if bool(state) == excluded:
        return
    if kind == 'rows11':
        months, tasks = await _monthly_state(db, row_id=row_id)
        by_month = {m['id']: m for m in months}
        if excluded:
            for task in tasks:
                month = by_month.get(task['month_plan_id'])
                if month is None or month['school_plan_id'] != plan_id:
                    raise AnnualRowConflict('foreign_month')
                reason = _block_reason(task, month)
                if reason:
                    raise AnnualRowConflict('task_blocked', task_id=task['id'], year=month['year'],
                                            month=month['month'], reason=reason, status=code(task['status']))
            required, document = SchoolPlanRow11RequiredDocument.__table__, TaskExecutionDocument.__table__
            if await db.scalar(select(exists(select(document.c.id).join(
                required, required.c.id == document.c.required_document_id,
            ).where(required.c.row11_id == row_id)))):
                raise AnnualRowConflict('documents')
            # Released/archived unused records already have is_included=False.
            # Preserve them byte-for-byte; only drafts need inclusion snapshots.
            draft_ids = [t['id'] for t in tasks if code(by_month[t['month_plan_id']]['status']) == 'draft']
            if draft_ids:
                i = SchoolMonthPlanItem.__table__
                await db.execute(update(i).where(i.c.id.in_(draft_ids)).values(
                    annual_exclusion_was_included=i.c.is_included, is_included=False,
                ))
        else:
            # Restore the exact old checkbox only in still-editable, valid drafts.
            # Published/archived months and wrong-year legacy stubs stay unincluded.
            marked = [t for t in tasks if t['annual_exclusion_was_included'] is not None]
            restore_ids = []
            for task in marked:
                month = by_month.get(task['month_plan_id'])
                if (month and month['school_plan_id'] == plan_id and code(month['status']) == 'draft'
                        and not task['protected']
                        and month['year'] == calc_year_from_academic(plan['academic_year'], month['month'])):
                    restore_ids.append(task['id'])
            i = SchoolMonthPlanItem.__table__
            if restore_ids:
                await db.execute(update(i).where(i.c.id.in_(restore_ids)).values(is_included=i.c.annual_exclusion_was_included))
            if marked:
                await db.execute(update(i).where(i.c.id.in_([t['id'] for t in marked])).values(annual_exclusion_was_included=None))
    await db.execute(update(model).where(model.id == row_id).values(is_excluded=excluded))
    await db.flush()


async def delete_custom_row(db, *, plan_id, direction_id, row_id, kind, user):
    """Only unlinked custom rows may be deleted; linked rows use exclusion."""
    model = {'rows4': SchoolPlanRow4, 'rows11': SchoolPlanRow11}.get(kind)
    if model is None:
        raise HTTPException(400, text('Некорректный вид строки', 'Жол түрі дұрыс емес'))
    p = SchoolPlan.__table__
    school_id = await db.scalar(select(p.c.school_id).where(p.c.id == plan_id))
    if school_id is None:
        raise HTTPException(404, text('План не найден', 'Жоспар табылмады'))
    assert_can_edit_school(user, school_id=school_id)
    locked = await ReviewPlaceSyncRepo.lock_plan(db, school_plan_id=plan_id)
    if locked is None:
        raise HTTPException(404, text('План не найден', 'Жоспар табылмады'))
    if code(locked['status']) == 'archived':
        raise AnnualRowConflict('archived_plan')
    row = model.__table__
    custom = await db.scalar(select(row.c.is_custom).where(
        row.c.id == row_id, row.c.school_plan_id == plan_id, row.c.direction_id == direction_id,
    ).with_for_update(of=row))
    if custom is None:
        raise HTTPException(404, text('Строка не найдена', 'Жол табылмады'))
    if not custom:
        raise AnnualRowConflict('custom_only')
    if kind == 'rows11':
        i = SchoolMonthPlanItem.__table__
        linked_id = await db.scalar(select(i.c.id).where(i.c.source_row11_id == row_id).order_by(i.c.id).limit(1))
        if linked_id is not None:
            raise AnnualRowConflict('monthly_records', task_id=linked_id)
        required, document = SchoolPlanRow11RequiredDocument.__table__, TaskExecutionDocument.__table__
        await db.execute(select(required.c.id).where(required.c.row11_id == row_id)
                         .order_by(required.c.id).with_for_update(of=required))
        if await db.scalar(select(exists(select(document.c.id).join(
            required, required.c.id == document.c.required_document_id,
        ).where(required.c.row11_id == row_id)))):
            raise AnnualRowConflict('documents')
    await db.execute(delete(model).where(model.id == row_id, model.school_plan_id == plan_id,
                                        model.direction_id == direction_id, model.is_custom.is_(True)))
    await db.flush()
