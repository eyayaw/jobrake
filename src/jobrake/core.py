"""Shared plumbing: job normalization and the per-site dispatch."""

from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup
from jobrake.fetchkit import HttpxFetcher


def html_text(html: str) -> str:
    """Plain text from an HTML fragment (descriptions arrive as HTML)."""
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def epoch_ms_to_date(ms) -> str:
    """``YYYY-MM-DD`` (UTC) from epoch milliseconds; ``""`` if unparseable."""
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def make_job(
    *,
    id: str,
    title: str,
    company: str,
    url: str,
    site: str,
    location: str,
    description: str = "",
    date: str = "",
) -> dict:
    """
    Normalize scraped fields into the job dict.

    ``id`` is the site-local posting identifier (LinkedIn's numeric posting
    id, Indeed's job key): stable per posting, unique only within a site.
    """
    return {
        "id": (id or "").strip(),
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "url": (url or "").strip(),
        "location": (location or "").strip(),
        "description": (description or "").strip(),
        "date": (date or "")[:10],
        "site": site,
    }


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
    ``fetch_description`` costs one extra paced request per job, every call, on linkedin
    (indeed always includes descriptions); for repeated searches
    call ``linkedin.fetch_descriptions`` on just the new ids instead.
    """
    from jobrake import indeed, linkedin

    searches = {"indeed": indeed.search, "linkedin": linkedin.search}
    if site not in searches:
        raise ValueError(f"unknown site {site!r}; expected one of {sorted(searches)}")

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
        return await searches[site](fetcher, **kwargs)
    finally:
        if owns_fetcher:
            await fetcher.close()
