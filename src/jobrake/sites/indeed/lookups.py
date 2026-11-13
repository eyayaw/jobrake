"""Indeed location and company suggestions, and attribute codes from matching jobs."""

import json
from typing import Annotated, Any
from urllib.parse import urlencode

from jobrake.fetchkit import Fetcher
from jobrake.sites.responses import json_list, read_json
from jobrake.utils import as_dict, as_str, checked

from .client import API_HEADERS, API_URL, AUTOCOMPLETE_HEADERS, AUTOCOMPLETE_URL
from .countries import Country, indeed_domain

ATTRIBUTES_QUERY = """
query {{
  jobSearch(what: {query}, limit: 100, sort: RELEVANCE) {{
    results {{ job {{ attributes {{ key label }} }} }}
  }}
}}
"""


def _candidate(hit: object, id_key: str, name_key: str) -> dict[str, str] | None:
    """Read one ``{"id", "name"}`` candidate from a hit's two fields, or None when either is blank."""
    hit = as_dict(hit)
    hit_id, name = ((as_str(hit.get(key)) or "").strip() for key in (id_key, name_key))
    return {"id": hit_id, "name": name} if hit_id and name else None


# Each autocomplete kind: the hit field that holds the ID, and the parameters it adds.
_KINDS: dict[str, tuple[str, dict[str, Any]]] = {
    "location": ("suggestion", {"formatted": 1}),
    "company": ("employerKey", {}),
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
    id_key, extra = _KINDS[kind]
    _, code = indeed_domain(country)
    params = {"query": name.strip(), "country": code, "language": "en", "count": 10, "rich": "true"}
    url = f"{AUTOCOMPLETE_URL}/{kind}?{urlencode(params | extra)}"
    result = await fetcher.fetch(url, headers=AUTOCOMPLETE_HEADERS)

    def candidates(hits: Any) -> list[dict[str, str]]:  # noqa: ANN401  any decoded JSON, which json_list checks
        found = [c for hit in json_list(hits) if (c := _candidate(hit, id_key, "suggestion"))]
        if hits and not found:
            raise TypeError(f"no suggestion has a {id_key} and a suggestion")
        return found

    return read_json(result, candidates, site="indeed")


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


def _attribute_codes(payload: Any) -> list[dict[str, str]]:  # noqa: ANN401  any decoded JSON, which json_list checks
    """
    Collect each attribute code of a search response once, in first-seen order.

    Raises:
        KeyError: The response lacks the search results.
        TypeError: The results are not a list, or they hold malformed entries
            and no readable attribute.
    """
    found: dict[str, dict[str, str]] = {}
    malformed = False
    for hit in json_list(payload["data"]["jobSearch"], "results"):
        entries = as_dict(as_dict(hit).get("job")).get("attributes")
        if not isinstance(entries, list):
            malformed = True
            continue
        for entry in entries:
            if candidate := _candidate(entry, "key", "label"):
                found.setdefault(candidate["id"], candidate)
            else:
                malformed = True
    if malformed and not found:
        raise TypeError("no result has a readable attribute")
    return list(found.values())


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
    _, code = indeed_domain(country)
    result = await fetcher.fetch(
        API_URL,
        headers={**API_HEADERS, "indeed-co": code},
        json={"query": ATTRIBUTES_QUERY.format(query=json.dumps(query.strip()))},
    )
    return read_json(result, _attribute_codes, site="indeed")
