from __future__ import annotations

import json
from time import monotonic

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.models import ClientKind, MessageDraft
from app.realtime import ChatRealtimeBroker, chat_message_event, chat_message_payload
from app.services.auth import AuthError, AuthService
from app.services.chat import ChatError, ChatService
from app.services.presence import presence
from app.api._automod import moderate_message
from pydantic import BaseModel, Field


router = APIRouter(tags=["realtime"])
MAX_WS_FRAME_BYTES = 64 * 1024


class OnlineCheckRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


@router.post("/realtime/online")
async def get_online_users(payload: OnlineCheckRequest, request: Request):
    """Return list of user IDs with active WebSocket connections."""
    # Verify admin
    auth = _auth_service(request)
    try:
        session = auth.get_session(payload.session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail={"code": exc.code, "message": exc.message})
    if session.user.role not in {"admin", "moderator"}:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Admin or moderator required"})
    broker = request.app.state.realtime_broker
    # WebSocket connections plus recent authenticated activity (the web SPA
    # talks over HTTP polling, so presence is the main source there).
    online_ids = sorted(set(broker.online_users()) | set(presence.online_user_ids()))
    return {"status": "ok", "online_user_ids": online_ids, "count": len(online_ids)}



def _auth_service(websocket: WebSocket) -> AuthService:
    data_layer = websocket.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _chat_service(websocket: WebSocket) -> ChatService:
    data_layer = websocket.app.state.data_layer
    return ChatService(db_path=data_layer.database_path)


def _broker(websocket: WebSocket) -> ChatRealtimeBroker:
    return websocket.app.state.realtime_broker


def _message_payload(message: dict[str, object]) -> dict[str, object]:
    return {
        "type": "chat.message",
        "message": message,
    }


def _messages_payload(messages: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "chat.history",
        "items": messages,
        "count": len(messages),
    }


def _error_payload(code: str, message: str) -> dict[str, object]:
    return {
        "type": "error",
        "error": {
            "code": code,
            "message": message,
        },
    }


def _ws_event_rate_limited(
    websocket: WebSocket,
    *,
    user_id: int,
    client_ip: str,
) -> bool:
    now_ms = int(monotonic() * 1000)
    user_limiter = getattr(websocket.app.state, "ws_user_limiter", None)
    if user_limiter is not None:
        decision = user_limiter.check(
            ip_address=f"user:{user_id}",
            path="/realtime/chat/event",
            now_ms=now_ms,
        )
        if not decision.allowed:
            return True
    ip_limiter = getattr(websocket.app.state, "ws_ip_limiter", None)
    if ip_limiter is not None:
        decision = ip_limiter.check(
            ip_address=f"ip:{client_ip or 'unknown'}",
            path="/realtime/chat/event",
            now_ms=now_ms,
        )
        if not decision.allowed:
            return True
    return False


def _to_message_dict(chat_message: object) -> dict[str, object]:
    from app.models import ChatMessage

    if not isinstance(chat_message, ChatMessage):
        raise TypeError("chat_message must be ChatMessage")

    return chat_message_payload(chat_message)


