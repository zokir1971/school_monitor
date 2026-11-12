# app/routers/web/assessment/teacher_question_bank_web.py

from __future__ import annotations
from uuid import uuid4
from app.modules.assessment.helpers.question_creation_plan import parse_plan, expand_plan
from app.modules.assessment.repositories.manual_creation_set_repo import ManualCreationSetRepo as CreationSets
from app.modules.assessment.helpers.ai_education_track import selected_track

from decimal import Decimal
from typing import Annotated, cast

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
    File,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.factory import get_storage
from app.modules.assessment.services.question_bank_media_service import (
    QuestionBankMediaService, MAX_IMAGE_BYTES, MEDIA_KEY_PATTERN,
)
from app.db.session import get_db
from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
    QuestionBankItemStatus,
)
from app.modules.assessment.helpers.question_bank_form import (
    build_question_form_contract,
    build_question_plain_text,
    build_question_text_segments,
)
from app.modules.assessment.schemas.teacher_question_bank_dto import TeacherQuestionBankCreateDraftDTO, \
    TeacherQuestionBankUpdateDraftDTO
from app.modules.assessment.services.teacher_question_bank_service import TeacherQuestionBankService
from app.modules.users.deps import require_teacher_workspace
from app.modules.assessment.helpers.bank_access import require_bank_reader
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.helpers.request import parse_optional_int
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/teacher/question-bank",
    tags=["teacher-question-bank"],
)


# =========================================================
# HELPERS
# =========================================================


def _parse_question_bank_status(
        value: str | None,
) -> QuestionBankItemStatus | None:
    """
    Без параметра возвращает None = все статусы.

    Неизвестное значение query-параметра
    считается ошибкой запроса.
    """
    if value is None:
        return None

    normalized = value.strip().lower()

    if not normalized:
        return None

    try:
        return QuestionBankItemStatus(
            normalized
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Некорректный статус Question Bank."
            ),
        ) from exc


# =========================================================
# QUESTION BANK
# =========================================================


@router.get(
    "",
    name="teacher_question_bank_page",
    response_class=HTMLResponse,
)
async def teacher_question_bank_page(
        request: Request,
        user: User = Depends(require_teacher_workspace),
):
    """
    Главная рабочая страница
    конструктора заданий учителя.

    На первом этапе является точкой входа
    в Question Bank.

    Дальнейшая функциональность:
        - создание задания вручную;
        - AI generation;
        - черновики;
        - экспертная проверка;
        - готовые задания;
        - история review.
    """

    return render(
        templates,
        request,
        "teacher/assessment/question_bank/index.html",
        {
            "user": user,
        },
    )


# =========================================================
# QUESTION BANK CATALOG
# =========================================================


