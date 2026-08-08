"""Httpx-based fetcher implementation."""

import httpx

from .base import DEFAULT_ACCEPT, DEFAULT_USER_AGENT, HTTP_TIMEOUT, BaseFetcher
from .types import FetchResult, build_result


class HttpxFetcher(BaseFetcher):
    """Fetcher using httpx: an async HTTP client with connection pooling."""

    network_errors = (httpx.TimeoutException, httpx.NetworkError)

    def __init__(
        self,
        timeout: float = HTTP_TIMEOUT,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
        cookies: dict[str, str] | None = None,
        jitter: float = 0.1,
    ):
        # A non-positive timeout would surface at fetch time as a NETWORK
        # timeout; it is a config fault, so fail at construction.
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        super().__init__(jitter=jitter)
        self.timeout = timeout
        self.follow_redirects = follow_redirects

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": DEFAULT_ACCEPT,
                **(headers or {}),
            },
            follow_redirects=follow_redirects,
            cookies=cookies,
        )

    async def _fetch(self, url: str, headers: dict[str, str] | None) -> FetchResult:
        r = await self._client.get(url, headers=headers)
        return build_result(str(r.url), r.status_code, r.text, r.headers)

    async def close(self) -> None:
        await self._client.aclose()
