"""Two-step assembly: verified availability, choice of variants, atomic snapshots."""
from collections import defaultdict
from copy import deepcopy
from types import SimpleNamespace as N
from app.modules.assessment.services import work_plan_service as work
from app.modules.assessment.repositories import work_plan_repo as repo
from app.modules.assessment.models_work_plans import AssessmentWorkPlanItem as Item
from app.modules.assessment.helpers.work_plan_rules import integer,item_profile,task_signature,available_quarters,WorkPlanError
from app.modules.assessment.helpers.bilingual_question_contract import code,fingerprint

MAX_SELECTION=50

def selected_ids(values):
    ids=list(dict.fromkeys(integer(v,1,2_147_483_647) for v in values))
    if not 1<=len(ids)<=MAX_SELECTION:raise WorkPlanError('Выберите от 1 до 50 заданий работы.')
    return ids

def existing_slots(plan,saved):
    from app.modules.assessment.helpers.work_plan_positions import position_rows
    return {p['slots'][1].bank_item_id:dict(p['slots']) for p in position_rows(plan,saved) if 1 in p['slots']}

async def load_checked(db,plan,ids):
    _,allowed=await work.goal_context(db,plan)
    sources=await work.bank.load_items(db,plan.curriculum_subject_id,plan.curriculum_grade,
        ids=ids,objective_quarters=available_quarters(plan)) if ids else []
    translations=await work.bank.load_variants(db,sources)
    result={}
    for source in sources:
        if not work.eligible(source,plan,allowed):continue
        try:payloads=work.payloads_for(source,plan,translations)
        except work.bank.BankSelectionError:continue
        result[source.id]=N(source=source,payloads=payloads,profile=item_profile(work.profile_row(source,payloads)),
            signature=task_signature(code(source.question_type),payloads))
    return result

async def inspect(db,plan,ids,saved):
    """Statuses are confirmed, never inferred from coarse SQL counts alone."""
    slots_by_seed=existing_slots(plan,saved)
    pairs=await repo.variant_pair_ids(db,plan,ids,[r.bank_item_id for r in saved])
    coarse=defaultdict(list)
    for pair in pairs:coarse[pair.reference_id].append(pair.candidate_id)
    matched_ids=[row.bank_item_id for seed in ids for row in slots_by_seed.get(seed,{}).values()]
    pool_ids=list(dict.fromkeys([*ids,*matched_ids,*(p.candidate_id for p in pairs)]))
    limited=pool_ids[:500]
    checked=await load_checked(db,plan,limited)
    used={r.bank_item_id for r in saved}
    used_signatures={task_signature(r.question_type,r.payloads) for r in saved}
    result={}
    for seed in ids:
        anchor=checked.get(seed);slots=slots_by_seed.get(seed,{})
        if anchor is None:
            result[seed]=N(state='blocked',count=0,choices=[],slots=slots,anchor=None,complete=False);continue
        if seed in used and not slots:
            result[seed]=N(state='used',count=0,choices=[],slots={},anchor=anchor,complete=True);continue
        if any(row.bank_item_id not in checked or fingerprint(checked[row.bank_item_id].source)!=row.source_fingerprint
            or checked[row.bank_item_id].payloads!=row.payloads for row in slots.values()):
            result[seed]=N(state='dirty',count=0,choices=[],slots=slots,anchor=anchor,complete=False);continue
        signatures={anchor.signature};choices=[]
        for candidate_id in coarse[seed][:40]:
            candidate=checked.get(candidate_id)
            if (candidate is None or candidate.profile!=anchor.profile or candidate_id in used
                or candidate.signature in used_signatures or candidate.signature in signatures):continue
            signatures.add(candidate.signature);choices.append(candidate)
        truncated=(len(coarse[seed])>40 or any(i not in checked and i not in limited for i in coarse[seed][:40]))
        count=len({r.bank_item_id for r in slots.values()}) if slots else 1
        count+=len(choices)
        complete=bool(slots) and len(slots)==plan.variant_count
        state=('complete' if complete else 'ready' if count>=plan.variant_count
            else 'check' if truncated else 'common' if count==1 else 'partial')
        result[seed]=N(state=state,count=count,choices=choices,slots=slots,anchor=anchor,complete=complete)
    return result

