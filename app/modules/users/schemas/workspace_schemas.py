# app/modules/users/schemas/workspace_schemas.py

from __future__ import annotations

from dataclasses import dataclass

from app.modules.users.enums import (
    UserRole,
    UserWorkspace,
)


# ============================================================
# WORKSPACE ITEM
# ============================================================


@dataclass(frozen=True, slots=True)
class UserWorkspaceItemDTO:
    """
    Один доступный рабочий интерфейс пользователя.

    Workspace не изменяет User.role.

    Например, пользователь с глобальной ролью SCHOOL_ADMIN
    может дополнительно иметь интерфейсы:

        STAFF
        TEACHER
        QUESTION_BANK_EXPERT
    """

    code: UserWorkspace

    label: str

    is_active: bool


# ============================================================
# WORKSPACE CONTEXT
# ============================================================


@dataclass(frozen=True, slots=True)
class UserWorkspaceContextDTO:
    """
    Полный контекст рабочих интерфейсов пользователя.

    Используется:
    - для определения текущего интерфейса;
    - для построения переключателя в base.html;
    - для проверки наличия дополнительных workspace.
    """

    user_role: UserRole

    active: UserWorkspace

    items: list[UserWorkspaceItemDTO]

    # --------------------------------------------------------
    # COMMON
    # --------------------------------------------------------

    @property
    def can_switch(self) -> bool:
        """
        Показывать переключатель только тогда,
        когда пользователю доступно более одного интерфейса.
        """

        return len(self.items) > 1

    @property
    def active_item(self) -> UserWorkspaceItemDTO | None:
        """
        DTO текущего активного интерфейса.
        """

        for item in self.items:
            if item.code == self.active:
                return item

        return None

    @property
    def active_label(self) -> str:
        """
        Название текущего интерфейса для UI.
        """

        item = self.active_item

        if item is None:
            return ""

        return item.label

    # --------------------------------------------------------
    # AVAILABLE WORKSPACES
    # --------------------------------------------------------

    def has_workspace(
        self,
        workspace: UserWorkspace,
    ) -> bool:
        """
        Проверяет, доступен ли пользователю workspace.
        """

        return any(
            item.code == workspace
            for item in self.items
        )

    @property
    def has_staff_workspace(self) -> bool:
        return self.has_workspace(
            UserWorkspace.STAFF
        )

    @property
    def has_teacher_workspace(self) -> bool:
        return self.has_workspace(
            UserWorkspace.TEACHER
        )

    @property
    def has_question_bank_expert_workspace(self) -> bool:
        return self.has_workspace(
            UserWorkspace.QUESTION_BANK_EXPERT
        )

    # --------------------------------------------------------
    # ACTIVE WORKSPACE
    # --------------------------------------------------------

    @property
    def is_primary(self) -> bool:
        return self.active == UserWorkspace.PRIMARY

    @property
    def is_staff(self) -> bool:
        return self.active == UserWorkspace.STAFF

    @property
    def is_teacher(self) -> bool:
        return self.active == UserWorkspace.TEACHER

    @property
    def is_question_bank_expert(self) -> bool:
        return (
            self.active
            == UserWorkspace.QUESTION_BANK_EXPERT
        )
