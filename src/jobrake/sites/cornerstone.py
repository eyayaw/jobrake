"""Search an employer's Cornerstone career site through its public search API."""

import functools
import itertools
import json
import logging
import re
from collections.abc import AsyncGenerator
from datetime import date
from typing import Annotated, Any, NamedTuple
from urllib.parse import parse_qs, urlencode

lazy from bs4 import BeautifulSoup

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, make_job
from jobrake.sites.responses import (
    collect,
    failure,
    json_page,
    offset_pages,
    read_html,
    read_json,
)
from jobrake.utils import (
    HOST_LABEL,
    as_dict,
    as_int,
    as_list,
    as_str,
    checked,
    on_domain,
    split_url,
)

logger = logging.getLogger(__name__)

# The API caps a page at 1,000 requisitions (measured 2026-11-24 on Henkel's board of 1,037).
PAGE_SIZE = 1000
EXAMPLE_BOARD = "https://worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup"

# A career site lives at https://<tenant>.csod.com/ux/ats/careersite/<id>/home?c=<corp>.
# Its HTML embeds csod.context with an anonymous bearer token, the board's culture, and the
# regional cloud API host (measured 2026-11-24: us.api.csod.com on World Bank Group and Project
# HOPE; eu-fra.api.csod.com on Henkel).
_HOST = re.compile(rf"({HOST_LABEL})\.csod\.com")
# The home page, or a requisition page on the same career site.
_PATH = re.compile(
    r"/ux/ats/careersite/0*([1-9][0-9]*)/home(?:/requisition/[0-9]+)?/?", re.IGNORECASE
)
_CONTEXT = re.compile(r"\bcsod\.context\s*=\s*")
# In Cornerstone's cultures 1 to 51 (measured 2026-11-24 on Henkel's board), a short date is three
# numbers with the year first or last. The separators vary: "/", ". ", right-to-left marks, or a
# trailing Bulgarian year mark. Thai years count in the Buddhist Era, as in 24/11/2569.
_NUMBERS = re.compile(r"[0-9]+")
_BUDDHIST_ERA = 543
# Regions whose .NET short date format puts month before day (M/d/yyyy).
_MONTH_FIRST_REGIONS = frozenset({"AS", "FM", "GU", "MH", "MP", "PH", "PR", "UM", "US", "VI"})


class _CareerSite(NamedTuple):
    tenant: str
    site_id: int
    board_url: str
    posting_prefix: str
    query_c: str


class _Context(NamedTuple):
    api_url: str
    token: str
    culture_id: int
    culture_name: str


def _career_site(board: str) -> _CareerSite:
    """
    Split a Cornerstone career site URL, or a requisition URL on it, into its tenant, ID, and URLs.

    The ``c`` parameter names the employer and defaults to the tenant, and ``lang`` carries over.

    Raises:
        ValueError: ``board`` is not a Cornerstone career site URL or carries a port or credentials.
    """
    parts = split_url(board)
    host = (parts.hostname or "").lower()
    # Requests go to the bare host, so an authority with credentials or a port is refused.
    if not (
        parts.scheme in {"http", "https"}
        and parts.netloc.lower() == host
        and (tenant := _HOST.fullmatch(host))
        and (path := _PATH.fullmatch(parts.path))
    ):
        raise ValueError(
            f"board {board!r} is not a Cornerstone career site URL. Pass the address a visitor "
            f"sees, https://<tenant>.csod.com/ux/ats/careersite/<id>/home?c=<corp>, "
            f"such as {EXAMPLE_BOARD}"
        )
    params = parse_qs(parts.query)
    corp = params.get("c", [""])[0].strip() or tenant[1]
    board_query = {"c": corp}
    if lang := params.get("lang", [""])[0].strip():
        board_query["lang"] = lang
    base = f"https://{host}/ux/ats/careersite/{path[1]}/home"
    return _CareerSite(
        tenant=tenant[1],
        site_id=int(path[1]),
        board_url=f"{base}?{urlencode(board_query)}",
        posting_prefix=f"{base}/requisition/",
        query_c=urlencode({"c": corp}),
    )


