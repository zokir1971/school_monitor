"""Work-plan SQL; all mutations lock the owning plan before bank rows."""
from sqlalchemy import select
from app.modules.assessment.models_work_plans import AssessmentWorkPlan as Plan, AssessmentWorkPlanItem as Item
from app.modules.assessment.models import QuestionBankItem
from app.modules.education.models import Subject
from app.modules.org.models import Region, District, School

async def scope_options(db, user):
    role = str(getattr(user.role,'value',user.role))
    kind = {'teacher':'school','school_admin':'school','school_staff':'school',
        'district_admin':'district','district_staff':'district','region_admin':'region','region_staff':'region'}.get(role)
    result=[]
    for label,model in [('school',School),('district',District),('region',Region)]:
        if role!='superuser' and label!=kind: continue
        query=select(model.id,model.name)
        if role!='superuser':
            key=getattr(user,label+'_id',None)
            if not key: continue
            query=query.where(model.id==key)
        rows=(await db.execute(query.order_by(model.name))).all()
        result.extend(dict(value=f'{label}:{r.id}',kind=label,id=r.id,name=r.name) for r in rows)
    return result

async def subjects(db):
    return (await db.execute(select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.sort_order,Subject.id))).scalars().all()

async def list_owned(db,user_id,after=0):
    q=select(Plan).where(Plan.created_by_user_id==user_id)
    if after: q=q.where(Plan.id<after)
    return (await db.execute(q.order_by(Plan.id.desc()).limit(21))).scalars().all()

async def owned(db,user_id,plan_id,lock=False):
    q=select(Plan).where(Plan.id==plan_id,Plan.created_by_user_id==user_id)
    if lock: q=q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()

async def items(db,plan_id):
    return (await db.execute(select(Item).where(Item.work_plan_id==plan_id)
        .order_by(Item.variant_no,Item.order_no,Item.id))).scalars().all()

async def lock_bank(db,ids):
    await db.execute(select(QuestionBankItem.__table__.c.id).where(QuestionBankItem.__table__.c.id.in_(ids))
        .order_by(QuestionBankItem.__table__.c.id).with_for_update())


def alternative_query(plan, reference_ids, used_ids):
    """Coarse candidate pairs, shared by batched counts and keyset lookup.

    Exact scoring profiles, stale translations and duplicates are checked by the
    service. Counts are deliberately labelled preliminary in the UI.
    """
    from sqlalchemy import exists, and_, or_
    from app.modules.assessment.models import QuestionBankItemObjective, QuestionBankLanguageVariant
    from app.modules.assessment.enums import AssessmentLanguage, QuestionBankItemStatus
    from app.modules.assessment.helpers.work_plan_rules import required_languages
    a=QuestionBankItem.__table__.alias('wp_reference')
    c=QuestionBankItem.__table__.alias('wp_candidate')
    link=QuestionBankItemObjective.__table__
    def contained(left,right):
        l=link.alias();r=link.alias()
        matching=exists(select(1).select_from(r).where(
            r.c.question_bank_item_id==right.c.id,
            r.c.learning_objective_id==l.c.learning_objective_id).correlate(l,right))
        return ~exists(select(1).select_from(l).where(
            l.c.question_bank_item_id==left.c.id,~matching).correlate(left,right))
    clauses=[a.c.id.in_(reference_ids),c.c.id!=a.c.id,
        c.c.status==QuestionBankItemStatus.READY,c.c.subject_id==plan.curriculum_subject_id,
        c.c.grade_level==plan.curriculum_grade,c.c.question_type==a.c.question_type,
        c.c.difficulty==a.c.difficulty,c.c.max_score==a.c.max_score,
        contained(a,c),contained(c,a)]
    if used_ids: clauses.append(c.c.id.not_in(used_ids))
    if plan.quarter is not None:
        from app.modules.assessment.repositories.learning_objective_quarter_queries import item_quarters_match
        clauses.append(item_quarters_match(c,list(range(1,plan.quarter+1))))
    for language in required_languages(plan.language_policy):
        variant=QuestionBankLanguageVariant.__table__.alias()
        translated=exists(select(1).select_from(variant).where(
            variant.c.item_id==c.c.id,variant.c.language==language).correlate(c))
        clauses.append(or_(c.c.language==AssessmentLanguage(language),translated))
    return select(a.c.id.label('reference_id'),c.c.id.label('candidate_id')).select_from(
        a.join(c,and_(*clauses)))

async def alternative_counts(db,plan,reference_ids,used_ids):
    if not reference_ids:return {}
    from sqlalchemy import func
    pairs=alternative_query(plan,reference_ids,used_ids).subquery()
    rows=(await db.execute(select(pairs.c.reference_id,func.count().label('total'))
        .group_by(pairs.c.reference_id))).all()
    return {r.reference_id:r.total for r in rows}

async def alternative_ids(db,plan,reference_id,used_ids,after=0):
    pairs=alternative_query(plan,[reference_id],used_ids).subquery()
    return list((await db.execute(select(pairs.c.candidate_id).where(pairs.c.candidate_id>after)
        .order_by(pairs.c.candidate_id).limit(101))).scalars().all())

async def variant_pair_ids(db,plan,reference_ids,used_ids=None):
    """One bounded query for all rows: at most 41 candidate IDs per reference."""
    if not reference_ids:return []
    from sqlalchemy import func
    pairs=alternative_query(plan,reference_ids,used_ids or []).subquery()
    ranked=select(pairs.c.reference_id,pairs.c.candidate_id,func.row_number().over(
        partition_by=pairs.c.reference_id,order_by=pairs.c.candidate_id).label('rank')).subquery()
    return (await db.execute(select(ranked.c.reference_id,ranked.c.candidate_id)
        .where(ranked.c.rank<=41).order_by(ranked.c.reference_id,ranked.c.candidate_id))).all()
