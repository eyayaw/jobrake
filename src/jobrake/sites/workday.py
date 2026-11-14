"""Search an employer's Workday career site through the JSON API behind it."""

import functools
import json
import logging
import re
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, employment_type, make_job
from jobrake.sites.postings import fetch_postings, fill_details
from jobrake.sites.responses import collect, json_page, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, html_text

logger = logging.getLogger(__name__)

# Workday answers a limit above 20 with HTTP 400 (measured 2026-11-14 on two
# career sites in different Workday data centers).
PAGE_SIZE = 20
# Workday reports at most this many postings for one search, however many the site lists.
MAX_TOTAL = 2000

EXAMPLE_BOARD = "https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External"
_HOST = re.compile(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com")
_LOCALE = re.compile(r"[a-z]{2}-[A-Z]{2}")
_POSTED = re.compile(r"Posted (?:Today|(Yesterday)|(\d{1,4}) Days Ago)")
# The requisition ID follows the first underscore of the path's last segment,
# because title slugs join words with hyphens, so an ID such as JR_2024_00123
# stays whole. An ID holds a digit, and a title word such as Scientist in
# /job/Remote/Data_Scientist does not.
_REQUISITION = re.compile(r"/(?:[^/]+/)*[^/_]*_([^/]*\d[^/]*)")
_LOCATION_COUNT = re.compile(r"\d+ Locations")


def _career_site(board: str) -> tuple[str, str, str, str]:
    """
    Split a career site URL into its tenant, site URL, API URL, and the path after the site name.

    A locale segment such as ``en-US`` before the site name is skipped. The
    API serves a site and its postings under their public paths.

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
    tenant, career_site, rest = host.partition(".")[0], names[0], "/".join(names[1:])
    return (
        tenant,
        f"https://{host}/{career_site}",
        f"https://{host}/wday/cxs/{tenant}/{career_site}",
        f"/{rest}" if rest else "",
    )


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
    as in ``zillow:P751481-1``, because requisition IDs are unique only
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


async def _pages(
    fetcher: Fetcher, board: str, query: str, limit: int
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """
    Yield each page's cards with the first page's total until the pages reach it.

    Reading every page of a total of ``MAX_TOTAL`` logs a warning, because
    Workday reports no more than that for one search.

    Raises:
        Stopped: A request failed, Workday has no such site, it sent an
            unreadable response, or an empty page came before the total.
    """
    tenant, site_url, api_url, _ = _career_site(board)
    parse = functools.partial(_parse_card, site_url=site_url, tenant=tenant)
    unknown = (
        f"workday has no career site at {board!r}. Copy the URL of the employer's "
        f"job search page, such as {EXAMPLE_BOARD}"
    )
    offset, total = 0, None
    while total is None or offset < total:
        body = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": query}
        result = await fetcher.fetch(f"{api_url}/jobs", json=body)
        cards, page_total = read_json(
            result,
            lambda page: json_page(page, "jobPostings", "total"),
            site="workday",
            board=site_url,
            # A site that served a page exists, so a later 404 is a failed request.
            unknown=unknown if total is None else None,
        )
        # One of the two sites measured at PAGE_SIZE reported total 0 on every
        # page after the first, so the first page's total stands.
        total = page_total if total is None else total
        if not cards and offset < total:
            raise Stopped(
                f"workday site {site_url} reported {total} postings but sent an empty page "
                f"after {offset}, so the result may be incomplete. Postings may have closed "
                "during the search. A rerun reads the current list"
            )
        if not cards:
            break
        offset += len(cards)
        yield parse_postings(cards, parse, site="workday"), total
    if total >= MAX_TOTAL:
        logger.warning(
            "workday reports at most %d postings per search, fewer than requested. "
            "Narrow the search with a query to reach the rest",
            MAX_TOTAL,
        )


def _withdrawn(text: str) -> bool:
    # career-ops reads a 403 whose body names error S22 as a withdrawn posting
    # (liveness-api.mjs in https://github.com/career-ops-hq/career-ops, checked
    # 2026-11-14). No such answer was seen here. Any other 403 is a block,
    # which a rerun may pass.
    try:
        return as_dict(json.loads(text)).get("errorCode") == "S22"
    except ValueError:
        return False


def _parse_details(payload: dict[str, Any], card: JobDict) -> dict[str, Any]:
    """
    Return the detail fields of a card's posting from its ``jobPostingInfo``.

    A posting with a start date takes its ``date`` from it, because the
    card's date counts from today in UTC and can be a day past Workday's own.
    """
    info = payload["jobPostingInfo"]
    country = as_dict(as_dict(info.get("jobRequisitionLocation")).get("country"))
    primary = (as_str(info.get("location")) or "").strip()
    others = info.get("additionalLocations")
    # The requisition's country is the primary location's. Without one, the card's place leads.
    locations = [
        *(
            [{"name": primary, "country_code": country.get("alpha2Code")}]
            if primary
            else card["locations"]
        ),
        *({"name": name} for name in (others if isinstance(others, list) else [])),
    ]
    start = as_str(info.get("startDate"))
    return {
        "title": as_str(info.get("title")),
        "description": html_text(as_str(info.get("jobDescription")) or ""),
        "date": start,
        "posted_at": start,
        "employment_type": employment_type(as_str(info.get("timeType"))),
        "locations": locations,
    }


async def _detail_fields(fetcher: Fetcher, card: JobDict) -> dict[str, Any] | None:
    """
    Fetch the detail fields of a card's posting, or None when Workday reports it gone or withdrawn.

    Raises:
        Stopped: The request failed, or the response is unreadable.
    """
    _, _, api_url, path = _career_site(card["url"])
    result = await fetcher.fetch(api_url + path)
    if result.status == 404 or (result.status == 403 and _withdrawn(result.text)):
        return None
    return read_json(result, functools.partial(_parse_details, card=card), site="workday")


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, f"employer's career site URL, e.g., {EXAMPLE_BOARD}"],
    query: Annotated[str, "job title or keywords"] = "",
    results: Annotated[int, "maximum number of postings"] = 20,
    details: Annotated[bool, "fetch each posting for its description and other details"] = False,
) -> list[JobDict]:
    """
    Search one employer's Workday career site.

    ``board`` is the address of the site's job search page as a visitor
    copies it, such as ``https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External``.
    ``query=""`` lists every posting. Results keep Workday's order and stop
    at ``results``. Workday reports at most ``MAX_TOTAL`` postings per
    search, and a search that reaches that cap short of ``results`` warns.
    A card carries no description, so ``details`` hydrates each posting
    with one more request. Requests are neither paced nor retried.

    Raises:
        Stopped: A request failed, Workday has no such career site, it
            sent an unreadable response, or an empty page came before the
            reported total. ``partial`` holds the postings collected before
            it. With ``details``, a posting's details could not be fetched,
            and ``partial`` holds every posting, with the details fetched so
            far.
        ValueError: ``board`` is not a Workday career site URL.
    """
    # Reading the board here rejects a bad one before the first request.
    logger.info("searching workday site %s for %r", _career_site(board)[1], query)
    pages = _pages(fetcher, board, query, min(PAGE_SIZE, results))
    jobs = await collect("workday", pages, results)
    if details:
        return await fill_details("workday", jobs, functools.partial(_detail_fields, fetcher))
    return jobs


def _card(reference: str) -> JobDict:
    """
    Read a Workday posting URL as the card it names.

    Raises:
        ValueError: The reference is not a posting URL on a Workday career site.
    """
    try:
        tenant, site_url, _, path = _career_site(reference)
    except ValueError:
        match = None
    else:
        path = path.rstrip("/")
        match = _REQUISITION.fullmatch(path) if path.startswith("/job/") else None
    if match is None:
        raise ValueError(
            f"{reference!r} is not a Workday posting URL. Pass a record's url, such as "
            f"{EXAMPLE_BOARD}/job/Remote-USA/Applied-Scientist_P751481-1"
        ) from None
    return make_job(site="workday", id=f"{tenant}:{match.group(1)}", url=site_url + path)


@checked
async def postings(
    fetcher: Fetcher,
    references: Annotated[list[str], "Workday posting URLs"],
) -> dict[str, JobDict | None]:
    """
    Fetch known Workday postings by URL, one request each.

    The result is keyed by the references given. A reference is a record's
    ``url``, the posting's address on its career site, and references naming
    one posting share one request. A reference maps to ``None`` when Workday
    reports its posting gone. After a failed request or an unreadable
    response it has no key, and a warning names it.

    Raises:
        ValueError: A reference is not a Workday posting URL. Nothing is
            fetched in that case.
    """
    return await fetch_postings(
        "workday", references, _card, functools.partial(_detail_fields, fetcher)
    )


__all__ = ["postings", "search"]
