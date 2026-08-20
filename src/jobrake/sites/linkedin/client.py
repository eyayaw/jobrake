"""Shared guest API URLs, headers, pacing, posting IDs, and cache."""

import asyncio

from jobrake.cache import PostingCache
from jobrake.fetchkit import ErrorCategory, Fetcher, FetchResult, TokenBucket

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

# A 429 remains after five seconds and clears around ten.
RETRY_DELAY = 10.0

# One cache per process, lazy, so no file is touched until the first cached fetch.
CACHE = PostingCache()


async def paced_fetch(fetcher: Fetcher, url: str) -> FetchResult:
    """
    Take a token, fetch, and retry once after a 429.

    A 429 despite this pacing indicates other traffic from the same IP. The
    server bucket usually refills within seconds. The caller receives a second
    rate-limited result unchanged and decides whether to stop.
    """
    await LIMITER.acquire()
    result = await fetcher.fetch(url, headers=HEADERS)
    if result.error and result.error.category is ErrorCategory.RATE_LIMITED:
        await asyncio.sleep(RETRY_DELAY)
        await LIMITER.acquire()
        result = await fetcher.fetch(url, headers=HEADERS)
    return result


def job_id(url: str) -> str:
    """Return the numeric ID in a job URL, or ``""`` when it has no numeric suffix."""
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else ""
