"""LinkedIn via the guest search API (HTML job cards, no login)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobrake.constants import JobrakeConstants as JBC
from jobrake.core import html_text, make_job
from jobrake.fetchkit import ErrorCategory, Fetcher, FetchResult, TokenBucket

logger = logging.getLogger(__name__)

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

MAX_START = 1000  # the guest API stops serving past this offset

# The server budget is not uniform: search pages 429 under a 4-burst +
# 2.25s cadence (the sixth request, deterministically), while a steady 3s
# never does. A longer-horizon limit still yields sporadic 429s on 100+
# request runs; the retry in _paced_fetch absorbs those. Module-level on
# purpose: the budget is per IP, so one bucket per process, shared across
# all search calls.
LIMITER = TokenBucket(capacity=2, refill_interval=3.0)

RETRY_DELAY = 10.0  # seconds before retrying a 429; still 429 at +5s, clear by ~10s


async def _paced_fetch(fetcher: Fetcher, url: str) -> FetchResult:
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


def parse_cards(html: str) -> list[dict]:
    """Job dicts (no description) from one guest search page."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.find_all("div", class_="base-search-card"):
        link = card.find("a", class_="base-card__full-link")
        if link is None or not link.get("href"):
            continue
        url = link["href"].split("?")[0]

        title_tag = card.find("span", class_="sr-only")
        company_tag = card.find("h4", class_="base-search-card__subtitle")
        location_tag = card.find("span", class_="job-search-card__location")
        time_tag = card.find("time")

        jobs.append(
            make_job(
                id=job_id(url),
                title=title_tag.get_text(strip=True) if title_tag else "",
                company=company_tag.get_text(strip=True) if company_tag else "",
                url=url,
                location=location_tag.get_text(strip=True) if location_tag else "",
                date=(time_tag.get("datetime") or "") if time_tag else "",
                site="linkedin",
            )
        )
    return jobs


def parse_description(html: str) -> str:
    """
    Description text from a job page or guest fragment; ``""`` when the markup is absent.

    LinkedIn nondeterministically serves a signup page (interstitial) instead of the job page.
    """
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in c)
    return html_text(div.decode_contents()) if div else ""


async def fetch_descriptions(fetcher: Fetcher, ids: Iterable[str]) -> dict[str, str | None]:
    """
    Full description per posting id, via the guest jobPosting fragment.

    The fragment (~30KB) carries the same description markup as the full
    job page (~300KB) at the same one-token price. Duplicate and empty ids
    are skipped. Three outcomes per id: description text (hydrated), ``None``
    (the posting is gone—404/410—stop asking), or absent from the result
    (transient: rate-limited past the retry, network failure, or markup
    absent) and safe to try again later. Never raises.
    """
    descriptions: dict[str, str | None] = {}
    for posting_id in dict.fromkeys(i for i in ids if i):
        result = await _paced_fetch(fetcher, f"{DETAIL_URL}/{posting_id}")
        if result.ok:
            if description := parse_description(result.text):
                descriptions[posting_id] = description
        elif result.error.http_status in (404, 410):
            descriptions[posting_id] = None
    return descriptions


async def search(
    fetcher: Fetcher,
    *,
    search_term: str,
    location: str,
    distance: int | None = JBC.radius,
    results_wanted: int = JBC.results_wanted,
    hours_old: int | None = JBC.hours_old,
    fetch_description: bool = JBC.fetch_description,
) -> list[dict]:
    """
    Paginate guest-search job cards into job dicts.

    Every request first takes a token from ``LIMITER``, so bursts ride the
    bucket and sustained fetching settles onto its refill rate. A 429 is
    retried once after ``RETRY_DELAY``; if it persists, the search ends with
    whatever was collected—the fetch layer reports it as a RATE_LIMITED
    error rather than raising.
    """
    jobs: list[dict] = []
    seen: set[str] = set()
    start = 0
    while len(jobs) < results_wanted and start < MAX_START:
        params = {
            "keywords": search_term,
            "location": location,
            "distance": distance,
            "start": start,
            "f_TPR": f"r{hours_old * 3600}" if hours_old else None,
        }
        query = urlencode({k: v for k, v in params.items() if v is not None})
        result = await _paced_fetch(fetcher, f"{SEARCH_URL}?{query}")
        if not result.ok:
            break
        page = [j for j in parse_cards(result.text) if j["url"] not in seen]
        if not page:
            if start == 0:
                # An unresolvable location yields an empty 200 identical to a
                # genuine no-results page; the guest geocoder wants qualified
                # names ("Berlin" works, bare "Amsterdam" does not).
                logger.warning(
                    "linkedin returned an empty first page for location=%r; "
                    "if results were expected, try a qualified location like "
                    "'Amsterdam, North Holland, Netherlands'",
                    location,
                )
            break
        seen.update(j["url"] for j in page)
        jobs.extend(page)
        start += len(page)

    jobs = jobs[:results_wanted]
    if fetch_description:
        descriptions = await fetch_descriptions(fetcher, (job["id"] for job in jobs))
        for job in jobs:
            job["description"] = descriptions.get(job["id"]) or job["description"]
    return jobs
