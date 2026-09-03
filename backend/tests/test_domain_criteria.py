"""The hard filter.

⚠️ `test_hard_limits_are_never_crossed` and `test_unknown_is_not_no` are the
untouchable pair of this project. The first says the dashboard never shows a
flat outside budget, size, rooms or zone; the second says it never hides one
because the site left a field blank. Break either and the dashboard is noise
or blind.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.criteria import CRITERIA, TARGET_ZONES, Criteria, check
from app.domain.listing import Listing
from app.domain.vocabulary import SourceName, Zone


def make(**overrides: Any) -> Listing:
    """A listing that passes everything; override one field to test a rule."""
    base: dict[str, Any] = dict(
        source=SourceName.SUBITO,
        source_id="1",
        url="https://example.test/1",
        title="Quadrilocale",
        description="",
        price_eur=200_000,
        size_sqm=95,
        rooms=4,
        elevator=True,
        balcony=True,
        zone=Zone.CENISIA,
    )
    base.update(overrides)
    return Listing(**base)


def test_the_baseline_passes_cleanly() -> None:
    verdict = check(make())
    assert verdict.passes
    assert verdict.rejections == ()
    assert verdict.unknowns == ()


@pytest.mark.parametrize(
    ("field", "value", "reason_contains"),
    [
        ("price_eur", 250_001, "sopra i 250.000 €"),
        ("price_eur", 900, "non plausibile"),
        ("size_sqm", 79, "sotto gli 80 mq"),
        ("rooms", 2, "2 locali"),
        ("zone", Zone.MIRAFIORI, "fuori zona"),
        ("zone", Zone.CENTRO, "fuori zona"),
        ("elevator", False, "senza ascensore"),
        ("balcony", False, "senza balcone"),
    ],
)
def test_hard_limits_are_never_crossed(field: str, value: Any, reason_contains: str) -> None:
    verdict = check(make(**{field: value}))
    assert not verdict.passes
    assert any(reason_contains in r for r in verdict.rejections), verdict


@pytest.mark.parametrize(
    ("field", "unknown"),
    [
        ("price_eur", "prezzo assente"),
        ("size_sqm", "superficie assente"),
        ("rooms", "locali non indicati"),
        ("zone", "zona non indicata"),
        ("elevator", "ascensore non indicato"),
        ("balcony", "balcone non indicato"),
    ],
)
def test_unknown_is_not_no(field: str, unknown: str) -> None:
    verdict = check(make(**{field: None}))
    assert verdict.passes, verdict
    assert unknown in verdict.unknowns


@pytest.mark.parametrize(
    ("field", "value"),
    [("price_eur", 250_000), ("price_eur", 20_000), ("size_sqm", 80), ("rooms", 3)],
)
def test_limits_are_inclusive(field: str, value: Any) -> None:
    assert check(make(**{field: value})).passes


def test_every_target_zone_passes() -> None:
    for zone in TARGET_ZONES:
        assert check(make(zone=zone)).passes
    assert TARGET_ZONES == {Zone.CENISIA, Zone.CIT_TURIN, Zone.CROCETTA, Zone.SANTA_RITA}


def test_all_rejections_are_reported_together() -> None:
    verdict = check(make(price_eur=300_000, size_sqm=50, rooms=1, zone=Zone.MIRAFIORI))
    assert len(verdict.rejections) == 4


def test_criteria_are_the_agreed_ones() -> None:
    assert CRITERIA == Criteria(
        max_price_eur=250_000,
        min_price_eur=20_000,
        min_size_sqm=80,
        min_rooms=3,
        zones=TARGET_ZONES,
        require_elevator=True,
        require_balcony=True,
    )


def test_requirements_can_be_switched_off() -> None:
    relaxed = Criteria(require_elevator=False, require_balcony=False)
    verdict = check(make(elevator=False, balcony=None), relaxed)
    assert verdict.passes
    assert verdict.unknowns == ()
