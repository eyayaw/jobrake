"""Look up Indeed locations, employer keys, and attribute codes by name."""

import json
from typing import Annotated, Any
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher
from jobrake.models import Stopped
from jobrake.utils import checked

from .client import API_HEADERS, API_URL, AUTOCOMPLETE_HEADERS, AUTOCOMPLETE_URL
from .countries import Country, indeed_domain

ATTRIBUTES_QUERY = """
query {{
  jobSearch(what: {query}, limit: 100, sort: RELEVANCE) {{
    results {{ job {{ attributes {{ key label }} }} }}
  }}
}}
"""


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _candidate(hit: object, id_key: str, name_key: str) -> dict[str, str] | None:
    """Read one ``{"id", "name"}`` candidate from a hit's two fields, or None when either is blank."""
    if not isinstance(hit, dict):
        return None
    hit_id, name = _text(hit.get(id_key)), _text(hit.get(name_key))
    return {"id": hit_id, "name": name} if hit_id and name else None


# Each autocomplete kind: the noun for messages, the hit field that holds the
# ID, and the parameters it adds.
_KINDS: dict[str, tuple[str, str, dict[str, Any]]] = {
    "location": ("place", "suggestion", {"formatted": 1}),
    "company": ("company", "employerKey", {}),
}


async def _suggestions(
    fetcher: Fetcher, kind: str, name: str, country: str
) -> list[dict[str, str]]:
    """
    Ask an edition's search-box autocomplete for ``kind`` suggestions, keeping Indeed's order.

    Raises:
        Stopped: The request failed, or the response held no readable suggestion.
        ValueError: The country edition is unknown.
    """
    noun, id_key, extra = _KINDS[kind]
    name = name.strip()
    _, code = indeed_domain(country)
    params = {"query": name, "country": code, "language": "en", "count": 10, "rich": "true"}
    url = f"{AUTOCOMPLETE_URL}/{kind}?{urlencode(params | extra)}"
    result = await fetcher.fetch(url, headers=AUTOCOMPLETE_HEADERS)
    if result.error:
        raise Stopped(
            f"{noun} lookup for {name!r} failed: {result.error}. Try again later", partial=[]
        )
    try:
        hits = json.loads(result.text)
    except ValueError:
        hits = None
    candidates = (
        [c for hit in hits if (c := _candidate(hit, id_key, "suggestion"))]
        if isinstance(hits, list)
        else []
    )
    if not isinstance(hits, list) or (hits and not candidates):
        raise Stopped(
            f"could not read Indeed's {noun} suggestions for {name!r}. Try again later", partial=[]
        )
    return candidates


@checked
async def places(
    fetcher: Fetcher, name: Annotated[str, "place name, e.g., 'boston'"], *, country: Country
) -> list[dict[str, str]]:
    """
    List an Indeed edition's location suggestions for a name, best match first.

    Each is an ``{"id", "name"}`` dict, and ``id`` is the exact string the
    edition's search geocodes, ready for ``search``'s ``location``. Indeed
    sends up to ten. An empty list means the edition offers no such place.

    Raises:
        Stopped: The request failed, or the response held no readable suggestion.
        ValueError: The name is blank, or the country edition is unknown.
    """
    return await _suggestions(fetcher, "location", name, country)


@checked
async def companies(
    fetcher: Fetcher, name: Annotated[str, "company name, e.g., 'ABN AMRO'"], *, country: Country
) -> list[dict[str, str]]:
    """
    List an Indeed edition's company suggestions for a name.

    Each is an ``{"id", "name"}`` dict, and ``id`` is Indeed's employer key,
    which ``search`` takes in ``company_ids``. An empty list means Indeed
    returned no suggestions.

    Raises:
        Stopped: The request failed, or the response held no readable suggestion.
        ValueError: The name is blank, or the country edition is unknown.
    """
    return await _suggestions(fetcher, "company", name, country)


@checked
async def attributes(
    fetcher: Fetcher, query: Annotated[str, "job title or keywords"], *, country: Country
) -> list[dict[str, str]]:
    """
    Collect the attribute codes on the first 100 matching Indeed jobs.

    Each is an ``{"id", "name"}`` dict. ``id`` is a code that ``search`` takes
    in ``attributes``, and ``name`` is Indeed's label, which can vary by edition. The search has no posting-age
    restriction. Codes appear once, in first-seen order, and different codes
    with the same label stay separate. Malformed entries are skipped. A
    search with no attributes returns ``[]``.

    Raises:
        Stopped: The request failed, or the response held no readable attribute.
        ValueError: The query is blank, or the country edition is unknown.
    """
    query = query.strip()
    _, code = indeed_domain(country)
    result = await fetcher.fetch(
        API_URL,
        headers={**API_HEADERS, "indeed-co": code},
        json={"query": ATTRIBUTES_QUERY.format(query=json.dumps(query))},
    )
    if result.error:
        raise Stopped(
            f"attribute lookup for {query!r} failed: {result.error}. Try again later", partial=[]
        )
    unreadable = f"could not read Indeed's attributes for {query!r}. Try again later"
    try:
        hits = json.loads(result.text)["data"]["jobSearch"]["results"]
    except (ValueError, KeyError, TypeError) as error:
        raise Stopped(unreadable, partial=[]) from error
    if not isinstance(hits, list):
        raise Stopped(unreadable, partial=[])
    found: dict[str, dict[str, str]] = {}
    malformed = False
    for hit in hits:
        job = hit.get("job") if isinstance(hit, dict) else None
        entries = job.get("attributes") if isinstance(job, dict) else None
        if not isinstance(entries, list):
            malformed = True
            continue
        for entry in entries:
            if candidate := _candidate(entry, "key", "label"):
                found.setdefault(candidate["id"], candidate)
            else:
                malformed = True
    if malformed and not found:
        raise Stopped(unreadable, partial=[])
    return list(found.values())
