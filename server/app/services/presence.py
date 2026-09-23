"""In-memory presence tracking for chat members.

The web SPA talks to the server over plain HTTP polling, so "online" is
derived from recent authenticated activity instead of WebSocket connections.
The tracker lives in the server process (single uvicorn worker), so entries
disappear on restart — that is acceptable for a presence indicator.
"""
from __future__ import annotations

import threading
import time

PRESENCE_TTL_MS = 75_000


class PresenceTracker:
    def __init__(self, ttl_ms: int = PRESENCE_TTL_MS) -> None:
        self._ttl_ms = ttl_ms
        self._lock = threading.Lock()
        self._last_seen_ms: dict[int, int] = {}

    def touch(self, user_id: int, *, now_ms: int | None = None) -> None:
        if not user_id:
            return
        stamp = _now_ms() if now_ms is None else now_ms
        with self._lock:
            self._last_seen_ms[int(user_id)] = stamp

    def is_online(self, user_id: int, *, now_ms: int | None = None) -> bool:
        stamp = _now_ms() if now_ms is None else now_ms
        with self._lock:
            last = self._last_seen_ms.get(int(user_id))
            if last is None:
                return False
            if stamp - last > self._ttl_ms:
                self._last_seen_ms.pop(int(user_id), None)
                return False
            return True

    def online_user_ids(self, *, now_ms: int | None = None) -> list[int]:
        stamp = _now_ms() if now_ms is None else now_ms
        with self._lock:
            stale = [
                user_id
                for user_id, last in self._last_seen_ms.items()
                if stamp - last > self._ttl_ms
            ]
            for user_id in stale:
                self._last_seen_ms.pop(user_id, None)
            return sorted(self._last_seen_ms)


def _now_ms() -> int:
    return int(time.time() * 1000)


presence = PresenceTracker()
