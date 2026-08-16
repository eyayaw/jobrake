"""Transport result, exception, and HTTP adapter contracts."""

import asyncio
import math
import time

import httpx
import pytest

from jobrake.fetchkit import BaseFetcher, ErrorCategory, HttpxFetcher, TokenBucket, build_result


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


def test_token_bucket_burst_is_free_then_debt_compounds():
    bucket = TokenBucket(4, 2.0)
    assert [bucket.reserve(0.0) for _ in range(4)] == [0.0] * 4
    assert bucket.reserve(0.0) == 2.0
    assert bucket.reserve(0.0) == 4.0


def test_token_bucket_idle_refill_caps_at_capacity():
    bucket = TokenBucket(2, 1.0)
    bucket.reserve(0.0)
    bucket.reserve(0.0)
    assert [bucket.reserve(100.0) for _ in range(3)] == [0.0, 0.0, 1.0]


def test_token_bucket_partial_refill_charges_the_shortfall():
    bucket = TokenBucket(1, 2.0)
    assert bucket.reserve(0.0) == 0.0
    assert bucket.reserve(1.0) == 1.0


def test_token_bucket_treats_a_backwards_clock_as_no_elapsed_time():
    bucket = TokenBucket(1, 1.0)
    assert bucket.reserve(5.0) == 0.0
    assert bucket.reserve(4.0) == 1.0


def test_token_bucket_acquire_paces_in_real_time():
    async def run():
        bucket = TokenBucket(1, 0.05)
        start = time.monotonic()
        await bucket.acquire()
        await bucket.acquire()
        return time.monotonic() - start

    assert asyncio.run(run()) >= 0.04


def test_token_bucket_survives_successive_event_loops():
    bucket = TokenBucket(1, 0.001)

    async def contend():
        await asyncio.gather(bucket.acquire(), bucket.acquire())

    asyncio.run(contend())
    asyncio.run(contend())


def test_token_bucket_canceled_acquire_keeps_the_token(monkeypatch):
    async def canceled_sleep(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", canceled_sleep)

    async def run():
        bucket = TokenBucket(1, 2.0)
        await bucket.acquire()
        with pytest.raises(asyncio.CancelledError):
            await bucket.acquire()
        return bucket.reserve(time.monotonic())

    assert asyncio.run(run()) == pytest.approx(2.0, abs=0.1)


def test_token_bucket_canceled_waiter_does_not_delay_its_follower(monkeypatch):
    real_sleep = asyncio.sleep
    sleeps = []

    async def controlled_sleep(seconds):
        sleeps.append(seconds)
        await asyncio.Future()

    monkeypatch.setattr(asyncio, "sleep", controlled_sleep)

    async def run():
        bucket = TokenBucket(1, 2.0)
        await bucket.acquire()
        canceled = asyncio.create_task(bucket.acquire())
        follower = asyncio.create_task(bucket.acquire())
        await real_sleep(0)
        assert sleeps == pytest.approx([2.0], abs=0.1)
        canceled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await canceled
        await real_sleep(0)
        assert sleeps == pytest.approx([2.0, 2.0], abs=0.1)
        follower.cancel()
        with pytest.raises(asyncio.CancelledError):
            await follower

    asyncio.run(run())


@pytest.mark.parametrize(
    ("capacity", "refill_interval"),
    [
        (0, 1.0),
        (1, 0),
        (math.nan, 1.0),
        (1, math.nan),
        (math.inf, 1.0),
        (1, math.inf),
    ],
)
def test_token_bucket_rejects_invalid_parameters(capacity, refill_interval):
    with pytest.raises(ValueError):
        TokenBucket(capacity, refill_interval)
