"""
SQLite storage backend for Hopper.

Wraps a SQLAlchemy engine backed by a single SQLite file.  On initialize()
it runs Alembic migrations in-process so the schema is always current.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .base import StorageBackend, StorageConfig

logger = logging.getLogger(__name__)


class SQLiteStorage(StorageBackend):
    """SQLite-backed storage using SQLAlchemy + Alembic."""

    def __init__(self, config: StorageConfig, db_path: Path | None = None):
        """Create the backend.

        Args:
            config: StorageConfig (mode must be 'local' or 'embedded').
            db_path: Explicit path to the .db file.  Defaults to
                     ``<config.path>/hopper.db``.
        """
        self._config = config
        if db_path is not None:
            self.db_path = db_path
        elif config.path is not None:
            self.db_path = config.path / "hopper.db"
        else:
            raise ValueError("SQLiteStorage requires config.path or explicit db_path")

        self._url = f"sqlite:///{self.db_path}"
        self._engine = create_engine(
            self._url,
            connect_args={"check_same_thread": False},
            # WAL mode is set in initialize() for better concurrency
        )
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Run Alembic migrations and set SQLite pragmas."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_migrations()
        self._set_pragmas()
        logger.debug("SQLiteStorage initialized at %s", self.db_path)

    def get_config(self) -> StorageConfig:
        return self._config

    @property
    def is_local(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Session factory
    # ------------------------------------------------------------------

    def session(self) -> Session:
        """Return a new SQLAlchemy Session (caller must close/commit)."""
        return self._Session()

    def dispose(self) -> None:
        """Dispose the engine connection pool (call on shutdown)."""
        self._engine.dispose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_migrations(self) -> None:
        """Run any pending Alembic migrations in-process."""
        try:
            import os
            import alembic.config
            import alembic.command
            from pathlib import Path as _Path

            # Locate alembic.ini relative to this package
            # src/hopper/storage/sqlite.py -> project root is 4 levels up
            here = _Path(__file__).resolve()
            project_root = here.parent.parent.parent.parent  # .../hopper/
            alembic_ini = project_root / "alembic.ini"

            if not alembic_ini.exists():
                logger.warning(
                    "alembic.ini not found at %s — skipping migration", alembic_ini
                )
                return

            # env.py reads DATABASE_URL from the environment; set it so our
            # URL wins even when alembic.ini has a default.
            prev_db_url = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = self._url
            try:
                alembic_cfg = alembic.config.Config(str(alembic_ini))
                alembic_cfg.set_main_option("sqlalchemy.url", self._url)
                alembic_cfg.set_main_option(
                    "script_location", str(project_root / "alembic")
                )
                alembic.command.upgrade(alembic_cfg, "head")
            finally:
                if prev_db_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = prev_db_url
        except Exception:
            logger.exception("Alembic migration failed — proceeding anyway")

    def _set_pragmas(self) -> None:
        """Apply recommended SQLite pragmas for reliability and concurrency."""
        pragmas = [
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA foreign_keys=ON",
            "PRAGMA busy_timeout=5000",
        ]
        with self._engine.connect() as conn:
            for p in pragmas:
                conn.execute(text(p))
            conn.commit()
