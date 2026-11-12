"""Copy an approved language version into an independent draft Assessment snapshot.

No commits here: the web command owns the transaction. Lock the target first,
then all source tasks in ID order, so repeated/concurrent adds cannot duplicate.
"""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.modules.assessment.models import (Assessment, AssessmentQuestion, QuestionBankItem,
    QuestionBankItemObjective, QuestionBankLanguageVariant)
from app.modules.assessment.enums import (AssessmentStatus, AssessmentInputMode,
    AssessmentMode, AssessmentLanguage, QuestionBankItemStatus)
from app.modules.assessment.repositories.teacher_question_bank_repo import TeacherQuestionBankRepo
from app.modules.assessment.helpers.bilingual_question_contract import code, source_payload, fingerprint
from app.modules.assessment.services.bilingual_question_service import validate_payload
from app.modules.assessment.services.assessment_question_validation_service import AssessmentQuestionValidationService as Validator
from app.modules.assessment.services.bilingual_question_views import localized_view
from app.modules.assessment.repositories.learning_objective_formulation_repo import LearningObjectiveFormulationRepo as Formulations


class BankSelectionError(ValueError):
    """Stable localized UI message; technical validator details stay in logs."""


def normalize_language(value):
    if value not in ('ru', 'kk'):
        raise BankSelectionError('Выберите русский или казахский язык заданий.')
    return value


def choose_payload(item, language, variants):
    normalize_language(language)
    if code(item.status) != 'ready':
        raise BankSelectionError('Задание больше не доступно в банке проверенных заданий.')
    if code(item.language) == language:
        payload = source_payload(item)
    else:
        variant = variants.get((item.id, language))
        if variant is None:
            raise BankSelectionError('Нет проверенной версии на выбранном языке.')
        if variant.source_fingerprint != fingerprint(item):
            raise BankSelectionError('Перевод устарел. Требуется повторная проверка автора и эксперта.')
        try:
            validate_payload(item, variant.payload)
        except ValueError as exc:
            raise BankSelectionError('Версия задания не прошла техническую проверку.') from exc
        payload = deepcopy(variant.payload)
    # New bilingual items require a current counterpart even when using the source.
    if getattr(item, 'requires_bilingual', False):
        other = 'kk' if code(item.language) == 'ru' else 'ru'
        counterpart = variants.get((item.id, other))
        if counterpart is None or counterpart.source_fingerprint != fingerprint(item):
            raise BankSelectionError('Перевод устарел. Требуется повторная проверка автора и эксперта.')
        try:
            validate_payload(item, counterpart.payload)
        except ValueError as exc:
            raise BankSelectionError('Версия задания не прошла техническую проверку.') from exc
    try:
        Validator.validate_authoring(question_type=item.question_type, content=payload['content'],
            answer_key=payload['answer_key'], grading_settings=payload['grading_settings'], max_score=item.max_score)
    except ValueError as exc:
        raise BankSelectionError('Версия задания не прошла техническую проверку.') from exc
    return deepcopy(payload)


def snapshot_values(item, payload, language, assessment_id, order_no):
    content = deepcopy(payload['content'])
    content['_bank_source'] = dict(item_id=item.id, language=language,
        source_fingerprint=fingerprint(item), title=payload['title'],
        objective_ids=sorted(link.learning_objective_id for link in item.objectives),
        objectives=deepcopy(getattr(item, '_bank_objectives', [])), quarter=item.quarter)
    content['_statement_segments'] = deepcopy(payload['text_segments'])
    grading = deepcopy(payload['grading_settings'])
    # Teacher-only repository fields: never place solutions in student-facing content.
    grading['_bank_explanation'] = payload['explanation']
    grading['_bank_author_comment'] = payload['author_comment']
    return dict(assessment_id=assessment_id, question_type=item.question_type,
        text=payload['text'], instruction=payload['instruction'], max_score=item.max_score,
        order_no=order_no, content=content, answer_key=deepcopy(payload['answer_key']),
        grading_settings=grading, is_required=True, is_active=True)


