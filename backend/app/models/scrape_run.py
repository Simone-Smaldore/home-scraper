"""One row per source per run: what happened, in numbers.

The dashboard reads the latest one per source to say "aggiornata alle 07:31 ·
Immobiliare bloccato". `doctor` reads the last few to notice a source that has
been failing for days.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScrapeRun(Base):
    __tablename__ = "scrape_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ok | blocked | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    # A full run walks every page and is the only kind allowed to declare an
    # ad gone; an incremental one stops at the first page of known ids.
    full: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deactivated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_used: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
