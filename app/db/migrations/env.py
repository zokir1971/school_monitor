from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# импорт Base и всех моделей
from app.db.base import Base  # noqa: E402
from app.modules.users import models as users_models  # noqa: F401,E402
from app.modules.org import models as org_models  # noqa: F401,E402
from app.modules.planning import models as planning_models  # noqa: F401,E402
from app.modules.planning import models_school as planning_models_school  # noqa: F401,E402
from app.modules.planning import models_month_plan as planning_models_month_plan  # noqa: F401,E402
from app.modules.staff import models_staff_school as staff_models_staff_school  # noqa: F401,E402
from app.modules.reports import models_documents as reports_models_documents  # noqa: F401,E402

target_metadata = Base.metadata

PUBLIC_SCHEMA = "public"
VERSION_TABLE = "alembic_version"


def include_object(_object, name, type_, _reflected, _compare_to):
    if type_ == "table" and name == VERSION_TABLE:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=False,
        include_object=include_object,
        version_table=VERSION_TABLE,
        version_table_schema=PUBLIC_SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        bootstrap = connection.execution_options(isolation_level="AUTOCOMMIT")
        bootstrap.execute(text("SET search_path TO public"))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=False,
            include_object=include_object,
            version_table=VERSION_TABLE,
            version_table_schema=PUBLIC_SCHEMA,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
