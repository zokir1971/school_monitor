"""Bounded school/subject jobs and bulk writes into existing assessment tables."""
from sqlalchemy import select,update,func,case,and_,or_,exists,bindparam
from app.modules.assessment.repositories.diagnostic_result_repo import A,G,S,R,T,P,D,C,Q,O,insert
from app.modules.assessment.models import AssessmentQualitySummary
from app.modules.education.models import SchoolClass,SchoolStudent,SchoolClassSubjectTeacher
from app.modules.org.models import School,District
from app.modules.staff.models_staff_school import SchoolStaffMember
U=AssessmentQualitySummary.__table__;K=SchoolClass.__table__;N=SchoolStudent.__table__
H=School.__table__;E=District.__table__;L=SchoolClassSubjectTeacher.__table__;F=SchoolStaffMember.__table__


async def subjects(db,session_id,lock=False):
    q=select(D).where(D.c.session_id==session_id).order_by(D.c.id)
    if lock:q=q.with_for_update()
    return list((await db.execute(q)).mappings())


async def set_context(db,subject_id,context):
    await db.execute(update(D).where(D.c.id==subject_id).values(assessment_context=context))


async def claim(db):
    return (await db.execute(select(D).where(D.c.assessment_context['analytics']['state'].as_string()=='queued')
        .order_by(D.c.id).limit(1).with_for_update(skip_locked=True))).mappings().one_or_none()


async def session(db,session_id):
    return (await db.execute(select(C).where(C.c.id==session_id))).mappings().one()


async def next_school(db,session_id,cursor):
    return (await db.execute(select(K.c.school_id).select_from(P.join(K,K.c.id==P.c.school_class_id))
        .where(P.c.session_id==session_id,K.c.school_id>cursor).order_by(K.c.school_id).limit(1))).scalar_one_or_none()


async def school_count(db,session_id):
    return (await db.execute(select(func.count(func.distinct(K.c.school_id))).select_from(P.join(K,K.c.id==P.c.school_class_id)).where(P.c.session_id==session_id))).scalar_one()


async def lock_school(db,school_id):
    return (await db.execute(select(H.c.id,H.c.district_id,E.c.region_id).join(E,E.c.id==H.c.district_id)
        .where(H.c.id==school_id).with_for_update(of=H))).mappings().one()


async def conflicts(db,session_id,subject_id,checkpoint,school_id=None):
    # Both manuals and already finalized diagnostics reserve official checkpoints.
    classes=select(P.c.school_class_id).where(P.c.session_id==session_id)
    if school_id:classes=classes.where(P.c.school_class_id.in_(select(K.c.id).where(K.c.school_id==school_id)))
    source=(await db.execute(select(D.c.subject_id,C.c.academic_year_start).join(C,C.c.id==D.c.session_id).where(D.c.id==subject_id,D.c.session_id==session_id))).one()
    q=select(func.count(func.distinct(G.c.school_class_id))).select_from(G.join(A,A.c.id==G.c.assessment_id)).where(
        G.c.school_class_id.in_(classes),G.c.academic_year_start_snapshot==source.academic_year_start,
        A.c.subject_id==source.subject_id,A.c.checkpoint==checkpoint,
        or_(A.c.diagnostic_subject_id.is_(None),A.c.status=='completed'),
        or_(A.c.diagnostic_subject_id.is_(None),A.c.diagnostic_subject_id!=subject_id))
    return (await db.execute(q)).scalar_one()


async def conflicts_many(db,session_id,checkpoints):
    if not checkpoints:return {}
    classes=select(P.c.school_class_id).where(P.c.session_id==session_id)
    choices=or_(*(and_(D.c.id==sid,A.c.checkpoint==point) for sid,point in checkpoints.items()))
    q=(select(D.c.id,func.count(func.distinct(G.c.school_class_id)))
        .select_from(D.join(C,C.c.id==D.c.session_id).join(A,A.c.subject_id==D.c.subject_id).join(G,G.c.assessment_id==A.c.id))
        .where(D.c.session_id==session_id,choices,G.c.school_class_id.in_(classes),G.c.academic_year_start_snapshot==C.c.academic_year_start,
            or_(A.c.diagnostic_subject_id.is_(None),A.c.status=='completed'),
            or_(A.c.diagnostic_subject_id.is_(None),A.c.diagnostic_subject_id!=D.c.id)).group_by(D.c.id))
    return dict((await db.execute(q)).all())


async def set_contexts(db,prepared):
    if prepared:
        q=update(D).where(D.c.id==bindparam('subject_key')).values(assessment_context=bindparam('new_context'))
        await db.execute(q,[dict(subject_key=sid,new_context=context) for sid,context in prepared])


