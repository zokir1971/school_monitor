"""Small school-scoped projection used once by teacher-choice pages."""
from dataclasses import dataclass
from sqlalchemy import select
from app.modules.staff.models_staff_school import SchoolStaffMember

@dataclass(frozen=True, slots=True)
class TeacherChoice:
    id: int
    full_name: str
    subject: str | None
    diploma_specialty: str | None

class TeacherChoicesRepo:
    @staticmethod
    async def list_active(db, *, school_id) -> list[TeacherChoice]:
        table = SchoolStaffMember.__table__
        rows = (await db.execute(select(table.c.id, table.c.full_name, table.c.subject, table.c.diploma_specialty)
            .where(table.c.school_id == school_id, table.c.is_active.is_(True))
            .order_by(table.c.full_name, table.c.id))).mappings().all()
        return [TeacherChoice(**row) for row in rows]

    @staticmethod
    async def get_active(db, *, school_id, staff_member_id) -> TeacherChoice | None:
        table = SchoolStaffMember.__table__
        row = (await db.execute(select(table.c.id, table.c.full_name, table.c.subject, table.c.diploma_specialty)
            .where(table.c.school_id == school_id, table.c.id == staff_member_id, table.c.is_active.is_(True)))).mappings().one_or_none()
        return TeacherChoice(**row) if row else None
