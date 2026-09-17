"""Find LinkedIn company IDs by name."""

import json
import logging
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher

from . import client

logger = logging.getLogger(__name__)


async def companies(fetcher: Fetcher, name: str) -> list[dict] | None:
    """
    List LinkedIn's company suggestions for a name.

    Each dict has a ``companyId`` string of digits 0-9 and a nonblank ``displayName``.
    Valid entries keep their order when malformed entries are omitted.
    An empty list means no suggestions returned. Request failures and unreadable responses,
    including nonempty lists with no usable entries, log a warning and return ``None``.

    Requests use the shared LinkedIn limiter. The caller owns ``fetcher``.

    Raises:
        ValueError: The name is blank.
    """
    name = name.strip()
    if not name:
        raise ValueError("company name is blank. Try 'ABN AMRO'")
    query = urlencode({"query": name, "typeaheadType": "COMPANY"})
    result = await client.paced_fetch(fetcher, f"{client.TYPEAHEAD_URL}?{query}")
    if result.error:
        logger.warning(
            "company lookup for %r failed: %s. Try again later", name, result.error.message
        )
        return None
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    if not isinstance(hits, list):
        logger.warning(
            "could not read LinkedIn's company suggestions for %r. Try again later", name
        )
        return None
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
        logger.warning(
            "could not read LinkedIn's company suggestions for %r. Try again later", name
        )
        return None
    return candidates
