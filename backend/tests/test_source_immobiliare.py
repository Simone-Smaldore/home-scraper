"""Immobiliare normalization, on payloads saved from the real API on 2026-09-03.

`tests/fixtures/immobiliare_torino_sample.json` holds nine search results
picked for their shape, each tagged with `_fixture`. Nothing here touches the
network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.criteria import Criteria
from app.domain.vocabulary import Condition, Garage, SourceName, Zone
from app.sources.immobiliare import SEARCH_URL, ImmobiliareSource, parse_result

FIXTURE = Path(__file__).parent / "fixtures" / "immobiliare_torino_sample.json"


@pytest.fixture(scope="module")
def results() -> dict[str, dict[str, Any]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {item["_fixture"]: item for item in data["results"]}


def test_agency_ad_is_normalized(results: dict[str, dict[str, Any]]) -> None:
    listing = parse_result(results["agency_full"])
    assert listing is not None

    assert listing.source is SourceName.IMMOBILIARE
    assert listing.source_id == "131601550"
    assert listing.url == "https://www.immobiliare.it/annunci/131601550/"
    assert listing.title.startswith("Quadrilocale corso Taranto")
    assert listing.price_eur == 149_000
    assert listing.size_sqm == 100
    assert listing.rooms == 4
    assert listing.bathrooms == 1
    assert listing.floor == 2
    assert listing.floor_raw == "2°, con ascensore"
    assert listing.elevator is True
    assert listing.balcony is True
    assert listing.condition is Condition.RISTRUTTURATO
    assert listing.heating == "Centralizzato"
    assert listing.zone is Zone.VANCHIGLIA
    assert listing.zone_raw == "Regio Parco"
    assert listing.is_private is False
    assert listing.advertiser_name
    assert listing.phone == "011 1852 4180"
    assert listing.lat and listing.lng
    assert len(listing.images) >= 1
    assert all(url.startswith("https://") and "im-cdn.it" in url for url in listing.images)
    assert listing.published_at is None
    assert listing.raw is results["agency_full"]


def test_absent_fields_are_unknown_not_no(results: dict[str, dict[str, Any]]) -> None:
    listing = parse_result(results["unknown_elevator"])
    assert listing is not None
    assert listing.elevator is None
    assert listing.garage is None
    assert listing.zone is Zone.AURORA


def test_ground_floor_is_zero(results: dict[str, dict[str, Any]]) -> None:
    listing = parse_result(results["ground_floor"])
    assert listing is not None
    assert listing.floor == 0
    assert listing.floor_raw == "Piano terra, con ascensore"


def test_split_level_keeps_wording_and_no_number(results: dict[str, dict[str, Any]]) -> None:
    listing = parse_result(results["multi_floor"])
    assert listing is not None
    assert listing.floor is None
    assert listing.floor_raw and "Interrato" in listing.floor_raw
    assert listing.zone is Zone.SANTA_RITA
    assert listing.zone_raw == "Santa Rita"


def test_box_and_terrace(results: dict[str, dict[str, Any]]) -> None:
    listing = parse_result(results["box"])
    assert listing is not None
    assert listing.garage is Garage.BOX
    assert listing.balcony is True
    assert listing.price_eur == 249_000


def test_outside_turin_is_dropped(results: dict[str, dict[str, Any]]) -> None:
    assert parse_result(results["other_city"]) is None
    assert parse_result(results["project"]) is None  # a Moncalieri development


def test_target_zone_maps_through_microzone(results: dict[str, dict[str, Any]]) -> None:
    listing = parse_result(results["target_cenisia"])
    assert listing is not None
    assert listing.zone is Zone.CENISIA
    assert listing.zone_raw == "Cenisia"


def test_auction_is_flagged_not_dropped(results: dict[str, dict[str, Any]]) -> None:
    listing = parse_result(results["asta"])
    assert listing is not None
    assert listing.is_auction is True
    assert listing.title.startswith("Appartamento all'asta")
    assert listing.price_eur == 84_375


def test_project_rooms_take_the_top_of_the_range() -> None:
    raw = _result("1", rooms="2 - 5+", city="Torino")
    listing = parse_result(raw)
    assert listing is not None
    assert listing.rooms == 5


# --- paging -----------------------------------------------------------------


def _result(ad_id: str, *, rooms: str = "3", city: str = "Torino") -> dict[str, Any]:
    return {
        "realEstate": {
            "id": int(ad_id),
            "title": f"Trilocale {ad_id}",
            "price": {"value": 100_000},
            "properties": [
                {"isMain": True, "rooms": rooms, "surface": "90 m²", "location": {"city": city}}
            ],
        },
        "seo": None,
    }


class FakeClient:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        assert url == SEARCH_URL
        self.calls.append(dict(params or {}))
        return self.pages[len(self.calls) - 1]


def _page(items: list[dict[str, Any]], max_pages: int) -> dict[str, Any]:
    return {"results": items, "maxPages": max_pages}


def test_criteria_become_server_side_filters() -> None:
    client = FakeClient([_page([_result("1")], 1)])
    source = ImmobiliareSource(client, Criteria(max_price_eur=200_000, min_size_sqm=70, min_rooms=2))  # type: ignore[arg-type]
    list(source.fetch())
    sent = client.calls[0]
    assert sent["prezzoMassimo"] == "200000"
    assert sent["superficieMinima"] == "70"
    assert sent["localiMinimo"] == "2"
    assert sent["pag"] == "1"
    assert sent["minLat"] and sent["maxLng"]


def test_walks_to_max_pages() -> None:
    client = FakeClient([_page([_result("1")], 2), _page([_result("2")], 2)])
    got = list(ImmobiliareSource(client).fetch())  # type: ignore[arg-type]
    assert [item.source_id for item in got] == ["1", "2"]
    assert [call["pag"] for call in client.calls] == ["1", "2"]


def test_stops_after_a_page_of_known_ids() -> None:
    client = FakeClient([_page([_result("9"), _result("1")], 9), _page([_result("2")], 9)])
    known = {"1", "2"}
    got = list(ImmobiliareSource(client).fetch(is_known=lambda i: i in known))  # type: ignore[arg-type]
    assert [item.source_id for item in got] == ["9", "1", "2"]
    assert len(client.calls) == 2


def test_a_page_of_other_towns_does_not_end_the_walk() -> None:
    client = FakeClient([_page([_result("1", city="Moncalieri")], 2), _page([_result("2")], 2)])
    got = list(ImmobiliareSource(client).fetch(is_known=lambda _i: True))  # type: ignore[arg-type]
    assert [item.source_id for item in got] == ["2"]


def test_max_pages_caps_the_walk() -> None:
    client = FakeClient([_page([_result("1")], 50), _page([_result("2")], 50)])
    got = list(ImmobiliareSource(client).fetch(max_pages=1))  # type: ignore[arg-type]
    assert [item.source_id for item in got] == ["1"]
