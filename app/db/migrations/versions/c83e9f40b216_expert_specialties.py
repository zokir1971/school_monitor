"""Expert specialties and editable subject/grade/instruction-language rules.

Existing expert IDs, user links and review history are preserved.
"""
from alembic import op
import sqlalchemy as sa
import re

revision = 'c83e9f40b216'
down_revision = 'b72d8e3fa105'
branch_labels = None
depends_on = None

SPECIALTIES = [
    ('primary', 'Бастауыш сынып мұғалімі', 'Учитель начальных классов'),
    ('math', 'Математика мұғалімі', 'Учитель математики'),
    ('informatics', 'Информатика мұғалімі', 'Учитель информатики'),
    ('physics', 'Физика мұғалімі', 'Учитель физики'),
    ('chemistry', 'Химия мұғалімі', 'Учитель химии'),
    ('biology', 'Биология мұғалімі', 'Учитель биологии'),
    ('geography', 'География мұғалімі', 'Учитель географии'),
    ('history', 'Тарих мұғалімі', 'Учитель истории'),
    ('kazakh', 'Қазақ тілі мен әдебиеті мұғалімі', 'Учитель казахского языка и литературы'),
    ('russian', 'Орыс тілі мен әдебиеті мұғалімі', 'Учитель русского языка и литературы'),
    ('uzbek', 'Өзбек тілі мен әдебиеті мұғалімі', 'Учитель узбекского языка и литературы'),
    ('uyghur', 'Ұйғыр тілі мен әдебиеті мұғалімі', 'Учитель уйгурского языка и литературы'),
    ('tajik', 'Тәжік тілі мен әдебиеті мұғалімі', 'Учитель таджикского языка и литературы'),
    ('english', 'Ағылшын тілі мұғалімі', 'Учитель английского языка'),
]
ALIASES = {
    'math': ('математика',),
    'algebra': ('алгебра',),
    'analysis': ('алгебра и начала анализа', 'алгебра и начало анализа', 'алгебра және анализ бастамалары',
                 'алгебра және анализдің бастамалары'),
    'geometry': ('геометрия',),
    'digital': (
        'цифровая грамотность', 'цифровая грамотность и ии', 'цифрлық сауаттылық', 'цифрлық сауаттылық және жи'),
    'informatics': ('информатика', 'информатика и ии', 'информатика және жи'),
    'physics': ('физика',), 'chemistry': ('химия',), 'biology': ('биология',), 'geography': ('география',),
    'science': ('естествознание', 'жаратылыстану'),
    'history_kz': ('история казахстана', 'қазақстан тарихы'),
    'history_world': ('всемирная история', 'дүниежүзі тарихы', 'дүние жүзі тарихы'),
    'law': ('основы права', 'основы право', 'құқық негіздері'),
    'kz': ('казахский язык', 'қазақ тілі'), 'kz_lit': ('казахская литература', 'қазақ әдебиеті'),
    'kz_combined': ('казахский язык и литература', 'қазақ тілі мен әдебиеті'),
    'ru': ('русский язык', 'орыс тілі'), 'ru_lit': ('русская литература', 'орыс әдебиеті'),
    'ru_combined': ('русский язык и литература', 'орыс тілі мен әдебиеті'),
    'uz': ('узбекский язык', 'өзбек тілі'), 'uz_lit': ('узбекская литература', 'өзбек әдебиеті'),
    'ug': ('уйгурский язык', 'ұйғыр тілі'), 'ug_lit': ('уйгурская литература', 'ұйғыр әдебиеті'),
    'tg': ('таджикский язык', 'тәжік тілі'), 'tg_lit': ('таджикская литература', 'тәжік әдебиеті'),
    'english': ('английский язык', 'ағылшын тілі'),
}


def normalize(value):
    return re.sub(r'\W+', ' ', (value or '').casefold().replace('ё', 'е').replace('_', ' ')).strip()


