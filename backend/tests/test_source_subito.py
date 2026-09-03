"""Subito normalization, on payloads saved from the real API on 2026-09-03.

`tests/fixtures/subito_torino_sample.json` holds nine ads picked for their
shape (a private seller, a raised-ground floor, a box, no zone, …), each tagged
with `_fixture`. Nothing here touches the network.
"""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path
from typing import Any

import pytest

from app.domain.vocabulary import Condition, Garage, SourceName, Zone
from app.sources.base import Blocked, PoliteClient, SourceError
from app.sources.subito import SEARCH_URL, SubitoSource, parse_ad

FIXTURE = Path(__file__).parent / "fixtures" / "subito_torino_sample.json"


@pytest.fixture(scope="module")
def ads() -> dict[str, dict[str, Any]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {ad["_fixture"]: ad for ad in data["ads"]}


def test_full_ad_is_normalized(ads: dict[str, dict[str, Any]]) -> None:
    listing = parse_ad(ads["target_full"])

    assert listing.source is SourceName.SUBITO
    assert listing.source_id == "612258928"
    assert listing.url.startswith("https://www.subito.it/appartamenti/")
    assert listing.price_eur == 155_000
    assert listing.size_sqm == 75
    assert listing.rooms == 3
    assert listing.bathrooms == 1
    assert listing.elevator is True
    assert listing.balcony is True
    assert listing.condition is Condition.ABITABILE
    assert listing.zone is Zone.CENISIA
    assert listing.zone_raw == "Cenisia/San Paolo"
    assert listing.is_private is False
    assert len(listing.images) == 2
    assert all(url.startswith("https://images.sbito.it/") for url in listing.images)
    assert listing.published_at is not None
    assert listing.published_at.tzinfo is not None
    assert listing.published_at.astimezone(timezone.utc).year == 2026
    assert listing.price_per_sqm == round(155_000 / 75)
    assert listing.raw is ads["target_full"]


def test_missing_features_are_none_not_false(ads: dict[str, dict[str, Any]]) -> None:
    listing = parse_ad(ads["cit_turin"])
    assert listing.zone is Zone.CIT_TURIN
    assert listing.elevator is None
    assert listing.balcony is None
    assert listing.garage is None
    assert listing.condition is None
    assert listing.floor == 3
    assert listing.floor_raw == "3"


def test_explicit_no_is_false(ads: dict[str, dict[str, Any]]) -> None:
    listing = parse_ad(ads["no_elevator"])
    assert listing.elevator is False
    assert listing.balcony is False
    assert listing.floor == 0
    assert listing.is_private is True
    assert listing.images == ()


def test_private_seller_comes_from_company_flag(ads: dict[str, dict[str, Any]]) -> None:
    assert parse_ad(ads["private"]).is_private is True
    assert parse_ad(ads["box"]).is_private is False


def test_uuid_ad_id_and_missing_zone(ads: dict[str, dict[str, Any]]) -> None:
    listing = parse_ad(ads["no_zone"])
    assert listing.source_id == "2301058b-40e0-45f3-bd67-0e7be5969a3c"
    assert listing.zone is None
    assert listing.zone_raw is None


def test_raised_ground_floor_is_zero_with_wording_kept(ads: dict[str, dict[str, Any]]) -> None:
    listing = parse_ad(ads["rialzato"])
    assert listing.floor == 0
    assert listing.floor_raw == "Rialzato"
    assert listing.garage is Garage.NONE  # "Posto bici"
    assert listing.price_eur == 900  # a rent in the sale category: the filter's job


def test_box_and_condition(ads: dict[str, dict[str, Any]]) -> None:
    listing = parse_ad(ads["box"])
    assert listing.garage is Garage.BOX
    assert listing.condition is Condition.DA_RISTRUTTURARE
    assert listing.floor == 7
    assert listing.price_eur == 285_000
    assert listing.size_sqm == 135
    assert listing.rooms == 5


@pytest.mark.parametrize(
    "value", ["2026-09-02T03:29:37.255+0200", "2026-08-30T03:23:31+0200"]
)
def test_published_at_accepts_both_date_shapes(value: str) -> None:
    ad = {**_ad("1"), "dates": {"display_iso8601": value}}
    published = parse_ad(ad).published_at
    assert published is not None
    assert published.utcoffset() is not None
    assert published.year == 2026


def test_phone_is_masked_by_the_site(ads: dict[str, dict[str, Any]]) -> None:
    for ad in ads.values():
        assert parse_ad(ad).phone is None


# --- paging and manners -----------------------------------------------------


def _page(ads_: list[dict[str, Any]], count_all: int) -> dict[str, Any]:
    return {"count_all": count_all, "ads": ads_}


def _ad(ad_id: str) -> dict[str, Any]:
    return {"urn": f"id:ad:{ad_id}:list:1", "subject": ad_id, "features": [], "geo": {}}


class FakeClient:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        assert url == SEARCH_URL
        self.calls.append(dict(params or {}))
        return self.pages[len(self.calls) - 1]


def test_walks_every_page_when_nothing_is_known() -> None:
    client = FakeClient([_page([_ad("1"), _ad("2")], 3), _page([_ad("3")], 3)])
    got = list(SubitoSource(client).fetch())  # type: ignore[arg-type]
    assert [item.source_id for item in got] == ["1", "2", "3"]
    assert [call["start"] for call in client.calls] == [0, 2]


def test_stops_after_a_page_of_known_ids() -> None:
    client = FakeClient([_page([_ad("9"), _ad("1")], 300), _page([_ad("2"), _ad("3")], 300)])
    known = {"1", "2", "3"}
    got = list(SubitoSource(client).fetch(is_known=lambda i: i in known))  # type: ignore[arg-type]
    # First page has a new ad, so the second is read; that one is all known.
    assert [item.source_id for item in got] == ["9", "1", "2", "3"]
    assert len(client.calls) == 2


def test_max_pages_caps_the_walk() -> None:
    client = FakeClient([_page([_ad("1")], 500), _page([_ad("2")], 500)])
    got = list(SubitoSource(client).fetch(max_pages=1))  # type: ignore[arg-type]
    assert [item.source_id for item in got] == ["1"]


def test_a_malformed_ad_is_skipped_not_fatal(caplog: pytest.LogCaptureFixture) -> None:
    client = FakeClient([_page([{"urn": "garbage"}, _ad("1")], 2)])
    got = list(SubitoSource(client).fetch())  # type: ignore[arg-type]
    assert [item.source_id for item in got] == ["1"]
    assert "saltato" in caplog.text


class FakeSession:
    """Answers every GET with the same canned response; counts the hits."""

    def __init__(self, status_code: int, body: str = "{}") -> None:
        self.status_code = status_code
        self.body = body
        self.hits = 0

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        self.hits += 1
        return _Response(self.status_code, self.body)

    def close(self) -> None:
        pass


class _Response:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        return json.loads(self.text)


def test_a_block_is_raised_not_retried() -> None:
    session = FakeSession(403, "<HTML>Access Denied</HTML>")
    with pytest.raises(Blocked):
        PoliteClient(sleep=lambda _s: None, session=session).get_json("https://example.test/x")
    assert session.hits == 1


def test_other_http_errors_are_source_errors() -> None:
    session = FakeSession(500, '{"error": "Internal Server Error"}')
    with pytest.raises(SourceError):
        PoliteClient(sleep=lambda _s: None, session=session).get_json("https://example.test/x")


def test_non_json_is_a_source_error() -> None:
    session = FakeSession(200, "<html>captcha</html>")
    with pytest.raises(SourceError):
        PoliteClient(sleep=lambda _s: None, session=session).get_json("https://example.test/x")


def test_pauses_between_requests_but_not_before_the_first() -> None:
    pauses: list[float] = []
    client = PoliteClient(pause_seconds=(1.0, 3.0), sleep=pauses.append, session=FakeSession(200))
    client.get_json("https://example.test/a")
    client.get_json("https://example.test/b")
    client.get_json("https://example.test/c")
    assert len(pauses) == 2
    assert all(1.0 <= p <= 3.0 for p in pauses)
