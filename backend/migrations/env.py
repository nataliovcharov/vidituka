from logging.config import fileConfig

from alembic import context
from alembic.environment import IncludeNameFn, NameFilterParentNames, NameFilterType
from geoalchemy2 import alembic_helpers
from sqlalchemy import Connection, engine_from_config, pool, text

from vidituka.config import get_settings
from vidituka.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# tests pass their own url, otherwise use the app settings
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def skip_extension_tables(connection: Connection) -> IncludeNameFn:
    # postgis and the image's extra extensions (tiger geocoder, topology) bring their own tables
    owned: set[str] = set(
        connection.execute(
            text(
                "SELECT c.relname FROM pg_class c"
                " JOIN pg_depend d ON d.objid = c.oid AND d.deptype = 'e'"
                " WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')"
            )
        ).scalars()
    )
    # end the read so alembic opens and commits its own transaction
    connection.rollback()

    def include_name(
        name: str | None, type_: NameFilterType, parent_names: NameFilterParentNames
    ) -> bool:
        if type_ == "table":
            return name not in owned
        if type_ in {"index", "unique_constraint", "foreign_key_constraint", "column"}:
            return parent_names.get("table_name") not in owned
        return True

    return include_name


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        render_item=alembic_helpers.render_item,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=skip_extension_tables(connection),
            # spatial columns and their indexes
            include_object=alembic_helpers.include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
