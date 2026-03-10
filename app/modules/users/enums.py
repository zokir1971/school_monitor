# app/modules/users/enums.py (enum ролей)

import enum


class UserRole(str, enum.Enum):
    SUPERUSER = "superuser"

    REGION_ADMIN = "region_admin"
    REGION_STAFF = "region_staff"

    DISTRICT_ADMIN = "district_admin"
    DISTRICT_STAFF = "district_staff"

    SCHOOL_ADMIN = "school_admin"
    SCHOOL_STAFF = "school_staff"
