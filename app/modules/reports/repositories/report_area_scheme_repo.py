"""School-scoped, optimistic writes; no commit outside the algorithm transaction."""
from sqlalchemy import select, update, exists, or_, func
from sqlalchemy.dialects.postgresql import insert
from app.modules.reports.models_documents import SchoolReportAreaScheme
from app.modules.planning.models_month_plan import SchoolMonthPlanItemAssignee
from app.modules.planning.enums import AssignmentKind
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember
from app.modules.users.models import User
from app.modules.users.enums import UserRole


async def save(db, *, school_id, task_id, user_id, expected_revision, configuration):
    U, A, R, F = User.__table__, SchoolMonthPlanItemAssignee.__table__, SchoolStaffRole.__table__, SchoolStaffMember.__table__
    primary = exists(select(A.c.id).select_from(A.join(R, R.c.id == A.c.staff_role_id).join(F, F.c.id == R.c.staff_member_id))
                     .where(A.c.month_item_id == task_id, A.c.assignment_kind == AssignmentKind.PRIMARY,
                            F.c.school_id == school_id, F.c.id == U.c.staff_member_id, R.c.school_id == school_id, R.c.is_active.is_(True), F.c.is_active.is_(True)))
    permitted = (await db.execute(select(U.c.id).where(U.c.id == user_id, U.c.school_id == school_id,
                  or_(U.c.role == UserRole.SCHOOL_ADMIN, primary)))).scalar_one_or_none()
    if permitted is None:
        raise ValueError('Школьную схему сохраняет администратор школы или основной исполнитель задачи. / Мектеп сызбасын мектеп әкімшісі немесе тапсырманың негізгі орындаушысы сақтайды.')
    T = SchoolReportAreaScheme.__table__
    values = dict(configuration=configuration, updated_by_user_id=user_id, updated_at=func.now(), revision=expected_revision+1)
    if expected_revision == 0:
        statement = insert(T).values(school_id=school_id, **values).on_conflict_do_nothing(index_elements=[T.c.school_id]).returning(T.c.revision)
    else:
        statement = update(T).where(T.c.school_id == school_id, T.c.revision == expected_revision).values(**values).returning(T.c.revision)
    if (await db.execute(statement)).scalar_one_or_none() is None:
        raise ValueError('Школьная схема изменена в другом окне. Обновите страницу. / Мектеп сызбасы басқа терезеде өзгертілген. Бетті жаңартыңыз.')
