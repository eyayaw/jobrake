"""Shared guest API URLs, headers, pacing, and posting IDs."""

import asyncio
import logging
import re
from math import inf
from time import monotonic
from urllib.parse import urljoin, urlsplit

from jobrake.fetchkit import Fetcher, FetchResult

logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com"
SEARCH_URL = f"{BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"
TYPEAHEAD_URL = f"{BASE_URL}/jobs-guest/api/typeaheadHits"
# The guest fragment has the same topcard and criteria markup as the posting page
# at about a tenth of the size. The canonical page sets a locale cookie from
# the posting country's subdomain. Request ``_l=en_US`` so the fragment uses
# the labels and number format understood by the markup parsers.
FRAGMENT_URL = f"{BASE_URL}/jobs-guest/jobs/api/jobPosting"

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
# Measured 2026-10-13 from a residential IP: a fabric serves 5 requests per
# sliding 11.5-second window. Live posting-page probes on 2026-11-07 also
# accepted five-request bursts. The same three fabrics answer from North
# America, Europe, Asia, and Oceania.
#
# A cookie holding only the b= field pins a request to the fabric its first
# letter names, and LinkedIn routes it without checking a signature.
# paced_fetch therefore starts from FABRICS and pins each request to
# the least recently used fabric. When a pin drops, it sends requests without
# the cookie to learn a replacement. If LinkedIn starts ignoring these
# cookies, their pins drop the same way.
# pick records sends in a sliding window, allowing a short batch to finish
# without waiting between requests while keeping the sustained rate bounded.
# A request that LinkedIn reroutes to another fabric lands there out of turn.
# Requests overlap, so several can be in flight to a fabric when its pin
# drops, and the fabric that answers them then takes that many beyond its
# window. The pool coordinates this process only; LinkedIn counts every
# process on the IP.
FABRICS = {"prod-lor1": '"b=OGST02"', "prod-ltx1": '"b=TGST02"', "prod-lva1": '"b=VGST02"'}
WINDOW = 11.6  # seconds per fabric window, with 0.1 s beyond the measured limit
REQUESTS = 5  # requests per fabric window
FABRICS_WANTED = len(FABRICS)  # distinct fabrics to look for before every request is pinned
DISCOVERY = 12  # unpinned requests to spend looking for them
# In our runs, LinkedIn refused up to a quarter of requests however slow the
# pace, and every such refusal passed on a retry. A request is therefore
# retried this many times before its 429 counts as persistent.
RETRIES = 3

# Match HTTPX's default: https://www.python-httpx.org/api/#asyncclient (checked 2026-11-07).
_MAX_REDIRECTS = 20

# LinkedIn's guest 429 responses carry no Retry-After header. A 429 from a
# full window clears once the window's oldest request ages out, so a retry
# that waits sleeps one full window.
RETRY_DELAY = WINDOW

# The cookie value is quoted and holds neither comma nor semicolon, so it
# survives the comma-joined set-cookie header a fetcher may deliver.
_LIDC = re.compile(r'lidc=("[^"]*")')


class Fabrics:
    """Known fabrics, their pinning cookies, and this process's request windows."""

    def __init__(self) -> None:
        self.known: dict[str, str] = dict(FABRICS)
        self.unpinned = 0
        self.sent: dict[str, float] = {}  # monotonic time of each fabric's latest send
        # None holds unanswered unpinned sends, charged against every fabric.
        self.history: dict[str | None, list[float]] = {}
        # Discovery stays spaced because its routing is unknown until the answer.
        self.next_turn = -inf

    def discovering(self) -> bool:
        return not self.known or (len(self.known) < FABRICS_WANTED and self.unpinned < DISCOVERY)

    def pick(self, tried: set[str]) -> tuple[str | None, float]:
        """
        Choose a fabric for a request that already tried ``tried``, and the seconds to wait first.

        During discovery the request goes out unpinned, as ``None``, unless
        it is a retry with a known fabric left to try. An unpinned request can
        land on any fabric, so it needs room in every fabric's window.
        Otherwise pick chooses the earliest available fabric outside ``tried``,
        or among all known fabrics once the request has tried each one, with
        the least recently used first. With no wait, pick records the send
        and adds a pinned fabric to ``tried``.
        """
        now = monotonic()
        self.history = {
            name: [stamp for stamp in times if stamp > now - WINDOW]
            for name, times in self.history.items()
        }
        unknown = self.history.get(None, [])
        waits = {}
        for name in self.known.keys() | self.history.keys() | {None}:
            times = sorted(self.history.get(name, []) + (unknown if name is not None else []))
            waits[name] = (
                max(0.0, times[-REQUESTS] + WINDOW - now) if len(times) >= REQUESTS else 0.0
            )
        fresh = [name for name in self.known if name not in tried]
        if self.discovering() and not (tried and fresh):
            wait = max(self.next_turn - now, *waits.values())
            if wait > 0:
                return None, wait
            self.unpinned += 1
            self.history.setdefault(None, []).append(now)
            self.next_turn = now + WINDOW / REQUESTS
            return None, 0.0
        name = min(
            fresh or list(self.known), key=lambda name: (waits[name], self.sent.get(name, -inf))
        )
        wait = max(self.next_turn - now, waits[name])
        if wait > 0:
            return name, wait
        self.sent[name] = now
        self.history.setdefault(name, []).append(now)
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
            "refused" if result.status == 429 else "answered",
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
            # budget. Out-of-order replies must keep its window chronological.
            self.sent[fabric] = max(self.sent.get(fabric, -inf), sent)
            self.history[fabric] = sorted([*self.history.get(fabric, []), sent])
            if pinned is None:
                self.history[None] = [
                    stamp for stamp in self.history.get(None, []) if stamp != sent
                ]
        if fabric and (found := _LIDC.search(result.headers.get("set-cookie", ""))):
            if fabric not in self.known:
                logger.debug("linkedin fabric %s found, %d known", fabric, len(self.known) + 1)
            self.known[fabric] = found.group(1)


