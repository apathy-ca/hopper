"""
Database connection management for Hopper.

Provides database engine creation, session management, and connection pooling
configuration for both PostgreSQL (production) and SQLite (development).
"""
import os
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, event, pool
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

# Default database URLs
DEFAULT_SQLITE_URL = "sqlite:///./hopper.db"
DEFAULT_POSTGRES_URL = "postgresql://hopper:hopper@localhost/hopper"


def get_database_url(async_mode: bool = False) -> str:
    """
    Get database URL from environment or use default.

    Args:
        async_mode: If True, convert URL to async format

    Returns:
        Database URL string
    """
    url = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

    # Convert to async URL if needed
    if async_mode:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("sqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    return url


def create_sync_engine(database_url: Optional[str] = None, echo: bool = False) -> Engine:
    """
    Create a synchronous SQLAlchemy engine.

    Args:
        database_url: Database URL (uses environment or default if None)
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy Engine instance
    """
    if database_url is None:
        database_url = get_database_url(async_mode=False)

    # Configure connection pool based on database type
    if database_url.startswith("sqlite"):
        # SQLite doesn't support multiple connections well
        engine = create_engine(
            database_url,
            echo=echo,
            connect_args={"check_same_thread": False},  # Allow multi-threading
            poolclass=pool.StaticPool,  # Single connection pool for SQLite
        )

        # Enable foreign keys for SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):  # type: ignore
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        # PostgreSQL with connection pooling
        engine = create_engine(
            database_url,
            echo=echo,
            pool_size=5,  # Number of connections to maintain
            max_overflow=10,  # Maximum number of connections to create above pool_size
            pool_pre_ping=True,  # Verify connections before using them
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

    return engine


def create_async_engine_instance(
    database_url: Optional[str] = None, echo: bool = False
) -> AsyncEngine:
    """
    Create an asynchronous SQLAlchemy engine for use with FastAPI.

    Args:
        database_url: Database URL (uses environment or default if None)
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy AsyncEngine instance
    """
    if database_url is None:
        database_url = get_database_url(async_mode=True)

    # Configure connection pool based on database type
    if "sqlite" in database_url:
        # SQLite with async support
        engine = create_async_engine(
            database_url,
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=pool.StaticPool,
        )
    else:
        # PostgreSQL with async support
        engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    return engine


# Global session factory instances
_sync_session_factory: Optional[sessionmaker[Session]] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_sync_session_factory() -> sessionmaker[Session]:
    """
    Get or create the synchronous session factory.

    Returns:
        SQLAlchemy sessionmaker instance
    """
    global _sync_session_factory
    if _sync_session_factory is None:
        engine = create_sync_engine()
        _sync_session_factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _sync_session_factory


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get or create the asynchronous session factory.

    Returns:
        SQLAlchemy async_sessionmaker instance
    """
    global _async_session_factory
    if _async_session_factory is None:
        engine = create_async_engine_instance()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _async_session_factory


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """
    Context manager for synchronous database sessions.

    Yields:
        SQLAlchemy Session instance

    Example:
        with get_sync_session() as session:
            tasks = session.query(Task).all()
    """
    factory = get_sync_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Yields:
        SQLAlchemy AsyncSession instance

    Example:
        async with get_async_session() as session:
            result = await session.execute(select(Task))
            tasks = result.scalars().all()
    """
    factory = get_async_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def reset_session_factories() -> None:
    """
    Reset session factories (useful for testing).

    This closes existing engines and allows new ones to be created
    with different configurations.
    """
    global _sync_session_factory, _async_session_factory

    if _sync_session_factory is not None:
        engine = _sync_session_factory.kw["bind"]
        engine.dispose()
        _sync_session_factory = None

    if _async_session_factory is not None:
        # Async engine disposal needs to be done in an async context
        _async_session_factory = None
