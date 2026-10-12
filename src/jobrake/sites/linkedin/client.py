"""Shared guest API URLs, headers, pacing, posting IDs, and cache."""

import asyncio

from jobrake.cache import Cache
from jobrake.fetchkit import ErrorCategory, Fetcher, FetchResult, TokenBucket


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

# In testing, the sixth search request returned 429 after a four-request burst
# when requests were 2.25 seconds apart. Three seconds between requests avoided
# that limit. Longer runs can still hit another rate limit, so paced_fetch
# retries once. The module-level bucket coordinates calls in this process;
# LinkedIn applies the budget per IP.
LIMITER = TokenBucket(capacity=2, refill_interval=3.0)

# A 429 remains after five seconds and clears around ten. Measured on
# 2026-08-27 and 2026-10-12: LinkedIn's guest 429 responses carry no
# Retry-After header.
RETRY_DELAY = 10.0


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
    Pace one LinkedIn request and retry a 429 once after ``RETRY_DELAY``.

    A persistent 429 is returned for the caller to decide whether the larger
    operation should stop. Both attempts use the supplied transport, which
    remains open afterward.
    """
    await LIMITER.acquire()
    result = await fetcher.fetch(url, headers=HEADERS)
    if rate_limited(result):
        await asyncio.sleep(RETRY_DELAY)
        await LIMITER.acquire()
        result = await fetcher.fetch(url, headers=HEADERS)
    return result


def job_id(url: str) -> str:
    """Extract a numeric posting ID, using ``""`` when the URL has none."""
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else ""
