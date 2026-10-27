"""httpx-backed fetcher."""

import logging
import math
from typing import Any, Self

lazy import httpx

from .types import FetchResult

logger = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "text/html,application/json,*/*",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


class HttpxFetcher:
    """A pooled httpx transport that follows redirects and returns every httpx exception as ``FetchResult.error``."""

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
            follow_redirects=True,
            transport=transport,
        )

    async def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> FetchResult:
        """GET ``url``, or POST ``json`` to it when given. Cancellation propagates."""
        try:
            if json is None:
                response = await self._client.get(url, headers=headers)
            else:
                response = await self._client.post(url, json=json, headers=headers)
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


__all__ = ["HttpxFetcher"]