@router.get(
    "/catalog",
    name="teacher_question_bank_catalog_page",
    response_class=HTMLResponse,
)
async def teacher_question_bank_catalog_page(
        request: Request,
        subject_id: str | None = None,
        grade_level: str | None = None,
        quarter: str | None = None,
        objective_id: str | None = None,
        education_track: str | None = None,
        offset: int = 0,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_bank_reader),
):
    """
    Общий каталог Question Bank.

    Учитель видит READY-задания всех авторов,
    если выбранные предмет и параллель входят
    в его teaching scope.

    Фильтрация выполняется последовательно:
        subject_id
        + grade_level
        + quarter
        + objective_id

    Авторство задания не ограничивает
    его присутствие в каталоге.
    """

    # =====================================================
    # 1. QUERY PARAMETERS
    # =====================================================

    subject_id_value = parse_optional_int(
        subject_id
    )

    grade_level_value = parse_optional_int(
        grade_level
    )

    quarter_value = parse_optional_int(
        quarter
    )

    objective_id_value = parse_optional_int(
        objective_id
    )

    # =====================================================
    # 2. TEACHER CONTEXT
    # =====================================================

    staff_member_id = cast(
        int | None,
        user.staff_member_id,
    )

    user_id = cast(
        int,
        user.id,
    )

    # =====================================================
    # 3. QUERY PARAMETER CONTRACT
    # =====================================================

    if grade_level_value is not None and subject_id_value is None:
        raise HTTPException(400, 'Сначала выберите предмет / Алдымен пәнді таңдаңыз.')
    if grade_level_value not in (10, 11):
        education_track = None
    elif education_track == '':
        education_track = None
    elif education_track not in (None, 'all', 'general', 'emn', 'ogn'):
        raise HTTPException(400, 'Некорректное направление / Бағыт дұрыс емес.')

    # quarter нельзя передавать без subject + grade.
    if quarter_value is not None and (
            subject_id_value is None
            or grade_level_value is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Тоқсанды таңдау үшін "
                "пән мен сынып көрсетілуі керек."
            ),
        )

    # objective_id требует полный учебный контекст.
    if objective_id_value is not None and (
            subject_id_value is None
            or grade_level_value is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Оқу мақсатын таңдау үшін "
                "пән, сынып және тоқсан "
                "көрсетілуі керек."
            ),
        )

    # =====================================================
    # 4. CATALOG PAGE
    # =====================================================

    try:
        page = (
            await TeacherQuestionBankService
            .get_catalog_page(
                db,
                user_id=user_id,
                staff_member_id=staff_member_id,
                shared_ready=True,
                offset=offset,
                education_track=education_track,
                subject_id=subject_id_value,
                grade_level=grade_level_value,
                quarter=quarter_value,
                objective_id=objective_id_value,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # =====================================================
    # 5. RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/question_bank/catalog.html",
        {
            "user": user,
            "page": page,
            "shared_ready": True,
            "education_track": education_track,
            "catalog_route": "shared_question_bank_catalog",
        },
    )


# =========================================================
# QUESTION BANK ITEMS
# =========================================================

@router.get(
    "/items",
    name="teacher_question_bank_items_page",
    response_class=HTMLResponse,
)
async def teacher_question_bank_items_page(
        request: Request,
        status: str | None = None,
        q: str = '', subject_id: str = '',
        grade_level: str = '', quarter: str = '',
        question_type: str = '',
        difficulty: str = '',
        language: str = '',
        origin: str = '',

        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_teacher_workspace),
):
    """
    Список собственных QuestionBankItem учителя.

    Поддерживает фильтрацию:

        ?status=draft
        ?status=review
        ?status=ready
        ?status=rejected
        ?status=archived

    Без status отображаются все задания.
    """

    from app.modules.assessment.enums import QuestionBankItemOrigin
    from app.modules.assessment.repositories.teacher_question_bank_repo import TeacherQuestionBankRepo
    filters = {'q': q.strip()}
    if len(filters['q']) > 200:
        raise HTTPException(400, 'Поиск: не более 200 символов / Іздеу: 200 таңбадан аспауы керек.')
    try:
        for name, value, minimum, maximum in [('subject_id',subject_id,1,2147483647), ('grade_level',grade_level,1,12), ('quarter',quarter,1,4)]:
            if value:
                number = int(value)
                if not minimum <= number <= maximum:
                    raise ValueError(name)
                filters[name] = number
        for name, value, enum in [('question_type',question_type,AssessmentQuestionType), ('difficulty',difficulty,AssessmentQuestionDifficulty), ('language',language,AssessmentLanguage), ('origin',origin,QuestionBankItemOrigin)]:
            if value:
                filters[name] = enum(value).value
    except ValueError as exc:
        raise HTTPException(400, 'Некорректный фильтр / Сүзгі мәні дұрыс емес.') from exc
    selected_status = _parse_question_bank_status(
        status
    )

    page = await TeacherQuestionBankService.get_page(
        db,
        user_id=user.id,
        status=selected_status,
        filters=filters,
    )

    return render(
        templates,
        request,
        "teacher/assessment/question_bank/items.html",
        {
            "user": user,
            "page": page,
            "filters": filters,
            "subject_filters": await TeacherQuestionBankRepo.list_subject_filters(db, user_id=user.id),
            "filter_types": list(AssessmentQuestionType),
            "filter_difficulties": list(AssessmentQuestionDifficulty),
            "filter_languages": list(AssessmentLanguage),
        },
    )


