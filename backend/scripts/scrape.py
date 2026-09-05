"""The runner: fetch listings from the sources, filter, store.

    python -m scripts.scrape                    # incremental: stops at the first page of known ads
    python -m scripts.scrape --full             # every page; the only run that can declare an ad gone
    python -m scripts.scrape --source subito
    python -m scripts.scrape --dry-run --no-llm --pages 2 [--show-rejected]   # no database at all

Two kinds of run, and the difference is not cosmetic. An incremental run reads
newest-first and stops at the first page made entirely of ids it already has,
so it cannot know what disappeared further down. A full run walks everything
and is therefore the only one allowed to bump `missed_runs` and deactivate.
The morning cron is full, the evening one incremental.

Each source gets its own ScrapeRun row and its own try/except: a block on one
site must not cost the other its run. A block or an error ends that source's
walk without deactivating anything — an ad you did not get to see is not an
ad that is gone.

The LLM evaluation (--no-llm to skip) plugs in here at M2.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone

from app.db import get_session_factory
from app.domain.criteria import CRITERIA, check
from app.domain.format import eur, sqm
from app.domain.listing import Listing
from app.domain.vocabulary import Garage, SourceName
from app.models import ScrapeRun
from app.sources.base import Blocked, ListingSource, PoliteClient, SourceError
from app.sources.immobiliare import ImmobiliareSource
from app.sources.subito import SubitoSource
from app.store.listings import fetch_existing, known_ids, mark_missing, upsert
from scripts._common import Abort, announce, plural

# Pages to read in a dry run unless --all is given: enough to see the filter at
# work, few enough to stay polite while iterating on it.
DRY_RUN_PAGES = 2

# Ads per database round trip and per commit: one lookup query per batch, and
# a block halfway through keeps what came before.
BATCH = 50

# Seconds between requests, per site. Immobiliare counts requests and answers
# 418 when it has had enough; a longer pause is the polite half of the fix,
# the smaller bounding box is the other.
PAUSES: dict[SourceName, tuple[float, float]] = {
    SourceName.SUBITO: (1.0, 3.0),
    SourceName.IMMOBILIARE: (2.0, 5.0),
}


def build_source(name: SourceName) -> ListingSource:
    client = PoliteClient(pause_seconds=PAUSES[name])
    if name is SourceName.SUBITO:
        return SubitoSource(client)
    if name is SourceName.IMMOBILIARE:
        return ImmobiliareSource(client, CRITERIA)
    raise NotImplementedError(f"fonte non ancora implementata: {name}")


def _batches(items: Iterable[Listing], size: int) -> Iterator[list[Listing]]:
    batch: list[Listing] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


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


# --- the real run -----------------------------------------------------------


def run_source(source: ListingSource, *, full: bool, max_pages: int | None) -> ScrapeRun:
    """One source, one ScrapeRun row, its own transaction boundary."""
    now = datetime.now(timezone.utc)
    factory = get_session_factory()
    run = ScrapeRun(source=source.name, started_at=now, full=full, status="ok")

    with factory() as db:
        db.add(run)
        db.commit()

        known = set() if full else known_ids(db, source.name)
        seen: set[str] = set()
        counts: Counter[str] = Counter()

        try:
            listings = source.fetch(is_known=lambda i: i in known, max_pages=max_pages)
            for batch in _batches(listings, BATCH):
                existing = fetch_existing(db, source.name, {item.source_id for item in batch})
                for listing in batch:
                    verdict = check(listing, CRITERIA)
                    result = upsert(db, listing, verdict, now, existing)
                    seen.add(listing.source_id)
                    counts["fetched"] += 1
                    counts["new" if result.created else "updated"] += 1
                    counts["price_changes"] += result.price_changed
                    counts["passing"] += verdict.passes
                db.commit()
            if full:
                counts["deactivated"] = mark_missing(db, source.name, seen)
        except Blocked as exc:
            run.status = "blocked"
            run.error = str(exc)
        except SourceError as exc:
            run.status = "failed"
            run.error = str(exc)

        run.fetched = counts["fetched"]
        run.new = counts["new"]
        run.updated = counts["updated"]
        run.price_changes = counts["price_changes"]
        run.deactivated = counts["deactivated"]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

    _report(run, counts["passing"])
    return run


def _report(run: ScrapeRun, passing: int) -> None:
    kind = "completo" if run.full else "incrementale"
    print(f"\n{run.source} — giro {kind}")
    if run.status != "ok":
        label = "BLOCCATO" if run.status == "blocked" else "ERRORE"
        print(f"  {label}: {run.error}")
    print(f"  letti {run.fetched} · nuovi {run.new} · aggiornati {run.updated}")
    print(f"  {plural(run.price_changes, 'prezzo cambiato', 'prezzi cambiati')}")
    print(f"  passano il filtro (fra i letti): {passing}")
    if run.full:
        print(f"  {plural(run.deactivated, 'annuncio sparito', 'annunci spariti')}")
    seconds = (run.finished_at - run.started_at).total_seconds() if run.finished_at else 0
    print(f"  durata {seconds:.0f} s")


# --- the dry run ------------------------------------------------------------


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


# --- entry point ------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Raccoglie gli annunci, li filtra e li salva.")
    parser.add_argument(
        "--source",
        choices=[name.value for name in SourceName],
        default=None,
        help="una fonte sola (default: tutte)",
    )
    parser.add_argument("--full", action="store_true", help="tutte le pagine; segna chi è sparito")
    parser.add_argument("--dry-run", action="store_true", help="niente database: stampa e basta")
    parser.add_argument("--no-llm", action="store_true", help="salta la valutazione (arriva con M2)")
    parser.add_argument("--pages", type=int, default=None, help="quante pagine leggere")
    parser.add_argument("--all", action="store_true", help="(dry run) tutte le pagine")
    parser.add_argument("--show-rejected", action="store_true", help="(dry run) stampa anche gli scartati")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    names = [SourceName(args.source)] if args.source else list(SourceName)

    if args.dry_run:
        max_pages = None if args.all else (args.pages or DRY_RUN_PAGES)
        codes = [
            dry_run(build_source(name), max_pages=max_pages, show_rejected=args.show_rejected)
            for name in names
        ]
        return max(codes)

    try:
        announce(f"Raccolta annunci — giro {'completo' if args.full else 'incrementale'}")
    except Abort as exc:
        print(exc)
        return 1
    if not args.no_llm:
        print("valutazione LLM: non ancora disponibile, arriva con M2")

    runs = [run_source(build_source(name), full=args.full, max_pages=args.pages) for name in names]
    # A blocked or failed source turns the workflow red, which is the alert.
    return 0 if all(run.status == "ok" for run in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
