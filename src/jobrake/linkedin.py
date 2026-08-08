"""LinkedIn via the guest search API (HTML job cards, no login)."""

from __future__ import annotations

import asyncio
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobrake.core import html_text, make_job
from jobrake.constants import JobrakeConstants as JBC

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

PAGE_DELAY = 3.0  # seconds between search pages; measured safe sustained pace
MAX_START = 1000  # the guest API stops serving past this offset


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
    Description text from a public job page; ``""`` when the markup is absent.

    LinkedIn nondeterministically serves a signup page (interstitial) instead of the job page.
    """
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in c)
    return html_text(div.decode_contents()) if div else ""


async def search(
    fetcher,
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

    The endpoint has a small burst bucket (~5 requests) that refills within
    seconds, so pages are fetched with a delay between requests. A 429 ends
    the search with whatever was collected—the fetch layer reports it as a
    RATE_LIMITED error rather than raising.
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
        result = await fetcher.fetch(f"{SEARCH_URL}?{query}", headers=HEADERS)
        if not result.ok:
            break
        page = [j for j in parse_cards(result.text) if j["url"] not in seen]
        if not page:
            break
        seen.update(j["url"] for j in page)
        jobs.extend(page)
        start += len(page)
        if len(jobs) < results_wanted:
            await asyncio.sleep(PAGE_DELAY)

    jobs = jobs[:results_wanted]
    if fetch_description:
        for job in jobs:
            result = await fetcher.fetch(job["url"], headers=HEADERS)
            if result.ok and "linkedin.com/signup" not in result.url:
                job["description"] = parse_description(result.text)
            await asyncio.sleep(PAGE_DELAY)
    return jobs
