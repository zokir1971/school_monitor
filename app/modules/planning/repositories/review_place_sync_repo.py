"""Transactional, batched propagation of annual review places to pending tasks."""
from collections import defaultdict
import re
from sqlalchemy import select, delete, insert, update
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11, SchoolPlanRow11ReviewPlace
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemReviewPlace
from app.modules.reviews.models_task_review import SchoolMonthPlanItemReviewResult
from app.modules.planning.enums import PlanStatus, PlanItemStatus, ReviewPlace

def code(value):
    return str(getattr(value, 'value', value) or '').strip()

class ReviewPlaceSyncRepo:
    @staticmethod
    async def lock_plan(db, *, school_plan_id):
        p = SchoolPlan.__table__
        # NO KEY UPDATE serializes edits/builds but permits protocol FK inserts.
        return (await db.execute(select(p.c.id,p.c.status).where(p.c.id==school_plan_id).with_for_update(of=p,key_share=True))).mappings().first()

    @staticmethod
    async def month_context(db, *, month_plan_id, school_id):
        p,m = SchoolPlan.__table__,SchoolMonthPlan.__table__
        return (await db.execute(select(m,p.c.status.label('annual_status')).join(p,p.c.id==m.c.school_plan_id).where(m.c.id==month_plan_id,p.c.school_id==school_id).with_for_update(of=p,key_share=True))).mappings().first()

    @staticmethod
    def legacy_places(raw):
        if not code(raw):
            return set()
        lookup = {v:v for v in ReviewPlace}
        lookup.update({v.value:v for v in ReviewPlace})
        lookup.update({v.label_kz:v for v in ReviewPlace})
        # Confirmed legacy abbreviations; structured selections remain authoritative.
        lookup.update({
            "ДЖК": ReviewPlace.DIRECTOR_COUNCIL,
            "ДЖО": ReviewPlace.DIRECTOR_COUNCIL,
            "ӘКО": ReviewPlace.METHOD_COUNCIL,
            "Әдістемелік отырысы": ReviewPlace.METHOD_COUNCIL,
            "Әдістеме-лік отырысы": ReviewPlace.METHOD_COUNCIL,
            "ПК": ReviewPlace.PED_COUNCIL,
        })
        values = {part.strip() for part in re.split(r'[,;\n]+',code(raw)) if part.strip()}
        if any(v not in lookup for v in values):
            return None
        return {lookup[v].value for v in values}

    @classmethod
    async def replace_annual(cls, db, *, row11_id, values):
        r,p,y = SchoolPlanRow11.__table__,SchoolPlan.__table__,SchoolPlanRow11ReviewPlace.__table__
        context = (await db.execute(select(r.c.school_plan_id,p.c.status).join(p,p.c.id==r.c.school_plan_id).where(r.c.id==row11_id).with_for_update(of=p,key_share=True))).mappings().first()
        if context is None:
            raise ValueError('Строка годового плана не найдена')
        if code(context['status']) == 'archived':
            raise ValueError('Нельзя изменять архивный годовой план')
        normalized = sorted({ReviewPlace(code(v)) for v in values if code(v)},key=lambda v:v.value)
        await db.execute(delete(y).where(y.c.row11_id==row11_id))
        if normalized:
            await db.execute(insert(y),[dict(row11_id=row11_id,review_place=v) for v in normalized])
        # The old free-text field must not revive a value explicitly removed by admin.
        await db.execute(update(r).where(r.c.id==row11_id).values(review_place=', '.join(v.label_kz for v in normalized) or None))
        return await cls.sync(db,school_plan_id=context['school_plan_id'],row11_id=row11_id,locked=True)

    @classmethod
    async def sync(cls, db, *, school_plan_id, month_plan_id=None, row11_id=None, locked=False):
        await db.flush()
        stats = dict(updated=0,added=0,removed=0,protected=0,unrecognized=0)
        if not locked:
            plan = await cls.lock_plan(db,school_plan_id=school_plan_id)
            if not plan or code(plan['status'])=='archived':
                return stats
        m,i,r = SchoolMonthPlan.__table__,SchoolMonthPlanItem.__table__,SchoolPlanRow11.__table__
        y,c,h = SchoolPlanRow11ReviewPlace.__table__,SchoolMonthPlanItemReviewPlace.__table__,SchoolMonthPlanItemReviewResult.__table__
        query = select(m.c.id).where(m.c.school_plan_id==school_plan_id,m.c.status!=PlanStatus.ARCHIVED).order_by(m.c.id).with_for_update(of=m,key_share=True)
        if month_plan_id is not None: query=query.where(m.c.id==month_plan_id)
        months = list((await db.execute(query)).scalars())
        if not months:return stats
        query = select(i.c.id,i.c.source_row11_id,i.c.status,r.c.review_place.label('legacy_place')).join(r,r.c.id==i.c.source_row11_id).where(i.c.month_plan_id.in_(months),r.c.school_plan_id==school_plan_id).order_by(i.c.id).with_for_update(of=i)
        if row11_id is not None:query=query.where(r.c.id==row11_id)
        tasks=list((await db.execute(query)).mappings())
        if not tasks:return stats
        ids=[t['id'] for t in tasks]
        # Fresh read after row locks: a review may have committed while we waited.
        protected=set((await db.execute(select(h.c.month_item_id).where(h.c.month_item_id.in_(ids)).distinct())).scalars())
        protected.update(t['id'] for t in tasks if code(t['status'])=='reviewed')
        stats['protected']=len(protected)
        tasks=[t for t in tasks if t['id'] not in protected]
        if not tasks:return stats
        ids=[t['id'] for t in tasks];source_ids={t['source_row11_id'] for t in tasks}
        planned=defaultdict(set)
        for row in (await db.execute(select(y.c.row11_id,y.c.review_place).where(y.c.row11_id.in_(source_ids)))).mappings():
            planned[row['row11_id']].add(code(row['review_place']))
        current=defaultdict(dict)
        for row in (await db.execute(select(c).where(c.c.month_item_id.in_(ids)))).mappings():
            current[row['month_item_id']][code(row['review_place'])]=row['id']
        removed=[];added=[]
        for task in tasks:
            desired=planned.get(task['source_row11_id'])
            if not desired:
                desired=cls.legacy_places(task['legacy_place'])
            if desired is None:
                stats['unrecognized']+=1;continue
            old=current[task['id']]
            if set(old)==desired:continue
            stats['updated']+=1
            removed.extend(id_ for place,id_ in old.items() if place not in desired)
            added.extend(dict(month_item_id=task['id'],review_place=ReviewPlace(place)) for place in sorted(desired-set(old)))
        if removed:await db.execute(delete(c).where(c.c.id.in_(removed)))
        if added:await db.execute(insert(c),added)
        stats.update(added=len(added),removed=len(removed))
        return stats
