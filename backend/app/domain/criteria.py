"""What you are looking for, and the hard filter that applies it.

Two levels, and the distinction is the heart of the product:

  - **hard**: budget, size, rooms, zone, lift and balcony. Deterministic, tested,
    and applied before any LLM call — a listing that fails here never spends
    quota.
  - **soft**: living room, a spare room for a future nursery, condition, floor,
    price against the zone median. Read from the free text by the LLM, scored,
    never used to reject.

⚠️ "Unknown" is not "no". A listing with no "ascensore" field passes the lift
rule and carries the gap in `unknowns`, so the LLM reads the description for it
and the dashboard says "da verificare". Rejecting on missing data would throw
away half the good flats, because listings are filled in carelessly.

One user, so the criteria are constants: changing them is a commit, not a form.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.format import eur, sqm
from app.domain.listing import Listing
from app.domain.vocabulary import Zone

TARGET_ZONES = frozenset(
    {
        Zone.CENISIA,  # Cenisia, San Paolo
        Zone.CIT_TURIN,  # Cit Turin, San Donato, Campidoglio
        Zone.CROCETTA,
        Zone.SANTA_RITA,  # the zone also covers Lingotto: the LLM refines from the address
    }
)


@dataclass(frozen=True)
class Criteria:
    max_price_eur: int = 250_000
    # Below this a "sale" is a rent posted in the wrong category or a typo.
    # Seen in the wild: a two-room flat "for sale" at 900 €.
    min_price_eur: int = 20_000
    min_size_sqm: int = 80
    min_rooms: int = 3
    zones: frozenset[Zone] = TARGET_ZONES
    require_elevator: bool = True
    require_balcony: bool = True


CRITERIA = Criteria()


@dataclass(frozen=True)
class Verdict:
    """The outcome of the hard filter, with its reasons spelled out.

    `rejections` is why it failed (empty when it passes); `unknowns` lists the
    fields the site left blank, which the listing passed on the benefit of the
    doubt. Both are Italian, because they end up on screen.
    """

    rejections: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()

    @property
    def passes(self) -> bool:
        return not self.rejections


def check(listing: Listing, criteria: Criteria = CRITERIA) -> Verdict:
    rejections: list[str] = []
    unknowns: list[str] = []

    if listing.price_eur is None:
        unknowns.append("prezzo assente")
    elif listing.price_eur < criteria.min_price_eur:
        rejections.append(f"prezzo {eur(listing.price_eur)} non plausibile per una vendita")
    elif listing.price_eur > criteria.max_price_eur:
        rejections.append(f"prezzo {eur(listing.price_eur)} sopra i {eur(criteria.max_price_eur)}")

    if listing.size_sqm is None:
        unknowns.append("superficie assente")
    elif listing.size_sqm < criteria.min_size_sqm:
        rejections.append(f"{sqm(listing.size_sqm)} sotto gli {sqm(criteria.min_size_sqm)}")

    if listing.rooms is None:
        unknowns.append("locali non indicati")
    elif listing.rooms < criteria.min_rooms:
        rejections.append(f"{listing.rooms} locali, ne servono almeno {criteria.min_rooms}")

    if listing.zone is None:
        unknowns.append("zona non indicata")
    elif listing.zone not in criteria.zones:
        rejections.append(f"fuori zona: {listing.zone}")

    if criteria.require_elevator:
        if listing.elevator is None:
            unknowns.append("ascensore non indicato")
        elif listing.elevator is False:
            rejections.append("senza ascensore")

    if criteria.require_balcony:
        if listing.balcony is None:
            unknowns.append("balcone non indicato")
        elif listing.balcony is False:
            rejections.append("senza balcone")

    return Verdict(rejections=tuple(rejections), unknowns=tuple(unknowns))