async def roster(db,session_id,subject_id,school_id):
    return list((await db.execute(select(P,T.c.id.label('attempt_id'),T.c.status.label('attempt_status'),T.c.assessment_student_id)
        .select_from(P.join(K,K.c.id==P.c.school_class_id).join(N,and_(N.c.id==P.c.student_id,N.c.school_id==K.c.school_id))
            .outerjoin(T,and_(T.c.participant_id==P.c.id,T.c.diagnostic_subject_id==subject_id)))
        .where(P.c.session_id==session_id,K.c.school_id==school_id).order_by(P.c.id))).mappings())


async def teachers(db,school_id,subject_id,class_ids):
    return list((await db.execute(select(L.c.school_class_id,L.c.staff_member_id,L.c.teacher_name_snapshot)
        .join(F,and_(F.c.id==L.c.staff_member_id,F.c.school_id==school_id))
        .where(L.c.school_id==school_id,L.c.subject_id==subject_id,L.c.school_class_id.in_(class_ids),
            L.c.subgroup_id.is_(None),L.c.is_active.is_(True),L.c.is_primary.is_(True)))).mappings())


async def ensure_assessments(db,values,subject_id,school_id,checkpoint):
    if values:await db.execute(insert(db,A).values(values).on_conflict_do_nothing(index_elements=['diagnostic_subject_id','school_id','diagnostic_variant','diagnostic_language']))
    rows=list((await db.execute(select(A).where(A.c.diagnostic_subject_id==subject_id,A.c.school_id==school_id))).mappings())
    await db.execute(update(A).where(A.c.id.in_([r['id'] for r in rows])).values(checkpoint=checkpoint))
    return [dict(r,checkpoint=checkpoint) for r in rows]


async def ensure_structure(db,assessments,definitions):
    goals=[]
    for a in assessments:
        _,objectives=definitions[(a['diagnostic_variant'],a['diagnostic_language'])]
        goals.extend(dict(o,assessment_id=a['id']) for o in objectives)
    for offset in range(0,len(goals),500):
        await db.execute(insert(db,O).values(goals[offset:offset+500]).on_conflict_do_nothing(index_elements=['assessment_id','learning_objective_id']))
    rows=list((await db.execute(select(O.c.id,O.c.assessment_id,O.c.learning_objective_id).where(O.c.assessment_id.in_([a['id'] for a in assessments])))).mappings())
    by_goal={(o['assessment_id'],o['learning_objective_id']):o['id'] for o in rows}
    questions=[]
    for a in assessments:
        entries,_=definitions[(a['diagnostic_variant'],a['diagnostic_language'])]
        for q in entries:
            ids=q['diagnostic_snapshot']['objective_ids']
            questions.append(dict(q,assessment_id=a['id'],assessment_objective_id=by_goal.get((a['id'],ids[0])) if len(ids)==1 else None))
    for offset in range(0,len(questions),500):
        await db.execute(insert(db,Q).values(questions[offset:offset+500]).on_conflict_do_nothing(index_elements=['assessment_id','order_no']))


async def ensure_groups(db,values,assessment_ids):
    if values:
        for offset in range(0,len(values),1000):
            q=insert(db,G).values(values[offset:offset+1000])
            await db.execute(q.on_conflict_do_update(index_elements=['assessment_id','school_class_id'],set_={
                'teacher_staff_member_id':func.coalesce(G.c.teacher_staff_member_id,q.excluded.teacher_staff_member_id),
                'teacher_name_snapshot':func.coalesce(G.c.teacher_name_snapshot,q.excluded.teacher_name_snapshot)}))
    return list((await db.execute(select(G).where(G.c.assessment_id.in_(assessment_ids)))).mappings())


async def ensure_students(db,values):
    # Bounded chunks, not a query per pupil; do not overwrite existing checked statuses.
    for offset in range(0,len(values),1000):
        await db.execute(insert(db,S).values(values[offset:offset+1000]).on_conflict_do_nothing(index_elements=['assessment_group_id','student_id']))


async def participants(db,assessment_ids):
    return list((await db.execute(select(S,G.c.assessment_id,R.c.score,R.c.max_score,R.c.percent,R.c.grade)
        .join(G,G.c.id==S.c.assessment_group_id).outerjoin(R,R.c.assessment_student_id==S.c.id)
        .where(G.c.assessment_id.in_(assessment_ids)).order_by(G.c.id,S.c.id))).mappings())


async def finish(db,summaries,assessment_ids,at):
    if summaries:
        values=[{c.name:getattr(row,c.name) for c in U.columns if c.name not in ('id','created_at','updated_at')} for row in summaries]
        for offset in range(0,len(values),500):
            q=insert(db,U).values(values[offset:offset+500])
            await db.execute(q.on_conflict_do_update(index_elements=['assessment_group_id'],set_={k:q.excluded[k] for k in values[0] if k!='assessment_group_id'}))
    await db.execute(update(A).where(A.c.id.in_(assessment_ids)).values(status='completed',completed_at=at))


async def overview(db,session_id):
    return list((await db.execute(select(D.c.id,D.c.name_ru,D.c.name_kk,D.c.assessment_context).where(D.c.session_id==session_id).order_by(D.c.order_no))).mappings())
