from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.schemas import MyTaskDTO
from app.modules.staff.staff_repo import SchoolStaffRepo
from app.modules.staff.task_repo import StaffTasksRepo
from app.modules.users.models import User

from typing import cast


class StaffTasksService:

    @staticmethod
    async def get_my_tasks_page(
            db: AsyncSession,
            *,
            user: User,
            month: int,
    ) -> list[MyTaskDTO]:
        school_id_raw = getattr(user, "school_id", None)
        if school_id_raw is None:
            return []

        school_id = cast(int, school_id_raw)

        staff_member = await SchoolStaffRepo.get_member_by_user_id(
            db,
            user_id=cast(int, getattr(user, "id")),
        )
        if not staff_member:
            return []

        staff_role_ids = [cast(int, r.id) for r in (staff_member.roles or []) if r.is_active]
        if not staff_role_ids:
            return []

        items = await StaffTasksRepo.list_tasks_for_staff(
            db,
            school_id=school_id,
            staff_role_ids=staff_role_ids,
            month=month,
        )

        result: list[MyTaskDTO] = []
        for item in items:
            src = item.source_row11

            review_place_text = "—"
            if src and src.review_places:
                parts: list[str] = []
                for rp in src.review_places:
                    review_place = getattr(rp, "review_place", None)
                    if not review_place:
                        continue
                    parts.append(getattr(review_place, "label_kz", None) or str(review_place))

                if parts:
                    review_place_text = ", ".join(parts)

            result.append(
                MyTaskDTO(
                    month_item_id=item.id,
                    week_of_month=item.week_of_month,
                    planned_start=item.planned_start,
                    planned_end=item.planned_end,
                    topic=getattr(src, "topic", None),
                    goal=getattr(src, "goal", None),
                    control_object=getattr(src, "control_object", None),
                    control_type=getattr(src, "control_type", None),
                    review_place=review_place_text,
                )
            )

        return result
