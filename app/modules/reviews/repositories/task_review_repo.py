# app/modules/tasks/task_review_repo.py
from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.org.models import School
from app.modules.planning.enums import PlanItemStatus, PlanStatus, ReviewPlace
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee, SchoolMonthPlanItemReviewPlace,
)
from app.modules.planning.models_school import (
    SchoolPlan,
    SchoolPlanRow11,
    SchoolPlanRow11ReviewPlace,
)
from app.modules.reports.enums import (
    DocumentType,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.staff.models_staff_school import SchoolStaffRole
from app.modules.reviews.models_task_review import (
    SchoolMethodAssociation,
    SchoolMonthPlanItemReviewResult,
    SchoolTaskReview,
)
from app.modules.reviews.task_review_dto import TaskReviewCreateDTO


class TaskReviewRepository:

    # ==========================================================
    # 1. Получение основных данных
    # ==========================================================
    @staticmethod
    async def get_active_school_plan(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> SchoolPlan | None:
        """
        Возвращает активный годовой план ВШК школы.

        Выполняет явный async-запрос и не использует
        ленивую загрузку relationships.
        """

        stmt = (
            select(SchoolPlan)
            .where(
                SchoolPlan.school_id == school_id,
                SchoolPlan.status == PlanStatus.ACTIVE,
            )
            .order_by(
                SchoolPlan.created_at.desc(),
                SchoolPlan.id.desc(),
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_school_plan_by_id(
            db: AsyncSession,
            *,
            school_plan_id: int,
            with_storage_relations: bool = False,
    ) -> SchoolPlan | None:
        """
        Возвращает годовой план по идентификатору.

        При with_storage_relations=True загружает связи,
        необходимые для файлового хранилища:

            SchoolPlan -> School -> District
        """

        stmt = (
            select(SchoolPlan)
            .where(
                SchoolPlan.id == school_plan_id
            )
        )

        if with_storage_relations:
            stmt = stmt.options(
                selectinload(
                    SchoolPlan.school
                ).selectinload(
                    School.district
                )
            )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_available_years(
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[int]:
        """
            Возвращает список учебных лет,
            для которых существуют месячные планы школы.

            Используется на странице выбора задач
            для заполнения списка доступных годов.
        """
        stmt = (
            select(SchoolMonthPlan.year)
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
            )
            .distinct()
            .order_by(SchoolMonthPlan.year.desc())
        )

        result = await db.execute(stmt)

        return list(result.scalars().all())

    @staticmethod
    async def get_available_months(
            db: AsyncSession,
            *,
            school_plan_id: int,
            year: int,
    ) -> list[int]:
        """
            Возвращает список месяцев выбранного учебного года,
            для которых существуют месячные планы школы.

            Используется для заполнения списка месяцев
            после выбора учебного года.
        """
        stmt = (
            select(SchoolMonthPlan.month)
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlan.year == year,
            )
            .distinct()
            .order_by(SchoolMonthPlan.month.asc())
        )

        result = await db.execute(stmt)

        return list(result.scalars().all())

    @staticmethod
    async def get_method_association_by_id(
            db: AsyncSession,
            *,
            method_association_id: int,
            school_id: int,
            active_only: bool = True,
    ) -> SchoolMethodAssociation | None:
        """
        Возвращает методическое объединение по ID.

        При переданном school_id дополнительно проверяет,
        что МО принадлежит нужной школе.
        """

        stmt = select(SchoolMethodAssociation).where(
            SchoolMethodAssociation.id == method_association_id,
        )

        stmt = stmt.where(
            SchoolMethodAssociation.school_id == school_id,
        )

        if active_only:
            stmt = stmt.where(
                SchoolMethodAssociation.is_active.is_(True),
            )

        result = await db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_method_associations(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> list[SchoolMethodAssociation]:
        """
        Возвращает активные методические объединения школы.
        """

        stmt = (
            select(SchoolMethodAssociation)
            .where(
                SchoolMethodAssociation.school_id == school_id,
                SchoolMethodAssociation.is_active.is_(True),
            )
            .order_by(
                SchoolMethodAssociation.name.asc(),
            )
        )

        result = await db.scalars(stmt)
        return list(result.all())

    # ==========================================================
    # 2. Получение задач
    # ==========================================================
    @staticmethod
    async def get_month_item_by_id(
            db: AsyncSession,
            month_item_id: int,
            *,
            with_relations: bool = False,
            for_update: bool = False,
    ) -> SchoolMonthPlanItem | None:
        """
            Возвращает одну задачу месячного плана по идентификатору.

            По необходимости загружает связанные сущности
            и может блокировать запись для изменения
            при пакетном рассмотрении.
        """
        stmt = (
            select(SchoolMonthPlanItem)
            .where(
                SchoolMonthPlanItem.id == month_item_id,
            )
        )

        if with_relations:
            stmt = stmt.options(
                selectinload(
                    SchoolMonthPlanItem.month_plan
                ),

                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.review_places
                ),

                selectinload(
                    SchoolMonthPlanItem.assignees
                ).selectinload(
                    SchoolMonthPlanItemAssignee.staff_role
                ).selectinload(
                    SchoolStaffRole.staff_member
                ),

                selectinload(
                    SchoolMonthPlanItem.review_results
                ).selectinload(
                    SchoolMonthPlanItemReviewResult.task_review
                ),

                selectinload(
                    SchoolMonthPlanItem.execution_documents
                ),
            )
        if for_update:
            stmt = stmt.with_for_update(
                of=SchoolMonthPlanItem,
            )
        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_month_items_by_ids(
            db: AsyncSession,
            *,
            month_item_ids: Sequence[int],
            school_plan_id: int,
            for_update: bool = False,
    ) -> list[SchoolMonthPlanItem]:
        """
        Возвращает включённые задачи указанного годового плана
        по списку идентификаторов.

        Метод используется при пакетном рассмотрении задач.

        Заранее загружает только связи, необходимые
        сервису пакетного рассмотрения:
        - результаты рассмотрения и их SchoolTaskReview;
        - исходную строку годового плана;
        - места рассмотрения исходной строки.

        Остальные relationships намеренно не загружаются,
        чтобы не создавать лишние SELECT при сохранении пакета.

        При for_update=True блокируются только строки
        SchoolMonthPlanItem до завершения текущей транзакции.
        """

        unique_ids = list(dict.fromkeys(month_item_ids))

        if not unique_ids:
            return []

        stmt = (
            select(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .where(
                SchoolMonthPlanItem.id.in_(unique_ids),
                SchoolMonthPlanItem.is_included.is_(True),
                SchoolMonthPlan.school_plan_id == school_plan_id,
            )
            .options(
                # Для пакетного рассмотрения сервису нужны только:
                # - допустимые места рассмотрения исходной строки;
                # - история рассмотрений с родительским SchoolTaskReview.
                #
                # Месячный план, исполнители и документы исполнения здесь
                # не используются и намеренно не загружаются.
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.review_places
                ),

                selectinload(
                    SchoolMonthPlanItem.review_results
                ).selectinload(
                    SchoolMonthPlanItemReviewResult.task_review
                ),
            )
            .order_by(
                SchoolMonthPlanItem.id.asc(),
            )
        )

        if for_update:
            stmt = stmt.with_for_update(
                of=SchoolMonthPlanItem,
            )

        result = await db.execute(stmt)

        items = list(
            result.scalars().unique().all()
        )

        items_by_id = {
            item.id: item
            for item in items
        }

        return [
            items_by_id[item_id]
            for item_id in unique_ids
            if item_id in items_by_id
        ]

    @staticmethod
    async def get_items_for_review_by_place(
            db: AsyncSession,
            *,
            school_plan_id: int,
            review_place: ReviewPlace,
            method_association_id: int | None = None,
    ) -> list[SchoolMonthPlanItem]:
        """
        Возвращает задачи месячного плана, доступные для рассмотрения
        в выбранном месте рассмотрения.

        Обычные места:
        - DONE;
        - NOT_EXECUTED;
        - задача ещё не имеет результатов рассмотрения.

        METHOD_ASSOC:
        - DONE;
        - NOT_EXECUTED;
        - задача ещё не рассматривалась выбранным МО.

        Статус SchoolMonthPlanItem отражает только исполнение.
        Факт рассмотрения хранится отдельно в review_results.
        """

        if review_place == ReviewPlace.METHOD_ASSOC:
            if method_association_id is None:
                raise ValueError(
                    "Для рассмотрения на методическом объединении "
                    "необходимо указать method_association_id."
                )

        elif method_association_id is not None:
            raise ValueError(
                "Методическое объединение можно указывать только "
                "для места рассмотрения METHOD_ASSOC."
            )

        allowed_statuses: set[PlanItemStatus] = {
            PlanItemStatus.DONE,
            PlanItemStatus.NOT_EXECUTED,
        }

        stmt = (
            select(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolMonthPlanItemReviewPlace,
                SchoolMonthPlanItemReviewPlace.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlan.school_plan_id
                == school_plan_id,

                SchoolMonthPlanItem.is_included.is_(True),

                SchoolMonthPlanItem.status.in_(
                    allowed_statuses
                ),

                SchoolMonthPlanItemReviewPlace.review_place
                == review_place,
            )
            .options(
                # Для строки выбора нужны название задачи,
                # исполнители и факт наличия рассмотрений.
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ),

                selectinload(
                    SchoolMonthPlanItem.assignees
                ).selectinload(
                    SchoolMonthPlanItemAssignee.staff_role
                ).selectinload(
                    SchoolStaffRole.staff_member
                ),

                selectinload(
                    SchoolMonthPlanItem.review_results
                ),
            )
            .order_by(
                SchoolMonthPlanItem.planned_start
                .asc()
                .nulls_last(),

                SchoolMonthPlanItem.planned_end
                .asc()
                .nulls_last(),

                SchoolMonthPlanItem.id.asc(),
            )
        )

        if review_place == ReviewPlace.METHOD_ASSOC:
            already_reviewed_by_selected_ma = (
                select(
                    SchoolMonthPlanItemReviewResult.id
                )
                .join(
                    SchoolTaskReview,
                    SchoolTaskReview.id
                    == SchoolMonthPlanItemReviewResult.task_review_id,
                )
                .where(
                    SchoolMonthPlanItemReviewResult.month_item_id
                    == SchoolMonthPlanItem.id,

                    SchoolTaskReview.review_place
                    == ReviewPlace.METHOD_ASSOC,

                    SchoolTaskReview.method_association_id
                    == method_association_id,
                )
                .exists()
            )

            stmt = stmt.where(
                ~already_reviewed_by_selected_ma
            )

        else:
            stmt = stmt.where(
                ~SchoolMonthPlanItem.review_results.any()
            )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    @staticmethod
    async def get_overdue_items_for_review(
            db: AsyncSession,
            *,
            school_plan_id: int,
            review_place: ReviewPlace,
    ) -> list[SchoolMonthPlanItem]:
        """
        Возвращает просроченные задачи, которые ещё не переведены
        в окончательный статус.
        """

        today = date.today()

        stmt = (
            select(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlanRow11,
                SchoolPlanRow11.id == SchoolMonthPlanItem.source_row11_id,
            )
            .join(
                SchoolPlanRow11ReviewPlace,
                SchoolPlanRow11ReviewPlace.row11_id
                == SchoolPlanRow11.id,
            )
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,

                SchoolMonthPlanItem.is_included.is_(True),

                SchoolPlanRow11ReviewPlace.review_place
                == review_place,

                SchoolMonthPlanItem.status.in_(
                    {
                        PlanItemStatus.TODO,
                        PlanItemStatus.IN_PROGRESS,
                    }
                ),

                SchoolMonthPlanItem.planned_end.is_not(None),
                SchoolMonthPlanItem.planned_end < today,

                ~SchoolMonthPlanItem.review_results.any(),
            )
            .options(
                # Для отображения просроченной строки нужны только
                # название, исполнители и факт рассмотрения.
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ),

                selectinload(
                    SchoolMonthPlanItem.assignees
                ).selectinload(
                    SchoolMonthPlanItemAssignee.staff_role
                ).selectinload(
                    SchoolStaffRole.staff_member
                ),

                selectinload(
                    SchoolMonthPlanItem.review_results
                ),
            )
            .order_by(
                SchoolMonthPlan.year.asc(),
                SchoolMonthPlan.month.asc(),
                SchoolMonthPlanItem.planned_end.asc(),
                SchoolMonthPlanItem.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    # ==========================================================
    # 3. Работа с результатами рассмотрения
    # ==========================================================
    @staticmethod
    async def get_by_id(
            db: AsyncSession,
            review_result_id: int,
            *,
            with_relations: bool = False,
            for_update: bool = False,
    ) -> SchoolMonthPlanItemReviewResult | None:
        """
        Возвращает результат рассмотрения задачи по идентификатору.

        При with_relations=True загружает связи, необходимые
        для просмотра, обновления и удаления результата.

        При for_update=True блокирует строку результата рассмотрения
        до завершения текущей транзакции.
        """

        stmt = select(
            SchoolMonthPlanItemReviewResult
        ).where(
            SchoolMonthPlanItemReviewResult.id == review_result_id
        )

        if with_relations:
            stmt = stmt.options(
                selectinload(
                    SchoolMonthPlanItemReviewResult.month_item
                ).selectinload(
                    SchoolMonthPlanItem.month_plan
                ),

                selectinload(
                    SchoolMonthPlanItemReviewResult.month_item
                ).selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.review_places
                ),

                selectinload(
                    SchoolMonthPlanItemReviewResult.month_item
                ).selectinload(
                    SchoolMonthPlanItem.review_results
                ).selectinload(
                    SchoolMonthPlanItemReviewResult.task_review
                ),

                selectinload(
                    SchoolMonthPlanItemReviewResult.reviewed_by_user
                ),

                selectinload(
                    SchoolMonthPlanItemReviewResult.protocol_document
                ),

                selectinload(
                    SchoolMonthPlanItemReviewResult.task_review
                ),
            )

        if for_update:
            stmt = stmt.with_for_update(
                of=SchoolMonthPlanItemReviewResult,
            )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_history_by_month_item_id(
            db: AsyncSession,
            month_item_id: int,
            *,
            limit: int = 50,
            offset: int = 0,
            with_relations: bool = False,
    ) -> list[SchoolMonthPlanItemReviewResult]:
        """
            Возвращает историю рассмотрений
            выбранной задачи.

            Поддерживает постраничную загрузку
            посредством limit и offset.
        """
        if limit < 1:
            raise ValueError("limit должен быть больше нуля.")

        if offset < 0:
            raise ValueError("offset не может быть отрицательным.")

        stmt = (
            select(SchoolMonthPlanItemReviewResult)
            .where(SchoolMonthPlanItemReviewResult.month_item_id == month_item_id)
            .order_by(
                SchoolMonthPlanItemReviewResult.created_at.desc(),
                SchoolMonthPlanItemReviewResult.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        if with_relations:
            stmt = stmt.options(
                selectinload(SchoolMonthPlanItemReviewResult.reviewed_by_user),
                selectinload(SchoolMonthPlanItemReviewResult.protocol_document),
                selectinload(SchoolMonthPlanItemReviewResult.task_review),
            )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_month_item_id(
            db: AsyncSession,
            month_item_id: int,
    ) -> int:
        """
            Возвращает количество рассмотрений
            выбранной задачи.
        """
        stmt = (
            select(func.count(SchoolMonthPlanItemReviewResult.id))
            .where(SchoolMonthPlanItemReviewResult.month_item_id == month_item_id)
        )

        result = await db.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def exists_for_month_item_id(
            db: AsyncSession,
            month_item_id: int,
    ) -> bool:
        """
            Проверяет наличие хотя бы одного
            результата рассмотрения
            для выбранной задачи.
        """
        stmt = (
            select(SchoolMonthPlanItemReviewResult.id)
            .where(SchoolMonthPlanItemReviewResult.month_item_id == month_item_id)
            .limit(1)
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create(
            db: AsyncSession,
            dto: TaskReviewCreateDTO,
            *,
            flush: bool = True,
    ) -> SchoolMonthPlanItemReviewResult:
        """
            Создаёт одно новое рассмотрение задачи.

            Используется при обычном режиме,
            когда рассматривается одна задача.
        """
        review_result = SchoolMonthPlanItemReviewResult(
            month_item_id=dto.month_item_id,
            task_review_id=dto.task_review_id,
            review_place=dto.review_place,
            status=dto.status,
            reviewed_by_user_id=dto.reviewed_by_user_id,
            protocol_document_id=dto.protocol_document_id,
            reviewed_at=dto.reviewed_at,
            comment=dto.comment,
        )

        db.add(review_result)

        if flush:
            await db.flush()

        return review_result

    @staticmethod
    async def create_many(
            db: AsyncSession,
            dtos: Sequence[TaskReviewCreateDTO],
            *,
            flush: bool = True,
    ) -> list[SchoolMonthPlanItemReviewResult]:
        """
        Создаёт результаты рассмотрения для нескольких задач.

        Статус результата заранее рассчитывается сервисом
        и передаётся через TaskReviewCreateDTO.status.

        В каждом DTO поле protocol_document_id должно содержать
        ID соответствующего TaskExecutionDocument, а не ID
        общего SchoolTaskReview.
        """

        if not dtos:
            return []

        review_results = [
            SchoolMonthPlanItemReviewResult(
                month_item_id=dto.month_item_id,
                task_review_id=dto.task_review_id,
                review_place=dto.review_place,
                status=dto.status,
                reviewed_by_user_id=dto.reviewed_by_user_id,
                protocol_document_id=dto.protocol_document_id,
                reviewed_at=dto.reviewed_at,
                comment=dto.comment,
            )
            for dto in dtos
        ]

        db.add_all(review_results)

        if flush:
            await db.flush()

        return review_results

    # ==========================================================
    # 4. Работа с протоколами рассмотрения
    # ==========================================================
    @staticmethod
    async def get_protocol_by_identity(
            db: AsyncSession,
            *,
            school_plan_id: int,
            review_place: ReviewPlace,
            protocol_number: str,
            protocol_date: date,
            method_association_id: int | None,
    ) -> SchoolTaskReview | None:
        """
        Проверяет дубликат записи для загруженного протокола рассмотрения.
        """
        stmt = select(SchoolTaskReview).where(
            SchoolTaskReview.school_plan_id == school_plan_id,
            SchoolTaskReview.review_place == review_place,
            SchoolTaskReview.protocol_number == protocol_number.strip(),
            SchoolTaskReview.protocol_date == protocol_date,
        )

        if method_association_id is None:
            stmt = stmt.where(
                SchoolTaskReview.method_association_id.is_(None)
            )
        else:
            stmt = stmt.where(
                SchoolTaskReview.method_association_id
                == method_association_id
            )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def create_protocol_document(
            db: AsyncSession,
            *,
            school_plan_id: int,
            review_place: ReviewPlace,
            method_association_id: int | None,
            reviewed_by_user_id: int,
            protocol_number: str,
            protocol_date: date,
            original_file_name: str,
            stored_file_name: str,
            file_path: str,
            mime_type: str,
            file_size: int,
            comment: str | None = None,
            flush: bool = True,
    ) -> SchoolTaskReview:
        """
        Создаёт запись загруженного протокола рассмотрения.
        """

        normalized_protocol_number = protocol_number.strip()

        protocol_document = SchoolTaskReview(
            school_plan_id=school_plan_id,
            review_place=review_place,
            method_association_id=method_association_id,
            reviewed_by_user_id=reviewed_by_user_id,

            protocol_number=normalized_protocol_number,
            protocol_date=protocol_date,

            protocol_original_file_name=original_file_name,
            protocol_stored_file_name=stored_file_name,
            protocol_file_path=file_path,
            protocol_mime_type=mime_type,
            protocol_file_size=file_size,

            comment=comment,
        )

        db.add(protocol_document)

        if flush:
            await db.flush()

        return protocol_document

    @staticmethod
    async def get_protocol_by_id(
            db: AsyncSession,
            protocol_id: int,
    ) -> SchoolTaskReview | None:
        """
        Возвращает общий протокол рассмотрения по первичному ключу.
        """

        # Поиск по PK через Session.get использует identity map.
        # Если протокол уже загружен в текущей транзакции,
        # дополнительный SELECT не выполняется.
        return await db.get(
            SchoolTaskReview,
            protocol_id,
        )

    @classmethod
    async def create_task_protocol_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            protocol_id: int,
            flush: bool = True,
    ) -> TaskExecutionDocument:
        """
        Создаёт TaskExecutionDocument для одной задачи
        на основании общего SchoolTaskReview.

        Физический файл повторно не загружается.
        Создаётся только отдельная запись документа задачи,
        которая использует тот же file_path.
        """

        protocol = await cls.get_protocol_by_id(
            db,
            protocol_id=protocol_id,
        )

        if protocol is None:
            raise ValueError(
                f"Протокол рассмотрения с ID={protocol_id} не найден."
            )

        document = TaskExecutionDocument(
            month_item_id=month_item_id,

            required_document_id=None,
            report_type_id=None,
            selected_report_id=None,

            report_code=None,
            report_label=None,

            document_type=DocumentType.PROTOCOL,
            status=TaskDocumentStatus.ACCEPTED,
            source=TaskDocumentSource.UPLOAD,

            version=1,
            is_current=True,
            is_final=True,

            title=cls._build_protocol_document_title(protocol),

            original_file_name=protocol.protocol_original_file_name,
            stored_file_name=protocol.protocol_stored_file_name,
            file_path=protocol.protocol_file_path,
            mime_type=protocol.protocol_mime_type,
            file_size=protocol.protocol_file_size,

            review_comment=protocol.comment,

            uploaded_by_user_id=protocol.reviewed_by_user_id,
            submitted_by_user_id=protocol.reviewed_by_user_id,
            reviewed_by_user_id=protocol.reviewed_by_user_id,

            submitted_at=protocol.created_at,
            reviewed_at=protocol.created_at,
        )

        db.add(document)

        if flush:
            await db.flush()

        return document

    @staticmethod
    def _build_protocol_document_title(
            protocol: SchoolTaskReview,
    ) -> str:
        """
        Формирует название документа протокола.
        """

        protocol_number = (
            protocol.protocol_number.strip()
            if protocol.protocol_number
            else None
        )

        if protocol_number:
            return f"Протокол №{protocol_number}"

        return "Протокол рассмотрения"

    # ==========================================================
    # 5. Автоматические операции
    # ==========================================================
    @staticmethod
    async def mark_items_not_executed(
            db: AsyncSession,
            *,
            month_item_ids: Sequence[int],
            school_plan_id: int,
    ) -> int:
        """
        Атомарно переводит подходящие просроченные задачи
        из TODO/IN_PROGRESS в NOT_EXECUTED.

        UPDATE сам блокирует изменяемые строки. Дополнительный SELECT
        с FOR UPDATE не требуется, поэтому операция выполняется одним
        запросом и масштабируется лучше пакетного изменения ORM-объектов.
        """

        unique_ids = list(dict.fromkeys(month_item_ids))

        if not unique_ids:
            return 0

        today = date.today()

        eligible_item_ids = (
            select(SchoolMonthPlanItem.id)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .where(
                SchoolMonthPlanItem.id.in_(unique_ids),
                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlanItem.is_included.is_(True),
                SchoolMonthPlanItem.status.in_(
                    {
                        PlanItemStatus.TODO,
                        PlanItemStatus.IN_PROGRESS,
                    }
                ),
                SchoolMonthPlanItem.planned_end.is_not(None),
                SchoolMonthPlanItem.planned_end < today,
                ~SchoolMonthPlanItem.review_results.any(),
            )
        )

        stmt = (
            update(SchoolMonthPlanItem)
            .where(
                SchoolMonthPlanItem.id.in_(eligible_item_ids),
            )
            .values(
                status=PlanItemStatus.NOT_EXECUTED,
            )
            .returning(
                SchoolMonthPlanItem.id,
            )
            .execution_options(
                synchronize_session=False,
            )
        )

        result = await db.execute(stmt)
        updated_ids = list(result.scalars().all())

        return len(updated_ids)
