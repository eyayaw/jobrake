"""LinkedIn via the guest search API (HTML job cards, no login)."""

from .client import BASE_URL, CACHE, HEADERS, LIMITER, RETRY_DELAY, SEARCH_URL, job_id
from .postings import FRAGMENT_URL, fetch_postings, parse_posting
from .search import MAX_START, parse_cards, search

__all__ = [
    "BASE_URL",
    "CACHE",
    "FRAGMENT_URL",
    "HEADERS",
    "LIMITER",
    "MAX_START",
    "RETRY_DELAY",
    "SEARCH_URL",
    "fetch_postings",
    "job_id",
    "parse_cards",
    "parse_posting",
    "search",
]
