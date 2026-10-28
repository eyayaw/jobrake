"""Lever Postings API requests and parsing."""

import logging
from gettext import ngettext
from html import escape
from typing import Annotated, Any
from urllib.parse import quote

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, epoch_ms_to_iso, finite, html_text

logger = logging.getLogger(__name__)

# A board lives on one of Lever's two instances, and the other answers 404 for it.
API_URLS = ("https://api.lever.co/v0/postings", "https://api.eu.lever.co/v0/postings")


def _description(posting: dict[str, Any]) -> str:
    # description already holds the opening, so the opening fields stay out.
    parts = [as_str(posting.get("description")) or ""]
    for entry in posting.get("lists") or []:
        if isinstance(entry, dict):
            # The list name is plain text, and its content is bare <li> elements.
            heading = escape(as_str(entry.get("text")) or "")
            parts.append(f"<h3>{heading}</h3><ul>{as_str(entry.get('content')) or ''}</ul>")
    parts.append(as_str(posting.get("additional")) or "")
    return html_text("".join(parts))


def _posted_at(posting: dict[str, Any]) -> str | None:
    if (ms := finite(posting.get("createdAt"))) is None:
        return None
    try:
        return epoch_ms_to_iso(ms)
    except ValueError as error:
        # One posting's bad timestamp costs that field, not the posting.
        logger.warning("lever posting %s: %s", posting.get("id"), error)
        return None


def _parse_posting(posting: dict[str, Any]) -> JobDict:
    """
    Build a record from one entry of a board's posting list.

    Raises:
        TypeError: The posting lacks an ``id`` or a ``hostedUrl``.
        AttributeError: The posting is not an object.
    """
    categories = as_dict(posting.get("categories"))
    return make_job(
        site="lever",
        id=posting.get("id"),
        url=posting.get("hostedUrl"),
        title=posting.get("text"),
        location=as_str(categories.get("location")),
        description=_description(posting),
        employment_type=employment_type(as_str(categories.get("commitment"))),
        is_remote=True if posting.get("workplaceType") == "remote" else None,
        country_code=as_str(posting.get("country")),
        posted_at=_posted_at(posting),
        apply_url=as_str(posting.get("applyUrl")),
    )


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "board token from the employer's board URL, e.g., palantir"],
) -> list[JobDict]:
    """
    List every published posting on one employer's Lever board.

    ``board`` is the token that ends the board's address, as in
    ``jobs.lever.co/palantir``. One request returns the whole board,
    descriptions included, in Lever's order. A board the global host does not
    know is requested once more from the EU host. Neither request is paced or
    retried. A malformed posting costs only that posting. The caller owns
    ``fetcher``.

    Raises:
        Stopped: A request failed, neither host has the board, or Lever sent
            an unreadable response. ``partial`` is empty.
        ValueError: ``board`` is blank.
    """
    token = board.strip()
    logger.info("reading lever board %r", token)
    for api_url in API_URLS:
        result = await fetcher.fetch(f"{api_url}/{quote(token, safe='')}?mode=json")
        if result.status != 404:
            break
    # After a 404 from every host, result holds the last one.
    postings = read_json(
        result,
        json_list,
        site="lever",
        board=token,
        unknown=f"lever has no board {token!r} on its global or EU host. Pass the token that "
        "ends the employer's board URL, jobs.lever.co/<token> or jobs.eu.lever.co/<token>",
    )
    jobs = parse_postings(postings, _parse_posting, site="lever")
    logger.info(
        "lever board %r has %s",
        token,
        ngettext("%d posting", "%d postings", len(jobs)) % len(jobs),
    )
    return jobs
