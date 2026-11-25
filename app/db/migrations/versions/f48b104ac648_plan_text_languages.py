"""Store language versions without changing plan identities or task links."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f48b104ac648'
down_revision = 'f47b104ac647'
branch_labels = None
depends_on = None

TABLES={
 'plan_directions':('short_title','full_title'),
 'plan_template_directions':('title_override',),
 'plan_template_rows_4':('control_object','risk_text','decision_text'),
 'school_plan_rows_4':('control_object','risk_text','decision_text'),
 'plan_template_rows_11':('topic','goal','control_object','control_type','methods','deadlines','responsibles','review_place','management_decision','second_control'),
 'school_plan_rows_11':('topic','goal','control_object','control_type','methods','deadlines','responsibles','review_place','management_decision','second_control'),
}


def upgrade():
    for table,names in TABLES.items():
        op.add_column(table,sa.Column('text_i18n',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
        pairs=', '.join("'%s', %s"%(name,name) for name in names)
        value=f'jsonb_build_object({pairs})'
        op.execute(sa.text(f"UPDATE {table} SET text_i18n = jsonb_build_object('_base_language','kk','_base',{value},'kk',{value})"))


def downgrade():
    # Code can be rolled back with the additional column retained. Refuse data loss.
    for table in TABLES:
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {table} WHERE text_i18n ? 'ru' OR text_i18n->>'_base_language'='ru' LIMIT 1")).first():
            raise RuntimeError('Language versions exist. Export them before removing the localization columns.')
    for table in reversed(TABLES):
        op.drop_column(table,'text_i18n')
