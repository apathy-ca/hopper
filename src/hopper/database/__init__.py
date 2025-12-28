"""
Hopper database module.

Provides database connection management, session handling, and initialization utilities.
"""
from .connection import (
    create_async_engine_instance,
    create_sync_engine,
    get_async_session,
    get_async_session_factory,
    get_database_url,
    get_sync_session,
    get_sync_session_factory,
    reset_session_factories,
)
from .init import (
    check_database_health,
    check_database_health_async,
    drop_all_tables,
    get_database_info,
    init_database,
    reset_database,
    run_migrations,
)

__all__ = [
    # Connection management
    "create_sync_engine",
    "create_async_engine_instance",
    "get_database_url",
    "get_sync_session_factory",
    "get_async_session_factory",
    "get_sync_session",
    "get_async_session",
    "reset_session_factories",
    # Database initialization
    "init_database",
    "run_migrations",
    "check_database_health",
    "check_database_health_async",
    "drop_all_tables",
    "reset_database",
    "get_database_info",
]
