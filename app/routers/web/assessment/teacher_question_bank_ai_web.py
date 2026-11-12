from dataclasses import replace
from app.modules.assessment.helpers.question_creation_plan import parse_plan
"""Included by the existing /teacher/question-bank router."""
import re
from app.modules.assessment.helpers.ai_education_track import selected_track
from decimal import Decimal
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from app.db.session import async_session_maker
from app.modules.users.deps import require_teacher_workspace
from app.modules.users.models import User
from app.modules.assessment.enums import AssessmentLanguage, AssessmentQuestionDifficulty, AssessmentQuestionType
from app.modules.assessment.ai.bilingual_generation_provider import BilingualGenerationProvider
from app.modules.assessment.schemas.teacher_ai_question_dto import TeacherAIQuestionInputDTO
from app.modules.assessment.services.teacher_question_bank_service import TeacherQuestionBankService
from app.modules.assessment.services.teacher_ai_question_web_service import TeacherAIQuestionWebService as Service, \
    AIRequestNotFound
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(tags=['teacher-question-bank-ai'])


def staff_id(user):
    if user.staff_member_id is None:
        raise HTTPException(403, 'Мұғалім профилі қызметкермен байланыстырылмаған.')
    return user.staff_member_id


def parse_scope(scope):
    if not scope:
        return None, None
    if not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*', scope):
        raise HTTPException(400, 'Пән мен сыныпты дұрыс таңдаңыз.')
    return tuple(int(value) for value in scope.split(':'))


async def page(request, user, *, scope=None, quarter=1, token=None, values=None, error=None, status_code=200,
               language=AssessmentLanguage.KAZAKH, education_track=None):
    values = dict(values or {})
    # One source for GET filters, POST errors and the task language.
    selected_language = AssessmentLanguage(values.get('language', language.value))
    values['language'] = selected_language.value
    sid, grade = parse_scope(scope)
    if grade not in (10, 11):
        education_track = None
    if education_track is not None and education_track not in ('general', 'emn', 'ogn'):
        raise HTTPException(400, 'Некорректное направление обучения.')
    track_pending = grade in (10, 11) and education_track is None
    track = selected_track(grade, education_track) if grade and not track_pending else None
    if not 1 <= quarter <= 4:
        raise HTTPException(400, 'Тоқсан 1–4 аралығында болуы керек.')
    member = staff_id(user)
    async with async_session_maker() as db:
        context = await TeacherQuestionBankService.get_create_context(
            db,
            staff_member_id=member,
        )

        objectives = []

        if sid is not None and grade is not None:
            allowed = any(
                item.subject_id == sid and item.grade_level == grade
                for item in context.teaching_scope
            )

            if not allowed:
                raise HTTPException(
                    403,
                    'Бұл пән мен сыныпқа қолжетімділік жоқ.',
                )

            if not track_pending:
                objectives = await TeacherQuestionBankService.get_learning_objectives(
                    db,
                    staff_member_id=member,
                    subject_id=sid,
                    grade_level=grade,
                    quarter=quarter,
                    education_track=track,
                )
    # Do not create unused tokens until a full educational context is selected.
    if token is None and objectives:
        token = await Service.issue(session_factory=async_session_maker, user_id=user.id)
    response = render(templates, request, 'teacher/assessment/question_bank/ai_create.html', {
        'user': user, 'teaching_scope': context.teaching_scope, 'objectives': objectives,
        'scope': scope, 'subject_id': sid, 'grade_level': grade, 'quarter': quarter, 'token': token,
        'education_track': education_track, 'track_pending': track_pending,
        'values': values or {}, 'error': error, 'selected_language': selected_language.value,
        'question_types': list(AssessmentQuestionType),
        'difficulties': list(AssessmentQuestionDifficulty), 'languages': list(AssessmentLanguage),
    })
    response.status_code = status_code
    response.headers['Cache-Control'] = 'no-store'
    return response


def result_url(request, row):
    if row['status']=='completed' and len(row.get('item_ids') or []) > 1:
        return str(request.url_for('teacher_question_bank_ai_status_page',token=row['token']))
    if row['status'] == 'completed' and row['item_id'] is not None:
        name = ('teacher_question_languages' if row.get('item_language') in ('ru', 'kk')
                else 'teacher_question_bank_item_edit_page') if row.get('item_status', 'draft') in (
            'draft', 'rejected') else 'teacher_question_bank_item_detail_page'
        return str(request.url_for(name, item_id=row['item_id']))
    return str(request.url_for('teacher_question_bank_ai_status_page', token=row['token']))


