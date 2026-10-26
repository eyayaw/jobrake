"""Find LinkedIn company IDs by name."""

import json
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher
from jobrake.models import Stopped

from . import client


async def companies(fetcher: Fetcher, name: str) -> list[dict[str, str]]:
    """
    List LinkedIn's company suggestions for a name.

    Each dict has a ``companyId`` string of digits 0-9 and a nonblank ``displayName``.
    Valid entries keep their order when malformed entries are omitted.
    An empty list means LinkedIn returned no suggestions.

    Requests use the shared LinkedIn limiter. The caller owns ``fetcher``.

    Raises:
        Stopped: The request failed, or the response held no readable suggestion.
        ValueError: The name is blank.
    """
    name = name.strip()
    if not name:
        raise ValueError("company name is blank. Try 'ABN AMRO'")
    unreadable = f"could not read LinkedIn's company suggestions for {name!r}. Try again later"
    query = urlencode({"query": name, "typeaheadType": "COMPANY"})
    result = await client.paced_fetch(fetcher, f"{client.TYPEAHEAD_URL}?{query}")
    if result.error:
        raise Stopped(
            f"company lookup for {name!r} failed: {result.error}. Try again later", partial=[]
        )
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    if not isinstance(hits, list):
        raise Stopped(unreadable, partial=[])
    candidates = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        company_id, display = hit.get("id"), hit.get("displayName")
        if not (isinstance(company_id, str) and isinstance(display, str)):
            continue
        company_id, display = company_id.strip(), display.strip()
        if company_id.isascii() and company_id.isdigit() and display:
            candidates.append({"companyId": company_id, "displayName": display})
    if hits and not candidates:
        raise Stopped(unreadable, partial=[])
    return candidates
