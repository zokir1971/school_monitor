"""SQL expressions shared by repositories; never used to issue queries in services."""

from typing import cast
from sqlalchemy import Table, func, select
from app.modules.assessment.models import (
    LearningObjective,
    QuestionBankItem,
    QuestionBankItemObjective,
)
from app.modules.assessment.models_learning_objective_reference import (
    LearningObjectiveQuarter,
)


def objective_quarter_matches(quarter):
    objective = cast(Table, LearningObjective.__table__).c
    allocation = cast(Table, LearningObjectiveQuarter.__table__).c
    return (
        select(allocation.learning_objective_id)
        .where(
            allocation.learning_objective_id == objective.id,
            allocation.quarter == quarter,
        )
        .correlate(LearningObjective.__table__)
        .exists()
    )


def objective_quarter_for_validation(quarter):
    # Selected quarter if allocated, otherwise retain the legacy value so the
    # existing service validation still rejects a mismatched objective.
    from sqlalchemy import case

    objective = cast(Table, LearningObjective.__table__).c
    return case((objective_quarter_matches(quarter), quarter), else_=objective.quarter)


def item_objective_quarter():
    item = cast(Table, QuestionBankItem.__table__).c
    objective = cast(Table, LearningObjective.__table__).c
    selected = (
        select(item.quarter)
        .where(
            item.id
            == cast(Table, QuestionBankItemObjective.__table__).c.question_bank_item_id
        )
        .scalar_subquery()
    )
    return func.coalesce(selected, objective.quarter)


def objective_display_title(language):
    from sqlalchemy import case, literal
    columns = cast(Table, LearningObjective.__table__).c
    title = columns.title_kz if language == "kz" else columns.title_ru
    suffix = case((columns.education_track == "emn", literal(" [ЕМН]")),
                  (columns.education_track == "ogn", literal(" [ОГН]")), else_=literal(""))
    return title + suffix


def objective_quarters_match(quarters):
    objective=cast(Table,LearningObjective.__table__).c
    allocation=cast(Table,LearningObjectiveQuarter.__table__).c
    return select(allocation.learning_objective_id).where(
        allocation.learning_objective_id==objective.id,
        allocation.quarter.in_(quarters)).correlate(LearningObjective.__table__).exists()

def item_quarters_match(item,quarters):
    """Every linked objective must have an effective task quarter in the range.

    Legacy cards have no own quarter: use their objective's legacy quarter, as
    in the existing exact-quarter bank filter. Never let a future link through.
    """
    from sqlalchemy import exists,or_
    link=cast(Table,QuestionBankItemObjective.__table__).alias()
    objective=cast(Table,LearningObjective.__table__).alias()
    effective=func.coalesce(item.c.quarter,objective.c.quarter)
    invalid=exists(select(1).select_from(link.join(objective,objective.c.id==link.c.learning_objective_id))
        .where(link.c.question_bank_item_id==item.c.id,
            or_(effective.is_(None),effective.not_in(quarters))).correlate(item))
    return ~invalid