def _parse_context(page: BeautifulSoup) -> _Context:
    """
    Extract the anonymous bearer token, cloud API URL, and culture from ``csod.context``.

    Raises:
        TypeError: The page holds no ``csod.context``, no bearer token, or a cloud endpoint outside
            ``csod.com``.
        ValueError: The embedded ``csod.context`` is not valid JSON.
    """
    decoder = json.JSONDecoder()
    for script in page.find_all("script"):
        text = script.get_text()
        if not (match := _CONTEXT.search(text)):
            continue
        raw, _ = decoder.raw_decode(text, match.end())
        if not isinstance(raw, dict):
            raise TypeError("csod.context is not an object")
        token = (as_str(raw.get("token")) or "").strip()
        if not token:
            raise TypeError("csod.context holds no anonymous bearer token")
        cloud = (as_str(as_dict(raw.get("endpoints")).get("cloud")) or "").strip()
        cloud_parts = split_url(cloud)
        if cloud_parts.scheme != "https" or not on_domain(cloud_parts, "csod.com"):
            raise TypeError(
                f"csod.context cloud endpoint {cloud!r} is not an HTTPS address on csod.com"
            )
        culture_id = as_int(raw.get("cultureID"))
        culture_name = (as_str(raw.get("cultureName")) or "").strip() or "en-US"
        path = cloud_parts.path.rstrip("/")
        return _Context(
            api_url=f"https://{cloud_parts.netloc}{path}/rec-job-search/external/jobs",
            token=token,
            culture_id=culture_id if culture_id and culture_id > 0 else 1,
            culture_name=culture_name,
        )
    raise TypeError("the career site page holds no csod.context")


async def _fetch_context(fetcher: Fetcher, site: _CareerSite, board: str) -> _Context:
    """
    Read the career site HTML page and return its bootstrap context.

    Raises:
        Stopped: The career site does not exist, the request failed, or the page is unreadable.
    """
    unknown = (
        f"Cornerstone has no career site at {board!r}. Copy the URL of the employer's "
        f"career site, such as {EXAMPLE_BOARD}"
    )
    # The tenant host's robots.txt asks for a 10-second crawl delay. A search reads one page there
    # and then pages the API host, whose robots.txt holds no rules (checked 2026-11-24), so it
    # does not wait.
    result = await fetcher.fetch(site.board_url)
    if result.status == 404:
        raise Stopped(unknown)
    if reason := failure(result):
        raise Stopped(f"Cornerstone request for board {site.board_url!r} failed: {reason}")
    # An unknown careerSiteId redirects to /error.aspx with HTTP 200 (measured 2026-11-24 on
    # worldbankgroup.csod.com with careerSiteId 99999).
    if split_url(result.url).path.lower().endswith("/error.aspx"):
        raise Stopped(unknown)
    return read_html(result, _parse_context, site="cornerstone")


def _month_first(culture: str) -> bool:
    # Cornerstone formats dates in the requested culture's .NET short date pattern (measured
    # 2026-11-24: en-US sent 11/23/2026, en-GB sent 24/11/2026, de-DE sent 24.11.2026).
    region = culture.replace("_", "-").split("-")[-1].upper()
    return region in _MONTH_FIRST_REGIONS


def _parse_date(raw: object, culture: str) -> str | None:
    """
    Convert a Cornerstone short date in ``culture`` to ISO 8601, or None when absent.

    Cornerstone sends ``"-"`` when a posting has no expiration date (measured 2026-11-24 on
    Henkel's board). Unrecognized text passes through so ``make_job`` warns and omits it.
    """
    text = (as_str(raw) or "").strip()
    if not text or text == "-":
        return None
    numbers = _NUMBERS.findall(text)
    if len(numbers) != 3 or 4 not in (len(numbers[0]), len(numbers[2])):
        return text
    if len(numbers[0]) == 4:
        year, month, day = map(int, numbers)
    else:
        first, second, year = map(int, numbers)
        month, day = (first, second) if _month_first(culture) else (second, first)
    if culture.lower().replace("_", "-").split("-")[0] == "th":
        year -= _BUDDHIST_ERA
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return text


