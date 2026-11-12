"""Single SQL boundary for queue, direct review access and decisions.

Instruction language belongs to the objective programme, never to item.language.
Every objective must be covered; a partially covered multilingual programme is denied.
"""
from typing import Any, cast

from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import FromClause, Exists

from sqlalchemy import and_, or_, exists, select, func
from app.modules.assessment.models import QuestionBankItem, QuestionBankItemObjective, LearningObjective
from app.modules.assessment.models_learning_objective_reference import LearningObjectiveProgram
from app.modules.assessment.models_question_bank_experts import (
    QuestionBankExpert, QuestionBankExpertRule, QuestionBankExpertSpecialty,
)


def _column(table: FromClause, name: str) -> ColumnElement[Any]:
    """Typed access to a real SQL column; cast does not alter the SQL expression."""
    return cast(ColumnElement[Any], table.c[name])


def review_scope_clause(user_id: int) -> ColumnElement[bool]:
    item = QuestionBankItem.__table__
    link = QuestionBankItemObjective.__table__.alias('scope_link')
    objective = LearningObjective.__table__.alias('scope_objective')
    program = LearningObjectiveProgram.__table__.alias('scope_program')
    rule = QuestionBankExpertRule.__table__.alias('scope_rule')
    expert = QuestionBankExpert.__table__.alias('scope_expert')
    specialty = QuestionBankExpertSpecialty.__table__.alias('scope_specialty')
    language = func.lower(func.trim(_column(program, "instruction_language")))

    def covered(language_clause: ColumnElement[bool]) -> Exists:
        return exists(select(1).select_from(
            rule.join(expert, _column(expert, "specialty_id") == _column(rule, "specialty_id"))
            .join(specialty, _column(specialty, "id") == _column(rule, "specialty_id"))
        ).where(
            _column(expert, "user_id") == user_id, _column(expert, "is_active").is_(True),
            _column(specialty, "is_active").is_(True), _column(rule, "is_active").is_(True),
            _column(rule, "subject_id") == _column(item, "subject_id"),
            _column(item, "grade_level").between(_column(rule, "grade_from"), _column(rule, "grade_to")),
            language_clause,
        ).correlate(item, objective, program))

    allowed = or_(
        covered(_column(rule, "instruction_language") == 'all'),
        and_(language.in_(['kz', 'kk', 'ru', 'uz', 'ug', 'tg']), covered(
            or_(_column(rule, "instruction_language") == language,
                and_(language == 'kk', _column(rule, "instruction_language") == 'kz')))),
        and_(language == 'uz_ug_tg', *[
            covered(_column(rule, "instruction_language") == lang) for lang in ('uz', 'ug', 'tg')
        ]),
    )
    objectives = link.join(objective, _column(objective, "id") == _column(link, "learning_objective_id")).outerjoin(
        program, _column(program, "id") == _column(objective, "program_id"),
    )
    linked = exists(select(1).select_from(link).where(
        _column(link, "question_bank_item_id") == _column(item, "id"),
    ).correlate(item))
    invalid = exists(select(1).select_from(objectives).where(
        _column(link, "question_bank_item_id") == _column(item, "id"),
        or_(_column(objective, "subject_id") != _column(item, "subject_id"),
            _column(objective, "grade_level") != _column(item, "grade_level"),
            and_(_column(objective, "program_id").is_not(None),
                 or_(_column(program, "id").is_(None), _column(program, "subject_id") != _column(item, "subject_id"))),
            ~func.coalesce(allowed, False)),
    ).correlate(item))
    return and_(linked, ~invalid)


async def active_scope_subject_ids(db, user_id: int) -> list[int]:
    result = await db.execute(select(QuestionBankExpertRule.subject_id).join(
        QuestionBankExpert, QuestionBankExpert.specialty_id == QuestionBankExpertRule.specialty_id,
    ).join(QuestionBankExpertSpecialty,
           QuestionBankExpertSpecialty.id == QuestionBankExpertRule.specialty_id).where(
        QuestionBankExpert.user_id == user_id, QuestionBankExpert.is_active.is_(True),
        QuestionBankExpertSpecialty.is_active.is_(True), QuestionBankExpertRule.is_active.is_(True),
    ).distinct())
    return list(result.scalars().all())
