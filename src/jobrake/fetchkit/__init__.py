"""Vendored subset of fetchkit: fetch result and error types."""

from .types import ErrorCategory, FetchError, FetchResult, build_result

__all__ = [
    "ErrorCategory",
    "FetchError",
    "FetchResult",
    "build_result",
]
