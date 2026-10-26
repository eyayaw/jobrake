"""Look up Indeed employer keys by company name."""

import json
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher
from jobrake.models import Stopped

from .client import AUTOCOMPLETE_HEADERS
from .countries import indeed_domain

COMPANY_URL = "https://autocomplete.indeed.com/api/v0/suggestions/company"


async def companies(fetcher: Fetcher, name: str, country: str) -> list[dict[str, str]]:
    """
    Find company names and employer keys through an Indeed edition's autocomplete.

    Each dictionary contains an ``employerKey`` and a company name in ``suggestion``.
    Both are nonblank strings with surrounding whitespace removed. Malformed
    entries are skipped, and the remaining suggestions keep their original order.
    An empty suggestion list returns ``[]``. The caller owns ``fetcher``.

    Raises:
        Stopped: The request failed, or the response held no readable suggestion.
        ValueError: The name is blank or the country edition is unknown.
    """
    name = name.strip()
    if not name:
        raise ValueError("company name is blank. Try 'ABN AMRO'")
    _, code = indeed_domain(country)
    params = urlencode(
        {"query": name, "country": code, "language": "en", "count": 10, "rich": "true"}
    )
    result = await fetcher.fetch(f"{COMPANY_URL}?{params}", headers=AUTOCOMPLETE_HEADERS)
    if result.error:
        raise Stopped(
            f"company lookup for {name!r} failed: {result.error}. Try again later", partial=[]
        )
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    unreadable = f"could not read Indeed's company suggestions for {name!r}. Try again later"
    if not isinstance(hits, list):
        raise Stopped(unreadable, partial=[])
    candidates = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        key, suggestion = hit.get("employerKey"), hit.get("suggestion")
        if (
            isinstance(key, str)
            and key.strip()
            and isinstance(suggestion, str)
            and suggestion.strip()
        ):
            candidates.append({"employerKey": key.strip(), "suggestion": suggestion.strip()})
    if hits and not candidates:
        raise Stopped(unreadable, partial=[])
    return candidates
