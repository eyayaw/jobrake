"""TokenBucket tests: the reserve policy with plain numbers, acquire with real time."""

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


def test_rejects_invalid_parameters():
    with pytest.raises(ValueError):
        TokenBucket(0, 1.0)
    with pytest.raises(ValueError):
        TokenBucket(1, 0)
