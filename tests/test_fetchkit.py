"""Transport result and HTTP adapter contracts."""

import asyncio
import json
import math

import httpx
import pytest
from hypothesis import given
from hypothesis import strategies as st

from jobrake.fetchkit import FetchResult, HttpxFetcher


def run_with(respond, url, **kwargs):
    async def run():
        async with HttpxFetcher(
            headers={"x-test": "yes"}, transport=httpx.MockTransport(respond)
        ) as fetcher:
            return await fetcher.fetch(url, **kwargs)

    return asyncio.run(run())


def test_an_http_error_status_fails_the_result_and_keeps_the_body():
    result = FetchResult("https://example.test", 429, "body", {"Retry-After": "3"})
    assert (result.ok, result.error, result.text) == (False, "HTTP 429", "body")
    assert result.headers == {"retry-after": "3"}
    assert FetchResult("https://example.test", 200, "body").ok


def test_httpx_fetcher_gets_and_posts_json():
    def respond(request):
        assert request.headers["x-test"] == "yes"
        if request.method == "GET":
            return httpx.Response(200, text="got")
        return httpx.Response(503, text=json.loads(request.content)["q"])

    get = run_with(respond, "https://example.test/get")
    post = run_with(respond, "https://example.test/post", json={"q": "posted"})
    assert (get.ok, get.status, get.text) == (True, 200, "got")
    assert (post.ok, post.status, post.text) == (False, 503, "posted")


@pytest.mark.parametrize(("payload", "method"), [(None, "GET"), ({"q": "x"}, "POST")])
def test_redirect_following_can_be_disabled_for_one_request(payload, method):
    requests = []

    def respond(request):
        requests.append((request.url.path, request.method))
        if request.url.path == "/start":
            return httpx.Response(307, headers={"location": "/final"}, text="redirect")
        return httpx.Response(200, text="arrived")

    async def run():
        async with HttpxFetcher(transport=httpx.MockTransport(respond)) as fetcher:
            followed = await fetcher.fetch("https://example.test/start", json=payload)
            first = await fetcher.fetch(
                "https://example.test/start", json=payload, follow_redirects=False
            )
            again = await fetcher.fetch("https://example.test/start", json=payload)
        return followed, first, again

    followed, first, again = asyncio.run(run())
    assert (followed.url, followed.text) == ("https://example.test/final", "arrived")
    assert (again.url, again.text) == ("https://example.test/final", "arrived")
    assert (first.url, first.status, first.text, first.ok) == (
        "https://example.test/start",
        307,
        "redirect",
        True,
    )
    assert first.headers["location"] == "/final"
    assert requests == [
        (path, method) for path in ("/start", "/final", "/start", "/start", "/final")
    ]


def test_httpx_fetcher_returns_a_transport_exception_as_the_error():
    def explode(request):
        raise httpx.ConnectError("offline")

    result = run_with(explode, "https://example.test")
    assert (result.status, result.error) == (None, "ConnectError: offline")


def test_httpx_fetcher_lets_cancellation_propagate():
    def cancel(request):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run_with(cancel, "https://example.test")


@given(timeout=st.floats(max_value=0) | st.sampled_from([math.nan, math.inf]))
def test_httpx_fetcher_rejects_a_timeout_not_positive_or_not_finite(timeout):
    with pytest.raises(ValueError, match="timeout must be finite"):
        HttpxFetcher(timeout=timeout)
