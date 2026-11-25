"""School authority predicates, independent of address filters."""
from sqlalchemy import and_, exists, select, false, case, literal
from app.modules.org.models import School, District

LEVELS = ("district", "region")


def normalize_level(value):
    if value not in LEVELS:
        raise ValueError("Некорректное подчинение школы / Мектептің бағыныстылығы қате")
    return value


def school_authority_clause(actor, school=None):
    """For administration/code issuance, never use geography alone."""
    school = School.__table__ if school is None else school
    role = getattr(actor["role"], "value", actor["role"])
    if role == "district_admin" and actor.get("district_id") is not None:
        return and_(school.c.governance_level == "district", school.c.district_id == actor["district_id"])
    if role == "region_admin" and actor.get("region_id") is not None:
        district = District.__table__
        return and_(school.c.governance_level == "region", exists(select(1).where(
            district.c.id == school.c.district_id, district.c.region_id == actor["region_id"])))
    return false()


def district_school_ids(district_id):
    return select(School.id).where(School.district_id == district_id, School.governance_level == "district")


def governance_filter(value):
    """Empty/all means the existing complete regional overview."""
    value = str(value or '').strip()
    if value in ('', 'all'):
        return ''
    return normalize_level(value)


def regional_label():
    from app.core.ui_locale_context import ui_locale
    return 'Облыстық бағыныстағы мектептер' if ui_locale.get() == 'kk' else 'Школы областного подчинения'


def reporting_names(names, ids):
    return {**names, **{key: regional_label() for key in ids if key < 0}}


def governance_school_ids(level):
    level = governance_filter(level)
    query = select(School.id)
    return query.where(School.governance_level == level) if level else query


def filter_school_statement(statement, school_id, governance=''):
    level = governance_filter(governance)
    return statement.where(school_id.in_(governance_school_ids(level))) if level else statement


def reporting_district_id(district_id, region_id, *, school_id=None, level=None):
    """A negative region ID is a reporting group, never a database district.

    School address and historical snapshots remain unchanged. A region's direct
    schools form exactly one separate group within that region.
    """
    direct = level == 'region' if level is not None else school_id.in_(governance_school_ids('region'))
    return case((direct, -region_id), else_=district_id)


def reporting_district_name(district_name, level):
    return case((level == 'region', literal(regional_label())), else_=district_name)


def reporting_group_school_ids(group_id, region_id):
    """Validate synthetic groups against the actor's own region."""
    if group_id < 0:
        if group_id != -region_id:
            return select(School.id).where(false())
        return select(School.id).join(District, District.id == School.district_id).where(
            District.region_id == region_id, School.governance_level == 'region')
    return district_school_ids(group_id)
