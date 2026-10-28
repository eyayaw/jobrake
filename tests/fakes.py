"""Shared network-free fakes that return canned FetchResults."""

from typing import Any

from jobrake.fetchkit import FetchResult


class StubFetcher:
    """Serve canned FetchResults by URL substring and record every request."""

    def __init__(self, responses: dict[str, FetchResult]):
        self.responses = responses
        self.requests: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.bodies: list[Any] = []  # the JSON each request posted, or None

    async def fetch(self, url, *, headers=None, json=None):
        self.requests.append(url)
        self.headers.append(headers or {})
        self.bodies.append(json)
        for fragment, result in self.responses.items():
            if fragment in url:
                return FetchResult(url, result.status, result.text, result.headers, result.error)
        return FetchResult(url, error="no stub")

    async def close(self):
        pass


def ok(text: str) -> FetchResult:
    return FetchResult(url="stub", status=200, text=text)


def not_found() -> FetchResult:
    return FetchResult(url="stub", status=404)


def network_down() -> FetchResult:
    return FetchResult(url="stub", error="connection reset")


def rate_limited() -> FetchResult:
    return FetchResult(url="stub", status=429)


class PagedFetcher(StubFetcher):
    """Answer each request with the next of ``pages``, text or a whole result, and fail on an extra request."""

    def __init__(self, pages: list[str | FetchResult]):
        super().__init__({})
        self.pages = pages

    async def fetch(self, url, *, headers=None, json=None):
        await super().fetch(url, headers=headers, json=json)
        page = self.pages[len(self.requests) - 1]
        return page if isinstance(page, FetchResult) else ok(page)
