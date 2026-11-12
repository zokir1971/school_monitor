"""Scoped geography and paged classes. Selected IDs are revalidated on POST."""
from sqlalchemy import select,func
from app.modules.org.models import Region,District,School
from app.modules.education.models import SchoolClass
from app.modules.assessment.repositories.work_plan_assignment_repo import class_query
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer


def optional_id(value):
    return integer(value,1,2147483647) if value not in (None,'',0,'0') else None


async def selection(db,plan,year,values):
    org=select(Region.id.label('region_id'),Region.name.label('region_name'),
               District.id.label('district_id'),District.name.label('district_name'),
               School.id.label('school_id'),School.name.label('school_name')).select_from(School).join(
               District,District.id==School.district_id).join(Region,Region.id==District.region_id)
    if plan.scope_kind=='school':org=org.where(School.id==plan.school_id)
    elif plan.scope_kind=='district':org=org.where(District.id==plan.district_id)
    else:org=org.where(Region.id==plan.region_id)
    rows=list((await db.execute(org.order_by(District.name,School.name,School.id))).all())
    regions={r.region_id:r.region_name for r in rows}
    region_id=optional_id(values.get('filter_region_id'))
    if region_id is None and len(regions)==1:region_id=next(iter(regions))
    if region_id is not None and region_id not in regions:raise WorkPlanError('Регион недоступен для выбранного комплекта. / Таңдалған жинақ үшін өңір қолжетімсіз.')
    regional=[r for r in rows if region_id is None or r.region_id==region_id]
    districts={r.district_id:r.district_name for r in regional}
    district_id=optional_id(values.get('filter_district_id'))
    if district_id is None and plan.scope_kind in ('school','district') and len(districts)==1:district_id=next(iter(districts))
    if district_id is not None and district_id not in districts:raise WorkPlanError('Район недоступен для выбранного региона и комплекта. / Таңдалған өңір мен жинақ үшін аудан қолжетімсіз.')
    local=[r for r in regional if district_id is None or r.district_id==district_id]
    schools={r.school_id:((r.district_name+' · ') if district_id is None and len(districts)>1 else '')+r.school_name for r in local}
    school_id=optional_id(values.get('filter_school_id'))
    if school_id is None and plan.scope_kind=='school' and len(schools)==1:school_id=next(iter(schools))
    if school_id is not None and school_id not in schools:raise WorkPlanError('Школа недоступна для выбранного района и комплекта. / Таңдалған аудан мен жинақ үшін мектеп қолжетімсіз.')
    q=class_query(plan,year).add_columns(District.name.label('district_name'))
    if region_id is not None:q=q.where(District.region_id==region_id)
    if district_id is not None:q=q.where(District.id==district_id)
    if school_id is not None:q=q.where(School.id==school_id)
    total=(await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    pages=max(1,(total+99)//100);page=min(integer(values.get('class_page',1),1,1000000),pages)
    classes=list((await db.execute(q.order_by(District.name,School.name,SchoolClass.letter,SchoolClass.id).offset((page-1)*100).limit(100))).all())
    return dict(regions=regions,districts=districts,schools=schools,school_options=regional,filter_region_id=region_id,
                filter_district_id=district_id,filter_school_id=school_id,classes=classes,
                class_total=total,class_page=page,class_pages=pages,scope_kind=plan.scope_kind)
