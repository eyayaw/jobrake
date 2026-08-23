"""Cancellation-safe token-bucket request pacing."""

import asyncio
import math
import time


class TokenBucket:
    """A token bucket with an initial burst and interval-based refills."""

    def __init__(self, capacity: float, refill_interval: float) -> None:
        """
        Create a full bucket.

        Args:
            capacity: Tokens available for the initial burst.
            refill_interval: Seconds required to restore one token.

        Raises:
            ValueError: Capacity is below one, an interval is not positive, or either value is non-finite.
        """
        self.capacity = float(capacity)
        self.refill_interval = float(refill_interval)
        if not math.isfinite(self.capacity) or self.capacity < 1:
            raise ValueError("capacity must be finite and at least 1")
        if not math.isfinite(self.refill_interval) or self.refill_interval <= 0:
            raise ValueError("refill_interval must be finite and positive")
        self._level = self.capacity
        self._stamp: float | None = None
        self._loop = None
        self._lock = None

    def _refill(self, now: float) -> None:
        if self._stamp is not None:
            elapsed = max(0.0, now - self._stamp)
            self._level = min(self.capacity, self._level + elapsed / self.refill_interval)
        self._stamp = now

    def reserve(self, now: float) -> float:
        """
        Reserve one token without sleeping.

        Args:
            now: Current monotonic time in seconds.

        Returns:
            Seconds the caller owes before using the reservation.
        """
        self._refill(now)
        wait = max(0.0, (1.0 - self._level) * self.refill_interval)
        self._level -= 1.0
        return wait

    async def acquire(self) -> None:
        """
        Wait for and consume one token.

        Concurrent callers are serialized. Cancellation while waiting spends no token.
        """
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self._lock = asyncio.Lock()
        lock = self._lock
        assert lock is not None
        async with lock:
            while True:
                self._refill(time.monotonic())
                if self._level >= 1:
                    self._level -= 1.0
                    return
                wait = (1.0 - self._level) * self.refill_interval
                await asyncio.sleep(wait)


__all__ = ["TokenBucket"]
