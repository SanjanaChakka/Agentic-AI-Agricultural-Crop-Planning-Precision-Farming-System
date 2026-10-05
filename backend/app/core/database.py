"""SQLAlchemy engine / session wiring.

Supports PostgreSQL (production) and SQLite (zero-config local development and
tests) through the same declarative models.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def _engine_kwargs(database_url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"echo": settings.sql_echo, "future": True}
    if database_url.startswith("sqlite"):
        # FastAPI serves requests from a thread pool, so the connection must
        # not be pinned to the creating thread.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return kwargs


engine: Engine = create_engine(settings.sqlalchemy_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for background/startup work."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables for a fresh database.

    Alembic migrations are the source of truth for deployments; this helper
    keeps local development and tests friction free.
    """
    from app import models  # noqa: F401  (ensures every mapper is registered)

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ensured (%s)", "sqlite" if settings.is_sqlite else "server")


def check_db_connection() -> bool:
    """Return ``True`` when a trivial round-trip to the database succeeds."""
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - the health probe must never raise
        logger.warning("Database connectivity check failed: %s", exc)
        return False
