from app.modules.assessment.repositories import diagnostic_result_repo as repo
from app.modules.assessment.helpers.diagnostic_report import build
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError


async def report(db,attempt_id,*,identity=None,user=None):
    from app.modules.assessment.services import diagnostic_attempt_service as execution
    context=await repo.context(db,attempt_id)
    if context is None:raise WorkPlanError('Работа не найдена. / Жұмыс табылмады.')
    attempt,person,subject,session=context
    if user is not None:
        from app.modules.assessment.services.diagnostic_session_service import own
        await own(db,user,session['id'])
    else:
        pupil=await execution.authorize(db,identity)
        if pupil.id!=person['id'] or not session['results_published_at']:
            raise execution.AttemptError('subject',404)
    if attempt['status']=='active':raise WorkPlanError('Работа ещё выполняется. / Жұмыс әлі орындалуда.')
    assignment=person['assignments'][str(subject['source_plan_id'])];language=assignment['language']

    names=(subject.get('assessment_context') or {}).get('standard_name_v1')
    if names:session=dict(session,title_ru=names['ru'],title_kk=names['kk'])
    sid=attempt['assessment_student_id'];answers=await repo.answer_rows(db,sid) if sid else []
    total=await repo.total(db,sid) if sid else None
    return dict(attempt=attempt,person=person,subject=subject,session=session,language=language,
        total=total,questions=build(attempt,answers,language=='ru') if sid else [],
        processing=not sid,processing_error=attempt['grading_error'],is_organizer=user is not None,
        tr=lambda ru,kk:ru if language=='ru' else kk)
