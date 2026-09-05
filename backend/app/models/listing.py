"""The listing as stored, plus its price trail.

Enum-valued columns are plain strings holding the vocabulary values: a
Postgres ENUM would turn every added value into a migration for nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Listing(TimestampMixin, Base):
    __tablename__ = "listing"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_listing_source_id"),
        # The dashboard's default view: active, passing, newest first.
        Index("ix_listing_dashboard", "is_active", "passes_hard_filter", "first_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    price_eur: Mapped[int | None] = mapped_column(Integer)
    size_sqm: Mapped[int | None] = mapped_column(Integer)
    rooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[int | None] = mapped_column(Integer)
    floor_raw: Mapped[str | None] = mapped_column(String(120))
    is_last_floor: Mapped[bool | None] = mapped_column(Boolean)
    elevator: Mapped[bool | None] = mapped_column(Boolean)
    balcony: Mapped[bool | None] = mapped_column(Boolean)
    garage: Mapped[str | None] = mapped_column(String(32))
    condition: Mapped[str | None] = mapped_column(String(32))
    energy_class: Mapped[str | None] = mapped_column(String(32))
    heating: Mapped[str | None] = mapped_column(String(64))
    is_auction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    zone: Mapped[str | None] = mapped_column(String(64))
    zone_raw: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)

    is_private: Mapped[bool | None] = mapped_column(Boolean)
    advertiser_name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(120))
    images: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Consecutive *full* runs that did not see this ad. Two in a row means it
    # is gone (sold, withdrawn); it comes back to zero the moment it reappears.
    missed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    passes_hard_filter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filter_rejections: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    filter_unknowns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # The site's payload as received, so a listing can be re-normalized or
    # re-evaluated without scraping it again.
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    prices: Mapped[list[PriceHistory]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="PriceHistory.seen_at",
    )


class PriceHistory(Base):
    """One row per price seen — the first, and every change after it.

    A price drop is the most useful signal in a months-long search, and a
    column overwritten in place would lose it.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listing.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_eur: Mapped[int | None] = mapped_column(Integer)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="prices")