@router.websocket("/realtime/chat/{chat_id}")
async def realtime_chat(websocket: WebSocket, chat_id: int) -> None:
    await websocket.accept()

    client_ip = websocket.client.host if websocket.client is not None else ""
    limiter = getattr(websocket.app.state, "rate_limiter", None)
    if limiter is not None:
        decision = limiter.check(
            ip_address=client_ip or "unknown",
            path=f"/realtime/chat/{chat_id}",
            now_ms=int(monotonic() * 1000),
        )
        if not decision.allowed:
            await websocket.send_json(
                _error_payload("rate_limited", "Too many WebSocket handshake attempts")
            )
            await websocket.close(code=4429)
            return

    session_token = (websocket.query_params.get("session_token") or "").strip()
    if not session_token:
        await websocket.send_json(_error_payload("missing_session", "session_token is required"))
        await websocket.close(code=4401)
        return

    auth_service = _auth_service(websocket)
    chat_service = _chat_service(websocket)
    broker = _broker(websocket)

    try:
        session = auth_service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        await websocket.send_json(_error_payload(exc.code, exc.message))
        await websocket.close(code=4401)
        return

    if session.user.user_id is None:
        await websocket.send_json(_error_payload("invalid_user", "Authenticated user id is missing"))
        await websocket.close(code=4401)
        return

    user_id = session.user.user_id

    try:
        _ = chat_service.list_messages(
            chat_id=chat_id,
            requester_user_id=user_id,
            limit=1,
            offset=0,
        )
    except ChatError as exc:
        await websocket.send_json(_error_payload(exc.code, exc.message))
        await websocket.close(code=4403)
        return

    connected = await broker.connect(
        chat_id=chat_id,
        websocket=websocket,
        user_id=user_id,
        session_id=session.session.token,
        expires_at_ms=session.session.expires_at_ms,
        ip_address=client_ip,
        device_id=session.session.device_id,
    )
    if not connected:
        return
    await websocket.send_json(
        {
            "type": "realtime.connected",
            "chat_id": chat_id,
            "user_id": user_id,
        }
    )

    def refresh_session() -> bool:
        nonlocal session
        try:
            session = auth_service.get_session(session_token, client_kind=ClientKind.WEB)
        except AuthError:
            return False
        return session.user.user_id == user_id

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except KeyError:
                await websocket.send_json(
                    _error_payload("invalid_frame", "Only text WebSocket frames are supported")
                )
                continue
            if not refresh_session():
                await websocket.send_json(
                    _error_payload("invalid_session", "Session is no longer valid")
                )
                await websocket.close(code=4401)
                return
            if len(raw.encode("utf-8")) > MAX_WS_FRAME_BYTES:
                await websocket.send_json(
                    _error_payload("frame_too_large", "WebSocket frame exceeds 64KB")
                )
                await websocket.close(code=1009)
                return
            try:
                payload = json.loads(raw)
            except (ValueError, KeyError):
                await websocket.send_json(
                    _error_payload("invalid_json", "WebSocket frame must be valid JSON")
                )
                continue
            if not isinstance(payload, dict):
                await websocket.send_json(
                    _error_payload("invalid_payload", "WebSocket frame must be a JSON object")
                )
                continue
            event_type = str(payload.get("type", "")).strip().lower()

            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if _ws_event_rate_limited(
                websocket,
                user_id=user_id,
                client_ip=client_ip,
            ):
                await websocket.send_json(
                    _error_payload(
                        "rate_limited",
                        "Too many realtime events; slow down",
                    )
                )
                continue

            if event_type == "chat.history":
                try:
                    limit = int(payload.get("limit", 100))
                    offset = int(payload.get("offset", 0))
                except (TypeError, ValueError):
                    await websocket.send_json(
                        _error_payload("invalid_history_query", "limit and offset must be integers")
                    )
                    continue

                try:
                    messages = chat_service.list_messages(
                        chat_id=chat_id,
                        requester_user_id=user_id,
                        limit=limit,
                        offset=offset,
                    )
                except ChatError as exc:
                    await websocket.send_json(_error_payload(exc.code, exc.message))
                    continue

                await websocket.send_json(
                    _messages_payload([_to_message_dict(message) for message in messages])
                )
                continue

            if event_type == "chat.send":
                body_text = str(payload.get("body_text", ""))
                client_message_id_raw = payload.get("client_message_id")
                client_message_id = (
                    str(client_message_id_raw).strip()
                    if client_message_id_raw is not None
                    else None
                )
                if client_message_id == "":
                    client_message_id = None

                try:
                    draft = MessageDraft(
                        body_text=body_text,
                        client_message_id=client_message_id,
                    )
                    message = chat_service.send_message(
                        chat_id=chat_id,
                        author_user_id=user_id,
                        draft=draft,
                    )
                except (ChatError, ValueError) as exc:
                    if isinstance(exc, ChatError):
                        await websocket.send_json(_error_payload(exc.code, exc.message))
                    else:
                        await websocket.send_json(
                            _error_payload("invalid_message", str(exc))
                        )
                    continue

                event = chat_message_event(message)
                delivered = await broker.publish(chat_id=chat_id, event=event)
                await websocket.send_json(
                    {
                        "type": "chat.ack",
                        "message": _to_message_dict(message),
                        "delivered_to": delivered,
                    }
                )
                moderate_message(websocket.app, message)
                continue

            await websocket.send_json(
                _error_payload(
                    "unsupported_event",
                    "Supported events: ping, chat.history, chat.send",
                )
            )
    except WebSocketDisconnect:
        return
    finally:
        await broker.disconnect(chat_id=chat_id, websocket=websocket)
