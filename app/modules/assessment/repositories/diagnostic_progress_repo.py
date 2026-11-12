"""Server-side progress filters and bounded pages; never load answer payloads."""
from sqlalchemy import select,func,case,exists,and_,or_
from app.modules.assessment.models_diagnostic_sessions import DiagnosticParticipant as Person,DiagnosticSubject as Subject
from app.modules.assessment.models_diagnostic_attempts import DiagnosticAttempt as Attempt
from app.modules.assessment.models import AssessmentResult
from app.modules.education.models import SchoolClass
from app.modules.org.models import School,District
P=Person.__table__;D=Subject.__table__;T=Attempt.__table__;R=AssessmentResult.__table__;K=SchoolClass.__table__;H=School.__table__;E=District.__table__


async def filter_options(db,session_id,district_id=None,school_id=None):
    roster=P.join(K,K.c.id==P.c.school_class_id).join(H,H.c.id==K.c.school_id).join(E,E.c.id==H.c.district_id)
    districts=list((await db.execute(select(E.c.id,E.c.name).distinct().select_from(roster)
        .where(P.c.session_id==session_id).order_by(E.c.name,E.c.id))).mappings())
    school_query=select(K.c.school_id,func.min(P.c.school_name).label('name'),E.c.name.label('district_name')).select_from(roster).where(P.c.session_id==session_id)
    if district_id:school_query=school_query.where(E.c.id==district_id)
    schools=list((await db.execute(school_query.group_by(K.c.school_id,E.c.name).order_by(E.c.name,func.min(P.c.school_name),K.c.school_id))).mappings())
    classes=[]
    if school_id is not None:
        query=select(P.c.school_class_id.label('id'),func.min(P.c.class_label).label('name')).select_from(roster).where(P.c.session_id==session_id,K.c.school_id==school_id)
        if district_id:query=query.where(E.c.id==district_id)
        classes=list((await db.execute(query.group_by(P.c.school_class_id).order_by(func.min(P.c.class_label),P.c.school_class_id))).mappings())
    return districts,schools,classes


async def page_rows(db,session_id,category,page,*,filters=None,page_size=25):
    filters=filters or {}
    all_subjects=list((await db.execute(select(D.c.id,D.c.source_plan_id,D.c.name_ru,D.c.name_kk)
        .where(D.c.session_id==session_id).order_by(D.c.order_no,D.c.id))).all())
    stats=(select(T.c.participant_id.label('person_id'),func.count(T.c.id).label('started'),
        func.sum(case((T.c.status.in_(['submitted','expired']),1),else_=0)).label('finished'))
        .where(T.c.participant_id.in_(select(P.c.id).where(P.c.session_id==session_id)))
        .group_by(T.c.participant_id).subquery())
    started=func.coalesce(stats.c.started,0);finished=func.coalesce(stats.c.finished,0)
    state=case((started==0,'not_started'),(finished==len(all_subjects),'completed'),else_='partial')
    base=(select(P.c.id,P.c.full_name,P.c.school_name,P.c.class_label,P.c.assignments,
                 started.label('started'),finished.label('finished'),state.label('state'))
          .select_from(P.outerjoin(stats,stats.c.person_id==P.c.id)).where(P.c.session_id==session_id))
    # Summary cards describe the whole session, independent of applied filters.
    summary=base.subquery()
    counts=dict((await db.execute(select(summary.c.state,func.count()).group_by(summary.c.state))).all())
    district_id=filters.get('district_id');school_id=filters.get('school_id');class_id=filters.get('class_id');subject_id=filters.get('subject_id')
    if district_id:base=base.where(P.c.school_class_id.in_(select(K.c.id).join(H,H.c.id==K.c.school_id).where(H.c.district_id==district_id)))
    if school_id:base=base.where(P.c.school_class_id.in_(select(K.c.id).where(K.c.school_id==school_id)))
    if class_id:base=base.where(P.c.school_class_id==class_id)
    if filters.get('q'):
        query=filters['q'].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        base=base.where(P.c.full_name.ilike('%'+query+'%',escape='\\'))
    if category!='all':base=base.where(state==category)
    # A subject filter narrows displayed columns; progress totals stay across all subjects.
    subjects=[s for s in all_subjects if not subject_id or s.id==subject_id]
    status=filters.get('status','all')
    if status!='all':
        scoped=select(T.c.id).where(T.c.participant_id==P.c.id,
            T.c.diagnostic_subject_id.in_([s.id for s in subjects]))
        if status=='not_started':
            # At least one selected subject has no attempt; NULL is not counted as an answer.
            missing=select(D.c.id).where(D.c.session_id==session_id)
            if subject_id:missing=missing.where(D.c.id==subject_id)
            has_attempt=exists(select(T.c.id).where(T.c.participant_id==P.c.id,T.c.diagnostic_subject_id==D.c.id).correlate(P,D))
            base=base.where(exists(missing.where(~has_attempt).correlate(P)))
        elif status in ('active','submitted','expired'):base=base.where(exists(scoped.where(T.c.status==status).correlate(P)))
        elif status=='scored':base=base.where(exists(scoped.join(R,R.c.assessment_student_id==T.c.assessment_student_id).correlate(P)))
        elif status=='pending_review':
            has_total=exists(select(R.c.id).where(R.c.assessment_student_id==T.c.assessment_student_id).correlate(T))
            base=base.where(exists(scoped.where(T.c.assessment_student_id.is_not(None),~has_total).correlate(P)))
        elif status=='error':base=base.where(exists(scoped.where(T.c.grading_error.is_not(None)).correlate(P)))
    total=(await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    pages=max(1,(total+page_size-1)//page_size);page=min(page,pages)
    rows=list((await db.execute(base.order_by(P.c.school_name,P.c.class_label,P.c.full_name,P.c.id)
        .offset((page-1)*page_size).limit(page_size))).all())
    person_ids=[r.id for r in rows]
    attempts=list((await db.execute(select(T.c.participant_id,T.c.diagnostic_subject_id,T.c.status)
        .where(T.c.participant_id.in_(person_ids),T.c.diagnostic_subject_id.in_([s.id for s in subjects])))).all()) if person_ids else []
    return subjects,counts,total,page,rows,attempts,all_subjects
