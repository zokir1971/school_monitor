"""Territorial WSHK statistics: scalar SQL aggregates, no ORM object graphs."""
from __future__ import annotations
from calendar import monthrange
from datetime import date
from sqlalchemy import select,func,case,and_,or_,literal,union,cast,Float
from app.modules.org.models import School,District,Region
from app.modules.planning.models import PlanDirection
from app.modules.planning.models_school import SchoolPlan,SchoolPlanRow11
from app.modules.planning.models_month_plan import SchoolMonthPlan,SchoolMonthPlanItem,SchoolMonthPlanItemAssignee,SchoolMonthPlanItemReviewPlace
from app.modules.staff.models_staff_school import SchoolStaffRole,SchoolStaffMember
from app.modules.users.models import User
from app.modules.reports.models_documents import TaskExecutionDocument,TaskExecutionData,TaskExecutionSelectedReport
from app.modules.reviews.models_task_review import SchoolMonthPlanItemReviewResult,SchoolTaskReview

METRICS=('schools','annual','monthly','direction_schools','tasks','assigned','completed','in_progress','todo',
         'not_executed','overdue','reports','submitted','drafts','waiting','reviewed','review_waiting')
MONTHS=(8,9,10,11,12,1,2,3,4,5,6)

def count_if(condition):return func.sum(case((condition,1),else_=0))
def zero(column):return func.coalesce(column,0)


