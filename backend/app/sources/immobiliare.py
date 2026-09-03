"""Immobiliare.it — flats for sale in Turin, through the JSON API behind its search page.

The HTML pages sit behind DataDome and answer 403 to anything that is not a
browser running JavaScript — Chrome impersonation included. The search API
(`api-next/search-list/listings/`) does not: it answers with no cookie at all.
What it needs is a way to say *where*, and the geography ids it wants
(`fkRegione`, `idProvincia`, `idComune`) are undocumented; the **bounding box**
the site's own map uses works instead, and is what we send. The box below is
Turin as the site draws it, which also takes in Nichelino, Moncalieri and
Grugliasco at the edges — those are dropped by `city` in `parse_result`.

The API also filters server-side (`prezzoMassimo`, `superficieMinima`,
`localiMinimo`) and sorts by modification date: 9,600 ads become ~2,700 and
we stop at the first page made entirely of known ids. ⚠️ This means the
database only ever sees ads within budget, size and rooms from this source —
the zone median in domain/pricing.py is a median of *comparable* flats, not of
the whole market. Fine for the job, worth knowing.

Field notes (probed 2026-09-03 on 100 filtered ads):
  - `elevator` is True or absent, never False: absence is "not said".
  - balcony lives in `ga4features` as "balcone" / "terrazzo"; absence is unknown.
  - `ga4Garage` is text: "1 in box privato/box in garage", "1 posto auto".
  - `floor.abbreviation` is "2", "T" (terra), "R" (rialzato), "S" (seminterrato),
    or a list like "S, 2" for split-level homes.
  - agencies carry their phone numbers in clear. No private seller appeared in
    the filtered sample; the rule is "no `agency` → private".
  - `price.value` on a project is the *minimum* of the range, `rooms` is a
    range ("2 - 5+"); we take the max rooms and let the LLM read the rest.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from app.domain.auction import is_auction
from app.domain.criteria import CRITERIA, Criteria
from app.domain.listing import Listing
from app.domain.vocabulary import Condition, Garage, SourceName, Zone
from app.sources.base import PoliteClient

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.immobiliare.it/api-next/search-list/listings/"
PAGE_SIZE = 25

# The box the site's map sends for "Torino".
TORINO_BBOX: dict[str, str] = {
    "minLat": "44.996368",
    "maxLat": "45.150569",
    "minLng": "7.614212",
    "maxLng": "7.737808",
}

# idCategoria=1 residenziale · idContratto=1 vendita · criterio/ordine = newest
# change first. `path` and `paramsCount` are what the site itself sends and
# the endpoint answers 500 without them.
BASE_PARAMS: dict[str, str] = {
    "fkl_search": "1",
    "idCategoria": "1",
    "idContratto": "1",
    "idNazione": "IT",
    "__lang": "it",
    "path": "/vendita-case/torino/",
    "paramsCount": "3",
    "criterio": "dataModifica",
    "ordine": "desc",
}

# Immobiliare's microzones fold onto Subito's fourteen areas. Where a macrozone
# straddles two of ours ("Lingotto, Nizza Millefonti") only the microzone can
# tell, so it is looked up first.
MICROZONES: dict[str, Zone] = {
    "San Paolo": Zone.CENISIA,
    "Cenisia": Zone.CENISIA,
    "Cit Turin": Zone.CIT_TURIN,
    "San Donato": Zone.CIT_TURIN,
    "Campidoglio": Zone.CIT_TURIN,
    "Crocetta": Zone.CROCETTA,
    "San Secondo": Zone.CROCETTA,
    "Santa Rita": Zone.SANTA_RITA,
    "Lingotto": Zone.SANTA_RITA,
    "Mirafiori Nord": Zone.MIRAFIORI,
    "Mirafiori Sud": Zone.MIRAFIORI,
    "Nizza Millefonti": Zone.NIZZA_MILLEFONTI,
    "Cavoretto": Zone.NIZZA_MILLEFONTI,
    "Gran Madre - Crimea": Zone.NIZZA_MILLEFONTI,
    "Parella": Zone.PARELLA,
    "Pozzo Strada": Zone.PARELLA,
    "Aurora": Zone.AURORA,
    "Valdocco": Zone.AURORA,
    "Barriera di Milano": Zone.BARRIERA_MILANO,
    "Rebaudengo": Zone.BARRIERA_MILANO,
    "Falchera": Zone.BARRIERA_MILANO,
    "Regio Parco": Zone.VANCHIGLIA,
    "Vanchiglia": Zone.VANCHIGLIA,
    "Vanchiglietta": Zone.VANCHIGLIA,
    "Madonna di Campagna": Zone.MADONNA_DI_CAMPAGNA,
    "Borgo Vittoria": Zone.MADONNA_DI_CAMPAGNA,
    "Parco Dora": Zone.MADONNA_DI_CAMPAGNA,
    "Lucento": Zone.LUCENTO,
    "Le Vallette": Zone.LUCENTO,
    "San Salvario": Zone.SAN_SALVARIO,
    "San Salvario - Dante": Zone.SAN_SALVARIO,
}

MACROZONES: dict[str, Zone] = {
    "Centro": Zone.CENTRO,
    "Crocetta, San Secondo": Zone.CROCETTA,
    "San Salvario": Zone.SAN_SALVARIO,
    "Borgo San Paolo, Cenisia": Zone.CENISIA,
    "Campidoglio, San Donato, Cit Turin": Zone.CIT_TURIN,
    "Pozzo Strada, Parella": Zone.PARELLA,
    "Regio Parco, Vanchiglia, Vanchiglietta": Zone.VANCHIGLIA,
    "Santa Rita, Mirafiori Nord": Zone.SANTA_RITA,
    "Lingotto, Nizza Millefonti": Zone.SANTA_RITA,
    "Mirafiori Sud": Zone.MIRAFIORI,
    "Aurora, Barriera di Milano, Rebaudengo": Zone.BARRIERA_MILANO,
    "Le Vallette, Lucento, Madonna di Campagna": Zone.LUCENTO,
    "Borgo Vittoria, Parco Dora": Zone.MADONNA_DI_CAMPAGNA,
    "Cavoretto, Gran Madre": Zone.NIZZA_MILLEFONTI,
    "Madonna del Pilone, Sassi": Zone.NIZZA_MILLEFONTI,
}

CONDITIONS: dict[str, Condition] = {
    "Da ristrutturare": Condition.DA_RISTRUTTURARE,
    "Buono / Abitabile": Condition.ABITABILE,
    "Ottimo / Ristrutturato": Condition.RISTRUTTURATO,
    "Nuovo / In costruzione": Condition.RISTRUTTURATO,
}


class ImmobiliareSource:
    name = SourceName.IMMOBILIARE

    def __init__(self, client: PoliteClient, criteria: Criteria = CRITERIA) -> None:
        self._client = client
        self._params = {
            **BASE_PARAMS,
            **TORINO_BBOX,
            "prezzoMassimo": str(criteria.max_price_eur),
            "superficieMinima": str(criteria.min_size_sqm),
            "localiMinimo": str(criteria.min_rooms),
        }

    def fetch(
        self,
        *,
        is_known: Callable[[str], bool] = lambda _id: False,
        max_pages: int | None = None,
    ) -> Iterator[Listing]:
        page = 1
        while True:
            data = self._client.get_json(SEARCH_URL, params={**self._params, "pag": str(page)})
            results = data.get("results") or []
            if not results:
                return

            listings: list[Listing] = []
            for raw in results:
                try:
                    listing = parse_result(raw)
                except (KeyError, ValueError, TypeError) as exc:
                    log.warning(
                        "annuncio Immobiliare %s saltato: %s",
                        (raw.get("realEstate") or {}).get("id"),
                        exc,
                    )
                    continue
                if listing is not None:
                    listings.append(listing)
            yield from listings

            if listings and all(is_known(item.source_id) for item in listings):
                return
            if page >= int(data.get("maxPages") or 0):
                return
            page += 1
            if max_pages is not None and page > max_pages:
                return


def parse_result(raw: dict[str, Any]) -> Listing | None:
    """One search result → Listing, or None when the flat is not in Turin.

    Pure; tested on saved payloads.
    """
    estate = raw["realEstate"]
    properties = estate.get("properties") or []
    prop = next((p for p in properties if p.get("isMain")), properties[0] if properties else {})
    location = prop.get("location") or {}

    if (location.get("city") or "") != "Torino":
        return None

    title = (estate.get("title") or prop.get("caption") or "").strip()
    description = (prop.get("description") or "").strip()
    floor = prop.get("floor") or {}
    floor_value = floor.get("value") or None
    features = {f.lower() for f in prop.get("ga4features") or []}
    advertiser = estate.get("advertiser") or {}
    agency = advertiser.get("agency")
    supervisor = advertiser.get("supervisor") or {}
    phones = (agency or {}).get("phones") or supervisor.get("phones") or []
    price = (estate.get("price") or {}).get("value")
    if price is None:
        price = (prop.get("price") or {}).get("value")

    macrozone = location.get("macrozone") or None
    microzone = location.get("microzone") or None
    zone = MICROZONES.get(microzone or "") or MACROZONES.get(macrozone or "")
    if zone is None and macrozone:
        log.warning("zona Immobiliare sconosciuta: %s / %s", macrozone, microzone)

    return Listing(
        source=SourceName.IMMOBILIARE,
        source_id=str(estate["id"]),
        url=(raw.get("seo") or {}).get("url") or f"https://www.immobiliare.it/annunci/{estate['id']}/",
        title=title,
        description=description,
        price_eur=int(price) if price is not None else None,
        size_sqm=_leading_int(prop.get("surface")),
        rooms=_rooms(prop.get("rooms")),
        bathrooms=_leading_int(prop.get("bathrooms")),
        floor=_floor(floor.get("abbreviation")),
        floor_raw=floor_value,
        is_last_floor=True if floor_value and "ultimo" in floor_value.lower() else None,
        elevator=True if prop.get("elevator") is True else None,
        balcony=True if ("balcone" in features or "terrazzo" in features) else None,
        garage=_garage(prop.get("ga4Garage")),
        condition=CONDITIONS.get(prop.get("ga4Condition") or ""),
        energy_class=None,  # not in the search payload
        heating=prop.get("ga4Heating") or None,
        is_auction=is_auction(title, description),
        zone=zone,
        zone_raw=microzone or macrozone,
        address=location.get("address") or None,
        lat=_float(location.get("latitude")),
        lng=_float(location.get("longitude")),
        is_private=agency is None,
        advertiser_name=((agency or {}).get("displayName") or supervisor.get("displayName") or None),
        phone=", ".join(p["value"] for p in phones if p.get("value")) or None,
        images=_images(prop),
        published_at=None,  # the search payload carries no date
        raw=raw,
    )


def _leading_int(value: Any) -> int | None:
    """"85 m²" → 85, "3" → 3, "5+" → 5."""
    if value is None:
        return None
    digits = ""
    for char in str(value).strip():
        if char.isdigit():
            digits += char
        elif char == "." and digits:
            continue
        else:
            break
    return int(digits) if digits else None


def _rooms(value: Any) -> int | None:
    """"4" → 4, "5+" → 5, "2 - 5+" → 5: a range is a project, take its top."""
    if value is None:
        return None
    numbers = [_leading_int(part) for part in str(value).split("-")]
    numbers = [n for n in numbers if n is not None]
    return max(numbers) if numbers else None


def _floor(abbreviation: Any) -> int | None:
    if not abbreviation:
        return None
    token = str(abbreviation).strip()
    if "," in token:
        return None  # split-level: "S, 2" — the wording stays in floor_raw
    if token.upper() in ("T", "R"):
        return 0
    if token.upper() == "S":
        return -1
    return int(token) if token.isdigit() else None


def _garage(value: Any) -> Garage | None:
    if not value:
        return None
    lowered = str(value).lower()
    if "box" in lowered:
        return Garage.BOX
    if "posto auto" in lowered:
        return Garage.POSTO_AUTO
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _images(prop: dict[str, Any]) -> tuple[str, ...]:
    def best(photo: dict[str, Any] | None) -> str | None:
        urls = (photo or {}).get("urls") or {}
        return urls.get("large") or urls.get("medium") or urls.get("small")

    seen: list[str] = []
    for photo in [prop.get("photo"), *((prop.get("multimedia") or {}).get("photos") or [])]:
        url = best(photo)
        if url and url not in seen:
            seen.append(url)
    return tuple(seen)
