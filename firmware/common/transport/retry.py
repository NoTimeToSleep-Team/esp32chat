from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff: 1s,2s,4s,8s,16s,30s, then 30s."""

    schedule_ms: tuple[int, ...] = (1000, 2000, 4000, 8000, 16000, 30000)

    def next_delay_ms(self, retry_count: int) -> int:
        if retry_count <= 0:
            return 0
        index = min(retry_count - 1, len(self.schedule_ms) - 1)
        return self.schedule_ms[index]

    def can_attempt(
        self,
        *,
        retry_count: int,
        last_attempt_ms: int | None,
        now_ms: int,
    ) -> bool:
        if last_attempt_ms is None:
            return True

        delay_ms = self.next_delay_ms(retry_count)
        return (now_ms - last_attempt_ms) >= delay_ms
