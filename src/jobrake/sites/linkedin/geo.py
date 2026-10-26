"""Look up LinkedIn geoIds by place name."""

import json
import logging
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher

from . import client

logger = logging.getLogger(__name__)


def _parse_place(geoid: object, display: object) -> dict[str, str] | None:
    if not (isinstance(geoid, str) and isinstance(display, str)):
        return None
    geoid, display = geoid.strip(), display.strip()
    return {"geoId": geoid, "displayName": display} if geoid and display else None


async def places(fetcher: Fetcher, name: str) -> list[dict[str, str]] | None:
    """
    List LinkedIn's candidate places for a name, best match first.

    Asks the guest GEO typeahead, paced through the shared limiter, and
    returns up to ten ``{"geoId", "displayName"}`` dicts, omitting candidates
    without both strings intact. An empty list means LinkedIn knows no such
    place. A failed request or an unreadable response logs the reason and
    returns ``None``.

    Raises:
        ValueError: The name is blank.
    """
    name = name.strip()
    if not name:
        raise ValueError("place name is blank. Try 'amsterdam'")
    query = urlencode({"query": name, "typeaheadType": "GEO"})
    result = await client.paced_fetch(fetcher, f"{client.TYPEAHEAD_URL}?{query}")
    if result.error:
        logger.warning("geoId lookup for %r failed: %s", name, result.error)
        return None
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    if not isinstance(hits, list):
        logger.warning("geoId lookup for %r returned an unreadable response", name)
        return None
    candidates = [
        place
        for hit in hits
        if isinstance(hit, dict) and (place := _parse_place(hit.get("id"), hit.get("displayName")))
    ]
    if hits and not candidates:
        logger.warning("geoId lookup for %r returned an unreadable response", name)
        return None
    return candidates
