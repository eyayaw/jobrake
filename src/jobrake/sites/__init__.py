"""Supported sites and the public ``scrape`` entrypoint."""

from collections.abc import Callable

from jobrake.fetchkit import Fetcher, HttpxFetcher
from jobrake.utils import check_distance, check_hours_old, check_results_wanted

from . import indeed, linkedin


def site_searchers() -> dict[str, Callable]:
    """Map supported site names to their search entrypoints."""
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
    fetcher: Fetcher | None = None,
) -> list[dict]:
    """
    Route a search through one provider.

    Indeed requires ``country``. LinkedIn requires a nonblank ``location``.
    ``detail`` and ``cache`` affect LinkedIn only. Every returned dictionary
    has the shared identity and summary keys, with available detail fields added.

    An injected fetcher remains open and belongs to the caller. Indeed requires
    one with JSON POST support. Without an injected fetcher, ``scrape`` creates
    and closes an ``HttpxFetcher``.

    Raises:
        ValueError: A site is unknown, a required location or country is
            missing, or a numeric search argument is outside its valid range.
    """
    searchers = site_searchers()
    if site not in searchers:
        raise ValueError(f"unknown site {site!r}. Expected one of {sorted(searchers)}")
    if site == "linkedin":
        if location is None or not location.strip():
            raise ValueError(f"location is required for site='{site}'. Try 'London, England'")
    elif site == "indeed":
        if country is None:
            raise ValueError(f"country is required for site='{site}'. Try 'usa' or 'germany'")
    check_results_wanted(results_wanted)
    check_distance(distance)
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