async def annotate(db,plan,rows,saved):
    statuses=await inspect(db,plan,[r.item.id for r in rows if not r.error],saved)
    for row in rows:row.availability=statuses.get(row.item.id,N(state='blocked',count=0,complete=False))
    return statuses

async def preview(db,user,plan_id,values,selection_mode='variants'):
    from app.modules.assessment.services.work_plan_position_service import ensure_unused
    plan=await work.own(db,user,plan_id);work.editable(plan);await ensure_unused(db,plan)
    if selection_mode not in ('variants','separate'):raise WorkPlanError('Выберите способ распределения карточек. / Карточкаларды бөлу тәсілін таңдаңыз.')
    ids=selected_ids(values);saved=await repo.items(db,plan.id)
    statuses=await inspect(db,plan,ids,saved)
    if any(statuses[i].state in ('blocked','dirty','used','complete') for i in ids):
        raise WorkPlanError('Некоторые выбранные задания недоступны или уже распределены. Измените выбор.')
    selected={i:statuses[i].anchor for i in ids}
    signatures={}
    for source_id,candidate in selected.items():
        if candidate.signature in signatures:
            raise WorkPlanError(f'Карточки №{signatures[candidate.signature]} и №{source_id} имеют одинаковое условие. Выберите одну. / Шарттары бірдей карточкалардың біреуін таңдаңыз.')
        signatures[candidate.signature]=source_id
    remaining=set(ids);reserved={r.bank_item_id for r in saved};families=[]
    for seed in ids:
        if seed not in remaining:continue
        remaining.remove(seed);reserved.add(seed)
        status=statuses[seed];anchor=status.anchor
        selected_choices=[selected[i] for i in ids if i!=seed and selected[i].profile==anchor.profile]
        pool={c.source.id:c for c in [*selected_choices,*status.choices]}
        choices=list(pool.values());assignments={};locked={};members=[seed];needs=0
        common_locked=len([r for r in saved if r.bank_item_id==seed])>1
        seen={anchor.signature}|{task_signature(r.question_type,r.payloads) for r in status.slots.values()}
        for variant in range(1,plan.variant_count+1):
            existing=status.slots.get(variant)
            if existing:
                assignments[variant]=existing.bank_item_id;locked[variant]=existing
                seen.add(task_signature(existing.question_type,existing.payloads))
            elif common_locked:assignments[variant]=seed
            elif variant==1:assignments[variant]=seed
            else:
                candidate=None
                if selection_mode=='variants':
                    candidate=next((c for c in selected_choices if c.source.id in remaining and c.source.id not in reserved and c.signature not in seen),None)
                if candidate is None:
                    candidate=next((c for c in status.choices if c.source.id not in ids and c.source.id not in reserved and c.signature not in seen),None)
                assignments[variant]=candidate.source.id if candidate else None
                if candidate:
                    reserved.add(candidate.source.id);seen.add(candidate.signature)
                    if candidate.source.id in remaining:remaining.remove(candidate.source.id);members.append(candidate.source.id)
                else:needs+=1
        common_blocked=any(r.bank_item_id!=seed for r in locked.values())
        families.append(N(seed=seed,source=anchor.source,payloads=anchor.payloads,choices=choices,
            assignments=assignments,locked=locked,members=members,needs=needs,can_common=not common_blocked,
            common_locked=common_locked,common=common_locked or (not common_blocked and any(r.is_shared for r in locked.values())),status=status))
    if len(saved)+sum(plan.variant_count-len(f.locked) for f in families)>200:
        raise WorkPlanError('Распределение превышает 200 карточек в комплекте. Уменьшите выбор. / Бөлу жинақтағы 200 карточка шегінен асады. Таңдауды азайтыңыз.')
    # Anchors are fixed in variant 1. They cannot also be selected for another row.
    anchors={f.seed for f in families}
    for family in families:family.choices=[c for c in family.choices if c.source.id not in anchors]
    return plan,saved,families