@router.get('/ai/create', response_class=HTMLResponse, name='teacher_question_bank_ai_create_page')
async def ai_create(request: Request, scope: str | None = None, quarter: int = 1,
                    language: AssessmentLanguage = AssessmentLanguage.KAZAKH,
                    education_track: str | None = None,
                    user: User = Depends(require_teacher_workspace)):
    return await page(request, user, scope=scope, quarter=quarter, language=language, education_track=education_track)


@router.post('/ai/create', name='teacher_question_bank_ai_create_submit')
async def ai_generate(request: Request, token: str = Form(...), subject_id: int = Form(...),
                      grade_level: int = Form(...), quarter: int = Form(...), objective_id: int = Form(...),
                      question_type: AssessmentQuestionType = Form(AssessmentQuestionType.SINGLE_CHOICE),
                      difficulty: AssessmentQuestionDifficulty = Form(AssessmentQuestionDifficulty.BASIC), language: AssessmentLanguage = Form(...),
                      max_score: Decimal = Form(Decimal("1")), title: str = Form(''), additional_requirements: str = Form(''),
                      education_track: str | None = Form(None),
                      source_image: UploadFile | None = File(None),
                      image_a: UploadFile | None = File(None), image_b: UploadFile | None = File(None),
                      image_c: UploadFile | None = File(None), image_d: UploadFile | None = File(None),
                      user: User = Depends(require_teacher_workspace)):
    member = staff_id(user)
    data = TeacherAIQuestionInputDTO(subject_id, grade_level, quarter, objective_id,
                                     question_type, difficulty, language, max_score, title, additional_requirements,
                                     education_track)
    try:
        raw_plan = (await request.form()).get('creation_plan')
        if raw_plan is not None:
            plan = parse_plan(raw_plan, ai=True)
            first = plan[0]
            data = replace(data, creation_plan=plan, question_type=AssessmentQuestionType(first['question_type']),
                difficulty=AssessmentQuestionDifficulty(first['difficulty']), max_score=Decimal(first['max_score']))
        image_mode = any(r['question_type']=='image_choice' for r in data.creation_plan) if data.creation_plan else data.question_type == AssessmentQuestionType.IMAGE_CHOICE
        uploads = (image_a, image_b, image_c, image_d)
        if image_mode:
            if data.creation_plan and (len(data.creation_plan)!=1 or data.creation_plan[0]['count']!=1):
                raise ValueError('Для рисунков: один тип и одна карточка / Суреттер үшін: бір түр және бір карточка.')
            if any(f is None or not f.filename for f in uploads):
                raise ValueError('Загрузите четыре варианта A–D / Төрт A–D нұсқасын жүктеңіз.')
        elif any(f is not None and f.filename for f in uploads):
            raise ValueError('Рисунки вариантов доступны только для image_choice / Нұсқа суреттері тек image_choice үшін.')
        provider = BilingualGenerationProvider()
        if source_image is not None and source_image.filename:
            if language.value not in ('ru','kk'):
                raise ValueError('Images currently support RU/KK only.')
            from app.core.storage.factory import get_storage
            from app.modules.assessment.helpers.ai_source_image import prepare_image
            key, image_data = await prepare_image(source_image, storage=get_storage(), user_id=user.id)
            data = replace(data, source_image_key=key)
            provider.source_image_data_url = image_data
        if image_mode:
            from app.core.storage.factory import get_storage
            from app.modules.assessment.helpers.ai_source_image import prepare_image
            keys, urls = [], []
            storage = get_storage()
            for upload in uploads:
                key, url = await prepare_image(upload, storage=storage, user_id=user.id)
                keys.append(key); urls.append(url)
            if len(set(keys)) != 4:
                raise ValueError('Варианты A–D должны быть разными / A–D нұсқалары әртүрлі болуы керек.')
            data = replace(data, image_option_keys=tuple(keys))
            provider.image_option_data_urls = tuple(urls)
        row = await Service.generate(session_factory=async_session_maker, provider=provider,
                                     token=token, user_id=user.id, staff_member_id=member, data=data)
    except AIRequestNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        return await page(request, user, scope=f'{subject_id}:{grade_level}', quarter=quarter, token=token,
                          values={'objective_id': objective_id, 'question_type': question_type.value,
                                  'difficulty': difficulty.value, 'language': language.value,
                                  'max_score': str(max_score),
                                  'title': title, 'additional_requirements': additional_requirements,
                                  'creation_plan': (await request.form()).get('creation_plan','')},
                          error=str(exc),
                          status_code=400, language=language, education_track=education_track)
    return RedirectResponse(result_url(request, row), status_code=303)


