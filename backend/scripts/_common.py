"""Shared plumbing for the scripts.

Two things live here because getting either wrong costs real data:

  - **which database you are about to touch**, printed before anything happens;
  - **the dry run**, which is the default for anything destructive and has to
    be opted out of with --apply.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.config import get_settings


class Abort(RuntimeError):
    """Something is wrong enough that the script should stop and say so."""


def target_database() -> str:
    """"ep-xxx-pooler.eu-central-1.aws.neon.tech / neondb", never the password.

    Printed by every script before it does anything. It is the guard against
    the one mistake that has no undo: being somewhere else than you thought.
    """
    url = get_settings().database_url
    if not url:
        raise Abort("DATABASE_URL non è configurata")

    parts = urlsplit(url)
    name = parts.path.lstrip("/") or "?"
    return f"{parts.hostname or '?'} / {name}"


def plural(count: int, one: str, many: str) -> str:
    """"1 annuncio" and "5 annunci"."""
    return f"{count} {one if count == 1 else many}"


def announce(what: str) -> None:
    print(f"database: {target_database()}")
    print(what)
