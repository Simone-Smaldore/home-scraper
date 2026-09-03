"""The runner: fetch listings from the sources and apply the hard filter.

    python -m scripts.scrape --source subito --dry-run --no-llm
    python -m scripts.scrape --source subito --dry-run --no-llm --pages 5
    python -m scripts.scrape --source subito --dry-run --no-llm --all --show-rejected

M0 shape: dry run only — nothing is written anywhere, the listings are printed
with the filter's verdict. Persistence (M1) and the LLM evaluation (M2) plug in
here, around the same loop.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from app.domain.criteria import CRITERIA, check
from app.domain.format import eur, sqm
from app.domain.listing import Listing
from app.domain.vocabulary import Garage, SourceName
from app.sources.base import Blocked, ListingSource, PoliteClient, SourceError
from app.sources.immobiliare import ImmobiliareSource
from app.sources.subito import SubitoSource

# Pages to read in a dry run unless --all is given: enough to see the filter at
# work, few enough to stay polite while iterating on it.
DRY_RUN_PAGES = 2


def build_source(name: SourceName, client: PoliteClient) -> ListingSource:
    if name is SourceName.SUBITO:
        return SubitoSource(client)
    if name is SourceName.IMMOBILIARE:
        return ImmobiliareSource(client, CRITERIA)
    raise NotImplementedError(f"fonte non ancora implementata: {name}")


def describe(listing: Listing) -> str:
    """One line, the way the dashboard row will read."""
    parts: list[str] = []
    parts.append(eur(listing.price_eur) if listing.price_eur is not None else "prezzo n.d.")
    parts.append(sqm(listing.size_sqm) if listing.size_sqm is not None else "mq n.d.")
    if listing.rooms is not None:
        parts.append(f"{listing.rooms} locali")
    if listing.floor_raw is not None:
        parts.append(f"piano {listing.floor_raw}")
    parts.append(str(listing.zone) if listing.zone else "zona n.d.")
    if listing.is_private is not None:
        parts.append("privato" if listing.is_private else "agenzia")
    if listing.garage is Garage.BOX:
        parts.append("box")
    elif listing.garage is Garage.POSTO_AUTO:
        parts.append("posto auto")
    if listing.price_per_sqm is not None:
        parts.append(f"{eur(listing.price_per_sqm)}/mq")
    if listing.is_auction:
        parts.append("ASTA")
    if listing.phone:
        parts.append(f"tel. {listing.phone}")
    return " · ".join(parts)


def dry_run(source: ListingSource, *, max_pages: int | None, show_rejected: bool) -> int:
    print(f"fonte: {source.name} — Torino, appartamenti in vendita")
    if source.name is SourceName.IMMOBILIARE:
        print("(prezzo, mq e locali sono già filtrati dal server: gli scarti qui sono zona, ascensore e balcone)")
    print("PROVA A VUOTO — niente viene scritto\n")

    passing: list[tuple[Listing, tuple[str, ...]]] = []
    rejected: list[tuple[Listing, tuple[str, ...]]] = []
    reasons: Counter[str] = Counter()

    try:
        for listing in source.fetch(max_pages=max_pages):
            verdict = check(listing, CRITERIA)
            if verdict.passes:
                passing.append((listing, verdict.unknowns))
            else:
                rejected.append((listing, verdict.rejections))
                # Count by kind, not by wording: the wording carries the number.
                for reason in verdict.rejections:
                    reasons[_kind(reason)] += 1
    except Blocked as exc:
        print(f"\nBLOCCATO: {exc}. Il giro si ferma qui e non riprova.")
        return 2
    except SourceError as exc:
        print(f"\nERRORE dalla fonte: {exc}")
        return 1

    total = len(passing) + len(rejected)
    print(f"annunci letti: {total}")
    print(f"passano il filtro: {len(passing)}")
    print(f"scartati: {len(rejected)}")
    for kind, count in reasons.most_common():
        print(f"  {kind}: {count}")

    print("\n--- passano ---")
    for listing, unknowns in passing:
        print(f"\n  {describe(listing)}")
        print(f"  {listing.title}")
        print(f"  {listing.url}")
        if unknowns:
            print(f"  da verificare: {', '.join(unknowns)}")

    if show_rejected:
        print("\n--- scartati ---")
        for listing, rejections in rejected:
            print(f"\n  {describe(listing)}")
            print(f"  {listing.title}")
            print(f"  perché: {'; '.join(rejections)}")
    return 0


def _kind(reason: str) -> str:
    """"prezzo 285.000 € sopra i 250.000 €" → "sopra budget", for the tally."""
    if "plausibile" in reason:
        return "prezzo non plausibile"
    if reason.startswith("prezzo"):
        return "sopra budget"
    if "sotto gli" in reason:
        return "troppo piccolo"
    if "locali" in reason:
        return "pochi locali"
    if reason.startswith("fuori zona"):
        return "fuori zona"
    return reason  # "senza ascensore", "senza balcone"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Raccoglie gli annunci e applica il filtro.")
    parser.add_argument(
        "--source",
        choices=[name.value for name in SourceName],
        default=SourceName.SUBITO.value,
    )
    parser.add_argument("--dry-run", action="store_true", help="non scrive niente (per ora l'unica modalità)")
    parser.add_argument("--no-llm", action="store_true", help="salta la valutazione (per ora sempre)")
    parser.add_argument("--pages", type=int, default=None, help="quante pagine leggere")
    parser.add_argument("--all", action="store_true", help="tutte le pagine")
    parser.add_argument("--show-rejected", action="store_true", help="stampa anche gli scartati")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.dry_run:
        print("Per ora esiste solo --dry-run: la persistenza arriva con M1.")
        return 1

    max_pages = None if args.all else (args.pages or DRY_RUN_PAGES)
    client = PoliteClient()
    try:
        source = build_source(SourceName(args.source), client)
        return dry_run(source, max_pages=max_pages, show_rejected=args.show_rejected)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
