"""Export everything to a JSON file.

    python -m scripts.backup                     # backup-AAAA-MM-GG.json here
    python -m scripts.backup --out ~/casa.json
    python -m scripts.backup --no-raw            # smaller: without the sites' payloads

Read-only, so no --apply. What you cannot get back by scraping again is what
this is for: your reviews, the price trails, and the ads that have since gone.

⚠️ backup-*.json is in .gitignore: it is the whole database.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from app.db import get_session_factory
from app.models import Listing, PriceHistory, Review, ScrapeRun
from scripts._common import Abort, announce, plural


def _plain(row: Any, *, skip: set[str] = frozenset()) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in skip:
            continue
        value = getattr(row, column.name)
        out[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Esporta tutto in JSON.")
    parser.add_argument("--out", default=f"backup-{date.today().isoformat()}.json")
    parser.add_argument("--no-raw", action="store_true", help="senza i payload dei siti")
    args = parser.parse_args(argv)

    try:
        announce("Backup")
    except Abort as exc:
        print(exc)
        return 1

    skip = {"raw"} if args.no_raw else set()
    with get_session_factory()() as db:
        payload = {
            "exported_at": datetime.now().astimezone().isoformat(),
            "listings": [_plain(r, skip=skip) for r in db.scalars(select(Listing).order_by(Listing.id))],
            "price_history": [_plain(r) for r in db.scalars(select(PriceHistory).order_by(PriceHistory.id))],
            "reviews": [_plain(r) for r in db.scalars(select(Review).order_by(Review.id))],
            "scrape_runs": [_plain(r) for r in db.scalars(select(ScrapeRun).order_by(ScrapeRun.id))],
        }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)

    print(
        f"scritto {args.out}: "
        f"{plural(len(payload['listings']), 'annuncio', 'annunci')}, "
        f"{plural(len(payload['reviews']), 'review', 'review')}, "
        f"{plural(len(payload['price_history']), 'prezzo', 'prezzi')}, "
        f"{plural(len(payload['scrape_runs']), 'giro', 'giri')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
