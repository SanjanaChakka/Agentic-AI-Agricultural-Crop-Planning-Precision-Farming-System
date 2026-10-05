"""Regression tests for the SQLAlchemy DSN that :mod:`app.core.config` produces.

The failure these guard against is real and took down a Render deploy: psycopg 3
is the only PostgreSQL driver installed, so a bare ``postgresql://`` DSN made
SQLAlchemy import psycopg2 and crash at ``create_engine`` during application
import, before the server ever bound a port.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.config import Settings


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        # Render hands out the bare form, which defaults to the psycopg2 dialect.
        ("postgresql://u:p@host:5432/agri", "postgresql+psycopg://u:p@host:5432/agri"),
        # Render's internal URL omits the port.
        ("postgresql://u:p@dpg-abc123/agri", "postgresql+psycopg://u:p@dpg-abc123/agri"),
        # Legacy alias seen in older connection strings.
        ("postgres://u:p@host/agri", "postgresql+psycopg://u:p@host/agri"),
        # Already pinned: must not be double-prefixed.
        ("postgresql+psycopg://u:p@host/agri", "postgresql+psycopg://u:p@host/agri"),
        # SQLite is untouched, and must not be mistaken for Postgres.
        ("sqlite:///C:/tmp/agri.db", "sqlite:///C:/tmp/agri.db"),
    ],
)
def test_sqlalchemy_url_pins_an_installed_driver(dsn: str, expected: str) -> None:
    assert Settings(database_url=dsn).sqlalchemy_url == expected


def test_is_sqlite_still_reads_the_raw_dsn() -> None:
    # _engine_kwargs branches on the raw URL, so it must keep seeing sqlite.
    assert Settings(database_url="sqlite:///agri.db").is_sqlite is True
    assert Settings(database_url="postgresql://u:p@h/agri").is_sqlite is False


def test_psycopg3_dialect_resolves_without_connecting() -> None:
    """create_engine() resolves the DBAPI eagerly, so a missing driver raises here.

    This mirrors the deploy failure: the original crash happened inside
    create_engine, during module import, not at first query.
    """
    engine = create_engine(Settings(database_url="postgresql://u:p@host/agri").sqlalchemy_url)

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
