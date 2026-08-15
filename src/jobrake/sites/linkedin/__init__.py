"""LinkedIn via the guest search API (HTML job cards, no login)."""

from .client import BASE_URL, DETAIL_URL, HEADERS, LIMITER, RETRY_DELAY, SEARCH_URL, job_id
from .descriptions import CACHE, fetch_descriptions, parse_description
from .postings import parse_posting
from .search import MAX_START, parse_cards, search

__all__ = [
    "BASE_URL",
    "CACHE",
    "DETAIL_URL",
    "HEADERS",
    "LIMITER",
    "MAX_START",
    "RETRY_DELAY",
    "SEARCH_URL",
    "fetch_descriptions",
    "job_id",
    "parse_cards",
    "parse_description",
    "parse_posting",
    "search",
]
