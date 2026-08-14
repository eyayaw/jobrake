"""The guest API's shared pieces: URLs, headers, pacing, posting ids."""

from __future__ import annotations

import asyncio

from jobrake.fetchkit import ErrorCategory, Fetcher, FetchResult, TokenBucket

BASE_URL = "https://www.linkedin.com"
SEARCH_URL = f"{BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = f"{BASE_URL}/jobs-guest/jobs/api/jobPosting"

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

# The server budget is not uniform: search pages 429 under a 4-burst +
# 2.25s cadence (the sixth request, deterministically), while a steady 3s
# never does. A longer-horizon limit still yields sporadic 429s on 100+
# request runs; the retry in paced_fetch absorbs those. Module-level on
# purpose: the budget is per IP, so one bucket per process, shared across
# all search calls.
LIMITER = TokenBucket(capacity=2, refill_interval=3.0)

RETRY_DELAY = 10.0  # seconds before retrying a 429; still 429 at +5s, clear by ~10s


async def paced_fetch(fetcher: Fetcher, url: str) -> FetchResult:
    """
    Take a token, fetch, and retry once after a 429.

    A 429 despite our pacing means someone else on this IP is spending the
    server's bucket; it refills within seconds, so one retry usually lands.
    A still-rate-limited result is returned as-is—give-up decisions stay
    with the caller.
    """
    await LIMITER.acquire()
    result = await fetcher.fetch(url, headers=HEADERS)
    if result.error and result.error.category is ErrorCategory.RATE_LIMITED:
        await asyncio.sleep(RETRY_DELAY)
        await LIMITER.acquire()
        result = await fetcher.fetch(url, headers=HEADERS)
    return result


def job_id(url: str) -> str:
    """Numeric posting id from a ``/jobs/view/<sluggified-title>-<id>`` URL; ``""`` when absent."""
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tail = slug.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else ""