def question_view(question, language):
    content = deepcopy(question.content)
    meta = content.pop('_bank_source', {})
    segments = content.pop('_statement_segments', [])
    grading = deepcopy(question.grading_settings)
    explanation = grading.pop('_bank_explanation', None)
    author_comment = grading.pop('_bank_author_comment', None)
    return SimpleNamespace(id=question.id, title=meta.get('title'), text=question.text,
        text_segments=segments, instruction=question.instruction, content=content,
        answer_key=question.answer_key, grading_settings=grading, explanation=explanation,
        author_comment=author_comment, max_score=question.max_score,
        language=AssessmentLanguage(language), question_type=question.question_type,
        bank_objectives=meta.get('objectives', []))


async def ensure_scope(db, staff_member_id, subject_id, grade_level):
    if not await TeacherQuestionBankRepo.has_teaching_scope(db, staff_member_id=staff_member_id,
            subject_id=subject_id, grade_level=grade_level):
        raise BankSelectionError('Нет доступа к выбранному предмету и классу.')


async def own_assessment(db, assessment_id, school_id, user_id, staff_member_id, *, lock=False):
    stmt = select(Assessment).where(Assessment.id == assessment_id,
        Assessment.school_id == school_id, Assessment.created_by_user_id == user_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    assessment = (await db.execute(stmt)).scalar_one_or_none()
    if assessment is None or assessment.settings.get('bank_builder_version') != 1:
        raise BankSelectionError('Черновик Assessment не найден или недоступен.')
    await ensure_scope(db, staff_member_id, assessment.subject_id, assessment.settings['bank_grade'])
    return assessment


def require_editable(assessment):
    if code(assessment.status) != 'draft' or code(assessment.input_mode) != 'online':
        raise BankSelectionError('Добавлять и удалять задания можно только в черновике Assessment.')


async def create_draft(db, *, school_id, user_id, staff_member_id, subject_id, grade_level, language, title):
    normalize_language(language)
    title = title.strip()
    if not title or len(title) > 255:
        raise BankSelectionError('Введите название Assessment длиной до 255 символов.')
    await ensure_scope(db, staff_member_id, subject_id, grade_level)
    assessment = Assessment(school_id=school_id, subject_id=subject_id, created_by_user_id=user_id,
        title=title, input_mode=AssessmentInputMode.ONLINE, status=AssessmentStatus.DRAFT,
        assessment_mode=AssessmentMode.WITHOUT_OBJECTIVES, max_score=None,
        settings=dict(bank_builder_version=1, bank_language=language, bank_grade=grade_level))
    db.add(assessment)
    await db.flush()
    return assessment.id


async def list_drafts(db, school_id, user_id):
    # Include non-drafts as read-only snapshots; no students or answer data returned.
    return list((await db.execute(select(Assessment).where(Assessment.school_id == school_id,
        Assessment.created_by_user_id == user_id,
        Assessment.settings['bank_builder_version'].as_integer() == 1)
        .order_by(Assessment.id.desc()).limit(100))).scalars().all())


async def saved_questions(db, assessment_id):
    return list((await db.execute(select(AssessmentQuestion).where(
        AssessmentQuestion.assessment_id == assessment_id)
        .order_by(AssessmentQuestion.order_no, AssessmentQuestion.id))).scalars().all())


async def load_items(db, subject_id, grade_level, *, ids=None, after=0, objective_quarters=None):
    stmt = select(QuestionBankItem).where(QuestionBankItem.subject_id == subject_id,
        QuestionBankItem.grade_level == grade_level, QuestionBankItem.status == QuestionBankItemStatus.READY)
    if ids is not None:
        stmt = stmt.where(QuestionBankItem.id.in_(ids))
    else:
        stmt = stmt.where(QuestionBankItem.id > after).limit(51)
    items = list((await db.execute(stmt.options(selectinload(QuestionBankItem.objectives)
        .selectinload(QuestionBankItemObjective.learning_objective))
        .order_by(QuestionBankItem.id))).scalars().all())
    forms = await Formulations.for_objectives(db, objective_ids=list({
        link.learning_objective_id for item in items for link in item.objectives}))
    for item in items:
        goals = []
        for link in sorted(item.objectives, key=lambda link: link.order_no):
            objective = link.learning_objective
            goal = dict(id=objective.id, code=objective.code)
            for lang in ['kz', 'ru']:
                effective_quarter=item.quarter if item.quarter is not None or objective_quarters is None else objective.quarter
                exact, segments = Formulations.display(forms.get(objective.id, []), quarter=effective_quarter, language=lang)
                # Do not silently substitute a formulation from a different quarter.
                goal['title_' + lang] = exact if forms.get(objective.id) else getattr(objective, 'title_' + lang, '')
                goal['segments_' + lang] = list(segments)
            goals.append(goal)
        item._bank_objectives = goals
    return items


async def load_variants(db, items):
    ids = [item.id for item in items]
    if not ids:
        return {}
    variants = (await db.execute(select(QuestionBankLanguageVariant).where(
        QuestionBankLanguageVariant.item_id.in_(ids)))).scalars().all()
    return {(v.item_id, v.language): v for v in variants}


async def catalog(db, assessment, *, after=0):
    items = await load_items(db, assessment.subject_id, assessment.settings['bank_grade'], after=after)
    next_after = items[49].id if len(items) > 50 else None
    items = items[:50]
    variants = await load_variants(db, items)
    language = assessment.settings['bank_language']
    rows = []
    for item in items:
        try:
            view = localized_view(item, choose_payload(item, language, variants), language)
            view.bank_objectives = getattr(item, '_bank_objectives', [])
            error = None
        except BankSelectionError as exc:
            view = None
            error = str(exc)
        rows.append(SimpleNamespace(id=item.id, view=view, error=error))
    return rows, next_after


async def add_from_bank(db, *, assessment_id, school_id, user_id, staff_member_id, item_ids):
    ids = sorted(set(item_ids))
    if not ids or len(ids) > 50 or any(type(i) is not int or i <= 0 for i in ids):
        raise BankSelectionError('Выберите от 1 до 50 заданий.')
    assessment = await own_assessment(db, assessment_id, school_id, user_id, staff_member_id, lock=True)
    require_editable(assessment)
    saved = await saved_questions(db, assessment.id)
    used = {q.content.get('_bank_source', {}).get('item_id') for q in saved}
    # All-or-nothing; repeated browser submission leaves the original snapshot intact.
    if used.intersection(ids):
        raise BankSelectionError('Некоторые задания уже добавлены. Обновите страницу.')
    # Source edits and review transitions use the same row locks.
    table = QuestionBankItem.__table__
    await db.execute(select(table.c.id).where(table.c.id.in_(ids)).order_by(table.c.id).with_for_update())
    items = await load_items(db, assessment.subject_id, assessment.settings['bank_grade'], ids=ids)
    if {item.id for item in items} != set(ids):
        raise BankSelectionError('Задание больше не доступно в банке проверенных заданий.')
    variants = await load_variants(db, items)
    language = normalize_language(assessment.settings['bank_language'])
    payloads = [(item, choose_payload(item, language, variants)) for item in items]
    order_no = max((q.order_no for q in saved), default=0)
    questions = [AssessmentQuestion(**snapshot_values(item, payload, language, assessment.id, order_no+i))
        for i, (item, payload) in enumerate(payloads, 1)]
    db.add_all(questions)
    assessment.max_score = sum((q.max_score for q in saved if q.is_active), Decimal(0)) + sum((q.max_score for q in questions), Decimal(0))
    await db.flush()


async def remove_question(db, *, assessment_id, school_id, user_id, staff_member_id, question_id):
    assessment = await own_assessment(db, assessment_id, school_id, user_id, staff_member_id, lock=True)
    require_editable(assessment)
    questions = await saved_questions(db, assessment.id)
    question = next((q for q in questions if q.id == question_id), None)
    if question is None:
        raise BankSelectionError('Задание Assessment не найдено.')
    await db.delete(question)
    total = sum((q.max_score for q in questions if q.id != question_id and q.is_active), Decimal(0))
    assessment.max_score = total or None
    await db.flush()
