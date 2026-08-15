"""Paginating the guest search API."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobrake import defaults
from jobrake.fetchkit import Fetcher
from jobrake.models import make_job

from .client import SEARCH_URL, job_id, paced_fetch
from .postings import fetch_postings

logger = logging.getLogger(__name__)

MAX_START = 1000  # the guest API stops serving past this offset


def parse_cards(html: str) -> list[dict]:
    """Fields from the cards on one search page."""
    # The description lives on the posting's own page; see fetch_postings.
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.find_all("div", class_="base-search-card"):
        link = card.find("a", class_="base-card__full-link")
        if link is None or not link.get("href"):
            continue
        url = str(link["href"]).split("?")[0]

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
                date=str(time_tag.get("datetime") or "") if time_tag else "",
                site="linkedin",
            )
        )
    return jobs


async def search(
    fetcher: Fetcher,
    *,
    search_term: str,
    location: str,
    country: str | None = None,
    distance: int | None = defaults.RADIUS,
    results_wanted: int = defaults.RESULTS_WANTED,
    hours_old: int | None = defaults.HOURS_OLD,
    fetch_description: bool = defaults.FETCH_DESCRIPTION,
    cache: bool = True,
) -> list[dict]:
    """
    Paginate the guest search, extracting each posting's fields.

    ``country`` is accepted for signature uniformity across sites and ignored.

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
        result = await paced_fetch(fetcher, f"{SEARCH_URL}?{query}")
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
        logger.info("fetching posting details for %d jobs...", len(jobs))
        postings = await fetch_postings(fetcher, (job["url"] for job in jobs), cache=cache)
        # A posting gone or unreachable between search and hydration keeps its summary fields.
        jobs = [make_job(**{**job, **(postings.get(job["url"]) or {})}) for job in jobs]
    return jobs