def subject_kind(row):
    names = {normalize(row.get('name_kz')), normalize(row.get('name_ru'))}
    for kind, aliases in ALIASES.items():
        if names.intersection(normalize(a) for a in aliases):
            return kind
    return {'kz_language': 'kz', 'kz_literature': 'kz_lit', 'kz_combined': 'kz_combined',
            'ru_language': 'ru', 'ru_literature': 'ru_lit', 'ru_combined': 'ru_combined',
            'english': 'english'}.get(row.get('curriculum_role'))


def rules_for(kind):
    """Frozen agreed policy. Each tuple is specialty, grade range, instruction language."""
    result = []

    def add(specialty_code, grade_from, grade_to, languages=('all',)):
        result.extend(
            (specialty_code, grade_from, grade_to, language_code)
            for language_code in languages
        )

    if kind not in {'kz', 'kz_lit', 'kz_combined', 'ru', 'ru_lit', 'ru_combined', 'digital', 'informatics', 'english'}:
        add('primary', 1, 4)
    if kind == 'kz':
        add('primary', 1, 4, ('kz',))
        add('kazakh', 1, 4, ('ru', 'uz', 'ug', 'tg'))
        add('kazakh', 5, 11, ('kz',))
    elif kind == 'kz_combined':
        add('kazakh', 5, 11, ('ru', 'uz', 'ug', 'tg'))
    elif kind == 'kz_lit':
        add('primary', 1, 4, ('kz',))
        add('kazakh', 5, 11, ('kz',))
    elif kind == 'ru':
        add('primary', 1, 4, ('ru',))
        add('russian', 1, 4, ('kz', 'uz', 'ug', 'tg'))
        add('russian', 5, 11, ('ru',))
    elif kind == 'ru_combined':
        add('russian', 5, 11, ('kz', 'uz', 'ug', 'tg'))
    elif kind == 'ru_lit':
        add('primary', 1, 4, ('ru',))
        add('russian', 5, 11, ('ru',))
    ranges = {'math': ('math', 5, 6), 'algebra': ('math', 7, 9), 'analysis': ('math', 10, 11),
              'geometry': ('math', 7, 11),
              'digital': ('informatics', 1, 4), 'informatics': ('informatics', 5, 11),
              'physics': ('physics', 7, 11), 'chemistry': ('chemistry', 7, 11), 'biology': ('biology', 7, 11),
              'science': ('geography', 5, 6), 'geography': ('geography', 7, 11),
              'history_kz': ('history', 5, 11), 'history_world': ('history', 5, 11), 'law': ('history', 9, 11),
              'english': ('english', 3, 11)}
    if kind in ranges:
        add(*ranges[kind])
    for prefix, sp, lang in [('uz', 'uzbek', 'uz'), ('ug', 'uyghur', 'ug'), ('tg', 'tajik', 'tg')]:
        if kind in (prefix, prefix + '_lit'):
            add(sp, 5, 11, (lang,))
    return result


