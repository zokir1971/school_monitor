"""Subject categories and automatic teaching policy; existing rule IDs stay unchanged."""
from alembic import op
import sqlalchemy as sa
import re

revision = 'b72d8e3fa105'
down_revision = 'a61c7d2e904b'
branch_labels = None
depends_on = None

CATEGORIES = [
    ('language_literature', 'Тіл және әдебиет', 'Язык и литература', 10),
    ('mathematics_informatics', 'Математика және информатика', 'Математика и информатика', 20),
    ('natural_sciences', 'Жаратылыстану', 'Естествознание', 30),
    ('human_society', 'Адам және қоғам', 'Человек и общество', 40),
    ('technology_arts', 'Технология және өнер', 'Технология и искусство', 50),
    ('physical_military', 'Дене шынықтыру және АӘД', 'Физкультура и НВП', 60),
]
# Frozen migration data: never import live application policies here.
LANGUAGE_ROLES = {
    'literacy', 'literary_reading', 'native_language', 'native_literature',
    'kz_language', 'kz_literature', 'kz_combined', 'ru_language', 'ru_literature',
    'ru_combined', 'english',
}
GENERAL_ROLES = {'general', 'mathematics', 'informatics', 'natural_science',
                 'physics', 'chemistry', 'biology', 'geography'}
ALIASES = {
    'language_literature': [
        'literacy', 'literary_reading', 'native_language', 'native_literature',
        'kazakh_language', 'kazakh_literature', 'kazakh_language_literature',
        'russian_language', 'russian_literature', 'russian_language_literature', 'english',
        'казахский язык', 'қазақ тілі', 'казахская литература', 'қазақ әдебиеті',
        'казахский язык и литература', 'қазақ тілі мен әдебиеті',
        'русский язык', 'орыс тілі', 'русская литература', 'орыс әдебиеті',
        'русский язык и литература', 'орыс тілі мен әдебиеті',
        'английский язык', 'ағылшын тілі', 'немецкий язык', 'неміс тілі',
        'французский язык', 'француз тілі', 'иностранный язык', 'шетел тілі',
        'родной язык', 'ана тілі', 'родная литература', 'ана әдебиеті',
        'узбекский язык', 'өзбек тілі', 'уйгурский язык', 'ұйғыр тілі',
        'таджикский язык', 'тәжік тілі', 'узбекская литература', 'өзбек әдебиеті',
        'уйгурская литература', 'ұйғыр әдебиеті', 'таджикская литература', 'тәжік әдебиеті',
        'литературное чтение', 'әдебиеттік оқу', 'обучение грамоте', 'сауат ашу',
        'азбука', 'әліппе', 'букварь',
    ],
    'mathematics_informatics': [
        'mathematics', 'math', 'algebra', 'algebra_and_analysis', 'algebra_and_calculus',
        'geometry', 'informatics', 'artificial_intelligence',
        'математика', 'алгебра', 'алгебра и начала анализа', 'алгебра и начало анализа',
        'алгебра және анализ бастамалары', 'геометрия', 'информатика',
        'информатика и искусственный интеллект', 'информатика және жасанды интеллект',
        'искусственный интеллект', 'жасанды интеллект', 'ии',
    ],
    'natural_sciences': [
        'natural_science', 'science', 'world_knowledge', 'physics', 'chemistry', 'biology', 'geography',
        'естествознание', 'жаратылыстану', 'познание мира', 'дүниетану', 'физика', 'химия',
        'биология', 'география',
    ],
    'human_society': [
        'kazakhstan_history', 'history_of_kazakhstan', 'world_history', 'law_basics',
        'история казахстана', 'қазақстан тарихы', 'всемирная история', 'дүниежүзі тарихы',
        'дүниежүзілік тарих', 'основы права', 'құқық негіздері',
    ],
    'technology_arts': [
        'music', 'art', 'artistic_labor', 'artistic_work', 'technology',
        'музыка', 'художественный труд', 'художественное труд', 'көркем еңбек',
        'трудовое обучение', 'еңбекке баулу', 'изобразительное искусство', 'бейнелеу өнері',
    ],
    'physical_military': [
        'physical_education', 'pe', 'military_training', 'basic_military_training',
        'физическая культура', 'физкультура', 'дене шынықтыру', 'нвп', 'аәд',
        'начальная военная подготовка', 'начальная военная и технологическая подготовка',
        'алғашқы әскери және технологиялық дайындық', 'алғашқы әскери дайындық',
    ],
}
POLICY_ALIASES = {
    'literacy': ['literacy', 'обучение грамоте', 'сауат ашу', 'азбука', 'әліппе', 'букварь'],
    'literary_reading': ['literary_reading', 'литературное чтение', 'әдебиеттік оқу'],
    'kz_language': ['kz_language', 'kazakh_language', 'казахский язык', 'қазақ тілі'],
    'kz_literature': ['kz_literature', 'kazakh_literature', 'казахская литература', 'қазақ әдебиеті'],
    'kz_combined': ['kz_combined', 'kazakh_language_literature', 'казахский язык и литература', 'қазақ тілі мен '
                                                                                                'әдебиеті'],
    'ru_language': ['ru_language', 'russian_language', 'русский язык', 'орыс тілі'],
    'ru_literature': ['ru_literature', 'russian_literature', 'русская литература', 'орыс әдебиеті'],
    'ru_combined': ['ru_combined', 'russian_language_literature', 'русский язык и литература',
                    'орыс тілі мен әдебиеті'],
    'native_language': ['native_language', 'узбекский язык', 'өзбек тілі', 'уйгурский язык', 'ұйғыр тілі',
                        'таджикский язык', 'тәжік тілі'],
    'native_literature': ['native_literature', 'узбекская литература', 'өзбек әдебиеті',
                          'уйгурская литература', 'ұйғыр әдебиеті', 'таджикская литература', 'тәжік әдебиеті'],
    'english': ['english', 'английский язык', 'ағылшын тілі'],
}


