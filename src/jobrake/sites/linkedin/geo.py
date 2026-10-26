"""Look up LinkedIn geoIds by place name."""

import json
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher
from jobrake.models import Stopped

from . import client


def _parse_place(geoid: object, display: object) -> dict[str, str] | None:
    if not (isinstance(geoid, str) and isinstance(display, str)):
        return None
    geoid, display = geoid.strip(), display.strip()
    return {"geoId": geoid, "displayName": display} if geoid and display else None


async def places(fetcher: Fetcher, name: str) -> list[dict[str, str]]:
    """
    List LinkedIn's candidate places for a name, best match first.

    Asks the guest GEO typeahead, paced through the shared limiter, and
    returns up to ten ``{"geoId", "displayName"}`` dicts, omitting candidates
    without both strings intact. An empty list means LinkedIn knows no such
    place.

    Raises:
        Stopped: The request failed, or the response held no readable place.
        ValueError: The name is blank.
    """
    name = name.strip()
    if not name:
        raise ValueError("place name is blank. Try 'amsterdam'")
    unreadable = f"geoId lookup for {name!r} returned an unreadable response. Try again later"
    query = urlencode({"query": name, "typeaheadType": "GEO"})
    result = await client.paced_fetch(fetcher, f"{client.TYPEAHEAD_URL}?{query}")
    if result.error:
        raise Stopped(
            f"geoId lookup for {name!r} failed: {result.error}. Try again later", partial=[]
        )
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    if not isinstance(hits, list):
        raise Stopped(unreadable, partial=[])
    candidates = [
        place
        for hit in hits
        if isinstance(hit, dict) and (place := _parse_place(hit.get("id"), hit.get("displayName")))
    ]
    if hits and not candidates:
        raise Stopped(unreadable, partial=[])
    return candidates
