"""Strict content matching and field-preserving bilingual catalog installation.

No deletes, inserts, assignments, schedules or legacy text updates. Callers own
transactions and backups. An edited/missing/ambiguous row is reported and skipped.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from functools import lru_cache
import json,re,unicodedata
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import raiseload
from app.modules.planning.models import PlanDirection,PlanTemplateDirection,PlanTemplateRow4,PlanTemplateRow11
from app.modules.planning.models_school import SchoolPlan,SchoolPlanRow4,SchoolPlanRow11
from app.modules.planning.content_i18n import seed_payload


def norm(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',str(value or ''))).strip().casefold()


def catalog():
    return json.loads((Path(__file__).parent/'data/vshk_2026_kk_ru.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=12)
def reviewed_rows_for(base_keys):
    """Immutable release data only; school rows and rendered text are not cached."""
    path=Path(__file__).parent/'data/vshk_reviewed_variants.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    keys=set(base_keys)
    return tuple(row for row in data['rows'] if row['base_key'] in keys)


def matching_row(obj,table):
    anchor = 'control_object' if table['kind']=='controls' else 'topic'
    anchor_index=table['fields'].index(anchor)
    current=norm(getattr(obj,anchor,None))
    if not current:
        return None
    scored=[]
    candidates=(*table['rows'],*reviewed_rows_for(tuple(row['key']for row in table['rows'])))
    for row in candidates:
        if current not in {norm(row[loc][anchor_index]) for loc in ('source','kk','ru')}:
            continue
        score=1
        for field in ('goal','control_object')if anchor=='topic'else():
            index=table['fields'].index(field)
            value=norm(getattr(obj,field,None))
            if value and value in {norm(row[loc][index])for loc in ('source','kk','ru')}:score+=1
        scored.append((score,row))
    if not scored:return None
    best=max(s for s,_ in scored)
    winners=[row for score,row in scored if score==best]
    return winners[0]if len(winners)==1 else None


def translated_payload(obj,table,row):
    data=deepcopy(obj.text_i18n or seed_payload({k:getattr(obj,k,None)for k in obj.__text_fields__}))
    changed=0;preserved=[]
    for field in obj.__text_fields__:
        if field not in table['fields']:continue
        index=table['fields'].index(field)
        raw=getattr(obj,field,None)
        aliases={norm(row[loc][index])for loc in ('source','kk','ru')}
        if norm(raw)not in aliases:
            preserved.append(field);continue
        for loc in ('kk','ru'):
            if (loc=='kk' and row.get('preserve_existing_kk')
                    and field in data.get('kk',{})
                    and data.get('_base',{}).get(field,raw)==raw):
                continue
            existing=data.get(loc,{}).get(field)
            if (existing and norm(existing)not in aliases) or (field in data.get(loc,{}) and not existing and data.get('_catalog_key') == row['key'] and row[loc][index]):
                preserved.append(loc+'.'+field);continue
            value=row[loc][index]
            if data.get(loc,{}).get(field)!=value:
                data.setdefault(loc,{})[field]=value;changed+=1
        data.setdefault('_base',{})[field]=raw
    if changed:data['_catalog_key']=row['key']
    return data,changed,preserved


async def prepare_catalog_changes(db,*,template_id):
    bundle=catalog();changes=[];stats=Counter();examples=[];title_examples=[]
    async def rows(model,condition):
        return list((await db.scalars(select(model).where(condition).options(raiseload('*')).order_by(model.id))).all())
    template_dirs=await rows(PlanTemplateDirection,PlanTemplateDirection.template_id==template_id)
    ids=[td.id for td in template_dirs]
    tr4=await rows(PlanTemplateRow4,PlanTemplateRow4.template_direction_id.in_(ids))
    tr11=await rows(PlanTemplateRow11,PlanTemplateRow11.template_direction_id.in_(ids))
    groups=defaultdict(list)
    for obj,ti in [(r,0)for r in tr4]+[(r,1)for r in tr11]:groups[obj.template_direction_id].append((obj,ti))
    resolved={}
    for td in template_dirs:
        votes=Counter()
        for obj,ti in groups[td.id]:
            candidates=[d for d in bundle['directions']if matching_row(obj,d['tables'][ti])]
            if len(candidates)==1:votes[candidates[0]['direction_number']]+=1
        # A direction number/row order alone is never sufficient evidence.
        if not votes:stats['unmatched_directions']+=1;continue
        best=votes.most_common()
        if best[0][1]<2 or(len(best)>1 and best[0][1]==best[1][1]):stats['unmatched_directions']+=1;continue
        resolved[td.direction_id]=next(d for d in bundle['directions']if d['direction_number']==best[0][0])
    def record(obj,new):
        old=deepcopy(obj.text_i18n or {})
        if new!=old:changes.append({'table':obj.__tablename__,'id':obj.id,'before':old,'after':new});stats['rows_to_update']+=1
    for td in template_dirs:
        direction=resolved.get(td.direction_id)
        if not direction:continue
        obj=await db.get(PlanDirection,td.direction_id,options=[raiseload('*')])
        # Titles are matched against an explicit numbered/source title or a unique
        # direction inferred from its actual template contents. Preserve custom names.
        canonical=direction['title']
        original_titles={norm(canonical['kk']),norm(canonical['ru'])}
        # Original headings, supplied alongside corrected content, are trusted aliases.
        originals=catalog_title_aliases().get(direction['direction_number'],[])
        original_titles.update(norm(v)for v in originals)
        for entity,fields in [(obj,('short_title','full_title')),(td,('title_override',))]:
            data=deepcopy(entity.text_i18n or seed_payload({k:getattr(entity,k,None)for k in entity.__text_fields__}))
            for field in fields:
                raw=getattr(entity,field,None)
                if not raw:continue
                if norm(raw)not in original_titles:
                    stats['preserved_custom_titles']+=1
                    title_examples.append({'table':entity.__tablename__,'id':entity.id,'field':field})
                    continue
                for loc in ('kk','ru'):
                    existing=data.get(loc,{}).get(field)
                    if existing and norm(existing)not in original_titles:continue
                    data.setdefault(loc,{})[field]=canonical[loc]
                data.setdefault('_base',{})[field]=raw
            record(entity,data)
    plan_ids=[r.id for r in await rows(SchoolPlan,SchoolPlan.template_id==template_id)]
    school4=await rows(SchoolPlanRow4,SchoolPlanRow4.school_plan_id.in_(plan_ids))
    school11=await rows(SchoolPlanRow11,SchoolPlanRow11.school_plan_id.in_(plan_ids))
    td_by_id={d.id:d for d in template_dirs}
    for obj,ti in [(r,0)for r in tr4]+[(r,1)for r in tr11]+[(r,0)for r in school4]+[(r,1)for r in school11]:
        if getattr(obj,'is_custom',False):stats['preserved_custom_rows']+=1;continue
        did=getattr(obj,'direction_id',None)
        if did is None:did=td_by_id[obj.template_direction_id].direction_id
        direction=resolved.get(did)
        row=matching_row(obj,direction['tables'][ti])if direction else None
        if not row:
            stats['unmatched_rows']+=1
            if len(examples)<20:examples.append({'table':obj.__tablename__,'id':obj.id})
            continue
        new,count,preserved=translated_payload(obj,direction['tables'][ti],row)
        stats['matched_rows']+=1;stats['preserved_edited_fields']+=len(preserved)
        stats['language_fields_to_update']+=count;record(obj,new)
    return {'template_id':template_id,'directions_matched':len(resolved),'template_direction_count':len(template_dirs),'direction_matches':[{'template_direction_id':td.id,'direction_id':td.direction_id,'catalog_direction_number':resolved[td.direction_id]['direction_number'] if td.direction_id in resolved else None} for td in template_dirs],'counts':dict(stats),'unmatched_examples':examples,'titles_for_manual_translation':title_examples},changes


def catalog_title_aliases():
    file=Path(__file__).parent/'data/vshk_title_aliases.json'
    return {int(k):v for k,v in json.loads(file.read_text(encoding='utf-8')).items()}
