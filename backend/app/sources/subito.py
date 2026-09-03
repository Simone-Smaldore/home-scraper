"""Subito.it — flats for sale in Turin, through the JSON API its own site uses.

`hades.subito.it/v1/search/items` is open: no cookie, no token, no DataDome.
One request returns up to 100 ads with every structured field the listing page
shows (price, size, rooms, floor, lift, balcony, energy class, condition,
heating, parking), the full description, the photos and the advertiser. There
is no reason to fetch a detail page, so we never do.

Geography, as probed on 2026-09-03: region 2 = Piemonte, city 6 = provincia di
Torino, town 001272 = Torino, whose zones are the fourteen `001272-N` keys
below. Roughly one ad in five has no zone at all; those keep `zone=None` and
go through with a "zona non indicata" warning rather than being dropped.

⚠️ `advertiser.company` is the private-vs-agency signal, not `/nosalesman`.
The latter is the "no agencies, please" checkbox, and a third of the agencies
tick it too.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

from app.domain.auction import is_auction
from app.domain.listing import Listing
from app.domain.vocabulary import Condition, Garage, SourceName, Zone
from app.sources.base import PoliteClient

log = logging.getLogger(__name__)

SEARCH_URL = "https://hades.subito.it/v1/search/items"

# c=7 appartamenti · t=s in vendita · r/ci/to = Piemonte / Torino / Torino
BASE_PARAMS: dict[str, str] = {
    "c": "7",
    "t": "s",
    "r": "2",
    "ci": "6",
    "to": "001272",
    "sort": "datedesc",
}
PAGE_SIZE = 100

ZONES: dict[str, Zone] = {
    "001272-1": Zone.CENTRO,
    "001272-2": Zone.CROCETTA,
    "001272-3": Zone.SAN_SALVARIO,
    "001272-4": Zone.NIZZA_MILLEFONTI,
    "001272-5": Zone.SANTA_RITA,
    "001272-6": Zone.CENISIA,
    "001272-7": Zone.CIT_TURIN,
    "001272-8": Zone.AURORA,
    "001272-9": Zone.VANCHIGLIA,
    "001272-10": Zone.BARRIERA_MILANO,
    "001272-11": Zone.MADONNA_DI_CAMPAGNA,
    "001272-12": Zone.LUCENTO,
    "001272-13": Zone.PARELLA,
    "001272-14": Zone.MIRAFIORI,
}

CONDITIONS: dict[str, Condition] = {
    "Da ristrutturare": Condition.DA_RISTRUTTURARE,
    "Buono - abitabile": Condition.ABITABILE,
    "Ottimo - ristrutturato": Condition.RISTRUTTURATO,
    "Nuovo - in costruzione": Condition.RISTRUTTURATO,
}


class SubitoSource:
    name = SourceName.SUBITO

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    def fetch(
        self,
        *,
        is_known: Callable[[str], bool] = lambda _id: False,
        max_pages: int | None = None,
    ) -> Iterator[Listing]:
        start = 0
        pages = 0
        while True:
            data = self._client.get_json(
                SEARCH_URL, params={**BASE_PARAMS, "lim": PAGE_SIZE, "start": start}
            )
            ads = data.get("ads") or []
            if not ads:
                return

            listings: list[Listing] = []
            for raw in ads:
                try:
                    listings.append(parse_ad(raw))
                except (KeyError, ValueError, TypeError) as exc:
                    # One malformed ad must not end the daily run, but it must
                    # not vanish quietly either.
                    log.warning("annuncio Subito %s saltato: %s", raw.get("urn"), exc)
            yield from listings

            pages += 1
            # Sorted newest first: a page made entirely of ids we already have
            # means everything after it is older still.
            if listings and all(is_known(item.source_id) for item in listings):
                return
            start += len(ads)
            if start >= int(data.get("count_all") or 0):
                return
            if max_pages is not None and pages >= max_pages:
                return


def parse_ad(raw: dict[str, Any]) -> Listing:
    """One ad from the search response → Listing. Pure; tested on saved payloads."""
    geo = raw.get("geo") or {}
    zone_key = (geo.get("zone") or {}).get("key")
    zone_raw = (geo.get("zone") or {}).get("value")
    if zone_key and zone_key not in ZONES:
        log.warning("zona Subito sconosciuta %s (%s)", zone_key, zone_raw)
    map_ = geo.get("map") or {}
    advertiser = raw.get("advertiser") or {}
    company = advertiser.get("company")

    floor_raw = _feature(raw, "/floor")
    title = (raw.get("subject") or "").strip()
    description = (raw.get("body") or "").strip()
    return Listing(
        source=SourceName.SUBITO,
        source_id=_ad_id(raw["urn"]),
        url=(raw.get("urls") or {}).get("default") or "",
        title=title,
        description=description,
        is_auction=is_auction(title, description),
        price_eur=_leading_int(_feature(raw, "/price")),
        size_sqm=_leading_int(_feature(raw, "/size")),
        rooms=_leading_int(_feature(raw, "/room")),
        bathrooms=_leading_int(_feature(raw, "/bathrooms")),
        floor=_floor(floor_raw),
        floor_raw=floor_raw,
        is_last_floor=_yes_no(_feature(raw, "/last_floor")),
        elevator=_yes_no(_feature(raw, "/elevator")),
        balcony=_yes_no(_feature(raw, "/balcony")),
        garage=_garage(_feature(raw, "/parking")),
        condition=CONDITIONS.get(_feature(raw, "/building_condition") or ""),
        energy_class=_feature(raw, "/energy_class"),
        heating=_feature(raw, "/heating"),
        zone=ZONES.get(zone_key) if zone_key else None,
        zone_raw=zone_raw,
        address=map_.get("address") or None,
        lat=_float(map_.get("latitude")),
        lng=_float(map_.get("longitude")),
        is_private=(not company) if isinstance(company, bool) else None,
        advertiser_name=(advertiser.get("name") or "").strip() or None,
        phone=_phone(advertiser.get("phone")),
        images=tuple(
            img["cdn_base_url"] for img in raw.get("images") or [] if img.get("cdn_base_url")
        ),
        published_at=_published(raw.get("dates") or {}),
        raw=raw,
    )


def _ad_id(urn: str) -> str:
    # "id:ad:612258928:list:659200649" → "612258928". The ad id is the stable
    # one; the list id changes when an ad is renewed. Ad ids can also be UUIDs.
    parts = urn.split(":")
    if len(parts) < 3 or parts[1] != "ad":
        raise ValueError(f"urn inatteso: {urn}")
    return parts[2]


def _feature(raw: dict[str, Any], uri: str) -> str | None:
    for feature in raw.get("features") or []:
        if feature.get("uri") == uri:
            values = feature.get("values") or []
            return values[0].get("value") if values else None
    return None


def _leading_int(value: str | None) -> int | None:
    """"250.000 €" → 250000, "70 mq" → 70, "5+" → 5. Nothing numeric → None."""
    if not value:
        return None
    digits = ""
    for char in value.strip():
        if char.isdigit():
            digits += char
        elif char == "." and digits:
            continue  # thousands separator
        else:
            break
    return int(digits) if digits else None


def _yes_no(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in ("sì", "si", "yes"):
        return True
    if lowered == "no":
        return False
    return None


def _floor(value: str | None) -> int | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in ("rialzato", "terra", "t", "piano terra", "0"):
        return 0
    if lowered.isdigit():
        return int(lowered)
    return None  # "Oltre il 7°", "Interrato", …: kept verbatim in floor_raw


def _garage(value: str | None) -> Garage | None:
    if value is None:
        return None
    lowered = value.lower()
    if "box" in lowered:
        return Garage.BOX
    if "posto auto" in lowered:
        return Garage.POSTO_AUTO
    return Garage.NONE  # "Posto bici" is not where a car goes


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _phone(value: Any) -> str | None:
    # Subito masks numbers in the list API: "0" or absent means "ask the app".
    if not value or str(value).strip() in ("0", "None"):
        return None
    return str(value).strip()


def _published(dates: dict[str, Any]) -> datetime | None:
    # Seen both "2026-09-02T03:29:37.255+0200" and, on older ads,
    # "2026-08-30T03:23:31+0200" — fromisoformat takes either since 3.11.
    value = dates.get("display_iso8601")
    if not value:
        return None
    return datetime.fromisoformat(value)
