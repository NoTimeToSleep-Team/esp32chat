from __future__ import annotations


class WatchdogSupervisor:
    def __init__(self, *, timeout_ms: int) -> None:
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be > 0")
        self._timeout_ms = timeout_ms
        self._last_feed_ms: int | None = None
        self._missed_count = 0

    @property
    def timeout_ms(self) -> int:
        return self._timeout_ms

    @property
    def missed_count(self) -> int:
        return self._missed_count

    def feed(self, now_ms: int) -> None:
        if now_ms < 0:
            raise ValueError("now_ms must be >= 0")
        self._last_feed_ms = now_ms

    def is_healthy(self, now_ms: int) -> bool:
        if self._last_feed_ms is None:
            return True
        return (now_ms - self._last_feed_ms) <= self._timeout_ms

    def evaluate(self, now_ms: int) -> bool:
        healthy = self.is_healthy(now_ms)
        if not healthy:
            self._missed_count += 1
        return healthy
