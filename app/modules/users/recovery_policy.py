"""Explicit delegation hierarchy, independent of optional workspace roles."""
from sqlalchemy import and_,false,or_,select
from app.modules.users.enums import UserRole
from app.modules.org.models import District,School

ADMIN_ROLES={'superuser','region_admin','district_admin','school_admin'}


def role_value(role):
    return getattr(role,'value',role)


def allowed_roles(actor_role):
    value=role_value(actor_role)
    present={r.value:r for r in UserRole}
    allowed={
        'superuser':set(present)-{'superuser'},
        'region_admin':{'district_admin','region_staff'},
        'district_admin':{'school_admin','district_staff'},
        'school_admin':{'school_staff','teacher'},
    }.get(value,set())
    return [present[r] for r in sorted(allowed) if r in present]


def recovery_scope(U,actor):
    """One SQL predicate: hierarchy plus current territory; no relationship loading."""
    role=role_value(actor['role']);roles=allowed_roles(role)
    if not actor['is_active'] or not roles:
        return false()
    base=and_(U.c.id!=actor['id'],U.c.role.in_(roles))
    if role=='superuser':return base
    if role=='region_admin' and actor.get('region_id'):
        D=District.__table__
        return and_(base,or_(U.c.region_id==actor['region_id'],U.c.district_id.in_(select(D.c.id).where(D.c.region_id==actor['region_id']))))
    if role=='district_admin' and actor.get('district_id'):
        S=School.__table__
        return and_(base,or_(U.c.district_id==actor['district_id'],U.c.school_id.in_(select(S.c.id).where(S.c.district_id==actor['district_id']))))
    if role=='school_admin' and actor.get('school_id'):
        return and_(base,U.c.school_id==actor['school_id'])
    return false()
