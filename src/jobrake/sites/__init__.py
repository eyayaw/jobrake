"""Supported sites and the public ``scrape`` entrypoint."""

from collections.abc import Callable

from jobrake import defaults
from jobrake.fetchkit import Fetcher, HttpxFetcher

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
    geoid: str | bool = defaults.GEOID,
    company_ids: list[str] | None = None,
    employer_key: str | None = None,
    remote: bool = False,
    language: str | None = None,
    attributes: list[str] | None = None,
    easy_apply: bool = False,
    early_applicant: bool = False,
    fetcher: Fetcher | None = None,
) -> list[dict]:
    """
    Route a search through one provider.

    Both providers take ``query``, ``location``, ``radius`` in kilometers, ``results``, and ``max_age_hours``.
    Searches cover the past seven days by default, and ``max_age_hours=None`` lifts the age limit.
    Indeed requires ``country`` and applies ``employer_key``, ``remote``, ``language``, and ``attributes``.
    LinkedIn requires a ``location`` or a geoId string and applies ``geoid``, ``company_ids``, ``easy_apply``, ``early_applicant``, ``details``, and ``cache``.
    Each provider's ``search`` documents the values its options accept.

    One signature covers both providers, so a caller can send the same options
    to each. A provider warns for a filter it cannot apply and leaves that
    filter unchecked, so a wrong type there cannot stop the search.

    Every returned dict has the shared identity and summary keys, with available detail fields added.
    The provider validates its arguments before the first request.
    An injected fetcher remains open and belongs to the caller. Indeed requires one with JSON POST support.
    Without an injected fetcher, ``scrape`` creates and closes an ``HttpxFetcher``.

    Raises:
        TypeError: An argument the provider applies has the wrong type.
        ValueError: The site is unknown, required geography is missing, or an
            argument the provider applies has an unusable value.
    """
    searchers = site_searchers()
    if site not in searchers:
        raise ValueError(f"unknown site {site!r}. Expected one of {sorted(searchers)}")
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
        "geoid": geoid,
        "company_ids": company_ids,
        "employer_key": employer_key,
        "remote": remote,
        "language": language,
        "attributes": attributes,
        "easy_apply": easy_apply,
        "early_applicant": early_applicant,
    }
    try:
        return await searchers[site](fetcher, **options)
    finally:
        if owns_fetcher:
            await fetcher.close()
