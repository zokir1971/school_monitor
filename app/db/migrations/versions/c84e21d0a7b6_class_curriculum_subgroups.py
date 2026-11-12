"""Class curriculum and automatic subject subgroups.

Revision ID: c84e21d0a7b6
Revises: a91d4e7b2c60
"""
from alembic import op
import sqlalchemy as sa

revision = 'c84e21d0a7b6'
down_revision = 'a91d4e7b2c60'
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    """ALTER TABLE school_classes ADD COLUMN instruction_language VARCHAR(5)""",
    """ALTER TABLE school_classes ADD CONSTRAINT ck_school_class_instruction_language CHECK (instruction_language IS 
    NULL OR instruction_language IN ('kz','ru','uz','tg','ug'))""",
    """CREATE TABLE subject_method_profiles (
	id SERIAL NOT NULL, 
	code VARCHAR(80) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
)""",
    """CREATE TABLE curriculum_subject_rules (
	id SERIAL NOT NULL, 
	instruction_language VARCHAR(5) NOT NULL, 
	grade_level INTEGER NOT NULL, 
	education_track VARCHAR(10) DEFAULT '' NOT NULL, 
	subject_id INTEGER NOT NULL, 
	subject_role VARCHAR(30) DEFAULT 'general' NOT NULL, 
	method_profile_id INTEGER, 
	split_threshold INTEGER, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_curriculum_subject_context UNIQUE (instruction_language, grade_level, education_track, subject_id), 
	CONSTRAINT ck_curriculum_language CHECK (instruction_language IN ('kz','ru','uz','tg','ug')), 
	CONSTRAINT ck_curriculum_grade CHECK (grade_level BETWEEN 1 AND 12), 
	CONSTRAINT ck_curriculum_track CHECK (education_track = '' OR (grade_level IN (10,11) AND education_track IN ('emn','ogn'))), 
	CONSTRAINT ck_curriculum_subject_role CHECK (subject_role IN ('general','kz_language','kz_literature','kz_combined','ru_language','ru_literature','ru_combined','english','informatics')), 
	CONSTRAINT ck_curriculum_split CHECK (split_threshold IS NULL OR split_threshold = 20), 
	FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT, 
	FOREIGN KEY(method_profile_id) REFERENCES subject_method_profiles (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE school_class_subjects (
	id SERIAL NOT NULL, 
	school_id INTEGER NOT NULL, 
	school_class_id INTEGER NOT NULL, 
	subject_id INTEGER NOT NULL, 
	rule_id INTEGER NOT NULL, 
	split_enabled BOOLEAN DEFAULT false NOT NULL, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(school_class_id, school_id) REFERENCES school_classes (id, school_id) ON DELETE RESTRICT, 
	CONSTRAINT uq_class_subject UNIQUE (school_class_id, subject_id), 
	CONSTRAINT uq_class_subject_school UNIQUE (id, school_id), 
	CONSTRAINT uq_class_subject_context UNIQUE (id, school_class_id, subject_id, school_id), 
	FOREIGN KEY(school_id) REFERENCES schools (id) ON DELETE RESTRICT, 
	FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT, 
	FOREIGN KEY(rule_id) REFERENCES curriculum_subject_rules (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE school_subject_subgroups (
	id SERIAL NOT NULL, 
	class_subject_id INTEGER NOT NULL, 
	school_id INTEGER NOT NULL, 
	school_class_id INTEGER NOT NULL, 
	subject_id INTEGER NOT NULL, 
	number INTEGER NOT NULL, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(class_subject_id, school_class_id, subject_id, school_id) REFERENCES school_class_subjects (id, school_class_id, subject_id, school_id) ON DELETE RESTRICT, 
	CONSTRAINT uq_subject_subgroup_number UNIQUE (class_subject_id, number), 
	CONSTRAINT uq_subgroup_offer_school UNIQUE (id, class_subject_id, school_id), 
	CONSTRAINT uq_subgroup_assignment_context UNIQUE (id, school_class_id, subject_id, school_id), 
	CONSTRAINT ck_subgroup_number CHECK (number IN (1,2))
)""",
    """CREATE TABLE school_subject_subgroup_members (
	id SERIAL NOT NULL, 
	class_subject_id INTEGER NOT NULL, 
	subgroup_id INTEGER NOT NULL, 
	school_id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	joined_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	left_at TIMESTAMP WITH TIME ZONE, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(subgroup_id, class_subject_id, school_id) REFERENCES school_subject_subgroups (id, class_subject_id, school_id) ON DELETE RESTRICT, 
	FOREIGN KEY(student_id, school_id) REFERENCES school_students (id, school_id) ON DELETE RESTRICT, 
	CONSTRAINT ck_subgroup_member_dates CHECK (left_at IS NULL OR left_at >= joined_at)
)""",
    """CREATE UNIQUE INDEX uq_active_subject_subgroup_member ON school_subject_subgroup_members (class_subject_id, student_id) WHERE is_active = true""",
    """CREATE INDEX ix_subgroup_member_school ON school_subject_subgroup_members (school_id, is_active)""",
    """ALTER TABLE school_class_subject_teachers ADD COLUMN subgroup_id INTEGER""",
    """ALTER TABLE school_class_subject_teachers ADD CONSTRAINT fk_teacher_subgroup_context FOREIGN KEY (subgroup_id, school_class_id, subject_id, school_id) REFERENCES school_subject_subgroups (id, school_class_id, subject_id, school_id) ON DELETE RESTRICT""",
    """DROP INDEX uq_active_class_subject_teacher""",
    """DROP INDEX uq_class_subject_primary_teacher""",
    """CREATE UNIQUE INDEX uq_active_class_subject_teacher ON school_class_subject_teachers (school_class_id, subject_id, staff_member_id, coalesce(subgroup_id, 0)) WHERE is_active = true AND staff_member_id IS NOT NULL""",
    """CREATE UNIQUE INDEX uq_class_subject_primary_teacher ON school_class_subject_teachers (school_class_id, subject_id, coalesce(subgroup_id, 0)) WHERE is_primary = true AND is_active = true""",
)
DOWNGRADE_SQL = (
    """DROP INDEX uq_active_class_subject_teacher""",
    """DROP INDEX uq_class_subject_primary_teacher""",
    """ALTER TABLE school_class_subject_teachers DROP CONSTRAINT fk_teacher_subgroup_context""",
    """ALTER TABLE school_class_subject_teachers DROP COLUMN subgroup_id""",
    """CREATE UNIQUE INDEX uq_active_class_subject_teacher ON school_class_subject_teachers (school_class_id, subject_id, staff_member_id) WHERE is_active = true AND staff_member_id IS NOT NULL""",
    """CREATE UNIQUE INDEX uq_class_subject_primary_teacher ON school_class_subject_teachers (school_class_id, subject_id) WHERE is_primary = true AND is_active = true""",
    """DROP TABLE school_subject_subgroup_members""",
    """DROP TABLE school_subject_subgroups""",
    """DROP TABLE school_class_subjects""",
    """DROP TABLE curriculum_subject_rules""",
    """DROP TABLE subject_method_profiles""",
    """ALTER TABLE school_classes DROP CONSTRAINT ck_school_class_instruction_language""",
    """ALTER TABLE school_classes DROP COLUMN instruction_language""",
)


def upgrade():
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade():
    # Refuse a destructive downgrade after this feature has been used.
    bind = op.get_bind()
    if bind.execute(
            sa.text("SELECT EXISTS(SELECT 1 FROM school_class_subjects) OR EXISTS(SELECT 1 FROM school_class_subject_teachers WHERE subgroup_id IS NOT NULL)")).scalar():
        raise RuntimeError(
            'Cannot downgrade populated curriculum/subgroups; preserve history and restore from a reviewed backup if needed.')
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
