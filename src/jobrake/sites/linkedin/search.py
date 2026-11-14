"""LinkedIn guest-search parsing and pagination."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated
from urllib.parse import urlencode

lazy from bs4 import BeautifulSoup

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, make_job
from jobrake.sites.responses import collect
from jobrake.utils import checked

from .client import SEARCH_URL, job_id, numeric, on_linkedin, paced_fetch
from .pages import fetch_pages

logger = logging.getLogger(__name__)

MAX_START = 1000  # the guest API stops serving past this offset
KM_PER_MILE = 1.609344


def _parse_page(html: str) -> tuple[list[JobDict], int]:
    """Parse card summaries, and count every card LinkedIn served, parsable or not."""
    # Search cards contain only summary fields. fetch_pages() reads the
    # detail fields from each posting page.
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="base-search-card")
    jobs = []
    for card in cards:
        link = card.find("a", class_="base-card__full-link")
        if link is None or not link.get("href"):
            continue
        url = str(link["href"]).split("?")[0]
        posting_id = job_id(url)
        # details=True requests this address, so it must be LinkedIn's.
        if not (posting_id and on_linkedin(url)):
            continue

        title_tag = card.find("span", class_="sr-only")
        company_tag = card.find("h4", class_="base-search-card__subtitle")
        location_tag = card.find("span", class_="job-search-card__location")
        time_tag = card.find("time")

        jobs.append(
            make_job(
                id=posting_id,
                title=title_tag.get_text(strip=True) if title_tag else None,
                company=company_tag.get_text(strip=True) if company_tag else None,
                url=url,
                locations=[{"name": location_tag.get_text(strip=True)}] if location_tag else [],
                date=time_tag.get("datetime") if time_tag else None,
                site="linkedin",
            )
        )
    return jobs, len(cards)


async def _pages(
    fetcher: Fetcher, params: dict[str, object]
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """
    Yield each page's cards until an empty page, or until ``MAX_START``, which warns.

    Raises:
        Stopped: A page request failed after its retries.
    """
    start = 0
    while start < MAX_START:
        page = {k: v for k, v in (params | {"start": start}).items() if v is not None}
        result = await paced_fetch(fetcher, f"{SEARCH_URL}?{urlencode(page)}")
        if result.error:
            raise Stopped(f"linkedin request failed: {result.error}")
        cards, raw = _parse_page(result.text)
        if not raw and start == 0 and params["geoId"]:
            logger.warning("linkedin returned no postings for geoId=%s", params["geoId"])
        elif not raw and start == 0:
            # An unresolvable location and a genuine no-results page both return an
            # empty 200. The guest geocoder often needs a region and country. "Berlin"
            # works, while bare "Amsterdam" does not.
            logger.warning(
                "linkedin returned no postings for location=%r. "
                "A location without its region and country may not resolve; try "
                "'Amsterdam, North Holland, Netherlands'",
                params["location"],
            )
        if not raw:
            return
        yield cards, MAX_START
        # Offsets can overlap, and some cards cannot be parsed. Only a page
        # without cards marks the end. Advance by the server's own card count.
        start += raw
    logger.warning(
        "linkedin's guest search serves nothing past offset %d, fewer postings than requested. "
        "Narrow the search to reach more of its inventory",
        MAX_START,
    )


@checked
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    location: Annotated[str | None, "place, preferably with region and country"] = None,
    geoid: Annotated[str | None, "LinkedIn place ID, in place of a location"] = None,
    radius: Annotated[int | None, "search radius in kilometers"] = None,
    results: Annotated[int, "maximum number of postings"] = 10,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
    company_ids: Annotated[list[str] | None, "LinkedIn company IDs"] = None,
    easy_apply: Annotated[bool, "only postings with LinkedIn's Easy Apply form"] = False,
    early_applicant: Annotated[bool, "only postings with fewer than 10 applicants"] = False,
    details: Annotated[bool, "fetch each posting for its description and other details"] = False,
) -> list[JobDict]:
    """
    Search LinkedIn's login-free guest endpoint.

    ``geoid``, a place ID from :func:`places`, names the search area and makes ``location`` optional.
    Otherwise ``location`` is required and works best with a region and country.
    ``radius`` reaches LinkedIn's undocumented ``distance`` parameter as whole miles.
    A search by geoId ignores the radius for some places.
    ``query=""`` searches without keywords. A filter left at its default, or given ``[]``, applies no restriction.
    Filters combine and travel with every page.
    ``details`` hydrates posting pages, reusing cached copies.

    Search requests share the process-wide fabric pacing. The guest endpoint
    serves about ten cards per page and stops at offset ``MAX_START``,
    limiting one search to roughly 1,000 cards. Results retain guest-search
    order and stop at ``results``.

    Raises:
        Stopped: A request failed after its retries, or a posting's details
            could not be fetched. ``partial`` holds the postings collected,
            with the details fetched so far.
        ValueError: The location is missing or blank, or the geoid or a
            company ID uses characters other than digits 0-9.
    """
    if geoid is None and (location is None or not location.strip()):
        raise ValueError(
            "location is required without a geoid. Try 'Amsterdam, North Holland, Netherlands'"
        )
    if geoid is not None and not numeric(geoid):
        raise ValueError(
            f"geoid {geoid!r} must use digits 0-9, such as '102011674'. "
            "Find IDs with 'jobrake linkedin places NAME'"
        )
    for company in company_ids or []:
        if not numeric(company):
            raise ValueError(
                f"company ID {company!r} must use digits 0-9, such as '1173'. "
                "Find IDs with 'jobrake linkedin companies NAME'"
            )
    if location:
        logger.info("searching linkedin for %r in %r", query, location)
    else:
        logger.info("searching linkedin for %r with geoId %s", query, geoid)
    params: dict[str, object] = {
        "keywords": query,
        "location": location or None,
        # A geoId outranks LinkedIn's own geocoding of the location text.
        "geoId": geoid,
        # LinkedIn names its radius parameter ``distance`` and reads it in miles.
        "distance": None if radius is None else round(radius / KM_PER_MILE),
        "f_TPR": f"r{max_age_hours * 3600}" if max_age_hours else None,
        # Newest first. The guest endpoint ignored it in October 2026 and
        # ranked by relevance.
        "sortBy": "DD",
        "f_C": ",".join(company_ids) if company_ids else None,
        "f_AL": "true" if easy_apply else None,
        "f_EA": "true" if early_applicant else None,
    }
    jobs = await collect("linkedin", _pages(fetcher, params), results)
    if details:
        found = await fetch_pages(fetcher, {job["id"]: dict(job) for job in jobs})
        # A posting that is gone, or failed, keeps its card.
        jobs = [found.get(job["id"]) or job for job in jobs]
        if missing := sum(job["id"] not in found for job in jobs):
            raise Stopped(
                f"linkedin could not fetch the details of {missing} of {len(jobs)} postings. "
                "A rerun retries them",
                partial=jobs,
            )
    return jobs