async def assemble(db,user,plan_id,values,common_values,choices,*,expected_revision=None):
    plan=await work.own(db,user,plan_id,True);work.editable(plan)
    ids=selected_ids(values);common=set(integer(v,1,2_147_483_647) for v in common_values)
    if not common<=set(ids):raise WorkPlanError('Проверьте распределение заданий по вариантам.')
    saved=await repo.items(db,plan.id)
    if expected_revision is not None:
        from app.modules.assessment.helpers.work_plan_positions import composition_revision
        from app.modules.assessment.services.work_plan_position_service import CompositionChanged
        if expected_revision!=composition_revision(plan,saved):raise CompositionChanged('Состав изменился. Проверьте распределение заново. / Құрам өзгерді. Бөлуді қайта тексеріңіз.')
    slots=existing_slots(plan,saved)
    mapping={};all_ids=set(ids)
    for seed in ids:
        mapping[seed]={}
        for variant in range(1,plan.variant_count+1):
            raw=seed if seed in common or variant==1 else choices.get((seed,variant))
            if raw in (None,''):raise WorkPlanError('Выберите карточку для каждого варианта или отметьте задание как общее.')
            selected=integer(raw,1,2_147_483_647);mapping[seed][variant]=selected;all_ids.add(selected)
    if len(all_ids)>200:raise WorkPlanError('В комплекте допускается не более 200 карточек.')
    await repo.lock_bank(db,sorted(all_ids))
    checked=await load_checked(db,plan,sorted(all_ids))
    if set(checked)!=all_ids:raise WorkPlanError('Некоторые выбранные задания недоступны или уже распределены. Измените выбор.')
    used={r.bank_item_id for r in saved}
    signatures=defaultdict(set)
    for row in saved:signatures[task_signature(row.question_type,row.payloads)].add(row.bank_item_id)
    assigned={};pending=[];flag_updates=[]
    orders={v:max((r.order_no for r in saved if r.variant_no==v),default=0) for v in range(1,plan.variant_count+1)}
    for seed in ids:
        anchor=checked[seed];existing=slots.get(seed,{})
        if seed in used and not existing:raise WorkPlanError('Проверьте распределение заданий по вариантам.')
        copies=[r for r in saved if r.bank_item_id==seed]
        if len(copies)>1 and seed not in common:
            raise WorkPlanError('Сначала уберите повторные копии задания из других вариантов, затем снимите отметку общего задания.')
        for variant,selected in mapping[seed].items():
            candidate=checked[selected];row=existing.get(variant)
            if candidate.profile!=anchor.profile:raise WorkPlanError('Карточки вариантов должны совпадать по целям, типу, сложности и баллам.')
            if row is not None and row.bank_item_id!=selected:
                raise WorkPlanError('В этом месте уже сохранено другое задание. Сначала уберите его из состава работы.')
            if row is not None:
                if fingerprint(candidate.source)!=row.source_fingerprint or candidate.payloads!=row.payloads:
                    raise WorkPlanError('Задание банка изменилось или стало недоступно. Удалите его из комплекта и выберите заново.')
                if selected==seed:flag_updates.append((row,seed in common))
                continue
            if selected in used and not (seed in common and selected==seed):
                raise WorkPlanError('Одна карточка выбрана для разных заданий работы. Измените распределение.')
            owner=assigned.get(selected)
            if owner is not None and not (owner==seed and seed in common):
                raise WorkPlanError('Одна карточка выбрана для разных заданий работы. Измените распределение.')
            signature=candidate.signature
            if signatures[signature] and not (seed in common and selected==seed and signatures[signature]=={seed}):
                raise WorkPlanError('Такое условие уже есть в комплекте. Перемешивание вариантов ответа не создаёт другое задание.')
            assigned[selected]=seed;signatures[signature].add(selected);orders[variant]+=1
            objectives=deepcopy(copies[0].objectives if copies and seed in common else candidate.source._bank_objectives)
            pending.append(Item(work_plan_id=plan.id,bank_item_id=selected,variant_no=variant,order_no=orders[variant],
                question_type=code(candidate.source.question_type),difficulty=code(candidate.source.difficulty),
                max_score=candidate.source.max_score,is_shared=seed in common,
                source_fingerprint=fingerprint(candidate.source),objectives=objectives,payloads=deepcopy(candidate.payloads)))
    if len(saved)+len(pending)>200:raise WorkPlanError('В комплекте допускается не более 200 карточек.')
    for row,flag in flag_updates:row.is_shared=flag
    db.add_all(pending);await db.flush()
    work.validate_shared_copies([*saved,*pending])
