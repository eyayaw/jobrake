"""Fetcher protocol, shared base implementation, and backend constants."""

import asyncio
import logging
import math
import random
from collections.abc import Awaitable, Callable
from typing import Protocol

from .types import ErrorCategory, FetchError, FetchResult

logger = logging.getLogger(__name__)

HTTP_TIMEOUT: float = 30.0

DEFAULT_ACCEPT = "text/html,application/json,*/*"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class Fetcher(Protocol):
    """
    Protocol for URL fetchers.

    A fetcher retrieves content from a URL and reports the outcome as a
    ``FetchResult``: failures become ``result.error`` rather than exceptions,
    and retry decisions stay with the caller.

    Implementations can wrap any HTTP library (httpx, aiohttp, requests, etc.)
    or browser automation tools (Playwright, Selenium, etc.).
    """

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResult:
        """
        Fetch content from a URL.

        Args:
            url: The URL to fetch
            headers: Optional per-request headers

        Returns:
            FetchResult carrying content on success or an error on failure.
            Never raises exceptions.
        """
        ...

    async def close(self) -> None:
        """Clean up resources (close connections, etc.)."""
        ...


class PostFetcher(Fetcher, Protocol):
    """A Fetcher that can also POST JSON, e.g., the indeed scraper."""

    async def post(
        self, url: str, json_body: dict, headers: dict[str, str] | None = None
    ) -> FetchResult:
        """POST a JSON body, under the same never-raises contract as ``fetch``."""
        ...


class BaseFetcher:
    """
    Shared fetcher implementation. Custom backends may subclass this.

    Subclasses implement ``_fetch`` and declare ``network_errors``; the
    never-raises guarantee, jitter spacing, and error mapping live here.
    """

    # Backend-specific exceptions that should map to a NETWORK error.
    network_errors: tuple[type[BaseException], ...] = ()

    def __init__(self, jitter: float = 0.0):
        jitter = float(jitter)
        if jitter < 0 or not math.isfinite(jitter):
            raise ValueError("jitter must be nonnegative and finite")
        self.jitter = jitter

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResult:
        """Fetch a URL, never raising—failures become FetchResult errors."""
        if self.jitter > 0:
            # Small random spacing between requests (anti-fingerprinting).
            await asyncio.sleep(random.uniform(0, self.jitter))
        return await self._capture_result(url, lambda: self._fetch(url, headers))

    async def _capture_result(
        self,
        url: str,
        operation: Callable[[], Awaitable[FetchResult]],
    ) -> FetchResult:
        """Run a backend operation under the fetcher's error contract."""
        try:
            return await operation()
        except Exception as e:
            if isinstance(e, self.network_errors):
                category = ErrorCategory.NETWORK
            else:
                category = ErrorCategory.UNKNOWN
            logger.debug("Fetch error for %s: %s", url, e)
            return FetchResult(url=url, error=FetchError(category, str(e), original_error=e))

    async def _fetch(self, url: str, headers: dict[str, str] | None) -> FetchResult:
        raise NotImplementedError

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "BaseFetcher":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
