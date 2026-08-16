"""Fetch result and error types."""

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
    """A transport or HTTP failure."""

    category: ErrorCategory
    message: str
    http_status: int | None = None
    original_error: Exception | None = field(default=None, repr=False)


@dataclass
class FetchResult:
    """Content or an error returned by a fetcher."""

    url: str
    status_code: int | None = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: FetchError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def build_result(url: str, status_code: int, text: str, headers: Mapping[str, str]) -> FetchResult:
    """Build a result from an HTTP response, retaining error response bodies."""
    headers = {name.lower(): value for name, value in headers.items()}
    if status_code < 400:
        return FetchResult(url, status_code, text, headers)
    if status_code == 429:
        category, label = ErrorCategory.RATE_LIMITED, "Rate limited"
    elif status_code >= 500:
        category, label = ErrorCategory.SERVER, "Server error"
    else:
        category, label = ErrorCategory.CLIENT, "Client error"
    return FetchResult(
        url,
        status_code,
        text,
        headers,
        FetchError(category, f"{label}: {status_code}", status_code),
    )


__all__ = ["ErrorCategory", "FetchError", "FetchResult", "build_result"]
