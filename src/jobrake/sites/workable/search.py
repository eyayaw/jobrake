"""Workable widget API requests and parsing."""

import logging
from gettext import ngettext
from typing import Annotated, Any
from urllib.parse import quote

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job, make_places
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, html_text

logger = logging.getLogger(__name__)

# Workable documents www.workable.com/api/accounts/<board>, which answers with
# a 302 to this URL. Requesting it directly costs one request on any fetcher.
API_URL = "https://apply.workable.com/api/v1/widget/accounts"


def _texts(source: dict[str, Any], keys: tuple[str, ...]) -> tuple[str, ...]:
    """Return the stripped text under each key, using an empty string where a key holds none."""
    return tuple((as_str(source.get(key)) or "").strip() for key in keys)


def _parse_posting(posting: dict[str, Any], company: str | None) -> JobDict:
    """
    Build a record from one entry of a board's ``jobs`` list.

    Raises:
        TypeError: The posting lacks a ``shortcode`` or a ``url``.
        AttributeError: The posting is not an object.
    """
    places = posting.get("locations")
    listed = [as_dict(place) for place in (places if isinstance(places, list) else [])]
    # Each place is named with Workable's own text, whose country is a name
    # such as France, so a country without its code keeps the place.
    locations = make_places(
        [
            {
                "name": ", ".join(filter(None, _texts(place, ("city", "region", "country")))),
                "city": place.get("city"),
                "region": place.get("region"),
                "country_code": place.get("countryCode"),
            }
            for place in listed
        ]
    )
    top = _texts(posting, ("city", "state", "country"))
    # On the board we measured, the top-level fields repeated the first place
    # and added none.
    if all(_texts(place, ("city", "region", "country")) != top for place in listed):
        city, state, _ = top
        name = ", ".join(filter(None, top))
        locations = [*locations, {"name": name, "city": city, "region": state}]
    education = as_str(posting.get("education"))
    return make_job(
        site="workable",
        # The shortcode alone resolves at apply.workable.com/j/<shortcode>, so
        # it is unique across all boards, not just this one.
        id=posting.get("shortcode"),
        url=posting.get("url"),
        title=posting.get("title"),
        company=company,
        locations=locations,
        description=html_text(as_str(posting.get("description")) or ""),
        employment_type=employment_type(as_str(posting.get("employment_type"))),
        is_remote=True if posting.get("telecommuting") is True else None,
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
            # make_places drops a place equal to one the posting already has.
            kept["locations"] = make_places(kept["locations"] + job["locations"])
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
    places comes back once, with each place in ``locations``. It is neither paced
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
