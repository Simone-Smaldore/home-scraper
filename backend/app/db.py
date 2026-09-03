import re
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


class DatabaseNotConfigured(RuntimeError):
    """Raised when DATABASE_URL is missing."""


def normalize_database_url(url: str) -> str:
    """Turn a Neon connection string into a SQLAlchemy + psycopg 3 URL.

    Neon (like most providers) hands out `postgresql://...`, which SQLAlchemy
    resolves to psycopg2. We ship psycopg 3, so the driver has to be explicit.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


# Matches a DSN anywhere inside a longer message, driver suffix included.
_DSN = re.compile(r"postgres(?:ql)?(?:\+\w+)?://\S*", re.IGNORECASE)


def redact_dsn(message: str) -> str:
    """Strip connection strings out of text that is about to be shown.

    /api/health is unauthenticated on purpose — see api/health.py — and a
    SQLAlchemy error message quotes the URL it tried to connect to, password
    included. The host is left alone: without it the detail would stop being
    useful for the one job it has, which is debugging an outage.
    """
    return _DSN.sub("postgresql://[rimosso]", message)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.database_url:
        raise DatabaseNotConfigured("DATABASE_URL non è configurata")

    # NullPool: every serverless invocation is short-lived and Neon's pooled
    # endpoint already runs pgbouncer. Holding a local pool would keep
    # connections open across cold starts and exhaust the free tier.
    return create_engine(
        normalize_database_url(settings.database_url),
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
