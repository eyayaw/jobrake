"""SmartRecruiters Posting API requests and parsing."""

import logging
from datetime import UTC, datetime, timedelta
from gettext import ngettext
from typing import Annotated, Any
from urllib.parse import quote, urlencode

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job
from jobrake.sites.responses import json_page, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, finite

logger = logging.getLogger(__name__)

API_URL = "https://api.smartrecruiters.com/v1/companies"
# The list cards carry no URL. This one opens the posting's page on the hosted board.
POSTING_URL = "https://jobs.smartrecruiters.com/{company}/{id}"
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
    # SmartRecruiters' own example card has the place fields without fullLocation.
    country = as_str(location.get("country"))
    parts = (
        as_str(location.get("city")),
        as_str(location.get("region")),
        country and country.upper(),
    )
    place = as_str(location.get("fullLocation")) or ", ".join(
        part.strip() for part in parts if part and part.strip()
    )
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
        location=place,
        employment_type=employment_type(as_str(as_dict(card.get("typeOfEmployment")).get("label"))),
        is_remote=True if location.get("remote") is True else None,
        city=as_str(location.get("city")),
        region=as_str(location.get("region")),
        country_code=as_str(location.get("country")),
        latitude=_coordinate(location.get("latitude")),
        longitude=_coordinate(location.get("longitude")),
        language=as_str(as_dict(card.get("language")).get("code")),
        posted_at=as_str(card.get("releasedDate")),
    )


def _filters(query: str, max_age_hours: int | None, *, remote: bool) -> dict[str, str]:
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


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "board token from the employer's board URL, e.g., BoschGroup"],
    query: Annotated[str, "job title or keywords"] = "",
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
    remote: Annotated[bool, "only postings SmartRecruiters marks remote"] = False,
) -> list[JobDict]:
    """
    List the published postings on one employer's SmartRecruiters board.

    ``board`` is the company identifier that follows
    ``jobs.smartrecruiters.com/`` in the board's address. SmartRecruiters
    applies every option: ``query`` searches titles and locations, and
    ``max_age_hours`` keeps postings released within that many hours. Pages
    of up to 100 cards follow one another without pacing or retries until
    ``results``, the board's last match, or an empty page, and a posting
    that a later page repeats is kept once. An unknown board
    answers like a board with no postings, so it returns ``[]`` and logs that
    the board may be misspelled. A malformed card costs only that card. The
    caller owns ``fetcher``.

    Raises:
        Stopped: A request failed or SmartRecruiters sent an unreadable
            response. ``partial`` holds the postings of the pages before it.
        ValueError: ``board`` is blank, or ``results`` or ``max_age_hours``
            is below 1.
    """
    token = board.strip()
    params = _filters(query, max_age_hours, remote=remote)
    logger.info("reading smartrecruiters board %r", token)
    jobs: list[JobDict] = []
    seen: set[str] = set()
    offset = 0  # cards SmartRecruiters has sent, malformed ones included
    while len(jobs) < results:
        page = {"limit": min(PAGE_SIZE, results - len(jobs)), "offset": offset, **params}
        result = await fetcher.fetch(
            f"{API_URL}/{quote(token, safe='')}/postings?{urlencode(page)}"
        )
        cards, total = read_json(
            result,
            lambda page: json_page(page, "content", "totalFound"),
            site="smartrecruiters",
            board=token,
            partial=jobs,
        )
        # A posting released between two requests shifts the cards, so a page can repeat one.
        for job in parse_postings(cards, _parse_card, site="smartrecruiters"):
            if job["id"] not in seen:
                seen.add(job["id"])
                jobs.append(job)
        offset += len(cards)
        if not cards or offset >= total:
            break
    if offset == 0:
        logger.info(
            "smartrecruiters board %r returned no postings. SmartRecruiters answers the same "
            "for an unknown board, so check the identifier that follows "
            "jobs.smartrecruiters.com/ in the board's URL",
            token,
        )
    else:
        logger.info(
            "smartrecruiters board %r returned %s",
            token,
            ngettext("%d posting", "%d postings", len(jobs)) % len(jobs),
        )
    return jobs
