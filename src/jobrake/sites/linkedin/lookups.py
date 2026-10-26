"""Look up LinkedIn place and company IDs by name through the guest typeahead."""

import json
from typing import Annotated
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher
from jobrake.models import Stopped

from . import client


def _candidate(hit: object) -> dict[str, str] | None:
    """Read one typeahead hit, which ``search`` can use only with a numeric ID and a name."""
    if not isinstance(hit, dict):
        return None
    hit_id, display = hit.get("id"), hit.get("displayName")
    if not (isinstance(hit_id, str) and isinstance(display, str)):
        return None
    hit_id, display = hit_id.strip(), display.strip()
    if not (hit_id.isascii() and hit_id.isdigit() and display):
        return None
    return {"id": hit_id, "name": display}


# Each typeahead kind with the noun and an example name for messages.
_KINDS = {"GEO": ("place", "amsterdam"), "COMPANY": ("company", "ABN AMRO")}


async def _typeahead(fetcher: Fetcher, kind: str, name: str) -> list[dict[str, str]]:
    """
    Ask the paced guest typeahead for ``kind`` hits on ``name``, keeping LinkedIn's order.

    Raises:
        Stopped: The request failed, or the response held no readable hit.
        ValueError: The name is blank.
    """
    noun, example = _KINDS[kind]
    name = name.strip()
    if not name:
        raise ValueError(f"{noun} name is blank. Try {example!r}")
    query = urlencode({"query": name, "typeaheadType": kind})
    result = await client.paced_fetch(fetcher, f"{client.TYPEAHEAD_URL}?{query}")
    if result.error:
        raise Stopped(
            f"{noun} lookup for {name!r} failed: {result.error}. Try again later", partial=[]
        )
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    candidates = [c for hit in hits if (c := _candidate(hit))] if isinstance(hits, list) else []
    if not isinstance(hits, list) or (hits and not candidates):
        raise Stopped(
            f"could not read LinkedIn's {noun} suggestions for {name!r}. Try again later",
            partial=[],
        )
    return candidates


async def places(
    fetcher: Fetcher, name: Annotated[str, "place name, e.g., 'amsterdam'"]
) -> list[dict[str, str]]:
    """
    List LinkedIn's places for a name, best match first.

    Each is an ``{"id", "name"}`` dict, and ``id`` is the geoId that ``search``
    takes as ``geoid``. LinkedIn sends up to ten. An empty list means
    LinkedIn knows no such place.

    Raises:
        Stopped: The request failed, or the response held no readable place.
        ValueError: The name is blank.
    """
    return await _typeahead(fetcher, "GEO", name)


async def companies(
    fetcher: Fetcher, name: Annotated[str, "company name, e.g., 'ABN AMRO'"]
) -> list[dict[str, str]]:
    """
    List LinkedIn's company suggestions for a name.

    Each is an ``{"id", "name"}`` dict, and ``id`` is a company ID that
    ``search`` takes in ``company_ids``. An empty list means LinkedIn returned
    no suggestions.

    Raises:
        Stopped: The request failed, or the response held no readable suggestion.
        ValueError: The name is blank.
    """
    return await _typeahead(fetcher, "COMPANY", name)
