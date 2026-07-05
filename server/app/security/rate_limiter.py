from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock


def _is_auth_path(path: str) -> bool:
    return path.startswith("/auth/")


def _is_exempt_path(path: str) -> bool:
    if path.startswith("/health"):
        return True
    if path.startswith("/docs"):
        return True
    if path.startswith("/redoc"):
        return True
    if path == "/openapi.json":
        return True
    if path.startswith("/static/"):
        return True
    return False


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_ms: int
    bucket: str
    key: str
    limit: int
    window_ms: int


class InMemoryRateLimiter:
    def __init__(
        self,
        *,
        global_limit: int,
        global_window_ms: int,
        auth_limit: int,
        auth_window_ms: int,
    ) -> None:
        self._global_limit = global_limit
        self._global_window_ms = global_window_ms
        self._auth_limit = auth_limit
        self._auth_window_ms = auth_window_ms
        self._events: dict[str, deque[int]] = {}
        self._lock = Lock()

    @staticmethod
    def is_exempt(path: str) -> bool:
        return _is_exempt_path(path)

    def check(self, *, ip_address: str, path: str, now_ms: int) -> RateLimitDecision:
        bucket = "auth" if _is_auth_path(path) else "global"
        limit = self._auth_limit if bucket == "auth" else self._global_limit
        window_ms = self._auth_window_ms if bucket == "auth" else self._global_window_ms
        key = f"{bucket}:{ip_address}"

        with self._lock:
            queue = self._events.get(key)
            if queue is None:
                queue = deque()
                self._events[key] = queue

            boundary = now_ms - window_ms
            while queue and queue[0] <= boundary:
                queue.popleft()

            if len(queue) >= limit:
                oldest_ms = queue[0]
                retry_after_ms = max((oldest_ms + window_ms) - now_ms, 1)
                return RateLimitDecision(
                    allowed=False,
                    retry_after_ms=retry_after_ms,
                    bucket=bucket,
                    key=key,
                    limit=limit,
                    window_ms=window_ms,
                )

            queue.append(now_ms)
            return RateLimitDecision(
                allowed=True,
                retry_after_ms=0,
                bucket=bucket,
                key=key,
                limit=limit,
                window_ms=window_ms,
            )
