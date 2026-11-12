# app/modules/users/services/workspace_service.py

from __future__ import annotations

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.repositories.question_bank_expert_repo import (
    QuestionBankExpertRepo,
)
from app.modules.assessment.repositories.teacher_question_bank_repo import (
    TeacherQuestionBankRepo,
)
from app.modules.users.enums import (
    UserRole,
    UserWorkspace,
)
from app.modules.users.models import User
from app.modules.users.repositories.workspace_repo import (
    UserWorkspaceRepo,
)
from app.modules.users.schemas.workspace_schemas import (
    UserWorkspaceContextDTO,
    UserWorkspaceItemDTO,
)


class UserWorkspaceService:
    """
    Определяет рабочие интерфейсы,
    доступные текущему пользователю.

    Workspace не изменяет User.role
    и не является заменой authorization.

    User.role определяет глобальную роль.

    Дополнительные workspace определяются
    фактическими связями пользователя.
    """

    # =========================================================
    # PUBLIC API
    # =========================================================

    @classmethod
    async def get_context(
        cls,
        db: AsyncSession,
        *,
        user: User,
        requested_workspace: UserWorkspace | None = None,
    ) -> UserWorkspaceContextDTO:
        """
        Возвращает полный workspace-контекст пользователя.

        requested_workspace обычно приходит из session.

        Если запрошенный workspace больше недоступен,
        автоматически используется PRIMARY.
        """

        items = await cls._build_available_items(
            db,
            user=user,
        )

        available_codes = {
            item.code
            for item in items
        }

        active = cls._resolve_active_workspace(
            requested_workspace=requested_workspace,
            available_codes=available_codes,
        )

        active_items = [
            UserWorkspaceItemDTO(
                code=item.code,
                label=item.label,
                is_active=item.code == active,
            )
            for item in items
        ]

        return UserWorkspaceContextDTO(
            user_role=user.role,
            active=active,
            items=active_items,
        )

    @classmethod
    async def can_use_workspace(
        cls,
        db: AsyncSession,
        *,
        user: User,
        workspace: UserWorkspace,
    ) -> bool:
        """
        Проверяет, доступен ли конкретный workspace
        текущему пользователю.
        """

        context = await cls.get_context(
            db,
            user=user,
        )

        return context.has_workspace(
            workspace
        )

    # =========================================================
    # AVAILABLE WORKSPACES
    # =========================================================

    @classmethod
    async def _build_available_items(
            cls,
            db: AsyncSession,
            *,
            user: User,
    ) -> list[UserWorkspaceItemDTO]:

        items: list[UserWorkspaceItemDTO] = []

        # -----------------------------------------------------
        # NORMALIZED USER VALUES
        # -----------------------------------------------------

        user_id = cast(
            int,
            user.id,
        )

        staff_member_id = cast(
            int | None,
            user.staff_member_id,
        )

        user_role = cast(
            UserRole,
            user.role,
        )

        # -----------------------------------------------------
        # PRIMARY
        # -----------------------------------------------------

        items.append(
            UserWorkspaceItemDTO(
                code=UserWorkspace.PRIMARY,
                label=cls._get_primary_label(
                    user_role
                ),
                is_active=False,
            )
        )

        # -----------------------------------------------------
        # STAFF / TEACHER
        # -----------------------------------------------------

        if staff_member_id is not None:

            has_staff = (
                await UserWorkspaceRepo
                .has_active_staff_member(
                    db,
                    staff_member_id=staff_member_id,
                )
            )

            if has_staff:

                # Для SCHOOL_STAFF основной workspace
                # уже является интерфейсом сотрудника.
                if user_role != UserRole.SCHOOL_STAFF:
                    cls._append_if_missing(
                        items,
                        code=UserWorkspace.STAFF,
                        label="Қызметкер",
                    )

                teaching_scope = (
                    await TeacherQuestionBankRepo
                    .list_teaching_scope(
                        db,
                        staff_member_id=staff_member_id,
                    )
                )

                # Для TEACHER основной workspace
                # уже является интерфейсом учителя.
                if (
                        teaching_scope
                        and user_role != UserRole.TEACHER
                ):
                    cls._append_if_missing(
                        items,
                        code=UserWorkspace.TEACHER,
                        label="Мұғалім",
                    )

        # -----------------------------------------------------
        # QUESTION BANK EXPERT
        # -----------------------------------------------------

        from app.core.feature_flags import assessment_enabled
        if not assessment_enabled():return items
        has_expert = (
            await QuestionBankExpertRepo
            .has_active_expert_scope(
                db,
                user_id=user_id,
            )
        )

        if has_expert:
            cls._append_if_missing(
                items,
                code=UserWorkspace.QUESTION_BANK_EXPERT,
                label="Сарапшы",
            )

        return items

    # =========================================================
    # ACTIVE WORKSPACE
    # =========================================================

    @staticmethod
    def _resolve_active_workspace(
        *,
        requested_workspace: UserWorkspace | None,
        available_codes: set[UserWorkspace],
    ) -> UserWorkspace:
        """
        Определяет активный workspace.

        Некорректный или уже недоступный workspace
        безопасно сбрасывается в PRIMARY.
        """

        if (
            requested_workspace is not None
            and requested_workspace in available_codes
        ):
            return requested_workspace

        return UserWorkspace.PRIMARY

    # =========================================================
    # ITEMS
    # =========================================================

    @staticmethod
    def _append_if_missing(
        items: list[UserWorkspaceItemDTO],
        *,
        code: UserWorkspace,
        label: str,
    ) -> None:
        """
        Не допускает дублирования workspace.

        Это особенно важно, когда PRIMARY по смыслу
        совпадает с дополнительным workspace.

        Например:
            UserRole.TEACHER + TEACHER workspace.
        """

        if any(
            item.code == code
            for item in items
        ):
            return

        items.append(
            UserWorkspaceItemDTO(
                code=code,
                label=label,
                is_active=False,
            )
        )

    # =========================================================
    # PRIMARY LABEL
    # =========================================================

    @staticmethod
    def _get_primary_label(
        role: UserRole,
    ) -> str:
        """
        UI-название основного интерфейса
        глобальной роли пользователя.
        """

        labels = {
            UserRole.SUPERUSER:
                "Суперадминистратор",

            UserRole.REGION_ADMIN:
                "Өңір әкімшісі",

            UserRole.REGION_STAFF:
                "Өңір қызметкері",

            UserRole.DISTRICT_ADMIN:
                "Аудан әкімшісі",

            UserRole.DISTRICT_STAFF:
                "Аудан қызметкері",

            UserRole.SCHOOL_ADMIN:
                "Мектеп әкімшісі",

            UserRole.SCHOOL_STAFF:
                "Мектеп қызметкері",

            UserRole.TEACHER:
                "Мұғалім",
        }

        return labels.get(
            role,
            role.value,
        )
