"""Fetcher protocols and shared base class."""

import asyncio
import logging
import math
import random
from collections.abc import Awaitable
from typing import Protocol, Self

from .types import ErrorCategory, FetchError, FetchResult

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0
DEFAULT_ACCEPT = "text/html,application/json,*/*"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class Fetcher(Protocol):
    """A GET transport that returns failures in ``FetchResult.error``."""

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResult: ...

    async def close(self) -> None: ...


class PostFetcher(Fetcher, Protocol):
    """A fetcher that also supports JSON POST requests."""

    async def post(
        self, url: str, json_body: dict, headers: dict[str, str] | None = None
    ) -> FetchResult: ...


class BaseFetcher:
    """Base for transports that map exceptions onto results and add GET jitter."""

    network_errors: tuple[type[BaseException], ...] = ()

    def __init__(self, jitter: float = 0.0):
        self.jitter = float(jitter)
        if not math.isfinite(self.jitter) or self.jitter < 0:
            raise ValueError("jitter must be nonnegative and finite")

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResult:
        if self.jitter:
            await asyncio.sleep(random.uniform(0, self.jitter))
        return await self._capture_result(url, self._fetch(url, headers))

    async def _capture_result(self, url: str, operation: Awaitable[FetchResult]) -> FetchResult:
        try:
            return await operation
        except Exception as error:
            category = (
                ErrorCategory.NETWORK
                if isinstance(error, self.network_errors)
                else ErrorCategory.UNKNOWN
            )
            logger.debug("fetch error for %s: %s", url, error)
            return FetchResult(
                url=url,
                error=FetchError(category, str(error), original_error=error),
            )

    async def _fetch(self, url: str, headers: dict[str, str] | None) -> FetchResult:
        raise NotImplementedError

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


__all__ = [
    "BaseFetcher",
    "DEFAULT_ACCEPT",
    "DEFAULT_USER_AGENT",
    "Fetcher",
    "HTTP_TIMEOUT",
    "PostFetcher",
]
