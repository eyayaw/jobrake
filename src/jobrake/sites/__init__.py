"""Supported sites and the public ``scrape`` entrypoint."""

from collections.abc import Callable

from jobrake.fetchkit import HttpxFetcher

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

    ``fetcher`` accepts any ``jobrake.fetchkit.Fetcher`` (injected fetchers are
    not closed here—the caller owns their lifecycle); indeed needs the
    ``PostFetcher`` variant. The default :class:`HttpxFetcher` qualifies for
    every site.

    Indeed requires ``country``, LinkedIn requires ``location``.
    In LinkedIn, posting attributes for ``detail`` are hydrated from the posting page, and
    ``cache`` reuses fresh hydration results.
    """
    searchers = site_searchers()
    if site not in searchers:
        raise ValueError(f"unknown site {site!r}; expected one of {sorted(searchers)}")
    if site == "linkedin":
        if location is None:
            raise ValueError(
                f"location is required for site='{site}' (pass e.g. 'London, England')"
            )
    elif site == "indeed":
        if country is None:
            raise ValueError(f"country is required for site='{site}' (pass e.g. 'usa', 'germany')")

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
