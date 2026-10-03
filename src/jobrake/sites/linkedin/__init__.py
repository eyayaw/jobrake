"""LinkedIn through the login-free guest API and its HTML job cards."""

from jobrake.cache import Cache

from . import client
from .client import (
    BASE_URL,
    HEADERS,
    LIMITER,
    RETRY_DELAY,
    SEARCH_URL,
    TYPEAHEAD_URL,
    job_id,
)
from .companies import companies
from .geo import places, resolve_geoid
from .postings import FRAGMENT_URL, fetch_details, fetch_postings, parse_posting
from .search import MAX_START, parse_cards, search


def __getattr__(name: str) -> Cache:
    # Reading the client's attribute on each access leaves the shared cache
    # unbuilt until first use and follows a replacement of it.
    if name == "CACHE":
        return client.CACHE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BASE_URL",
    "CACHE",
    "FRAGMENT_URL",
    "HEADERS",
    "LIMITER",
    "MAX_START",
    "RETRY_DELAY",
    "SEARCH_URL",
    "TYPEAHEAD_URL",
    "companies",
    "fetch_details",
    "fetch_postings",
    "job_id",
    "parse_cards",
    "parse_posting",
    "places",
    "resolve_geoid",
    "search",
]
