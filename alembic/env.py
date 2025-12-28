import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add the src directory to the Python path
src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_path))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models for autogenerate support
from hopper.models import Base  # noqa: E402

# Set target metadata for autogenerate
target_metadata = Base.metadata

# Override sqlalchemy.url from environment variable if set
database_url = os.getenv("DATABASE_URL", "sqlite:///./hopper.db")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_name(name, type_, parent_names):
    """Exclude certain objects from autogenerate."""
    # Skip indexes that are automatically created by the database
    if type_ == "index" and name and name.startswith("_"):
        return False
    return True


def render_item(type_, obj, autogen_context):
    """Customize rendering of migration items."""
    return False


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Compare types to avoid false differences between PostgreSQL and SQLite."""
    # For SQLite, ignore differences between JSON and JSONB
    if context.dialect.name == "sqlite":
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy.types import JSON

        if isinstance(metadata_type, JSONB) and str(inspected_type).upper() in ("JSON", "TEXT"):
            return False

    return None  # Use default comparison


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        compare_type=compare_type,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            compare_type=compare_type,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
