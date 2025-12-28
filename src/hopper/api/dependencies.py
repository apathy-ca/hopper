"""
FastAPI dependencies for the Hopper API.

Provides reusable dependencies for:
- Database session management
- Authentication
- Pagination
- Common query parameters
"""

from typing import AsyncGenerator, Optional, Annotated
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import os

from hopper.models.base import Base


# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./hopper.db"  # Default to SQLite for development
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True if os.getenv("SQL_ECHO") == "true" else False,
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.

    Yields:
        AsyncSession: SQLAlchemy async session

    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            # Use db session
            pass
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class PaginationParams:
    """
    Dependency for pagination parameters.

    Attributes:
        skip: Number of items to skip
        limit: Maximum number of items to return
    """

    def __init__(
        self,
        skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
        limit: Annotated[int, Query(ge=1, le=100, description="Number of items to return")] = 20,
    ):
        self.skip = skip
        self.limit = limit


class FilterParams:
    """
    Dependency for common filter parameters.

    Attributes:
        search: Search query string
        sort_by: Field to sort by
        sort_order: Sort order (asc/desc)
    """

    def __init__(
        self,
        search: Annotated[Optional[str], Query(description="Search query")] = None,
        sort_by: Annotated[Optional[str], Query(description="Sort by field")] = None,
        sort_order: Annotated[
            Optional[str],
            Query(regex="^(asc|desc)$", description="Sort order (asc/desc)")
        ] = "desc",
    ):
        self.search = search
        self.sort_by = sort_by
        self.sort_order = sort_order


async def get_current_user(
    # This will be implemented in Task 5 with proper authentication
    # For now, return a placeholder
) -> dict:
    """
    Dependency that provides the current authenticated user.

    This is a placeholder that will be implemented in Task 5.

    Returns:
        dict: Current user information
    """
    # TODO: Implement proper authentication
    return {"id": "development-user", "username": "dev"}


async def get_current_active_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Dependency that provides the current active user.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        dict: Current active user information

    Raises:
        HTTPException: If user is inactive
    """
    # TODO: Check if user is active
    return current_user


async def get_optional_current_user() -> Optional[dict]:
    """
    Dependency that provides the current user if authenticated, None otherwise.

    Useful for endpoints that have optional authentication.

    Returns:
        Optional[dict]: Current user information or None
    """
    # TODO: Implement optional authentication
    return None