POOL = Fabrics()


async def paced_fetch(fetcher: Fetcher, url: str) -> FetchResult:
    """
    Fetch ``url`` with paced redirect hops and up to ``RETRIES`` retries for each hop's 429.

    Each request carries a lidc Cookie header in place of the fetcher's own
    cookies. Only HTTPS LinkedIn redirects are followed. A persistent 429 is
    returned to the caller. The transport stays open.
    """
    for hop in range(_MAX_REDIRECTS + 1):
        result = await _fetch_with_retries(fetcher, url)
        # GET redirects: https://www.rfc-editor.org/rfc/rfc9110#section-15.4 (checked 2026-11-07).
        if result.error or result.status not in {301, 302, 303, 307, 308}:
            return result
        if not (location := result.headers.get("location")):
            return result
        if hop == _MAX_REDIRECTS:
            result.error = f"LinkedIn exceeded {_MAX_REDIRECTS} redirects"
            return result
        try:
            target = urljoin(result.url, location)
            parts = urlsplit(target)
            if parts.scheme != "https" or not (
                parts.hostname == "linkedin.com" or (parts.hostname or "").endswith(".linkedin.com")
            ):
                raise ValueError("expected an HTTPS LinkedIn URL")
        except ValueError as error:
            result.error = f"invalid LinkedIn redirect: {error}"
            return result
        url = target
    return result


async def _fetch_with_retries(fetcher: Fetcher, url: str) -> FetchResult:
    tried: set[str] = set()
    result = await _fetch_on_turn(fetcher, url, tried)
    for _ in range(RETRIES):
        if result.status != 429:
            break
        # A pinned retry goes to a fabric this request has not tried, which
        # has its own budget. Once it has tried every known fabric, it waits
        # for the window to clear first, so a fabric that refused it does not
        # get it back at once. During discovery that retry goes out unpinned
        # instead, without the wait. Unpinned attempts also reserve room in
        # every fabric's window until their answers identify where they landed.
        if POOL.known.keys() <= tried and not POOL.discovering():
            await asyncio.sleep(RETRY_DELAY)
        result = await _fetch_on_turn(fetcher, url, tried)
    return result


async def _fetch_on_turn(fetcher: Fetcher, url: str, tried: set[str]) -> FetchResult:
    """Send one paced request on the fabric ``POOL.pick`` chooses for ``tried``."""
    # pick records a send before any await, so concurrent callers never
    # share a turn.
    while True:
        fabric, wait = POOL.pick(tried)
        if not wait:
            break
        # A request that must wait asks again afterward. Waiters that wake
        # together, after an event loop stall or when a dropped pin starts
        # discovery, then leave one turn at a time: the first to ask takes it.
        await asyncio.sleep(wait)
    # An explicit Cookie header replaces the jar's cookies for this request.
    headers = HEADERS | {"cookie": f"lidc={POOL.known[fabric]}" if fabric else "lidc="}
    sent = POOL.history[fabric][-1]
    result = await fetcher.fetch(url, headers=headers, follow_redirects=False)
    POOL.learn(fabric, result, sent)
    # An unpinned or rerouted attempt reveals the fabric that refused it only
    # in its answer, so a retry learns to skip that fabric here.
    if answered := result.headers.get("x-li-fabric"):
        tried.add(answered)
    return result


def numeric(text: str) -> bool:
    """
    Tell whether text is all digits 0-9, as a LinkedIn ID is.

    ``isdigit`` alone also accepts other scripts' digits, such as fullwidth ones.
    """
    return text.isascii() and text.isdigit()


def job_id(url: str) -> str:
    """Extract a numeric posting ID, using ``""`` when the URL has none."""
    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if numeric(tail) else ""
