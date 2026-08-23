"""Shared guest API URLs, headers, pacing, posting IDs, and cache."""

import asyncio

from jobrake.cache import PostingCache
from jobrake.fetchkit import ErrorCategory, Fetcher, FetchResult, TokenBucket


def rate_limited(result: FetchResult) -> bool:
    """Check for a rate-limited error."""
    return result.error is not None and result.error.category is ErrorCategory.RATE_LIMITED


BASE_URL = "https://www.linkedin.com"
SEARCH_URL = f"{BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"

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

# A 429 remains after five seconds and clears around ten. A seconds-form
# Retry-After takes precedence. jobrake will not wait longer than a minute:
# past that, the 429 goes back to the caller unretried.
RETRY_DELAY = 10.0
MAX_RETRY_DELAY = 60.0


def _retry_delay(result: FetchResult) -> float | None:
    """Choose a retry delay within the local wait limit."""
    value = result.headers.get("retry-after", "")
    # Unicode digits such as "²" pass isdigit but not float().
    if not (value.isascii() and value.isdigit()):
        return RETRY_DELAY
    seconds = float(value)
    return seconds if seconds <= MAX_RETRY_DELAY else None


# One cache per process, lazy, so no file is touched until the first cached fetch.
CACHE = PostingCache()


async def paced_fetch(fetcher: Fetcher, url: str) -> FetchResult:
    """
    Pace one LinkedIn request and retry a 429 within the wait limit.

    A seconds-form ``Retry-After`` sets the wait. A missing or unreadable value
    uses ``RETRY_DELAY``. A delay above ``MAX_RETRY_DELAY`` skips the retry. A
    persistent 429 is returned for the caller to decide whether the larger
    operation should stop. Both attempts use the supplied transport, which
    remains open afterward.
    """
    await LIMITER.acquire()
    result = await fetcher.fetch(url, headers=HEADERS)
    if rate_limited(result):
        delay = _retry_delay(result)
        if delay is None:
            return result
        await asyncio.sleep(delay)
        await LIMITER.acquire()
        result = await fetcher.fetch(url, headers=HEADERS)
    return result


def job_id(url: str) -> str:
    """Extract a numeric posting ID, using ``""`` when the URL has none."""
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else ""
