"""Writing listings to the database: the one place that knows the upsert.

Sits between the sources (which return `Listing`) and the tables. The runner
calls this and counts; nothing here decides what a listing *means* — the hard
filter has already run, and its verdict travels in alongside the listing.

Lifecycle, in one place:
  - first sight: the row is created, the first price goes in `price_history`;
  - every sight: `last_seen_at` moves, fields refresh, a changed price adds a
    row to `price_history`, `missed_runs` resets, the ad is active again;
  - a **full** run that did not see an active ad bumps `missed_runs`; at
    MISSED_RUNS_BEFORE_INACTIVE the ad is deactivated. Never deleted: it is
    history, and the zone median needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.criteria import Verdict
from app.domain.listing import Listing as ListingData
from app.models import Listing, PriceHistory

# Two full runs — two mornings — without a trace. One could be a hiccup on
# the site's side; two is a sale or a withdrawal.
MISSED_RUNS_BEFORE_INACTIVE = 2


@dataclass(frozen=True)
class UpsertResult:
    created: bool
    price_changed: bool


def known_ids(db: Session, source: str) -> set[str]:
    return set(db.scalars(select(Listing.source_id).where(Listing.source == source)))


def upsert(db: Session, data: ListingData, verdict: Verdict, now: datetime) -> UpsertResult:
    row = db.scalar(
        select(Listing).where(Listing.source == data.source, Listing.source_id == data.source_id)
    )
    created = row is None
    if row is None:
        row = Listing(source=data.source, source_id=data.source_id, first_seen_at=now)
        db.add(row)

    price_changed = not created and row.price_eur != data.price_eur

    row.url = data.url
    row.title = data.title
    row.description = data.description
    row.price_eur = data.price_eur
    row.size_sqm = data.size_sqm
    row.rooms = data.rooms
    row.bathrooms = data.bathrooms
    row.floor = data.floor
    row.floor_raw = data.floor_raw
    row.is_last_floor = data.is_last_floor
    row.elevator = data.elevator
    row.balcony = data.balcony
    row.garage = data.garage
    row.condition = data.condition
    row.energy_class = data.energy_class
    row.heating = data.heating
    row.is_auction = data.is_auction
    row.zone = data.zone
    row.zone_raw = data.zone_raw
    row.address = data.address
    row.lat = data.lat
    row.lng = data.lng
    row.is_private = data.is_private
    row.advertiser_name = data.advertiser_name
    row.phone = data.phone
    row.images = list(data.images)
    row.published_at = data.published_at
    row.last_seen_at = now
    row.missed_runs = 0
    row.is_active = True
    row.passes_hard_filter = verdict.passes
    row.filter_rejections = list(verdict.rejections)
    row.filter_unknowns = list(verdict.unknowns)
    row.raw = data.raw

    if created or price_changed:
        row.prices.append(PriceHistory(price_eur=data.price_eur, seen_at=now))

    return UpsertResult(created=created, price_changed=price_changed)


def mark_missing(db: Session, source: str, seen_ids: set[str]) -> int:
    """After a full run: bump the miss counter of every active ad not seen, and
    deactivate the ones that reached the threshold. Returns how many were
    deactivated."""
    missing = list(
        db.scalars(
            select(Listing).where(
                Listing.source == source,
                Listing.is_active.is_(True),
                Listing.source_id.not_in(seen_ids) if seen_ids else True,
            )
        )
    )
    deactivated = 0
    for row in missing:
        row.missed_runs += 1
        if row.missed_runs >= MISSED_RUNS_BEFORE_INACTIVE:
            row.is_active = False
            deactivated += 1
    return deactivated