def upgrade():
    op.create_table('qb_expert_specialties',
                    sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('code', sa.String(80), nullable=False, unique=True),
                    sa.Column('name_kz', sa.String(200), nullable=False),
                    sa.Column('name_ru', sa.String(200), nullable=False),
                    sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.true()))
    op.create_table('qb_expert_rules',
                    sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('specialty_id', sa.Integer,
                              sa.ForeignKey('qb_expert_specialties.id', ondelete='RESTRICT'), nullable=False),
                    sa.Column('subject_id', sa.Integer, sa.ForeignKey('subjects.id', ondelete='RESTRICT'),
                              nullable=False),
                    sa.Column('grade_from', sa.Integer, nullable=False),
                    sa.Column('grade_to', sa.Integer, nullable=False),
                    sa.Column('instruction_language', sa.String(8), nullable=False, server_default='all'),
                    sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.true()),
                    sa.CheckConstraint('grade_from BETWEEN 1 AND 12 AND grade_to BETWEEN grade_from AND 12',
                                       name='ck_qb_expert_rule_grades'),
                    sa.CheckConstraint("instruction_language IN ('all','kz','ru','uz','ug','tg')",
                                       name='ck_qb_expert_rule_language'),
                    sa.UniqueConstraint('specialty_id', 'subject_id', 'grade_from', 'grade_to', 'instruction_language',
                                        name='uq_qb_expert_rule'))
    op.create_index('ix_qb_expert_rule_scope', 'qb_expert_rules', ['specialty_id', 'subject_id', 'is_active'])
    op.add_column('question_bank_experts', sa.Column('specialty_id', sa.Integer, nullable=True))
    op.create_foreign_key('fk_qb_expert_specialty', 'question_bank_experts', 'qb_expert_specialties', ['specialty_id'],
                          ['id'], ondelete='RESTRICT')
    op.create_index('ix_question_bank_experts_specialty_id', 'question_bank_experts', ['specialty_id'])
    op.alter_column('question_bank_experts', 'subject_id', existing_type=sa.Integer(), nullable=True)
    db = op.get_bind()
    for code, kz, ru in SPECIALTIES:
        db.execute(sa.text('INSERT INTO qb_expert_specialties(code,name_kz,name_ru) VALUES(:code,:kz,:ru)'),
                   dict(code=code, kz=kz, ru=ru))
    rows = db.execute(
        sa.text('SELECT code, id FROM qb_expert_specialties')
    ).mappings().all()

    specialties = {
        str(row['code']): int(row['id'])
        for row in rows
    }
    subjects = db.execute(sa.text('SELECT id,name_kz,name_ru,curriculum_role FROM subjects')).mappings().all()
    # One registered subject becomes a specialty; unrecognized assignments require explicit selection.
    owners = {'math': 'math', 'algebra': 'math', 'analysis': 'math', 'geometry': 'math', 'digital': 'informatics',
              'informatics': 'informatics',
              'science': 'geography', 'geography': 'geography', 'physics': 'physics', 'chemistry': 'chemistry',
              'biology': 'biology',
              'history_kz': 'history', 'history_world': 'history', 'law': 'history', 'english': 'english',
              'kz': 'kazakh', 'kz_lit': 'kazakh', 'kz_combined': 'kazakh', 'ru': 'russian', 'ru_lit': 'russian',
              'ru_combined': 'russian',
              'uz': 'uzbek', 'uz_lit': 'uzbek', 'ug': 'uyghur', 'ug_lit': 'uyghur', 'tg': 'tajik', 'tg_lit': 'tajik'}
    for sub in subjects:
        kind = subject_kind(sub)
        for sp, lo, hi, lang in rules_for(kind):
            db.execute(sa.text(
                'INSERT INTO qb_expert_rules(specialty_id,subject_id,grade_from,grade_to,instruction_language) '
                'VALUES(:sp,:sub,:lo,:hi,:lang)'),
                dict(sp=specialties[sp], sub=sub['id'], lo=lo, hi=hi, lang=lang))
        if kind in owners:
            db.execute(sa.text('UPDATE question_bank_experts SET specialty_id=:sp WHERE subject_id=:sub'),
                       dict(sp=specialties[owners[kind]], sub=sub['id']))
    primary_names = {normalize(x) for x in
                     ('Учитель начальных классов', 'Бастауыш сынып мұғалімі', 'Начальные классы', 'Бастауыш сынып')}
    for ex in db.execute(sa.text('SELECT id,specialty_text FROM question_bank_experts')).mappings():
        if normalize(ex['specialty_text']) in primary_names:
            db.execute(sa.text('UPDATE question_bank_experts SET specialty_id=:sp WHERE id=:id'),
                       dict(sp=specialties['primary'], id=ex['id']))


def downgrade():
    # New specialty-only records have no legacy subject; do not fabricate one or delete experts.
    db = op.get_bind()
    if db.execute(sa.text('SELECT count(*) FROM question_bank_experts WHERE subject_id IS NULL')).scalar_one():
        raise RuntimeError('Downgrade requires assigning legacy subject_id to specialty-only experts first.')
    op.alter_column('question_bank_experts', 'subject_id', existing_type=sa.Integer(), nullable=False)
    op.drop_index('ix_question_bank_experts_specialty_id', table_name='question_bank_experts')
    op.drop_constraint('fk_qb_expert_specialty', 'question_bank_experts', type_='foreignkey')
    op.drop_column('question_bank_experts', 'specialty_id')
    op.drop_table('qb_expert_rules')
    op.drop_table('qb_expert_specialties')
