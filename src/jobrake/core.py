"""
Shared plumbing: the POST-capable fetcher, job normalization, dispatch.

fetchkit's ``Fetcher`` protocol is GET-only; Indeed's GraphQL API needs POST.
:class:`HttpxPostFetcher` extends ``HttpxFetcher`` with a ``post`` that keeps the
same contract (a ``FetchResult``, never a raise). Callers may inject any
fetchkit fetcher instead—LinkedIn only GETs—but Indeed requires one with a
``post`` method.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup
from fetchkit import HttpxFetcher
from fetchkit.types import FetchResult, build_result


class HttpxPostFetcher(HttpxFetcher):
    """HttpxFetcher plus JSON POST, under the same never-raises contract."""

    async def post(self, url: str, json_body: dict, headers: dict | None = None) -> FetchResult:
        return await self._capture_result(url, lambda: self._post(url, json_body, headers))

    async def _post(self, url: str, json_body: dict, headers: dict | None) -> FetchResult:
        r = await self._client.post(url, json=json_body, headers=headers)
        return build_result(str(r.url), r.status_code, r.text, r.headers)


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
    title: str,
    company: str,
    url: str,
    site: str,
    location: str = "",
    description: str = "",
    date: str = "",
) -> dict:
    return {
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
    location: str = "",
    country: str = "usa",
    distance: int | None = None,
    results_wanted: int = 25,
    hours_old: int | None = None,
    linkedin_fetch_description: bool = False,
    fetcher=None,
) -> list[dict]:
    """
    Scrape one site; returns plain job dicts.

    ``fetcher`` accepts any fetchkit fetcher (injected fetchers are not closed
    here—the caller owns their lifecycle). Indeed needs one with a ``post``
    method; the default :class:`HttpxPostFetcher` provides it.
    """
    from jobrake import indeed, linkedin

    searches = {"indeed": indeed.search, "linkedin": linkedin.search}
    if site not in searches:
        raise ValueError(f"unknown site {site!r}; expected one of {sorted(searches)}")

    owns_fetcher = fetcher is None
    fetcher = fetcher or HttpxPostFetcher()
    kwargs = dict(
        search_term=search_term,
        location=location,
        distance=distance,
        results_wanted=results_wanted,
        hours_old=hours_old,
    )
    if site == "linkedin":
        kwargs["fetch_description"] = linkedin_fetch_description
    elif site == "indeed":
        kwargs["country"] = country
    try:
        return await searches[site](fetcher, **kwargs)
    finally:
        if owns_fetcher:
            await fetcher.close()
