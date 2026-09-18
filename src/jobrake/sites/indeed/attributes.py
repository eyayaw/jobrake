"""Discover Indeed attribute codes from matching job postings."""

import json
import logging

from jobrake.fetchkit import PostFetcher

from .client import API_HEADERS, API_URL
from .countries import indeed_domain

logger = logging.getLogger(__name__)

QUERY = """
query {{
  jobSearch(what: {query}, limit: 100, sort: RELEVANCE) {{
    results {{ job {{ attributes {{ key label }} }} }}
  }}
}}
"""


async def attributes(fetcher: PostFetcher, query: str, country: str) -> list[dict] | None:
    """
    Collect attribute codes and labels from the first 100 matching Indeed jobs.

    The country selects the edition. The search has no posting-age restriction.
    Each dictionary pairs a ``key`` with its ``label``. Codes appear once, in
    first-seen order. Different codes with the same label remain separate.
    Labels come from Indeed and can vary by edition. Malformed entries are skipped.
    A search with no attributes returns ``[]``. A failed request or unreadable
    response returns ``None`` and logs a warning. The caller owns ``fetcher``.

    Raises:
        ValueError: The query is blank or the country edition is unknown.
    """
    query = query.strip()
    if not query:
        raise ValueError("attribute lookup query is blank. Try 'data scientist'")
    _, code = indeed_domain(country)
    result = await fetcher.post(
        API_URL,
        {"query": QUERY.format(query=json.dumps(query))},
        headers={**API_HEADERS, "indeed-co": code},
    )
    if result.error:
        logger.warning(
            "attribute lookup for %r failed: %s. Try again later", query, result.error.message
        )
        return None
    try:
        hits = json.loads(result.text)["data"]["jobSearch"]["results"]
        if not isinstance(hits, list):
            raise TypeError("results must be a list")
    except (ValueError, KeyError, TypeError):
        logger.warning("could not read Indeed's attributes for %r. Try again later", query)
        return None
    candidates = {}
    malformed = False
    for hit in hits:
        try:
            entries = hit["job"]["attributes"]
            if not isinstance(entries, list):
                raise TypeError("attributes must be a list")
        except (KeyError, TypeError):
            malformed = True
            continue
        for entry in entries:
            if isinstance(entry, dict):
                key, label = entry.get("key"), entry.get("label")
                if (
                    isinstance(key, str)
                    and key.strip()
                    and isinstance(label, str)
                    and label.strip()
                ):
                    candidates.setdefault(key.strip(), {"key": key.strip(), "label": label.strip()})
                    continue
            malformed = True
    if malformed and not candidates:
        logger.warning("could not read Indeed's attributes for %r. Try again later", query)
        return None
    return list(candidates.values())