@router.get(
    "/items/create",
    name="teacher_question_bank_item_create_page",
    response_class=HTMLResponse,
)
async def teacher_question_bank_item_create_page(
        request: Request,
        subject_id: int | None = None,
        grade_level: int | None = None,
        quarter: int | None = None,
        education_track: str | None = None,
        objective_id: int | None = None,
        created_item_id: int | None = None,
        set_token: str | None = None,
        slot_index: int | None = None,
        language: AssessmentLanguage = AssessmentLanguage.KAZAKH,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_teacher_workspace),
):
    """
    Страница создания нового QuestionBankItem.

    Шаги:
        1. Предмет + класс
        2. Четверть
        3. Одна учебная цель
        4. Создание задания
    """

    manual_set = None
    creation_slot = None
    if set_token:
        manual_set = await CreationSets.get(db, token=set_token, user_id=user.id)
        if manual_set is None:
            raise HTTPException(404, 'Набор заданий не найден.')
        if slot_index is None:
            slot_index = next((i for i,item_id in enumerate(manual_set['item_ids']) if item_id is None),0)
        if not 0 <= slot_index < len(manual_set['slots']):
            raise HTTPException(400, 'Некорректный номер задания.')
        context = manual_set['context']
        subject_id, grade_level, quarter = context['subject_id'], context['grade_level'], context['quarter']
        objective_id, education_track = context['objective_id'], context.get('education_track')
        language = AssessmentLanguage(context['language'])
        if manual_set['item_ids'][slot_index] is None:
            creation_slot = manual_set['slots'][slot_index]

    staff_member_id = cast(
        int | None,
        user.staff_member_id,
    )

    if staff_member_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Профиль учителя не связан "
                "с сотрудником школы."
            ),
        )

    # =====================================================
    # CREATE CONTEXT
    # =====================================================

    create_context = (
        await TeacherQuestionBankService.get_create_context(
            db,
            staff_member_id=staff_member_id,
        )
    )

    objectives = []
    selected_objective = None

    # =====================================================
    # QUERY PARAMETER CONTRACT
    # =====================================================

    # subject_id и grade_level должны передаваться вместе.
    if (
            (subject_id is None)
            != (grade_level is None)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "subject_id және grade_level "
                "бірге көрсетілуі керек."
            ),
        )

    # quarter нельзя передавать без subject + grade.
    if quarter is not None and (
            subject_id is None
            or grade_level is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Тоқсанды таңдау үшін "
                "пән мен сынып көрсетілуі керек."
            ),
        )

    # objective_id нельзя передавать,
    # пока не выбран полный контекст.
    if objective_id is not None and (
            subject_id is None
            or grade_level is None
            or quarter is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Оқу мақсатын таңдау үшін "
                "пән, сынып және тоқсан "
                "көрсетілуі керек."
            ),
        )

    if grade_level not in (10, 11):
        education_track = None
    if education_track == '':
        education_track = None
    track_pending = grade_level in (10, 11) and education_track is None
    try:
        track = selected_track(grade_level, education_track) if not track_pending else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if track_pending and objective_id is not None:
        raise HTTPException(status_code=400, detail='Для 10–11 классов выберите направление обучения.')

    # =====================================================
    # LEARNING OBJECTIVES
    # =====================================================

    if (
            subject_id is not None
            and grade_level is not None
            and quarter is not None
            and not track_pending
    ):
        objectives = (
            await TeacherQuestionBankService.get_learning_objectives(
                db,
                staff_member_id=staff_member_id,
                subject_id=subject_id,
                grade_level=grade_level,
                quarter=quarter,
                education_track=track,
            )
        )

    # =====================================================
    # SELECTED LEARNING OBJECTIVE
    #
    # Дополнительного SELECT здесь нет.
    # Ищем выбранную цель в уже загруженном списке.
    # =====================================================

    if objective_id is not None:
        selected_objective = next(
            (
                objective
                for objective in objectives
                if (
                    objective.learning_objective_id
                    == objective_id
                )
            ),
            None,
        )

        # objective_id существует как query parameter,
        # но не входит в разрешённый teacher context.
        if selected_objective is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Таңдалған оқу мақсаты "
                    "табылмады немесе оған "
                    "қолжетімділік жоқ."
                ),
            )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/question_bank/create.html",
        {
            "user": user,

            "create_context": create_context,
            "objectives": objectives,

            "selected_subject_id": subject_id,
            "selected_grade_level": grade_level,
            "selected_quarter": quarter,
            "education_track": education_track,
            "track_pending": track_pending,

            "selected_objective_id": objective_id,
            "selected_objective": selected_objective,
            "selected_language": language.value,
            "created_item_id": created_item_id,
            "manual_set": manual_set,
            "creation_slot": creation_slot,
            "slot_index": slot_index,
            "plan_token": uuid4().hex,
            "recent_sets": await CreationSets.recent(db, user_id=user.id),
        },
    )


