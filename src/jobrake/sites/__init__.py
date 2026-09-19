"""Supported sites and the public ``scrape`` entrypoint."""

from collections.abc import Callable

from jobrake import defaults
from jobrake.fetchkit import Fetcher, HttpxFetcher
from jobrake.utils import (
    check_attributes,
    check_bounds,
    check_companies,
    check_flags,
    check_language,
)

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
    companies: list[str] | None = None,
    remote: bool = False,
    language: str | None = None,
    attributes: list[str] | None = None,
    easy_apply: bool = False,
    early_applicant: bool = False,
    fetcher: Fetcher | None = None,
) -> list[dict]:
    """
    Route a search through one provider.

    Indeed requires ``country``. LinkedIn requires either a ``location`` or a geoId string.
    ``companies`` restricts LinkedIn results to jobs at the listed employer numeric IDs.
    ``None`` or ``[]`` applies no company restriction. Indeed ignores ``companies``.
    ``remote=True`` restricts Indeed results to postings tagged Remote.
    ``False`` leaves remote status unrestricted. LinkedIn requires ``remote=False``.
    ``details``, ``cache``, and ``geoid`` affect LinkedIn only.
    ``geoid=True`` resolves ``location`` to a LinkedIn geoId before searching, and a string passes through as the geoId.
    Every returned dict has the shared identity and summary keys, with available detail fields added.
    Searches ask the provider for jobs from the past seven days by default. ``max_age_hours=None`` omits the age filter.
    A ``None`` radius uses Indeed's standard radius and omits LinkedIn's undocumented distance parameter.
    ``language`` restricts Indeed postings to the provider's language code,
    supplied as two ASCII letters in either case. The code is sent to Indeed in lowercase.
    ``None`` omits the restriction. LinkedIn ignores ``language``.
    ``attributes`` selects Indeed postings carrying every supplied attribute code.
    Pass a list of nonblank strings. Surrounding whitespace is stripped from each code.
    ``None`` and ``[]`` omit this restriction.
    LinkedIn ignores ``attributes``.
    ``easy_apply=True`` selects LinkedIn jobs with Easy Apply.
    ``early_applicant=True`` asks LinkedIn for jobs with fewer than 10 applicants.
    Both default to ``False``. Indeed ignores them.

    One signature covers both providers, so a caller can send the same options
    to each. A provider applies the filters it supports and warns for the rest.
    An ignored value goes unvalidated.

    An injected fetcher remains open and belongs to the caller. Indeed requires one with JSON POST support.
    Without an injected fetcher, ``scrape`` creates and closes an ``HttpxFetcher``.

    Raises:
        TypeError: A numeric argument or Boolean filter has the wrong type, company IDs
            are not supplied as a list of strings, or Indeed language or attribute filters
            have the wrong type.
        ValueError: The site is unknown, required geography is missing, a numeric
            argument is out of range, a company ID is blank or malformed,
            too many company IDs are supplied, an attribute code is blank,
            or the Indeed language code is malformed.
    """
    searchers = site_searchers()
    if site not in searchers:
        raise ValueError(f"unknown site {site!r}. Expected one of {sorted(searchers)}")
    check_flags(remote=remote, easy_apply=easy_apply, early_applicant=early_applicant)
    check_companies(companies, site=site)
    if site == "linkedin":
        if isinstance(geoid, str) and not geoid.strip():
            raise ValueError("geoid is blank")
        if not isinstance(geoid, str) and (location is None or not location.strip()):
            raise ValueError(
                f"location is required for site='{site}' unless geoid is an ID. Try 'London, England'"
            )
    elif site == "indeed":
        check_language(language)
        check_attributes(attributes)
        if country is None:
            raise ValueError(f"country is required for site='{site}'. Try 'usa' or 'germany'")
    check_bounds(results=results, radius=radius, max_age_hours=max_age_hours)

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
        "companies": companies,
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
