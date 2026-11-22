import importlib.util
import io
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_postgresql_migration_and_reverse():
    path = Path(__file__).resolve().parents[2] / 'app/db/migrations/versions/d94f103ac527_user_ui_language.py'
    spec=importlib.util.spec_from_file_location('language_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.down_revision=='c83e9f40b216'
    output=io.StringIO()
    context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql': True,'output_buffer':output})
    with Operations.context(context): module.upgrade()
    sql=output.getvalue()
    assert 'ADD COLUMN ui_language VARCHAR(2)' in sql
    assert "ui_language IN ('ru', 'kk')" in sql
    assert 'assessment' not in sql.lower()
    output.seek(0);output.truncate()
    with Operations.context(context): module.downgrade()
    assert 'DROP COLUMN ui_language' in output.getvalue()
