# app/modules/planning/services/month_plan_notification_service.py

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
import hashlib
import json
from urllib.parse import quote_plus

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.phone import normalize_kz_phone
from app.modules.planning.enums import (
    AssignmentKind,
    MonthPlanNotificationStatus,
)
from app.modules.planning.models_month_plan_notification import (
    SchoolMonthPlanNotification,
)
from app.modules.planning.repositories.month_plan_notification_repo import (
    SchoolMonthPlanNotificationRepo,
)
from app.modules.planning.schemas.month_plan_notification_dto import (
    MonthPlanNotificationProgressDTO,
    MonthPlanNotificationRecipientDTO,
    MonthPlanNotificationStatusDTO,
    MonthPlanNotificationTaskDTO,
)


class MonthPlanNotificationService:
    """
    Сервис WhatsApp-уведомлений исполнителей
    включённых задач месячного плана.

    Репозиторий выполняет запросы и изменяет модели.

    Сервис:

    - группирует плоские строки назначений по сотрудникам;
    - разделяет задачи ответственного и соисполнителя;
    - удаляет возможные дубли задач;
    - формирует персональный текст уведомления;
    - формирует ссылку wa.me;
    - фиксирует отправку через WhatsApp;
    - увеличивает open_count;
    - фиксирует принятие задачи исполнителем;
    - возвращает сводный прогресс уведомлений;
    - управляет бизнес-переходами статусов.

    commit внутри сервиса не выполняется. Границей транзакции
    управляет маршрут или вызывающий application-сервис.
    """

    # =========================================================
    # MESSAGE
    # =========================================================

    @staticmethod
    def build_message(
        *,
        recipient: MonthPlanNotificationRecipientDTO,
        platform_url: str,
        school_name: str | None = None,
        language: str = "kk",
    ) -> str:
        from app.core.monthly_notification_message import build_monthly_notification_message
        return build_monthly_notification_message(
            recipient=recipient, platform_url=platform_url,
            school_name=school_name, language=language,
        )

    @staticmethod
    def build_whatsapp_url(
        *,
        phone: str,
        message: str,
    ) -> str:
        """
        Сформировать ссылку wa.me с готовым сообщением.
        """

        normalized_phone = normalize_kz_phone(phone)

        if not normalized_phone:
            raise ValueError("Некорректный номер телефона.")

        encoded_message = quote_plus(message)

        return (
            f"https://wa.me/{normalized_phone}"
            f"?text={encoded_message}"
        )

    # =========================================================
    # RECIPIENTS
    # =========================================================

    @classmethod
    async def list_recipients(
        cls,
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
    ) -> list[MonthPlanNotificationRecipientDTO]:
        """
        Получить уникальных исполнителей включённых задач.

        Репозиторий возвращает плоские строки назначений.
        Сервис группирует их по сотрудникам и разделяет
        задачи по виду назначения.
        """

        assignment_rows = await (
            SchoolMonthPlanNotificationRepo
            .list_notification_assignment_rows(
                db,
                month_plan_id=month_plan_id,
                school_id=school_id,
            )
        )

        recipients_by_staff: dict[
            int,
            MonthPlanNotificationRecipientDTO,
        ] = {}

        seen_primary_tasks: dict[int, set[int]] = {}
        seen_co_executor_tasks: dict[int, set[int]] = {}

        for assignment_row in assignment_rows:
            staff_member_id = assignment_row.staff_member_id

            recipient = recipients_by_staff.get(staff_member_id)

            if recipient is None:
                recipient = MonthPlanNotificationRecipientDTO(
                    staff_member_id=staff_member_id,
                    full_name=assignment_row.full_name,
                    is_registered=assignment_row.is_registered,
                    phone=assignment_row.phone,
                    user_id=assignment_row.user_id,
                )

                recipients_by_staff[staff_member_id] = recipient
                seen_primary_tasks[staff_member_id] = set()
                seen_co_executor_tasks[staff_member_id] = set()

            task_dto = MonthPlanNotificationTaskDTO(
                month_item_id=assignment_row.month_item_id,
                title=assignment_row.task_title,
                planned_start=assignment_row.planned_start,
                planned_end=assignment_row.planned_end,
            )

            if (
                assignment_row.assignment_kind
                == AssignmentKind.PRIMARY.value
            ):
                if (
                    task_dto.month_item_id
                    not in seen_primary_tasks[staff_member_id]
                ):
                    recipient.primary_tasks.append(task_dto)
                    seen_primary_tasks[staff_member_id].add(
                        task_dto.month_item_id
                    )

                continue

            if (
                assignment_row.assignment_kind
                == AssignmentKind.CO_EXECUTOR.value
            ):
                if (
                    task_dto.month_item_id
                    not in seen_co_executor_tasks[staff_member_id]
                ):
                    recipient.co_executor_tasks.append(task_dto)
                    seen_co_executor_tasks[staff_member_id].add(
                        task_dto.month_item_id
                    )

        return sorted(
            recipients_by_staff.values(),
            key=lambda recipient_dto: (
                recipient_dto.full_name.casefold(),
                recipient_dto.staff_member_id,
            ),
        )

    @classmethod
    async def get_recipient(
        cls,
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
        staff_member_id: int,
    ) -> MonthPlanNotificationRecipientDTO:
        """
        Получить одного исполнителя и проверить, что он:

        - принадлежит школе;
        - назначен на включённые задачи;
        - относится к указанному месячному плану.
        """

        recipients = await cls.list_recipients(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )

        recipient = next(
            (
                recipient_item
                for recipient_item in recipients
                if (
                    recipient_item.staff_member_id
                    == staff_member_id
                )
            ),
            None,
        )

        if recipient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Исполнитель не найден среди "
                    "включённых задач месячного плана."
                ),
            )

        return recipient

    # =========================================================
    # STATUS LIST
    # =========================================================

    @staticmethod
    async def list_notification_statuses(
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
    ) -> list[MonthPlanNotificationStatusDTO]:
        """
        Получить созданные состояния уведомлений
        выбранного месячного плана.
        """

        return await SchoolMonthPlanNotificationRepo.list_status_rows(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )

    @staticmethod
    async def get_notification_progress(
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
    ) -> MonthPlanNotificationProgressDTO:
        """
        Получить сводный прогресс уведомлений месячного плана.

        Репозиторий считает:

        - total_recipients — уникальные исполнители;
        - pending_count — уведомление ещё не отправлено;
        - sent_count — уведомление отправлено;
        - accepted_count — задача принята к исполнению.
        """

        return await (
            SchoolMonthPlanNotificationRepo
            .get_notification_progress(
                db,
                month_plan_id=month_plan_id,
                school_id=school_id,
            )
        )

    # =========================================================
    # SEND WHATSAPP
    # =========================================================
    @classmethod
    async def open_recipient_whatsapp(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
            school_id: int,
            staff_member_id: int,
            phone: str,
            platform_url: str,
            opened_by_user_id: int,
            school_name: str | None = None,
            language: str = "kk",
    ) -> str:
        """
        Подготовить WhatsApp-сообщение и зафиксировать отправку.

        Сценарий:

        1. Проверить получателя и его назначения.
        2. Проверить и нормализовать телефон.
        3. Сформировать персональное сообщение.
        4. Создать состояние уведомления или обновить существующее.
        5. Увеличить open_count.
        6. Вернуть ссылку wa.me.

        При первом открытии устанавливается статус SENT.

        Если задача уже принята и уведомление имеет статус ACCEPTED,
        повторное открытие WhatsApp увеличивает open_count, но не
        понижает статус обратно до SENT.
        """

        recipient = await cls.get_recipient(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
        )

        normalized_phone = normalize_kz_phone(phone)

        if not normalized_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Введите номер телефона в формате "
                    "+7 700 123 45 67."
                ),
            )

        message = cls.build_message(
            recipient=recipient,
            platform_url=platform_url,
            school_name=school_name,
            language=language,
        )

        opened_at = datetime.now(timezone.utc)

        notification = await (
            SchoolMonthPlanNotificationRepo
            .ensure_for_update(
                db,
                month_plan_id=month_plan_id,
                staff_member_id=staff_member_id,
            )
        )

        next_status = (
            MonthPlanNotificationStatus.ACCEPTED
            if notification.status == MonthPlanNotificationStatus.ACCEPTED
            else MonthPlanNotificationStatus.SENT
        )
        await SchoolMonthPlanNotificationRepo.register_open(
            db,
            notification=notification,
            status=next_status,
            opened_at=opened_at,
            opened_by_user_id=opened_by_user_id,
            phone=normalized_phone,
            message_text=message,
        )

        return cls.build_whatsapp_url(
            phone=normalized_phone,
            message=message,
        )

    @classmethod
    async def build_recipient_whatsapp_url(
        cls,
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
        staff_member_id: int,
        phone: str,
        platform_url: str,
        opened_by_user_id: int,
        school_name: str | None = None,
        language: str = "kk",
    ) -> str:
        """
        Совместимое имя старого метода.

        Новый основной сценарий находится в
        open_recipient_whatsapp(). Метод также фиксирует отправку
        уведомления в базе данных.
        """

        return await cls.open_recipient_whatsapp(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
            phone=phone,
            platform_url=platform_url,
            opened_by_user_id=opened_by_user_id,
            school_name=school_name,
            language=language,
        )

    # =========================================================
    # ACCEPT TASK
    # =========================================================

    @classmethod
    async def accept_notification(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
            school_id: int,
            staff_member_id: int,
            accepted_by_user_id: int,
    ) -> SchoolMonthPlanNotification:
        """
        Зафиксировать принятие задачи ответственным исполнителем.

        Вызывается после проверки, что сотрудник назначен
        ответственным исполнителем PRIMARY, и после перевода
        задачи в статус IN_PROGRESS.

        Commit выполняется вызывающим маршрутом.
        """

        await cls.get_recipient(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
        )

        notification = await (
            SchoolMonthPlanNotificationRepo
            .ensure_for_update(
                db,
                month_plan_id=month_plan_id,
                staff_member_id=staff_member_id,
            )
        )

        if (
                notification.status
                == MonthPlanNotificationStatus.ACCEPTED
        ):
            return notification

        return await SchoolMonthPlanNotificationRepo.confirm(
            db,
            notification=notification,
            status=MonthPlanNotificationStatus.ACCEPTED,
            confirmed_at=datetime.now(timezone.utc),
            confirmed_by_user_id=accepted_by_user_id,
        )

    @classmethod
    async def confirm_notification(
        cls,
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
        staff_member_id: int,
        confirmed_by_user_id: int,
    ) -> SchoolMonthPlanNotification:
        """
        Совместимое имя старого метода.

        Новый основной метод — accept_notification().
        """

        return await cls.accept_notification(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
            accepted_by_user_id=confirmed_by_user_id,
        )

    # =========================================================
    # RESET
    # =========================================================

    @classmethod
    async def reset_notification_confirmation(
        cls,
        db: AsyncSession,
        *,
        month_plan_id: int,
        school_id: int,
        staff_member_id: int,
    ) -> SchoolMonthPlanNotification:
        """
        Сбросить принятие задачи, сохранив историю отправок.

        После сброса:

        - confirmed_at очищается;
        - confirmed_by_user_id очищается;
        - если WhatsApp ранее открывался, статус становится SENT.
        """

        await cls.get_recipient(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
        )

        notification = await (
            SchoolMonthPlanNotificationRepo
            .get_by_month_plan_and_staff_for_update(
                db,
                month_plan_id=month_plan_id,
                staff_member_id=staff_member_id,
            )
        )

        if notification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Состояние уведомления не найдено.",
            )

        return await (
            SchoolMonthPlanNotificationRepo.reset_confirmation(
                db,
                notification=notification,
                status=MonthPlanNotificationStatus.SENT,
            )
        )

    @classmethod
    async def reset_notification_state(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
            school_id: int,
            staff_member_id: int,
    ) -> None:
        """
        Полностью сбросить состояние уведомления.

        После сброса уведомление снова считается
        неотправленным.
        """

        await cls.get_recipient(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
        )

        notification = await (
            SchoolMonthPlanNotificationRepo
            .get_by_month_plan_and_staff_for_update(
                db,
                month_plan_id=month_plan_id,
                staff_member_id=staff_member_id,
            )
        )

        if notification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Уведомление исполнителя не найдено.",
            )

        await SchoolMonthPlanNotificationRepo.reset_open_state(
            db,
            notification=notification,
            status=MonthPlanNotificationStatus.PENDING,
        )


    @staticmethod
    def internal_payload(rows, plan):
        tasks = sorted([dict(id=r.month_item_id, title=r.task_title, kind=r.assignment_kind,
            start=r.planned_start.isoformat() if r.planned_start else None,
            end=r.planned_end.isoformat() if r.planned_end else None) for r in rows], key=lambda t:(t['id'],t['kind']))
        # A person can have several role records; a task/kind occurs only once.
        tasks = list({(t['id'],t['kind']):t for t in tasks}.values())
        payload = dict(month=plan['month'],year=plan['year'],tasks=tasks)
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        return payload, digest

    @classmethod
    async def send_internal(cls, db, *, school_id, month_plan_id, actor_id):
        repo = SchoolMonthPlanNotificationRepo
        plan = await repo.internal_plan(db,school_id=school_id,month_plan_id=month_plan_id,lock=True)
        if not plan:
            raise HTTPException(404,'План не найден / Жоспар табылмады')
        if str(getattr(plan['status'],'value',plan['status'])) != 'active' or str(getattr(plan['annual_status'],'value',plan['annual_status'])) == 'archived':
            raise HTTPException(409,'Сначала отправьте месячный план на исполнение / Алдымен айлық жоспарды орындауға жіберіңіз')
        source = await repo.list_notification_assignment_rows(db,school_id=school_id,month_plan_id=month_plan_id)
        groups, unregistered = {}, set()
        for row in source:
            if not row.is_registered or not row.is_account_active or not row.user_id:
                unregistered.add(row.staff_member_id)
            else:
                groups.setdefault(row.staff_member_id,[]).append(row)
        parents = {n['staff_member_id']:n for n in await repo.internal_parents(db,month_plan_id=month_plan_id,staff_ids=set(groups))}
        previous = {n['staff_member_id']:n for n in await repo.internal_latest(db,month_plan_id=month_plan_id)}
        inserts, created, changed, unchanged = [], 0, 0, 0
        for staff_id, rows in groups.items():
            payload,digest = cls.internal_payload(rows,plan)
            old = previous.get(staff_id)
            if old and old['digest'] == digest and old['recipient_user_id'] == rows[0].user_id:
                unchanged += 1
                continue
            created += int(old is None); changed += int(old is not None)
            inserts.append(dict(notification_id=parents[staff_id]['id'],recipient_user_id=rows[0].user_id,
                revision=old['revision']+1 if old else 1,digest=digest,payload=payload,sent_by_user_id=actor_id))
        await repo.internal_insert(db,inserts)
        return dict(created=created,changed=changed,unchanged=unchanged,unregistered=len(unregistered))

    @staticmethod
    def internal_identity(user):
        if not user.school_id or not user.staff_member_id:
            raise HTTPException(403,'Нет профиля сотрудника школы / Мектеп қызметкерінің профилі жоқ')

    @classmethod
    async def internal_notice(cls, db, *, user, notice_id):
        cls.internal_identity(user)
        row = await SchoolMonthPlanNotificationRepo.internal_detail(db,user=user,notice_id=notice_id)
        if not row:
            raise HTTPException(404,'Уведомление не найдено / Хабарлама табылмады')
        current = await SchoolMonthPlanNotificationRepo.list_notification_assignment_rows(db,
            school_id=user.school_id,month_plan_id=row['month_plan_id'],staff_member_id=user.staff_member_id)
        allowed = {t.month_item_id for t in current}
        result = dict(row)
        result['payload'] = dict(row['payload'],tasks=[t for t in row['payload']['tasks'] if t['id'] in allowed])
        return cls.internal_display(result)


    @staticmethod
    async def internal_statuses(db, *, school_id, month_plan_id, recipients):
        plan = await SchoolMonthPlanNotificationRepo.internal_plan(db,school_id=school_id,month_plan_id=month_plan_id)
        if not plan:
            raise HTTPException(404,'План не найден / Жоспар табылмады')
        rows = await SchoolMonthPlanNotificationRepo.internal_latest(db,month_plan_id=month_plan_id)
        current = {r.staff_member_id:r for r in recipients}
        result = []
        for row in rows:
            recipient = current.get(row['staff_member_id'])
            tasks = []
            if recipient:
                for kind, group in [('primary',recipient.primary_tasks),('co_executor',recipient.co_executor_tasks)]:
                    tasks.extend(SimpleNamespace(month_item_id=t.month_item_id,task_title=t.title,
                        assignment_kind=kind,planned_start=t.planned_start,planned_end=t.planned_end) for t in group)
            _, digest = MonthPlanNotificationService.internal_payload(tasks,plan)
            notice = MonthPlanNotificationService.internal_display(dict(row))
            notice['stale'] = not recipient or digest != row['digest'] or row['recipient_user_id'] != recipient.user_id
            result.append(notice)
        return result

    @staticmethod
    def internal_display(row):
        result = dict(row)
        for key in ('sent_at','read_at'):
            if result.get(key):
                result[key] = result[key].astimezone(timezone(timedelta(hours=5)))
        if 'payload' in result:
            result['payload'] = dict(result['payload'],tasks=[dict(t,
                start_text=date.fromisoformat(t['start']).strftime('%d.%m.%Y') if t.get('start') else '—',
                end_text=date.fromisoformat(t['end']).strftime('%d.%m.%Y') if t.get('end') else '—') for t in result['payload']['tasks']])
        return result


    @staticmethod
    def internal_summary(recipients, notices):
        people = {r.staff_member_id:r for r in recipients}
        registered = {sid for sid,r in people.items() if r.is_registered}
        latest = {n['staff_member_id']:n for n in notices}
        current = [latest[sid] for sid in registered if sid in latest and not latest[sid].get('stale',False)]
        read = sum(n['read_at'] is not None for n in current)
        return dict(total=len(people),registered=len(registered),notified=len(current),read=read,
            unread=len(current)-read,pending=len(registered)-len(current),no_account=len(people)-len(registered))
