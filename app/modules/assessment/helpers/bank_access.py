"""READY bank reading is shared; authoring, reviewing and assessment scopes are separate."""
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole

require_bank_reader = require_roles(
    UserRole.TEACHER, UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF,
    UserRole.DISTRICT_ADMIN, UserRole.DISTRICT_STAFF,
    UserRole.REGION_ADMIN, UserRole.REGION_STAFF,
)
