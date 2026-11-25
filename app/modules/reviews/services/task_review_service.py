# app/modules/tasks/task_review_service.py
from __future__ import annotations
from app.modules.planning.content_i18n import content_text

import logging
import re
from datetime import date, timezone, datetime
from pathlib import Path
from typing import cast

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.storage import get_storage, SchoolStorageContext  # путь проверьте по своему проекту
from app.core.storage.school_storage import SchoolStorageService
from app.modules.planning.enums import PlanItemStatus, ReviewPlace, PlanStatus, AssignmentKind
from app.modules.planning.models_month_plan import SchoolMonthPlanItem, SchoolMonthPlanItemAssignee
from app.modules.reviews.models_task_review import (
    SchoolMonthPlanItemReviewResult,
    SchoolTaskReview,
)
from app.modules.reviews.task_review_dto import (
    TaskReviewBatchCreateDTO,
    TaskReviewCreateDTO,
    TaskReviewSelectionItemDTO,
    TaskReviewSelectionPageDTO,
    MethodAssociationSelectionItemDTO,
)
from app.modules.reviews.repositories.task_review_repo import TaskReviewRepository
from app.modules.users.enums import UserRole
from app.modules.users.models import User

logger = logging.getLogger(__name__)


class TaskReviewService:

    @staticmethod
    async def _authorize_plan(db: AsyncSession, *, user: User, school_plan_id: int):
        if user.role != UserRole.SCHOOL_ADMIN or user.school_id is None:
            raise HTTPException(403, "Рассмотрение задач доступно администратору своей школы.")
        plan = await TaskReviewRepository.get_school_plan_by_id(db, school_plan_id=school_plan_id)
        if plan is None or plan.school_id != user.school_id or plan.status != PlanStatus.ACTIVE:
            raise HTTPException(403, "Нет доступа к активному плану выбранной школы.")
        return plan

    @staticmethod
    async def cleanup_protocol_file(object_key: str) -> None:
        try:
            await SchoolStorageService(storage=get_storage()).delete(object_key=object_key)
        except Exception:
            logger.warning("Не удалось удалить новый файл протокола после отката.", exc_info=True)

    @staticmethod
    def _get_task_name(
            item: SchoolMonthPlanItem,
    ) -> str:
        """
        Возвращает отображаемое название задачи.
        """

        source = item.source_row11

        if source is None:
            return f"Задача №{item.id}"

        return (
                getattr(source, "task_name", None)
                or getattr(source, "title", None)
                or content_text(source,"topic")
                or getattr(source, "control_topic", None)
                or getattr(source, "activity", None)
                or getattr(source, "content", None)
                or getattr(source, "name", None)
                or f"Задача №{item.id}"
        )

    @staticmethod
    def _assignee_sort_key(
            assignment: SchoolMonthPlanItemAssignee,
    ) -> tuple[int, str]:
        """
        Формирует ключ сортировки исполнителей.

        Основной исполнитель выводится первым,
        затем соисполнители в алфавитном порядке.
        """

        staff_role = assignment.staff_role

        staff_member = (
            staff_role.staff_member
            if staff_role is not None
            else None
        )

        full_name = (
            str(staff_member.full_name or "").strip()
            if staff_member is not None
            else ""
        )

        priority = (
            0
            if assignment.assignment_kind == AssignmentKind.PRIMARY
            else 1
        )

        return priority, full_name.casefold()

    @classmethod
    def _get_responsible_name(
            cls,
            item: SchoolMonthPlanItem,
    ) -> str:
        """
        Возвращает ФИО всех назначенных исполнителей задачи.

        Негізгі орындаушы выводится первым,
        затем Қосалқы орындаушы.
        """

        assignees = list(item.assignees or [])

        if not assignees:
            return "Не назначены"

        assignees.sort(
            key=cls._assignee_sort_key,
        )

        prepared_names: list[str] = []

        for assignment in assignees:
            staff_role = assignment.staff_role

            if staff_role is None:
                continue

            staff_member = staff_role.staff_member

            if staff_member is None:
                continue

            full_name = str(
                staff_member.full_name or ""
            ).strip()

            if not full_name:
                continue

            assignment_kind = assignment.assignment_kind

            if assignment_kind == AssignmentKind.PRIMARY:
                assignment_label = AssignmentKind.PRIMARY.label_kz

            elif assignment_kind == AssignmentKind.CO_EXECUTOR:
                assignment_label = AssignmentKind.CO_EXECUTOR.label_kz

            else:
                assignment_label = getattr(
                    assignment_kind,
                    "label_kz",
                    str(assignment_kind),
                )

            prepared_names.append(
                f"{full_name} — {assignment_label}"
            )

        if not prepared_names:
            return "Не назначены"

        return "; ".join(prepared_names)

    @staticmethod
    def _build_planned_period_text(
            planned_start: date | None,
            planned_end: date | None,
    ) -> str:
        """
        Формирует текст планового срока выполнения задачи.
        """

        if planned_start and planned_end:
            if planned_start == planned_end:
                return planned_start.strftime("%d.%m.%Y")

            return (
                f"{planned_start.strftime('%d.%m.%Y')} – "
                f"{planned_end.strftime('%d.%m.%Y')}"
            )

        if planned_start:
            return planned_start.strftime("%d.%m.%Y")

        if planned_end:
            return f"до {planned_end.strftime('%d.%m.%Y')}"

        return "—"

    @staticmethod
    def _get_status_value(
            status: PlanItemStatus,
    ) -> str:
        """
        Возвращает значение статуса.
        """

        return status.value

    @staticmethod
    def _get_status_label(
            status: PlanItemStatus,
    ) -> str:
        """
        Возвращает отображаемое название статуса.
        """

        return getattr(status, "label_kz", str(status))

    @staticmethod
    def _can_select_for_review(
            item: SchoolMonthPlanItem,
    ) -> bool:
        """
        Определяет, можно ли выбрать задачу
        для пакетного рассмотрения.
        """
        return item.status in {
            PlanItemStatus.DONE,
            PlanItemStatus.NOT_EXECUTED,
        }

    @staticmethod
    def _get_expected_result_label(
            status: PlanItemStatus,
    ) -> str:
        """
        Возвращает результат, который будет установлен
        после пакетного рассмотрения.
        """

        if status == PlanItemStatus.DONE:
            return "Будет рассмотрена"

        if status in {
            PlanItemStatus.TODO,
            PlanItemStatus.IN_PROGRESS,
        }:
            return "Будет окончательно отмечена как не выполненная"

        if status == PlanItemStatus.NOT_EXECUTED:
            return "Останется окончательно не выполненной"

        return "Недоступно"

    @classmethod
    def _build_selection_item(
            cls,
            item: SchoolMonthPlanItem,
    ) -> TaskReviewSelectionItemDTO:
        """
        Преобразует задачу месячного плана
        в строку таблицы рассмотрения.
        """

        return TaskReviewSelectionItemDTO(
            month_item_id=item.id,

            task_name=cls._get_task_name(item),
            responsible_name=cls._get_responsible_name(item),

            planned_start=item.planned_start,
            planned_end=item.planned_end,
            planned_period_text=cls._build_planned_period_text(
                item.planned_start,
                item.planned_end,
            ),

            status=cls._get_status_value(item.status),
            status_label=cls._get_status_label(item.status),

            can_select=cls._can_select_for_review(item),
            has_review_result=bool(item.review_results),

            expected_result_label=cls._get_expected_result_label(
                item.status
            ),
        )

    @staticmethod
    def _sanitize_file_part(value: str) -> str:
        """
        Подготавливает часть имени файла:
        удаляет недопустимые символы и заменяет пробелы
        и разделители на подчёркивания.
        """

        normalized_value = (
                value or ""
        ).strip().lower()

        normalized_value = re.sub(
            r"[^a-zа-яёәіңғүұқөһ0-9_-]+",
            "_",
            normalized_value,
            flags=re.IGNORECASE,
        )

        normalized_value = re.sub(
            r"_+",
            "_",
            normalized_value,
        )

        return (
                normalized_value.strip("_")
                or "protocol"
        )

    # ==========================================================
    # 1. Страницы выбора
    # ==========================================================
    @classmethod
    async def get_review_selection_page_data(
            cls,
            db: AsyncSession,
            *,
            user: User,
            review_place: ReviewPlace | None,
            method_association_id: int | None = None,
    ) -> TaskReviewSelectionPageDTO:
        """
        Формирует данные страницы пакетного рассмотрения задач
        активного годового плана ВШК школы администратора.

        Логика выбора задач:

        - пока место рассмотрения не выбрано, задачи не загружаются;

        - для обычного места рассмотрения доступны задачи
          со статусами DONE и NOT_EXECUTED;

        - для METHOD_ASSOC сначала необходимо выбрать конкретное
          методическое объединение;

        - для METHOD_ASSOC задача со статусом DONE или NOT_EXECUTED
          остаётся доступной, если выбранное МО ещё её не рассматривало;

        - задача, уже рассмотренная выбранным МО, повторно
          не отображается;

        - задача, рассмотренная другим МО, остаётся доступной.
        """

        # 1. Проверка пользователя
        if user.role != UserRole.SCHOOL_ADMIN:
            raise ValueError(
                "Рассмотрение задач доступно только "
                "администратору школы."
            )

        raw_school_id = user.school_id

        if raw_school_id is None:
            raise ValueError(
                "Для администратора школы не определена школа."
            )

        school_id = cast(int, raw_school_id)

        # 2. Получение активного годового плана
        active_plan = await TaskReviewRepository.get_active_school_plan(
            db,
            school_id=school_id,
        )

        if active_plan is None:
            raise ValueError(
                "Для школы не найден активный план ВШК."
            )

        school_plan_id = active_plan.id

        academic_year = str(
            active_plan.academic_year or ""
        ).strip()

        if not academic_year:
            raise ValueError(
                "В активном плане ВШК не указан учебный год."
            )

        academic_year_label = (
            f"{academic_year} учебный год"
        )

        # 3. Получение методических объединений школы
        method_association_entities = (
            await TaskReviewRepository.get_active_method_associations(
                db,
                school_id=school_id,
            )
        )

        method_associations = [
            MethodAssociationSelectionItemDTO(
                id=association.id,
                name=association.name,
            )
            for association in method_association_entities
        ]

        # 4. Проверка выбранного методического объединения
        selected_method_association = None

        if review_place == ReviewPlace.METHOD_ASSOC:
            if method_association_id is not None:
                selected_method_association = (
                    await TaskReviewRepository.get_method_association_by_id(
                        db,
                        method_association_id=method_association_id,
                        school_id=school_id,
                        active_only=True,
                    )
                )

                if selected_method_association is None:
                    raise ValueError(
                        "Выбранное методическое объединение "
                        "не найдено, неактивно или относится "
                        "к другой школе."
                    )

        elif method_association_id is not None:
            raise ValueError(
                "Методическое объединение можно выбирать только "
                "для места рассмотрения METHOD_ASSOC."
            )

        # 5. Получение задач
        tasks: list[TaskReviewSelectionItemDTO] = []
        overdue_tasks: list[TaskReviewSelectionItemDTO] = []

        should_load_tasks = (
                review_place is not None
                and (
                        review_place != ReviewPlace.METHOD_ASSOC
                        or selected_method_association is not None
                )
        )

        if should_load_tasks:
            items = (
                await TaskReviewRepository.get_items_for_review_by_place(
                    db,
                    school_plan_id=school_plan_id,
                    review_place=review_place,
                    method_association_id=method_association_id,
                )
            )

            overdue_items = (
                await TaskReviewRepository.get_overdue_items_for_review(
                    db,
                    school_plan_id=school_plan_id,
                    review_place=review_place,
                )
            )

            tasks = [
                cls._build_selection_item(item)
                for item in items
            ]

            overdue_tasks = [
                cls._build_selection_item(item)
                for item in overdue_items
            ]

        # 6. Формирование DTO страницы
        return TaskReviewSelectionPageDTO(
            school_plan_id=school_plan_id,
            academic_year_label=academic_year_label,

            selected_review_place=review_place,
            selected_method_association_id=method_association_id,

            review_places=list(ReviewPlace),
            method_associations=method_associations,

            tasks=tasks,
            overdue_tasks=overdue_tasks,
        )

    # ==========================================================
    # 2. Загрузка протоколов
    # ==========================================================
    @classmethod
    async def upload_protocol_document(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            review_place: ReviewPlace,
            method_association_id: int | None,
            protocol_number: str,
            protocol_date: date,
            protocol_file: UploadFile,
            uploaded_by_user_id: int,
            comment: str | None = None,
    ) -> SchoolTaskReview:
        """
        Проверяет и сохраняет протокол рассмотрения через единое
        файловое хранилище проекта, затем создаёт запись в БД.

        Для METHOD_ASSOC обязательно проверяет принадлежность
        методического объединения школе.

        Метод не выполняет commit и rollback основной транзакции.
        Управление основной транзакцией остаётся в маршруте.
        """

        # 1. Проверка номера и даты протокола
        normalized_protocol_number = (
                protocol_number or ""
        ).strip()

        if not normalized_protocol_number:
            raise ValueError(
                "Не указан номер протокола."
            )

        if len(normalized_protocol_number) > 100:
            raise ValueError(
                "Номер протокола не должен превышать 100 символов."
            )

        if protocol_date is None:
            raise ValueError(
                "Не указана дата протокола."
            )

        if protocol_date > date.today():
            raise ValueError(
                "Дата протокола не может быть позже текущей даты."
            )

        # 2. Получение данных файла
        original_file_name = (
                protocol_file.filename or ""
        ).strip()

        if len(original_file_name) > 255:
            raise ValueError("Имя файла протокола не должно превышать 255 символов.")
        if not original_file_name:
            raise ValueError(
                "Не выбран файл протокола."
            )

        normalized_content_type = (
                protocol_file.content_type
                or "application/octet-stream"
        ).strip().lower()

        # 3. Проверка расширения файла
        extension = Path(
            original_file_name
        ).suffix.lower()

        allowed_extensions = {
            ".pdf",
            ".doc",
            ".docx",
        }

        if extension not in allowed_extensions:
            raise ValueError(
                "Разрешены только файлы PDF, DOC и DOCX."
            )

        # 4. Проверка MIME-типа
        allowed_content_types = {
            "application/pdf",
            "application/msword",
            (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            "application/octet-stream",
        }

        if normalized_content_type not in allowed_content_types:
            raise ValueError(
                "Недопустимый тип файла протокола."
            )

        # Дополнительная проверка соответствия расширения MIME-типу.
        # application/octet-stream разрешаем, поскольку некоторые
        # браузеры передают его для DOC и DOCX.
        expected_content_types = {
            ".pdf": {
                "application/pdf",
                "application/octet-stream",
            },
            ".doc": {
                "application/msword",
                "application/octet-stream",
            },
            ".docx": {
                (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                "application/octet-stream",
            },
        }

        if (
                normalized_content_type
                not in expected_content_types[extension]
        ):
            raise ValueError(
                "Тип содержимого файла не соответствует "
                "его расширению."
            )

        # 5. Чтение и проверка содержимого
        max_file_size = 20 * 1024 * 1024
        file_content = await protocol_file.read(max_file_size + 1)

        if not file_content:
            raise ValueError(
                "Загруженный файл протокола пуст."
            )

        file_size = len(file_content)
        max_file_size = 20 * 1024 * 1024

        if file_size > max_file_size:
            raise ValueError(
                "Размер файла протокола не должен превышать 20 МБ."
            )

        # 6. Проверка годового плана
        school_plan = (
            await TaskReviewRepository.get_school_plan_by_id(
                db,
                school_plan_id=school_plan_id,
                with_storage_relations=True,
            )
        )

        if school_plan is None:
            raise ValueError(
                "Годовой план ВШК не найден."
            )

        if school_plan.status != PlanStatus.ACTIVE:
            raise ValueError(
                "Загрузка протокола разрешена только "
                "для активного плана ВШК."
            )

        school = school_plan.school

        if school is None:
            raise ValueError(
                "Для годового плана не определена школа."
            )

        district = school.district

        if district is None:
            raise ValueError(
                "Для школы не определён район."
            )

        academic_year = str(
            school_plan.academic_year or ""
        ).strip()

        if not academic_year:
            raise ValueError(
                "В годовом плане не указан учебный год."
            )

        # 7. Проверка методического объединения
        normalized_method_association_id: int | None = None

        if review_place == ReviewPlace.METHOD_ASSOC:
            if method_association_id is None:
                raise ValueError(
                    "Для рассмотрения на методическом объединении "
                    "необходимо выбрать методическое объединение."
                )

            association = (
                await TaskReviewRepository.get_method_association_by_id(
                    db,
                    method_association_id=method_association_id,
                    school_id=school.id,
                    active_only=True,
                )
            )

            if association is None:
                raise ValueError(
                    "Выбранное методическое объединение не найдено, "
                    "неактивно или относится к другой школе."
                )

            normalized_method_association_id = method_association_id

        elif method_association_id is not None:
            raise ValueError(
                "Методическое объединение можно указывать только "
                "для места рассмотрения METHOD_ASSOC."
            )

        # 8. Предварительная проверка существующего протокола
        existing_protocol = (
            await TaskReviewRepository.get_protocol_by_identity(
                db,
                school_plan_id=school_plan_id,
                review_place=review_place,
                method_association_id=(
                    normalized_method_association_id
                ),
                protocol_number=normalized_protocol_number,
                protocol_date=protocol_date,
            )
        )

        if existing_protocol is not None:
            raise ValueError(
                "Протокол с таким номером и датой уже загружен."
            )

        # 9. Формирование технического места хранения
        review_place_value = review_place.value

        if normalized_method_association_id is not None:
            review_place_value = (
                f"{review_place_value}_"
                f"{normalized_method_association_id}"
            )

        storage_context = SchoolStorageContext(
            region_id=district.region_id,
            district_id=district.id,
            school_id=school.id,
            academic_year=academic_year,
            school_plan_id=school_plan.id,
        )

        storage_service = SchoolStorageService(
            storage=get_storage(),
        )

        saved_object_key: str | None = None

        # 10. Сохранение файла и создание записи
        try:
            stored_file = (
                await storage_service.save_review_protocol(
                    context=storage_context,
                    review_place=review_place_value,
                    protocol_number=normalized_protocol_number,
                    protocol_date=protocol_date,
                    content=file_content,
                    original_file_name=original_file_name,
                    content_type=normalized_content_type,
                )
            )

            saved_object_key = stored_file.object_key

            try:
                # SAVEPOINT нужен, чтобы IntegrityError не разрушил
                # внешнюю транзакцию, которой управляет маршрут.
                async with db.begin_nested():
                    protocol_document = (
                        await TaskReviewRepository.create_protocol_document(
                            db,
                            school_plan_id=school_plan_id,
                            review_place=review_place,
                            method_association_id=(
                                normalized_method_association_id
                            ),
                            protocol_number=normalized_protocol_number,
                            protocol_date=protocol_date,
                            reviewed_by_user_id=uploaded_by_user_id,
                            original_file_name=(
                                stored_file.original_file_name
                            ),
                            stored_file_name=(
                                stored_file.stored_file_name
                            ),
                            file_path=stored_file.object_key,
                            mime_type=stored_file.content_type,
                            file_size=stored_file.file_size,
                            comment=comment,
                            flush=True,
                        )
                    )

            except IntegrityError as exc:
                sqlstate = (
                        getattr(exc.orig, "sqlstate", None)
                        or getattr(exc.orig, "pgcode", None)
                )

                # PostgreSQL unique_violation.
                if sqlstate == "23505":
                    raise ValueError(
                        "Протокол с таким номером и датой "
                        "уже загружен."
                    ) from exc

                raise

            return protocol_document

        except Exception:
            if saved_object_key is not None:
                try:
                    await storage_service.delete(
                        object_key=saved_object_key,
                    )
                except (OSError, RuntimeError):
                    logger.warning(
                        (
                            "Не удалось удалить файл протокола "
                            "после ошибки создания записи в БД: "
                            "object_key=%s"
                        ),
                        saved_object_key,
                        exc_info=True,
                    )
            raise

    # ==========================================================
    # 3. Рассмотрение задач
    # ==========================================================
    @classmethod
    async def review_tasks_batch(
            cls,
            db: AsyncSession,
            *,
            dto: TaskReviewBatchCreateDTO,
            school_plan_id: int,
        user: User,
        pending_file_keys: list[str] | None = None,
            protocol_file: UploadFile,
    ) -> list[SchoolMonthPlanItemReviewResult]:
        """
        Атомарно подготавливает пакетное рассмотрение нескольких задач.

        В рамках одной внешней транзакции:

        - валидирует выбранные задачи;
        - проверяет место рассмотрения и повторные рассмотрения;
        - сохраняет общий протокол SchoolTaskReview;
        - создаёт TaskExecutionDocument для каждой задачи;
        - создаёт SchoolMonthPlanItemReviewResult для каждой задачи.

        Статус SchoolMonthPlanItem не изменяется:
        DONE и NOT_EXECUTED остаются статусами исполнения.

        Для METHOD_ASSOC одна задача может рассматриваться разными МО,
        но одно и то же МО не может рассматривать её повторно.

        Commit/rollback выполняются маршрутом. Если после сохранения
        файла возникает ошибка, сервис удаляет файл из storage, а БД
        затем откатывается маршрутом.
        """

        # 1. Нормализация выбранных задач.
        await cls._authorize_plan(db, user=user, school_plan_id=school_plan_id)
        if dto.reviewed_by_user_id != user.id:
            raise HTTPException(403, "Недопустимый автор рассмотрения.")
        unique_ids = list(dict.fromkeys(dto.month_item_ids))

        if not unique_ids:
            raise ValueError(
                "Не выбрана ни одна задача для рассмотрения."
            )

        # 2. Получение и блокировка задач до файлового I/O.
        month_items = await TaskReviewRepository.get_month_items_by_ids(
            db,
            month_item_ids=unique_ids,
            school_plan_id=school_plan_id,
            for_update=True,
        )

        found_ids = {item.id for item in month_items}
        unavailable_ids = set(unique_ids) - found_ids

        if unavailable_ids:
            unavailable_text = ", ".join(
                str(item_id)
                for item_id in sorted(unavailable_ids)
            )
            raise ValueError(
                "Некоторые задачи не найдены, исключены из плана "
                "или не относятся к выбранному годовому плану: "
                f"{unavailable_text}"
            )

        # 3. Проверка места рассмотрения, статуса и повторов.
        invalid_place_ids: list[int] = []
        invalid_status_ids: list[int] = []
        already_reviewed_ids: list[int] = []
        from app.modules.reports.repositories.document_correction_repo import DocumentCorrectionRepo
        correction_ids = await DocumentCorrectionRepo.pending_ids(db, unique_ids)

        allowed_statuses = {
            PlanItemStatus.DONE,
            PlanItemStatus.NOT_EXECUTED,
        }

        if dto.review_place == ReviewPlace.METHOD_ASSOC:
            if dto.method_association_id is None:
                raise ValueError(
                    "Для рассмотрения на методическом объединении "
                    "необходимо выбрать методическое объединение."
                )
        elif dto.method_association_id is not None:
            raise ValueError(
                "Методическое объединение можно указывать только "
                "для места рассмотрения METHOD_ASSOC."
            )

        for item in month_items:
            allowed_places = {place.review_place for place in item.review_places}
            if dto.review_place not in allowed_places:
                invalid_place_ids.append(item.id)

            if item.status not in allowed_statuses:
                invalid_status_ids.append(item.id)

            if dto.review_place == ReviewPlace.METHOD_ASSOC:
                already_reviewed = any(
                    review_result.task_review is not None
                    and review_result.task_review.review_place
                    == ReviewPlace.METHOD_ASSOC
                    and review_result.task_review.method_association_id
                    == dto.method_association_id
                    for review_result in item.review_results
                )
            else:
                already_reviewed = bool(item.review_results)

            if already_reviewed and item.id not in correction_ids:
                already_reviewed_ids.append(item.id)

        if invalid_place_ids:
            invalid_text = ", ".join(
                str(item_id)
                for item_id in sorted(invalid_place_ids)
            )
            raise ValueError(
                "Некоторые задачи не относятся к выбранному "
                f"месту рассмотрения: {invalid_text}"
            )

        if invalid_status_ids:
            invalid_text = ", ".join(
                str(item_id)
                for item_id in sorted(invalid_status_ids)
            )
            raise ValueError(
                "Рассматривать можно только выполненные или "
                "окончательно неисполненные задачи: "
                f"{invalid_text}"
            )

        if already_reviewed_ids:
            already_reviewed_text = ", ".join(
                str(item_id)
                for item_id in sorted(already_reviewed_ids)
            )

            if dto.review_place == ReviewPlace.METHOD_ASSOC:
                raise ValueError(
                    "Некоторые задачи уже рассматривались выбранным "
                    "методическим объединением: "
                    f"{already_reviewed_text}"
                )

            raise ValueError(
                "Некоторые задачи уже были рассмотрены ранее. "
                "Повторное рассмотрение разрешено только разными "
                "методическими объединениями: "
                f"{already_reviewed_text}"
            )

        # 4. Только после успешной проверки задач сохраняем протокол.
        task_review: SchoolTaskReview | None = None

        try:
            task_review = await cls.upload_protocol_document(
                db,
                school_plan_id=school_plan_id,
                review_place=dto.review_place,
                method_association_id=dto.method_association_id,
                protocol_number=dto.protocol_number,
                protocol_date=dto.protocol_date,
                protocol_file=protocol_file,
                uploaded_by_user_id=dto.reviewed_by_user_id,
                comment=dto.comment,
            )

            if pending_file_keys is not None:
                pending_file_keys.append(task_review.protocol_file_path)
            protocol_id = cast(int, task_review.id)

            # 5. Документы задач создаются без flush внутри цикла.
            task_protocol_documents = []

            for item in month_items:
                task_protocol_document = (
                    await TaskReviewRepository.create_task_protocol_document(
                        db,
                        month_item_id=item.id,
                        protocol_id=protocol_id,
                        flush=False,
                    )
                )
                task_protocol_documents.append(task_protocol_document)

            # Один flush сразу для всех TaskExecutionDocument.
            await db.flush()

            # 6. Подготовка результатов рассмотрения.
            reviewed_at = datetime.now(timezone.utc)
            create_dtos: list[TaskReviewCreateDTO] = []

            for item, task_protocol_document in zip(
                    month_items,
                    task_protocol_documents,
                    strict=True,
            ):
                if item.status == PlanItemStatus.DONE:
                    review_status = PlanItemStatus.REVIEWED
                elif item.status == PlanItemStatus.NOT_EXECUTED:
                    review_status = PlanItemStatus.NOT_EXECUTED
                else:
                    raise ValueError(
                        f"Недопустимый статус задачи ID={item.id}: "
                        f"{item.status}"
                    )

                create_dtos.append(
                    TaskReviewCreateDTO(
                        month_item_id=item.id,
                        task_review_id=protocol_id,
                        reviewed_by_user_id=dto.reviewed_by_user_id,
                        review_place=dto.review_place,
                        status=review_status,
                        protocol_document_id=task_protocol_document.id,
                        reviewed_at=reviewed_at,
                        comment=dto.comment,
                    )
                )

            # 7. Один пакетный flush результатов.
            results = await TaskReviewRepository.create_many(
                db,
                create_dtos,
                flush=True,
            )
            await DocumentCorrectionRepo.accept_corrections(db, unique_ids)
            return results

        except Exception:
            # БД откатывает маршрут. Здесь компенсируем файловое I/O,
            # которое транзакция PostgreSQL откатить не может.
            if task_review is not None and task_review.protocol_file_path:
                try:
                    storage_service = SchoolStorageService(
                        storage=get_storage(),
                    )
                    await storage_service.delete(
                        object_key=task_review.protocol_file_path,
                    )
                except (OSError, RuntimeError):
                    logger.warning(
                        "Не удалось удалить файл протокола после ошибки "
                        "пакетного рассмотрения: object_key=%s",
                        task_review.protocol_file_path,
                        exc_info=True,
                    )
            raise

    # ==========================================================
    # 4. Просмотр результатов
    # ==========================================================
    @staticmethod
    async def get_review_page_data(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> dict:
        """
        Формирует данные страницы просмотра
        результата рассмотрения одной задачи.
        """

        task = await TaskReviewRepository.get_month_item_by_id(
            db,
            month_item_id=month_item_id,
            with_relations=True,
        )

        if task is None:
            raise ValueError("Задача не найдена")

        if task.status not in {
            PlanItemStatus.DONE,
            PlanItemStatus.NOT_EXECUTED,
        }:
            raise ValueError(
                "Задача ещё не прошла итоговое рассмотрение"
            )

        review_history = (
            await TaskReviewRepository.get_history_by_month_item_id(
                db,
                month_item_id=month_item_id,
                limit=50,
                offset=0,
                with_relations=True,
            )
        )

        if not review_history:
            raise ValueError("Задача ещё не была рассмотрена")

        latest_review = review_history[0]

        review_count = await TaskReviewRepository.count_by_month_item_id(
            db,
            month_item_id=month_item_id,
        )

        return {
            "task": task,
            "latest_review": latest_review,
            "review_history": review_history,
            "review_count": review_count,
            "review_places": list(ReviewPlace),
        }

    @staticmethod
    async def mark_overdue_tasks_not_executed(
            db: AsyncSession,
            *,
            month_item_ids: list[int],
            school_plan_id: int,
            user: User,
            review_place: ReviewPlace,
            method_association_id: int | None = None,
    ) -> int:
        """
        Переводит выбранные просроченные задачи
        в статус NOT_EXECUTED.
        """

        plan = await TaskReviewService._authorize_plan(db, user=user, school_plan_id=school_plan_id)
        if review_place == ReviewPlace.METHOD_ASSOC:
            association = (await TaskReviewRepository.get_method_association_by_id(
                db, method_association_id=method_association_id, school_id=plan.school_id,
            )) if method_association_id is not None else None
            if association is None:
                raise ValueError("Выбранное методическое объединение не найдено, неактивно или относится к другой школе.")
        elif method_association_id is not None:
            raise ValueError("Методическое объединение можно выбирать только для места рассмотрения METHOD_ASSOC.")
        unique_ids = list(
            dict.fromkeys(month_item_ids)
        )

        if not unique_ids:
            raise ValueError(
                "Не выбрана ни одна просроченная задача"
            )

        updated_count = (
            await TaskReviewRepository.mark_items_not_executed(
                db,
                month_item_ids=unique_ids,
                school_plan_id=school_plan_id,
                review_place=review_place,
            )
        )

        if updated_count != len(unique_ids):
            raise ValueError(
                "Некоторые выбранные задачи не являются просроченными, "
                "уже рассмотрены или имеют недопустимый статус"
            )

        return updated_count
