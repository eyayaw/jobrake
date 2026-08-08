"""Httpx-based fetcher implementation."""

import httpx

from .base import DEFAULT_ACCEPT, DEFAULT_USER_AGENT, HTTP_TIMEOUT, BaseFetcher
from .types import FetchResult, build_result


class HttpxFetcher(BaseFetcher):
    """
    Fetcher using httpx: an async HTTP client with connection pooling.

    Satisfies ``PostFetcher``: JSON ``post`` on top of the GET-only
    ``Fetcher`` contract.
    """

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

    async def post(
        self, url: str, json_body: dict, headers: dict[str, str] | None = None
    ) -> FetchResult:
        """POST JSON, under the same never-raises contract as ``fetch``."""
        return await self._capture_result(url, lambda: self._post(url, json_body, headers))

    async def _post(self, url: str, json_body: dict, headers: dict[str, str] | None) -> FetchResult:
        r = await self._client.post(url, json=json_body, headers=headers)
        return build_result(str(r.url), r.status_code, r.text, r.headers)

    async def close(self) -> None:
        await self._client.aclose()
