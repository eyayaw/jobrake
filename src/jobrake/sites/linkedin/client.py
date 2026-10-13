"""Shared guest API URLs, headers, pacing, posting IDs, and cache."""

import asyncio
import logging
import re
from math import inf
from time import monotonic

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
# A cookie holding only the b= field pins a request to the fabric its first
# letter names, and LinkedIn routes it without checking a signature.
# paced_fetch therefore starts from FABRICS and pins each request to
# the least recently used fabric. When a pin drops, it sends requests without
# the cookie to learn a replacement. If LinkedIn starts ignoring these
# cookies, their pins drop the same way.
# One pacer at PACE / number of fabrics spaces the requests, which gives each
# fabric PACE between its requests while the fabrics take turns. A retry
# skips the fabrics it tried, so it can reach a fabric before that fabric's
# turn. pick therefore keeps each fabric's latest send time, and a request
# that reaches a fabric early waits for the rest of PACE.
# A request that LinkedIn reroutes to another fabric lands there out of turn
# and can put one request too many in that fabric's window. The pacer
# coordinates this process only; LinkedIn counts every process on the IP.
FABRICS = {"prod-lor1": '"b=OGST02"', "prod-ltx1": '"b=TGST02"', "prod-lva1": '"b=VGST02"'}
PACE = 2.5  # seconds between requests to one fabric: five per window, 1 s to spare
FABRICS_WANTED = len(FABRICS)  # distinct fabrics to look for before every request is pinned
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
        """Start from the fabrics in FABRICS."""
        self.known: dict[str, str] = dict(FABRICS)
        self.unpinned = 0
        self.sent: dict[str, float] = {}  # monotonic time of each fabric's latest send

    def discovering(self) -> bool:
        """Whether this pool still looks for fabrics with unpinned requests."""
        return not self.known or (len(self.known) < FABRICS_WANTED and self.unpinned < DISCOVERY)

    def pick(self, tried: set[str]) -> tuple[str | None, float]:
        """
        Choose a fabric for a request that already tried ``tried``, and the seconds to wait first.

        During discovery the request goes out unpinned, as ``None``, unless
        it is a retry with a known fabric left to try. An unpinned request can
        land on any fabric, so it waits until every fabric's latest request is
        PACE old. Otherwise pick chooses the least recently used known fabric
        outside ``tried``, or of all known fabrics once the request has tried
        each one, and waits until that fabric's latest request is PACE old.
        With no wait, pick records the send and adds the fabric to ``tried``.
        """
        now = monotonic()
        fresh = [name for name in self.known if name not in tried]
        if self.discovering() and not (tried and fresh):
            wait = max(self.sent.values(), default=-inf) + PACE - now
            if wait > 0:
                return None, wait
            self.unpinned += 1
            return None, 0.0
        name = min(fresh or list(self.known), key=lambda name: self.sent.get(name, -inf))
        wait = self.sent.get(name, -inf) + PACE - now
        if wait > 0:
            return name, wait
        self.sent[name] = now
        tried.add(name)
        return name, 0.0

    def learn(self, pinned: str | None, result: FetchResult, sent: float) -> None:
        """
        Record from ``result`` which fabric answered a request pinned to ``pinned`` and sent at ``sent``.

        Stores the fabric's lidc cookie, drops a pin whose request landed
        elsewhere, and records the send on a fabric that answered a request
        pick did not pin to it.
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
        if fabric and fabric != pinned:
            # An unpinned or rerouted request still spent this fabric's
            # budget, so its next turn comes PACE after this one.
            self.sent[fabric] = max(self.sent.get(fabric, -inf), sent)
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
    Fetch ``url`` through ``fetcher`` at the fabric pace and retry a 429 up to ``RETRIES`` times.

    The request carries an lidc Cookie header in place of the fetcher's own
    cookies, except on a redirect hop. A 429 that survives every retry is
    returned for the caller to decide whether the larger operation should
    stop. The transport stays open.
    """
    tried: set[str] = set()
    result = await _fetch_on_turn(fetcher, url, tried)
    for _ in range(RETRIES):
        if not rate_limited(result):
            break
        # A pinned retry goes to a fabric this request has not tried, which
        # has its own budget. Once it has tried every known fabric, it waits
        # for the window to clear first, so a fabric that refused it does not
        # get it back at once. During discovery that retry goes out unpinned
        # instead, without the wait. An unpinned request leaves only once every fabric
        # is PACE past its latest request, so apart from a reroute this
        # process cannot have filled the window that refused it.
        if POOL.known.keys() <= tried and not POOL.discovering():
            await asyncio.sleep(RETRY_DELAY)
        result = await _fetch_on_turn(fetcher, url, tried)
    return result


async def _fetch_on_turn(fetcher: Fetcher, url: str, tried: set[str]) -> FetchResult:
    """Send one paced request on the fabric ``POOL.pick`` chooses for ``tried``."""
    # The fabric is chosen after the pacer admits the request, so concurrent
    # callers take turns in the order they send. The interval set here
    # paces the next request.
    while True:
        await LIMITER.acquire()
        fabric, wait = POOL.pick(tried)
        if not wait:
            break
        # A request that must wait gives up its turn and takes a new one
        # afterward. Waiters that wake together, after an event loop stall or
        # when a dropped pin starts discovery, then leave one turn at a time.
        await asyncio.sleep(wait)
    LIMITER.refill_interval = PACE / len(POOL.known) if fabric else PACE
    # An explicit Cookie header replaces the jar's cookies for this request.
    # httpx sends the jar's cookies on a redirect hop instead.
    headers = HEADERS | {"cookie": f"lidc={POOL.known[fabric]}" if fabric else "lidc="}
    sent = monotonic()
    result = await fetcher.fetch(url, headers=headers)
    POOL.learn(fabric, result, sent)
    # An unpinned or rerouted attempt reveals the fabric that refused it only
    # in its answer, so a retry learns to skip that fabric here.
    if answered := result.headers.get("x-li-fabric"):
        tried.add(answered)
    return result


def job_id(url: str) -> str:
    """Extract a numeric posting ID, using ``""`` when the URL has none."""
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else ""
