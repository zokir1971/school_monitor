"""Prepare reusable school/district/region work sets without starting execution."""
from dataclasses import asdict
from collections import Counter
from decimal import Decimal
from copy import deepcopy
from types import SimpleNamespace
from app.modules.assessment.models_work_plans import AssessmentWorkPlan as Plan, AssessmentWorkPlanItem as Item
from app.modules.assessment.repositories import work_plan_repo as repo
from app.modules.assessment.repositories.teacher_question_bank_repo import TeacherQuestionBankRepo as Bank
from app.modules.assessment.services import assessment_bank_service as bank
from app.modules.assessment.helpers.work_plan_rules import (WorkPlanError,parse_parameters,required_languages,integer,completeness,task_signature,item_profile,available_quarters,source_quarter_value,item_quarter_allowed)
from app.modules.assessment.helpers.bilingual_question_contract import fingerprint,code

async def own(db,user,plan_id,lock=False):
    plan=await repo.owned(db,user.id,plan_id,lock)
    if plan is None: raise WorkPlanError('Комплект не найден или недоступен.')
    options=await repo.scope_options(db,user)
    key=(plan.scope_kind,getattr(plan,plan.scope_kind+'_id'))
    scope=next((r for r in options if (r['kind'],r['id'])==key),None)
    if scope is None: raise WorkPlanError('Комплект не найден или недоступен.')
    plan._scope_name=scope['name']
    return plan

def editable(plan):
    if plan.status!='draft': raise WorkPlanError('Подготовленный комплект закрыт для изменения.')

async def create(db,user,values):
    params=parse_parameters({**values,'title':'auto'})
    options=await repo.scope_options(db,user)
    scope=next((r for r in options if r['value']==values.get('scope')),None)
    if scope is None: raise WorkPlanError('Выберите доступную область проведения.')
    subjects={s.id:s for s in await repo.subjects(db)}
    available=set(subjects)
    if params.subject_id not in available or params.curriculum_subject_id not in available:
        raise WorkPlanError('Выберите действующий предмет.')
    from app.modules.assessment.helpers.assessment_names import names as standard_names
    year=integer(values.get('academic_year_start'),2000,2100)
    number=integer(values.get('section_number'),1,99) if params.work_type=='sor' and values.get('section_number') else None
    subject=subjects[params.subject_id]
    names=standard_names(kind=params.work_type,subject_kk=subject.name_kz,subject_ru=subject.name_ru,
        grades=[params.participant_grade],year=year,quarter=params.quarter,track=params.education_track,number=number)
    params_dict=asdict(params);params_dict['title']=names['ru']
    plan=Plan(**params_dict,title_kk=names['kk'],title_ru=names['ru'],academic_year_start=year,section_number=number,
        description=str(values.get('description') or '').strip() or None,created_by_user_id=user.id,scope_kind=scope['kind'],
        **{scope['kind']+'_id':scope['id']},status='draft')
    db.add(plan);await db.flush();return plan

async def goals(db,plan):
    track='' if plan.education_track=='general' else plan.education_track
    return await Bank.list_learning_objectives(db,subject_id=plan.curriculum_subject_id,
        grade_level=plan.curriculum_grade,quarter=None,quarters=available_quarters(plan),education_track=track)

async def goal_context(db,plan):
    rows=await goals(db,plan)
    return rows,{r.learning_objective_id for r in rows}

def eligible(item,plan,allowed):
    ids={o.learning_objective_id for o in item.objectives}
    return (item.subject_id==plan.curriculum_subject_id and item.grade_level==plan.curriculum_grade
        and bool(ids) and ids<=allowed and code(item.status)=='ready'
        and item_quarter_allowed(item,plan))

def payloads_for(item,plan,variants):
    languages=required_languages(plan.language_policy)
    if any(lang!=code(item.language) and (item.id,lang) not in variants for lang in languages):
        raise bank.BankSelectionError('Нет проверенной версии на выбранном языке.')
    return {lang:bank.choose_payload(item,lang,variants) for lang in required_languages(plan.language_policy)}

def quarter_label(item):
    if item.quarter is not None:return str(item.quarter)
    quarters={getattr(getattr(link,'learning_objective',None),'quarter',None) for link in item.objectives}
    return ', '.join(str(q) for q in sorted(q for q in quarters if q is not None)) or '—'

