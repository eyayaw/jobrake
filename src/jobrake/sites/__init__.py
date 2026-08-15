"""One package per site, the table of supported sites, and the ``scrape`` entrypoint."""

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
    fetch_description: bool = False,
    cache: bool = True,
    fetcher=None,
) -> list[dict]:
    """
    Scrape one site; returns plain job dicts.

    ``fetcher`` accepts any ``jobrake.fetchkit.Fetcher`` (injected fetchers are
    not closed here—the caller owns their lifecycle); indeed needs the
    ``PostFetcher`` variant. The default :class:`HttpxFetcher` qualifies for
    every site.

    ``country`` is required for indeed, ignored by linkedin.
    ``location`` is required for linkedin, optional for indeed.
    ``fetch_description`` (linkedin) hydrates each job from its posting
    page—the description and every other field the posting states—at one
    extra paced request per job; indeed's search response already carries
    everything it knows, so the flag is a no-op there.
    ``cache`` (linkedin) serves still-fresh postings from an on-disk cache
    in the user cache directory instead of refetching (freshness window:
    ``jobrake.cache.TTL``).
    """
    searchers = site_searchers()
    if site not in searchers:
        raise ValueError(f"unknown site {site!r}; expected one of {sorted(searchers)}")

    owns_fetcher = fetcher is None
    fetcher = fetcher or HttpxFetcher()
    kwargs = dict(
        search_term=search_term,
        location=location,
        country=country,
        distance=distance,
        results_wanted=results_wanted,
        hours_old=hours_old,
        fetch_description=fetch_description,
        cache=cache,
    )
    if site == "linkedin":
        if location is None:
            raise ValueError(
                f"location is required for site='{site}' (pass e.g. 'London, England')"
            )
    elif site == "indeed":
        if country is None:
            raise ValueError(f"country is required for site='{site}' (pass e.g. 'usa', 'germany')")
    try:
        return await searchers[site](fetcher, **kwargs)
    finally:
        if owns_fetcher:
            await fetcher.close()
