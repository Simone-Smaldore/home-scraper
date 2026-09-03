from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    environment: str
    database: Literal["ok", "unreachable", "not_configured"]
    detail: str | None = None
