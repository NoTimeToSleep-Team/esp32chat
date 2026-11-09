from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock


def _is_auth_path(path: str) -> bool:
    return (
        path.startswith("/auth/")
        or path.startswith("/chat/api/private/")
        or path in {
            "/device-challenge",
            "/device-session",
            "/devices/api/pair",
            "/devices/api/pair/request",
            "/devices/api/pair/claim",
            "/devices/api/pair/reset",
        }
    )


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


class FailureRateLimiter:
    """Blocks a key after a number of failures in a sliding window.

    Unlike ``InMemoryRateLimiter`` successful operations do not consume the
    budget. This keeps normal registration/login traffic unaffected while
    stopping repeated enumeration or room-code guessing from one source.
    """

    def __init__(self, *, max_failures: int, window_ms: int, block_ms: int) -> None:
        self._max_failures = max(1, int(max_failures))
        self._window_ms = max(1, int(window_ms))
        self._block_ms = max(1, int(block_ms))
        self._failures: dict[str, deque[int]] = {}
        self._blocked: dict[str, int] = {}
        self._lock = Lock()

    def check(self, *, key: str, now_ms: int) -> tuple[bool, int | None]:
        with self._lock:
            blocked_until = self._blocked.get(key)
            if blocked_until is not None:
                if blocked_until <= now_ms:
                    self._blocked.pop(key, None)
                else:
                    return False, blocked_until

            queue = self._failures.get(key)
            if queue is None:
                return True, None
            boundary = now_ms - self._window_ms
            while queue and queue[0] <= boundary:
                queue.popleft()
            if not queue:
                self._failures.pop(key, None)
            return True, None

    def record_failure(self, *, key: str, now_ms: int) -> int | None:
        with self._lock:
            queue = self._failures.get(key)
            if queue is None:
                queue = deque()
                self._failures[key] = queue
            boundary = now_ms - self._window_ms
            while queue and queue[0] <= boundary:
                queue.popleft()
            queue.append(now_ms)
            if len(queue) >= self._max_failures:
                blocked_until = now_ms + self._block_ms
                self._blocked[key] = blocked_until
                self._failures.pop(key, None)
                return blocked_until
            return None

    def reset(self, *, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._blocked.pop(key, None)
