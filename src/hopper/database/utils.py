"""
Database utilities and helper functions.
"""
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from hopper.database.connection import create_sync_engine, get_database_url
from hopper.models import Base


def build_database_url(
    db_type: str = "sqlite",
    host: str = "localhost",
    port: Optional[int] = None,
    database: str = "hopper",
    username: Optional[str] = None,
    password: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """
    Build a database URL from components.

    Args:
        db_type: Database type ("sqlite" or "postgresql")
        host: Database host
        port: Database port (uses default if None)
        database: Database name
        username: Database username
        password: Database password
        **kwargs: Additional connection parameters

    Returns:
        Database URL string

    Examples:
        >>> build_database_url("sqlite", database="test.db")
        'sqlite:///./test.db'

        >>> build_database_url("postgresql", username="user", password="pass")
        'postgresql://user:pass@localhost/hopper'
    """
    if db_type == "sqlite":
        return f"sqlite:///./{database}" if not database.startswith("/") else f"sqlite:///{database}"

    # PostgreSQL
    if db_type == "postgresql":
        if not port:
            port = 5432

        auth = ""
        if username:
            auth = username
            if password:
                auth = f"{username}:{password}"
            auth += "@"

        url = f"postgresql://{auth}{host}:{port}/{database}"

        # Add query parameters
        if kwargs:
            params = "&".join(f"{k}={v}" for k, v in kwargs.items())
            url = f"{url}?{params}"

        return url

    raise ValueError(f"Unsupported database type: {db_type}")


def run_migration_runner(
    target: str = "head", revision: Optional[str] = None
) -> int:
    """
    Run Alembic migrations using the alembic command.

    Args:
        target: Migration target ("head", "base", or specific revision)
        revision: Optional revision ID for rollback

    Returns:
        Exit code (0 for success)
    """
    cmd = [sys.executable, "-m", "alembic", "upgrade", target]
    if revision:
        cmd = [sys.executable, "-m", "alembic", "downgrade", revision]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Migration failed:\n{result.stderr}", file=sys.stderr)

    return result.returncode


def dump_schema(engine: Optional[Engine] = None) -> Dict[str, Any]:
    """
    Dump database schema information for debugging.

    Args:
        engine: SQLAlchemy engine (creates default if None)

    Returns:
        Dictionary with schema information
    """
    if engine is None:
        engine = create_sync_engine()

    inspector = inspect(engine)
    schema = {
        "tables": {},
        "database_url": get_database_url(),
    }

    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        indexes = inspector.get_indexes(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)

        schema["tables"][table_name] = {
            "columns": [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col["nullable"],
                    "default": col.get("default"),
                }
                for col in columns
            ],
            "indexes": [
                {
                    "name": idx["name"],
                    "columns": idx["column_names"],
                    "unique": idx["unique"],
                }
                for idx in indexes
            ],
            "foreign_keys": [
                {
                    "name": fk["name"],
                    "constrained_columns": fk["constrained_columns"],
                    "referred_table": fk["referred_table"],
                    "referred_columns": fk["referred_columns"],
                }
                for fk in foreign_keys
            ],
        }

    return schema


def reset_database_dev_only(engine: Optional[Engine] = None) -> None:
    """
    Reset database for development (DROP and CREATE all tables).

    WARNING: This is DESTRUCTIVE and should only be used in development!

    Args:
        engine: SQLAlchemy engine (creates default if None)

    Raises:
        RuntimeError: If called with a production database
    """
    if engine is None:
        engine = create_sync_engine()

    # Safety check - don't allow reset on production databases
    url = str(engine.url)
    if "localhost" not in url and ":memory:" not in url and "test" not in url:
        raise RuntimeError(
            "Cannot reset database: appears to be a production database. "
            "Only localhost, in-memory, or test databases can be reset."
        )

    # Drop all tables
    Base.metadata.drop_all(bind=engine)

    # Recreate all tables
    Base.metadata.create_all(bind=engine)


def vacuum_database(engine: Optional[Engine] = None) -> None:
    """
    Run VACUUM on SQLite database to reclaim space.

    This is a no-op for PostgreSQL databases.

    Args:
        engine: SQLAlchemy engine (creates default if None)
    """
    if engine is None:
        engine = create_sync_engine()

    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            # Need to close transaction for VACUUM
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("VACUUM"))


def get_table_row_counts(engine: Optional[Engine] = None) -> Dict[str, int]:
    """
    Get row counts for all tables.

    Args:
        engine: SQLAlchemy engine (creates default if None)

    Returns:
        Dictionary mapping table names to row counts
    """
    if engine is None:
        engine = create_sync_engine()

    inspector = inspect(engine)
    counts = {}

    with engine.connect() as conn:
        for table_name in inspector.get_table_names():
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            counts[table_name] = result.scalar() or 0

    return counts


def analyze_database_statistics(engine: Optional[Engine] = None) -> Dict[str, Any]:
    """
    Analyze database and return statistics.

    Args:
        engine: SQLAlchemy engine (creates default if None)

    Returns:
        Dictionary with database statistics
    """
    if engine is None:
        engine = create_sync_engine()

    schema = dump_schema(engine)
    row_counts = get_table_row_counts(engine)

    return {
        "database_url": get_database_url(),
        "database_type": engine.dialect.name,
        "table_count": len(schema["tables"]),
        "tables": list(schema["tables"].keys()),
        "row_counts": row_counts,
        "total_rows": sum(row_counts.values()),
    }
