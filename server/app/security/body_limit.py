"""ASGI request-body limits.

Content-Length checks alone are not enough because a client can use chunked
transfer encoding.  This middleware counts actual bytes as they arrive.
"""
from __future__ import annotations

from starlette.responses import JSONResponse


MAX_JSON_BODY_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        limit = MAX_JSON_BODY_BYTES if content_type == "application/json" else MAX_REQUEST_BODY_BYTES

        raw_length = headers.get("content-length", "").strip()
        if raw_length:
            try:
                if int(raw_length) > limit:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        method = str(scope.get("method", "")).upper()
        needs_prebuffer = method in {"POST", "PUT", "PATCH", "DELETE"} and (
            content_type == "application/json" or not raw_length
        )
        if needs_prebuffer:
            body = await self._read_body(receive, limit)
            if body is None:
                await self._reject(scope, receive, send)
                return

            replay_done = False

            async def replay_receive():
                nonlocal replay_done
                if not replay_done:
                    replay_done = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            await self.app(scope, replay_receive, send)
            return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge()
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(scope, receive, send)

    @staticmethod
    async def _read_body(receive, limit: int) -> bytes | None:
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return None
            if message.get("type") != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    @staticmethod
    async def _reject(scope, receive, send) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "detail": {
                    "code": "payload_too_large",
                    "message": "Request body is too large",
                }
            },
        )
        await response(scope, receive, send)
