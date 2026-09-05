"""The upsert and the lifecycle, on SQLite in memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.criteria import Verdict, check
from app.domain.listing import Listing as ListingData
from app.domain.vocabulary import ReviewStatus, SourceName, Zone
from app.models import Listing, PriceHistory, Review
from app.store.listings import (
    MISSED_RUNS_BEFORE_INACTIVE,
    fetch_existing,
    known_ids,
    mark_missing,
    upsert,
)

T0 = datetime(2026, 9, 3, 7, 30, tzinfo=timezone.utc)


def make(source_id: str = "1", **overrides: Any) -> ListingData:
    base: dict[str, Any] = dict(
        source=SourceName.SUBITO,
        source_id=source_id,
        url=f"https://example.test/{source_id}",
        title="Quadrilocale",
        description="",
        price_eur=200_000,
        size_sqm=95,
        rooms=4,
        elevator=True,
        balcony=True,
        zone=Zone.CENISIA,
        images=("https://img.test/a.jpg",),
        raw={"urn": source_id},
    )
    base.update(overrides)
    return ListingData(**base)


def store(db: Session, data: ListingData, at: datetime = T0):
    result = upsert(db, data, check(data), at)
    db.commit()
    return result


def test_first_sight_creates_row_and_first_price(db: Session) -> None:
    result = store(db, make())
    assert result.created and not result.price_changed

    row = db.scalar(select(Listing))
    assert row is not None
    assert row.source == "subito" and row.source_id == "1"
    assert row.price_eur == 200_000
    assert row.zone == "Cenisia / San Paolo"
    assert row.images == ["https://img.test/a.jpg"]
    assert row.passes_hard_filter is True
    assert row.filter_rejections == [] and row.filter_unknowns == []
    assert row.is_active and row.missed_runs == 0
    assert row.raw == {"urn": "1"}
    assert [p.price_eur for p in row.prices] == [200_000]


def test_second_sight_updates_without_a_new_price_row(db: Session) -> None:
    store(db, make())
    later = T0 + timedelta(hours=12)
    result = store(db, make(title="Quadrilocale luminoso"), later)
    assert not result.created and not result.price_changed

    row = db.scalar(select(Listing))
    assert row is not None
    assert row.title == "Quadrilocale luminoso"
    assert row.last_seen_at.replace(tzinfo=timezone.utc) == later
    assert row.first_seen_at.replace(tzinfo=timezone.utc) == T0
    assert db.scalar(select(PriceHistory).where(PriceHistory.listing_id == row.id).limit(1))
    assert len(list(db.scalars(select(PriceHistory)))) == 1


def test_price_change_adds_a_history_row(db: Session) -> None:
    store(db, make())
    result = store(db, make(price_eur=185_000), T0 + timedelta(days=1))
    assert result.price_changed

    row = db.scalar(select(Listing))
    assert row is not None
    assert row.price_eur == 185_000
    assert [p.price_eur for p in row.prices] == [200_000, 185_000]


def test_verdict_is_stored_and_refreshed(db: Session) -> None:
    store(db, make(elevator=None))
    row = db.scalar(select(Listing))
    assert row is not None
    assert row.passes_hard_filter and row.filter_unknowns == ["ascensore non indicato"]

    store(db, make(price_eur=300_000))
    db.refresh(row)
    assert row.passes_hard_filter is False
    assert row.filter_rejections == ["prezzo 300.000 € sopra i 250.000 €"]


def test_known_ids_is_per_source(db: Session) -> None:
    store(db, make("a"))
    store(db, make("b", source=SourceName.IMMOBILIARE))
    assert known_ids(db, "subito") == {"a"}
    assert known_ids(db, "immobiliare") == {"b"}


def test_missing_twice_deactivates_and_reappearing_revives(db: Session) -> None:
    store(db, make("gone"))
    store(db, make("stays"))

    assert mark_missing(db, "subito", {"stays"}) == 0
    db.commit()
    gone = db.scalar(select(Listing).where(Listing.source_id == "gone"))
    assert gone is not None and gone.is_active and gone.missed_runs == 1

    assert MISSED_RUNS_BEFORE_INACTIVE == 2
    assert mark_missing(db, "subito", {"stays"}) == 1
    db.commit()
    db.refresh(gone)
    assert gone.is_active is False

    # Already inactive: not counted again.
    assert mark_missing(db, "subito", {"stays"}) == 0

    store(db, make("gone"), T0 + timedelta(days=3))
    db.refresh(gone)
    assert gone.is_active and gone.missed_runs == 0

    stays = db.scalar(select(Listing).where(Listing.source_id == "stays"))
    assert stays is not None and stays.missed_runs == 0


def test_mark_missing_only_touches_its_own_source(db: Session) -> None:
    store(db, make("x", source=SourceName.IMMOBILIARE))
    assert mark_missing(db, "subito", set()) == 0
    row = db.scalar(select(Listing))
    assert row is not None and row.missed_runs == 0


def test_rescrape_never_touches_the_review(db: Session) -> None:
    store(db, make())
    row = db.scalar(select(Listing))
    assert row is not None
    db.add(Review(listing_id=row.id, status=ReviewStatus.INTERESSANTE, note="da vedere"))
    db.commit()

    store(db, make(price_eur=190_000), T0 + timedelta(days=1))
    review = db.scalar(select(Review))
    assert review is not None
    assert review.status == "interessante" and review.note == "da vedere"


def test_batched_upsert_with_prefetched_rows(db: Session) -> None:
    store(db, make("a"))
    store(db, make("b", price_eur=150_000))

    batch = [make("a", price_eur=210_000), make("b", price_eur=150_000), make("c")]
    existing = fetch_existing(db, "subito", {item.source_id for item in batch})
    assert set(existing) == {"a", "b"}

    later = T0 + timedelta(days=1)
    results = [upsert(db, item, check(item), later, existing) for item in batch]
    db.commit()

    assert [r.created for r in results] == [False, False, True]
    assert [r.price_changed for r in results] == [True, False, False]
    assert len(list(db.scalars(select(Listing)))) == 3
    assert fetch_existing(db, "subito", set()) == {}


def test_verdict_object_round_trips_as_lists(db: Session) -> None:
    data = make(zone=Zone.MIRAFIORI, balcony=None)
    upsert(db, data, Verdict(rejections=("fuori zona: Mirafiori",), unknowns=("balcone non indicato",)), T0)
    db.commit()
    row = db.scalar(select(Listing))
    assert row is not None
    assert row.filter_rejections == ["fuori zona: Mirafiori"]
    assert row.filter_unknowns == ["balcone non indicato"]