def normalize(value):
    return re.sub(
        r'\W+',
        ' ',
        (value or '').lower().replace('_', ' ').replace('ё', 'е'),
    ).strip()


def classify(subject, roles):
    keys = {normalize(subject[key]) for key in ('code', 'name_kz', 'name_ru') if subject[key]}
    candidates = {code for code, aliases in ALIASES.items()
                  if keys.intersection(normalize(alias) for alias in aliases)}
    role_categories = set()
    if roles.intersection(LANGUAGE_ROLES):
        role_categories.add('language_literature')
    if roles.intersection({'mathematics', 'informatics'}):
        role_categories.add('mathematics_informatics')
    if roles.intersection({'natural_science', 'physics', 'chemistry', 'biology', 'geography'}):
        role_categories.add('natural_sciences')
    candidates |= role_categories
    category = next(iter(candidates)) if len(candidates) == 1 else None
    normalized = {'general' if role in GENERAL_ROLES else role for role in roles}
    if len(normalized) == 1:
        policy = next(iter(normalized))
    elif normalized:
        policy = None
    elif category == 'language_literature':
        found = {code for code, aliases in POLICY_ALIASES.items()
                 if keys.intersection(normalize(alias) for alias in aliases)}
        policy = next(iter(found)) if len(found) == 1 else None
    else:
        policy = 'general'
    return category, policy


def backfill(bind):
    category_ids = dict(bind.execute(sa.text('SELECT code, id FROM subject_categories')).all())
    roles = {}
    for row in bind.execute(sa.text('SELECT subject_id, subject_role FROM curriculum_subject_rules')):
        roles.setdefault(row.subject_id, set()).add(row.subject_role)
    for subject in bind.execute(sa.text('SELECT id, code, name_kz, name_ru FROM subjects')).mappings().all():
        category, policy = classify(subject, roles.get(subject['id'], set()))
        bind.execute(sa.text('UPDATE subjects SET category_id=:category, curriculum_role=:policy WHERE id=:id'),
                     dict(category=category_ids.get(category), policy=policy, id=subject['id']))


def upgrade():
    op.create_table(
        'subject_categories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(80), nullable=False),
        sa.Column('name_kz', sa.String(255), nullable=False),
        sa.Column('name_ru', sa.String(255), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'),
        sa.UniqueConstraint('code', name='uq_subject_categories_code'),
    )
    op.add_column('subjects', sa.Column('category_id', sa.Integer(), nullable=True))
    op.add_column('subjects', sa.Column('curriculum_role', sa.String(30), nullable=True, server_default='general'))
    op.create_foreign_key('fk_subjects_category_id', 'subjects', 'subject_categories',
                          ['category_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_subjects_category_id', 'subjects', ['category_id'])
    categories = sa.table('subject_categories', sa.column('code', sa.String(80)), sa.column('name_kz', sa.String(255)),
                          sa.column('name_ru', sa.String(255)), sa.column('sort_order', sa.Integer()))
    op.bulk_insert(categories, [dict(zip(('code', 'name_kz', 'name_ru', 'sort_order'), row)) for row in CATEGORIES])
    backfill(op.get_bind())
    # Also supports deployments where earlier natural-subject SQL was not applied.
    op.execute('ALTER TABLE curriculum_subject_rules DROP CONSTRAINT IF EXISTS ck_curriculum_subject_role')
    values = ','.join("'" + role + "'" for role in sorted(LANGUAGE_ROLES | GENERAL_ROLES))
    op.create_check_constraint('ck_curriculum_subject_role', 'curriculum_subject_rules',
                               'subject_role IN (' + values + ')')


def downgrade():
    # Existing subjects and rule IDs remain intact. Category metadata is removed.
    op.drop_index('ix_subjects_category_id', table_name='subjects')
    op.drop_constraint('fk_subjects_category_id', 'subjects', type_='foreignkey')
    op.drop_column('subjects', 'curriculum_role')
    op.drop_column('subjects', 'category_id')
    op.drop_table('subject_categories')
    # Expanded compatibility check is retained: narrowing it could reject legacy rules.
