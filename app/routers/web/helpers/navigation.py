# app/web/helpers/navigation.py (функция маршрутизации navigation / mapping)

from app.modules.users.enums import UserRole


def dashboard_url_for_role(role: UserRole) -> str:
    return {
        UserRole.SUPERUSER: "/dashboards/l0",
        UserRole.REGION_ADMIN: "/dashboards/l1",
        UserRole.DISTRICT_ADMIN: "/dashboards/l2",
        UserRole.SCHOOL_ADMIN: "/dashboards/l3",
        UserRole.SCHOOL_STAFF: "/dashboards/staff_school",
    }.get(role, "/dashboards")
