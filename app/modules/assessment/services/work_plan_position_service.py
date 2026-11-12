"""Atomic removal of a reviewed compatible position from every variant."""
from datetime import datetime,timezone
from sqlalchemy import select,exists,or_,delete
from app.modules.assessment.models_work_plans import AssessmentWorkPlanItem as Item
from app.modules.assessment.models_work_assignments import AssessmentWorkAssignment as Assignment
from app.modules.assessment.models_diagnostic_sessions import DiagnosticSubject
from app.modules.assessment.services import work_plan_service as work
from app.modules.assessment.repositories import work_plan_repo as repo
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError
from app.modules.assessment.helpers.work_plan_positions import position_rows,composition_revision
from app.modules.assessment.helpers.work_plan_presentation import ordered_items


class CompositionChanged(WorkPlanError):pass


async def is_used(db,plan_id):
    return bool(await db.scalar(select(or_(exists(select(Assignment.id).where(Assignment.work_plan_id==plan_id)),
        exists(select(DiagnosticSubject.id).where(DiagnosticSubject.source_plan_id==plan_id))))))


async def ensure_unused(db,plan):
    if await is_used(db,plan.id):
        raise WorkPlanError('Комплект уже использован или назначен участникам. Изменять его состав нельзя. / Жинақ қолданылған немесе қатысушыларға тағайындалған. Құрамын өзгертуге болмайды.')


async def reviewed_position(db,user,plan_id,key,lock=False):
    plan=await work.own(db,user,plan_id,lock);work.editable(plan);await ensure_unused(db,plan)
    items=await repo.items(db,plan.id)
    position=next((p for p in position_rows(plan,items) if p['key']==key),None)
    if position is None:raise WorkPlanError('Позиция больше не найдена. Обновите состав комплекта. / Позиция табылмады. Жинақ құрамын жаңартыңыз.')
    return plan,items,position,composition_revision(plan,items)


async def remove_position(db,user,plan_id,key,revision):
    plan=await work.own(db,user,plan_id,True);work.editable(plan);await ensure_unused(db,plan)
    items=await repo.items(db,plan.id);current=composition_revision(plan,items)
    if revision!=current:raise CompositionChanged('Состав комплекта изменился. Проверьте таблицу и подтвердите удаление заново. / Жинақ құрамы өзгерді. Кестені тексеріп, жоюды қайта растаңыз.')
    position=next((p for p in position_rows(plan,items) if p['key']==key),None)
    if position is None:raise WorkPlanError('Позиция не найдена. / Позиция табылмады.')
    ids={r.id for r in position['slots'].values()}
    await db.execute(delete(Item).where(Item.work_plan_id==plan.id,Item.id.in_(ids)))
    remaining=[r for r in items if r.id not in ids]
    await renumber(db,plan,remaining)
    return len(ids)


async def renumber(db,plan,remaining):
    # Two phases avoid temporary collisions with uq_work_plan_item_order.
    shift=max((r.order_no for r in remaining),default=0)+len(remaining)+1
    for r in remaining:r.order_no+=shift
    await db.flush()
    for v in range(1,plan.variant_count+1):
        for no,r in enumerate(ordered_items([i for i in remaining if i.variant_no==v]),1):r.order_no=no
    plan.updated_at=datetime.now(timezone.utc)
    await db.flush()
