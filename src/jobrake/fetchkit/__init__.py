"""Minimal async fetch layer: the httpx transport, its base contract, and result types."""

from .base import BaseFetcher, Fetcher, PostFetcher
from .httpx import HttpxFetcher
from .types import ErrorCategory, FetchError, FetchResult, build_result

__all__ = [
    "BaseFetcher",
    "ErrorCategory",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "HttpxFetcher",
    "PostFetcher",
    "build_result",
]
