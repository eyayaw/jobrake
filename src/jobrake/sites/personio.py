"""Read an employer's Personio career site through its public XML feed."""

import logging
import re
import xml.etree.ElementTree as ET
from functools import partial
from gettext import ngettext
from html import escape
from typing import Annotated, Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, employment_type, make_job
from jobrake.sites.responses import parse_postings, read_xml
from jobrake.utils import checked, finite, html_text

logger = logging.getLogger(__name__)

# The feed's languages, from Personio's recruiting API spec on 2026-11-15:
# https://github.com/personio/api-docs/blob/master/personio-recruiting-api.yaml
# English comes first because it described 152 of the 161 postings that the default feeds of 71
# boards left without a description. The rest keep the spec's order.
LANGUAGES = ("en", "de", "fr", "es", "nl", "it", "pt")

# The board becomes the first label of the host name, so it must be one DNS label, or a value
# such as x@evil.com# would send the request elsewhere.
_BOARD = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.IGNORECASE | re.ASCII)

# The salary types measured on 62 postings of 71 boards (2026-11-15). Another type leaves the period
# out and keeps the amounts.
_PERIODS = {"hourly": "HOUR", "monthly": "MONTH", "yearly": "YEAR"}

# Fields only Personio carries, under the feed's own names.
_SITE_FIELDS = (
    "recruitingCategory",
    "seniority",
    "schedule",
    "yearsOfExperience",
    "keywords",
    "occupation",
    "occupationCategory",
)


def _validate(*, board: str, **_: object) -> None:
    if _BOARD.fullmatch(board.strip()) is None:
        raise ValueError(
            f"board {board!r} is not a Personio subdomain. Pass the name before .jobs.personio.de "
            "in the employer's career site URL, such as tado"
        )


def _positions(root: ET.Element) -> list[ET.Element]:
    if root.tag != "workzag-jobs":
        raise TypeError(f"the feed's root is <{root.tag}>, not <workzag-jobs>")
    return root.findall("position")


def _amount(text: str | None) -> float | None:
    try:
        return finite(float(text or ""))
    except ValueError:
        return None


def _salary(position: ET.Element) -> dict[str, Any]:
    if (salary := position.find("salaryInformation")) is None:
        return {}
    return {
        "salary_min": _amount(salary.findtext("min")),
        "salary_max": _amount(salary.findtext("max")),
        "salary_currency": salary.findtext("currencyCode"),
        "salary_period": _PERIODS.get(salary.findtext("type") or ""),
    }


def _description(position: ET.Element) -> str:
    # A block's name is plain text, and its value is HTML.
    blocks = (
        f"<div><h3>{escape(block.findtext('name') or '')}</h3>{block.findtext('value') or ''}</div>"
        for block in position.iterfind("jobDescriptions/jobDescription")
        if (block.findtext("value") or "").strip()
    )
    return html_text("".join(blocks))


def _parse_position(position: ET.Element, board: str) -> JobDict:
    """
    Build a record from one ``position`` of a board's feed.

    Raises:
        TypeError: The position lacks a numeric ``id``.
    """
    posting_id = position.findtext("id") or ""
    if not (posting_id.isascii() and posting_id.isdigit()):
        raise TypeError(f"position id {posting_id!r} is not a number")
    others = position.iterfind("additionalOffices/office")
    offices = [position.findtext("office"), *(office.text for office in others)]
    return make_job(
        site="personio",
        id=posting_id,
        url=f"https://{board}.jobs.personio.de/job/{posting_id}",
        title=position.findtext("name"),
        company=position.findtext("subcompany"),
        locations=[{"name": office} for office in offices],
        description=_description(position),
        department=position.findtext("department"),
        employment_type=employment_type(position.findtext("employmentType")),
        posted_at=position.findtext("createdAt"),
        **_salary(position),
        # Employers type some of these with a trailing space, which make_job leaves in site_data.
        site_data={name: (position.findtext(name) or "").strip() for name in _SITE_FIELDS},
    )


async def _feed(fetcher: Fetcher, board: str, language: str | None = None) -> list[JobDict]:
    query = f"?language={language}" if language else ""
    result = await fetcher.fetch(f"https://{board}.jobs.personio.de/xml{query}")
    positions = read_xml(
        result,
        _positions,
        site="personio",
        board=board,
        unknown=f"personio serves no feed for board {board!r}, so the board does not exist or its "
        "employer switched the feed off. Pass the name before .jobs.personio.de in the employer's "
        "career site URL",
    )
    return parse_postings(positions, partial(_parse_position, board=board), site="personio")


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    board: Annotated[str, "subdomain of the employer's career site, e.g., tado"],
) -> list[JobDict]:
    """
    List every published posting on one employer's Personio career site.

    ``board`` is the subdomain of the career site, as in ``tado.jobs.personio.de``. The feed in the
    board's default language comes first and sets the order. A posting it leaves without a
    description is taken whole, title included, from the first feed in ``LANGUAGES`` that describes
    it. Each language costs one request, read in order while a posting lacks a description.
    Requests are neither paced nor retried.

    Raises:
        Stopped: A request failed, the board has no feed, or Personio sent an unreadable response.
            ``partial`` holds the postings read before a failed request for another language.
        ValueError: ``board`` is not a subdomain.
    """
    token = board.strip().lower()
    logger.info("reading personio board %r", token)
    jobs = {job["id"]: job for job in await _feed(fetcher, token)}
    for language in LANGUAGES:
        blank = [posting for posting, job in jobs.items() if "description" not in job]
        if not blank:
            break
        missing = ngettext("%d posting", "%d postings", len(blank)) % len(blank)
        logger.info("reading the %s feed for %s without a description", language, missing)
        try:
            other = {job["id"]: job for job in await _feed(fetcher, token, language)}
        except Stopped as stopped:
            count = ngettext("%d posting", "%d postings", len(jobs)) % len(jobs)
            raise Stopped(
                f"{stopped}. Kept the {count} read, {len(blank)} without a description",
                partial=list(jobs.values()),
            ) from stopped
        described = [posting for posting in blank if "description" in other.get(posting, {})]
        jobs |= {posting: other[posting] for posting in described}
    return list(jobs.values())


__all__ = ["search"]