@router.post('/sets/manual/{token}/delete', name='teacher_question_creation_set_delete')
async def delete_manual_set(token: str, request: Request,
                            db: AsyncSession = Depends(get_db),
                            user: User = Depends(require_teacher_workspace)):
    # Same lock as slot saving: deletion cannot race an in-flight attachment.
    row = await CreationSets.get(db, token=token, user_id=user.id, lock=True)
    if row is not None:
        await CreationSets.delete(db, token=token, user_id=user.id)
    await db.commit()
    # Fixed local GET target; never repeat the destructive POST on language change.
    return RedirectResponse(request.url_for('teacher_question_bank_item_create_page'), status_code=303)


@router.post('/sets/manual', name='teacher_question_creation_set_prepare')
async def prepare_manual_set(request: Request, db: AsyncSession = Depends(get_db),
                             user: User = Depends(require_teacher_workspace)):
    form = await request.form()
    try:
        from uuid import UUID
        token = str(form.get('plan_token', ''))
        if UUID(hex=token).hex != token:
            raise ValueError('Некорректный идентификатор набора.')
        rows = parse_plan(form.get('creation_plan', ''))
        slots = expand_plan(rows)
        subject_id, grade, quarter, objective_id = (int(str(form.get(key, ''))) for key in
            ('subject_id','grade_level','quarter','objective_id'))
        if user.staff_member_id is None:
            raise ValueError('Профиль учителя не связан с сотрудником.')
        language = AssessmentLanguage(form.get('language'))
        track_code = form.get('education_track') if grade in (10,11) else None
        track = selected_track(grade, track_code)
        objectives = await TeacherQuestionBankService.get_learning_objectives(db,
            staff_member_id=user.staff_member_id, subject_id=subject_id, grade_level=grade,
            quarter=quarter, education_track=track)
        if objective_id not in {obj.learning_objective_id for obj in objectives}:
            raise ValueError('Выбранная учебная цель недоступна.')
        context = dict(subject_id=subject_id,grade_level=grade,quarter=quarter,
            objective_id=objective_id,language=language.value,education_track=track_code)
        await CreationSets.create(db,token=token,user_id=user.id,context=context,slots=slots)
        row = await CreationSets.get(db,token=token,user_id=user.id)
        if row is None or row['context'] != context or row['slots'] != list(slots):
            raise ValueError('Параметры набора изменились. Обновите страницу.')
        await db.commit()
    except (ValueError, TypeError) as exc:
        await db.rollback()
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(request.url_for('teacher_question_bank_item_create_page').include_query_params(set_token=token),status_code=303)


