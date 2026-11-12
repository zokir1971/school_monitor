# app/modules/planning/repositories/month_plan_notification_repo.py

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import update, exists
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.modules.planning.models_month_plan import SchoolMonthPlan
from app.modules.planning.models_school import SchoolPlan
from app.modules.planning.models_month_plan_notification import SchoolMonthPlanInternalNotice

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
        staff_member_id: int | None = None,
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
                User.is_active.label("account_active"),
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

        if staff_member_id is not None:
            stmt = stmt.where(SchoolStaffMember.id == staff_member_id)
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
                is_registered=row.user_id is not None and bool(row.account_active),
                user_id=row.user_id, is_account_active=bool(row.account_active),
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

    @classmethod
    async def ensure_for_update(
        cls,
        db: AsyncSession,
        *,
        month_plan_id: int,
        staff_member_id: int,
    ) -> SchoolMonthPlanNotification:
        """Create an unsent state atomically, then lock it for acceptance/opening.

        Authorization is performed by the caller before this method. The existing
        unique (plan, staff) key prevents duplicate rows on concurrent requests.
        No WhatsApp sending or opening is recorded by this operation.
        """
        if db.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif db.bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise ValueError("Unsupported notification database dialect")
        table = SchoolMonthPlanNotification.__table__
        statement = insert(table).values(
            month_plan_id=month_plan_id,
            staff_member_id=staff_member_id,
            status=MonthPlanNotificationStatus.PENDING,
            open_count=0,
        ).on_conflict_do_nothing(
            index_elements=[table.c.month_plan_id, table.c.staff_member_id],
        )
        await db.execute(statement)
        notification = await cls.get_by_month_plan_and_staff_for_update(
            db, month_plan_id=month_plan_id, staff_member_id=staff_member_id,
        )
        if notification is None:
            raise RuntimeError("Notification state missing after atomic creation")
        return notification

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


    @staticmethod
    async def internal_plan(db, *, school_id, month_plan_id, lock=False):
        m, p = SchoolMonthPlan.__table__, SchoolPlan.__table__
        stmt = select(m, p.c.status.label('annual_status')).join(p, p.c.id == m.c.school_plan_id).where(m.c.id == month_plan_id, p.c.school_id == school_id)
        if lock:
            stmt = stmt.with_for_update(of=m)
        return (await db.execute(stmt)).mappings().first()

    @staticmethod
    async def internal_parents(db, *, month_plan_id, staff_ids):
        n = SchoolMonthPlanNotification.__table__
        if staff_ids:
            await db.execute(pg_insert(n).on_conflict_do_nothing(index_elements=['month_plan_id','staff_member_id']), [dict(month_plan_id=month_plan_id, staff_member_id=s, status=MonthPlanNotificationStatus.PENDING, open_count=0) for s in sorted(staff_ids)])
        return list((await db.execute(select(n).where(n.c.month_plan_id == month_plan_id).order_by(n.c.id).with_for_update())).mappings())

    @staticmethod
    async def internal_latest(db, *, month_plan_id):
        e, n = SchoolMonthPlanInternalNotice.__table__, SchoolMonthPlanNotification.__table__
        stmt = select(e, n.c.staff_member_id).join(n, n.c.id == e.c.notification_id).where(n.c.month_plan_id == month_plan_id).distinct(e.c.notification_id).order_by(e.c.notification_id, e.c.id.desc())
        return list((await db.execute(stmt)).mappings())

    @staticmethod
    async def internal_insert(db, rows):
        if rows:
            await db.execute(SchoolMonthPlanInternalNotice.__table__.insert(), rows)

    @staticmethod
    def internal_access(user):
        # Only current, active assignments of this user's own school/staff profile.
        e, n = SchoolMonthPlanInternalNotice.__table__, SchoolMonthPlanNotification.__table__
        i, a = SchoolMonthPlanItem.__table__, SchoolMonthPlanItemAssignee.__table__
        r, s = SchoolStaffRole.__table__, SchoolStaffMember.__table__
        m, p = SchoolMonthPlan.__table__, SchoolPlan.__table__
        live_assignment = exists(select(a.c.id).join(i, i.c.id == a.c.month_item_id).join(r, r.c.id == a.c.staff_role_id).join(s, s.c.id == r.c.staff_member_id).where(i.c.month_plan_id == n.c.month_plan_id, i.c.is_included.is_(True), r.c.staff_member_id == user.staff_member_id, r.c.school_id == user.school_id, r.c.is_active.is_(True), s.c.is_active.is_(True), s.c.school_id == user.school_id))
        return select(e, n.c.month_plan_id, m.c.year, m.c.month).join(n,n.c.id == e.c.notification_id).join(m,m.c.id == n.c.month_plan_id).join(p,p.c.id == m.c.school_plan_id).where(e.c.recipient_user_id == user.id, n.c.staff_member_id == user.staff_member_id, p.c.school_id == user.school_id, m.c.status == 'active', p.c.status != 'archived', live_assignment)

    @classmethod
    async def internal_inbox(cls, db, *, user, page=1, count_only=False):
        # Latest version per parent, scoped before aggregation.
        accessible = cls.internal_access(user).subquery()
        latest = select(accessible.c.notification_id, func.max(accessible.c.id).label('id')).group_by(accessible.c.notification_id).subquery()
        stmt = select(accessible).join(latest, latest.c.id == accessible.c.id)
        if count_only:
            return int((await db.scalar(select(func.count()).select_from(stmt.where(accessible.c.read_at.is_(None)).subquery()))) or 0)
        return list((await db.execute(stmt.order_by(accessible.c.sent_at.desc(),accessible.c.id.desc()).limit(21).offset((page-1)*20))).mappings())

    @classmethod
    async def internal_detail(cls, db, *, user, notice_id):
        e = SchoolMonthPlanInternalNotice.__table__
        return (await db.execute(cls.internal_access(user).where(e.c.id == notice_id))).mappings().first()

    @classmethod
    async def internal_mark_read(cls, db, *, user, notice_id):
        e = SchoolMonthPlanInternalNotice.__table__
        allowed = cls.internal_access(user).with_only_columns(e.c.id)
        result = await db.execute(update(e).where(e.c.id == notice_id, e.c.id.in_(allowed)).values(read_at=func.coalesce(e.c.read_at,func.now())))
        return bool(result.rowcount)
