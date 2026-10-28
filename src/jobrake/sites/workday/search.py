"""Workday career site requests and parsing."""

import functools
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from gettext import ngettext
from typing import Annotated, Any
from urllib.parse import urlsplit

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Place, Stopped, employment_type, make_job
from jobrake.sites.responses import json_page, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, html_text

logger = logging.getLogger(__name__)

# A community report says the search returns no cards for a larger limit.
PAGE_SIZE = 20
# Workday reports at most this many postings for one search, however many the site lists.
MAX_TOTAL = 2000

EXAMPLE_BOARD = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
_HOST = re.compile(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com")
_LOCALE = re.compile(r"[a-z]{2}-[A-Z]{2}")
_POSTED = re.compile(r"Posted (?:Today|(Yesterday)|(\d{1,4}) Days Ago)")
_REQUISITION = re.compile(r"/.*_([^/_]+)")
_LOCATION_COUNT = re.compile(r"\d+ Locations")


def _career_site(board: str) -> tuple[str, str, str]:
    """
    Split a career site URL into its host, tenant, and site name.

    A locale segment such as ``en-US`` before the site name is skipped, and
    anything after the site name is ignored.

    Raises:
        ValueError: ``board`` is not a ``myworkdayjobs.com`` career site URL,
            names a port, or is an API address under ``/wday/``.
    """
    parts = urlsplit(board.strip())
    host = parts.hostname or ""
    names = [name for name in parts.path.split("/") if name]
    if names and _LOCALE.fullmatch(names[0]):
        names = names[1:]
    # The requests go to the host alone, so an authority with more, such as a port, is refused.
    bare = parts.netloc.lower() == host and _HOST.fullmatch(host)
    if parts.scheme not in {"http", "https"} or not bare or not names or names[0] == "wday":
        raise ValueError(
            f"board {board!r} is not a Workday career site URL. Pass the address a visitor "
            f"sees, https://<tenant>.wd<n>.myworkdayjobs.com/<site>, such as {EXAMPLE_BOARD}"
        )
    return host, host.partition(".")[0], names[0]


def _today() -> date:
    return datetime.now(UTC).date()


def _posted_date(posted_on: object) -> str | None:
    """Date a card's ``postedOn``, such as ``Posted 3 Days Ago``, counting back from today in UTC."""
    match = _POSTED.fullmatch(posted_on) if isinstance(posted_on, str) else None
    if match is None:
        return None
    yesterday, days = match.groups()
    age = int(days) if days else 1 if yesterday else 0
    return (_today() - timedelta(days=age)).isoformat()


def _parse_card(card: dict[str, Any], site_url: str, tenant: str) -> JobDict:
    """
    Build a record from one entry of a search page's ``jobPostings`` list.

    The ID joins the tenant and the requisition ID that ends ``externalPath``,
    as in ``nvidia:JR1996377``, because requisition IDs are unique only
    within a tenant.

    Raises:
        TypeError: The card lacks an ``externalPath`` ending in a requisition ID.
        AttributeError: The card is not an object.
    """
    path = card.get("externalPath")
    if not isinstance(path, str) or not (match := _REQUISITION.fullmatch(path)):
        raise TypeError(f"externalPath {path!r} does not end in a requisition ID")
    location = card.get("locationsText")
    # A posting with several locations shows only their count.
    if isinstance(location, str) and _LOCATION_COUNT.fullmatch(location):
        location = None
    return make_job(
        site="workday",
        id=f"{tenant}:{match.group(1)}",
        url=site_url + path,
        title=card.get("title"),
        locations=[{"name": location}],
        date=_posted_date(card.get("postedOn")),
    )


async def _collect_cards(
    fetcher: Fetcher,
    *,
    board: str,
    api_url: str,
    site_url: str,
    tenant: str,
    query: str,
    results: int,
) -> tuple[list[JobDict], bool]:
    """
    Return the unique cards, paging until ``results`` cards, the first page's total, or an empty page.

    The flag tells whether the paging reached a total at ``MAX_TOTAL``, the
    most Workday reports.

    Raises:
        Stopped: A page request failed, Workday has no such site, it sent
            an unreadable response, or an empty page came before the first
            page's total. ``partial`` holds the cards collected before it.
    """
    jobs: list[JobDict] = []
    seen: set[str] = set()
    offset, total = 0, None
    parse = functools.partial(_parse_card, site_url=site_url, tenant=tenant)
    unknown = (
        f"workday has no career site at {board!r}. Copy the URL of the employer's "
        f"job search page, such as {EXAMPLE_BOARD}"
    )
    while len(jobs) < results and (total is None or offset < total):
        limit = min(PAGE_SIZE, results - len(jobs))
        body = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": query}
        result = await fetcher.fetch(f"{api_url}/jobs", json=body)
        cards, page_total = read_json(
            result,
            lambda page: json_page(page, "jobPostings", "total"),
            site="workday",
            board=site_url,
            # A site that served a page exists, so a later 404 is a failed request.
            unknown=unknown if total is None else None,
            partial=jobs,
        )
        # Later pages are reported to say 0, so the first page's total stands.
        total = page_total if total is None else total
        if not cards:
            if offset < total:
                raise Stopped(
                    f"workday site {site_url} reported {total} postings but sent an empty page "
                    f"after {offset}, so the result may be incomplete. Postings may have closed "
                    "during the search. A rerun reads the current list",
                    partial=jobs,
                )
            break
        offset += len(cards)
        for job in parse_postings(cards, parse, site="workday"):
            if job["id"] not in seen:
                seen.add(job["id"])
                jobs.append(job)
    return jobs, total is not None and offset >= total >= MAX_TOTAL


async def _detail_fields(
    fetcher: Fetcher, url: str, posting: str, card_places: list[Place]
) -> dict[str, Any] | None:
    """
    Fetch one posting's detail fields, or ``{}`` when Workday reports it gone.

    Returns None when the request failed or the response is unreadable, which it logs.
    """
    result = await fetcher.fetch(url)
    if result.status == 404:
        return {}
    if result.error:
        logger.warning("skipping the details of %s: %s. A rerun retries it", posting, result.error)
        return None
    # ValueError covers JSONDecodeError and an integer longer than Python reads.
    try:
        info = json.loads(result.text)["jobPostingInfo"]
        country = as_dict(as_dict(info.get("jobRequisitionLocation")).get("country"))
        primary = (as_str(info.get("location")) or "").strip()
        others = info.get("additionalLocations")
        # The requisition's country is the primary location's. Without one, the card's place leads.
        locations = [
            *(
                [{"name": primary, "country_code": country.get("alpha2Code")}]
                if primary
                else card_places
            ),
            *({"name": name} for name in (others if isinstance(others, list) else [])),
        ]
        return {
            "description": html_text(as_str(info.get("jobDescription")) or ""),
            "posted_at": as_str(info.get("startDate")),
            "employment_type": employment_type(as_str(info.get("timeType"))),
            "locations": locations,
        }
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        logger.warning(
            "skipping the details of %s, which this version cannot read: %r", posting, error
        )
        return None


async def _fill_details(
    fetcher: Fetcher, jobs: list[JobDict], *, api_url: str, site_url: str
) -> list[JobDict]:
    """
    Hydrate each card with its posting's detail fields, one request after another.

    A posting Workday reports gone keeps its card. A posting with a start
    date takes its ``date`` from it, because the card's date counts from
    today in UTC and can be a day past Workday's own.

    Raises:
        Stopped: A posting's details could not be fetched. ``partial`` holds
            every posting, with the details fetched so far.
    """
    filled: list[JobDict] = []
    missing = 0
    for position, job in enumerate(jobs, start=1):
        # The CLI renders progress-flagged records as one self-updating stderr line.
        logger.info(
            "workday details %d/%d", position, len(jobs), extra={"progress": (position, len(jobs))}
        )
        fields = await _detail_fields(
            fetcher, api_url + job["url"].removeprefix(site_url), job["url"], job["locations"]
        )
        missing += fields is None
        # Without a card date, make_job falls back to posted_at.
        card = {**job, "date": None} if fields and fields["posted_at"] else job
        filled.append(make_job(**{**card, **(fields or {})}))
    if missing:
        raise Stopped(
            f"workday could not fetch the details of {missing} of {len(jobs)} postings. "
            "A rerun retries them",
            partial=filled,
        )
    return filled


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, f"employer's career site URL, e.g., {EXAMPLE_BOARD}"],
    query: Annotated[str, "job title or keywords"] = "",
    results: Annotated[int, "maximum number of postings"] = 20,
    details: Annotated[bool, "fetch posting pages for descriptions and other details"] = False,
) -> list[JobDict]:
    """
    Search one employer's Workday career site.

    ``board`` is the address of the site's job search page as a visitor
    copies it, such as ``https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite``.
    ``query=""`` lists every posting. Results keep Workday's order and stop
    at ``results``. Workday reports at most ``MAX_TOTAL`` postings per
    search, and a search that reaches that cap short of ``results`` warns.
    A card carries no description, so ``details`` hydrates each posting
    with one more request. Requests are neither paced nor retried. A
    malformed card costs only that posting. The caller owns ``fetcher``.

    Raises:
        Stopped: A request failed, Workday has no such career site, it
            sent an unreadable response, or an empty page came before the
            reported total. ``partial`` holds the postings collected before it. With ``details``, a posting's details could
            not be fetched, and ``partial`` holds every posting, with the
            details fetched so far.
        ValueError: ``board`` is not a Workday career site URL.
    """
    host, tenant, career_site = _career_site(board)
    site_url = f"https://{host}/{career_site}"
    # The API serves a site and its postings under their public paths.
    api_url = f"https://{host}/wday/cxs/{tenant}/{career_site}"
    logger.info("searching workday site %s for %r", site_url, query)
    jobs, capped = await _collect_cards(
        fetcher,
        board=board,
        api_url=api_url,
        site_url=site_url,
        tenant=tenant,
        query=query,
        results=results,
    )
    if capped and len(jobs) < results:
        logger.warning(
            "workday reports at most %d postings per search; returning %d of the %d "
            "requested. Narrow the search with a query to reach the rest",
            MAX_TOTAL,
            len(jobs),
            results,
        )
    jobs = jobs[:results]
    logger.info(
        "workday search finished with %s",
        ngettext("%d posting", "%d postings", len(jobs)) % len(jobs),
    )
    if details:
        return await _fill_details(fetcher, jobs, api_url=api_url, site_url=site_url)
    return jobs