async def candidates(db,plan,offset=0,objective_id=None,source_quarter=None):
    source_quarter=source_quarter_value(plan,source_quarter)
    offset=integer(offset,0,1_000_000)
    if offset%20: raise WorkPlanError('Некорректная страница каталога.')
    goal_rows,allowed=await goal_context(db,plan)
    if objective_id is not None and objective_id not in allowed: raise WorkPlanError('Учебная цель не относится к проверяемой программе.')
    rows=await Bank.list_catalog_items(db,subject_id=plan.curriculum_subject_id,grade_level=plan.curriculum_grade,
        objective_id=objective_id,objective_ids=sorted(allowed),quarter=source_quarter,
        quarters=[source_quarter] if source_quarter is not None else available_quarters(plan),limit=21,offset=offset)
    has_next=len(rows)>20;ids=[r.item_id for r in rows[:20]]
    items=await bank.load_items(db,plan.curriculum_subject_id,plan.curriculum_grade,ids=ids,objective_quarters=available_quarters(plan)) if ids else []
    variants=await bank.load_variants(db,items)
    result=[]
    for item in items:
        error=None
        if not eligible(item,plan,allowed): error='Учебные цели задания не соответствуют проверяемой программе.'
        else:
            try: payloads_for(item,plan,variants)
            except bank.BankSelectionError as exc: error=str(exc)
        result.append(SimpleNamespace(item=item,error=error,quarter_label=quarter_label(item)))
    return goal_rows,result,has_next

def profile_row(item,payloads):
    return SimpleNamespace(objectives=item._bank_objectives,question_type=code(item.question_type),
        difficulty=code(item.difficulty),max_score=item.max_score,payloads=payloads)

async def annotate_alternatives(db,plan,rows,saved):
    # One aggregate query for all visible rows; never one query per card.
    ids=[r.item.id for r in rows if not r.error]
    counts=await repo.alternative_counts(db,plan,ids,[i.bank_item_id for i in saved])
    for row in rows:
        row.alternative_count=counts.get(row.item.id,0) if not row.error else None

async def alternatives(db,plan,reference_id,saved,after=0):
    reference_id=integer(reference_id,1,2_147_483_647)
    after=integer(after,0,2_147_483_647)
    goal_rows,allowed=await goal_context(db,plan)
    sources=await bank.load_items(db,plan.curriculum_subject_id,plan.curriculum_grade,ids=[reference_id],objective_quarters=available_quarters(plan))
    if not sources or not eligible(sources[0],plan,allowed):
        raise WorkPlanError('Исходная карточка недоступна для подбора вариантов.')
    reference=sources[0]
    reference_variants=await bank.load_variants(db,sources)
    try: reference_payloads=payloads_for(reference,plan,reference_variants)
    except bank.BankSelectionError as exc: raise WorkPlanError(str(exc)) from exc
    profile=item_profile(profile_row(reference,reference_payloads))
    signatures={task_signature(i.question_type,i.payloads) for i in saved}
    signatures.add(task_signature(code(reference.question_type),reference_payloads))
    ids=await repo.alternative_ids(db,plan,reference_id,[i.bank_item_id for i in saved],after)
    batch=ids[:100]
    items=await bank.load_items(db,plan.curriculum_subject_id,plan.curriculum_grade,ids=batch,objective_quarters=available_quarters(plan)) if batch else []
    variants=await bank.load_variants(db,items)
    by_id={item.id:item for item in items}
    rows=[];checked=0;next_after=None
    for item_id in batch:
        checked+=1
        item=by_id.get(item_id)
        if item is not None and eligible(item,plan,allowed):
            try:
                payloads=payloads_for(item,plan,variants)
                compatible=(item_profile(profile_row(item,payloads))==profile
                    and task_signature(code(item.question_type),payloads) not in signatures)
            except bank.BankSelectionError: compatible=False
            if compatible:
                signatures.add(task_signature(code(item.question_type),payloads))
                rows.append(SimpleNamespace(item=item,error=None,alternative_count=None,quarter_label=quarter_label(item)))
        if len(rows)==20:break
    if checked and (checked<len(batch) or len(ids)>100): next_after=batch[checked-1]
    return goal_rows,rows,dict(reference=reference,checked=checked,next_after=next_after,after=after)

