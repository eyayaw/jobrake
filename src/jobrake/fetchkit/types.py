"""Fetcher protocol and result type."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class FetchResult:
    """
    One response, or the failure that took its place.

    Header names are lowercased. A status of 400 or more sets ``error`` to
    ``"HTTP <status>"`` unless the fetcher supplied a message, so a 429 from
    any fetcher reads as ``status == 429`` and fails ``ok``.

    Attributes:
        url: Final response URL, or the requested URL when no response arrived.
        status: HTTP status, or ``None`` when no response arrived.
        text: Response body, kept for HTTP error responses too.
        error: Failure message, or ``None`` after a successful request.
    """

    url: str
    status: int | None = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        self.headers = {name.lower(): value for name, value in self.headers.items()}
        if self.error is None and self.status is not None and self.status >= 400:
            self.error = f"HTTP {self.status}"

    @property
    def ok(self) -> bool:
        """Whether the request completed without a failure."""
        return self.error is None


class Fetcher(Protocol):
    """An async HTTP transport that returns each failure in ``FetchResult.error``."""

    async def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> FetchResult:
        """GET ``url``, or POST ``json`` to it when given. Cancellation propagates."""
        ...

    async def close(self) -> None: ...


__all__ = ["FetchResult", "Fetcher"]
