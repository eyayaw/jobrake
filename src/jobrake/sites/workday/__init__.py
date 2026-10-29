"""Search an employer's Workday career site through the JSON API behind it."""

from .search import postings, search

__all__ = ["postings", "search"]