@router.post(
    "/items/create",
    name="teacher_question_bank_item_create",
)
async def teacher_question_bank_item_create(
        request: Request,

        subject_id: Annotated[
            int,
            Form(),
        ],

        grade_level: Annotated[
            int,
            Form(),
        ],

        quarter: Annotated[
            int,
            Form(),
        ],

        objective_id: Annotated[
            int,
            Form(),
        ],

        question_type: Annotated[
            AssessmentQuestionType,
            Form(),
        ],

        difficulty: Annotated[
            AssessmentQuestionDifficulty,
            Form(),
        ],

        language: Annotated[
            AssessmentLanguage,
            Form(),
        ],

        max_score: Annotated[
            Decimal,
            Form(),
        ],

        title: Annotated[
            str | None,
            Form(),
        ] = None,

        instruction: Annotated[
            str | None,
            Form(),
        ] = None,

        explanation: Annotated[
            str | None,
            Form(),
        ] = None,

        author_comment: Annotated[
            str | None,
            Form(),
        ] = None,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Создаёт QuestionBankItem DRAFT
    через конструктор учителя.

    Основной текст вопроса и типоспецифичные
    поля HTML-form преобразуются web-helper'ом.

    Финальная доменная валидация выполняется в
    TeacherQuestionBankService.create_draft().
    """

    # =====================================================
    # 1. TEACHER CONTEXT
    # =====================================================

    staff_member_id = cast(
        int | None,
        user.staff_member_id,
    )

    if staff_member_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Профиль учителя не связан "
                "с сотрудником школы."
            ),
        )

    user_id = cast(
        int,
        user.id,
    )

    # =====================================================
    # 2. NORMALIZE OPTIONAL COMMON DATA
    # =====================================================

    normalized_title = (
        title.strip()
        if title and title.strip()
        else None
    )

    normalized_instruction = (
        instruction.strip()
        if instruction and instruction.strip()
        else None
    )

    normalized_explanation = (
        explanation.strip()
        if explanation and explanation.strip()
        else None
    )

    normalized_author_comment = (
        author_comment.strip()
        if author_comment and author_comment.strip()
        else None
    )

    # =====================================================
    # 3. HTML FORM -> QUESTION DATA / CONTRACT
    # =====================================================

    form = await request.form()
    education_track = form.get('education_track') if grade_level in (10, 11) else None
    try:
        track = selected_track(grade_level, education_track)
        if grade_level in (10, 11):
            eligible = await TeacherQuestionBankService.get_learning_objectives(
                db, staff_member_id=staff_member_id, subject_id=subject_id,
                grade_level=grade_level, quarter=quarter, education_track=track)
            if objective_id not in {obj.learning_objective_id for obj in eligible}:
                raise ValueError('Учебная цель не соответствует выбранному направлению.')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        text_segments = (
            build_question_text_segments(
                form
            )
        )

        await QuestionBankMediaService(get_storage()).validate_references(
            text_segments, user_id=user.id,
        )

        normalized_text = (
            build_question_plain_text(
                text_segments
            )
        )

        contract = (
            build_question_form_contract(
                question_type=question_type,
                form=form,
            )
        )

        if question_type == AssessmentQuestionType.SINGLE_CHOICE and 'parts' in contract.content:
            # Validate each distinct uploaded image through the existing storage ACL.
            images = {}
            for part in contract.content['parts']:
                for segments in [part['segments'], *[option['segments'] for option in part['options']]]:
                    for segment in segments:
                        if segment.get('type') == 'image':
                            images[segment['object_key']] = segment
            await QuestionBankMediaService(get_storage()).validate_references(list(images.values()), user_id=user.id)
        if question_type == AssessmentQuestionType.IMAGE_CHOICE:
            await QuestionBankMediaService(get_storage()).validate_option_references(
                contract.content["options"], user_id=user.id,
            )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # =====================================================
    # 4. DTO
    # =====================================================

    data = TeacherQuestionBankCreateDraftDTO(
        subject_id=subject_id,
        grade_level=grade_level,
        quarter=quarter,

        objective_id=objective_id,

        question_type=question_type,
        difficulty=difficulty,
        language=language,

        title=normalized_title,

        text=normalized_text,
        text_segments=text_segments,

        instruction=normalized_instruction,

        content=contract.content,
        answer_key=contract.answer_key,
        grading_settings=(
            contract.grading_settings
        ),

        max_score=max_score,

        explanation=normalized_explanation,
        author_comment=(
            normalized_author_comment
        ),
    )

    manual_set = None
    set_token = form.get('set_token')
    slot_index = 0
    if set_token:
        try:
            slot_index = int(str(form.get('slot_index', '')))
            manual_set = await CreationSets.get(db, token=set_token, user_id=user.id, lock=True)
            if manual_set is None or not 0 <= slot_index < len(manual_set['slots']):
                raise ValueError('Набор заданий не найден.')
            context = manual_set['context']
            expected = manual_set['slots'][slot_index]
            if (context != dict(subject_id=subject_id,grade_level=grade_level,quarter=quarter,
                    objective_id=objective_id,language=data.language.value,education_track=education_track)
                    or expected['question_type'] != data.question_type.value
                    or expected['difficulty'] != data.difficulty.value
                    or Decimal(expected['max_score']) != data.max_score):
                raise ValueError('Параметры задания не соответствуют составу набора.')
            from app.modules.assessment.helpers.element_scoring import weighted, parameters
            if weighted(expected) and any(data.grading_settings.get(k)!=v for k,v in parameters(data.question_type.value,expected).items()):
                raise ValueError('Параметры задания не соответствуют составу набора.')
            if manual_set['item_ids'][slot_index] is not None:
                return RedirectResponse(request.url_for('teacher_question_bank_item_edit_page',
                    item_id=manual_set['item_ids'][slot_index]),status_code=303)
        except (ValueError,TypeError) as exc:
            await db.rollback()
            raise HTTPException(400,str(exc)) from exc

    # =====================================================
    # 5. CREATE
    # =====================================================

    try:
        created = (
            await TeacherQuestionBankService
            .create_draft(
                db,
                user_id=user_id,
                staff_member_id=(
                    staff_member_id
                ),
                data=data,
                commit=manual_set is None,
            )
        )

        if manual_set is not None:
            ids = list(manual_set['item_ids'])
            ids[slot_index] = created.item_id
            await CreationSets.attach(db,token=set_token,user_id=user.id,item_ids=ids)
            await db.commit()
            next_slot = next((i for i,item_id in enumerate(ids) if item_id is None), None)
            if form.get('after_save') != 'translate':
                if next_slot is None:
                    return RedirectResponse(request.url_for('teacher_question_bank_item_detail_page', item_id=created.item_id), status_code=303)
                return RedirectResponse(request.url_for('teacher_question_bank_item_create_page').include_query_params(
                    set_token=set_token,slot_index=next_slot),status_code=303)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400,detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise

    if form.get('after_save') == 'translate' and data.language.value in {'ru','kk'}:
        return RedirectResponse(request.url_for('teacher_question_languages',item_id=created.item_id),status_code=303)

    # =====================================================
    # 6. PRG — KEEP CURRENT OBJECTIVE
    # =====================================================

    create_url = request.url_for(
        "teacher_question_bank_item_create_page"
    )

    create_url = (
        create_url.include_query_params(
            subject_id=subject_id,
            grade_level=grade_level,
            quarter=quarter,
            objective_id=objective_id,
            created_item_id=created.item_id,
            language=data.language.value,
            **({"education_track": education_track} if education_track else {}),
        )
    )

    return RedirectResponse(
        url=create_url,
        status_code=303,
    )


@router.get(
    "/items/{item_id}/edit",
    name="teacher_question_bank_item_edit_page",
    response_class=HTMLResponse,
)
async def teacher_question_bank_item_edit_page(
        request: Request,
        item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_teacher_workspace),
):
    """
    Страница редактирования собственного QuestionBankItem.

    Редактирование разрешено только для:
        - DRAFT;
        - REJECTED.
    """

    # =====================================================
    # 1. TEACHER CONTEXT
    # =====================================================

    staff_member_id = cast(
        int | None,
        user.staff_member_id,
    )

    if staff_member_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Профиль учителя не связан "
                "с сотрудником школы."
            ),
        )

    user_id = cast(
        int,
        user.id,
    )

    # =====================================================
    # 2. EDIT CONTEXT
    # =====================================================

    try:
        edit_context = (
            await TeacherQuestionBankService
            .get_edit_context(
                db,
                user_id=user_id,
                staff_member_id=staff_member_id,
                item_id=item_id,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # =====================================================
    # 3. CURRENT OBJECTIVE
    # =====================================================

    selected_objective_id = (
        edit_context.item.objectives[0].learning_objective_id
        if edit_context.item.objectives
        else None
    )

    selected_objective = next(
        (
            objective
            for objective in edit_context.learning_objectives
            if (
                objective.learning_objective_id
                == selected_objective_id
            )
        ),
        None,
    )

    # =====================================================
    # 4. RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/question_bank/edit.html",
        {
            "user": user,

            "edit_context": edit_context,
            "item": edit_context.item,

            "teaching_scope": (
                edit_context.teaching_scope
            ),
            "objectives": (
                edit_context.learning_objectives
            ),

            "selected_subject_id": (
                edit_context.item.subject_id
            ),
            "selected_grade_level": (
                edit_context.item.grade_level
            ),
            "selected_quarter": (
                edit_context.item.quarter
            ),

            "selected_objective_id": (
                selected_objective_id
            ),
            "selected_objective": (
                selected_objective
            ),
        },
    )


@router.post(
    "/items/{item_id}/edit",
    name="teacher_question_bank_item_update",
)
async def teacher_question_bank_item_update(
        request: Request,
        item_id: int,

        subject_id: Annotated[
            int,
            Form(),
        ],

        grade_level: Annotated[
            int,
            Form(),
        ],

        quarter: Annotated[
            int,
            Form(),
        ],

        objective_id: Annotated[
            int,
            Form(),
        ],

        question_type: Annotated[
            AssessmentQuestionType,
            Form(),
        ],

        difficulty: Annotated[
            AssessmentQuestionDifficulty,
            Form(),
        ],

        language: Annotated[
            AssessmentLanguage,
            Form(),
        ],

        max_score: Annotated[
            Decimal,
            Form(),
        ],

        title: Annotated[
            str | None,
            Form(),
        ] = None,

        instruction: Annotated[
            str | None,
            Form(),
        ] = None,

        explanation: Annotated[
            str | None,
            Form(),
        ] = None,

        author_comment: Annotated[
            str | None,
            Form(),
        ] = None,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Сохраняет изменения собственного QuestionBankItem.

    Допустимые исходные состояния:
        DRAFT
        REJECTED

    Lifecycle после успешного сохранения:
        DRAFT    -> DRAFT
        REJECTED -> DRAFT
    """

    # =====================================================
    # 1. TEACHER CONTEXT
    # =====================================================

    staff_member_id = cast(
        int | None,
        user.staff_member_id,
    )

    if staff_member_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Профиль учителя не связан "
                "с сотрудником школы."
            ),
        )

    user_id = cast(
        int,
        user.id,
    )

    # =====================================================
    # 2. NORMALIZE OPTIONAL COMMON DATA
    # =====================================================

    normalized_title = (
        title.strip()
        if title and title.strip()
        else None
    )

    normalized_instruction = (
        instruction.strip()
        if instruction and instruction.strip()
        else None
    )

    normalized_explanation = (
        explanation.strip()
        if explanation and explanation.strip()
        else None
    )

    normalized_author_comment = (
        author_comment.strip()
        if author_comment and author_comment.strip()
        else None
    )

    # =====================================================
    # 3. HTML FORM -> QUESTION CONTRACT
    # =====================================================

    form = await request.form()

    try:
        text_segments = (
            build_question_text_segments(
                form
            )
        )

        await QuestionBankMediaService(get_storage()).validate_references(
            text_segments, user_id=user.id,
        )

        normalized_text = (
            build_question_plain_text(
                text_segments
            )
        )

        contract = (
            build_question_form_contract(
                question_type=question_type,
                form=form,
            )
        )

        if question_type == AssessmentQuestionType.SINGLE_CHOICE and 'parts' in contract.content:
            # Validate each distinct uploaded image through the existing storage ACL.
            images = {}
            for part in contract.content['parts']:
                for segments in [part['segments'], *[option['segments'] for option in part['options']]]:
                    for segment in segments:
                        if segment.get('type') == 'image':
                            images[segment['object_key']] = segment
            await QuestionBankMediaService(get_storage()).validate_references(list(images.values()), user_id=user.id)
        if question_type == AssessmentQuestionType.IMAGE_CHOICE:
            await QuestionBankMediaService(get_storage()).validate_option_references(
                contract.content["options"], user_id=user.id,
            )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # =====================================================
    # 4. DTO
    # =====================================================

    data = TeacherQuestionBankUpdateDraftDTO(
        subject_id=subject_id,
        grade_level=grade_level,
        quarter=quarter,

        objective_id=objective_id,

        question_type=question_type,
        difficulty=difficulty,
        language=language,

        title=normalized_title,

        text=normalized_text,
        text_segments=text_segments,

        instruction=normalized_instruction,

        content=contract.content,
        answer_key=contract.answer_key,
        grading_settings=(
            contract.grading_settings
        ),

        max_score=max_score,

        explanation=normalized_explanation,
        author_comment=(
            normalized_author_comment
        ),
    )

    # =====================================================
    # 5. UPDATE
    # =====================================================

    try:
        await TeacherQuestionBankService.update_draft(
            db,
            user_id=user_id,
            staff_member_id=staff_member_id,
            item_id=item_id,
            data=data,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if form.get('after_save') == 'translate' and data.language.value in {'ru','kk'}:
        return RedirectResponse(request.url_for('teacher_question_languages',item_id=item_id),status_code=303)

    # =====================================================
    # 6. PRG -> DETAIL
    # =====================================================

    return RedirectResponse(
        url=request.url_for(
            "teacher_question_bank_item_detail_page",
            item_id=item_id,
        ),
        status_code=303,
    )


@router.get(
    "/items/{item_id}",
    name="teacher_question_bank_item_detail_page",
    response_class=HTMLResponse,
)
async def teacher_question_bank_item_detail_page(
        request: Request,
        item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_teacher_workspace),
):
    """
    Просмотр собственного QuestionBankItem учителя.
    """

    item = await TeacherQuestionBankService.get_detail(
        db,
        user_id=user.id,
        item_id=item_id,
    )

    if item is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Тапсырма табылмады немесе "
                "оған қол жеткізуге рұқсат жоқ."
            ),
        )

    return render(
        templates,
        request,
        "teacher/assessment/question_bank/detail.html",
        {
            "user": user,
            "item": item,
        },
    )


