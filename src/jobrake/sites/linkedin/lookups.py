"""Look up LinkedIn place and company IDs by name through the guest typeahead."""

from typing import Annotated, Any
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher
from jobrake.sites.responses import json_list, read_json
from jobrake.utils import as_dict, as_str, checked

from . import client


def _candidates(hits: Any) -> list[dict[str, str]]:  # noqa: ANN401  any decoded JSON, which json_list checks
    """
    Read the typeahead hits that ``search`` can use, those with a numeric ID and a name.

    Raises:
        TypeError: The response is not a list, or it has hits and none is usable.
    """
    candidates = []
    for hit in map(as_dict, json_list(hits)):
        hit_id, name = ((as_str(hit.get(key)) or "").strip() for key in ("id", "displayName"))
        if client.numeric(hit_id) and name:
            candidates.append({"id": hit_id, "name": name})
    if hits and not candidates:
        raise TypeError("no hit has a numeric id and a displayName")
    return candidates


async def _typeahead(fetcher: Fetcher, kind: str, name: str) -> list[dict[str, str]]:
    """
    Ask the paced guest typeahead for ``kind`` hits on ``name``, keeping LinkedIn's order.

    Raises:
        Stopped: The request failed, or the response held no readable hit.
    """
    query = urlencode({"query": name.strip(), "typeaheadType": kind})
    result = await client.paced_fetch(fetcher, f"{client.TYPEAHEAD_URL}?{query}")
    return read_json(result, _candidates, site="linkedin")


@checked
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


@checked
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
