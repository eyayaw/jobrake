"""The ``Fetcher`` protocol, its ``FetchResult``, and the httpx-backed ``HttpxFetcher``."""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Protocol, Self

lazy import httpx

logger = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "text/html,application/json,*/*",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


@dataclass
class FetchResult:
    """
    One response, or the failure that took its place.

    Header names are lowercased. A status of 400 or more sets ``error`` to
    ``"HTTP <status>"`` unless the fetcher supplied a message, so a 429 from
    any fetcher reads as ``status == 429`` and carries an ``error``.

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


class Fetcher(Protocol):
    """An async HTTP transport that returns each failure in ``FetchResult.error``."""

    async def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> FetchResult:
        """
        GET ``url``, or POST ``json`` to it when given. Cancellation propagates.

        With ``follow_redirects=False``, return the first response, including its Location header.
        """
        ...


class HttpxFetcher:
    """A pooled httpx ``Fetcher``, which reports a request's exception in ``FetchResult.error``."""

    def __init__(
        self,
        timeout: float = 30.0,
        *,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """
        Configure the pooled client.

        ``timeout`` applies to each network operation, in seconds. Headers
        override the browser-like defaults. ``transport`` replaces the
        network, as ``httpx.MockTransport`` does in tests.

        Raises:
            ValueError: ``timeout`` is not finite and positive.
        """
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=_HEADERS | (headers or {}),
            transport=transport,
        )

    async def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> FetchResult:
        try:
            response = await self._client.request(
                "GET" if json is None else "POST",
                url,
                json=json,
                headers=headers,
                follow_redirects=follow_redirects,
            )
        except Exception as error:  # noqa: BLE001  the Fetcher contract reports failures in the result
            logger.debug("fetch error for %s: %r", url, error)
            return FetchResult(url, error=f"{type(error).__name__}: {error}")
        return FetchResult(
            str(response.url), response.status_code, response.text, dict(response.headers)
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
