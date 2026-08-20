"""Supported sites and the public ``scrape`` entrypoint."""

from collections.abc import Callable

from jobrake.fetchkit import HttpxFetcher
from jobrake.utils import check_hours_old

from . import indeed, linkedin


def site_searchers() -> dict[str, Callable]:
    """Every supported site, mapped to its package's ``search``."""
    return {"indeed": indeed.search, "linkedin": linkedin.search}


async def scrape(
    site: str,
    *,
    search_term: str,
    location: str | None = None,
    country: str | None = None,
    distance: int | None = None,
    results_wanted: int = 25,
    hours_old: int | None = None,
    detail: bool = False,
    cache: bool = True,
    fetcher=None,
) -> list[dict]:
    """
    Scrape one site into unified job dicts.

    Every dict has the identity and summary keys. An unavailable summary value
    is ``None``. A detail key is present when a value is available.

    LinkedIn accepts a ``jobrake.fetchkit.Fetcher``. Indeed requires the
    ``PostFetcher`` variant. The caller owns an injected fetcher, so ``scrape``
    leaves it open. The default :class:`HttpxFetcher` works for every site.

    Indeed requires ``country``. LinkedIn requires ``location``. For LinkedIn,
    ``detail`` fetches fields from each posting page and ``cache`` reuses
    fresh results.
    """
    searchers = site_searchers()
    if site not in searchers:
        raise ValueError(f"unknown site {site!r}. Expected one of {sorted(searchers)}")
    if site == "linkedin":
        if location is None:
            raise ValueError(f"location is required for site='{site}'. Try 'London, England'")
    elif site == "indeed":
        if country is None:
            raise ValueError(f"country is required for site='{site}'. Try 'usa' or 'germany'")
    check_hours_old(hours_old)

    owns_fetcher = fetcher is None
    if owns_fetcher:
        fetcher = HttpxFetcher()
    options = {
        "search_term": search_term,
        "location": location,
        "country": country,
        "distance": distance,
        "results_wanted": results_wanted,
        "hours_old": hours_old,
        "detail": detail,
        "cache": cache,
    }
    try:
        return await searchers[site](fetcher, **options)
    finally:
        if owns_fetcher:
            await fetcher.close()
