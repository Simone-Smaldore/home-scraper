"""What every source shares: the HTTP client and its manners.

A source does network I/O and returns `Listing`s. It never touches the
database — the runner in scripts/scrape.py tells it which ids are already known
through a callback, which is all it needs to decide when to stop paging.

⚠️ The client is curl_cffi impersonating Chrome, not httpx or urllib. Subito
sits behind Akamai, which fingerprints the TLS handshake: every pure-Python SSL
stack gets "Access Denied" with the very same headers that curl accepts. This
was measured, not assumed (2026-09-03). Because the impersonation also sets a
matching User-Agent, we do not override it — a browser UA on a non-browser
handshake is itself a bot signal.

Politeness here is also self-defence. Two runs a day, a pause between requests,
no parallelism. A 403 or 429 ends the run for that source with `Blocked` and is
**not retried**: hammering a site that just said no is exactly the behaviour
that raises the wall for good.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator
from typing import Any, Protocol
from urllib.parse import urlsplit

from curl_cffi import requests

from app.domain.listing import Listing
from app.domain.vocabulary import SourceName

# A recent Chrome; curl_cffi resolves "chrome" to the newest it knows.
IMPERSONATE = "chrome"

# Only what an XHR from the site itself would add. Everything else — UA,
# sec-ch-*, accept-encoding — comes from the impersonation and must match it.
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
}


class SourceError(RuntimeError):
    """The site answered, but not with what we asked for."""


class Blocked(SourceError):
    """403 or 429: the site said no. Stop this source's run; do not retry."""


class HttpResponse(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...


class HttpSession(Protocol):
    """The slice of curl_cffi's Session we use; tests hand in a fake."""

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> HttpResponse: ...

    def close(self) -> None: ...


class PoliteClient:
    """A session that waits between requests and refuses to push through a block.

    `sleep` and `session` are injectable so tests run instantly and offline.
    """

    def __init__(
        self,
        *,
        pause_seconds: tuple[float, float] = (1.0, 3.0),
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        session: HttpSession | None = None,
    ) -> None:
        self._pause = pause_seconds
        self._sleep = sleep
        self._session: HttpSession = session or requests.Session(
            impersonate=IMPERSONATE, headers=DEFAULT_HEADERS, timeout=timeout
        )
        self._requests_made = 0

    @property
    def requests_made(self) -> int:
        return self._requests_made

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self._requests_made > 0:
            self._sleep(random.uniform(*self._pause))
        self._requests_made += 1

        response = self._session.get(url, params=params)
        host = urlsplit(url).hostname or url
        # 418 is Immobiliare's way of saying "enough": seen after ~65 pages in a
        # row from a GitHub runner on 2026-09-04. A block like the others.
        if response.status_code in (403, 418, 429) or _is_rate_limit_in_disguise(response):
            raise Blocked(f"{response.status_code} da {host}: {response.text[:120]}")
        if response.status_code >= 400:
            raise SourceError(f"{response.status_code} da {host}: {response.text[:120]}")
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError(f"risposta non JSON da {host}") from exc

    def close(self) -> None:
        self._session.close()


def _is_rate_limit_in_disguise(response: HttpResponse) -> bool:
    """Subito answers a rate limit as a 500 whose body says
    `[429 Too Many Requests]` — seen on 2026-09-03 after a day of probing.
    It is a block, and must end the run like one."""
    if response.status_code < 500:
        return False
    text = response.text[:500].lower()
    return "429" in text or "too many requests" in text


class ListingSource(Protocol):
    name: SourceName

    def fetch(
        self,
        *,
        is_known: Callable[[str], bool],
        max_pages: int | None = None,
    ) -> Iterator[Listing]:
        """Yield listings newest first, stopping once a whole page is already known.

        `is_known(source_id)` answers from the database. On a first run it is
        always False and the source walks every page; on a daily run the first
        page is usually enough.
        """
        ...