async def add(db,user,plan_id,variant_no,item_ids):
    plan=await own(db,user,plan_id,True);editable(plan)
    variant_no=integer(variant_no,1,plan.variant_count)
    ids=sorted({integer(x,1,2_147_483_647) for x in item_ids})
    if not 1<=len(ids)<=20: raise WorkPlanError('Выберите от 1 до 20 заданий.')
    saved=await repo.items(db,plan.id)
    if len(saved)+len(ids)>200: raise WorkPlanError('В комплекте допускается не более 200 карточек.')
    existing={i.bank_item_id:[row for row in saved if row.bank_item_id==i.bank_item_id] for i in saved}
    for source_id in ids:
        copies=existing.get(source_id,[])
        if any(row.variant_no==variant_no for row in copies):
            raise WorkPlanError('Задание уже добавлено в этот вариант.')
        if copies and not all(row.is_shared for row in copies):
            raise WorkPlanError('Задание уже используется в одном из вариантов. Сначала отметьте его как общее.')
    await repo.lock_bank(db,ids)
    sources=await bank.load_items(db,plan.curriculum_subject_id,plan.curriculum_grade,ids=ids,objective_quarters=available_quarters(plan))
    if {i.id for i in sources}!=set(ids): raise WorkPlanError('Некоторые задания больше не доступны в банке готовых заданий.')
    _,allowed=await goal_context(db,plan)
    variants=await bank.load_variants(db,sources)
    signatures={}
    for row in saved:
        signatures.setdefault(task_signature(row.question_type,row.payloads),set()).add(row.bank_item_id)
    order=max((i.order_no for i in saved if i.variant_no==variant_no),default=0)
    for no,item in enumerate(sources,1):
        if not eligible(item,plan,allowed): raise WorkPlanError('Учебные цели задания не соответствуют проверяемой программе.')
        try: payloads=payloads_for(item,plan,variants)
        except bank.BankSelectionError as exc: raise WorkPlanError(str(exc)) from exc
        signature=task_signature(code(item.question_type),payloads)
        copies=existing.get(item.id,[])
        shared=bool(copies) and all(row.is_shared for row in copies)
        if signature in signatures and not (shared and signatures[signature]=={item.id}):
            raise WorkPlanError('Такое условие уже есть в комплекте. Перемешивание вариантов ответа не создаёт другое задание.')
        if copies and (fingerprint(item)!=copies[0].source_fingerprint or payloads!=copies[0].payloads):
            raise WorkPlanError('Общее задание изменилось в банке. Удалите старые копии из комплекта и выберите заново.')
        signatures.setdefault(signature,set()).add(item.id)
        objectives=deepcopy(copies[0].objectives if shared else item._bank_objectives)
        db.add(Item(work_plan_id=plan.id,bank_item_id=item.id,variant_no=variant_no,order_no=order+no,
            question_type=code(item.question_type),difficulty=code(item.difficulty),max_score=item.max_score,
            source_fingerprint=fingerprint(item),objectives=objectives,payloads=payloads,is_shared=shared))
    await db.flush()

async def set_shared(db,user,plan_id,bank_item_id,enabled):
    plan=await own(db,user,plan_id,True);editable(plan)
    if enabled not in ('0','1'):raise WorkPlanError('Некорректная отметка общего задания.')
    copies=[i for i in await repo.items(db,plan.id) if i.bank_item_id==bank_item_id]
    if not copies:raise WorkPlanError('Задание не найдено в комплекте.')
    if enabled=='0' and len(copies)>1:
        raise WorkPlanError('Сначала уберите повторные копии задания из других вариантов, затем снимите отметку общего задания.')
    for row in copies:row.is_shared=enabled=='1'
    await db.flush()

def validate_shared_copies(items):
    by_source={}
    for row in items:by_source.setdefault(row.bank_item_id,[]).append(row)
    for copies in by_source.values():
        if len(copies)<2:continue
        first=copies[0]
        if (not all(row.is_shared for row in copies)
            or len({row.variant_no for row in copies})!=len(copies)
            or any((row.payloads,row.objectives,row.source_fingerprint,row.question_type,row.difficulty,row.max_score)
                !=(first.payloads,first.objectives,first.source_fingerprint,first.question_type,first.difficulty,first.max_score) for row in copies)):
            raise WorkPlanError('Повторные карточки должны быть отмечены как общие и иметь одинаковое содержание и баллы.')

