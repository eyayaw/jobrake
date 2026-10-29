"""Read an employer's SmartRecruiters job board through its public Posting API."""

from .search import postings, search

__all__ = ["postings", "search"]