def _parse_requisition(item: dict[str, Any], site: _CareerSite, culture: str) -> JobDict:
    """
    Build a record from one entry of ``data.requisitions``.

    The ID joins the tenant and the integer ``requisitionId``, as in ``worldbankgroup:39579``,
    because requisition IDs are unique only within a tenant.

    Raises:
        TypeError: The entry lacks an integer ``requisitionId``.
        AttributeError: The entry is not an object.
    """
    if (req_id := as_int(item.get("requisitionId"))) is None:
        raise TypeError(f"requisitionId {item.get('requisitionId')!r} is not an integer")
    locations = [
        {
            "city": place.get("city"),
            "region": place.get("state"),
            "country_code": place.get("country"),
        }
        for place in map(as_dict, as_list(item.get("locations")))
    ]
    return make_job(
        site="cornerstone",
        id=f"{site.tenant}:{req_id}",
        url=f"{site.posting_prefix}{req_id}?{site.query_c}",
        title=item.get("displayJobTitle"),
        locations=locations,
        description=as_str(item.get("externalDescription")),
        posted_at=_parse_date(item.get("postingEffectiveDate"), culture),
        expires_at=_parse_date(item.get("postingExpirationDate"), culture),
    )


def _pages(
    fetcher: Fetcher,
    site: _CareerSite,
    context: _Context,
    body: dict[str, object],
    size: int,
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    headers = {
        "Authorization": f"Bearer {context.token}",
        "CSOD-Accept-Language": context.culture_name,
    }
    parse = functools.partial(_parse_requisition, site=site, culture=context.culture_name)
    numbers = itertools.count(1)

    async def read(_offset: int) -> tuple[list[Any], int]:
        payload = body | {"pageNumber": next(numbers), "pageSize": size}
        result = await fetcher.fetch(context.api_url, headers=headers, json=payload)
        return read_json(
            result,
            lambda answer: json_page(answer["data"], "requisitions", "totalCount"),
            site="cornerstone",
            board=site.board_url,
        )

    return offset_pages(read, parse, site="cornerstone", where=f"Cornerstone site {site.board_url}")


def _validate(*, board: str, **_: object) -> None:
    _career_site(board)


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, f"employer's career site URL, e.g., {EXAMPLE_BOARD}"],
    query: Annotated[str, "job title or keywords"] = "",
    country: Annotated[str | None, "ISO 3166-1 country code, e.g., us"] = None,
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours, rounded up to days"] = None,
) -> list[JobDict]:
    """
    Search one employer's Cornerstone career site, each requisition with its description.

    ``max_age_hours`` rounds up to whole days. The search first reads the career site's page,
    which holds the anonymous token and the regional host of its API.

    Raises:
        Stopped: A request failed, Cornerstone has no such career site, it sent an unreadable page
            or response, or an empty page came before the reported total. ``partial`` holds the
            postings collected before it.
        ValueError: ``board`` is not a Cornerstone career site URL, ``country`` is not an
            ISO 3166-1 code, or ``results`` or ``max_age_hours`` is below 1.
    """
    site = _career_site(board)
    logger.info("searching Cornerstone site %s for %r", site.board_url, query)
    context = await _fetch_context(fetcher, site, board)
    body: dict[str, object] = {
        "careerSiteId": site.site_id,
        "careerSitePageId": site.site_id,
        "cultureId": context.culture_id,
        "cultureName": context.culture_name,
        "searchText": query.strip(),
        "states": [],
        # checked passes the country as its upper-case alpha-2 code.
        "countryCodes": [country] if country else [],
        "cities": [],
        "placeID": "",
        # Both radius and postingsWithinDays must be null when unfiltered; guessed numbers
        # returned nothing (measured 2026-11-23 on the World Bank Group's board).
        "radius": None,
        # The API filters posting age in whole days (measured 2026-11-24 on World Bank Group with
        # 1, 2, 3, 5, 7, 10, and 14 days), so hours round up in integer arithmetic.
        "postingsWithinDays": -(-max_age_hours // 24) if max_age_hours is not None else None,
        "customFieldCheckboxKeys": [],
        "customFieldDropdowns": [],
        "customFieldRadios": [],
    }
    pages = _pages(fetcher, site, context, body, min(PAGE_SIZE, results))
    return await collect("cornerstone", pages, results)


__all__ = ["search"]
