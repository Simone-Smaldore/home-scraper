"""The normalized listing, common to every source.

Sources fetch whatever shape their site returns and hand back one of these.
Everything downstream — the hard filter, the LLM prompt, the database row —
reads this and never the raw payload, which is kept only so a listing can be
re-normalized later without scraping it again.

Field conventions:
  - `None` means "the site did not say", never "no". The distinction is
    load-bearing for the hard filter: listings are filled in carelessly and a
    missing "ascensore" is the norm, not a refusal.
  - Prices are whole euros. Listings have no cents.
  - `floor` is 0 for ground and raised-ground floors; the site's own wording
    stays in `floor_raw` because "rialzato" and "terra" are different things to
    a buyer even if they are the same number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.vocabulary import Condition, Garage, SourceName, Zone


@dataclass(frozen=True)
class Listing:
    source: SourceName
    source_id: str
    url: str
    title: str
    description: str

    price_eur: int | None = None
    size_sqm: int | None = None
    rooms: int | None = None
    bathrooms: int | None = None
    floor: int | None = None
    floor_raw: str | None = None
    is_last_floor: bool | None = None
    elevator: bool | None = None
    balcony: bool | None = None
    garage: Garage | None = None
    condition: Condition | None = None
    energy_class: str | None = None
    heating: str | None = None

    # Auctions are flagged, never dropped: a judicial sale can be a bargain or a
    # trap, and that is a judgement for you, not for the filter.
    is_auction: bool = False

    zone: Zone | None = None
    zone_raw: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None

    is_private: bool | None = None
    advertiser_name: str | None = None
    phone: str | None = None

    images: tuple[str, ...] = ()
    published_at: datetime | None = None

    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def price_per_sqm(self) -> int | None:
        """Whole euros per square metre, or None when either side is missing."""
        if self.price_eur is None or not self.size_sqm:
            return None
        return round(self.price_eur / self.size_sqm)
