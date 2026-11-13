"""Read an employer's SmartRecruiters job board through its public Posting API."""

import functools
import logging
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Annotated, Any
from urllib.parse import quote, urlencode, urlsplit

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, employment_type, make_job
from jobrake.sites.postings import fetch_postings, fill_details
from jobrake.sites.responses import collect, json_page, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, finite, html_text

logger = logging.getLogger(__name__)

API_URL = "https://api.smartrecruiters.com/v1/companies"
# The list cards carry no URL. This one opens the posting's page on the hosted board.
POSTING_URL = "https://jobs.smartrecruiters.com/{company}/{id}"
# A posting's page path, where a title slug may follow the ID, as in
# /BoschGroup/744000158197889-product-expert.
_POSTING_PATH = re.compile(r"/([^/]+)/(\d+)(?:-[^/]*)?/?")
PAGE_SIZE = 100  # the largest limit the API accepts


def _coordinate(value: object) -> float | None:
    """Return a coordinate SmartRecruiters sends as text, or None for text that holds no finite number."""
    if not isinstance(value, str):
        return None
    try:
        return finite(float(value))
    except ValueError:
        return None


def _parse_card(card: dict[str, Any]) -> JobDict:
    """
    Build a record from one card of a board's ``content`` list.

    Raises:
        TypeError: The card lacks a string ``id`` or a company identifier.
        AttributeError: The card is not an object.
    """
    company = as_dict(card.get("company"))
    location = as_dict(card.get("location"))
    # SmartRecruiters' own example card has the place fields without
    # fullLocation, so make_job names that place from its parts.
    place = {
        "name": location.get("fullLocation"),
        "city": location.get("city"),
        "region": location.get("region"),
        "country_code": location.get("country"),
        "latitude": _coordinate(location.get("latitude")),
        "longitude": _coordinate(location.get("longitude")),
    }
    identifier, posting_id = company.get("identifier"), card.get("id")
    url = (
        POSTING_URL.format(company=identifier, id=posting_id)
        if isinstance(identifier, str)
        else None
    )
    return make_job(
        site="smartrecruiters",
        id=posting_id,
        url=url,
        title=card.get("name"),
        company=company.get("name"),
        locations=[place],
        employment_type=employment_type(as_str(as_dict(card.get("typeOfEmployment")).get("label"))),
        department=as_str(as_dict(card.get("department")).get("label")),
        # Both flags false does not state on-site, so such a card has no workplace type.
        workplace_type="remote"
        if location.get("remote") is True
        else "hybrid"
        if location.get("hybrid") is True
        else None,
        language=as_str(as_dict(card.get("language")).get("code")),
        posted_at=as_str(card.get("releasedDate")),
    )


def _description(posting: dict[str, Any]) -> str:
    """Join every section of a posting's ad in SmartRecruiters' order, each under its title."""
    parts = []
    for section in as_dict(as_dict(posting.get("jobAd")).get("sections")).values():
        if text := as_str(as_dict(section).get("text")):
            title = escape(as_str(as_dict(section).get("title")) or "")
            parts.append(f"<h3>{title}</h3><div>{text}</div>")
    return html_text("".join(parts))


def _parse_posting(posting: dict[str, Any]) -> dict[str, Any] | None:
    """Return a posting's card fields with its ad as ``description``, or None if it is inactive."""
    if posting.get("active") is False:
        return None
    return {**_parse_card(posting), "description": _description(posting)}


async def _posting_fields(fetcher: Fetcher, card: JobDict) -> dict[str, Any] | None:
    """
    Fetch the posting behind a card, or None when SmartRecruiters reports it gone.

    SmartRecruiters reports a posting gone with a 404, or by marking a posting
    it still serves inactive. A 400 stays a failure: it answers a malformed
    request, and an ID that belongs to another board.

    Raises:
        Stopped: The request failed, or the response is unreadable.
    """
    company, posting_id = urlsplit(card["url"]).path.strip("/").split("/")
    result = await fetcher.fetch(
        f"{API_URL}/{quote(company, safe='')}/postings/{quote(posting_id, safe='')}"
    )
    if result.status == 404:
        return None
    return read_json(result, _parse_posting, site="smartrecruiters")


def _filters(query: str, max_age_hours: int | None, *, remote: bool) -> dict[str, Any]:
    """Return the search options as the API's query parameters, leaving out an option left unset."""
    params = {}
    if query:
        params["q"] = query
    if max_age_hours:
        try:
            released_after = datetime.now(UTC) - timedelta(hours=max_age_hours)
        except OverflowError:
            pass  # A cutoff before year 1 excludes no posting, so the option stays out.
        else:
            params["releasedAfter"] = released_after.strftime("%Y-%m-%dT%H:%M:%SZ")
    if remote:
        params["locationType"] = "REMOTE"
    return params


