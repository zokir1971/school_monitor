"""Complete missing catalogue directions; preserve existing rows and workflow."""
from copy import deepcopy
import re
from sqlalchemy import select, func
from sqlalchemy.orm import raiseload
from app.modules.planning.models import PlanDirection, PlanTemplateDirection, PlanTemplateRow4, PlanTemplateRow11
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow4, SchoolPlanRow11
from app.modules.planning.content_i18n import seed_payload
from app.modules.planning.content_import import catalog, catalog_title_aliases, norm, prepare_catalog_changes

MODELS=(PlanDirection,PlanTemplateDirection,PlanTemplateRow4,PlanTemplateRow11,SchoolPlanRow4,SchoolPlanRow11)


def title_key(value):
    value=norm(value).replace('–','-').replace('—','-')
    value=re.sub(r'\s*-\s*','-',value)
    return re.sub(r'^(?:[ivxі]+|[1-6])\s*[.)]\s*','',value).strip()


def bilingual(values, ru, key=None):
    data=seed_payload(values,lang='kk');data['ru']=deepcopy(ru)
    if key:data['_catalog_key']=key
    return data


def row_values(table,row):
    kk={name:row['kk'][i] for i,name in enumerate(table['fields']) if name!='no'}
    ru={name:row['ru'][i] for i,name in enumerate(table['fields']) if name!='no'}
    values=dict(kk,row_order=row['ordinal'],text_i18n=bilingual(kk,ru,row['key']))
    if table['kind']=='controls':values['no']=str(row['ordinal'])
    return values


async def prepare_completion(db, *, template_id, academic_year):
    report,changes=await prepare_catalog_changes(db,template_id=template_id)
    matches=report['direction_matches']
    unresolved=[r for r in matches if r['catalog_direction_number'] is None]
    if unresolved:
        raise RuntimeError('Есть несопоставленные направления шаблона; заполнение остановлено: '+str(unresolved))
    nums=[r['catalog_direction_number'] for r in matches]
    if len(set(nums))!=len(nums):
        raise RuntimeError('Несколько направлений шаблона соответствуют одному разделу каталога. База не изменена.')
    bundle=catalog();aliases=catalog_title_aliases()
    directions=list((await db.scalars(select(PlanDirection).options(raiseload('*')).order_by(PlanDirection.id))).all())
    attached={r['direction_id']for r in matches}; additions=[];updates=[]
    for section in bundle['directions']:
        number=section['direction_number']
        if number in nums:continue
        titles={title_key(t)for t in [*section['title'].values(),*aliases.get(number,[])]}
        candidates=[d for d in directions if d.id not in attached and
                    (title_key(d.full_title) in titles or title_key(d.short_title) in titles)]
        if len(candidates)>1:
            raise RuntimeError('Неоднозначные названия направления '+str(number)+': '+str([d.id for d in candidates]))
        if not candidates:
            # A differently named placeholder in the expected position must be
            # resolved explicitly, rather than creating an apparent duplicate.
            unknown=[d for d in directions if d.id not in attached and d.sort_order==number]
            if unknown:
                raise RuntimeError('Проверьте название существующего направления '+str(number)+': '+str([
                    dict(id=d.id,short_title=d.short_title,full_title=d.full_title)for d in unknown]))
        direction=candidates[0] if candidates else None
        did=direction.id if direction else None
        if did:attached.add(did)
        if direction:
            # Only recognized standard titles are populated. Custom short labels
            # retain their text; the UI can use the translated full title.
            old=deepcopy(direction.text_i18n or {})
            new=deepcopy(old or seed_payload({k:getattr(direction,k)for k in direction.__text_fields__}))
            for field in direction.__text_fields__:
                raw=getattr(direction,field)
                if title_key(raw) not in titles:continue
                for loc in ('kk','ru'):
                    existing=new.get(loc,{}).get(field)
                    if existing and title_key(existing)not in titles:continue
                    new.setdefault(loc,{})[field]=section['title'][loc]
                new.setdefault('_base',{})[field]=raw
            if old!=new:changes.append(dict(table=direction.__tablename__,id=did,before=old,after=new))
            if not direction.is_active:
                updates.append(dict(table=direction.__tablename__,id=did,field='is_active',before=False,after=True))
        additions.append(dict(catalog_number=number,direction_id=did,create_direction=did is None,
                              objects=len(section['tables'][0]['rows']),tasks=len(section['tables'][1]['rows'])))
    plans=list((await db.execute(select(SchoolPlan.id,SchoolPlan.template_id,SchoolPlan.academic_year,SchoolPlan.status)
        .where(SchoolPlan.template_id==template_id,SchoolPlan.academic_year==academic_year,SchoolPlan.status!='archived')
        .order_by(SchoolPlan.id))).mappings())
    fills=[]
    for plan in plans:
        for operation in additions:
            did=operation['direction_id'];existing=0
            if did:
                for model in (SchoolPlanRow4,SchoolPlanRow11):
                    existing+=await db.scalar(select(func.count(model.id)).where(model.school_plan_id==plan['id'],model.direction_id==did))
            fills.append(dict(plan_id=plan['id'],catalog_number=operation['catalog_number'],preserve_existing=bool(existing)))
    report['completion']={'missing_catalog_directions':[a['catalog_number']for a in additions],
        'directions_to_add':additions,'school_plans':[dict(p)for p in plans],
        'school_directions':fills,'final_catalog_direction_count':len(nums)+len(additions)}
    return report,changes,updates,additions,[dict(p)for p in plans],fills


async def insert_completion(db, *, template_id, additions, fills):
    """Called after durable backup and locks. Return all created identities."""
    created=[];section_map={d['direction_number']:d for d in catalog()['directions']}
    async def add(obj):
        db.add(obj);await db.flush();created.append(obj);return obj
    for operation in additions:
        section=section_map[operation['catalog_number']];did=operation['direction_id']
        if did is None:
            values={'short_title':section['title']['kk'],'full_title':section['title']['kk']}
            ru={k:section['title']['ru']for k in values}
            direction=await add(PlanDirection(**values,sort_order=operation['catalog_number'],is_active=True,
                                             text_i18n=bilingual(values,ru)))
            did=direction.id
        td=await add(PlanTemplateDirection(template_id=template_id,direction_id=did,
            sort_order=operation['catalog_number'],text_i18n=bilingual({'title_override':None},{'title_override':None})))
        for table,tm,sm in zip(section['tables'],(PlanTemplateRow4,PlanTemplateRow11),(SchoolPlanRow4,SchoolPlanRow11)):
            for row in table['rows']:
                values=row_values(table,row)
                await add(tm(template_direction_id=td.id,**deepcopy(values)))
                for target in fills:
                    if target['catalog_number']==operation['catalog_number'] and not target['preserve_existing']:
                        school_values=deepcopy(values)
                        if table['kind']=='tasks':
                            # No month is eligible until the administrator selects
                            # periods; avoid the model's legacy ALL_YEAR default.
                            school_values.update(period_type='months',period_values=None)
                        await add(sm(school_plan_id=target['plan_id'],direction_id=did,is_custom=False,**school_values))
    return created
