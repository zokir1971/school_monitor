"""Deterministic parameter-compatible positions, with explicit shared-card priority.
Legacy plans have no persisted family ID: repeated profiles are labelled as inferred.
"""
from collections import Counter,defaultdict
from hashlib import sha256
import json
from app.modules.assessment.helpers.work_plan_rules import item_profile,WorkPlanError
from app.modules.assessment.helpers.work_plan_presentation import ordered_items


def composition_revision(plan,items):
    values=[dict(id=i.id,variant=i.variant_no,order=i.order_no,source=i.bank_item_id,
        shared=i.is_shared,kind=i.question_type,difficulty=i.difficulty,score=str(i.max_score),
        objectives=i.objectives,payloads=i.payloads,fingerprint=i.source_fingerprint) for i in sorted(items,key=lambda x:x.id)]
    data=dict(version=1,plan=plan.id,status=plan.status,variants=plan.variant_count,items=values)
    return sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def position_rows(plan,items):
    if any(not 1<=r.variant_no<=plan.variant_count for r in items):raise WorkPlanError('Проверьте количество вариантов комплекта. / Жинақ нұсқаларының санын тексеріңіз.')
    ordered=ordered_items(items);profiles={r.id:item_profile(r) for r in ordered}
    by_source=defaultdict(list);counts=Counter((r.variant_no,profiles[r.id]) for r in ordered)
    numbers={}
    for v in range(1,plan.variant_count+1):
        for no,r in enumerate([r for r in ordered if r.variant_no==v],1):numbers[r.id]=no
    for r in ordered:by_source[r.bank_item_id].append(r)
    taken=set();result=[]
    def append(slots,explicit=False):
        anchor=slots.get(1) or slots[min(slots)]
        taken.update(r.id for r in slots.values())
        result.append(dict(key=anchor.id,anchor=anchor,slots=slots,profile=profiles[anchor.id],
            missing=[v for v in range(1,plan.variant_count+1) if v not in slots],
            common=all(r.is_shared for r in slots.values()) and len({r.bank_item_id for r in slots.values()})==1,
            inferred=not explicit and any(counts[v,profiles[anchor.id]]>1 for v in range(1,plan.variant_count+1)),
            print_numbers={v:numbers[r.id] for v,r in slots.items()}))
    # Reserve same-source shared copies before pairing interchangeable profiles.
    for copies in by_source.values():
        if len(copies)>1 and all(r.is_shared for r in copies) and len({r.variant_no for r in copies})==len(copies) and len({profiles[r.id] for r in copies})==1:
            append({r.variant_no:r for r in copies},True)
    def pair(anchor):
        slots={anchor.variant_no:anchor}
        for v in range(1,plan.variant_count+1):
            if v in slots:continue
            candidates=[r for r in ordered if r.variant_no==v and r.id not in taken and profiles[r.id]==profiles[anchor.id]]
            if candidates:slots[v]=min(candidates,key=lambda r:(r.bank_item_id!=anchor.bank_item_id,r.order_no,r.id))
        append(slots)
    for anchor in [r for r in ordered if r.variant_no==1]:
        if anchor.id not in taken:pair(anchor)
    for anchor in ordered:
        if anchor.id not in taken:pair(anchor)
    sequence={r.id:no for no,r in enumerate(ordered_items([p['anchor'] for p in result]))}
    result.sort(key=lambda p:sequence[p['anchor'].id])
    for no,p in enumerate(result,1):p['number']=no
    return result
