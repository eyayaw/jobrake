"""httpx-backed fetcher."""

import math
from collections.abc import Awaitable

import httpx

from .base import DEFAULT_ACCEPT, DEFAULT_USER_AGENT, HTTP_TIMEOUT, BaseFetcher
from .types import FetchResult, build_result

DEFAULT_HEADERS = {
    "Accept": DEFAULT_ACCEPT,
    "User-Agent": DEFAULT_USER_AGENT,
}


class HttpxFetcher(BaseFetcher):
    """A pooled httpx transport for GET and JSON POST requests."""

    # Timeouts, sockets, framing, and proxies are operational network failures.
    # UnsupportedProtocol identifies a malformed caller URL and stays UNKNOWN.
    network_errors = (
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.ProtocolError,
        httpx.ProxyError,
    )

    def __init__(
        self,
        timeout: float = HTTP_TIMEOUT,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
        cookies: dict[str, str] | None = None,
        jitter: float = 0.1,
    ) -> None:
        """
        Configure the pooled client and GET pacing.

        ``timeout`` applies to each network operation. Headers override the
        browser-like defaults, and cookies seed the client session. Responses
        report the final URL when redirects are enabled. ``jitter`` delays GET
        requests only. Both time values are in seconds.

        Raises:
            ValueError: ``timeout`` or ``jitter`` is outside its valid range.
        """
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        super().__init__(jitter)
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=DEFAULT_HEADERS | (headers or {}),
            follow_redirects=follow_redirects,
            cookies=cookies,
        )

    async def _fetch(self, url: str, headers: dict[str, str] | None) -> FetchResult:
        response = await self._client.get(url, headers=headers)
        return build_result(
            str(response.url), response.status_code, response.text, response.headers
        )

    async def post(
        self, url: str, json_body: dict, headers: dict[str, str] | None = None
    ) -> FetchResult:
        """Send JSON without GET jitter and capture request exceptions."""
        operation = self._client.post(url, json=json_body, headers=headers)
        return await self._capture_result(url, self._response(operation))

    async def _response(self, operation: Awaitable[httpx.Response]) -> FetchResult:
        response = await operation
        return build_result(
            str(response.url), response.status_code, response.text, response.headers
        )

    async def close(self) -> None:
        await self._client.aclose()


__all__ = ["HttpxFetcher"]
