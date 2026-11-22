"""Territory authorization and validation for read-only statistics."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import HTTPException
from sqlalchemy import select
from app.modules.org.models import District,Region
from app.modules.statistics.territorial_repo import TerritorialStatisticsRepo as Repo,MONTHS


def integer(value,default=None,minimum=1,maximum=2147483647):
    if value is None or value=='':return default
    try:parsed=int(value)
    except (ValueError,TypeError):raise HTTPException(400,'Некорректный числовой фильтр / Сандық сүзгі қате')
    if not minimum<=parsed<=maximum:raise HTTPException(400,'Значение фильтра вне диапазона / Сүзгі мәні жарамсыз')
    return parsed


class TerritorialStatisticsService:
    @staticmethod
    async def scope(db,user):
        role=str(getattr(user.role,'value',user.role))
        if not user.is_active:raise HTTPException(403,'Нет доступа / Қолжетімділік жоқ')
        if role=='superuser':
            r,d=Region.__table__.c,District.__table__.c
            rows=(await db.execute(select(r.id,r.name,d.id.label('district_id'),d.name.label('district_name')).select_from(Region.__table__.outerjoin(District.__table__,d.region_id==r.id)).order_by(r.name,r.id,d.name,d.id))).mappings().all()
            return dict(kind='super',district_id=None,region_id=None,name='',
                        regions=list({row['id']:dict(id=row['id'],name=row['name'])for row in rows}.values()),
                        districts=[dict(id=row['district_id'],name=row['district_name'],region_id=row['id'])for row in rows if row['district_id'] is not None])
        if role=='district_admin' and user.district_id:
            d=District.__table__.c
            row=(await db.execute(select(d.id,d.name,d.region_id).where(d.id==user.district_id))).mappings().first()
            if row:return dict(kind='district',district_id=row['id'],region_id=row['region_id'],name=row['name'],
                               districts=[dict(id=row['id'],name=row['name'])])
        elif role=='region_admin' and user.region_id:
            r,d=Region.__table__.c,District.__table__.c
            rows=(await db.execute(select(r.id,r.name,d.id.label('district_id'),d.name.label('district_name'))
                                   .select_from(Region.__table__.outerjoin(District.__table__,d.region_id==r.id))
                                   .where(r.id==user.region_id).order_by(d.name,d.id))).mappings().all()
            if rows:return dict(kind='region',district_id=None,region_id=rows[0]['id'],name=rows[0]['name'],
                                districts=[dict(id=row['district_id'],name=row['district_name'])for row in rows if row['district_id'] is not None])
        raise HTTPException(403,'Не задана доступная территория / Қолжетімді аумақ белгіленбеген')

    @classmethod
    async def page(cls,db,user,params):
        try:local_timezone=ZoneInfo('Asia/Qyzylorda')
        except ZoneInfoNotFoundError:local_timezone=timezone(timedelta(hours=5))
        today=datetime.now(local_timezone).date()
        year=integer(params.get('year'),today.year if today.month>=8 else today.year-1,2000,2100)
        month=integer(params.get('month'),None,1,12)
        if month is not None and month not in MONTHS:raise HTTPException(400,'Месяц не входит в учебный период / Ай оқу кезеңіне кірмейді')
        direction_id=integer(params.get('direction_id'),None,0)
        region_id=integer(params.get('region_id'))
        district_id=integer(params.get('district_id'))
        school_id=integer(params.get('school_id'))
        page=integer(params.get('page'),1)
        search=(params.get('q')or'').strip()
        if len(search)>150:raise HTTPException(400,'Слишком длинный поиск / Іздеу мәтіні тым ұзын')
        sort=params.get('sort','name')
        if sort not in ('name','completed','overdue','rate','overdue_rate','assigned_rate','submitted_rate'):raise HTTPException(400,'Некорректная сортировка / Сұрыптау қате')
        order=params.get('order')or('asc' if sort=='name' else 'desc')
        if order not in ('asc','desc'):raise HTTPException(400,'Некорректный порядок / Реті қате')
        attention=integer(params.get('attention'),0,0,1)
        scope=await cls.scope(db,user)
        regions=scope.get('regions',[])
        districts=scope['districts']
        if scope['kind']=='super':
            if region_id is not None and region_id not in {row['id']for row in regions}:raise HTTPException(400,'Регион не найден / Өңір табылмады')
            if district_id is not None:
                selected=next((row for row in districts if row['id']==district_id),None)
                if selected is None or (region_id is not None and selected['region_id']!=region_id):raise HTTPException(400,'Район не принадлежит региону / Аудан өңірге жатпайды')
                region_id=selected['region_id']
            scope=dict(scope,region_id=region_id)
        else:
            if region_id is not None and region_id!=scope['region_id']:raise HTTPException(403,'Регион недоступен / Өңір қолжетімсіз')
            if district_id is not None and district_id not in {row['id']for row in districts}:raise HTTPException(403,'Район недоступен / Аудан қолжетімсіз')
            if scope['kind']=='district':district_id=scope['district_id']
            region_id=None
        school_name=None
        if school_id is not None:
            allowed=Repo.school_scope(scope,district_id,school_id)
            chosen=(await db.execute(select(allowed))).mappings().first()
            if chosen is None:raise HTTPException(403,'Школа недоступна / Мектеп қолжетімсіз')
            school_name=chosen['school_name']
            if scope['kind']=='super':
                region_id,district_id=chosen['region_id'],chosen['district_id']
                scope=dict(scope,region_id=region_id)
        if scope['kind']=='super':
            if region_id is not None:
                districts=[row for row in districts if row['region_id']==region_id]
                scope=dict(scope,name=next(row['name']for row in regions if row['id']==region_id))
        view=params.get('view')or('directions' if school_id else 'schools' if district_id else 'regions' if scope['kind']=='super' and region_id is None else 'districts')
        if attention and school_id is None:view='schools'
        if view not in ('regions','districts','schools','directions') or (scope['kind']=='district' and view=='districts') or (view=='regions' and (scope['kind']!='super' or region_id is not None or school_id is not None)):
            raise HTTPException(400,'Некорректное представление / Көрініс қате')
        if school_id and view!='directions':raise HTTPException(400,'Для школы выберите направления / Мектеп үшін бағыттарды таңдаңыз')
        schools=Repo.school_scope(scope,district_id,school_id,search)
        direction_scope=Repo.school_scope(dict(kind='super',region_id=None)) if scope['kind']=='super' else Repo.school_scope(scope,district_id,school_id)
        directions=await Repo.directions(db,direction_scope,year)
        if direction_id not in (None,0) and direction_id not in {row['id']for row in directions}:
            raise HTTPException(400,'Направление отсутствует в выбранных планах / Таңдалған жоспарларда бағыт жоқ')
        totals,rows,page,pages=await Repo.read(db,schools,year,month,direction_id,view,today,page,sort,order,attention=bool(attention and view=='schools'))
        for row in [totals,*rows]:
            row['unassigned']=row['tasks']-row['assigned']
            for key,num,den in [('assigned_percent','assigned','tasks'),('overdue_percent','overdue','tasks'),('submitted_percent','submitted','reports')]:
                row[key]=round(100*row[num]/row[den],1)if row[den] else None
            row['help_reasons']=[]
            if view=='schools' and row is not totals:
                for flag,rz,kz in [(not row.get('has_admin'),'Нет активного администратора','Белсенді әкімші жоқ'),(not row['annual'],'Нет годового плана / направления','Жылдық жоспар / бағыт жоқ'),(not row['monthly'],'Нет выпущенного месячного плана / задач направления','Шығарылған айлық жоспар / бағыт тапсырмасы жоқ'),(row['unassigned']>0,'Есть неназначенные задачи','Тағайындалмаған тапсырмалар бар'),(row['overdue']>0,'Есть просроченные задачи','Мерзімі өткен тапсырмалар бар')]:
                    if flag:row['help_reasons'].append((rz,kz))
            row['percent']=round(100*row['completed']/row['tasks'],1)if row['tasks'] else None
        return dict(scope=scope,regions=regions,region_id=region_id,year=year,month=month,direction_id=direction_id,district_id=district_id,
                    school_id=school_id,school_name=school_name,view=view,sort=sort,order=order,attention=attention,q=search,districts=districts,
                    directions=directions,totals=totals,rows=rows,page=page,pages=pages,today=today)
