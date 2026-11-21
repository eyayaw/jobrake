"""Read an employer's SmartRecruiters job board through its public Posting API."""

import logging
import re
from collections.abc import AsyncGenerator
from html import escape
from typing import Annotated, Any
from urllib.parse import quote, urlencode, urlsplit

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job
from jobrake.sites.postings import fill_details, postings_of, readable_url
from jobrake.sites.responses import collect, json_page, offset_pages, read_json
from jobrake.utils import as_dict, as_str, checked, cutoff, finite, html_text

logger = logging.getLogger(__name__)

API_URL = "https://api.smartrecruiters.com/v1/companies"
# The list cards carry no URL. This one opens the posting's page on the hosted board.
POSTING_URL = "https://jobs.smartrecruiters.com/{company}/{id}"
# A posting's page path, where a title slug may follow the ID, as in
# /BoschGroup/744000158197889-product-expert.
_POSTING_PATH = re.compile(r"/([^/\s]+)/([0-9]+)(?:-[^/]*)?/?")
PAGE_SIZE = 100  # the largest limit the API accepts


def _coordinate(value: object) -> float | None:
    """Return a coordinate SmartRecruiters sends as text, or None for text that holds no finite number."""
    if not isinstance(value, str):
        return None
    try:
        return finite(float(value))
    except ValueError:
        return None


def _parse_card(listing: dict[str, Any]) -> JobDict:
    """
    Build a record from one card of a board's ``content`` list.

    Raises:
        TypeError: The card's ``id`` and company identifier do not make a posting URL.
        AttributeError: The card is not an object.
    """
    company = as_dict(listing.get("company"))
    identifier, posting_id = company.get("identifier"), listing.get("id")
    # A missing identifier leaves the company out of the URL, which card then refuses.
    company_url = POSTING_URL.format(company=as_str(identifier) or "", id=posting_id)
    url = readable_url(card, posting_id, company_url)
    location = as_dict(listing.get("location"))
    # SmartRecruiters' own example card has the place fields without fullLocation,
    # so make_job names that place from its parts.
    place = {
        "name": location.get("fullLocation"),
        "city": location.get("city"),
        "region": location.get("region"),
        "country_code": location.get("country"),
        "latitude": _coordinate(location.get("latitude")),
        "longitude": _coordinate(location.get("longitude")),
    }
    return make_job(
        site="smartrecruiters",
        id=posting_id,
        url=url,
        title=listing.get("name"),
        company=company.get("name"),
        locations=[place],
        employment_type=employment_type(
            as_str(as_dict(listing.get("typeOfEmployment")).get("label"))
        ),
        department=as_str(as_dict(listing.get("department")).get("label")),
        # Both flags false does not state on-site, so such a card has no workplace type.
        workplace_type="remote"
        if location.get("remote") is True
        else "hybrid"
        if location.get("hybrid") is True
        else None,
        language=as_str(as_dict(listing.get("language")).get("code")),
        posted_at=as_str(listing.get("releasedDate")),
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
    """Return a posting's card fields, ``description``, and ``apply_url``, or None if inactive."""
    if posting.get("active") is False:
        return None
    return {
        **_parse_card(posting),
        "description": _description(posting),
        "apply_url": as_str(posting.get("applyUrl")),
    }


async def _posting_fields(fetcher: Fetcher, url: str) -> dict[str, Any] | None:
    """
    Fetch the posting at a URL, or None when SmartRecruiters reports it gone.

    SmartRecruiters reports a posting gone with a 404, or by marking a posting it still
    serves inactive. A 400 stays a failure: it answers a malformed request,
    and an ID that belongs to another board.

    Raises:
        Stopped: The request failed, or the response is unreadable.
    """
    company, posting_id = urlsplit(url).path.strip("/").split("/")
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
    if released_after := cutoff(max_age_hours):
        params["releasedAfter"] = released_after.strftime("%Y-%m-%dT%H:%M:%SZ")
    if remote:
        params["locationType"] = "REMOTE"
    return params


def _pages(
    fetcher: Fetcher, token: str, params: dict[str, Any]
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """Yield each page's cards with the board's count of matches, until its last match."""

    async def read(offset: int) -> tuple[list[Any], int]:
        page = urlencode(params | {"offset": offset})
        result = await fetcher.fetch(f"{API_URL}/{quote(token, safe='')}/postings?{page}")
        cards, total = read_json(
            result,
            lambda page: json_page(page, "content", "totalFound"),
            site="smartrecruiters",
            board=token,
        )
        # An unknown board and a filter that matches nothing both answer with no postings,
        # so only a search without filters hints at a misspelling.
        if offset == 0 and not cards and total <= 0 and params.keys() == {"limit"}:
            logger.info(
                "smartrecruiters board %r returned no postings. SmartRecruiters answers the same "
                "for an unknown board, so check the identifier that follows "
                "jobs.smartrecruiters.com/ in the board's URL",
                token,
            )
        return cards, total

    where = f"smartrecruiters board {token!r}"
    return offset_pages(read, _parse_card, site="smartrecruiters", where=where)


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "board token from the employer's board URL, e.g., BoschGroup"],
    query: Annotated[str, "job title or keywords"] = "",
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
    remote: Annotated[bool, "only postings SmartRecruiters marks remote"] = False,
    details: Annotated[bool, "fetch each posting for its description and other details"] = False,
) -> list[JobDict]:
    """
    List the published postings on one employer's SmartRecruiters board.

    ``board`` is the company identifier that follows ``jobs.smartrecruiters.com/`` in the board's
    address. SmartRecruiters applies every option: ``query`` searches titles and locations,
    and ``max_age_hours`` keeps postings released within that many hours. Pages of up to 100 cards
    follow one another without pacing or retries until ``results``, the board's last match,
    or an empty page. A posting that a later page repeats is kept once. An unknown board answers
    like a board with no postings, so it returns ``[]``, and a search without filters also logs
    that the board may be misspelled.
    A card carries no description, so ``details`` fetches each posting with one more request,
    which a cached posting skips.

    Raises:
        Stopped: A request failed, SmartRecruiters sent an unreadable response,
            or an empty page came before the reported total.
            ``partial`` holds the postings of the pages before it. With ``details``, a posting could
            not be fetched, and ``partial`` holds every posting, filled where its fetch succeeded,
            and ``failed`` the URLs of the postings whose fetch failed.
        ValueError: ``board`` is blank, or ``results`` or ``max_age_hours`` is below 1.
    """
    token = board.strip()
    logger.info("reading smartrecruiters board %r", token)
    params = _filters(query, max_age_hours, remote=remote) | {"limit": min(PAGE_SIZE, results)}
    jobs = await collect("smartrecruiters", _pages(fetcher, token, params), results)
    return await fill_details(fetcher, jobs, _posting_fields) if details else jobs


def card(reference: str) -> JobDict:
    """
    Read a SmartRecruiters posting URL as the card it names, for ``postings`` and ``identify``.

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


postings = postings_of(card, _posting_fields)


__all__ = ["postings", "search"]
