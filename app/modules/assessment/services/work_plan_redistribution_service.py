"""Reviewed conversion of complete shared-card pools to distinct variant positions."""
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import json
from sqlalchemy import delete
from app.modules.assessment.models_work_plans import AssessmentWorkPlanItem as Item
from app.modules.assessment.services import work_plan_service as work,work_plan_builder_service as builder,work_plan_position_service as positions
from app.modules.assessment.repositories import work_plan_repo as repo
from app.modules.assessment.helpers.work_plan_positions import position_rows,composition_revision
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,task_signature
from app.modules.assessment.helpers.bilingual_question_contract import fingerprint


async def proposal(db,user,plan_id,lock=False):
    plan=await work.own(db,user,plan_id,lock);work.editable(plan);await positions.ensure_unused(db,plan)
    saved=await repo.items(db,plan.id);work.validate_shared_copies(saved)
    matrix=position_rows(plan,saved)
    common=[p for p in matrix if p['common'] and not p['missing']]
    ids=[p['anchor'].bank_item_id for p in common]
    if lock and ids:await repo.lock_bank(db,sorted(ids))
    checked=await builder.load_checked(db,plan,ids)
    pools=defaultdict(list);notes=[dict(id=p['anchor'].bank_item_id,reason='incomplete') for p in matrix if p['common'] and p['missing']]
    for p in common:
        row=p['anchor'];candidate=checked.get(row.bank_item_id)
        if candidate is None:
            notes.append(dict(id=row.bank_item_id,reason='unavailable'));continue
        if any(fingerprint(candidate.source)!=copy.source_fingerprint or candidate.payloads!=copy.payloads for copy in p['slots'].values()):
            notes.append(dict(id=row.bank_item_id,reason='changed'));continue
        pools[p['profile']].append(p)
    groups=[]
    for pool in pools.values():
        pending=list(pool)
        while pending:
            chosen=[];seen=set()
            for p in pending:
                signature=task_signature(p['anchor'].question_type,p['anchor'].payloads)
                if signature in seen:continue
                chosen.append(p);seen.add(signature)
                if len(chosen)==plan.variant_count:break
            if len(chosen)<plan.variant_count:
                notes.extend(dict(id=p['anchor'].bank_item_id,reason='insufficient') for p in pending);break
            chosen_ids={p['key'] for p in chosen}
            groups.append(dict(key=str(chosen[0]['anchor'].bank_item_id),anchor=chosen[0]['anchor'],positions=chosen,
                variants={v:p['slots'][v] for v,p in enumerate(chosen,1)},
                sources=[p['anchor'].bank_item_id for p in chosen],
                reduction=Decimal(chosen[0]['anchor'].max_score)*(plan.variant_count-1)))
            pending=[p for p in pending if p['key'] not in chosen_ids]
    totals={v:sum((Decimal(r.max_score) for r in saved if r.variant_no==v),Decimal(0)) for v in range(1,plan.variant_count+1)}
    reduction=sum((g['reduction'] for g in groups),Decimal(0))
    token=sha256(json.dumps(dict(version=1,revision=composition_revision(plan,saved),groups=[g['sources'] for g in groups],notes=notes),sort_keys=True).encode()).hexdigest()
    return dict(plan=plan,saved=saved,groups=groups,notes=notes,totals=totals,
        after={v:total-reduction for v,total in totals.items()},proposal_token=token)


async def apply(db,user,plan_id,group_keys,token):
    data=await proposal(db,user,plan_id,True)
    if token!=data['proposal_token']:raise positions.CompositionChanged('Состав или доступность карточек изменились. Откройте предложение заново. / Құрам немесе карточкалардың қолжетімділігі өзгерді. Ұсынысты қайта ашыңыз.')
    keys=list(group_keys);allowed={g['key']:g for g in data['groups']}
    if not keys or len(keys)!=len(set(keys)) or not set(keys)<=set(allowed):raise WorkPlanError('Выберите позиции из предложения. / Ұсыныстағы позицияларды таңдаңыз.')
    remove_ids=set();keep=[]
    for key in keys:
        group=allowed[key]
        retained={r.id for r in group['variants'].values()};keep.extend(group['variants'].values())
        remove_ids.update(r.id for p in group['positions'] for r in p['slots'].values() if r.id not in retained)
    await db.execute(delete(Item).where(Item.work_plan_id==plan_id,Item.id.in_(remove_ids)))
    for row in keep:row.is_shared=False
    remaining=[r for r in data['saved'] if r.id not in remove_ids]
    await positions.renumber(db,data['plan'],remaining)
    work.validate_shared_copies(remaining)
    return len(keys)
