"""Client-side token-bucket rate limiter for paced fetching."""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """
    Rate limiter: allows ``capacity`` calls immediately, then one call every
    ``refill_interval`` seconds.

    The bucket starts full. Each call takes one token, and tokens refill
    continuously at one per ``refill_interval``. When the bucket is empty,
    the caller must wait for the next token, and the level goes negative in
    the meantime. Because each caller adds to that debt, concurrent callers
    are spaced out at the refill rate rather than released all at once.

    Two entry points:

    * ``acquire()``—takes a token and sleeps until it is allowed to
      proceed, using ``time.monotonic`` and ``asyncio.sleep``.
    * ``reserve(now)``—takes a token and returns the wait in seconds,
      leaving the waiting to the caller. It performs no I/O and reads no
      clock: its behavior depends only on the bucket's state and the
      ``now`` values passed in. This makes it usable from sync code and
      testable with a simulated clock.

    ``now`` may come from any non-decreasing clock; since only elapsed time
    matters, the choice of epoch is free. The instance holds no asyncio
    primitives, so one bucket can be shared across successive
    ``asyncio.run`` calls; the token count carries over from one run to
    the next.
    """

    def __init__(self, capacity: float, refill_interval: float):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_interval <= 0:
            raise ValueError("refill_interval must be positive")
        self.capacity = float(capacity)
        self.refill_interval = float(refill_interval)
        self._level = self.capacity
        self._stamp: float | None = None

    def reserve(self, now: float) -> float:
        """Take one token; returns the wait (seconds) owed before proceeding."""
        if self._stamp is not None:
            elapsed = max(0.0, now - self._stamp)
            self._level = min(self.capacity, self._level + elapsed / self.refill_interval)
        self._stamp = now
        wait = max(0.0, (1.0 - self._level) * self.refill_interval)
        self._level -= 1.0
        return wait

    async def acquire(self) -> None:
        # reserve() contains no await, so concurrent callers update the
        # bucket one at a time; each sees the debt left by those before it.
        wait = self.reserve(time.monotonic())
        if wait > 0:
            await asyncio.sleep(wait)
