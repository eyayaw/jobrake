"""Supported sites and the public ``scrape`` entrypoint."""

from types import ModuleType

from jobrake.fetchkit import Fetcher, HttpxFetcher
from jobrake.models import JobDict

from . import indeed, linkedin

# One entry per site. A site package exports search() and any of the lookups and postings().
SITES: dict[str, ModuleType] = {"indeed": indeed, "linkedin": linkedin}


async def scrape(site: str, *, fetcher: Fetcher | None = None, **options: object) -> list[JobDict]:
    """
    Search one site and return its postings as ``JobDict`` records.

    ``options`` are the keyword options of ``jobrake.sites.<site>.search``,
    which checks them against its signature before any request. Without ``fetcher``,
    ``scrape`` creates and closes an ``HttpxFetcher``. A given fetcher stays
    open and belongs to the caller.

    Raises:
        TypeError: An option is unknown to the site, a required option is
            missing, or a value has the wrong type.
        ValueError: The site is unknown, or an option value is out of range
            or unusable on the site.
    """
    if site not in SITES:
        raise ValueError(f"unknown site {site!r}. Expected one of {', '.join(SITES)}")
    search = SITES[site].search
    if fetcher is not None:
        return await search(fetcher, **options)
    fetcher = HttpxFetcher()
    try:
        return await search(fetcher, **options)
    finally:
        await fetcher.close()


__all__ = ["SITES", "scrape"]