async def run_row(token, user):
    staff_id(user)
    try:
        return await Service.status(session_factory=async_session_maker, token=token, user_id=user.id)
    except AIRequestNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get('/ai/runs/{token}', response_class=HTMLResponse, name='teacher_question_bank_ai_status_page')
async def ai_status(request: Request, token: str, user: User = Depends(require_teacher_workspace)):
    row = await run_row(token, user)
    response = render(templates, request, 'teacher/assessment/question_bank/ai_status.html', {
        'user': user, 'run': row,
        'edit_url': result_url(request, row) if row['status'] == 'completed' and row['item_id'] and len(row.get('item_ids') or []) <= 1 else None,
    })
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/ai/runs/{token}/status', name='teacher_question_bank_ai_status_json')
async def ai_status_json(request: Request, token: str, user: User = Depends(require_teacher_workspace)):
    row = await run_row(token, user)
    return JSONResponse({'status': row['status'], 'url': result_url(request, row)},
                        headers={'Cache-Control': 'no-store'})


@router.get('/ai/runs/{token}/recovery', response_class=HTMLResponse, name='teacher_ai_recovery_page')
async def ai_recovery(request: Request, token: str, index: int = 0,
                      user: User = Depends(require_teacher_workspace)):
    from app.modules.assessment.services.ai_generation_recovery_service import AIGenerationRecoveryService as Recovery
    try:
        row = await Recovery.view(session_factory=async_session_maker, token=token, user_id=user.id)
    except AIRequestNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    cards = Recovery.cards(row)
    if not 0 <= index < len(cards):
        raise HTTPException(404, 'Задание не найдено.')
    response = render(templates, request, 'teacher/assessment/question_bank/ai_recovery.html', {
        'user':user, 'run':row, 'cards':cards, 'card':cards[index],
    })
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.post('/ai/runs/{token}/recovery', name='teacher_ai_recovery_submit')
async def ai_recovery_submit(request: Request, token: str, index: int = Form(...),
                             revision: int = Form(...), editor_json: str = Form(...),
                             action: str = Form('check'), user: User = Depends(require_teacher_workspace)):
    from app.modules.assessment.services.ai_generation_recovery_service import AIGenerationRecoveryService as Recovery, RecoveryConflict
    if action not in ('check','save'):
        raise HTTPException(400, 'Неизвестное действие.')
    try:
        item_id, error = await Recovery.edit(session_factory=async_session_maker, token=token,
            user_id=user.id, staff_member_id=staff_id(user), index=index, revision=revision,
            editor_json=editor_json, save=action=='save')
    except AIRequestNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except RecoveryConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if item_id is not None:
        return RedirectResponse(str(request.url_for('teacher_question_languages',item_id=item_id)),status_code=303)
    return RedirectResponse(str(request.url_for('teacher_ai_recovery_page',token=token))+f'?index={index}',status_code=303)


@router.post('/ai/runs/{token}/recovery/import', name='teacher_ai_recovery_import')
async def ai_recovery_import(request: Request, token: str, diagnostic: UploadFile = File(...),
                             quarter: int = Form(...), education_track: str | None = Form(None),
                             user: User = Depends(require_teacher_workspace)):
    from app.modules.assessment.helpers.generation_recovery import MAX_BYTES
    from app.modules.assessment.services.ai_generation_recovery_service import AIGenerationRecoveryService as Recovery, RecoveryConflict
    try:
        contents = await diagnostic.read(MAX_BYTES+1)
        if len(contents) > MAX_BYTES:
            raise ValueError('Диагностический файл слишком большой.')
        await Recovery.import_diagnostic(session_factory=async_session_maker, token=token, user_id=user.id,
            staff_member_id=staff_id(user), diagnostic_json=contents.decode('utf-8-sig'),
            quarter=quarter, education_track=education_track)
    except AIRequestNotFound as exc:
        raise HTTPException(404,str(exc)) from exc
    except RecoveryConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise HTTPException(400,str(exc)) from exc
    finally:
        await diagnostic.close()
    return RedirectResponse(str(request.url_for('teacher_ai_recovery_page',token=token)),status_code=303)
