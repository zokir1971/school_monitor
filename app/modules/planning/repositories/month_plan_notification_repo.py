# app/modules/planning/repositories/month_plan_notification_repo.py

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import (
    String,
    and_,
    cast,
    func,
    or_,
    select, delete,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import MonthPlanNotificationStatus
from app.modules.planning.models_month_plan import SchoolMonthPlanItem, SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlanRow11
from app.modules.planning.models_month_plan_notification import SchoolMonthPlanNotification
from app.modules.planning.schemas.month_plan_notification_dto import (
    MonthPlanNotificationAssignmentRowDTO,
    MonthPlanNotificationStatusDTO, MonthPlanNotificationProgressDTO,
)
from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)
from app.modules.users.models import User


class SchoolMonthPlanNotificationRepo:
    """
    Репозиторий WhatsApp-уведомлений исполнителей
    по месячному плану.

    Репозиторий отвечает за:

    - получение назначений месячного плана;
    - получение текущего состояния уведомлений;
    - создание состояния уведомления;
    - регистрацию открытия WhatsApp;
    - подтверждение получения задач;
    - сброс и удаление состояния.

    Группировка задач по сотрудникам, формирование текста сообщения
    и бизнес-правила изменения статусов выполняются сервисом.
    """

    # =========================================================
    # ASSIGNMENTS
    # =========================================================

    @staticmethod
    async def list_notification_assignment_rows(
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
    ) -> list[MonthPlanNotificationAssignmentRowDTO]:
        """
        Получить плоские строки назначений включённых задач
        месячного плана одним пакетным SQL-запросом.

        Метод получает:

        - сотрудника;
        - состояние регистрации сотрудника;
        - номер телефона зарегистрированного пользователя;
        - вид назначения;
        - задачу месячного плана;
        - срок выполнения задачи.

        Один сотрудник может присутствовать в результате несколько раз,
        если ему назначено несколько задач.

        Группировка строк по сотрудникам выполняется сервисом.
        """

        stmt = (
            select(
                SchoolStaffMember.id.label("staff_member_id"),
                SchoolStaffMember.full_name.label("full_name"),
                User.id.label("user_id"),
                User.phone.label("phone"),
                SchoolMonthPlanItemAssignee.assignment_kind.label(
                    "assignment_kind"
                ),
                SchoolMonthPlanItem.id.label("month_item_id"),
                SchoolPlanRow11.topic.label("task_title"),
                SchoolMonthPlanItem.planned_start.label("planned_start"),
                SchoolMonthPlanItem.planned_end.label("planned_end"),
            )
            .select_from(SchoolMonthPlanItemAssignee)
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemAssignee.month_item_id,
            )
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id
                == SchoolStaffRole.staff_member_id,
            )
            .outerjoin(
                User,
                User.staff_member_id == SchoolStaffMember.id,
            )
            .outerjoin(
                SchoolPlanRow11,
                SchoolPlanRow11.id
                == SchoolMonthPlanItem.source_row11_id,
            )
            .where(
                SchoolMonthPlanItem.month_plan_id == month_plan_id,
                SchoolMonthPlanItem.is_included.is_(True),
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.is_active.is_(True),
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .order_by(
                SchoolStaffMember.full_name.asc(),
                SchoolMonthPlanItem.id.asc(),
                SchoolMonthPlanItemAssignee.assignment_kind.asc(),
            )
        )

        result = await db.execute(stmt)
        rows = result.all()

        return [
            MonthPlanNotificationAssignmentRowDTO(
                staff_member_id=int(row.staff_member_id),
                full_name=str(row.full_name or "—"),
                phone=(
                    str(row.phone).strip()
                    if row.phone
                    else None
                ),
                is_registered=row.user_id is not None,
                assignment_kind=str(
                    getattr(
                        row.assignment_kind,
                        "value",
                        row.assignment_kind,
                    )
                ),
                month_item_id=int(row.month_item_id),
                task_title=str(
                    row.task_title
                    or f"Задача №{row.month_item_id}"
                ),
                planned_start=row.planned_start,
                planned_end=row.planned_end,
            )
            for row in rows
        ]

    # =========================================================
    # READ NOTIFICATIONS
    # =========================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        notification_id: int,
    ) -> SchoolMonthPlanNotification | None:
        """
        Получить уведомление по идентификатору.
        """

        stmt = (
            select(SchoolMonthPlanNotification)
            .where(
                SchoolMonthPlanNotification.id == notification_id
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_month_plan_and_staff(
        db: AsyncSession,
        *,
        month_plan_id: int,
        staff_member_id: int,
    ) -> SchoolMonthPlanNotification | None:
        """
        Получить текущее состояние уведомления сотрудника
        по конкретному месячному плану.
        """

        stmt = (
            select(SchoolMonthPlanNotification)
            .where(
                SchoolMonthPlanNotification.month_plan_id
                == month_plan_id,
                SchoolMonthPlanNotification.staff_member_id
                == staff_member_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_month_plan_and_staff_for_update(
        db: AsyncSession,
        *,
        month_plan_id: int,
        staff_member_id: int,
    ) -> SchoolMonthPlanNotification | None:
        """
        Получить уведомление с блокировкой строки FOR UPDATE.

        Метод используется перед увеличением open_count,
        подтверждением или другим изменением состояния.
        """

        stmt = (
            select(SchoolMonthPlanNotification)
            .where(
                SchoolMonthPlanNotification.month_plan_id
                == month_plan_id,
                SchoolMonthPlanNotification.staff_member_id
                == staff_member_id,
            )
            .with_for_update()
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_month_plan(
        db: AsyncSession,
        *,
        month_plan_id: int,
    ) -> list[SchoolMonthPlanNotification]:
        """
        Получить все существующие состояния уведомлений
        месячного плана.
        """

        stmt = (
            select(SchoolMonthPlanNotification)
            .where(
                SchoolMonthPlanNotification.month_plan_id
                == month_plan_id
            )
            .order_by(
                SchoolMonthPlanNotification.staff_member_id.asc()
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_map_by_month_plan(
        cls,
        db: AsyncSession,
        *,
        month_plan_id: int,
    ) -> dict[int, SchoolMonthPlanNotification]:
        """
        Получить состояния уведомлений в виде словаря:

            staff_member_id -> SchoolMonthPlanNotification

        Метод удобен для объединения списка исполнителей
        с уже созданными уведомлениями.
        """

        notifications = await cls.list_by_month_plan(
            db,
            month_plan_id=month_plan_id,
        )

        return {
            notification.staff_member_id: notification
            for notification in notifications
        }

    @staticmethod
    async def list_status_rows(
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
    ) -> list[MonthPlanNotificationStatusDTO]:
        """
        Получить текущие состояния созданных уведомлений
        месячного плана вместе с данными сотрудников.

        В выборку входят только сотрудники, для которых
        уже существует SchoolMonthPlanNotification.
        """

        stmt = (
            select(
                SchoolMonthPlanNotification.staff_member_id.label(
                    "staff_member_id"
                ),
                SchoolStaffMember.full_name.label("full_name"),
                SchoolMonthPlanNotification.phone.label(
                    "notification_phone"
                ),
                User.phone.label("user_phone"),
                User.id.label("user_id"),
                SchoolMonthPlanNotification.status.label("status"),
                SchoolMonthPlanNotification.open_count.label(
                    "open_count"
                ),
                SchoolMonthPlanNotification.opened_at.label(
                    "opened_at"
                ),
                SchoolMonthPlanNotification.confirmed_at.label(
                    "confirmed_at"
                ),
            )
            .select_from(SchoolMonthPlanNotification)
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id
                == SchoolMonthPlanNotification.staff_member_id,
            )
            .outerjoin(
                User,
                User.staff_member_id == SchoolStaffMember.id,
            )
            .where(
                SchoolMonthPlanNotification.month_plan_id
                == month_plan_id,
                SchoolStaffMember.school_id == school_id,
            )
            .order_by(SchoolStaffMember.full_name.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        status_rows: list[MonthPlanNotificationStatusDTO] = []

        for row in rows:
            phone_value = (
                row.notification_phone
                or row.user_phone
            )

            status_value = row.status

            if not isinstance(
                status_value,
                MonthPlanNotificationStatus,
            ):
                status_value = MonthPlanNotificationStatus(
                    status_value
                )

            status_rows.append(
                MonthPlanNotificationStatusDTO(
                    staff_member_id=int(row.staff_member_id),
                    full_name=str(row.full_name or "—"),
                    phone=(
                        str(phone_value).strip()
                        if phone_value
                        else None
                    ),
                    is_registered=row.user_id is not None,
                    status=status_value,
                    open_count=int(row.open_count or 0),
                    opened_at=row.opened_at,
                    confirmed_at=row.confirmed_at,
                )
            )

        return status_rows

    # =========================================================
    # CREATE
    # =========================================================

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        month_plan_id: int,
        staff_member_id: int,
        phone: str | None,
        status: MonthPlanNotificationStatus,
        message_text: str | None = None,
        open_count: int = 0,
        opened_at: datetime | None = None,
        opened_by_user_id: int | None = None,
        confirmed_at: datetime | None = None,
        confirmed_by_user_id: int | None = None,
    ) -> SchoolMonthPlanNotification:
        """
        Создать состояние уведомления сотрудника.

        commit не выполняется. Транзакцией управляет сервис.
        """

        notification = SchoolMonthPlanNotification(
            month_plan_id=month_plan_id,
            staff_member_id=staff_member_id,
            phone=phone,
            status=status,
            message_text=message_text,
            open_count=open_count,
            opened_at=opened_at,
            opened_by_user_id=opened_by_user_id,
            confirmed_at=confirmed_at,
            confirmed_by_user_id=confirmed_by_user_id,
        )

        db.add(notification)

        await db.flush()
        await db.refresh(notification)

        return notification

    # =========================================================
    # UPDATE
    # =========================================================

    @staticmethod
    async def update_message_data(
        db: AsyncSession,
        *,
        notification: SchoolMonthPlanNotification,
        phone: str | None,
        message_text: str | None,
    ) -> SchoolMonthPlanNotification:
        """
        Обновить номер телефона и сохранённый текст сообщения.
        """

        notification.phone = phone
        notification.message_text = message_text

        await db.flush()
        await db.refresh(notification)

        return notification

    @staticmethod
    async def update_status(
        db: AsyncSession,
        *,
        notification: SchoolMonthPlanNotification,
        status: MonthPlanNotificationStatus,
    ) -> SchoolMonthPlanNotification:
        """
        Изменить только статус уведомления.
        """

        notification.status = status

        await db.flush()
        await db.refresh(notification)

        return notification

    @staticmethod
    async def register_open(
        db: AsyncSession,
        *,
        notification: SchoolMonthPlanNotification,
        status: MonthPlanNotificationStatus,
        opened_at: datetime,
        opened_by_user_id: int,
        phone: str | None = None,
        message_text: str | None = None,
    ) -> SchoolMonthPlanNotification:
        """
        Зарегистрировать открытие WhatsApp.

        При каждом открытии:

        - увеличивается open_count;
        - обновляется opened_at;
        - сохраняется пользователь, открывший WhatsApp;
        - обновляется статус;
        - при передаче обновляются телефон и текст сообщения.
        """

        notification.status = status
        notification.open_count = (
            notification.open_count or 0
        ) + 1

        notification.opened_at = opened_at
        notification.opened_by_user_id = opened_by_user_id

        if phone is not None:
            notification.phone = phone

        if message_text is not None:
            notification.message_text = message_text

        await db.flush()
        await db.refresh(notification)

        return notification

    @staticmethod
    async def confirm(
        db: AsyncSession,
        *,
        notification: SchoolMonthPlanNotification,
        status: MonthPlanNotificationStatus,
        confirmed_at: datetime,
        confirmed_by_user_id: int,
    ) -> SchoolMonthPlanNotification:
        """
        Зафиксировать подтверждение исполнителя.
        """

        notification.status = status
        notification.confirmed_at = confirmed_at
        notification.confirmed_by_user_id = confirmed_by_user_id

        await db.flush()
        await db.refresh(notification)

        return notification

    @staticmethod
    async def reset_confirmation(
        db: AsyncSession,
        *,
        notification: SchoolMonthPlanNotification,
        status: MonthPlanNotificationStatus,
    ) -> SchoolMonthPlanNotification:
        """
        Сбросить подтверждение уведомления.

        Используется, например, если после подтверждения
        изменился состав задач сотрудника.
        """

        notification.status = status
        notification.confirmed_at = None
        notification.confirmed_by_user_id = None

        await db.flush()
        await db.refresh(notification)

        return notification

    @staticmethod
    async def reset_open_state(
        db: AsyncSession,
        *,
        notification: SchoolMonthPlanNotification,
        status: MonthPlanNotificationStatus,
    ) -> SchoolMonthPlanNotification:
        """
        Полностью сбросить сведения об открытии WhatsApp
        и подтверждении уведомления.
        """

        notification.status = status

        notification.open_count = 0
        notification.opened_at = None
        notification.opened_by_user_id = None

        notification.confirmed_at = None
        notification.confirmed_by_user_id = None

        await db.flush()
        await db.refresh(notification)

        return notification

    # =========================================================
    # DELETE
    # =========================================================

    @staticmethod
    async def delete(
        db: AsyncSession,
        *,
        notification: SchoolMonthPlanNotification,
    ) -> None:
        """
        Удалить одно состояние уведомления.
        """

        await db.delete(notification)
        await db.flush()

    @staticmethod
    async def delete_by_month_plan_and_staff(
        db: AsyncSession,
        *,
        month_plan_id: int,
        staff_member_id: int,
    ) -> int:
        """
        Удалить уведомление конкретного сотрудника
        по месячному плану.

        Возвращает количество удалённых строк.
        """

        stmt = (
            delete(SchoolMonthPlanNotification)
            .where(
                SchoolMonthPlanNotification.month_plan_id
                == month_plan_id,
                SchoolMonthPlanNotification.staff_member_id
                == staff_member_id,
            )
        )

        result = await db.execute(stmt)
        await db.flush()

        return int(result.rowcount or 0)

    @staticmethod
    async def delete_by_month_plan(
        db: AsyncSession,
        *,
        month_plan_id: int,
    ) -> int:
        """
        Удалить все состояния уведомлений месячного плана.

        Возвращает количество удалённых строк.
        """

        stmt = (
            delete(SchoolMonthPlanNotification)
            .where(
                SchoolMonthPlanNotification.month_plan_id
                == month_plan_id
            )
        )

        result = await db.execute(stmt)
        await db.flush()

        return int(result.rowcount or 0)

    @staticmethod
    async def get_notification_progress(
            db: AsyncSession,
            *,
            month_plan_id: int,
            school_id: int,
    ) -> MonthPlanNotificationProgressDTO:
        """
        Получить сводное состояние уведомлений исполнителей
        выбранного месячного плана.

        Общее количество получателей определяется по актуальным
        назначениям включённых задач месячного плана.

        Один сотрудник учитывается один раз независимо от:
        - количества назначенных задач;
        - назначения ответственным;
        - назначения соисполнителем.

        Состояния:

        - PENDING:
          запись уведомления отсутствует либо имеет статус pending;

        - SENT:
          уведомление отправлено через WhatsApp;

        - ACCEPTED:
          ответственный исполнитель принял задачу в исполнение.

        PostgreSQL ENUM явно приводится к VARCHAR. Это исключает
        несовпадение между именем Python Enum, например SENT,
        и значением PostgreSQL ENUM — sent.
        """

        recipients_subquery = (
            select(
                SchoolStaffMember.id.label("staff_member_id")
            )
            .select_from(SchoolMonthPlanItemAssignee)
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemAssignee.month_item_id,
            )
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id
                == SchoolStaffRole.staff_member_id,
            )
            .where(
                SchoolMonthPlanItem.month_plan_id == month_plan_id,
                SchoolMonthPlanItem.is_included.is_(True),

                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.is_active.is_(True),

                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .distinct()
            .subquery()
        )

        notification_status_text = cast(
            SchoolMonthPlanNotification.status,
            String,
        )

        stmt = (
            select(
                func.count(
                    recipients_subquery.c.staff_member_id
                ).label("total_recipients"),

                func.count().filter(
                    or_(
                        SchoolMonthPlanNotification.id.is_(None),
                        notification_status_text
                        == MonthPlanNotificationStatus.PENDING.value,
                    )
                ).label("pending_count"),

                func.count().filter(
                    notification_status_text
                    == MonthPlanNotificationStatus.SENT.value
                ).label("sent_count"),

                func.count().filter(
                    notification_status_text
                    == MonthPlanNotificationStatus.ACCEPTED.value
                ).label("accepted_count"),
            )
            .select_from(recipients_subquery)
            .outerjoin(
                SchoolMonthPlanNotification,
                and_(
                    SchoolMonthPlanNotification.month_plan_id
                    == month_plan_id,
                    SchoolMonthPlanNotification.staff_member_id
                    == recipients_subquery.c.staff_member_id,
                ),
            )
        )

        row = (
            await db.execute(stmt)
        ).one()

        return MonthPlanNotificationProgressDTO(
            total_recipients=int(
                row.total_recipients or 0
            ),
            pending_count=int(
                row.pending_count or 0
            ),
            sent_count=int(
                row.sent_count or 0
            ),
            accepted_count=int(
                row.accepted_count or 0
            ),
        )
