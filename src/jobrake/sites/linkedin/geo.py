"""Resolve place names to LinkedIn geoIds."""

import json
import logging
import re
from urllib.parse import urlencode

from jobrake.cache import GEOIDS
from jobrake.fetchkit import Fetcher

from . import client

logger = logging.getLogger(__name__)

TYPEAHEAD_URL = f"{client.BASE_URL}/jobs-guest/api/typeaheadHits"


def _name_key(name: str) -> str:
    text = " ".join(name.casefold().replace(",", " ").split())
    return re.sub(r"^[\W_]+|[\W_]+$", "", text)


def _parse_place(geoid: object, display: object) -> tuple[str, str] | None:
    if not (isinstance(geoid, str) and isinstance(display, str)):
        return None
    geoid, display = geoid.strip(), display.strip()
    return (geoid, display) if geoid and _name_key(display) else None


def _saved(name: str) -> tuple[str, str] | None:
    entry = client.CACHE.get(GEOIDS, "linkedin", [name]).get(name)
    if not isinstance(entry, dict):
        return None
    return _parse_place(entry.get("geoId"), entry.get("displayName"))


async def places(fetcher: Fetcher, name: str) -> list[dict] | None:
    """
    List LinkedIn's candidate places for a name, best match first.

    Asks the guest GEO typeahead, paced through the shared limiter, and
    returns up to ten ``{"geoId", "displayName"}`` dicts, omitting candidates
    without both strings intact. An empty list means LinkedIn knows no such
    place. A failed request or an unreadable response logs the reason and
    returns ``None``. Valid candidates seed the SQLite cache by qualified name,
    and the first candidate also uses the normalized query.

    Raises:
        ValueError: The name is blank.
    """
    name_key = _name_key(name)
    if not name_key:
        raise ValueError(f"place name {name!r} is blank. Try 'amsterdam'")
    query = urlencode({"query": name.strip(), "typeaheadType": "GEO"})
    result = await client.paced_fetch(fetcher, f"{TYPEAHEAD_URL}?{query}")
    if result.error:
        logger.warning("geoId lookup for %r failed: %s", name, result.error.message)
        return None
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    if not isinstance(hits, list):
        logger.warning("geoId lookup for %r returned an unreadable response", name)
        return None
    candidates = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        place = _parse_place(hit.get("id"), hit.get("displayName"))
        if place is None:
            continue
        geoid, display = place
        candidates.append({"geoId": geoid, "displayName": display})
    if hits and not candidates:
        logger.warning("geoId lookup for %r returned an unreadable response", name)
        return None
    if candidates:
        saved = {}
        for candidate in candidates:
            saved.setdefault(_name_key(candidate["displayName"]), candidate)
        saved[name_key] = candidates[0]
        client.CACHE.put(GEOIDS, "linkedin", saved)
    return candidates


async def resolve_geoid(fetcher: Fetcher, location: str) -> str | None:
    """
    Resolve a place name to the geoId LinkedIn itself would pick for it.

    A saved name resolves from the SQLite cache. Any other name goes through
    :func:`places`, and the first hit becomes the answer for later runs. Every
    resolution logs the geoId and qualified place name. When the lookup fails
    or LinkedIn knows no such place, this logs the reason and returns ``None``.

    Raises:
        ValueError: The location is blank.
    """
    name = _name_key(location)
    if not name:
        raise ValueError(f"place name {location!r} is blank. Try 'amsterdam'")
    if entry := _saved(name):
        geoid, display = entry
    else:
        hits = await places(fetcher, location)
        if hits is None:
            return None
        if not hits:
            logger.warning("linkedin knows no place named %r; check the spelling", location)
            return None
        geoid, display = hits[0]["geoId"], hits[0]["displayName"]
    logger.info("resolved %r to geoId %s (%s)", location, geoid, display)
    return geoid
