"""Scoped geography and paged classes. Selected IDs are revalidated on POST."""
from sqlalchemy import select,func
from app.modules.org.models import Region,District,School
from app.modules.org.governance import governance_filter, reporting_district_id, reporting_district_name
from app.modules.education.models import SchoolClass
from app.modules.assessment.repositories.work_plan_assignment_repo import class_query
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer


def optional_id(value):
    return integer(value,1,2147483647) if value not in (None,'',0,'0') else None


def optional_group(value):
    return integer(value,-2147483647,2147483647) if value not in (None,'',0,'0') else None


def apply_selection(query, filters):
    district_id=filters['filter_district_id']
    if filters['filter_region_id'] is not None:query=query.where(District.region_id==filters['filter_region_id'])
    if district_id is not None:
        if district_id<0:query=query.where(District.region_id==-district_id,School.governance_level=='region')
        else:query=query.where(District.id==district_id,School.governance_level=='district')
    if filters['filter_school_id'] is not None:query=query.where(School.id==filters['filter_school_id'])
    if filters.get('filter_governance'):query=query.where(School.governance_level==filters['filter_governance'])
    return query


async def selection(db,plan,year,values):
    try:governance=governance_filter(values.get('filter_governance'))
    except ValueError as exc:raise WorkPlanError(str(exc)) from exc
    if plan.scope_kind=='district' and governance=='region':raise WorkPlanError('Областные школы недоступны для районного комплекта. / Облыстық мектептер аудандық жинаққа қолжетімсіз.')
    org=select(Region.id.label('region_id'),Region.name.label('region_name'),
               reporting_district_id(District.id,Region.id,level=School.governance_level).label('district_id'),reporting_district_name(District.name,School.governance_level).label('district_name'),
               School.id.label('school_id'),School.name.label('school_name')).select_from(School).join(
               District,District.id==School.district_id).join(Region,Region.id==District.region_id)
    if plan.scope_kind=='school':org=org.where(School.id==plan.school_id)
    elif plan.scope_kind=='district':org=org.where(District.id==plan.district_id, School.governance_level=='district')
    else:org=org.where(Region.id==plan.region_id)
    if governance:org=org.where(School.governance_level==governance)
    rows=list((await db.execute(org.order_by(District.name,School.name,School.id))).all())
    regions={r.region_id:r.region_name for r in rows}
    region_id=optional_id(values.get('filter_region_id'))
    if region_id is None and len(regions)==1:region_id=next(iter(regions))
    if region_id is not None and region_id not in regions:raise WorkPlanError('Регион недоступен для выбранного комплекта. / Таңдалған жинақ үшін өңір қолжетімсіз.')
    regional=[r for r in rows if region_id is None or r.region_id==region_id]
    districts={r.district_id:r.district_name for r in regional}
    district_id=optional_group(values.get('filter_district_id'))
    if district_id is None and plan.scope_kind in ('school','district') and len(districts)==1:district_id=next(iter(districts))
    if district_id is not None and district_id not in districts:raise WorkPlanError('Район недоступен для выбранного региона и комплекта. / Таңдалған өңір мен жинақ үшін аудан қолжетімсіз.')
    local=[r for r in regional if district_id is None or r.district_id==district_id]
    schools={r.school_id:((r.district_name+' · ') if district_id is None and len(districts)>1 else '')+r.school_name for r in local}
    school_id=optional_id(values.get('filter_school_id'))
    if school_id is None and plan.scope_kind=='school' and len(schools)==1:school_id=next(iter(schools))
    if school_id is not None and school_id not in schools:raise WorkPlanError('Школа недоступна для выбранного района и комплекта. / Таңдалған аудан мен жинақ үшін мектеп қолжетімсіз.')
    q=class_query(plan,year).add_columns(reporting_district_name(District.name,School.governance_level).label('district_name'))
    q=apply_selection(q,dict(filter_region_id=region_id,filter_district_id=district_id,filter_school_id=school_id,filter_governance=governance))
    total=(await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    pages=max(1,(total+99)//100);page=min(integer(values.get('class_page',1),1,1000000),pages)
    classes=list((await db.execute(q.order_by(District.name,School.name,SchoolClass.letter,SchoolClass.id).offset((page-1)*100).limit(100))).all())
    return dict(filter_governance=governance,regions=regions,districts=districts,schools=schools,school_options=regional,filter_region_id=region_id,
                filter_district_id=district_id,filter_school_id=school_id,classes=classes,
                class_total=total,class_page=page,class_pages=pages,scope_kind=plan.scope_kind)
