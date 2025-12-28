"""
Database initialization and migration utilities for Hopper.
"""

import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from hopper.database.connection import create_sync_engine, get_database_url
from hopper.models import Base


def init_database(engine: Engine | None = None, create_tables: bool = True) -> None:
    """
    Initialize the database schema.

    Args:
        engine: SQLAlchemy engine (creates default if None)
        create_tables: If True, create all tables (for development)

    Note:
        In production, use Alembic migrations instead of create_all().
    """
    if engine is None:
        engine = create_sync_engine()

    if create_tables:
        # Create all tables from models
        Base.metadata.create_all(bind=engine)


def run_migrations(target: str = "head", alembic_ini: str | None = None) -> int:
    """
    Run Alembic migrations programmatically.

    Args:
        target: Migration target (default: "head" for latest)
        alembic_ini: Path to alembic.ini file

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Find alembic.ini if not provided
    if alembic_ini is None:
        # Look for alembic.ini in common locations
        possible_paths = [
            Path.cwd() / "alembic.ini",
            Path(__file__).parent.parent.parent.parent / "alembic.ini",
        ]
        for path in possible_paths:
            if path.exists():
                alembic_ini = str(path)
                break

    if alembic_ini is None:
        raise FileNotFoundError("Could not find alembic.ini")

    # Run alembic upgrade
    cmd = [sys.executable, "-m", "alembic", "-c", alembic_ini, "upgrade", target]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Migration failed: {result.stderr}", file=sys.stderr)

    return result.returncode


def check_database_health(engine: Engine | None = None) -> bool:
    """
    Check if database connection is healthy.

    Args:
        engine: SQLAlchemy engine (creates default if None)

    Returns:
        True if database is healthy, False otherwise
    """
    if engine is None:
        engine = create_sync_engine()

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_database_health_async(engine: AsyncEngine | None = None) -> bool:
    """
    Check if database connection is healthy (async version).

    Args:
        engine: SQLAlchemy AsyncEngine (creates default if None)

    Returns:
        True if database is healthy, False otherwise
    """
    from hopper.database.connection import create_async_engine_instance

    if engine is None:
        engine = create_async_engine_instance()

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def drop_all_tables(engine: Engine | None = None, confirm: bool = False) -> None:
    """
    Drop all database tables (DESTRUCTIVE - USE WITH CAUTION).

    Args:
        engine: SQLAlchemy engine (creates default if None)
        confirm: Must be True to actually drop tables (safety check)

    Raises:
        ValueError: If confirm is not True
    """
    if not confirm:
        raise ValueError("Must set confirm=True to drop all tables")

    if engine is None:
        engine = create_sync_engine()

    Base.metadata.drop_all(bind=engine)


def reset_database(engine: Engine | None = None, confirm: bool = False) -> None:
    """
    Reset database by dropping and recreating all tables (DESTRUCTIVE).

    Args:
        engine: SQLAlchemy engine (creates default if None)
        confirm: Must be True to actually reset database (safety check)

    Raises:
        ValueError: If confirm is not True
    """
    if not confirm:
        raise ValueError("Must set confirm=True to reset database")

    if engine is None:
        engine = create_sync_engine()

    # Drop all tables
    drop_all_tables(engine, confirm=True)

    # Recreate all tables
    init_database(engine, create_tables=True)


def get_database_info() -> dict:
    """
    Get information about the database configuration.

    Returns:
        Dictionary with database configuration details
    """
    url = get_database_url(async_mode=False)

    # Parse database type
    db_type = "unknown"
    if url.startswith("sqlite"):
        db_type = "sqlite"
    elif url.startswith("postgresql"):
        db_type = "postgresql"

    return {
        "url": url,
        "type": db_type,
        "async_url": get_database_url(async_mode=True),
    }
