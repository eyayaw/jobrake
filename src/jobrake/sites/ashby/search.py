"""Ashby Job Posting API requests and parsing."""

import logging
from gettext import ngettext
from typing import Annotated, Any
from urllib.parse import quote

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, finite, html_text, join_places

logger = logging.getLogger(__name__)

API_URL = "https://api.ashbyhq.com/posting-api/job-board"

# The Ashby pay intervals that match a JobDict period. Another interval
# leaves the period out and keeps the amounts.
_PERIODS = {
    "1 HOUR": "HOUR",
    "1 DAY": "DAY",
    "1 WEEK": "WEEK",
    "1 MONTH": "MONTH",
    "1 YEAR": "YEAR",
}


def _salary(compensation: dict[str, Any]) -> dict[str, Any]:
    """Return the salary fields of a posting's first Salary component, or nothing without one."""
    components = compensation.get("summaryComponents")
    for entry in components if isinstance(components, list) else []:
        component = as_dict(entry)
        if component.get("compensationType") == "Salary":
            return {
                "salary_min": finite(component.get("minValue")),
                "salary_max": finite(component.get("maxValue")),
                "salary_currency": as_str(component.get("currencyCode")),
                "salary_period": _PERIODS.get(as_str(component.get("interval"))),
            }
    return {}


def _parse_posting(posting: dict[str, Any]) -> JobDict:
    """
    Build a record from one entry of a board's ``jobs`` list.

    Raises:
        TypeError: The posting lacks a ``jobUrl``, or an ID in ``id`` or at its end.
        AttributeError: The posting is not an object.
    """
    address = as_dict(as_dict(posting.get("address")).get("postalAddress"))
    url = as_str(posting.get("jobUrl"))
    # Ashby's documentation lists no id. Every posting carried one on 2026-10-28,
    # and the last part of its jobUrl was the same ID, which stands in without it.
    # Plain splitting reads that part without raising on a malformed URL.
    posting_id = as_str(posting.get("id"))
    if not posting_id and url:
        posting_id = url.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    # Ashby's documentation lists no secondaryLocations either. On 2026-10-28,
    # 103 of the 172 postings on ramp listed more places there.
    secondary = posting.get("secondaryLocations")
    places = (
        [as_dict(entry).get("location") for entry in secondary]
        if isinstance(secondary, list)
        else []
    )
    return make_job(
        site="ashby",
        id=posting_id,
        url=url,
        title=posting.get("title"),
        company=None,  # the response never names the employer
        location=join_places([posting.get("location"), *places]),
        description=html_text(as_str(posting.get("descriptionHtml")) or ""),
        employment_type=employment_type(as_str(posting.get("employmentType"))),
        # isRemote is also true for a hybrid posting, so only the workplace type confirms remote.
        is_remote=True if posting.get("workplaceType") == "Remote" else None,
        city=as_str(address.get("addressLocality")),
        region=as_str(address.get("addressRegion")),
        posted_at=as_str(posting.get("publishedAt")),
        apply_url=as_str(posting.get("applyUrl")),
        **_salary(as_dict(posting.get("compensation"))),
    )


@checked
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "board token from the employer's board URL, e.g., ramp"],
) -> list[JobDict]:
    """
    List every published posting on one employer's Ashby board.

    ``board`` is the token that ends the board's address, as in
    ``jobs.ashbyhq.com/ramp``. One request returns the whole board,
    descriptions and compensation included, in Ashby's order. The result
    includes postings the employer marked unlisted, which Ashby serves for
    direct links. The request is neither paced nor retried. A malformed
    posting costs only that posting. The caller owns ``fetcher``.

    Raises:
        Stopped: The request failed, Ashby has no such board, or it sent an
            unreadable response. ``partial`` is empty.
        ValueError: ``board`` is blank.
    """
    token = board.strip()
    logger.info("reading ashby board %r", token)
    result = await fetcher.fetch(f"{API_URL}/{quote(token, safe='')}?includeCompensation=true")
    postings = read_json(
        result,
        lambda page: json_list(page, "jobs"),
        site="ashby",
        board=token,
        unknown=f"ashby has no board {token!r}. Pass the token that ends the employer's "
        "board URL, jobs.ashbyhq.com/<token>",
    )
    jobs = parse_postings(postings, _parse_posting, site="ashby")
    logger.info(
        "ashby board %r has %s",
        token,
        ngettext("%d posting", "%d postings", len(jobs)) % len(jobs),
    )
    return jobs
