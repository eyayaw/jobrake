"""Shared guest API URLs, headers, pacing, posting IDs, and cache."""

import asyncio
import logging
import re

from jobrake.cache import Cache
from jobrake.fetchkit import ErrorCategory, Fetcher, FetchResult, TokenBucket

logger = logging.getLogger(__name__)


def rate_limited(result: FetchResult) -> bool:
    """Check for a rate-limited error."""
    return result.error is not None and result.error.category is ErrorCategory.RATE_LIMITED


BASE_URL = "https://www.linkedin.com"
SEARCH_URL = f"{BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"
TYPEAHEAD_URL = f"{BASE_URL}/jobs-guest/api/typeaheadHits"

HEADERS = {
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# LinkedIn counts guest requests per IP and per fabric, its name for a data
# center, and reports the fabric that answered in the ``x-li-fabric`` header.
# The ``lidc`` cookie pins a client to one fabric; a request without it may
# land on any fabric and receives that fabric's cookie. Measured on 2026-10-07 from a
# residential IP: each fabric serves 5 requests per sliding 11.5-second
# window, and three fabrics answered. paced_fetch learns the fabrics from
# unpinned requests, then pins each request to the fabric whose turn it is.
# The fabrics take strict turns, so one pacer at PACE divided by their number
# keeps every fabric inside its own window. The pacer coordinates calls in
# this process only, while LinkedIn counts every process on the IP.
PACE = 2.5  # seconds between requests to one fabric: five per window, 1 s to spare
FABRICS_WANTED = 3  # distinct fabrics to look for before every request is pinned
DISCOVERY = 12  # unpinned requests to spend looking for them
LIMITER = TokenBucket(capacity=1, refill_interval=PACE)
# After heavy traffic LinkedIn refused 10-20% of requests for a while however
# slow the pace. Such a refusal passes on a retry, so a request is retried
# this many times before its 429 counts as persistent.
RETRIES = 3

# A 429 clears when the oldest request in the window ages out, within 11.5
# seconds. A seconds-form Retry-After takes precedence. jobrake will not wait
# longer than a minute: past that, the 429 goes back to the caller unretried.
RETRY_DELAY = 12.0
MAX_RETRY_DELAY = 60.0

# The cookie value is quoted and holds neither comma nor semicolon, so it
# survives the comma-joined set-cookie header a fetcher may deliver.
_LIDC = re.compile(r'lidc=("[^"]*")')


class Fabrics:
    """The fabrics seen by this process and the lidc cookie that pins each."""

    def __init__(self) -> None:
        """Start with no fabric known."""
        self.known: dict[str, str] = {}
        self.unpinned = 0

    def pick(self) -> str | None:
        """
        Choose the fabric for the next request.

        Returns ``None`` while fabrics are still being discovered, or none is
        known. Known fabrics take turns, least recently used first, at PACE
        per fabric.
        """
        if not self.known or (len(self.known) < FABRICS_WANTED and self.unpinned < DISCOVERY):
            self.unpinned += 1
            LIMITER.refill_interval = PACE
            return None
        name = next(iter(self.known))
        self.known[name] = self.known.pop(name)
        LIMITER.refill_interval = PACE / len(self.known)
        return name

    def learn(self, pinned: str | None, result: FetchResult) -> None:
        """
        Record which fabric answered a request pinned to ``pinned``.

        Stores the fabric's lidc cookie and drops a pin whose request landed
        elsewhere.
        """
        fabric = result.headers.get("x-li-fabric")
        logger.debug(
            "linkedin %s %s %s",
            fabric,
            "refused" if rate_limited(result) else "answered",
            f"a request pinned to {pinned}" if pinned else "an unpinned request",
        )
        if pinned and fabric and fabric != pinned:
            # The pin no longer holds, so its cookie would land anywhere. A
            # concurrent request may have dropped it already.
            self.known.pop(pinned, None)
        if fabric and (found := _LIDC.search(result.headers.get("set-cookie", ""))):
            if fabric not in self.known:
                logger.debug("linkedin fabric %s found, %d known", fabric, len(self.known) + 1)
            self.known[fabric] = found.group(1)


POOL = Fabrics()


def _retry_delay(result: FetchResult) -> float | None:
    """Choose a retry delay within the local wait limit."""
    value = result.headers.get("retry-after", "")
    # Unicode digits such as "²" pass isdigit but not float().
    if not (value.isascii() and value.isdigit()):
        return RETRY_DELAY
    seconds = float(value)
    return seconds if seconds <= MAX_RETRY_DELAY else None


def __getattr__(name: str) -> Cache:
    # One cache per process, built when a fetch first reads ``CACHE``. Its
    # environment settings are read at that moment, so importing jobrake
    # neither reads them nor warns about them.
    if name == "CACHE":
        cache = globals()["CACHE"] = Cache()
        return cache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def paced_fetch(fetcher: Fetcher, url: str) -> FetchResult:
    """
    Pace one LinkedIn request on its fabric and retry a 429 up to ``RETRIES`` times.

    The request carries the lidc cookie of the fabric whose turn it is, or an
    empty one while fabrics are being discovered, so the fetcher's own cookie
    jar does not pin every request to one fabric. That Cookie header replaces
    every cookie the fetcher would send. A retry goes to the fabric whose turn
    is next. It waits first when fewer than two fabrics are known, when the
    server names a wait, or before the last retry. A seconds-form
    ``Retry-After`` sets the wait, and a missing or unreadable value uses
    ``RETRY_DELAY``. A delay above ``MAX_RETRY_DELAY`` skips the retries. A
    429 that survives every retry is returned for the caller to decide whether
    the larger operation should stop. Every attempt uses the supplied
    transport, which remains open afterward.
    """
    fabric, result = await _fetch_on_turn(fetcher, url)
    for attempt in range(1, RETRIES + 1):
        if not rate_limited(result):
            break
        delay = _retry_delay(result)
        if delay is None:
            break
        # Another fabric has its own budget, so a retry goes there at once.
        # Without one, when the server names a wait, or on the last retry,
        # the retry waits for the window to clear first.
        if len(POOL.known) < 2 or "retry-after" in result.headers or attempt == RETRIES:
            await asyncio.sleep(delay)
        fabric, result = await _fetch_on_turn(fetcher, url)
    return result


async def _fetch_on_turn(fetcher: Fetcher, url: str) -> tuple[str | None, FetchResult]:
    """Send one request pinned to the fabric whose turn it is, and name the fabric."""
    fabric = POOL.pick()
    # An explicit Cookie header replaces the jar's cookies for this request.
    # httpx sends the jar's cookies on a redirect hop instead.
    headers = HEADERS | {"cookie": f"lidc={POOL.known[fabric]}" if fabric else "lidc="}
    await LIMITER.acquire()
    result = await fetcher.fetch(url, headers=headers)
    POOL.learn(fabric, result)
    return fabric, result


def job_id(url: str) -> str:
    """Extract a numeric posting ID, using ``""`` when the URL has none."""
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else ""
