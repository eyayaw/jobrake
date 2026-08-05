"""Shared test fakes: canned fetchkit results, no network."""

from fetchkit.types import ErrorCategory, FetchError, FetchResult


class StubFetcher:
    """Serves canned FetchResults by URL substring; records every request."""

    def __init__(self, responses: dict[str, FetchResult]):
        self.responses = responses
        self.requests: list[str] = []

    def _lookup(self, url: str) -> FetchResult:
        self.requests.append(url)
        for fragment, result in self.responses.items():
            if fragment in url:
                return FetchResult(
                    url=url, status_code=result.status_code, text=result.text, error=result.error
                )
        return FetchResult(url=url, error=FetchError(ErrorCategory.CLIENT, "no stub"))

    async def fetch(self, url, headers=None):
        return self._lookup(url)

    async def post(self, url, json_body, headers=None):
        return self._lookup(url)

    async def close(self):
        pass


def ok(text: str) -> FetchResult:
    return FetchResult(url="stub", status_code=200, text=text)


def rate_limited() -> FetchResult:
    return FetchResult(
        url="stub",
        status_code=429,
        error=FetchError(ErrorCategory.RATE_LIMITED, "Rate limited: 429", http_status=429),
    )
