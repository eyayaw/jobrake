"""Shared network-free fakes that return canned FetchResults."""

from typing import Any

from jobrake.fetchkit import FetchResult


class StubFetcher:
    """
    Serve canned FetchResults by URL substring, record every request, and count each close.

    A result answers with the requested URL when its own is ``"stub"``. Any other ``url``
    stands for a redirect the transport followed to that address.
    """

    def __init__(self, responses: dict[str, FetchResult]):
        self.responses = responses
        self.requests: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.bodies: list[Any] = []  # the JSON each request posted, or None
        self.closed = 0  # exits of its context manager, as HttpxFetcher closes

    async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
        self.requests.append(url)
        self.headers.append(headers or {})
        self.bodies.append(json)
        result = self.respond(url)
        landed = url if result.url == "stub" else result.url
        # A copy, so a test that edits one answer leaves the canned result intact.
        return FetchResult(landed, result.status, result.text, result.headers, result.error)

    def respond(self, url: str) -> FetchResult:
        for fragment, result in self.responses.items():
            if fragment in url:
                return result
        return FetchResult(url, error="no stub")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed += 1


def ok(text: str) -> FetchResult:
    return FetchResult(url="stub", status=200, text=text)


def not_found() -> FetchResult:
    return FetchResult(url="stub", status=404)


def network_down() -> FetchResult:
    return FetchResult(url="stub", error="connection reset")


def rate_limited() -> FetchResult:
    return FetchResult(url="stub", status=429)


class PagedFetcher(StubFetcher):
    """
    Answer each request with the next of ``pages``, and fail on an extra request.

    A page is text, a whole result, or an exception the request raises.
    """

    def __init__(self, pages: list[str | FetchResult | Exception]):
        super().__init__({})
        self.pages = pages

    def respond(self, url: str) -> FetchResult:
        page = self.pages[len(self.requests) - 1]
        if isinstance(page, Exception):
            raise page
        return page if isinstance(page, FetchResult) else ok(page)
