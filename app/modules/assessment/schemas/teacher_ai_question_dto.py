"""Teacher input for generating one Question Bank draft, independently of Blueprint."""
from dataclasses import dataclass
from decimal import Decimal
from app.modules.assessment.enums import AssessmentLanguage, AssessmentQuestionDifficulty, AssessmentQuestionType


@dataclass(slots=True, frozen=True)
class TeacherAIQuestionInputDTO:
    subject_id: int
    grade_level: int
    quarter: int
    objective_id: int
    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage
    max_score: Decimal
    title: str | None = None
    additional_requirements: str | None = None

    education_track: str | None = None

    creation_plan: tuple[dict, ...] = ()

    source_image_key: str | None = None
    image_option_keys: tuple[str, ...] = ()
