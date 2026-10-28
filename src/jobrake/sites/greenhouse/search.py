"""Greenhouse Job Board API requests and parsing."""

import logging
from gettext import ngettext
from html import unescape
from typing import Annotated, Any
from urllib.parse import quote

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, make_job
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, html_text

logger = logging.getLogger(__name__)

API_URL = "https://boards-api.greenhouse.io/v1/boards"


def _parse_posting(posting: dict[str, Any]) -> JobDict:
    """
    Build a record from one entry of a board's ``jobs`` list.

    Raises:
        TypeError: The posting lacks an integer ``id`` or an ``absolute_url``.
        AttributeError: The posting is not an object.
    """
    posting_id = posting.get("id")
    # bool is an int subclass, and str() of any other value would invent an ID.
    if isinstance(posting_id, bool) or not isinstance(posting_id, int):
        raise TypeError(f"posting id {posting_id!r} is not an integer")
    # Greenhouse escapes the description HTML, so its tags arrive as entities.
    content = unescape(as_str(posting.get("content")) or "")
    # Greenhouse does not say which of several departments hires, so only a lone one counts.
    departments = posting.get("departments")
    department = (
        as_dict(departments[0]).get("name")
        if isinstance(departments, list) and len(departments) == 1
        else None
    )
    return make_job(
        site="greenhouse",
        id=str(posting_id),
        url=posting.get("absolute_url"),
        title=posting.get("title"),
        company=posting.get("company_name"),
        locations=[{"name": as_dict(posting.get("location")).get("name")}],
        description=html_text(content),
        language=as_str(posting.get("language")),
        department=as_str(department),
        posted_at=as_str(posting.get("first_published")),
        expires_at=as_str(posting.get("application_deadline")),
    )


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "board token from the employer's board URL, e.g., airbnb"],
) -> list[JobDict]:
    """
    List every published posting on one employer's Greenhouse board.

    ``board`` is the token that ends the board's address, as in
    ``job-boards.greenhouse.io/airbnb``. One request returns the whole board,
    descriptions included, in Greenhouse's order. It is neither paced nor
    retried. A malformed posting costs only that posting. The caller owns
    ``fetcher``.

    Raises:
        Stopped: The request failed, Greenhouse has no such board, or it sent
            an unreadable response. ``partial`` is empty.
        ValueError: ``board`` is blank.
    """
    token = board.strip()
    logger.info("reading greenhouse board %r", token)
    result = await fetcher.fetch(f"{API_URL}/{quote(token, safe='')}/jobs?content=true")
    postings = read_json(
        result,
        lambda page: json_list(page, "jobs"),
        site="greenhouse",
        board=token,
        unknown=f"greenhouse has no board {token!r}. Pass the token that ends the employer's "
        "board URL, boards.greenhouse.io/<token> or job-boards.greenhouse.io/<token>",
    )
    jobs = parse_postings(postings, _parse_posting, site="greenhouse")
    logger.info(
        "greenhouse board %r has %s",
        token,
        ngettext("%d posting", "%d postings", len(jobs)) % len(jobs),
    )
    return jobs
