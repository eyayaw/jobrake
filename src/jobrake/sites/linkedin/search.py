"""LinkedIn guest-search parsing and pagination."""

import logging
from gettext import ngettext
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobrake import defaults
from jobrake.fetchkit import Fetcher
from jobrake.models import make_job
from jobrake.utils import check_distance, check_hours_old, check_results_wanted

from .client import SEARCH_URL, job_id, paced_fetch
from .postings import fetch_postings

logger = logging.getLogger(__name__)

MAX_START = 1000  # the guest API stops serving past this offset


def parse_cards(html: str) -> list[dict]:
    """
    Parse summaries in card order.

    Cards without a URL or numeric posting ID are omitted.
    """
    return _parse_page(html)[0]


def _parse_page(html: str) -> tuple[list[dict], int]:
    """Parse job summaries while retaining the provider's raw card count."""
    # Search cards contain only summary fields. fetch_postings() reads the
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
        if not posting_id:
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
                location=location_tag.get_text(strip=True) if location_tag else None,
                date=time_tag.get("datetime") if time_tag else None,
                site="linkedin",
            )
        )
    return jobs, len(cards)


async def search(
    fetcher: Fetcher,
    *,
    search_term: str,
    location: str,
    country: str | None = None,
    distance: int | None = defaults.RADIUS,
    results_wanted: int = defaults.RESULTS_WANTED,
    hours_old: int | None = defaults.HOURS_OLD,
    detail: bool = defaults.DETAIL,
    cache: bool = True,
) -> list[dict]:
    """
    Search LinkedIn's login-free guest endpoint.

    ``location`` must be nonblank and works best with a region and country.
    Distance is sent unchanged, and ``None`` omits it. When ``hours_old`` is
    ``None``, LinkedIn omits the ``f_TPR`` filter. ``country`` is accepted for
    the common provider call and ignored. ``detail`` hydrates posting pages,
    with ``cache`` controlling their reuse. The caller owns ``fetcher``.

    Search requests share the process-wide limiter. A persistent 429 ends the
    search with the jobs already collected. The guest endpoint serves about
    ten cards per page and stops at offset ``MAX_START``, limiting one search
    to roughly 1,000 cards. Results retain guest-search order and stop at
    ``results_wanted``.

    Raises:
        ValueError: Location is blank or a numeric search argument is outside its valid range.
    """
    if not location.strip():
        raise ValueError(
            f"location {location!r} is blank. Try 'Amsterdam, North Holland, Netherlands'"
        )
    check_results_wanted(results_wanted)
    check_distance(distance)
    check_hours_old(hours_old)
    logger.info("searching linkedin for %r in %r", search_term, location)
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
        if result.error:
            logger.warning(
                "linkedin search stopped by %s; keeping the %s already collected",
                result.error.message,
                ngettext("%d job", "%d jobs", len(jobs)) % len(jobs),
            )
            break
        cards, raw = _parse_page(result.text)
        if not raw:
            if start == 0:
                # An unresolvable location and a genuine no-results page both
                # return an empty 200. The guest geocoder often needs a region
                # and country. "Berlin" works, while bare "Amsterdam" does not.
                logger.warning(
                    "linkedin returned no jobs for location=%r. "
                    "A location without its region and country may not resolve; try "
                    "'Amsterdam, North Holland, Netherlands'",
                    location,
                )
            break
        for job in cards:
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            jobs.append(job)
        # Offsets can overlap, and some cards cannot be parsed. Only a page
        # without cards marks the end. Advance by the server's own card count.
        start += raw

    if len(jobs) < results_wanted and start >= MAX_START:
        logger.warning(
            "linkedin's guest search serves nothing past offset %d; returning "
            "%d of the %d jobs requested. Narrow the search to reach more of "
            "its inventory",
            MAX_START,
            len(jobs),
            results_wanted,
        )
    jobs = jobs[:results_wanted]
    logger.info(
        "linkedin search finished with %s", ngettext("%d job", "%d jobs", len(jobs)) % len(jobs)
    )
    if detail:
        postings = await fetch_postings(fetcher, (job["url"] for job in jobs), cache=cache)
        # Keep summary fields when a posting disappears or fails during hydration.
        jobs = [make_job(**{**job, **(postings.get(job["url"]) or {})}) for job in jobs]
    return jobs
