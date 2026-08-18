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
    """GET and JSON POST transport backed by one pooled httpx client."""

    # The operational transport failures: timeouts, sockets, framing, and
    # proxies. UnsupportedProtocol stays out—a malformed URL is the
    # caller's error, not the network's.
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
    ):
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
