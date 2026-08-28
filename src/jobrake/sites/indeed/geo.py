"""Resolve place names to Indeed's canonical location suggestions."""

import json
import logging
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher

from .countries import indeed_domain

logger = logging.getLogger(__name__)

AUTOCOMPLETE_URL = "https://autocomplete.indeed.com/api/v0/suggestions/location"

# The autocomplete backs indeed.com's search box and expects browser
# headers, unlike the app-keyed GraphQL API.
HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://www.indeed.com",
    "referer": "https://www.indeed.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


async def places(fetcher: Fetcher, name: str, country: str) -> list[dict] | None:
    """
    List Indeed's location suggestions for a name in one country edition, best match first.

    ``country`` is an edition name or alias, as in search. Asks the search
    box's autocomplete service and returns up to ten
    ``{"suggestion", "locationType"}`` dicts, omitting candidates without a
    suggestion string. A suggestion is the exact string the edition's search
    geocodes, ready to use as ``location``. ``locationType`` names the kind of
    match: ``CITY``, ``ADMIN1`` for a state or province, ``POSTAL_PLACE``,
    ``MISC`` for landmarks, and similar. An empty list means the edition
    offers no such place. A failed request or an unreadable response logs the
    reason and returns ``None``.

    Raises:
        ValueError: The name is blank, or the country name or alias is unknown.
    """
    if not name.strip():
        raise ValueError(f"place name {name!r} is blank. Try 'boston'")
    _, code = indeed_domain(country)
    params = urlencode(
        {
            "country": code,
            "language": "en",
            "count": 10,
            "formatted": 1,
            "rich": "true",
            "query": name.strip(),
        }
    )
    result = await fetcher.fetch(f"{AUTOCOMPLETE_URL}?{params}", headers=HEADERS)
    if result.error:
        logger.warning("location lookup for %r failed: %s", name, result.error.message)
        return None
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    if not isinstance(hits, list):
        logger.warning("location lookup for %r returned an unreadable response", name)
        return None
    candidates = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        suggestion = hit.get("suggestion")
        if not isinstance(suggestion, str):
            continue
        suggestion = suggestion.strip()
        if not suggestion:
            continue
        payload = hit.get("payload")
        kind = payload.get("locationType") if isinstance(payload, dict) else None
        kind = (kind.strip() or None) if isinstance(kind, str) else None
        candidates.append({"suggestion": suggestion, "locationType": kind})
    if hits and not candidates:
        logger.warning("location lookup for %r returned an unreadable response", name)
        return None
    return candidates