class TerritorialStatisticsRepo:
    @staticmethod
    def school_scope(scope, district_id=None, school_id=None, search=''):
        s,d,r=School.__table__.c,District.__table__.c,Region.__table__.c
        stmt=select(s.id.label('school_id'),s.name.label('school_name'),d.id.label('district_id'),d.name.label('district_name'),r.id.label('region_id'),r.name.label('region_name')).select_from(School.__table__.join(District.__table__,s.district_id==d.id).join(Region.__table__,d.region_id==r.id))
        if scope['kind']=='district':stmt=stmt.where(d.id==scope['district_id'])
        elif scope['kind']=='region':stmt=stmt.where(d.region_id==scope['region_id'])
        elif scope['kind']=='super':
            if scope.get('region_id') is not None:stmt=stmt.where(d.region_id==scope['region_id'])
        else:raise ValueError('Unknown territorial scope')
        if district_id is not None:stmt=stmt.where(d.id==district_id)
        if school_id is not None:stmt=stmt.where(s.id==school_id)
        if search:
            term=search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            stmt=stmt.where(s.name.ilike('%'+term+'%',escape='\\'))
        return stmt.cte('scope_schools')

    @staticmethod
    def plans(schools,year):
        p=SchoolPlan.__table__.c
        return select(p.id.label('plan_id'),p.school_id).join(schools,p.school_id==schools.c.school_id).where(p.academic_year==f'{year}-{year+1}').cte('scope_plans')

    @classmethod
    async def directions(cls,db,schools,year):
        plans=cls.plans(schools,year);r=SchoolPlanRow11.__table__.c;d=PlanDirection.__table__.c
        stmt=select(d.id,func.coalesce(func.nullif(d.full_title,''),d.short_title).label('name')).select_from(PlanDirection.__table__.join(SchoolPlanRow11.__table__,r.direction_id==d.id).join(plans,r.school_plan_id==plans.c.plan_id)).group_by(d.id,d.full_title,d.short_title,d.sort_order).order_by(d.sort_order,d.id)
        return [dict(row) for row in (await db.execute(stmt)).mappings()]

    @classmethod
    def query(cls,schools,year,month,direction_id,view,today,attention=False):
        plans=cls.plans(schools,year)
        r=SchoolPlanRow11.__table__.c;m=SchoolMonthPlan.__table__.c;i=SchoolMonthPlanItem.__table__.c
        direction=func.coalesce(r.direction_id,0)
        annual=select(plans.c.school_id, r.direction_id.label('direction_id')).select_from(plans.join(SchoolPlanRow11.__table__,r.school_plan_id==plans.c.plan_id)).distinct().cte('annual_directions')
        calendar=or_(*(and_(m.month==n,m.year==(year if n>=8 else year+1)) for n in MONTHS))
        months=select(m.id.label('month_id'),plans.c.school_id,m.school_plan_id,m.month).join(plans,m.school_plan_id==plans.c.plan_id).where(calendar,m.status.in_(('active','archived')))
        if month is not None:months=months.where(m.month==month)
        months=months.cte('released_months')
        due=func.coalesce(i.planned_end,case(*[(months.c.month==n,date(year if n>=8 else year+1,n,monthrange(year if n>=8 else year+1,n)[1]))for n in MONTHS],else_=None))
        task_stmt=select(i.id.label('task_id'),months.c.school_id,months.c.school_plan_id.label('plan_id'),direction.label('direction_id'),i.status,i.responsible_user_id,due.label('due')).select_from(months.join(SchoolMonthPlanItem.__table__,i.month_plan_id==months.c.month_id).outerjoin(SchoolPlanRow11.__table__,and_(r.id==i.source_row11_id,r.school_plan_id==months.c.school_plan_id))).where(i.is_included.is_(True))
        if direction_id is not None:
            task_stmt=task_stmt.where(r.direction_id==direction_id if direction_id else r.direction_id.is_(None))
        tasks=task_stmt.cte('scope_tasks')
        a,sr,sm=SchoolMonthPlanItemAssignee.__table__.c,SchoolStaffRole.__table__.c,SchoolStaffMember.__table__.c
        assignments=select(a.month_item_id.label('task_id')).select_from(SchoolMonthPlanItemAssignee.__table__.join(tasks,a.month_item_id==tasks.c.task_id).join(SchoolStaffRole.__table__,and_(sr.id==a.staff_role_id,sr.school_id==tasks.c.school_id)).join(SchoolStaffMember.__table__,and_(sm.id==sr.staff_member_id,sm.school_id==tasks.c.school_id))).distinct().cte('assigned_tasks')
        rv=SchoolMonthPlanItemReviewResult.__table__.c;protocol=SchoolTaskReview.__table__.c;rp=SchoolMonthPlanItemReviewPlace.__table__.c
        reviews=select(rv.month_item_id.label('task_id')).join(tasks,rv.month_item_id==tasks.c.task_id).join(SchoolTaskReview.__table__,and_(protocol.id==rv.task_review_id,protocol.school_plan_id==tasks.c.plan_id)).where(rv.reviewed_at.is_not(None)).distinct().cte('reviewed_tasks')
        expected=select(rp.month_item_id.label('task_id')).join(tasks,rp.month_item_id==tasks.c.task_id).distinct().cte('review_expected')
        ed,sel,doc=TaskExecutionData.__table__.c,TaskExecutionSelectedReport.__table__.c,TaskExecutionDocument.__table__.c
        slots=select(sel.id.label('slot_id'),tasks.c.task_id).select_from(tasks.join(TaskExecutionData.__table__,ed.month_item_id==tasks.c.task_id).join(TaskExecutionSelectedReport.__table__,sel.execution_data_id==ed.id)).cte('report_slots')
        # Aggregate current versions before joining: coexecutors/doc versions cannot multiply tasks or slots.
        slot_states=select(slots.c.slot_id,slots.c.task_id,func.max(case((doc.id.is_not(None),1),else_=0)).label('has_doc'),func.max(case((doc.status.in_(('submitted','approved','accepted')),1),else_=0)).label('submitted')).select_from(slots.outerjoin(TaskExecutionDocument.__table__,and_(doc.selected_report_id==slots.c.slot_id,doc.is_current.is_(True),doc.month_item_id==slots.c.task_id))).group_by(slots.c.slot_id,slots.c.task_id).cte('slot_states')
        report_counts=select(slot_states.c.task_id,func.count().label('reports'),func.sum(slot_states.c.submitted).label('submitted'),func.sum(case((and_(slot_states.c.has_doc==1,slot_states.c.submitted==0),1),else_=0)).label('drafts'),func.sum(case((slot_states.c.has_doc==0,1),else_=0)).label('waiting')).group_by(slot_states.c.task_id).cte('report_counts')
        u=User.__table__.c
        done=tasks.c.status.in_(('done','reviewed'))
        reviewed=or_(reviews.c.task_id.is_not(None),tasks.c.status=='reviewed')
        assigned=or_(assignments.c.task_id.is_not(None),u.id.is_not(None))
        fact=select(tasks.c.school_id,tasks.c.direction_id,func.count().label('tasks'),count_if(assigned).label('assigned'),count_if(done).label('completed'),count_if(tasks.c.status=='in_progress').label('in_progress'),count_if(tasks.c.status=='todo').label('todo'),count_if(tasks.c.status=='not_executed').label('not_executed'),count_if(and_(~done,tasks.c.due<today)).label('overdue'),*[func.sum(zero(report_counts.c[key])).label(key) for key in ('reports','submitted','drafts','waiting')],count_if(reviewed).label('reviewed'),count_if(and_(done,~reviewed,expected.c.task_id.is_not(None))).label('review_waiting')).select_from(tasks.outerjoin(assignments,assignments.c.task_id==tasks.c.task_id).outerjoin(User.__table__,and_(u.id==tasks.c.responsible_user_id,u.school_id==tasks.c.school_id)).outerjoin(reviews,reviews.c.task_id==tasks.c.task_id).outerjoin(expected,expected.c.task_id==tasks.c.task_id).outerjoin(report_counts,report_counts.c.task_id==tasks.c.task_id)).group_by(tasks.c.school_id,tasks.c.direction_id).cte('task_facts')
        annual_filter=select(annual.c.school_id).distinct()
        if direction_id is not None:annual_filter=annual_filter.where(annual.c.direction_id==direction_id)
        else:annual_filter=select(plans.c.school_id).distinct()
        annual_filter=annual_filter.cte('annual_coverage')
        month_filter=select(months.c.school_id).distinct() if direction_id is None else select(tasks.c.school_id).distinct()
        month_filter=month_filter.cte('monthly_coverage')
        has_tasks=select(tasks.c.school_id).distinct().cte('direction_coverage')
        byschool=select(fact.c.school_id,*[func.sum(fact.c[key]).label(key)for key in METRICS[4:]]).group_by(fact.c.school_id).cte('school_task_facts')
        active_admins=select(u.school_id).join(schools,u.school_id==schools.c.school_id).where(u.role=='school_admin',u.is_active.is_(True)).distinct().cte('active_school_admins')
        school_facts=select(schools,case((active_admins.c.school_id.is_not(None),1),else_=0).label('has_admin'),case((annual_filter.c.school_id.is_not(None),1),else_=0).label('annual'),case((month_filter.c.school_id.is_not(None),1),else_=0).label('monthly'),case((has_tasks.c.school_id.is_not(None),1),else_=0).label('direction_schools'),*[zero(byschool.c[key]).label(key)for key in METRICS[4:]]).select_from(schools.outerjoin(annual_filter,annual_filter.c.school_id==schools.c.school_id).outerjoin(month_filter,month_filter.c.school_id==schools.c.school_id).outerjoin(has_tasks,has_tasks.c.school_id==schools.c.school_id).outerjoin(byschool,byschool.c.school_id==schools.c.school_id).outerjoin(active_admins,active_admins.c.school_id==schools.c.school_id)).cte('school_facts')
        if attention:
            school_facts=select(school_facts).where(or_(school_facts.c.has_admin==0,school_facts.c.annual==0,school_facts.c.monthly==0,school_facts.c.assigned<school_facts.c.tasks,school_facts.c.overdue>0)).cte('attention_school_facts')
        if view=='directions':
            base=union(select(annual.c.school_id,annual.c.direction_id),select(tasks.c.school_id,tasks.c.direction_id)).cte('direction_membership')
            if direction_id is not None:base=select(base).where(base.c.direction_id==direction_id).cte('chosen_membership')
            if attention:base=select(base).join(school_facts,school_facts.c.school_id==base.c.school_id).cte('attention_direction_membership')
            d=PlanDirection.__table__.c
            grouped=select(base.c.direction_id.label('id'),func.coalesce(d.sort_order,2147483647).label('direction_order'),func.coalesce(func.nullif(d.full_title,''),d.short_title).label('name'),func.count().label('schools'),literal(0).label('annual'),literal(0).label('monthly'),count_if(fact.c.tasks>0).label('direction_schools'),*[func.sum(zero(fact.c[key])).label(key)for key in METRICS[4:]]).select_from(base.outerjoin(fact,and_(fact.c.school_id==base.c.school_id,fact.c.direction_id==base.c.direction_id)).outerjoin(PlanDirection.__table__,d.id==base.c.direction_id)).group_by(base.c.direction_id,d.full_title,d.short_title,d.sort_order).cte('groups')
        elif view=='regions':
            r=Region.__table__.c
            grouped=select(r.id,r.name,func.count(school_facts.c.school_id).label('schools'),*[zero(func.sum(school_facts.c[key])).label(key)for key in METRICS[1:]]).select_from(Region.__table__.outerjoin(school_facts,school_facts.c.region_id==r.id)).group_by(r.id,r.name).cte('groups')
        else:
            key,name=(school_facts.c.district_id,school_facts.c.district_name) if view=='districts' else (school_facts.c.school_id,school_facts.c.school_name)
            grouped=select(key.label('id'),name.label('name'),func.max(school_facts.c.region_name).label('region_name'),func.max(school_facts.c.district_name).label('district_name'),func.max(school_facts.c.has_admin).label('has_admin'),func.count().label('schools'),*[func.sum(school_facts.c[key]).label(key)for key in METRICS[1:]]).group_by(key,name).cte('groups')
        summary=select(func.count().label('schools'),*[zero(func.sum(school_facts.c[key])).label(key)for key in METRICS[1:]],select(func.count()).select_from(grouped).scalar_subquery().label('group_count')).select_from(school_facts)
        return summary,grouped

    @classmethod
    async def read(cls,db,schools,year,month,direction_id,view,today,page,sort,order=None,attention=False):
        summary,groups=cls.query(schools,year,month,direction_id,view,today,attention)
        totals=dict((await db.execute(summary)).mappings().one())
        pages=max(1,(totals['group_count']+49)//50);page=min(page,pages)
        rows=[dict(row)for row in (await db.execute(ordered_groups(groups,view,sort,order).limit(50).offset((page-1)*50))).mappings()]
        return totals,rows,page,pages


def ordered_groups(groups,view,sort,order=None):
    ratio=lambda numerator,denominator:cast(numerator,Float)/func.nullif(denominator,0)
    columns={'name':groups.c.direction_order if view=='directions' else groups.c.name,
             'completed':groups.c.completed,'overdue':groups.c.overdue,
             'rate':ratio(groups.c.completed,groups.c.tasks),
             'overdue_rate':ratio(groups.c.overdue,groups.c.tasks),
             'assigned_rate':ratio(groups.c.assigned,groups.c.tasks),
             'submitted_rate':ratio(groups.c.submitted,groups.c.reports)}
    ordering=order or ('asc' if sort=='name' else 'desc')
    primary=(columns[sort].asc() if ordering=='asc' else columns[sort].desc()).nullslast()
    ties=([groups.c.id] if sort=='name' else [groups.c.direction_order.asc(),groups.c.id]) if view=='directions' else [groups.c.name.asc(),groups.c.id]
    return select(groups).order_by(primary,*ties)
