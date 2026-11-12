"""Explicit assignment, with a preview before commit and an immutable source plan."""
from collections import Counter
from secrets import choice
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError, integer, participant_language, completeness
from app.modules.assessment.helpers.work_plan_presentation import title_values
from app.modules.assessment.repositories import work_plan_repo as plans
from app.modules.assessment.repositories import work_plan_assignment_repo as repo
from app.modules.assessment.models_work_assignments import AssessmentWorkAssignment as Assignment, AssessmentWorkParticipant as Participant
from app.modules.assessment.services import work_plan_service as works
has_assignments = repo.has_assignments

async def preview(db, user, plan_id, year, class_ids, lock=False):
    plan = await works.own(db,user,plan_id,lock)
    if plan.status != 'prepared': raise WorkPlanError('Сначала проверьте и подготовьте комплект.')
    title_values({'title_kk':plan.title_kk or '', 'title_ru':plan.title_ru or ''},plan.language_policy)
    year = integer(year,2000,2100)
    if plan.academic_year_start is not None and plan.academic_year_start!=year:
        raise WorkPlanError('Учебный год комплекта и проведения не совпадает. / Жинақ пен өткізу оқу жылы сәйкес емес.')
    ids = sorted({integer(value,1,2147483647) for value in class_ids})
    if not 1 <= len(ids) <= 100: raise WorkPlanError('Выберите от 1 до 100 классов.')
    valid = await repo.selected_class_ids(db,plan,year,ids,lock)
    if valid != set(ids): raise WorkPlanError('Класс не соответствует области, параллели или направлению комплекта.')
    rows = await repo.enrolled(db,plan,year,ids,lock)
    if len(rows)>5000: raise WorkPlanError('За один раз можно назначить работу не более 5000 ученикам.')
    if len({r.student_id for r in rows}) != len(rows): raise WorkPlanError('У ученика несколько активных зачислений. Исправьте список классов.')
    existing = await repo.existing_students(db,plan.id,[r.student_id for r in rows])
    fresh = [r for r in rows if r.student_id not in existing]
    if not fresh: raise WorkPlanError('Нет новых участников: классы пусты или работа уже назначена этим ученикам.')
    items = await plans.items(db,plan.id)
    if completeness(plan,items): raise WorkPlanError('Структура вариантов комплекта не завершена.')
    languages = {lang for i in items for lang in i.payloads}
    for row in fresh:
        if plan.language_policy in ('auto','both') and row.instruction_language not in ('kz','ru','uz','ug','tg'):
            raise WorkPlanError('Укажите язык обучения у всех выбранных классов.')
        language = participant_language(plan.language_policy,row.instruction_language)
        if language not in languages or any(language not in i.payloads for i in items):
            raise WorkPlanError('Нет сохранённой версии на выбранном языке.')
    return plan,year,ids,fresh,len(rows)-len(fresh)

def roster_digest(rows):
    import json
    from hashlib import sha256
    values=[(r.student_id,r.class_id,r.school_id,r.instruction_language,r.last_name,r.first_name,r.middle_name) for r in rows]
    return sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

async def assign(db,user,plan_id,year,class_ids,expected_digest):
    plan,year,ids,rows,_skipped = await preview(db,user,plan_id,year,class_ids,True)
    if not expected_digest or expected_digest != roster_digest(rows):
        raise WorkPlanError('Список участников изменился. Проверьте назначение ещё раз.')
    counts = Counter({(r.school_class_id,r.variant_no):r.total for r in await repo.variant_counts(db,plan.id,ids)})
    batch = Assignment(work_plan_id=plan.id,created_by_user_id=user.id,academic_year_start=year)
    db.add(batch); await db.flush()
    for row in rows:
        # Balanced inside each class; ties randomized rather than assigning all pupils variant 1.
        lowest=min(counts[(row.class_id,v)] for v in range(1,plan.variant_count+1))
        variant=choice([v for v in range(1,plan.variant_count+1) if counts[(row.class_id,v)]==lowest])
        counts[(row.class_id,variant)]+=1
        db.add(Participant(assignment_id=batch.id,work_plan_id=plan.id,student_id=row.student_id,
            school_id=row.school_id,school_class_id=row.class_id,
            full_name=' '.join(str(s).strip() for s in (row.last_name,row.first_name,row.middle_name) if s),
            school_name=row.school_name[:255],class_label=f'{row.grade_level}{row.letter}'[:32],
            language=participant_language(plan.language_policy,row.instruction_language),variant_no=variant))
    await db.flush()
    return batch