@router.post(
    "/items/{item_id}/submit-review",
    name="teacher_question_bank_item_submit_review",
)
async def teacher_question_bank_item_submit_review(
        request: Request,
        item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_teacher_workspace),
):
    """
    Отправляет собственное задание учителя
    на Human Review.

    Lifecycle:
        DRAFT -> REVIEW
    """

    try:
        await TeacherQuestionBankService.submit_for_review(
            db,
            user_id=user.id,
            item_id=item_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=request.url_for(
            "teacher_question_bank_item_detail_page",
            item_id=item_id,
        ),
        status_code=303,
    )


@router.post("/media/upload", name="teacher_question_bank_media_upload")
async def question_bank_media_upload(
    user: User = Depends(require_teacher_workspace),
    file: UploadFile = File(...),
):
    try:
        content = await file.read(MAX_IMAGE_BYTES + 1)
        return await QuestionBankMediaService(get_storage()).upload(content=content, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@router.get(
    "/media/view",
    name="teacher_question_bank_media_view",
    dependencies=[Depends(require_bank_reader)],
)
async def question_bank_media_view(
    object_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_bank_reader),
):
    if not MEDIA_KEY_PATTERN.fullmatch(object_key):
        raise HTTPException(
            status_code=400,
            detail="Суреттің сақтау кілті қате.",
        )

    from app.modules.users.enums import UserRole, UserWorkspace
    from app.modules.users.deps import resolve_workspace_context
    context = getattr(request.state, 'workspace_context', None) or await resolve_workspace_context(request=request, user=user, db=db)
    private_access = user.role in (UserRole.SUPERUSER, UserRole.TEACHER) or any(
        entry.code in (UserWorkspace.TEACHER, UserWorkspace.QUESTION_BANK_EXPERT) for entry in context.items)
    if not private_access and not object_key.startswith(f'question-bank/media/{user.id}/'):
        from sqlalchemy import select, or_
        from app.modules.assessment.models import QuestionBankItem
        ready_media = select(QuestionBankItem.id).where(
            QuestionBankItem.status == QuestionBankItemStatus.READY,
            or_(QuestionBankItem.text_segments.contains([{'object_key': object_key}]),
                QuestionBankItem.content.contains({'options':[{'object_key': object_key}]}))
        ).limit(1)
        if (await db.execute(ready_media)).scalar_one_or_none() is None:
            raise HTTPException(404, 'Изображение недоступно / Сурет қолжетімсіз.')
    storage = get_storage()

    if not await storage.exists(object_key=object_key):
        raise HTTPException(
            status_code=404,
            detail="Сурет табылмады.",
        )

    url = await storage.get_download_url(object_key=object_key)

    return RedirectResponse(
        url=url,
        status_code=307,
        headers={"Cache-Control": "no-store"},
    )
