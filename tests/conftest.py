"""
Pytest configuration and shared fixtures.
"""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hopper.models import Base


@pytest.fixture(scope="session")
def engine() -> Generator:
    """Create a test database engine."""
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Create a new database session for a test."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(scope="function")
def clean_db(db_session: Session) -> Generator[Session, None, None]:
    """Provide a clean database session with all tables cleared."""
    # Clear all tables before test
    for table in reversed(Base.metadata.sorted_tables):
        db_session.execute(table.delete())
    db_session.commit()

    yield db_session

    # Clean up after test
    for table in reversed(Base.metadata.sorted_tables):
        db_session.execute(table.delete())
    db_session.commit()
