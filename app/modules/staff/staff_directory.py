"""School-scoped directory reads and inline-role form helpers; no shared cache."""
import hashlib,json
from math import ceil
from types import SimpleNamespace as NS
from urllib.parse import urlencode
from fastapi import HTTPException
from app.core.ui_locale_context import ui_locale

def invalid(ru,kk):
    return HTTPException(400,ru if ui_locale.get()=='ru' else kk)
from sqlalchemy import select,func,exists,Integer
from app.modules.staff.models_staff_school import SchoolStaffMember,SchoolStaffRole
from app.modules.planning.enums import ResponsibleRole

PAGE_SIZE=50
FILTER_KEYS=('name','iin','role','status','page')

def filters_from(values):
    result={key:str(values.get(key,'')or'').strip()for key in FILTER_KEYS}
    result['status']=result['status']or'active'
    if len(result['name'])>200 or len(result['iin'])>12 or(result['iin']and not result['iin'].isascii())or(result['iin']and not result['iin'].isdigit()):
        raise invalid('Проверьте ФИО и ИИН в поиске.','Іздеудегі аты-жөні мен ЖСН-ді тексеріңіз.')
    if result['role']not in {'','none',*(r.value for r in ResponsibleRole)}or result['status']not in {'active','inactive','all'}:
        raise invalid('Проверьте выбранные фильтры.','Таңдалған сүзгілерді тексеріңіз.')
    try:result['page']=max(1,min(int(result['page']or'1'),100000))
    except ValueError:raise invalid('Неверный номер страницы.','Бет нөмірі қате.')
    return result

def filter_url(filters,*,page=None):
    values={k:filters[k]for k in FILTER_KEYS if filters.get(k)not in ('',None)}
    if page is not None:values['page']=page
    return '/staff/school?'+urlencode(values)

def roles_revision(roles):
    def value(row,key):return row.get(key)if isinstance(row,dict)else getattr(row,key)
    rows=sorted((value(r,'id'),str(getattr(value(r,'role'),'value',value(r,'role'))),value(r,'role_context')or'',bool(value(r,'is_active')))for r in roles)
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()

async def directory(db,*,school_id,filters):
    M,R=SchoolStaffMember.__table__,SchoolStaffRole.__table__
    summary=(await db.execute(select(func.count().label('total'),func.coalesce(func.sum(func.cast(M.c.is_active, Integer)),0).label('active')).where(M.c.school_id==school_id))).mappings().one()
    summary=dict(summary);summary['inactive']=summary['total']-summary['active']
    conditions=[M.c.school_id==school_id]
    if filters['status']!='all':conditions.append(M.c.is_active.is_(filters['status']=='active'))
    if filters['name']:conditions.append(M.c.full_name.ilike('%'+filters['name'].replace('!','!!').replace('%','!%').replace('_','!_')+'%',escape='!'))
    if filters['iin']:conditions.append(M.c.iin.startswith(filters['iin'],autoescape=True))
    role_scope=[R.c.school_id==school_id,R.c.staff_member_id==M.c.id,R.c.is_active.is_(True)]
    if filters['role']:
        match=exists(select(R.c.id).where(*role_scope,*([]if filters['role']=='none'else[R.c.role==ResponsibleRole(filters['role'])])))
        conditions.append(~match if filters['role']=='none'else match)
    matched=await db.scalar(select(func.count()).select_from(M).where(*conditions))
    pages=max(1,ceil(matched/PAGE_SIZE));filters=dict(filters,page=min(filters['page'],pages))
    rows=(await db.execute(select(M.c.id,M.c.school_id,M.c.full_name,M.c.iin,M.c.position_text,M.c.is_active).where(*conditions).order_by(M.c.full_name,M.c.id).offset((filters['page']-1)*PAGE_SIZE).limit(PAGE_SIZE))).mappings().all()
    members={r['id']:NS(**r,roles=[])for r in rows}
    if members:
        roles=(await db.execute(select(R.c.id,R.c.staff_member_id,R.c.role,R.c.role_context,R.c.is_active).join(M,M.c.id==R.c.staff_member_id).where(R.c.school_id==school_id,M.c.school_id==school_id,R.c.staff_member_id.in_(members)).order_by(R.c.id))).mappings().all()
        for r in roles:members[r['staff_member_id']].roles.append(NS(**r))
    for member in members.values():member.roles_revision=roles_revision(member.roles)
    return dict(members=list(members.values()),staff_summary=summary,filtered_count=matched,filters=filters,
                page_count=pages,previous_url=filter_url(filters,page=filters['page']-1)if filters['page']>1 else None,
                next_url=filter_url(filters,page=filters['page']+1)if filters['page']<pages else None)
