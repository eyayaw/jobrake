"""Vendored subset of fetchkit: the GET transport, its base contract, and types."""

from .base import BaseFetcher, Fetcher
from .httpx import HttpxFetcher
from .types import ErrorCategory, FetchError, FetchResult, build_result

__all__ = [
    "BaseFetcher",
    "ErrorCategory",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "HttpxFetcher",
    "build_result",
]
