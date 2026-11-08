from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import time

from fastapi import WebSocket


@dataclass(frozen=True)
class _SocketBinding:
    user_id: int
    session_id: str
    expires_at_ms: int
    ip_address: str
    device_id: str | None


class ChatRealtimeBroker:
    # These are deliberately higher than the old single global cap of 50.
    # Per-user and per-IP caps are the actual abuse boundary; the global cap is
    # only a process-memory guard.
    MAX_CONNECTIONS = 200
    MAX_CONNECTIONS_PER_USER = 5
    MAX_CONNECTIONS_PER_IP = 10

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._rooms: dict[int, set[WebSocket]] = {}
        self._bindings: dict[WebSocket, _SocketBinding] = {}

    def active_count(self) -> int:
        return sum(len(room) for room in self._rooms.values())

    def online_users(self) -> list[int]:
        return list({binding.user_id for binding in self._bindings.values()})

    async def connect(
        self,
        *,
        chat_id: int,
        websocket: WebSocket,
        user_id: int = 0,
        session_id: str = "",
        expires_at_ms: int = 0,
        ip_address: str = "",
        device_id: str | None = None,
    ) -> bool:
        reason: str | None = None
        async with self._lock:
            if self.active_count() >= self.MAX_CONNECTIONS:
                reason = "too many connections"
            elif user_id and sum(
                1 for binding in self._bindings.values() if binding.user_id == user_id
            ) >= self.MAX_CONNECTIONS_PER_USER:
                reason = "too many connections for user"
            elif ip_address and sum(
                1
                for binding in self._bindings.values()
                if binding.ip_address and binding.ip_address == ip_address
            ) >= self.MAX_CONNECTIONS_PER_IP:
                reason = "too many connections for address"
            else:
                room = self._rooms.setdefault(chat_id, set())
                room.add(websocket)
                self._bindings[websocket] = _SocketBinding(
                    user_id=user_id,
                    session_id=session_id,
                    expires_at_ms=expires_at_ms,
                    ip_address=ip_address,
                    device_id=device_id,
                )
                return True

        try:
            await asyncio.wait_for(
                websocket.close(code=4503, reason=reason or "too many connections"),
                timeout=2.0,
            )
        except Exception:
            pass
        return False

    async def disconnect(self, *, chat_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(chat_id)
            if room is None:
                return
            room.discard(websocket)
            self._bindings.pop(websocket, None)
            if not room:
                self._rooms.pop(chat_id, None)

    async def disconnect_user(self, *, chat_id: int, user_id: int) -> int:
        """Close every socket a user has in one chat (kick/leave)."""
        async with self._lock:
            room = self._rooms.get(chat_id, set())
            targets = [
                websocket
                for websocket in room
                if self._bindings.get(websocket) is not None
                and self._bindings[websocket].user_id == user_id
            ]
        await self._close_and_remove(targets, code=4403, reason="removed from chat")
        return len(targets)

    async def disconnect_session(self, session_id: str) -> int:
        """Close every socket authenticated with a revoked session."""
        normalized = (session_id or "").strip()
        if not normalized:
            return 0
        async with self._lock:
            targets = [
                websocket
                for websocket, binding in self._bindings.items()
                if binding.session_id == normalized
            ]
        await self._close_and_remove(targets, code=4401, reason="session revoked")
        return len(targets)

    async def disconnect_device(self, device_id: str) -> int:
        normalized = (device_id or "").strip()
        if not normalized:
            return 0
        async with self._lock:
            targets = [
                websocket
                for websocket, binding in self._bindings.items()
                if binding.device_id == normalized
            ]
        await self._close_and_remove(targets, code=4401, reason="device revoked")
        return len(targets)

    async def disconnect_all_user(self, user_id: int) -> int:
        """Close every socket of a user across all rooms (ban/reset/delete)."""
        async with self._lock:
            targets = [
                websocket
                for websocket, binding in self._bindings.items()
                if binding.user_id == user_id
            ]
        await self._close_and_remove(targets, code=4401, reason="session revoked")
        return len(targets)

    async def close_room(self, *, chat_id: int, code: int = 4404, reason: str = "chat closed") -> int:
        """Close all sockets in a room after the chat is deleted."""
        async with self._lock:
            targets = list(self._rooms.get(chat_id, set()))
        await self._close_and_remove(targets, code=code, reason=reason, drop_room=chat_id)
        return len(targets)

    async def close_expired(self, *, now_ms: int | None = None) -> int:
        now = int(time() * 1000) if now_ms is None else int(now_ms)
        async with self._lock:
            targets = [
                websocket
                for websocket, binding in self._bindings.items()
                if binding.expires_at_ms and binding.expires_at_ms <= now
            ]
        await self._close_and_remove(targets, code=4401, reason="session expired")
        return len(targets)

    async def publish(self, *, chat_id: int, event: dict[str, object]) -> int:
        await self.close_expired()
        async with self._lock:
            targets = list(self._rooms.get(chat_id, set()))

        delivered = 0
        dead: list[WebSocket] = []

        for websocket in targets:
            try:
                await asyncio.wait_for(websocket.send_json(event), timeout=2.0)
                delivered += 1
            except Exception:
                dead.append(websocket)

        if dead:
            await self._remove(dead, drop_room=chat_id)
        return delivered

    async def connection_count(self, *, chat_id: int) -> int:
        async with self._lock:
            return len(self._rooms.get(chat_id, set()))

    async def _close_and_remove(
        self,
        targets: list[WebSocket],
        *,
        code: int,
        reason: str,
        drop_room: int | None = None,
    ) -> None:
        async def close_one(websocket: WebSocket) -> None:
            try:
                # A stalled client must never hold an admin request open.
                await asyncio.wait_for(
                    websocket.close(code=code, reason=reason),
                    timeout=2.0,
                )
            except Exception:
                pass

        if targets:
            await asyncio.gather(*(close_one(websocket) for websocket in targets))
        await self._remove(targets, drop_room=drop_room)

    async def _remove(self, targets: list[WebSocket], *, drop_room: int | None = None) -> None:
        if not targets:
            return
        target_set = set(targets)
        async with self._lock:
            for chat_id, room in list(self._rooms.items()):
                if drop_room is not None and chat_id == drop_room:
                    continue
                room.difference_update(target_set)
                if not room:
                    self._rooms.pop(chat_id, None)
            if drop_room is not None:
                self._rooms.pop(drop_room, None)
            for websocket in target_set:
                self._bindings.pop(websocket, None)
