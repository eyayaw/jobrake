"""Core types for fetch results and errors (stdlib-only by design)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class ErrorCategory(str, Enum):
    """Coarse classification of fetch failures."""

    NETWORK = "network"
    SERVER = "server"
    CLIENT = "client"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


@dataclass
class FetchError:
    """Unified error representation for fetchers."""

    category: ErrorCategory
    message: str
    http_status: int | None = None
    original_error: Exception | None = field(default=None, repr=False)


@dataclass
class FetchResult:
    """Result of a fetch operation."""

    url: str
    status_code: int | None = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: FetchError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def build_result(
    url: str,
    status_code: int,
    text: str,
    headers: Mapping[str, str],
) -> FetchResult:
    """
    Turn an HTTP response into a FetchResult.

    Handles 429 (rate-limited), 4xx/5xx (error), and 2xx/3xx (success).
    Header keys are normalized to lowercase, so lookups behave the same
    for every backend. Error results retain the response body for caller
    inspection.
    """
    normalized = {k.lower(): v for k, v in headers.items()}

    if status_code < 400:
        return FetchResult(
            url=url,
            status_code=status_code,
            text=text,
            headers=normalized,
        )

    if status_code == 429:
        error = FetchError(
            ErrorCategory.RATE_LIMITED,
            f"Rate limited: {status_code}",
            http_status=429,
        )
    elif status_code >= 500:
        error = FetchError(
            ErrorCategory.SERVER,
            f"Server error: {status_code}",
            http_status=status_code,
        )
    else:
        error = FetchError(
            ErrorCategory.CLIENT,
            f"Client error: {status_code}",
            http_status=status_code,
        )

    return FetchResult(
        url=url,
        status_code=status_code,
        text=text,
        headers=normalized,
        error=error,
    )
