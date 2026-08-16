"""Transport result, exception, and HTTP adapter contracts."""

import asyncio
import math

import httpx
import pytest

from jobrake.fetchkit import BaseFetcher, ErrorCategory, HttpxFetcher, build_result


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (400, ErrorCategory.CLIENT),
        (429, ErrorCategory.RATE_LIMITED),
        (500, ErrorCategory.SERVER),
    ],
)
def test_build_result_classifies_http_errors(status, category):
    result = build_result("https://example.test", status, "body", {"Retry-After": "3"})

    assert result.error is not None
    assert result.text == "body"
    assert result.headers == {"retry-after": "3"}
    assert result.error.category is category
    assert result.error.http_status == status


def test_base_fetcher_maps_transport_exceptions():
    class BrokenFetcher(BaseFetcher):
        network_errors = (OSError,)

        async def _fetch(self, url, headers):
            raise OSError("offline")

    result = asyncio.run(BrokenFetcher().fetch("https://example.test"))

    assert result.error is not None
    assert result.error.category is ErrorCategory.NETWORK
    assert isinstance(result.error.original_error, OSError)


def test_httpx_fetcher_maps_get_and_post_responses():
    async def run():
        def respond(request):
            assert request.headers["x-test"] == "yes"
            return httpx.Response(200 if request.method == "GET" else 503, text=request.method)

        fetcher = HttpxFetcher(headers={"x-test": "yes"}, jitter=0)
        await fetcher._client.aclose()
        fetcher._client = httpx.AsyncClient(
            headers={"x-test": "yes"}, transport=httpx.MockTransport(respond)
        )
        try:
            get = await fetcher.fetch("https://example.test/get")
            post = await fetcher.post("https://example.test/post", {})
            return get, post
        finally:
            await fetcher.close()

    get, post = asyncio.run(run())
    assert get.ok and get.text == "GET"
    assert post.error is not None
    assert post.error.category is ErrorCategory.SERVER
    assert post.text == "POST"


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf])
def test_httpx_fetcher_rejects_invalid_timeouts(value):
    with pytest.raises(ValueError):
        HttpxFetcher(timeout=value)
