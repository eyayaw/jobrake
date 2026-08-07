"""Vendored subset of fetchkit: fetch types and the fetcher contract."""

from .base import BaseFetcher, Fetcher
from .types import ErrorCategory, FetchError, FetchResult, build_result

__all__ = [
    "BaseFetcher",
    "ErrorCategory",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "build_result",
]
