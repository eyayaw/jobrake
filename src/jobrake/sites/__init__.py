"""Supported sites and the public ``scrape`` entrypoint."""

from collections.abc import Callable

from jobrake import defaults
from jobrake.fetchkit import Fetcher, HttpxFetcher
from jobrake.utils import check_max_age_hours, check_radius, check_results

from . import indeed, linkedin


def site_searchers() -> dict[str, Callable]:
    """Map supported site names to their search entrypoints."""
    return {"indeed": indeed.search, "linkedin": linkedin.search}


async def scrape(
    site: str,
    *,
    query: str,
    location: str | None = None,
    country: str | None = None,
    radius: int | None = None,
    results: int = defaults.RESULTS,
    max_age_hours: int | None = defaults.MAX_AGE_HOURS,
    details: bool = defaults.DETAILS,
    cache: bool = defaults.CACHE,
    fetcher: Fetcher | None = None,
) -> list[dict]:
    """
    Route a search through one provider.

    Indeed requires ``country``. LinkedIn requires a nonblank ``location``.
    ``details`` and ``cache`` affect LinkedIn only. Every returned dictionary
    has the shared identity and summary keys, with available detail fields added.
    Searches default to the last seven days. ``max_age_hours=None`` removes the age limit.
    A ``None`` radius uses Indeed's standard radius and omits LinkedIn's
    undocumented distance parameter.

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
    check_results(results)
    check_radius(radius)
    check_max_age_hours(max_age_hours)

    owns_fetcher = fetcher is None
    if owns_fetcher:
        fetcher = HttpxFetcher()
    options = {
        "query": query,
        "location": location,
        "country": country,
        "radius": radius,
        "results": results,
        "max_age_hours": max_age_hours,
        "details": details,
        "cache": cache,
    }
    try:
        return await searchers[site](fetcher, **options)
    finally:
        if owns_fetcher:
            await fetcher.close()
