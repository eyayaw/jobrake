"""Supported sites and the public ``scrape``, ``check``, and ``identify`` functions."""

import contextlib
from types import ModuleType

from jobrake.fetchkit import Fetcher, HttpxFetcher
from jobrake.models import JobDict
from jobrake.utils import Checked

from . import (
    academictransfer,
    adzuna,
    aea,
    ashby,
    cornerstone,
    econjobmarket,
    greenhouse,
    indeed,
    inomics,
    lever,
    linkedin,
    personio,
    reliefweb,
    smartrecruiters,
    stepstone,
    uncareers,
    workable,
    workday,
    xing,
)

# One entry per site. A site exports search() and any of the lookups and postings().
SITES: dict[str, ModuleType] = {
    "academictransfer": academictransfer,
    "adzuna": adzuna,
    "aea": aea,
    "ashby": ashby,
    "cornerstone": cornerstone,
    "econjobmarket": econjobmarket,
    "greenhouse": greenhouse,
    "indeed": indeed,
    "inomics": inomics,
    "lever": lever,
    "linkedin": linkedin,
    "personio": personio,
    "reliefweb": reliefweb,
    "smartrecruiters": smartrecruiters,
    "stepstone": stepstone,
    "uncareers": uncareers,
    "workable": workable,
    "workday": workday,
    "xing": xing,
}


def _search(site: str) -> Checked[..., list[JobDict]]:
    if site not in SITES:
        raise ValueError(f"unknown site {site!r}. Expected one of {', '.join(SITES)}")
    return SITES[site].search


async def scrape(site: str, *, fetcher: Fetcher | None = None, **options: object) -> list[JobDict]:
    """
    Search one site and return its postings as ``JobDict`` records.

    ``options`` are the keyword options of ``jobrake.sites.<site>.search``, which checks them as
    ``check`` does before any request. Without ``fetcher``, ``scrape`` creates and closes an
    ``HttpxFetcher``. A given fetcher stays open and belongs to the caller.

    Raises:
        TypeError: An option is unknown to the site, a required option is missing,
            or a value has the wrong type.
        ValueError: The site is unknown, or an option value is out of range or unusable on the site.
        Stopped: The search could not finish. ``partial`` holds the postings it collected.
    """
    search = _search(site)
    if fetcher is not None:
        return await search(fetcher, **options)
    async with HttpxFetcher() as own:
        return await search(own, **options)


def check(site: str, **options: object) -> None:
    """
    Raise the ``TypeError`` or ``ValueError`` that ``scrape`` would raise before its first request.

    It sends no request and needs no event loop, so a caller can check every planned search
    before the first one runs. A value that only the site's live catalog can confirm, such as a UN
    Careers duty station, passes, and the search refuses it after reading that catalog.
    """
    _search(site).check(**options)


def identify(link: str) -> tuple[str, str] | None:
    """
    Return the ``(site, id)`` pair for a posting link, or None if unrecognized.

    Sends no network requests; checks the link against each supported site's URL parser.
    """
    for module in SITES.values():
        if read := getattr(module, "card", None):
            with contextlib.suppress(ValueError):
                job = read(link)
                return job["site"], job["id"]
    return None


__all__ = ["SITES", "check", "identify", "scrape"]
