# app/modules/planning/services/month_plan_notification_service.py

from __future__ import annotations

from datetime import datetime, timezone
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
    ) -> str:
        """
        Сформировать персональное WhatsApp-сообщение
        исполнителю задач месячного плана.
        """

        lines: list[str] = [
            f"Сәлеметсіз бе, {recipient.full_name}!",
            "",
            (
                "School Monitor жүйесінде Сізге "
                "жаңа тапсырмалар тағайындалды."
            ),
        ]

        if school_name:
            lines.extend(
                [
                    "",
                    f"🏫 Мектеп: {school_name}",
                ]
            )

        if recipient.primary_tasks:
            lines.extend(
                [
                    "",
                    "📌 Жауапты ретінде:",
                ]
            )

            for task in recipient.primary_tasks:
                lines.extend(
                    [
                        f"• {task.title}",
                        (
                            "  🕒 Орындау мерзімі: "
                            f"{task.deadline_text}"
                        ),
                    ]
                )

        if recipient.co_executor_tasks:
            lines.extend(
                [
                    "",
                    "👥 Бірлескен орындаушы ретінде:",
                ]
            )

            for task in recipient.co_executor_tasks:
                lines.extend(
                    [
                        f"• {task.title}",
                        (
                            "  🕒 Орындау мерзімі: "
                            f"{task.deadline_text}"
                        ),
                    ]
                )

        lines.extend(
            [
                "",
                (
                    "📊 Барлық тапсырмалар саны: "
                    f"{recipient.task_count}"
                ),
                "",
                "🔗 School Monitor жүйесіне кіру:",
                platform_url.rstrip("/"),
                "",
                (
                    "Егер жүйеде алғаш рет жұмыс жасайтын "
                    "болсаңыз, алдымен тіркеліп, кейін "
                    "жүйеге кіріңіз."
                ),
                "",
                (
                    "Бұл хабарлама School Monitor жүйесі "
                    "арқылы автоматты түрде жіберілді."
                ),
            ]
        )

        return "\n".join(lines)

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
        )

        opened_at = datetime.now(timezone.utc)

        notification = await (
            SchoolMonthPlanNotificationRepo
            .get_by_month_plan_and_staff_for_update(
                db,
                month_plan_id=month_plan_id,
                staff_member_id=staff_member_id,
            )
        )

        if notification is None:
            await SchoolMonthPlanNotificationRepo.create(
                db,
                month_plan_id=month_plan_id,
                staff_member_id=staff_member_id,
                phone=normalized_phone,
                status=MonthPlanNotificationStatus.SENT,
                message_text=message,
                open_count=1,
                opened_at=opened_at,
                opened_by_user_id=opened_by_user_id,
            )

        else:
            next_status = (
                MonthPlanNotificationStatus.ACCEPTED
                if (
                        notification.status
                        == MonthPlanNotificationStatus.ACCEPTED
                )
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
            .get_by_month_plan_and_staff_for_update(
                db,
                month_plan_id=month_plan_id,
                staff_member_id=staff_member_id,
            )
        )

        if notification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Уведомление этому исполнителю "
                    "ещё не было отправлено."
                ),
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
