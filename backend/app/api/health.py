from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import DatabaseNotConfigured, get_engine, redact_dsn
from app.schemas.health import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health)
def health(response: Response) -> Health:
    """Walking-skeleton probe: is the app up, and can it reach Postgres?

    Public, like everything else in this API. `detail` is filled in only when
    something is broken and you need it to debug; a healthy system says "ok"
    and nothing else — no Postgres version, no counts.
    """
    settings = get_settings()

    try:
        with get_engine().connect() as connection:
            connection.execute(text("select 1"))
    except DatabaseNotConfigured as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(
            status="degraded",
            environment=settings.environment,
            database="not_configured",
            detail=str(exc),
        )
    except SQLAlchemyError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(
            status="degraded",
            environment=settings.environment,
            database="unreachable",
            # redact_dsn because this page is public: the driver quotes the URL
            # it failed to connect to, password and all.
            detail=redact_dsn(f"{type(exc).__name__}: {exc}"),
        )

    return Health(
        status="ok",
        environment=settings.environment,
        database="ok",
        detail=None,
    )