async def remove(db,user,plan_id,item_id):
    plan=await own(db,user,plan_id,True);editable(plan)
    row=next((i for i in await repo.items(db,plan.id) if i.id==item_id),None)
    if row is None: raise WorkPlanError('Задание не найдено в комплекте.')
    await db.delete(row);await db.flush()

async def prepare(db,user,plan_id):
    plan=await own(db,user,plan_id,True);editable(plan)
    from app.modules.assessment.helpers.work_plan_presentation import title_values
    title_values({'title_kk':plan.title_kk or '', 'title_ru':plan.title_ru or ''},plan.language_policy)
    saved=await repo.items(db,plan.id)
    if completeness(plan,saved): raise WorkPlanError('Заполните все варианты и выровняйте учебные цели, типы, сложность и баллы относительно варианта 1.')
    validate_shared_copies(saved)
    ids=sorted({i.bank_item_id for i in saved})
    await repo.lock_bank(db,ids)
    sources=await bank.load_items(db,plan.curriculum_subject_id,plan.curriculum_grade,ids=ids,objective_quarters=available_quarters(plan))
    by_id={s.id:s for s in sources};variants=await bank.load_variants(db,sources)
    _,allowed=await goal_context(db,plan)
    for row in saved:
        source=by_id.get(row.bank_item_id)
        if source is None or not eligible(source,plan,allowed) or fingerprint(source)!=row.source_fingerprint:
            raise WorkPlanError('Задание банка изменилось или стало недоступно. Удалите его из комплекта и выберите заново.')
        try: current=payloads_for(source,plan,variants)
        except bank.BankSelectionError as exc: raise WorkPlanError(str(exc)) from exc
        if current!=row.payloads: raise WorkPlanError('Перевод задания изменился. Удалите задание из комплекта и выберите заново.')
    plan.status='prepared';await db.flush()

async def reopen(db,user,plan_id):
    plan=await own(db,user,plan_id,True)
    from app.modules.assessment.services.work_plan_assignment_service import has_assignments
    if await has_assignments(db,plan.id):
        raise WorkPlanError('Комплект уже назначен участникам. Изменять его нельзя; создайте новый комплект.')
    plan.status='draft';await db.flush()

async def delete_draft(db,user,plan_id):
    plan=await own(db,user,plan_id,True);editable(plan)
    from app.modules.assessment.services.work_plan_position_service import ensure_unused
    await ensure_unused(db,plan)
    await db.delete(plan);await db.flush()


def grouped(plan,items):
    issues=completeness(plan,items)
    reference=[i for i in items if i.variant_no==1]
    reference_counts=Counter(item_profile(i) for i in reference)
    reference_rows={item_profile(i):i for i in reference}
    result=[]
    def describe(counts,by_profile):
        return [dict(count=count,goal_codes=', '.join(g['code'] for g in by_profile[profile].objectives),
            question_type=by_profile[profile].question_type,difficulty=by_profile[profile].difficulty,
            max_score=by_profile[profile].max_score) for profile,count in counts.items()]
    for variant in range(1,plan.variant_count+1):
        from app.modules.assessment.helpers.work_plan_presentation import ordered_items
        rows=ordered_items([i for i in items if i.variant_no==variant])
        counts=Counter(item_profile(i) for i in rows)
        by_profile={item_profile(i):i for i in rows}
        result.append(dict(no=variant,items=rows,total=sum((i.max_score for i in rows),Decimal(0)),
            issues=[reason for reason,no in issues if no==variant],
            missing=describe(reference_counts-counts,reference_rows) if reference else [],
            extra=describe(counts-reference_counts,by_profile) if reference else []))
    return result

async def standardize_name(db,plan,values):
    from app.modules.assessment.helpers.assessment_names import names as standard_names
    subject=next((s for s in await repo.subjects(db) if s.id==plan.subject_id),None)
    if subject is None:raise WorkPlanError('Выберите действующий предмет.')
    year=integer(values.get('academic_year_start'),2000,2100)
    number=integer(values.get('section_number'),1,99) if plan.work_type=='sor' and values.get('section_number') else None
    names=standard_names(kind=plan.work_type,subject_kk=subject.name_kz,subject_ru=subject.name_ru,
        grades=[plan.participant_grade],year=year,quarter=plan.quarter,track=plan.education_track,number=number)
    plan.academic_year_start=year;plan.section_number=number
    plan.description=str(values.get('description') or '').strip() or None
    plan.title_kk=names['kk'];plan.title_ru=names['ru'];plan.title=names['ru']
