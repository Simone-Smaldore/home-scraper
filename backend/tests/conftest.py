"""Test harness for anything that touches the database.

Runs against SQLite in memory rather than Neon: the suite has to be runnable
offline, in a second, without touching the real database. SQLite also hands
back naive datetimes where Postgres gives tz-aware ones, so anything that
compares the two fails here first.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


@pytest.fixture
def db_factory() -> Iterator[sessionmaker[DbSession]]:
    # StaticPool keeps one connection alive, which is what makes ":memory:"
    # survive across the several sessions a test opens.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless told; Postgres does not. Turning them
    # on here keeps ON DELETE CASCADE honest in both places.
    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def db(db_factory: sessionmaker[DbSession]) -> Iterator[DbSession]:
    session = db_factory()
    try:
        yield session
    finally:
        session.close()
