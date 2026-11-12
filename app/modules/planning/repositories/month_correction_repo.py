"""Batch reads/writes for monthly planning; no per-item database calls."""
from sqlalchemy import select, update, delete, insert, bindparam, case, cast, exists, or_
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemAssignee, SchoolMonthPlanItemExecution
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11Responsible
from app.modules.planning.models_month_plan_notification import SchoolMonthPlanNotification
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember
from app.modules.users.models import User
from app.modules.planning.enums import MonthPlanNotificationStatus
from app.modules.reports.models_documents import TaskExecutionDocument, TaskExecutionData
from app.modules.reviews.models_task_review import SchoolMonthPlanItemReviewResult

class MonthCorrectionRepo:
    @staticmethod
    async def snapshot(db, *, school_id, month_plan_id, lock=False):
        p, m, i = SchoolPlan.__table__, SchoolMonthPlan.__table__, SchoolMonthPlanItem.__table__
        notifications = SchoolMonthPlanNotification.__table__
        has_notifications = exists(select(notifications.c.id).where(notifications.c.month_plan_id == m.c.id)).label('has_notifications')
        stmt = select(m, p.c.status.label('annual_status'), has_notifications).join(p, p.c.id == m.c.school_plan_id).where(m.c.id == month_plan_id, p.c.school_id == school_id)
        if lock:
            stmt = stmt.with_for_update(of=m)
        plan = (await db.execute(stmt)).mappings().first()
        if plan is None:
            return None
        doc = TaskExecutionDocument.__table__
        execution = SchoolMonthPlanItemExecution.__table__
        data = TaskExecutionData.__table__
        review = SchoolMonthPlanItemReviewResult.__table__
        protected = or_(
            i.c.status != 'todo', i.c.completed_at.is_not(None), i.c.executed_at.is_not(None),
            exists(select(doc.c.id).where(doc.c.month_item_id == i.c.id)),
            exists(select(execution.c.id).where(execution.c.month_item_id == i.c.id)),
            exists(select(data.c.id).where(data.c.month_item_id == i.c.id)),
            exists(select(review.c.id).where(review.c.month_item_id == i.c.id)),
        ).label('exclusion_protected')
        stmt = select(i, protected).where(i.c.month_plan_id == month_plan_id).order_by(i.c.id)
        if lock:
            stmt = stmt.with_for_update()
        items = list((await db.execute(stmt)).mappings())
        a, r, s = SchoolMonthPlanItemAssignee.__table__, SchoolStaffRole.__table__, SchoolStaffMember.__table__
        assignments = list((await db.execute(select(a, r.c.staff_member_id).join(i, i.c.id == a.c.month_item_id).join(r, r.c.id == a.c.staff_role_id).where(i.c.month_plan_id == month_plan_id))).mappings())
        roles = list((await db.execute(select(r, s.c.full_name, User.__table__.c.id.label('user_id')).join(s, s.c.id == r.c.staff_member_id).outerjoin(User.__table__, User.__table__.c.staff_member_id == s.c.id).where(r.c.school_id == school_id, s.c.school_id == school_id, r.c.is_active.is_(True), s.c.is_active.is_(True)).order_by(s.c.full_name, r.c.id))).mappings())
        t = SchoolPlanRow11Responsible.__table__
        planned = list((await db.execute(select(i.c.id.label('item_id'), t.c.role).join(t, t.c.row11_id == i.c.source_row11_id).where(i.c.month_plan_id == month_plan_id))).mappings())
        return dict(plan=plan, items=items, assignments=assignments, roles=roles, planned=planned)

    @staticmethod
    async def apply(db, *, updates, assignment_ids, assignments, notification_staff_ids, month_plan_id):
        i, a, n = SchoolMonthPlanItem.__table__, SchoolMonthPlanItemAssignee.__table__, SchoolMonthPlanNotification.__table__
        if updates:
            keys = ('is_included', 'week_of_month', 'planned_start', 'planned_end', 'notes', 'responsible_role', 'responsible_user_id')
            await db.execute(update(i).where(i.c.id == bindparam('_item_id'), i.c.month_plan_id == month_plan_id).values({key:bindparam('_'+key) for key in keys}), updates)
        if assignment_ids:
            await db.execute(delete(a).where(a.c.month_item_id.in_(assignment_ids)))
        if assignments:
            await db.execute(insert(a), assignments)
        if notification_staff_ids:
            await db.execute(update(n).where(n.c.month_plan_id == month_plan_id, n.c.staff_member_id.in_(notification_staff_ids)).values(confirmed_at=None, confirmed_by_user_id=None, status=cast(case((n.c.open_count > 0, MonthPlanNotificationStatus.SENT), else_=MonthPlanNotificationStatus.PENDING), n.c.status.type)))
