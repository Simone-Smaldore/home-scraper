"""Spotting judicial auctions from the text of a listing.

Neither site has a reliable structured flag for them, so this looks at the
words. Deliberately narrow: "asta" alone would also match "fantastica", and a
listing that mentions a nearby "piazza dell'Asta" is not an auction.
"""

from __future__ import annotations

import re

_AUCTION = re.compile(
    r"\b(?:all'asta|in asta|asta giudiziaria|asta immobiliare|vendita giudiziaria|"
    r"immobile in asta|tribunale di)\b",
    re.IGNORECASE,
)


def is_auction(*texts: str | None) -> bool:
    return any(text and _AUCTION.search(text) for text in texts)
