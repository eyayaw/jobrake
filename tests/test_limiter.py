"""TokenBucket tests: the reserve policy with plain numbers, acquire with real or stubbed time."""

import asyncio
import time

import pytest

from jobrake.fetchkit import TokenBucket


def test_burst_is_free_then_debt_compounds():
    bucket = TokenBucket(4, 2.0)
    assert [bucket.reserve(0.0) for _ in range(4)] == [0.0] * 4
    # Empty: the 5th caller owes one refill, the 6th two.
    assert bucket.reserve(0.0) == 2.0
    assert bucket.reserve(0.0) == 4.0


def test_idle_refill_caps_at_capacity():
    bucket = TokenBucket(2, 1.0)
    bucket.reserve(0.0)
    bucket.reserve(0.0)
    assert [bucket.reserve(100.0) for _ in range(3)] == [0.0, 0.0, 1.0]


def test_partial_refill_charges_the_shortfall():
    bucket = TokenBucket(1, 2.0)
    assert bucket.reserve(0.0) == 0.0
    # Half a token back after 1s; the missing half costs 1s.
    assert bucket.reserve(1.0) == 1.0


def test_backwards_clock_is_treated_as_no_elapsed_time():
    bucket = TokenBucket(1, 1.0)
    assert bucket.reserve(5.0) == 0.0
    assert bucket.reserve(4.0) == 1.0


def test_acquire_paces_in_real_time():
    bucket = TokenBucket(1, 0.05)

    async def two_acquires():
        start = time.monotonic()
        await bucket.acquire()
        await bucket.acquire()
        return time.monotonic() - start

    # Lower bound only: the second acquire owes roughly one refill.
    assert asyncio.run(two_acquires()) >= 0.04


def test_survives_successive_event_loops():
    bucket = TokenBucket(1, 0.001)

    async def contend():
        await asyncio.gather(bucket.acquire(), bucket.acquire())

    asyncio.run(contend())
    asyncio.run(contend())


def test_canceled_acquire_keeps_the_token(monkeypatch):
    async def canceled_sleep(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", canceled_sleep)

    async def run():
        bucket = TokenBucket(1, 2.0)
        await bucket.acquire()  # burst token, no sleep
        with pytest.raises(asyncio.CancelledError):
            await bucket.acquire()  # owes one refill; canceled mid-wait
        return bucket.reserve(time.monotonic())

    # Acquire waits before spending, so the canceled waiter took nothing:
    # one refill owed, not two.
    assert asyncio.run(run()) == pytest.approx(2.0, abs=0.1)


def test_canceled_waiter_does_not_delay_its_follower(monkeypatch):
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
        # The follower owes the same single refill, on its own schedule.
        assert sleeps == pytest.approx([2.0, 2.0], abs=0.1)
        follower.cancel()
        with pytest.raises(asyncio.CancelledError):
            await follower

    asyncio.run(run())


@pytest.mark.parametrize(
    "capacity, refill_interval",
    [
        (0, 1.0),
        (1, 0),
        (float("nan"), 1.0),  # nan passes `< 1` checks and disables pacing
        (1, float("nan")),
        (float("inf"), 1.0),
        (1, float("inf")),  # an infinite interval means an infinite wait
    ],
)
def test_rejects_invalid_parameters(capacity, refill_interval):
    with pytest.raises(ValueError):
        TokenBucket(capacity, refill_interval)
