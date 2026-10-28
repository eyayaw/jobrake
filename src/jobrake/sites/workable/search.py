"""Workable widget API requests and parsing."""

import logging
from gettext import ngettext
from typing import Annotated, Any
from urllib.parse import quote

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, html_text, join_places

logger = logging.getLogger(__name__)

# Workable documents www.workable.com/api/accounts/<board>, which answers with
# a 302 to this URL. Requesting it directly costs one request on any fetcher.
API_URL = "https://apply.workable.com/api/v1/widget/accounts"


def _parse_posting(posting: dict[str, Any], company: str | None) -> JobDict:
    """
    Build a record from one entry of a board's ``jobs`` list.

    Raises:
        TypeError: The posting lacks a ``shortcode`` or a ``url``.
        AttributeError: The posting is not an object.
    """
    places = posting.get("locations")
    place = as_dict(places[0] if isinstance(places, list) and places else None)
    parts = (as_str(posting.get(key)) for key in ("city", "state", "country"))
    education = as_str(posting.get("education"))
    return make_job(
        site="workable",
        # The shortcode alone resolves at apply.workable.com/j/<shortcode>, so
        # it is unique across all boards, not just this one.
        id=posting.get("shortcode"),
        url=posting.get("url"),
        title=posting.get("title"),
        company=company,
        location=", ".join(part.strip() for part in parts if part and part.strip()),
        description=html_text(as_str(posting.get("description")) or ""),
        employment_type=employment_type(as_str(posting.get("employment_type"))),
        is_remote=True if posting.get("telecommuting") is True else None,
        city=as_str(place.get("city")),
        region=as_str(place.get("region")),
        country_code=as_str(place.get("countryCode")),
        posted_at=as_str(posting.get("published_on")),
        apply_url=as_str(posting.get("application_url")),
        # Workable's education menu offers "Unspecified" for no requirement.
        education=None if education == "Unspecified" else education,
    )


def _one_per_shortcode(jobs: list[JobDict]) -> list[JobDict]:
    """Merge the entries of one posting, which Workable repeats once per place, into its first."""
    first: dict[str, JobDict] = {}
    for job in jobs:
        kept = first.setdefault(job["id"], job)
        if job is not kept:
            kept["location"] = join_places([*(kept["location"] or "").split("; "), job["location"]])
    return list(first.values())


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "board token from the employer's careers page URL, e.g., huggingface"],
) -> list[JobDict]:
    """
    List every published posting on one employer's Workable board.

    ``board`` is the token that follows the host in the careers page address,
    as in ``apply.workable.com/huggingface``. One request returns the whole
    board, descriptions included, in Workable's order. A posting open in several
    places comes back once, with each place in ``location``. It is neither paced
    nor retried. A malformed posting costs only that posting. The caller owns
    ``fetcher``.

    Raises:
        Stopped: The request failed, Workable has no such board, or it sent
            an unreadable response. ``partial`` is empty.
        ValueError: ``board`` is blank.
    """
    token = board.strip()
    logger.info("reading workable board %r", token)
    result = await fetcher.fetch(f"{API_URL}/{quote(token, safe='')}?details=true")
    postings, company = read_json(
        result,
        # json_list runs first and rejects an account that is not an object.
        lambda account: (json_list(account, "jobs"), as_str(account.get("name"))),
        site="workable",
        board=token,
        unknown=f"workable has no board {token!r}. Pass the token that follows the host in the "
        "employer's careers page URL, apply.workable.com/<token>",
    )
    jobs = _one_per_shortcode(
        parse_postings(postings, lambda posting: _parse_posting(posting, company), site="workable")
    )
    logger.info(
        "workable board %r has %s",
        token,
        ngettext("%d posting", "%d postings", len(jobs)) % len(jobs),
    )
    return jobs
