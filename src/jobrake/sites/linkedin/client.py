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

# LinkedIn serves the guest API from several data centers, which it calls
# fabrics, and counts the 429 budget per IP and per fabric. The response
# header ``x-li-fabric`` names the fabric that answered.
#
# The ``lidc`` cookie pins a client to one fabric. A request without it may
# land on any fabric, and the response sets that fabric's cookie. A client
# that keeps its cookie jar therefore spends one fabric's budget only.
#
# As of 2026-10-13, from a residential IP, a fabric serves 5 requests per
# sliding 11.5-second window. The same three fabrics answer from North
# America, Europe, Asia, and Oceania.
#
# paced_fetch first sends requests without the cookie to learn the fabrics,
# then pins each request to the fabric whose turn it is. The fabrics take
# strict turns, so one pacer at PACE / number of fabrics gives each fabric
# PACE between its requests. A request that LinkedIn reroutes to another
# fabric lands there out of turn and can put one request too many in that
# fabric's window. The pacer coordinates this process only; LinkedIn counts
# every process on the IP.
PACE = 2.5  # seconds between requests to one fabric: five per window, 1 s to spare
FABRICS_WANTED = 3  # distinct fabrics to look for before every request is pinned
DISCOVERY = 12  # unpinned requests to spend looking for them
LIMITER = TokenBucket(capacity=1, refill_interval=PACE)
# In our runs, LinkedIn refused up to a quarter of requests however slow the
# pace, and every such refusal passed on a retry. A request is therefore
# retried this many times before its 429 counts as persistent.
RETRIES = 3

# LinkedIn's guest 429 responses carry no Retry-After header. A 429 from a
# full window clears once the window's oldest request ages out, so a retry
# that waits sleeps one full window.
RETRY_DELAY = 12.0

# The cookie value is quoted and holds neither comma nor semicolon, so it
# survives the comma-joined set-cookie header a fetcher may deliver.
_LIDC = re.compile(r'lidc=("[^"]*")')


class Fabrics:
    """The fabrics seen by this process and the lidc cookie that pins each."""

    def __init__(self) -> None:
        """Start with no fabric known."""
        self.known: dict[str, str] = {}
        self.unpinned = 0

    def discovering(self) -> bool:
        """Whether the next request goes out unpinned to look for fabrics."""
        return not self.known or (len(self.known) < FABRICS_WANTED and self.unpinned < DISCOVERY)

    def pick(self) -> str | None:
        """
        Choose the fabric for the next request.

        Returns ``None`` while fabrics are still being discovered, or none is
        known. Known fabrics take turns, least recently used first.
        """
        if self.discovering():
            self.unpinned += 1
            return None
        name = next(iter(self.known))
        self.known[name] = self.known.pop(name)
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
            # concurrent request may have dropped it already. The discovery
            # budget resets, so pick looks for a replacement while fewer than
            # FABRICS_WANTED are known.
            self.known.pop(pinned, None)
            self.unpinned = 0
        if fabric in self.known and fabric != pinned:
            # An unpinned or rerouted request still spent this fabric's
            # budget, so it goes to the back of the turns.
            self.known[fabric] = self.known.pop(fabric)
        if fabric and (found := _LIDC.search(result.headers.get("set-cookie", ""))):
            if fabric not in self.known:
                logger.debug("linkedin fabric %s found, %d known", fabric, len(self.known) + 1)
            self.known[fabric] = found.group(1)


POOL = Fabrics()


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

    The request carries an lidc Cookie header in place of the fetcher's own
    cookies, except on a redirect hop. A 429 that survives every retry is returned for the
    caller to decide whether the larger operation should stop. The transport
    stays open.
    """
    result = await _fetch_on_turn(fetcher, url)
    for attempt in range(1, RETRIES + 1):
        if not rate_limited(result):
            break
        # A pinned retry goes to the next fabric in turn, which has its own
        # budget. Once the request has had as many attempts as there are known
        # fabrics, a pinned retry waits for the window to clear first, so a
        # fabric that refused it does not get it back at once. During
        # discovery the retry goes out unpinned without waiting. Unpinned
        # requests leave PACE apart, so apart from a reroute this process
        # cannot have filled the window that refused it.
        if attempt >= len(POOL.known) and not POOL.discovering():
            await asyncio.sleep(RETRY_DELAY)
        result = await _fetch_on_turn(fetcher, url)
    return result


async def _fetch_on_turn(fetcher: Fetcher, url: str) -> FetchResult:
    """Send one paced request, pinned to the fabric whose turn it is."""
    # The fabric is chosen after the pacer admits the request, so concurrent
    # callers take turns in the order they send. The interval set here
    # paces the next request.
    await LIMITER.acquire()
    fabric = POOL.pick()
    LIMITER.refill_interval = PACE / len(POOL.known) if fabric else PACE
    # An explicit Cookie header replaces the jar's cookies for this request.
    # httpx sends the jar's cookies on a redirect hop instead.
    headers = HEADERS | {"cookie": f"lidc={POOL.known[fabric]}" if fabric else "lidc="}
    result = await fetcher.fetch(url, headers=headers)
    POOL.learn(fabric, result)
    return result


def job_id(url: str) -> str:
    """Extract a numeric posting ID, using ``""`` when the URL has none."""
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else ""