async def _pages(
    fetcher: Fetcher, token: str, params: dict[str, Any]
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """
    Yield each page's cards with the board's count of matches, until its last match.

    Raises:
        Stopped: A request failed, SmartRecruiters sent an unreadable response,
            or an empty page came before the reported total.
    """
    offset = 0  # cards SmartRecruiters has sent, malformed ones included
    while True:
        page = urlencode(params | {"offset": offset})
        result = await fetcher.fetch(f"{API_URL}/{quote(token, safe='')}/postings?{page}")
        cards, total = read_json(
            result,
            lambda page: json_page(page, "content", "totalFound"),
            site="smartrecruiters",
            board=token,
        )
        if not cards:
            break
        offset += len(cards)
        # A posting released between two requests shifts the cards, so a page can repeat one.
        yield parse_postings(cards, _parse_card, site="smartrecruiters"), total
        if offset >= total:
            return
    if offset < total:
        raise Stopped(
            f"smartrecruiters board {token!r} reported {total} postings but sent an empty "
            f"page after {offset}, so the result may be incomplete. Postings may have "
            "closed during the search. A rerun reads the current list"
        )
    if offset == 0:
        logger.info(
            "smartrecruiters board %r returned no postings. SmartRecruiters answers the same "
            "for an unknown board, so check the identifier that follows "
            "jobs.smartrecruiters.com/ in the board's URL",
            token,
        )


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "board token from the employer's board URL, e.g., BoschGroup"],
    query: Annotated[str, "job title or keywords"] = "",
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
    remote: Annotated[bool, "only postings SmartRecruiters marks remote"] = False,
    details: Annotated[bool, "fetch posting pages for descriptions and other details"] = False,
) -> list[JobDict]:
    """
    List the published postings on one employer's SmartRecruiters board.

    ``board`` is the company identifier that follows
    ``jobs.smartrecruiters.com/`` in the board's address. SmartRecruiters
    applies every option: ``query`` searches titles and locations, and
    ``max_age_hours`` keeps postings released within that many hours. Pages
    of up to 100 cards follow one another without pacing or retries until
    ``results``, the board's last match, or an empty page. A posting that a
    later page repeats is kept once. An unknown board
    answers like a board with no postings, so it returns ``[]`` and logs that
    the board may be misspelled. A malformed card costs only that card. A
    card carries no description, so ``details`` fetches each posting with one
    more request. The caller owns ``fetcher``.

    Raises:
        Stopped: A request failed, SmartRecruiters sent an unreadable
            response, or an empty page came before the reported total.
            ``partial`` holds the postings of the pages before it. With
            ``details``, a posting could not be fetched, and ``partial`` holds
            every posting, filled where its fetch succeeded.
        ValueError: ``board`` is blank, or ``results`` or ``max_age_hours``
            is below 1.
    """
    token = board.strip()
    logger.info("reading smartrecruiters board %r", token)
    params = _filters(query, max_age_hours, remote=remote) | {"limit": min(PAGE_SIZE, results)}
    jobs = await collect("smartrecruiters", _pages(fetcher, token, params), results)
    if details:
        return await fill_details(
            "smartrecruiters", jobs, functools.partial(_posting_fields, fetcher)
        )
    return jobs


def _card(reference: str) -> JobDict:
    """
    Read a SmartRecruiters posting URL as the card it names.

    Raises:
        ValueError: The reference is not a posting URL on jobs.smartrecruiters.com.
    """
    parts = urlsplit(reference.strip())
    hosted = (
        parts.scheme in ("http", "https") and parts.netloc.lower() == "jobs.smartrecruiters.com"
    )
    if not (hosted and (match := _POSTING_PATH.fullmatch(parts.path))):
        raise ValueError(
            f"{reference!r} is not a SmartRecruiters posting URL. Pass a record's url, such "
            "as https://jobs.smartrecruiters.com/BoschGroup/744000158197889"
        )
    company, posting_id = match.groups()
    return make_job(
        site="smartrecruiters",
        id=posting_id,
        url=POSTING_URL.format(company=company, id=posting_id),
    )


@checked
async def postings(
    fetcher: Fetcher,
    references: Annotated[list[str], "SmartRecruiters posting URLs"],
) -> dict[str, JobDict | None]:
    """
    Fetch known SmartRecruiters postings by URL, one request each.

    The result is keyed by the references given. A reference is a record's
    ``url`` or the posting's ``postingUrl``, which adds a title slug, and
    references naming one posting share one request. A reference maps to
    ``None`` when SmartRecruiters reports its posting gone, and has no key
    after a failed request or an unreadable response, each logged, so a
    rerun retries it. The caller owns ``fetcher``.

    Raises:
        ValueError: A reference is not a SmartRecruiters posting URL. Nothing
            is fetched in that case.
    """
    return await fetch_postings(
        "smartrecruiters", references, _card, functools.partial(_posting_fields, fetcher)
    )


__all__ = ["postings", "search"]
