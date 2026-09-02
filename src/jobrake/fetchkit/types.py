"""Fetch result and error types."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class ErrorCategory(str, Enum):
    """Failure categories used by retry and reporting code."""

    NETWORK = "network"
    SERVER = "server"
    CLIENT = "client"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


@dataclass
class FetchError:
    """
    A mapped transport or HTTP failure.

    Attributes:
        category: Broad cause used by retry and reporting code.
        message: Human-readable context from the transport or HTTP status.
        http_status: Response status, or ``None`` when no response arrived.
        original_error: Exception captured from the transport, when available.
    """

    category: ErrorCategory
    message: str
    http_status: int | None = None
    original_error: Exception | None = field(default=None, repr=False)


@dataclass
class FetchResult:
    """
    Response content or a mapped failure.

    HTTP error bodies remain available in ``text``. Transport failures have no
    status code and retain their exception in ``error.original_error``.

    Attributes:
        url: Final response URL, or the requested URL when no response arrived.
        status_code: HTTP status when a response arrived.
        text: Response body for successful and HTTP-error responses.
        headers: Response headers, normalized to lowercase by ``build_result``.
        error: Failure details, or ``None`` after a successful request.
    """

    url: str
    status_code: int | None = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: FetchError | None = None

    @property
    def ok(self) -> bool:
        """Whether the request completed without a mapped failure."""
        return self.error is None


def build_result(url: str, status_code: int, text: str, headers: Mapping[str, str]) -> FetchResult:
    """
    Convert an HTTP response into the transport-neutral result model.

    Status 429 is rate limited, other 4xx statuses are client failures, and
    5xx statuses are server failures. Error response bodies are retained.
    """
    headers = {name.lower(): value for name, value in headers.items()}
    if status_code < 400:
        return FetchResult(url, status_code, text, headers)
    if status_code == 429:
        category, label = ErrorCategory.RATE_LIMITED, "rate limited"
    elif status_code >= 500:
        category, label = ErrorCategory.SERVER, "server error"
    else:
        category, label = ErrorCategory.CLIENT, "client error"
    return FetchResult(
        url,
        status_code,
        text,
        headers,
        FetchError(category, f"{label} (HTTP {status_code})", status_code),
    )


__all__ = ["ErrorCategory", "FetchError", "FetchResult", "build_result"]
