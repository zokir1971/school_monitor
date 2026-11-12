"""Teacher-only draft assembly; UI language never selects task content language."""
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from app.db.session import get_db
from app.core.i18n import translate, resolve_language
from app.core.assessment_bank_ui_messages import BANK_MESSAGES
from app.modules.users.deps import require_teacher_workspace
from app.modules.staff.utils.staff_require_member import require_staff_member_id
from app.modules.staff.utils.staff_require_school import require_school_id
from app.modules.assessment.repositories.teacher_question_bank_repo import TeacherQuestionBankRepo
from app.modules.assessment.services import assessment_bank_service as service
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix='/teacher/assessment/from-bank', tags=['assessment-bank'])
logger = logging.getLogger(__name__)


def boundary(user):
    return dict(school_id=require_school_id(user), user_id=user.id,
        staff_member_id=require_staff_member_id(user))


def number(value):
    try:
        result = int(str(value))
        if result <= 0:
            raise ValueError
        return result
    except (TypeError, ValueError) as exc:
        raise service.BankSelectionError('Выберите предмет и класс из доступного списка.') from exc


async def index_context(db, user, error=None, values=None):
    scope = boundary(user)
    return dict(user=user, error=error, values=values or {},
        teaching_scope=await TeacherQuestionBankRepo.list_teaching_scope(db, staff_member_id=scope['staff_member_id']),
        assessments=await service.list_drafts(db, scope['school_id'], scope['user_id']))


async def workspace(request, db, user, assessment_id, *, error=None, status_code=200):
    try:
        assessment = await service.own_assessment(db, assessment_id, **boundary(user))
    except service.BankSelectionError as exc:
        raise HTTPException(404, translate(str(exc), resolve_language(request, user))) from exc
    if error is None:
        candidate = request.query_params.get('bank_error')
        error = candidate if candidate in BANK_MESSAGES else None
    try:
        after = max(0, int(request.query_params.get('after', 0)))
    except ValueError:
        after = 0
    questions = await service.saved_questions(db, assessment_id)
    rows, next_after = await service.catalog(db, assessment, after=after)
    used = {q.content.get('_bank_source', {}).get('item_id') for q in questions}
    return render(templates, request, 'teacher/assessment/from_bank/workspace.html', dict(
        user=user, assessment=assessment, language=assessment.settings['bank_language'],
        grade_level=assessment.settings['bank_grade'], error=error, rows=rows, used=used,
        saved=[dict(question=q, view=service.question_view(q, assessment.settings['bank_language'])) for q in questions],
        next_after=next_after, after=after,
        editable=service.code(assessment.status) == 'draft'), status_code=status_code)


@router.get('', name='teacher_assessment_bank_page')
async def index(request: Request, db=Depends(get_db), user=Depends(require_teacher_workspace)):
    return render(templates, request, 'teacher/assessment/from_bank/index.html', await index_context(db, user))


@router.post('', name='teacher_assessment_bank_create')
async def create(request: Request, db=Depends(get_db), user=Depends(require_teacher_workspace)):
    scope = boundary(user)
    form = await request.form()
    values = {k: str(form.get(k, '')) for k in ['title', 'scope', 'language']}
    try:
        parts = values['scope'].split(':')
        if len(parts) != 2:
            raise service.BankSelectionError('Выберите предмет и класс из доступного списка.')
        assessment_id = await service.create_draft(db, **scope, subject_id=number(parts[0]),
            grade_level=number(parts[1]), title=values['title'], language=values['language'])
        await db.commit()
    except service.BankSelectionError as exc:
        await db.rollback()
        await db.refresh(user)
        return render(templates, request, 'teacher/assessment/from_bank/index.html',
            await index_context(db, user, str(exc), values), status_code=400)
    except Exception:
        await db.rollback()
        raise
    return RedirectResponse(request.url_for('teacher_assessment_bank_workspace', assessment_id=assessment_id), status_code=303)


@router.get('/{assessment_id}', name='teacher_assessment_bank_workspace')
async def detail(request: Request, assessment_id: int, db=Depends(get_db), user=Depends(require_teacher_workspace)):
    return await workspace(request, db, user, assessment_id)


@router.post('/{assessment_id}/add', name='teacher_assessment_bank_add')
async def add(request: Request, assessment_id: int, db=Depends(get_db), user=Depends(require_teacher_workspace)):
    scope = boundary(user)
    form = await request.form()
    try:
        ids = [number(v) for v in form.getlist('item_ids')]
        await service.add_from_bank(db, assessment_id=assessment_id, **scope, item_ids=ids)
        await db.commit()
    except service.BankSelectionError as exc:
        logger.info('Assessment bank selection rejected: %s', exc)
        await db.rollback()
        await db.refresh(user)
        return RedirectResponse(request.url_for('teacher_assessment_bank_workspace', assessment_id=assessment_id)
            .include_query_params(bank_error=str(exc)), status_code=303)
    except Exception:
        await db.rollback()
        raise
    return RedirectResponse(request.url_for('teacher_assessment_bank_workspace', assessment_id=assessment_id), status_code=303)


@router.post('/{assessment_id}/remove/{question_id}', name='teacher_assessment_bank_remove')
async def remove(request: Request, assessment_id: int, question_id: int, db=Depends(get_db), user=Depends(require_teacher_workspace)):
    scope = boundary(user)
    try:
        await service.remove_question(db, assessment_id=assessment_id, question_id=question_id, **scope)
        await db.commit()
    except service.BankSelectionError as exc:
        await db.rollback()
        await db.refresh(user)
        return RedirectResponse(request.url_for('teacher_assessment_bank_workspace', assessment_id=assessment_id)
            .include_query_params(bank_error=str(exc)), status_code=303)
    except Exception:
        await db.rollback()
        raise
    return RedirectResponse(request.url_for('teacher_assessment_bank_workspace', assessment_id=assessment_id), status_code=303)


@router.get('/{assessment_id}/add', name='teacher_assessment_bank_add_return', dependencies=[Depends(require_teacher_workspace)])
@router.get('/{assessment_id}/remove/{question_id}', name='teacher_assessment_bank_remove_return', dependencies=[Depends(require_teacher_workspace)])
async def command_return(request: Request, assessment_id: int):
    # Compatibility navigation only. The target GET enforces school and ownership.
    return RedirectResponse(request.url_for('teacher_assessment_bank_workspace', assessment_id=assessment_id), status_code=303)
